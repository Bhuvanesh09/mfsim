# mutual_fund_backtester/backtester/simulator.py

import pandas as pd
import numpy as np
from datetime import timedelta
from mfsim.utils.data_loader import MfApiDataLoader, get_lowerbound_date
from mfsim.utils.logger import setup_logger
from mfsim.metrics.metrics_collection import (
    TotalReturnMetric,
    SharpeRatioMetric,
    MaximumDrawdownMetric,
    SortinoRatioMetric,
)
from mfsim.strategies.base_strategy import BaseStrategy


class Simulator:
    def __init__(
        self,
        start_date,
        end_date,
        initial_investment,
        strategy: BaseStrategy,
        sip_amount=0,
        sip_frequency="monthly",
        data_loader=None,
        **kwargs
    ):
        """
        Initialize the Simulator.

        :param start_date: Simulation start date (string 'YYYY-MM-DD')
        :param end_date: Simulation end date (string 'YYYY-MM-DD')
        :param initial_investment: Initial investment amount (float)
        :param strategy: Strategy instance
        :param sip_amount: SIP amount per period (float)
        :param sip_frequency: SIP frequency (e.g., 'monthly')
        :param data_loader: (optional) Custom DataLoader instance. If None, defaults to MfApiDataLoader.
        """
        self.start_date = pd.to_datetime(start_date)
        self.end_date = pd.to_datetime(end_date)
        self.initial_investment = initial_investment
        self.strategy = strategy
        self.sip_amount = sip_amount
        self.sip_frequency = sip_frequency
        self.logger = setup_logger()
        if data_loader is None:
            self.data_loader = MfApiDataLoader()
        else:
            from mfsim.utils.data_loader import BaseDataLoader

            assert isinstance(
                data_loader, BaseDataLoader
            ), f"data_loader must be an instance of BaseDataLoader, got {type(data_loader)}"
            self.data_loader = data_loader
        self.fund_list = self.strategy.fund_list
        self.nav_data = self._load_all_nav_data()
        self.start_date = get_lowerbound_date(
            self.nav_data[self.fund_list[0]], self.start_date
        )
        self.portfolio_history = []
        self.metrics_results = {}

    @property
    def current_portfolio(self):
        df = pd.DataFrame.from_records(self.portfolio_history, index="date")
        # remove the date index, and amount column
        df = df.drop(columns=["amount"])
        return df.groupby("fund_name")["units"].sum().to_dict()

    @property
    def portfolio_history_df(self):
        return pd.DataFrame.from_records(self.portfolio_history, index="date")

    def _load_all_nav_data(self):
        nav_data = {}
        for fund in self.fund_list:
            nav_data[fund] = self.data_loader.load_nav_data(fund)
            nav_data[fund]["date"] = pd.to_datetime(
                nav_data[fund]["date"], format="%d-%m-%Y"
            )
            nav_data[fund]["nav"] = nav_data[fund]["nav"].astype(float)
            nav_data[fund].set_index("date", inplace=True)
        return nav_data

    def calculate_units_for_amount(self, fund_name, date, amount):
        try:
            # Get NAV on the date
            nav = self.nav_data[fund_name].loc[date]["nav"]
        except KeyError:
            raise ValueError(f"NAV data not available for {fund_name} on {date}")
        # Calculate units
        units = float(amount / nav)
        return units

    def make_purchase(self, fund_name, date, amount):
        # Calculate units
        units = self.calculate_units_for_amount(fund_name, date, amount)
        # Update portfolio
        self.portfolio_history.append(
            {
                "fund_name": fund_name,
                "date": date,
                "units": units,
                "amount": amount,
            }
        )
        self.logger.info(
            f"Purchased {units} units of {fund_name} on {date.date()} for {amount}"
        )

    def _initialize_portfolio(self):
        # Equally allocate initial investment to all funds
        allocation = self.strategy.allocate_money(
            self.initial_investment, self.nav_data, self.start_date
        )

        for fund, amount in allocation.items():
            self.make_purchase(fund, self.start_date, amount)

    def _apply_sip(self, current_date):
        if self.sip_amount > 0:
            # Equally distribute SIP amount to all funds
            allocation = self.strategy.allocate_money(
                self.sip_amount, self.nav_data, current_date
            )
            for fund, amount in allocation.items():
                self.make_purchase(fund, current_date, amount)

            self.logger.info(
                f"Applied SIP of {self.sip_amount} on {current_date.date()}"
            )

    def run(self):
        self._initialize_portfolio()
        current_date = self.start_date

        # Create a date range
        all_dates = pd.date_range(start=self.start_date, end=self.end_date, freq="D")

        # print(f"the dates to iterate over are: {all_dates}")
        # Iterate through each date
        for date in all_dates:
            if date not in self.nav_data[self.fund_list[0]].index:
                # self.logger.info(f\"Couldn't find date {date} in the index\")
                # Skip if NAV data is not available for this date
                continue

            # Let the strategy update the SIP amount if applicable
            if self.sip_amount > 0: # Only update if there's an SIP to begin with
                self.sip_amount = self.strategy.update_sip_amount(date, self.sip_amount)

            # Apply SIP
            if self.sip_amount > 0:
                if self._is_sip_date(date):
                    portfolio = self._apply_sip(date)

            # Rebalance if needed
            if self._is_rebalance_date(date):
                self.logger.info(f"Rebalancing on {date.date()}")
                current_portfolio = self.current_portfolio  # Get current portfolio
                orders = self.strategy.rebalance(current_portfolio, self.nav_data, date)
                for order in orders:
                    fund_name = order["fund_name"]
                    amount = order["amount"]
                    self.make_purchase(fund_name, date, amount)
        # After simulation, calculate metrics
        self._calculate_metrics()

        return self.metrics_results

    def _is_rebalance_date(self, date):
        freq = self.strategy.frequency.lower()
        if freq == "daily":
            return True
        elif freq == "weekly":
            return date.weekday() == 0  # Rebalance on Mondays
        elif freq == "monthly":
            return date.day == 1  # Rebalance on the first day of the month
        elif freq == "quarterly":
            return (
                date.month in [1, 4, 7, 10] and date.day == 1
            )  # Rebalance on the first day of January, April, July, October
        elif freq == "semi-annually":
            return (
                date.month in [1, 7] and date.day == 1
            )  # Rebalance on the first day of January and July
        elif freq == "annually":
            return (
                date.month == 1 and date.day == 1
            )  # Rebalance on the first day of January
        else:
            return False

    def _is_sip_date(self, date):
        freq = self.sip_frequency.lower()
        if freq == "daily":
            return True
        elif freq == "weekly":
            return date.weekday() == 0
        elif freq == "monthly":
            return date == date.replace(day=1)
        else:
            return False

    def _calculate_metrics(self):
        # Initialize metrics
        metrics_instances = []
        for metric_name in self.strategy.metrics:
            if metric_name.lower() == "total return":
                metrics_instances.append(TotalReturnMetric())
            elif metric_name.lower() == "sharpe ratio":
                metrics_instances.append(SharpeRatioMetric(frequency="daily"))
            elif metric_name.lower() == "maximum drawdown":
                metrics_instances.append(MaximumDrawdownMetric())
            elif metric_name.lower() == "sortino ratio":
                metrics_instances.append(
                    SortinoRatioMetric(frequency=self.strategy.frequency)
                )
            else:
                self.logger.warning(f"Unknown metric: {metric_name}")

        # Calculate each metric
        for metric in metrics_instances:
            metric_name = metric.__class__.__name__.replace("Metric", "").replace(
                "_", " "
            )
            self.metrics_results[metric_name] = metric.calculate(
                self.portfolio_history_df,
                self.current_portfolio,
                self.end_date,
                self.nav_data,
            )
            self.logger.info(f"{metric_name}: {self.metrics_results[metric_name]}")

    def get_portfolio_history(self):
        return self.portfolio_history

    def get_metrics(self):
        return self.metrics_results

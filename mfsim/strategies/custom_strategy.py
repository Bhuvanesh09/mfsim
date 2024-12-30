# mutual_fund_backtester/strategies/custom_strategy.py

import pandas as pd
from .base_strategy import BaseStrategy
from ..utils.data_loader import get_lowerbound_date


class MomentumValueStrategy(BaseStrategy):
    def __init__(
        self, frequency, metrics, value_fund, momentum_fund, momentum_period=180
    ):
        """
        Initialize the MomentumValueStrategy.

        :param frequency: Rebalancing frequency (e.g., 'monthly')
        :param metrics: List of metrics to track
        :param momentum_period: Number of days to consider for momentum calculation
        """
        super().__init__(frequency, metrics, [value_fund, momentum_fund])
        self.value_fund = value_fund
        self.momentum_fund = momentum_fund
        self.momentum_period = momentum_period

    def allocate_money(self, money_invested, nav_data, current_date):
        return super().allocate_money(money_invested, nav_data, current_date)

    def rebalance(self, portfolio, nav_data, current_date):
        """
        Rebalance between momentum and value funds based on past performance.

        :param portfolio: Current portfolio holdings (dict of fund: units)
        :param nav_data: Dictionary of NAV series for each fund
        :param current_date: The current date in simulation
        :return: Updated portfolio holdings
        """
        # Assuming two funds: 'Momentum Fund' and 'Value Fund'
        momentum_fund = self.momentum_fund
        value_fund = self.value_fund

        # Calculate momentum for both funds
        start_date = current_date - pd.Timedelta(days=self.momentum_period)
        start_date = get_lowerbound_date(nav_data[momentum_fund], start_date)
        current_date = get_lowerbound_date(nav_data[momentum_fund], current_date)
        try:
            momentum_returns = (
                nav_data[momentum_fund]["nav"].loc[current_date]
                / nav_data[momentum_fund]["nav"].loc[start_date]
            ) - 1
            value_returns = (
                nav_data[value_fund]["nav"].loc[current_date]
                / nav_data[value_fund]["nav"].loc[start_date]
            ) - 1
        except KeyError as e:
            raise ValueError(f"Missing NAV data for {e}")

        orders = []

        # Simple rule: Allocate more to the better performing fund
        if momentum_returns > value_returns:
            # Shift 10% from value to momentum
            shift_amount = (
                0.1
                * portfolio.get(value_fund, 0)
                * nav_data[value_fund]["nav"].loc[current_date].astype(float)
            )
            orders.append(
                {
                    "fund_name": value_fund,
                    "amount": -shift_amount,
                    "date": current_date,
                }
            )
            orders.append(
                {
                    "fund_name": momentum_fund,
                    "amount": shift_amount,
                    "date": current_date,
                }
            )
        else:
            # Shift 10% from momentum to value
            shift_amount = (
                0.1
                * portfolio.get(momentum_fund, 0)
                * nav_data[momentum_fund]["nav"].loc[current_date].astype(float)
            )
            orders.append(
                {
                    "fund_name": value_fund,
                    "amount": shift_amount,
                    "date": current_date,
                }
            )
            orders.append(
                {
                    "fund_name": momentum_fund,
                    "amount": -shift_amount,
                    "date": current_date,
                }
            )

        return orders

# mutual_fund_backtester/metrics/metrics_collection.py

import numpy as np
import pandas as pd
from .base_metric import BaseMetric


class TotalReturnMetric(BaseMetric):
    def calculate(self, portfolio_history, current_portfolio, date, nav_data):
        """
        Calculate the total return of the portfolio.

        :param portfolio_history: DataFrame containing portfolio values over time.
            Columns:
            - date: Date of the transaction
            - fund_name: Name of the fund
            - units: Number of units purchased/sold
            - amount: Amount invested/withdrawn

        :param current_portfolio: Dictionary of current portfolio holdings
            Key: Fund name (string)
            Value: Number of units held (float)

        :param date: The current date in simulation (datetime object)

        :param nav_data: Dictionary of NAV series for each fund
            Key: Fund name (string)
            Value: DataFrame with columns:
                - date: Date of NAV
                - nav: Net Asset Value on that date

        :return: Float representing the total return of the portfolio
        """

        money_invested = portfolio_history["amount"].sum()
        final_value = 0
        for fund, units in current_portfolio.items():
            final_value += units * nav_data[fund]["nav"].loc[date]
        total_return = (final_value / money_invested) - 1
        return float(total_return)


class SharpeRatioMetric(BaseMetric):
    def __init__(self, risk_free_rate=0.06, frequency="daily"):
        """
        Initialize the SharpeRatioMetric.

        :param risk_free_rate: Annual risk-free rate as a decimal (default 6%).
        :param frequency: Frequency of returns ('daily', 'monthly', etc.).
        """
        self.risk_free_rate = risk_free_rate
        self.frequency = frequency

    def calculate(self, portfolio_history, current_portfolio, date, nav_data):
        """
        Calculate the Sharpe Ratio of the portfolio.

        :param portfolio_history: DataFrame containing portfolio transactions.
        :param current_portfolio: Dictionary of current portfolio holdings.
        :param date: The current date in simulation (datetime object).
        :param nav_data: Dictionary of NAV series for each fund.
        :return: Float representing the Sharpe Ratio of the portfolio.
        """
        portfolio_values = self._compute_portfolio_value_history(
            portfolio_history, nav_data, date
        )
        if portfolio_values.empty or len(portfolio_values) < 2:
            return np.nan  # Not enough data to compute returns

        # Calculate daily returns
        portfolio_values = portfolio_values.sort_index()
        daily_returns = portfolio_values.pct_change().dropna()

        # Compute excess returns
        if self.frequency == "daily":
            rf_daily = self.risk_free_rate / 252
            scaling_factor = np.sqrt(252)
        elif self.frequency == "monthly":
            rf_daily = self.risk_free_rate / 12
            scaling_factor = np.sqrt(12)
        else:
            raise ValueError("Unsupported frequency. Use 'daily' or 'monthly'.")

        excess_returns = daily_returns - rf_daily

        mean_excess_return = excess_returns.mean()
        std_excess_return = excess_returns.std()

        if std_excess_return == 0:
            return np.nan  # Avoid division by zero

        sharpe_ratio = (mean_excess_return / std_excess_return) * scaling_factor
        return float(sharpe_ratio)

    def _compute_portfolio_value_history(
        self, portfolio_history, nav_data, current_date
    ):
        """
        Reconstruct the portfolio value over time up to the current date.

        :param portfolio_history: DataFrame containing portfolio transactions.
        :param nav_data: Dictionary of NAV series for each fund.
        :param current_date: The current date in simulation (datetime object).
        :return: Pandas Series with dates as index and portfolio value as values.
        """
        # Initialize an empty DataFrame for holdings over time
        holdings = {}
        value_history = []

        # Ensure portfolio_history is sorted by date
        portfolio_history = portfolio_history.sort_values("date")

        # Get all relevant dates up to current_date
        all_dates = pd.date_range(
            start=portfolio_history.index.min(), end=current_date, freq="D"
        )

        # Initialize holdings DataFrame
        holdings_df = pd.DataFrame(index=all_dates, columns=nav_data.keys()).fillna(0.0)

        # Process each transaction
        for txn_date, row in portfolio_history.iterrows():
            if txn_date > current_date:
                continue
            fund = row["fund_name"]
            units = row["units"]
            holdings_df.loc[txn_date:, fund] += units

        # Calculate portfolio value for each date
        portfolio_values = pd.Series(index=all_dates, dtype=float)
        for fund, nav_df in nav_data.items():
            # Merge NAV data with all_dates
            nav_df = nav_df[nav_df.index <= current_date]
            holdings = holdings_df[fund]
            portfolio_values += holdings * nav_df["nav"]

        portfolio_values = portfolio_values.fillna(0.0)
        return portfolio_values


class MaximumDrawdownMetric(BaseMetric):
    def calculate(self, portfolio_history, nav_data):
        """
        Calculate the Maximum Drawdown of the portfolio.

        :param portfolio_history: DataFrame containing portfolio values over time
        :param nav_data: Dictionary of NAV series for each fund
        :return: Maximum Drawdown as a float
        """
        cumulative = portfolio_history["total"]
        rolling_max = cumulative.cummax()
        drawdown = (cumulative - rolling_max) / rolling_max
        max_drawdown = drawdown.min()
        return max_drawdown


class SortinoRatioMetric(BaseMetric):
    def __init__(self, risk_free_rate=0.05, frequency="daily"):
        self.risk_free_rate = risk_free_rate
        self.frequency = frequency

    def calculate(self, portfolio_history, nav_data):
        """
        Calculate the Sortino Ratio of the portfolio.

        :param portfolio_history: DataFrame containing portfolio values over time
        :param nav_data: Dictionary of NAV series for each fund
        :return: Sortino Ratio as a float
        """
        returns = portfolio_history["total"].pct_change().dropna()
        excess_returns = returns - self.risk_free_rate / self._get_periods_per_year()
        downside_returns = excess_returns[excess_returns < 0]
        expected_return = excess_returns.mean()
        downside_deviation = downside_returns.std()
        sortino_ratio = (
            expected_return / downside_deviation * np.sqrt(self._get_periods_per_year())
        )
        return sortino_ratio

    def _get_periods_per_year(self):
        if self.frequency == "daily":
            return 252
        elif self.frequency == "weekly":
            return 52
        elif self.frequency == "monthly":
            return 12
        else:
            return 252  # default to daily
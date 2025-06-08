# mutual_fund_backtester/metrics/base_metric.py

from abc import ABC, abstractmethod


class BaseMetric(ABC):
    @abstractmethod
    def calculate(self, portfolio_history, current_portfolio, date, nav_data) -> float:
        """
        Calculate the metric of the portfolio.

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

        :return: Float representing the metric of the portfolio
        """
        pass

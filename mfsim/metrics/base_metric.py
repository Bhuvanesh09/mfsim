# mutual_fund_backtester/metrics/base_metric.py

from abc import ABC, abstractmethod


class BaseMetric(ABC):
    @abstractmethod
    def calculate(self, portfolio_history, current_portfolio, date, nav_data) -> float:
        """
        Calculate the metric based on portfolio history.

        :param portfolio_history: DataFrame containing portfolio values over time
        :param nav_data: Dictionary of NAV series for each fund
        :return: Calculated metric value
        """
        pass

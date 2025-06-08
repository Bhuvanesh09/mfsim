# mutual_fund_backtester/strategies/base_strategy.py

from abc import ABC, abstractmethod
import logging


class BaseStrategy(ABC):
    def __init__(self, frequency, metrics, fund_list, **kwargs):
        """
        Initialize the base strategy.

        :param frequency: Rebalancing frequency (e.g., 'monthly', 'weekly')
        :param metrics: List of metrics to track
        """
        self.frequency = frequency
        self.metrics = metrics
        self.logger = logging.getLogger()
        self.fund_list = fund_list

    def allocate_money(self, money_invested, nav_data, current_date):
        num_funds = len(self.fund_list)
        equal_allocation = {fund: money_invested / num_funds for fund in self.fund_list}
        self.logger.info(
            f"Invested {money_invested} equally in {num_funds} funds: {equal_allocation}"
        )
        return equal_allocation

    @abstractmethod
    def rebalance(self, portfolio, nav_data, current_date) -> list[dict]:
        """
        Define the rebalancing logic.

        :param portfolio: Current portfolio holdings
        :param nav_data: Dictionary of NAV series for each fund
        :param current_date: The current date in simulation
        :return: List of order dicts to execute (e.g., [{'fund_name': ..., 'amount': ...}])
            - 'fund_name': Name of the fund
            - 'amount': Amount to buy (>0) or sell (<0)
        """
        pass

    def update_sip_amount(self, current_date, current_sip_amount: float) -> float:
        """
        Allows the strategy to dynamically update the SIP amount.
        By default, returns the current SIP amount without modification.
        Subclasses should override this method to implement custom SIP increase logic.

        :param current_date: The current date in the simulation.
        :param current_sip_amount: The current SIP amount.
        :return: The (potentially) updated SIP amount.
        """
        # self.logger.debug(f"Strategy {self.__class__.__name__} returning SIP amount: {current_sip_amount} for date {current_date}")
        return current_sip_amount

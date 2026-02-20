"""
Abstract base class for investment strategies.

All strategies must subclass :class:`BaseStrategy` and implement
:meth:`rebalance`. Optionally override :meth:`allocate_money` and
:meth:`update_sip_amount` for custom allocation and dynamic SIP logic.

Example — a fixed-allocation strategy::

    from mfsim.strategies.base_strategy import BaseStrategy

    class FixedAllocationStrategy(BaseStrategy):
        def __init__(self, fund_list, allocation):
            super().__init__(
                frequency="quarterly",
                metrics=["Total Return", "XIRR"],
                fund_list=fund_list,
            )
            self.allocation = allocation  # e.g. {"Fund A": 0.6, "Fund B": 0.4}

        def allocate_money(self, money_invested, nav_data, current_date):
            return {
                fund: money_invested * pct
                for fund, pct in self.allocation.items()
            }

        def rebalance(self, portfolio, nav_data, current_date):
            # No rebalancing — just hold
            return []
"""

from abc import ABC, abstractmethod
import logging


class BaseStrategy(ABC):
    """Abstract base class that all strategies must inherit from.

    A strategy defines three things:

    1. **Which funds** to invest in (``fund_list``).
    2. **How to allocate** new money across those funds (``allocate_money``).
    3. **When and how to rebalance** the portfolio (``rebalance``).

    The simulator calls these methods at the appropriate times during the
    backtest — you just implement the logic.

    Args:
        frequency: How often to rebalance. One of ``'daily'``, ``'weekly'``,
            ``'monthly'``, ``'quarterly'``, ``'semi-annually'``, ``'annually'``.
        metrics: List of metric names to compute after simulation. Supported:
            ``'Total Return'``, ``'Sharpe Ratio'``, ``'Maximum Drawdown'``,
            ``'Sortino Ratio'``, ``'XIRR'``.
        fund_list: List of fund names (must match names in the data loader's
            fund database exactly).

    Attributes:
        frequency: Rebalancing frequency string.
        metrics: List of metric names.
        fund_list: List of fund names.
        logger: Python logger instance for the strategy.
    """

    def __init__(self, frequency, metrics, fund_list, **kwargs):
        self.frequency = frequency
        self.metrics = metrics
        self.logger = logging.getLogger()
        self.fund_list = fund_list

    def allocate_money(self, money_invested, nav_data, current_date):
        """Decide how to split new money across funds.

        Called by the simulator for the initial lump sum investment and
        for every SIP installment. The default implementation splits
        money equally across all funds in ``fund_list``.

        Override this to implement custom allocation logic (e.g.,
        weighted allocation, or allocation based on recent performance).

        Args:
            money_invested: Total amount to allocate (in rupees).
            nav_data: Dict mapping fund names to DataFrames with ``date``
                index and ``nav`` column. Use this for performance-based
                allocation decisions.
            current_date: The date of the allocation.

        Returns:
            Dict mapping fund names to the rupee amount allocated to each.
            The values should sum to ``money_invested``.

        Example::

            # Equal allocation (the default)
            {"Fund A": 5000.0, "Fund B": 5000.0}

            # 70/30 split
            {"Fund A": 7000.0, "Fund B": 3000.0}
        """
        num_funds = len(self.fund_list)
        equal_allocation = {fund: money_invested / num_funds for fund in self.fund_list}
        self.logger.info(
            f"Invested {money_invested} equally in {num_funds} funds: {equal_allocation}"
        )
        return equal_allocation

    @abstractmethod
    def rebalance(self, portfolio, nav_data, current_date) -> list[dict]:
        """Define the rebalancing logic. **Must be implemented by subclasses.**

        Called by the simulator on every rebalance date (determined by
        ``frequency``). Receives the current portfolio state and NAV data,
        and returns a list of buy/sell orders.

        Args:
            portfolio: Current holdings as ``{fund_name: total_units}``.
                Units are the sum of all buys minus all sells to date.
            nav_data: Dict mapping fund names to DataFrames with ``date``
                index and ``nav`` column. Contains full historical NAV
                data — use for lookback calculations.
            current_date: The date of the rebalance.

        Returns:
            List of order dicts to execute. Each order has:

            - ``'fund_name'``: Name of the fund.
            - ``'amount'``: Rupee amount. **Positive = buy, negative = sell.**

            Return an empty list ``[]`` to skip rebalancing on this date.

        Example::

            # Shift 10000 from Fund A to Fund B
            [
                {"fund_name": "Fund A", "amount": -10000},
                {"fund_name": "Fund B", "amount": 10000},
            ]
        """
        pass

    def update_sip_amount(self, current_date, current_sip_amount: float) -> float:
        """Hook to dynamically adjust the SIP amount over time.

        Called by the simulator on every trading day when SIP is active
        (``sip_amount > 0``). Override this to implement SIP step-ups
        (e.g., increase SIP by 5% every year).

        The default implementation returns the SIP amount unchanged.

        Args:
            current_date: The current simulation date.
            current_sip_amount: The current SIP amount in rupees.

        Returns:
            The (potentially updated) SIP amount for this date onward.

        Example — 10% annual step-up::

            def update_sip_amount(self, current_date, current_sip_amount):
                if current_date.month == 1 and current_date.day == 1:
                    return current_sip_amount * 1.10
                return current_sip_amount
        """
        return current_sip_amount

"""
Abstract base class for performance metrics.

All metrics subclass :class:`BaseMetric` and implement :meth:`calculate`,
which receives the full simulation state and returns a single float value.

To create a custom metric::

    from mfsim.metrics.base_metric import BaseMetric

    class MyMetric(BaseMetric):
        def calculate(self, portfolio_history, current_portfolio, date, nav_data):
            # Your calculation here
            return some_float_value
"""

from abc import ABC, abstractmethod


class BaseMetric(ABC):
    """Abstract interface for all portfolio performance metrics.

    Metrics are stateless calculators — they receive the full simulation
    state after the backtest completes and return a single numeric value.
    """

    @abstractmethod
    def calculate(self, portfolio_history, current_portfolio, date, nav_data) -> float:
        """Compute the metric value from the simulation results.

        Args:
            portfolio_history: DataFrame of all transactions, indexed by
                ``date``, with columns:

                - ``fund_name`` (str): Name of the fund.
                - ``units`` (float): Units bought (positive) or sold (negative).
                - ``amount`` (float): Rupees invested (positive) or
                  withdrawn (negative).

            current_portfolio: Final holdings as ``{fund_name: total_units}``.
                This is the net sum of all units per fund.
            date: The simulation end date (used to look up final NAV values).
            nav_data: Dict mapping fund names to DataFrames with ``date``
                index and ``nav`` column (float). Contains the full
                historical NAV series for each fund.

        Returns:
            A single float representing the metric value. Return
            ``float('nan')`` if the metric cannot be computed (e.g.,
            insufficient data).
        """
        pass

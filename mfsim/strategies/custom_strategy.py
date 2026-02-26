"""
Built-in strategy: Momentum vs Value rotation.

Compares the trailing returns of a momentum fund and a value fund over
a configurable lookback period, and shifts 10% of holdings toward the
outperformer on each rebalance date.
"""

import pandas as pd
from .base_strategy import BaseStrategy
from ..utils.data_loader import get_lowerbound_date


class MomentumValueStrategy(BaseStrategy):
    """Rotates between a momentum fund and a value fund based on relative performance.

    On each rebalance date, this strategy:

    1. Calculates trailing returns over ``momentum_period`` days for both funds.
    2. If the momentum fund outperformed: shifts 10% of value fund holdings
       into the momentum fund.
    3. If the value fund outperformed: shifts 10% of momentum fund holdings
       into the value fund.

    This is a simple trend-following approach — it assumes recent outperformance
    is likely to continue in the near term.

    Args:
        frequency: Rebalancing frequency (e.g., ``'semi-annually'``).
        metrics: List of metric names to compute after simulation.
        value_fund: Exact name of the value fund (must match the data source).
        momentum_fund: Exact name of the momentum fund.
        momentum_period: Lookback period in calendar days for return
            comparison. Defaults to ``180`` (roughly 6 months).

    Example::

        strategy = MomentumValueStrategy(
            frequency="semi-annually",
            metrics=["Total Return", "XIRR", "Sharpe Ratio"],
            value_fund="NIPPON INDIA NIFTY 50 VALUE 20 INDEX FUND - DIRECT Plan",
            momentum_fund="BANDHAN NIFTY200 MOMENTUM 30 INDEX FUND - DIRECT PLAN",
            momentum_period=180,
        )
    """

    def __init__(self, frequency, metrics, value_fund, momentum_fund, momentum_period=180):
        super().__init__(frequency, metrics, [value_fund, momentum_fund])
        self.value_fund = value_fund
        self.momentum_fund = momentum_fund
        self.momentum_period = momentum_period

    def allocate_money(self, money_invested, nav_data, current_date):
        """Split money equally between the two funds.

        Uses the default equal-weight allocation from
        :meth:`BaseStrategy.allocate_money`.
        """
        return super().allocate_money(money_invested, nav_data, current_date)

    def rebalance(self, portfolio, nav_data, current_date):
        """Shift 10% of holdings toward the better-performing fund.

        Computes trailing returns over ``momentum_period`` days for both
        funds. If one outperformed the other, 10% of the lagging fund's
        current value is sold and used to buy the outperformer.

        Args:
            portfolio: Current holdings as ``{fund_name: total_units}``.
            nav_data: Dict of fund name to NAV DataFrame (date-indexed).
            current_date: The rebalance date.

        Returns:
            List of two orders — one sell and one buy — that shift 10%
            of the underperformer into the outperformer.

        Raises:
            ValueError: If NAV data is missing for the lookback window.
        """
        momentum_fund = self.momentum_fund
        value_fund = self.value_fund

        # Calculate trailing returns over the lookback period
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

        if momentum_returns > value_returns:
            # Momentum outperformed — shift 10% from value to momentum
            shift_amount = (
                0.1
                * portfolio.get(value_fund, 0)
                * nav_data[value_fund]["nav"].loc[current_date].astype(float)
            )
            orders.append({"fund_name": value_fund, "amount": -shift_amount, "date": current_date})
            orders.append(
                {
                    "fund_name": momentum_fund,
                    "amount": shift_amount,
                    "date": current_date,
                }
            )
        else:
            # Value outperformed — shift 10% from momentum to value
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

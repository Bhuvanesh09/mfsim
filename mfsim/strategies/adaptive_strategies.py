"""
Adaptive factor rotation strategies for Experiment 002.

Three strategies that dynamically shift between a value fund and a momentum
fund based on market signals, rather than using fixed 50/50 blends:

- :class:`TrendFilterStrategy` (Option A): uses a simple moving average on a
  reference index to detect risk-on vs risk-off regimes.
- :class:`RelativeStrengthStrategy` (Option B): uses multi-horizon relative
  strength of momentum vs value to tilt allocations.
- :class:`DualSignalStrategy` (Option C): combines both signals — agrees =
  amplify, disagrees = neutral.
"""

from datetime import timedelta

import numpy as np

from .base_strategy import BaseStrategy

# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

_DEFAULT_METRICS = ["Total Return", "XIRR", "Maximum Drawdown", "Sharpe Ratio", "Sortino Ratio"]


def _to_target_orders(portfolio, nav_data, current_date, target_weights):
    """Hard-rebalance to target_weights using last available NAV.

    Safe for non-trading days: uses the most recent NAV on or before
    ``current_date`` for portfolio valuation, then emits buy/sell orders
    to hit the target allocation.

    Args:
        portfolio: Current holdings ``{fund_name: total_units}``.
        nav_data: Dict mapping fund names to date-indexed NAV DataFrames.
        current_date: Rebalance date.
        target_weights: ``{fund_name: weight}`` — must sum to 1.0 for the
            funds in the dict (trend reference funds should be omitted).

    Returns:
        List of order dicts ``{"fund_name": ..., "amount": ...}`` where
        positive amount = buy, negative = sell. Orders under ₹1 are skipped.
    """
    navs, total_value = {}, 0.0
    for fund in target_weights:
        avail = nav_data[fund][nav_data[fund].index <= current_date]["nav"]
        if avail.empty:
            continue
        nav = float(avail.iloc[-1])
        navs[fund] = nav
        total_value += portfolio.get(fund, 0) * nav

    orders = []
    for fund, pct in target_weights.items():
        nav = navs.get(fund)
        if nav is None:
            continue
        diff = total_value * pct - portfolio.get(fund, 0) * nav
        if abs(diff) > 1.0:
            orders.append({"fund_name": fund, "amount": diff})
    return orders


# ---------------------------------------------------------------------------
# Option A: TrendFilterStrategy
# ---------------------------------------------------------------------------


class TrendFilterStrategy(BaseStrategy):
    """Allocate between value and momentum based on a trend-filter regime.

    Uses a simple moving average (SMA) over ``ma_window`` days on a reference
    index (``trend_fund``). If the index is above its SMA → risk-on (tilt to
    momentum); if below → risk-off (tilt to value). Equal-weight when there is
    insufficient history.

    The trend fund is loaded for signal computation but **never traded**.

    Args:
        value_fund: Exact fund name for the value index fund.
        momentum_fund: Exact fund name for the momentum index fund.
        trend_fund: Exact fund name for the reference index (e.g. Nifty 50).
        ma_window: Number of trading days for the SMA. Default 200.
        risk_on_m_weight: Momentum weight when regime is risk-on. Default 0.7.
        risk_off_m_weight: Momentum weight when regime is risk-off. Default 0.3.
        frequency: Rebalancing frequency. Default ``'monthly'``.
        metrics: List of metric names. Defaults to the standard four.
    """

    def __init__(
        self,
        value_fund,
        momentum_fund,
        trend_fund,
        ma_window=200,
        risk_on_m_weight=0.7,
        risk_off_m_weight=0.3,
        frequency="monthly",
        metrics=None,
    ):
        metrics = metrics or _DEFAULT_METRICS
        super().__init__(frequency, metrics, [value_fund, momentum_fund, trend_fund])
        self.value_fund = value_fund
        self.momentum_fund = momentum_fund
        self.trend_fund = trend_fund
        self.ma_window = ma_window
        self.risk_on_m_weight = risk_on_m_weight
        self.risk_off_m_weight = risk_off_m_weight

    def _regime(self, nav_data, date):
        """Return ``'risk_on'``, ``'risk_off'``, or ``'neutral'``.

        Compares the latest NAV of the trend fund against its ``ma_window``-day
        SMA. Returns ``'neutral'`` when there is insufficient history.
        """
        avail = nav_data[self.trend_fund][nav_data[self.trend_fund].index <= date]["nav"]
        if len(avail) < self.ma_window:
            return "neutral"
        sma = float(avail.iloc[-self.ma_window :].mean())
        current = float(avail.iloc[-1])
        return "risk_on" if current >= sma else "risk_off"

    def _momentum_weight(self, nav_data, date):
        """Return the momentum fund weight for the current regime."""
        regime = self._regime(nav_data, date)
        if regime == "risk_on":
            return self.risk_on_m_weight
        if regime == "risk_off":
            return self.risk_off_m_weight
        return 0.5  # neutral

    def allocate_money(self, money, nav_data, date):
        m_w = self._momentum_weight(nav_data, date)
        return {self.value_fund: money * (1.0 - m_w), self.momentum_fund: money * m_w}

    def rebalance(self, portfolio, nav_data, date):
        m_w = self._momentum_weight(nav_data, date)
        target = {self.value_fund: 1.0 - m_w, self.momentum_fund: m_w}
        return _to_target_orders(portfolio, nav_data, date, target)


# ---------------------------------------------------------------------------
# Option B: RelativeStrengthStrategy
# ---------------------------------------------------------------------------


class RelativeStrengthStrategy(BaseStrategy):
    """Allocate based on multi-horizon relative strength of momentum vs value.

    Computes a weighted average of momentum-vs-value return edges across
    multiple lookback horizons. The edge drives the momentum weight via:

    ``m_weight = clip(0.5 + sensitivity * weighted_edge, min_weight, max_weight)``

    Horizons without sufficient data are skipped and the remaining weights are
    renormalized.

    Args:
        value_fund: Exact fund name for the value index fund.
        momentum_fund: Exact fund name for the momentum index fund.
        horizon_weights: ``{days: weight}`` for lookback horizons. Weights need
            not sum to 1 — they are normalized over available horizons.
            Default ``{30: 0.2, 90: 0.3, 180: 0.5}``.
        sensitivity: Scales how aggressively the edge shifts the weight.
            Higher = more extreme tilts. Default 1.0.
        min_weight: Floor on momentum weight. Default 0.2.
        max_weight: Ceiling on momentum weight. Default 0.8.
        frequency: Rebalancing frequency. Default ``'monthly'``.
        metrics: List of metric names. Defaults to the standard four.
    """

    def __init__(
        self,
        value_fund,
        momentum_fund,
        horizon_weights=None,
        sensitivity=1.0,
        min_weight=0.2,
        max_weight=0.8,
        frequency="monthly",
        metrics=None,
    ):
        metrics = metrics or _DEFAULT_METRICS
        super().__init__(frequency, metrics, [value_fund, momentum_fund])
        self.value_fund = value_fund
        self.momentum_fund = momentum_fund
        self.horizon_weights = horizon_weights if horizon_weights is not None else {30: 0.2, 90: 0.3, 180: 0.5}
        self.sensitivity = sensitivity
        self.min_weight = min_weight
        self.max_weight = max_weight

    def _momentum_weight(self, nav_data, date):
        """Compute momentum fund weight from multi-horizon relative strength."""
        weighted_edge = 0.0
        total_weight = 0.0
        for horizon, w in self.horizon_weights.items():
            past_target = date - timedelta(days=horizon)
            m_now = nav_data[self.momentum_fund][nav_data[self.momentum_fund].index <= date]["nav"]
            v_now = nav_data[self.value_fund][nav_data[self.value_fund].index <= date]["nav"]
            m_then = nav_data[self.momentum_fund][nav_data[self.momentum_fund].index <= past_target]["nav"]
            v_then = nav_data[self.value_fund][nav_data[self.value_fund].index <= past_target]["nav"]
            if m_now.empty or v_now.empty or m_then.empty or v_then.empty:
                continue
            m_ret = float(m_now.iloc[-1]) / float(m_then.iloc[-1]) - 1
            v_ret = float(v_now.iloc[-1]) / float(v_then.iloc[-1]) - 1
            weighted_edge += (m_ret - v_ret) * w
            total_weight += w
        if total_weight == 0.0:
            return 0.5
        weighted_edge /= total_weight
        return float(np.clip(0.5 + self.sensitivity * weighted_edge, self.min_weight, self.max_weight))

    def allocate_money(self, money, nav_data, date):
        m_w = self._momentum_weight(nav_data, date)
        return {self.value_fund: money * (1.0 - m_w), self.momentum_fund: money * m_w}

    def rebalance(self, portfolio, nav_data, date):
        m_w = self._momentum_weight(nav_data, date)
        target = {self.value_fund: 1.0 - m_w, self.momentum_fund: m_w}
        return _to_target_orders(portfolio, nav_data, date, target)


# ---------------------------------------------------------------------------
# Option C: DualSignalStrategy
# ---------------------------------------------------------------------------


class DualSignalStrategy(BaseStrategy):
    """Combine trend-filter regime and relative-strength signal.

    Agreement logic:

    - Both risk-on AND rs_weight >= 0.5 → amplify momentum:
      ``m_w = min(rs_weight, max_weight)``
    - Both risk-off AND rs_weight < 0.5 → amplify value:
      ``m_w = max(rs_weight, min_weight)``
    - Disagree → neutral: ``m_w = 0.5``

    Then clip to ``[min_weight, max_weight]``.

    Args:
        value_fund: Exact fund name for the value index fund.
        momentum_fund: Exact fund name for the momentum index fund.
        trend_fund: Exact fund name for the reference index (never traded).
        ma_window: SMA window for trend filter. Default 200.
        risk_on_m_weight: (Unused directly — signals drive the weight; kept for
            documentation.) Default 0.7.
        risk_off_m_weight: (Unused directly.) Default 0.3.
        horizon_weights: Horizon weights for relative strength. Default
            ``{30: 0.2, 90: 0.3, 180: 0.5}``.
        sensitivity: Relative-strength sensitivity. Default 1.0.
        min_weight: Floor on momentum weight. Default 0.2.
        max_weight: Ceiling on momentum weight. Default 0.8.
        frequency: Rebalancing frequency. Default ``'monthly'``.
        metrics: List of metric names. Defaults to the standard four.
    """

    def __init__(
        self,
        value_fund,
        momentum_fund,
        trend_fund,
        ma_window=200,
        risk_on_m_weight=0.7,
        risk_off_m_weight=0.3,
        horizon_weights=None,
        sensitivity=1.0,
        min_weight=0.2,
        max_weight=0.8,
        frequency="monthly",
        metrics=None,
    ):
        metrics = metrics or _DEFAULT_METRICS
        super().__init__(frequency, metrics, [value_fund, momentum_fund, trend_fund])
        self.value_fund = value_fund
        self.momentum_fund = momentum_fund
        self.trend_fund = trend_fund
        self.ma_window = ma_window
        self.risk_on_m_weight = risk_on_m_weight
        self.risk_off_m_weight = risk_off_m_weight
        self.horizon_weights = horizon_weights if horizon_weights is not None else {30: 0.2, 90: 0.3, 180: 0.5}
        self.sensitivity = sensitivity
        self.min_weight = min_weight
        self.max_weight = max_weight

    def _regime(self, nav_data, date):
        """Return trend-filter regime: ``'risk_on'``, ``'risk_off'``, or ``'neutral'``."""
        avail = nav_data[self.trend_fund][nav_data[self.trend_fund].index <= date]["nav"]
        if len(avail) < self.ma_window:
            return "neutral"
        sma = float(avail.iloc[-self.ma_window :].mean())
        current = float(avail.iloc[-1])
        return "risk_on" if current >= sma else "risk_off"

    def _rs_weight(self, nav_data, date):
        """Raw relative-strength momentum weight (before clipping)."""
        weighted_edge = 0.0
        total_weight = 0.0
        for horizon, w in self.horizon_weights.items():
            past_target = date - timedelta(days=horizon)
            m_now = nav_data[self.momentum_fund][nav_data[self.momentum_fund].index <= date]["nav"]
            v_now = nav_data[self.value_fund][nav_data[self.value_fund].index <= date]["nav"]
            m_then = nav_data[self.momentum_fund][nav_data[self.momentum_fund].index <= past_target]["nav"]
            v_then = nav_data[self.value_fund][nav_data[self.value_fund].index <= past_target]["nav"]
            if m_now.empty or v_now.empty or m_then.empty or v_then.empty:
                continue
            m_ret = float(m_now.iloc[-1]) / float(m_then.iloc[-1]) - 1
            v_ret = float(v_now.iloc[-1]) / float(v_then.iloc[-1]) - 1
            weighted_edge += (m_ret - v_ret) * w
            total_weight += w
        if total_weight == 0.0:
            return 0.5
        return 0.5 + self.sensitivity * (weighted_edge / total_weight)

    def _target_weights(self, nav_data, date):
        """Compute target weights by combining both signals."""
        regime = self._regime(nav_data, date)
        rs = self._rs_weight(nav_data, date)

        if regime == "risk_on" and rs >= 0.5:
            m_w = min(rs, self.max_weight)
        elif regime == "risk_off" and rs < 0.5:
            m_w = max(rs, self.min_weight)
        else:
            m_w = 0.5  # signals disagree — stay neutral

        m_w = float(np.clip(m_w, self.min_weight, self.max_weight))
        return {self.value_fund: 1.0 - m_w, self.momentum_fund: m_w}

    def allocate_money(self, money, nav_data, date):
        weights = self._target_weights(nav_data, date)
        return {fund: money * w for fund, w in weights.items()}

    def rebalance(self, portfolio, nav_data, date):
        return _to_target_orders(portfolio, nav_data, date, self._target_weights(nav_data, date))

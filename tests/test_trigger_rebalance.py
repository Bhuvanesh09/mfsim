"""Tests for trigger-based rebalancing with cooldown.

Covers the _TriggerMixin, should_rebalance() on BaseStrategy, trigger
behaviour on TrendFilter/RelativeStrength/DualSignal, cooldown enforcement,
backward compatibility, and rebalance_log tracking in the Simulator.
"""

import pandas as pd

from mfsim.backtester.simulator import Simulator
from mfsim.strategies.adaptive_strategies import (
    DualSignalStrategy,
    RelativeStrengthStrategy,
    TrendFilterStrategy,
)
from mfsim.strategies.base_strategy import BaseStrategy
from tests.conftest import MockDataLoader, make_nav_df, make_nav_df_with_crash

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trend_nav(start, num_days, start_nav=100.0, daily_return=0.0003):
    """Make NAV data for three funds (value, momentum, trend)."""
    return {
        "Value": make_nav_df(start, num_days, start_nav=start_nav, daily_return=daily_return),
        "Momentum": make_nav_df(
            start, num_days, start_nav=start_nav, daily_return=daily_return * 1.5,
        ),
        "Trend": make_nav_df(start, num_days, start_nav=start_nav, daily_return=daily_return),
    }


def _make_crash_data(start="2019-01-01", num_days=504, crash_day=300, crash_pct=0.30):
    """Three-fund data where the trend fund crashes mid-period."""
    return {
        "Value": make_nav_df(start, num_days, start_nav=100.0, daily_return=0.0003),
        "Momentum": make_nav_df(start, num_days, start_nav=100.0, daily_return=0.0005),
        "Trend": make_nav_df_with_crash(start, num_days, crash_day=crash_day, crash_pct=crash_pct),
    }


# ---------------------------------------------------------------------------
# 1. BaseStrategy default
# ---------------------------------------------------------------------------


class TestBaseStrategyDefault:
    def test_should_rebalance_returns_false(self):
        """Default should_rebalance() always returns False."""

        class Dummy(BaseStrategy):
            def __init__(self):
                super().__init__("monthly", ["Total Return"], ["Fund A"])

            def rebalance(self, portfolio, nav_data, current_date):
                return []

        s = Dummy()
        assert s.should_rebalance({}, {}, pd.Timestamp("2020-06-15")) is False


# ---------------------------------------------------------------------------
# 2. TrendFilter trigger
# ---------------------------------------------------------------------------


class TestTrendFilterTrigger:
    def test_trigger_disabled_by_default(self):
        """trigger_enabled defaults to False; should_rebalance returns False."""
        s = TrendFilterStrategy("Value", "Momentum", "Trend", ma_window=5)
        nav = _make_trend_nav("2020-01-01", 100)
        loader = MockDataLoader(nav)
        sim = Simulator(
            start_date="2020-01-02", end_date="2020-05-29",
            initial_investment=100000, strategy=s, sip_amount=0, data_loader=loader,
        )
        sim.run()
        # Only scheduled rebalances should exist
        triggered = [r for r in sim.rebalance_log if r["type"] == "triggered"]
        assert len(triggered) == 0

    def test_regime_flip_fires_trigger(self):
        """A crash that flips the regime should trigger a mid-month rebalance."""
        # Crash on day 250 (well past ma_window=50), sufficient to flip regime
        nav = _make_crash_data(crash_day=250, crash_pct=0.35)
        s = TrendFilterStrategy(
            "Value", "Momentum", "Trend",
            ma_window=50, trigger_enabled=True, cooldown_days=5,
        )
        loader = MockDataLoader(nav)
        sim = Simulator(
            start_date="2019-01-02", end_date="2020-12-31",
            initial_investment=100000, strategy=s, sip_amount=0, data_loader=loader,
        )
        sim.run()
        triggered = [r for r in sim.rebalance_log if r["type"] == "triggered"]
        assert len(triggered) >= 1

    def test_cooldown_blocks_rapid_retrigger(self):
        """A second regime flip within the cooldown window should be blocked."""
        s = TrendFilterStrategy(
            "Value", "Momentum", "Trend",
            ma_window=5, trigger_enabled=True, cooldown_days=100,
        )
        # Manually test the mixin logic
        nav = _make_crash_data(start="2019-01-01", num_days=100, crash_day=30, crash_pct=0.40)
        loader = MockDataLoader(nav)
        # Parse nav_data the same way Simulator does
        sim = Simulator(
            start_date="2019-01-02", end_date="2019-05-24",
            initial_investment=100000, strategy=s, sip_amount=0, data_loader=loader,
        )
        sim.run()
        triggered = [r for r in sim.rebalance_log if r["type"] == "triggered"]
        # With 100-day cooldown, at most 1 trigger in a ~100 day window
        assert len(triggered) <= 1

    def test_cooldown_expiry_allows_retrigger(self):
        """After cooldown expires, a new signal change should trigger."""
        s = TrendFilterStrategy(
            "Value", "Momentum", "Trend",
            ma_window=5, trigger_enabled=True, cooldown_days=10,
        )
        # Two crashes far enough apart: day 30 and day 80 (50 days apart > 10 day cooldown)
        dates = pd.bdate_range("2019-01-01", periods=150)
        navs = [100.0]
        for i in range(1, 150):
            if i == 30 or i == 80:
                navs.append(navs[-1] * 0.60)  # 40% crash
            else:
                navs.append(navs[-1] * 1.001)
        trend_df = pd.DataFrame({"date": [d.strftime("%d-%m-%Y") for d in dates], "nav": navs})
        nav = {
            "Value": make_nav_df("2019-01-01", 150),
            "Momentum": make_nav_df("2019-01-01", 150),
            "Trend": trend_df,
        }
        loader = MockDataLoader(nav)
        sim = Simulator(
            start_date="2019-01-02", end_date="2019-07-26",
            initial_investment=100000, strategy=s, sip_amount=0, data_loader=loader,
        )
        sim.run()
        triggered = [r for r in sim.rebalance_log if r["type"] == "triggered"]
        # Both crashes should have caused triggers (cooldown=10 << 50 day gap)
        assert len(triggered) >= 2


# ---------------------------------------------------------------------------
# 3. RelativeStrength threshold
# ---------------------------------------------------------------------------


class TestRelativeStrengthTrigger:
    def test_small_weight_change_no_trigger(self):
        """Weight changes below signal_threshold should not trigger."""
        # Stable NAV data — momentum weight won't move much
        nav = {
            "Value": make_nav_df("2020-01-01", 200, daily_return=0.0003),
            "Momentum": make_nav_df("2020-01-01", 200, daily_return=0.00031),
        }
        s = RelativeStrengthStrategy(
            "Value", "Momentum",
            horizon_weights={30: 1.0}, sensitivity=0.5,
            trigger_enabled=True, cooldown_days=5, signal_threshold=0.20,
        )
        loader = MockDataLoader(nav)
        sim = Simulator(
            start_date="2020-01-02", end_date="2020-10-09",
            initial_investment=100000, strategy=s, sip_amount=0, data_loader=loader,
        )
        sim.run()
        triggered = [r for r in sim.rebalance_log if r["type"] == "triggered"]
        # With very similar returns and high threshold, no triggers expected
        assert len(triggered) == 0

    def test_large_weight_change_triggers(self):
        """A divergence in returns beyond threshold should trigger."""
        # Momentum outperforms value dramatically
        nav = {
            "Value": make_nav_df("2020-01-01", 200, daily_return=0.0001),
            "Momentum": make_nav_df("2020-01-01", 200, daily_return=0.003),
        }
        s = RelativeStrengthStrategy(
            "Value", "Momentum",
            horizon_weights={30: 1.0}, sensitivity=2.0,
            trigger_enabled=True, cooldown_days=5, signal_threshold=0.05,
        )
        loader = MockDataLoader(nav)
        sim = Simulator(
            start_date="2020-01-02", end_date="2020-10-09",
            initial_investment=100000, strategy=s, sip_amount=0, data_loader=loader,
        )
        sim.run()
        triggered = [r for r in sim.rebalance_log if r["type"] == "triggered"]
        # With large return divergence and low threshold, at least one trigger
        assert len(triggered) >= 1


# ---------------------------------------------------------------------------
# 4. DualSignal trigger
# ---------------------------------------------------------------------------


class TestDualSignalTrigger:
    def test_regime_change_triggers(self):
        """A regime flip in the trend fund should trigger DualSignal."""
        nav = _make_crash_data(crash_day=250, crash_pct=0.35)
        s = DualSignalStrategy(
            "Value", "Momentum", "Trend",
            ma_window=50, trigger_enabled=True, cooldown_days=5, signal_threshold=0.05,
        )
        loader = MockDataLoader(nav)
        sim = Simulator(
            start_date="2019-01-02", end_date="2020-12-31",
            initial_investment=100000, strategy=s, sip_amount=0, data_loader=loader,
        )
        sim.run()
        triggered = [r for r in sim.rebalance_log if r["type"] == "triggered"]
        assert len(triggered) >= 1


# ---------------------------------------------------------------------------
# 5. Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_trigger_disabled_matches_original(self):
        """With trigger_enabled=False, no triggered rebalances appear."""
        nav = _make_crash_data(crash_day=250, crash_pct=0.35)
        s = TrendFilterStrategy(
            "Value", "Momentum", "Trend",
            ma_window=50, trigger_enabled=False,
        )
        loader = MockDataLoader(nav)
        sim = Simulator(
            start_date="2019-01-02", end_date="2020-12-31",
            initial_investment=100000, strategy=s, sip_amount=0, data_loader=loader,
        )
        sim.run()
        triggered = [r for r in sim.rebalance_log if r["type"] == "triggered"]
        assert len(triggered) == 0
        # All entries should be scheduled
        for entry in sim.rebalance_log:
            assert entry["type"] == "scheduled"

    def test_rs_disabled_no_triggers(self):
        """RelativeStrength with trigger disabled has no triggered events."""
        nav = {
            "Value": make_nav_df("2020-01-01", 200, daily_return=0.0001),
            "Momentum": make_nav_df("2020-01-01", 200, daily_return=0.003),
        }
        s = RelativeStrengthStrategy(
            "Value", "Momentum",
            horizon_weights={30: 1.0}, sensitivity=2.0,
            trigger_enabled=False,
        )
        loader = MockDataLoader(nav)
        sim = Simulator(
            start_date="2020-01-02", end_date="2020-10-09",
            initial_investment=100000, strategy=s, sip_amount=0, data_loader=loader,
        )
        sim.run()
        triggered = [r for r in sim.rebalance_log if r["type"] == "triggered"]
        assert len(triggered) == 0


# ---------------------------------------------------------------------------
# 6. Rebalance log
# ---------------------------------------------------------------------------


class TestRebalanceLog:
    def test_log_tracks_scheduled_events(self):
        """Rebalance log should record scheduled events even without triggers."""
        nav = _make_trend_nav("2020-01-01", 100)
        s = TrendFilterStrategy("Value", "Momentum", "Trend", ma_window=5)
        loader = MockDataLoader(nav)
        sim = Simulator(
            start_date="2020-01-02", end_date="2020-05-29",
            initial_investment=100000, strategy=s, sip_amount=0, data_loader=loader,
        )
        sim.run()
        scheduled = [r for r in sim.rebalance_log if r["type"] == "scheduled"]
        # Monthly strategy over ~5 months should have multiple scheduled rebalances
        assert len(scheduled) >= 3

    def test_log_distinguishes_types(self):
        """Triggered and scheduled events should have distinct type labels."""
        nav = _make_crash_data(crash_day=250, crash_pct=0.35)
        s = TrendFilterStrategy(
            "Value", "Momentum", "Trend",
            ma_window=50, trigger_enabled=True, cooldown_days=5,
        )
        loader = MockDataLoader(nav)
        sim = Simulator(
            start_date="2019-01-02", end_date="2020-12-31",
            initial_investment=100000, strategy=s, sip_amount=0, data_loader=loader,
        )
        sim.run()
        types = {r["type"] for r in sim.rebalance_log}
        assert "scheduled" in types
        # With a crash, at least one trigger should fire
        assert "triggered" in types

    def test_log_entries_have_date_and_type(self):
        """Each log entry should have 'date' and 'type' keys."""
        nav = _make_trend_nav("2020-01-01", 60)
        s = TrendFilterStrategy("Value", "Momentum", "Trend", ma_window=5)
        loader = MockDataLoader(nav)
        sim = Simulator(
            start_date="2020-01-02", end_date="2020-03-20",
            initial_investment=100000, strategy=s, sip_amount=0, data_loader=loader,
        )
        sim.run()
        for entry in sim.rebalance_log:
            assert "date" in entry
            assert "type" in entry
            assert isinstance(entry["date"], pd.Timestamp)
            assert entry["type"] in ("scheduled", "triggered")


# ---------------------------------------------------------------------------
# 7. Signal state update on scheduled rebalance
# ---------------------------------------------------------------------------


class TestSignalStateOnScheduled:
    def test_last_signal_updated_on_rebalance(self):
        """After a scheduled rebalance, _last_signal should be current."""
        nav = _make_trend_nav("2020-01-01", 100)
        s = TrendFilterStrategy(
            "Value", "Momentum", "Trend",
            ma_window=5, trigger_enabled=True, cooldown_days=21,
        )
        loader = MockDataLoader(nav)
        sim = Simulator(
            start_date="2020-01-02", end_date="2020-05-29",
            initial_investment=100000, strategy=s, sip_amount=0, data_loader=loader,
        )
        sim.run()
        # After running, the strategy should have a non-None _last_signal
        assert s._last_signal is not None


# ---------------------------------------------------------------------------
# 8. Trigger count tracking
# ---------------------------------------------------------------------------


class TestTriggerCount:
    def test_trigger_count_incremented(self):
        """_trigger_count should match the number of triggered rebalances."""
        nav = _make_crash_data(crash_day=250, crash_pct=0.35)
        s = TrendFilterStrategy(
            "Value", "Momentum", "Trend",
            ma_window=50, trigger_enabled=True, cooldown_days=5,
        )
        loader = MockDataLoader(nav)
        sim = Simulator(
            start_date="2019-01-02", end_date="2020-12-31",
            initial_investment=100000, strategy=s, sip_amount=0, data_loader=loader,
        )
        sim.run()
        triggered = [r for r in sim.rebalance_log if r["type"] == "triggered"]
        assert s._trigger_count == len(triggered)

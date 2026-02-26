"""Tests for the core simulation engine.

Covers initial investment, SIP scheduling (monthly / weekly), portfolio
value calculation, lot tracking integration, and metric computation.
All tests use the ``MockDataLoader`` and ``BuyAndHoldStrategy`` from conftest.
"""

import pandas as pd
import pytest

from mfsim.backtester.simulator import Simulator

# ---------------------------------------------------------------------------
# Basic simulation
# ---------------------------------------------------------------------------


class TestSimulatorBasic:
    def test_initial_investment_only(self, mock_loader, buy_hold_strategy):
        """A lump-sum with no SIP should invest exactly the initial amount."""
        sim = Simulator(
            start_date="2020-01-02",
            end_date="2020-02-01",
            initial_investment=100000,
            strategy=buy_hold_strategy,
            sip_amount=0,
            data_loader=mock_loader,
        )
        sim.run()
        assert sim.total_invested == pytest.approx(100000, rel=1e-4)

    def test_portfolio_value_positive(self, mock_loader, buy_hold_strategy):
        """With positive daily returns, the portfolio should grow."""
        sim = Simulator(
            start_date="2020-01-02",
            end_date="2020-12-31",
            initial_investment=100000,
            strategy=buy_hold_strategy,
            sip_amount=0,
            data_loader=mock_loader,
        )
        sim.run()
        value = sim.get_portfolio_value()
        assert value > 100000

    def test_portfolio_value_default_end_date(self, mock_loader, buy_hold_strategy):
        """get_portfolio_value() with no argument should use end_date."""
        sim = Simulator(
            start_date="2020-01-02",
            end_date="2020-06-30",
            initial_investment=100000,
            strategy=buy_hold_strategy,
            sip_amount=0,
            data_loader=mock_loader,
        )
        sim.run()
        v_default = sim.get_portfolio_value()
        v_explicit = sim.get_portfolio_value(date=sim.end_date)
        assert v_default == pytest.approx(v_explicit, rel=1e-8)

    def test_portfolio_history_records(self, mock_loader, buy_hold_strategy):
        """Each initial purchase should be recorded in portfolio_history."""
        sim = Simulator(
            start_date="2020-01-02",
            end_date="2020-02-01",
            initial_investment=100000,
            strategy=buy_hold_strategy,
            sip_amount=0,
            data_loader=mock_loader,
        )
        sim.run()
        history = sim.get_portfolio_history()
        assert len(history) == 2  # one entry per fund
        fund_names = {h["fund_name"] for h in history}
        assert fund_names == {"Fund A", "Fund B"}

    def test_metrics_calculated(self, mock_loader, buy_hold_strategy):
        """run() should return computed metrics matching the strategy."""
        sim = Simulator(
            start_date="2020-01-02",
            end_date="2020-12-31",
            initial_investment=100000,
            strategy=buy_hold_strategy,
            sip_amount=0,
            data_loader=mock_loader,
        )
        results = sim.run()
        assert "TotalReturn" in results
        assert "XIRR" in results

    def test_total_invested_with_sip(self, mock_loader, buy_hold_strategy):
        """total_invested should include initial + all SIP contributions."""
        sim = Simulator(
            start_date="2020-01-02",
            end_date="2020-06-30",
            initial_investment=100000,
            strategy=buy_hold_strategy,
            sip_amount=10000,
            sip_frequency="monthly",
            data_loader=mock_loader,
        )
        sim.run()
        # initial + at least 5 monthly SIPs (Jan through May; Jun may or may not trigger)
        assert sim.total_invested >= 100000 + 50000


# ---------------------------------------------------------------------------
# SIP scheduling
# ---------------------------------------------------------------------------


class TestSIPScheduling:
    def test_monthly_sip_fires_each_month(self, mock_loader, buy_hold_strategy):
        """Monthly SIP should invest in each calendar month."""
        sim = Simulator(
            start_date="2020-01-02",
            end_date="2020-06-30",
            initial_investment=0,
            strategy=buy_hold_strategy,
            sip_amount=10000,
            sip_frequency="monthly",
            data_loader=mock_loader,
        )
        sim.run()
        df = sim.portfolio_history_df
        months_with_purchases = set(d.month for d in df.index)
        # Expect at least 5 of the 6 months
        assert len(months_with_purchases) >= 5

    def test_weekly_sip(self, mock_loader, buy_hold_strategy):
        """Weekly SIP should fire roughly 4 times in one month."""
        sim = Simulator(
            start_date="2020-01-02",
            end_date="2020-02-01",
            initial_investment=0,
            strategy=buy_hold_strategy,
            sip_amount=5000,
            sip_frequency="weekly",
            data_loader=mock_loader,
        )
        sim.run()
        # ~4 ISO weeks overlap with Jan 2--Feb 1, so at least 3 weekly SIPs
        assert sim.total_invested >= 15000

    def test_daily_sip(self, mock_loader, buy_hold_strategy):
        """Daily SIP should fire on every trading day."""
        sim = Simulator(
            start_date="2020-01-02",
            end_date="2020-01-31",
            initial_investment=0,
            strategy=buy_hold_strategy,
            sip_amount=1000,
            sip_frequency="daily",
            data_loader=mock_loader,
        )
        sim.run()
        # ~21 business days in Jan 2--31, each triggers SIP.
        # Each SIP creates 2 transactions (one per fund).
        assert len(sim.portfolio_history) >= 40  # at least 20 days * 2 funds

    def test_sip_zero_disables(self, mock_loader, buy_hold_strategy):
        """sip_amount=0 should not produce any SIP transactions."""
        sim = Simulator(
            start_date="2020-01-02",
            end_date="2020-06-30",
            initial_investment=100000,
            strategy=buy_hold_strategy,
            sip_amount=0,
            data_loader=mock_loader,
        )
        sim.run()
        # Only the initial investment (2 purchases, one per fund)
        assert len(sim.portfolio_history) == 2


# ---------------------------------------------------------------------------
# Lot tracker integration
# ---------------------------------------------------------------------------


class TestLotTrackerIntegration:
    def test_lots_created_on_purchase(self, mock_loader, buy_hold_strategy):
        """Initial investment should create one lot per fund."""
        sim = Simulator(
            start_date="2020-01-02",
            end_date="2020-02-01",
            initial_investment=100000,
            strategy=buy_hold_strategy,
            sip_amount=0,
            data_loader=mock_loader,
        )
        sim.run()
        assert len(sim.lots) == 2  # one lot per fund

    def test_lots_accumulate_with_sip(self, mock_loader, buy_hold_strategy):
        """SIP should create additional lots for each investment date."""
        sim = Simulator(
            start_date="2020-01-02",
            end_date="2020-04-01",
            initial_investment=100000,
            strategy=buy_hold_strategy,
            sip_amount=10000,
            sip_frequency="monthly",
            data_loader=mock_loader,
        )
        sim.run()
        # Initial (2 lots) + at least 2 SIP months (4 lots) = >= 6
        assert len(sim.lots) >= 6

    def test_lot_tracker_matches_current_portfolio(self, mock_loader, buy_hold_strategy):
        """Lot tracker holdings should agree with current_portfolio."""
        sim = Simulator(
            start_date="2020-01-02",
            end_date="2020-06-30",
            initial_investment=100000,
            strategy=buy_hold_strategy,
            sip_amount=10000,
            sip_frequency="monthly",
            data_loader=mock_loader,
        )
        sim.run()
        cp = sim.current_portfolio
        lt = sim.lot_tracker.get_all_holdings()
        for fund in sim.fund_list:
            assert cp[fund] == pytest.approx(lt[fund], rel=1e-8)


# ---------------------------------------------------------------------------
# Start date snapping
# ---------------------------------------------------------------------------


class TestStartDateSnapping:
    def test_start_date_snaps_forward(self, mock_loader, buy_hold_strategy):
        """If start_date is not a trading day, it should snap forward."""
        # 2020-01-04 is a Saturday. NAV data only has business days.
        # Should snap forward to 2020-01-06 (Monday).
        sim = Simulator(
            start_date="2020-01-04",
            end_date="2020-02-01",
            initial_investment=100000,
            strategy=buy_hold_strategy,
            sip_amount=0,
            data_loader=mock_loader,
        )
        sim.run()
        assert sim.start_date == pd.Timestamp("2020-01-06")

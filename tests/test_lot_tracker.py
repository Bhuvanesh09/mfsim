"""Tests for the FIFO lot-level transaction tracker.

Covers buy / sell mechanics, FIFO ordering, realized gain calculation,
and edge cases (sell with loss, sell empty fund, partial lots).
"""

from datetime import datetime

import pytest

from mfsim.backtester.lot_tracker import LotTracker, RealizedGain

# ---------------------------------------------------------------------------
# Buy operations
# ---------------------------------------------------------------------------


class TestLotTrackerBuy:
    def test_single_buy(self):
        tracker = LotTracker()
        lot = tracker.buy("Fund A", datetime(2023, 1, 1), 100.0, 10.0)
        assert lot.units == 100.0
        assert lot.cost_per_unit == 10.0
        assert tracker.get_holdings("Fund A") == 100.0

    def test_multiple_buys_same_fund(self):
        tracker = LotTracker()
        tracker.buy("Fund A", datetime(2023, 1, 1), 100.0, 10.0)
        tracker.buy("Fund A", datetime(2023, 6, 1), 50.0, 12.0)
        assert tracker.get_holdings("Fund A") == 150.0
        assert len(tracker.get_lots("Fund A")) == 2

    def test_multiple_funds(self):
        tracker = LotTracker()
        tracker.buy("Fund A", datetime(2023, 1, 1), 100.0, 10.0)
        tracker.buy("Fund B", datetime(2023, 1, 1), 200.0, 5.0)
        holdings = tracker.get_all_holdings()
        assert holdings["Fund A"] == 100.0
        assert holdings["Fund B"] == 200.0

    def test_buy_returns_lot(self):
        tracker = LotTracker()
        lot = tracker.buy("Fund A", datetime(2023, 1, 1), 50.0, 20.0)
        assert lot.fund_name == "Fund A"
        assert lot.purchase_date == datetime(2023, 1, 1)
        assert lot.units == 50.0
        assert lot.cost_per_unit == 20.0
        assert lot.lot_id  # non-empty id

    def test_buy_zero_units(self):
        tracker = LotTracker()
        lot = tracker.buy("Fund A", datetime(2023, 1, 1), 0.0, 10.0)
        assert lot.units == 0.0
        assert tracker.get_holdings("Fund A") == 0.0


# ---------------------------------------------------------------------------
# Sell operations
# ---------------------------------------------------------------------------


class TestLotTrackerSell:
    def test_full_lot_sell(self):
        tracker = LotTracker()
        tracker.buy("Fund A", datetime(2023, 1, 1), 100.0, 10.0)
        gains = tracker.sell("Fund A", datetime(2024, 1, 1), 100.0, 15.0)

        assert len(gains) == 1
        assert gains[0].units == 100.0
        assert gains[0].gain == pytest.approx(500.0, abs=1e-8)  # (15 - 10) * 100
        assert gains[0].holding_days == 365
        assert tracker.get_holdings("Fund A") == pytest.approx(0.0, abs=1e-10)

    def test_partial_lot_sell(self):
        tracker = LotTracker()
        tracker.buy("Fund A", datetime(2023, 1, 1), 100.0, 10.0)
        gains = tracker.sell("Fund A", datetime(2023, 6, 1), 30.0, 12.0)

        assert len(gains) == 1
        assert gains[0].units == 30.0
        assert tracker.get_holdings("Fund A") == pytest.approx(70.0, abs=1e-8)

    def test_fifo_order(self):
        tracker = LotTracker()
        tracker.buy("Fund A", datetime(2023, 1, 1), 100.0, 10.0)
        tracker.buy("Fund A", datetime(2023, 6, 1), 50.0, 12.0)

        # Sell 120 -- should consume all of first lot (100) + 20 from second
        gains = tracker.sell("Fund A", datetime(2024, 1, 1), 120.0, 15.0)

        assert len(gains) == 2
        assert gains[0].units == 100.0
        assert gains[0].cost_per_unit == 10.0  # first (oldest) lot
        assert gains[1].units == 20.0
        assert gains[1].cost_per_unit == 12.0  # second lot
        assert tracker.get_holdings("Fund A") == pytest.approx(30.0, abs=1e-8)

    def test_sell_with_loss(self):
        tracker = LotTracker()
        tracker.buy("Fund A", datetime(2023, 1, 1), 100.0, 10.0)
        gains = tracker.sell("Fund A", datetime(2023, 6, 1), 100.0, 8.0)
        assert gains[0].gain == pytest.approx(-200.0, abs=1e-8)  # (8 - 10) * 100

    def test_sell_empty_fund_raises(self):
        tracker = LotTracker()
        with pytest.raises(ValueError, match="No lots available"):
            tracker.sell("Fund A", datetime(2023, 1, 1), 100.0, 10.0)

    def test_sell_nonexistent_fund_raises(self):
        tracker = LotTracker()
        tracker.buy("Fund A", datetime(2023, 1, 1), 100.0, 10.0)
        with pytest.raises(ValueError, match="No lots available"):
            tracker.sell("Fund B", datetime(2023, 6, 1), 50.0, 12.0)

    def test_oversell_raises_without_mutating_lots(self):
        tracker = LotTracker()
        tracker.buy("Fund A", datetime(2023, 1, 1), 100.0, 10.0)

        with pytest.raises(ValueError, match="Cannot sell"):
            tracker.sell("Fund A", datetime(2023, 6, 1), 120.0, 12.0)

        assert tracker.get_holdings("Fund A") == pytest.approx(100.0, abs=1e-8)
        assert len(tracker.realized_gains) == 0

    def test_realized_gains_accumulate(self):
        tracker = LotTracker()
        tracker.buy("Fund A", datetime(2023, 1, 1), 100.0, 10.0)
        tracker.sell("Fund A", datetime(2023, 6, 1), 50.0, 12.0)
        tracker.buy("Fund A", datetime(2023, 7, 1), 80.0, 11.0)
        tracker.sell("Fund A", datetime(2024, 1, 1), 80.0, 14.0)

        # First sell: 1 gain (from lot-1, 50 units).
        # Second sell: 80 units. Remaining from lot-1 is 50, lot-2 has 80.
        #   => consumes 50 from lot-1 + 30 from lot-2 = 2 gains.
        # Total realized_gains entries: 1 + 2 = 3
        assert len(tracker.realized_gains) == 3

    def test_sell_gain_record_fields(self):
        tracker = LotTracker()
        tracker.buy("Fund A", datetime(2023, 1, 1), 100.0, 10.0)
        gains = tracker.sell("Fund A", datetime(2023, 7, 1), 40.0, 14.0)
        g = gains[0]

        assert isinstance(g, RealizedGain)
        assert g.fund_name == "Fund A"
        assert g.purchase_date == datetime(2023, 1, 1)
        assert g.sell_date == datetime(2023, 7, 1)
        assert g.units == 40.0
        assert g.cost_per_unit == 10.0
        assert g.sell_price_per_unit == 14.0
        assert g.gain == pytest.approx(160.0, abs=1e-8)  # (14-10)*40
        assert g.holding_days == (datetime(2023, 7, 1) - datetime(2023, 1, 1)).days


# ---------------------------------------------------------------------------
# Holdings queries
# ---------------------------------------------------------------------------


class TestLotTrackerHoldings:
    def test_get_all_lots(self):
        tracker = LotTracker()
        tracker.buy("Fund A", datetime(2023, 1, 1), 100.0, 10.0)
        tracker.buy("Fund B", datetime(2023, 1, 1), 200.0, 5.0)
        all_lots = tracker.get_all_lots()
        assert len(all_lots) == 2

    def test_empty_holdings(self):
        tracker = LotTracker()
        assert tracker.get_holdings("Fund A") == 0.0
        assert tracker.get_all_holdings() == {}

    def test_get_lots_returns_copy(self):
        tracker = LotTracker()
        tracker.buy("Fund A", datetime(2023, 1, 1), 100.0, 10.0)
        lots = tracker.get_lots("Fund A")
        lots.pop()  # mutate the returned list
        assert len(tracker.get_lots("Fund A")) == 1  # original unchanged

    def test_holdings_after_full_sell(self):
        tracker = LotTracker()
        tracker.buy("Fund A", datetime(2023, 1, 1), 100.0, 10.0)
        tracker.sell("Fund A", datetime(2023, 6, 1), 100.0, 12.0)
        assert tracker.get_holdings("Fund A") == pytest.approx(0.0, abs=1e-10)
        assert tracker.get_lots("Fund A") == []

"""Tests for performance and risk metrics.

Each metric is tested against hand-calculated expected values using
minimal, controlled scenarios (known NAVs, known cash flows).
"""

import math

import numpy as np
import pandas as pd
import pytest

from mfsim.metrics.metrics_collection import (
    MaximumDrawdownMetric,
    SharpeRatioMetric,
    SortinoRatioMetric,
    TotalReturnMetric,
    XIRRMetric,
    compute_portfolio_value_history,
    latest_nav_on_or_before,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_portfolio_history(records):
    """Build a portfolio_history DataFrame from a list of dicts.

    Each dict must have ``date`` (str YYYY-MM-DD), ``fund_name``, ``units``,
    ``amount``.  Returns a DataFrame indexed by ``date``.
    """
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    return df


def _make_nav_data(fund_name, dates, navs):
    """Build a single-fund nav_data entry.

    Returns ``{fund_name: DataFrame}`` with DatetimeIndex named ``date``
    and a ``nav`` column.
    """
    idx = pd.to_datetime(dates)
    nav_df = pd.DataFrame({"nav": navs}, index=idx)
    nav_df.index.name = "date"
    return {fund_name: nav_df}


class TestLatestNavOnOrBefore:
    def test_unsorted_index_picks_latest_date(self):
        nav_df = pd.DataFrame(
            {"nav": [15.0, 10.0]},
            index=pd.to_datetime(["2020-12-31", "2020-01-01"]),
        )
        nav_df.index.name = "date"
        nav = latest_nav_on_or_before(nav_df, pd.Timestamp("2020-12-31"))
        assert nav == pytest.approx(15.0, abs=1e-8)

    def test_unsorted_date_column_picks_latest_date(self):
        nav_df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-12-31", "2020-01-01"]),
                "nav": [15.0, 10.0],
            }
        )
        nav = latest_nav_on_or_before(nav_df, pd.Timestamp("2020-12-31"))
        assert nav == pytest.approx(15.0, abs=1e-8)


# ---------------------------------------------------------------------------
# TotalReturn
# ---------------------------------------------------------------------------


class TestTotalReturn:
    def test_simple_gain(self):
        """100 invested at NAV 10, final NAV 15 => 50 % return."""
        metric = TotalReturnMetric()
        ph = _make_portfolio_history(
            [{"date": "2020-01-01", "fund_name": "Fund A", "units": 10.0, "amount": 100.0}]
        )
        current_portfolio = {"Fund A": 10.0}
        end_date = pd.Timestamp("2021-01-01")
        nav_data = _make_nav_data("Fund A", ["2020-01-01", "2021-01-01"], [10.0, 15.0])

        result = metric.calculate(ph, current_portfolio, end_date, nav_data)
        assert result == pytest.approx(0.5, abs=0.01)

    def test_loss(self):
        """100 invested at NAV 10, final NAV 8 => -20 % return."""
        metric = TotalReturnMetric()
        ph = _make_portfolio_history(
            [{"date": "2020-01-01", "fund_name": "Fund A", "units": 10.0, "amount": 100.0}]
        )
        current_portfolio = {"Fund A": 10.0}
        end_date = pd.Timestamp("2021-01-01")
        nav_data = _make_nav_data("Fund A", ["2020-01-01", "2021-01-01"], [10.0, 8.0])

        result = metric.calculate(ph, current_portfolio, end_date, nav_data)
        assert result == pytest.approx(-0.2, abs=0.01)

    def test_no_change(self):
        """NAV unchanged => 0 % return."""
        metric = TotalReturnMetric()
        ph = _make_portfolio_history(
            [{"date": "2020-01-01", "fund_name": "Fund A", "units": 10.0, "amount": 100.0}]
        )
        current_portfolio = {"Fund A": 10.0}
        end_date = pd.Timestamp("2021-01-01")
        nav_data = _make_nav_data("Fund A", ["2020-01-01", "2021-01-01"], [10.0, 10.0])

        result = metric.calculate(ph, current_portfolio, end_date, nav_data)
        assert result == pytest.approx(0.0, abs=0.01)

    def test_two_funds(self):
        """Two-fund portfolio total return should combine correctly."""
        metric = TotalReturnMetric()
        ph = _make_portfolio_history(
            [
                {"date": "2020-01-01", "fund_name": "Fund A", "units": 10.0, "amount": 100.0},
                {"date": "2020-01-01", "fund_name": "Fund B", "units": 20.0, "amount": 200.0},
            ]
        )
        current_portfolio = {"Fund A": 10.0, "Fund B": 20.0}
        end_date = pd.Timestamp("2021-01-01")
        nav_a = _make_nav_data("Fund A", ["2020-01-01", "2021-01-01"], [10.0, 15.0])
        nav_b = _make_nav_data("Fund B", ["2020-01-01", "2021-01-01"], [10.0, 12.0])
        nav_data = {**nav_a, **nav_b}

        result = metric.calculate(ph, current_portfolio, end_date, nav_data)
        # Final value = 10*15 + 20*12 = 150 + 240 = 390
        # Invested = 100 + 200 = 300
        # Return = (390 / 300) - 1 = 0.30
        assert result == pytest.approx(0.30, abs=0.01)

    def test_uses_latest_nav_when_index_is_unsorted(self):
        metric = TotalReturnMetric()
        ph = _make_portfolio_history(
            [{"date": "2020-01-01", "fund_name": "Fund A", "units": 10.0, "amount": 100.0}]
        )
        current_portfolio = {"Fund A": 10.0}
        end_date = pd.Timestamp("2020-12-31")
        nav_df = pd.DataFrame(
            {"nav": [15.0, 10.0]},
            index=pd.to_datetime(["2020-12-31", "2020-01-01"]),
        )
        nav_df.index.name = "date"

        result = metric.calculate(ph, current_portfolio, end_date, {"Fund A": nav_df})
        assert result == pytest.approx(0.5, abs=0.01)


# ---------------------------------------------------------------------------
# XIRR
# ---------------------------------------------------------------------------


class TestXIRR:
    def test_simple_lumpsum(self):
        """Lump sum doubles in 1 year => ~100 % XIRR."""
        metric = XIRRMetric()
        ph = _make_portfolio_history(
            [{"date": "2020-01-01", "fund_name": "Fund A", "units": 100.0, "amount": 1000.0}]
        )
        current_portfolio = {"Fund A": 100.0}
        end_date = pd.Timestamp("2021-01-01")
        nav_data = _make_nav_data("Fund A", ["2020-01-01", "2021-01-01"], [10.0, 20.0])

        result = metric.calculate(ph, current_portfolio, end_date, nav_data)
        assert result == pytest.approx(1.0, abs=0.05)  # ~100 % annualized

    def test_zero_return_xirr(self):
        """If NAV is unchanged, XIRR should be ~0."""
        metric = XIRRMetric()
        ph = _make_portfolio_history(
            [{"date": "2020-01-01", "fund_name": "Fund A", "units": 100.0, "amount": 1000.0}]
        )
        current_portfolio = {"Fund A": 100.0}
        end_date = pd.Timestamp("2021-01-01")
        nav_data = _make_nav_data("Fund A", ["2020-01-01", "2021-01-01"], [10.0, 10.0])

        result = metric.calculate(ph, current_portfolio, end_date, nav_data)
        assert result == pytest.approx(0.0, abs=0.05)

    def test_uses_latest_nav_when_index_is_unsorted(self):
        metric = XIRRMetric()
        ph = _make_portfolio_history(
            [{"date": "2020-01-01", "fund_name": "Fund A", "units": 100.0, "amount": 1000.0}]
        )
        current_portfolio = {"Fund A": 100.0}
        end_date = pd.Timestamp("2020-12-31")
        nav_df = pd.DataFrame(
            {"nav": [15.0, 10.0]},
            index=pd.to_datetime(["2020-12-31", "2020-01-01"]),
        )
        nav_df.index.name = "date"

        result = metric.calculate(ph, current_portfolio, end_date, {"Fund A": nav_df})
        assert result > 0

    def test_sip_xirr(self):
        """Two investments at different NAVs should produce a reasonable XIRR."""
        metric = XIRRMetric()
        ph = _make_portfolio_history(
            [
                {
                    "date": "2020-01-01",
                    "fund_name": "Fund A",
                    "units": 100.0,
                    "amount": 1000.0,
                },
                {
                    "date": "2020-07-01",
                    "fund_name": "Fund A",
                    "units": 83.33,
                    "amount": 1000.0,
                },
            ]
        )
        current_portfolio = {"Fund A": 183.33}
        end_date = pd.Timestamp("2021-01-01")
        nav_data = _make_nav_data(
            "Fund A",
            ["2020-01-01", "2020-07-01", "2021-01-01"],
            [10.0, 12.0, 15.0],
        )

        result = metric.calculate(ph, current_portfolio, end_date, nav_data)
        # Final value = 183.33 * 15 = 2749.95
        # Invested 1000 on Jan 1, 1000 on Jul 1 => positive XIRR
        assert result > 0
        assert not math.isnan(result)


# ---------------------------------------------------------------------------
# compute_portfolio_value_history
# ---------------------------------------------------------------------------


class TestComputePortfolioValueHistory:
    def test_returns_series_with_correct_length(self):
        dates = pd.bdate_range("2020-01-01", periods=10)
        nav_df = pd.DataFrame({"nav": range(10)}, index=dates)
        nav_df.index.name = "date"

        ph = _make_portfolio_history(
            [
                {
                    "date": str(dates[0].date()),
                    "fund_name": "Fund A",
                    "units": 100.0,
                    "amount": 10000.0,
                }
            ]
        )
        nav_data = {"Fund A": nav_df}
        result = compute_portfolio_value_history(ph, nav_data, dates[-1])
        # Uses trading dates from NAV history (business dates in this fixture).
        expected_len = len(dates)
        assert len(result) == expected_len

    def test_values_reflect_holdings_times_nav(self):
        """Portfolio value on trading days equals units * NAV."""
        dates = pd.bdate_range("2020-01-01", periods=5)
        navs = [100.0, 101.0, 102.0, 103.0, 104.0]
        nav_df = pd.DataFrame({"nav": navs}, index=dates)
        nav_df.index.name = "date"

        ph = _make_portfolio_history(
            [
                {
                    "date": str(dates[0].date()),
                    "fund_name": "Fund A",
                    "units": 100.0,
                    "amount": 10000.0,
                }
            ]
        )
        nav_data = {"Fund A": nav_df}
        result = compute_portfolio_value_history(ph, nav_data, dates[-1])
        # On the first trading day: 100 units * 100.0 NAV = 10000
        assert result.loc[dates[0]] == pytest.approx(10000.0, rel=1e-6)
        # On the last trading day: 100 units * 104.0 NAV = 10400
        assert result.loc[dates[-1]] == pytest.approx(10400.0, rel=1e-6)


# ---------------------------------------------------------------------------
# MaximumDrawdown
# ---------------------------------------------------------------------------


class TestMaxDrawdown:
    def test_no_drawdown_monotonic_increase(self):
        """Monotonically increasing NAV should have ~0 drawdown."""
        metric = MaximumDrawdownMetric()

        dates = pd.bdate_range("2020-01-01", periods=252)
        navs = [100.0 * (1.0005**i) for i in range(252)]
        nav_df = pd.DataFrame({"nav": navs}, index=dates)
        nav_df.index.name = "date"

        ph = _make_portfolio_history(
            [
                {
                    "date": str(dates[0].date()),
                    "fund_name": "Fund A",
                    "units": 100.0,
                    "amount": 10000.0,
                }
            ]
        )
        current_portfolio = {"Fund A": 100.0}
        nav_data = {"Fund A": nav_df}

        result = metric.calculate(ph, current_portfolio, dates[-1], nav_data)
        assert result >= -0.01  # Essentially no drawdown


# ---------------------------------------------------------------------------
# SharpeRatio
# ---------------------------------------------------------------------------


class TestSharpeRatio:
    def test_positive_sharpe_for_strong_returns(self):
        """Portfolio with returns well above risk-free rate has positive Sharpe."""
        metric = SharpeRatioMetric(risk_free_rate=0.06, frequency="daily")

        dates = pd.bdate_range("2020-01-01", periods=252)
        navs = [100.0 * (1.001**i) for i in range(252)]
        nav_df = pd.DataFrame({"nav": navs}, index=dates)
        nav_df.index.name = "date"

        ph = _make_portfolio_history(
            [
                {
                    "date": str(dates[0].date()),
                    "fund_name": "Fund A",
                    "units": 100.0,
                    "amount": 10000.0,
                }
            ]
        )
        current_portfolio = {"Fund A": 100.0}
        nav_data = {"Fund A": nav_df}

        result = metric.calculate(ph, current_portfolio, dates[-1], nav_data)
        assert result > 0


# ---------------------------------------------------------------------------
# SortinoRatio
# ---------------------------------------------------------------------------


class TestSortinoRatio:
    def test_sortino_with_mixed_returns(self):
        """Sortino should return a finite value for realistic return series."""
        metric = SortinoRatioMetric(risk_free_rate=0.05, frequency="daily")

        dates = pd.bdate_range("2020-01-01", periods=252)
        np.random.seed(42)
        daily_returns = np.random.normal(0.001, 0.005, 252)
        navs = [100.0]
        for r in daily_returns[1:]:
            navs.append(navs[-1] * (1 + r))
        nav_df = pd.DataFrame({"nav": navs}, index=dates)
        nav_df.index.name = "date"

        ph = _make_portfolio_history(
            [
                {
                    "date": str(dates[0].date()),
                    "fund_name": "Fund A",
                    "units": 100.0,
                    "amount": 10000.0,
                }
            ]
        )
        current_portfolio = {"Fund A": 100.0}
        nav_data = {"Fund A": nav_df}

        result = metric.calculate(ph, current_portfolio, dates[-1], nav_data)
        assert not math.isnan(result)
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# End-to-end via Simulator
# ---------------------------------------------------------------------------


class TestMetricsThroughSimulator:
    """Run the simulator end-to-end and verify metrics are populated."""

    def test_total_return_via_simulator(self, mock_loader, buy_hold_strategy):
        from mfsim.backtester.simulator import Simulator

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
        # NAVs have positive daily return, so total return should be positive
        assert results["TotalReturn"] > 0

    def test_xirr_via_simulator(self, mock_loader, buy_hold_strategy):
        from mfsim.backtester.simulator import Simulator

        sim = Simulator(
            start_date="2020-01-02",
            end_date="2020-12-31",
            initial_investment=100000,
            strategy=buy_hold_strategy,
            sip_amount=0,
            data_loader=mock_loader,
        )
        results = sim.run()
        assert "XIRR" in results
        assert not math.isnan(results["XIRR"])
        assert results["XIRR"] > 0

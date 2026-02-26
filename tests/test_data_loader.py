"""Tests for data-loader contracts and the ``get_lowerbound_date`` helper.

All tests use the ``MockDataLoader`` from conftest -- no real API calls.
"""

import pandas as pd
import pytest

from mfsim.utils.data_loader import get_lowerbound_date

# ---------------------------------------------------------------------------
# get_lowerbound_date
# ---------------------------------------------------------------------------


class TestGetLowerboundDate:
    """Tests for the forward-snapping date lookup used by the Simulator."""

    def _make_df(self, dates):
        """Return a DataFrame with a DatetimeIndex (like parsed NAV data)."""
        idx = pd.to_datetime(dates)
        return pd.DataFrame({"nav": range(len(idx))}, index=idx)

    def test_exact_match(self):
        df = self._make_df(["2020-01-01", "2020-01-02", "2020-01-03"])
        result = get_lowerbound_date(df, pd.Timestamp("2020-01-02"))
        assert result == pd.Timestamp("2020-01-02")

    def test_first_date(self):
        df = self._make_df(["2020-01-01", "2020-01-02", "2020-01-03"])
        result = get_lowerbound_date(df, pd.Timestamp("2020-01-01"))
        assert result == pd.Timestamp("2020-01-01")

    def test_snaps_forward_to_next_available(self):
        """If the target date is a gap, snap forward to the next date."""
        # Only Mon/Wed/Fri data
        df = self._make_df(["2020-01-06", "2020-01-08", "2020-01-10"])
        result = get_lowerbound_date(df, pd.Timestamp("2020-01-07"))
        assert result == pd.Timestamp("2020-01-08")

    def test_past_end_returns_nat(self):
        df = self._make_df(["2020-01-01", "2020-01-02", "2020-01-03"])
        result = get_lowerbound_date(df, pd.Timestamp("2020-02-01"))
        assert pd.isna(result)

    def test_before_start(self):
        df = self._make_df(["2020-01-05", "2020-01-06", "2020-01-07"])
        result = get_lowerbound_date(df, pd.Timestamp("2020-01-01"))
        assert result == pd.Timestamp("2020-01-05")


# ---------------------------------------------------------------------------
# MockDataLoader contract tests
# ---------------------------------------------------------------------------


class TestMockDataLoader:
    def test_load_nav_data_returns_correct_columns(self, mock_loader):
        df = mock_loader.load_nav_data("Fund A")
        assert "date" in df.columns
        assert "nav" in df.columns
        assert len(df) > 0

    def test_load_nav_data_unknown_fund_raises(self, mock_loader):
        with pytest.raises(FileNotFoundError):
            mock_loader.load_nav_data("Unknown Fund")

    def test_default_expense_ratio(self, mock_loader):
        assert mock_loader.get_expense_ratio("Fund A") == 0

    def test_default_exit_load(self, mock_loader):
        assert mock_loader.get_exit_load("Fund A") == 0

    def test_load_returns_copy(self, mock_loader):
        """Loading should return a copy so mutations don't leak."""
        df1 = mock_loader.load_nav_data("Fund A")
        df2 = mock_loader.load_nav_data("Fund A")
        df1.drop(df1.index, inplace=True)
        assert len(df2) > 0  # df2 should be unaffected

    def test_nav_data_types(self, mock_loader):
        """nav column should be numeric and date column should be string."""
        df = mock_loader.load_nav_data("Fund A")
        assert pd.api.types.is_numeric_dtype(df["nav"])
        assert pd.api.types.is_string_dtype(df["date"])

    def test_both_funds_available(self, mock_loader):
        """Both Fund A and Fund B should be loadable."""
        df_a = mock_loader.load_nav_data("Fund A")
        df_b = mock_loader.load_nav_data("Fund B")
        assert len(df_a) > 0
        assert len(df_b) > 0

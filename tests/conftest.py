"""Shared fixtures for the mfsim test suite.

Provides mock data loaders, a simple buy-and-hold strategy, and synthetic NAV
data generators so that no test ever hits a real API or the file system.
"""

import pandas as pd
import pytest

from mfsim.strategies.base_strategy import BaseStrategy
from mfsim.utils.data_loader import BaseDataLoader

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


class MockDataLoader(BaseDataLoader):
    """Data loader backed by in-memory dicts for testing.

    Expects *nav_data_dict* to map fund names to DataFrames that have a
    ``date`` column formatted as ``"DD-MM-YYYY"`` strings and a ``nav``
    column, exactly as the real ``Simulator._load_all_nav_data()`` expects
    before it parses the dates and sets the index.
    """

    def __init__(self, nav_data_dict):
        # Deliberately skip super().__init__() to avoid file system access.
        self.nav_data_dict = nav_data_dict

    def load_nav_data(self, fund_name):
        if fund_name not in self.nav_data_dict:
            raise FileNotFoundError(f"Fund not found: {fund_name}")
        return self.nav_data_dict[fund_name].copy()

    def get_expense_ratio(self, fund_name):
        return 0

    def get_exit_load(self, fund_name):
        return 0


class BuyAndHoldStrategy(BaseStrategy):
    """Strategy that allocates once and never rebalances.  For testing."""

    def __init__(self, fund_list, allocation=None, metrics=None):
        super().__init__(
            frequency="annually",
            metrics=metrics or ["Total Return", "XIRR"],
            fund_list=fund_list,
        )
        self.allocation = allocation

    def allocate_money(self, money_invested, nav_data, current_date):
        if self.allocation:
            return {f: money_invested * p for f, p in self.allocation.items()}
        n = len(self.fund_list)
        return {f: money_invested / n for f in self.fund_list}

    def rebalance(self, portfolio, nav_data, current_date):
        return []


# ---------------------------------------------------------------------------
# NAV data factory
# ---------------------------------------------------------------------------


def make_nav_df(start_date, num_days, start_nav=100.0, daily_return=0.0003):
    """Generate synthetic NAV data with consistent daily returns.

    Returns a DataFrame with columns ``date`` (string, DD-MM-YYYY format)
    and ``nav`` (float), which is the format expected by the real data
    loader pipeline (``Simulator._load_all_nav_data`` will parse it).

    Parameters
    ----------
    start_date : str
        Start date, e.g. ``"2020-01-01"``.
    num_days : int
        Number of business days to generate.
    start_nav : float
        NAV on the first day.
    daily_return : float
        Constant daily return (e.g. 0.0003 => 0.03 % / day).
    """
    dates = pd.bdate_range(start=start_date, periods=num_days)
    navs = [start_nav]
    for _ in range(1, num_days):
        navs.append(navs[-1] * (1 + daily_return))
    df = pd.DataFrame(
        {
            "date": [d.strftime("%d-%m-%Y") for d in dates],
            "nav": navs,
        }
    )
    return df


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_nav_data():
    """Two funds with ~2 years of synthetic business-day NAV data."""
    return {
        "Fund A": make_nav_df("2020-01-01", 504, start_nav=100.0, daily_return=0.0004),
        "Fund B": make_nav_df("2020-01-01", 504, start_nav=50.0, daily_return=0.0002),
    }


@pytest.fixture
def mock_loader(simple_nav_data):
    """``MockDataLoader`` seeded with the ``simple_nav_data`` fixture."""
    return MockDataLoader(simple_nav_data)


@pytest.fixture
def buy_hold_strategy():
    """60 / 40 buy-and-hold strategy over Fund A and Fund B."""
    return BuyAndHoldStrategy(
        fund_list=["Fund A", "Fund B"],
        allocation={"Fund A": 0.6, "Fund B": 0.4},
    )

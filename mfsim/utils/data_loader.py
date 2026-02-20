"""
Data loading abstractions for NAV and fund data.

Provides :class:`BaseDataLoader` (abstract) and :class:`MfApiDataLoader`
(default implementation that fetches live data from api.mfapi.in).

To use a custom data source, subclass :class:`BaseDataLoader`::

    from mfsim.utils.data_loader import BaseDataLoader
    import pandas as pd

    class CsvDataLoader(BaseDataLoader):
        def __init__(self, csv_dir):
            super().__init__(data_dir=csv_dir)
            self.csv_dir = csv_dir

        def load_nav_data(self, fund_name):
            df = pd.read_csv(f"{self.csv_dir}/{fund_name}.csv")
            df["date"] = pd.to_datetime(df["date"])
            df["nav"] = df["nav"].astype(float)
            return df.sort_values("date").reset_index(drop=True)

    sim = Simulator(..., data_loader=CsvDataLoader("/path/to/csvs"))
"""

import os
import json
import pandas as pd
import importlib.resources as resourcelib
import requests
from abc import ABC, abstractmethod


def get_lowerbound_date(dates, target_date):
    """Find the earliest date in a DataFrame's index that is >= ``target_date``.

    Used to snap a requested date forward to the nearest available trading
    day. For example, if you request Jan 1 (a holiday), this returns the
    first trading day after Jan 1.

    Args:
        dates: A DataFrame with a DatetimeIndex (typically NAV data).
        target_date: The date to search from.

    Returns:
        The earliest date in the index that is on or after ``target_date``.
        Returns ``NaT`` if no such date exists.
    """
    return dates[dates.index >= target_date].index.min()


class BaseDataLoader(ABC):
    """Abstract base class for all data loaders.

    Subclass this to implement custom data sources (CSVs, databases,
    other APIs). The only required method is :meth:`load_nav_data`.

    The returned NAV DataFrame must have these columns:

    - ``date`` — pandas datetime64, sorted ascending.
    - ``nav`` — float, the Net Asset Value for that date.

    Additional columns are allowed and will be ignored by the simulator.

    Optionally override :meth:`get_expense_ratio` and :meth:`get_exit_load`
    to provide fund-level cost data for reporting purposes.

    Args:
        data_dir: Path to the directory containing data files.
            If ``None``, defaults to the ``mfsim/data/`` package directory.

    Note:
        **NAV values from AMFI (the default source) are already net of
        expense ratio.** The expense ratio is deducted daily by the fund
        house before publishing NAV. If your custom data source provides
        gross-of-fee NAVs, you'll need to handle the deduction yourself
        in your data loader or strategy.
    """

    def __init__(self, data_dir=None):
        self.data_dir = data_dir
        if not self.data_dir:
            self.data_dir = str(resourcelib.files("mfsim") / "data")
        self.fund_list_path = os.path.join(self.data_dir, "mf_list.json")
        self.nav_data_dir = os.path.join(self.data_dir, "nav_data")

    @abstractmethod
    def load_nav_data(self, fund_name) -> pd.DataFrame:
        """Load historical NAV data for a fund. **Must be implemented.**

        Args:
            fund_name: Name of the fund to load data for. Must match
                the name used in the strategy's ``fund_list``.

        Returns:
            DataFrame with columns:

            - ``date`` (datetime64): NAV date, sorted ascending.
            - ``nav`` (float): Net Asset Value.

            Additional columns are allowed but ignored.

        Raises:
            FileNotFoundError: If data cannot be loaded for the fund.
        """
        pass

    def get_expense_ratio(self, fund_name) -> float:
        """Return the annual expense ratio (TER) for a fund.

        This is used for **informational/reporting purposes only**.
        The simulator does not apply expense ratio deductions because
        AMFI NAV data is already net of TER.

        Override in your data loader if you want to track expense ratios.

        Args:
            fund_name: Name of the fund.

        Returns:
            Annual expense ratio as a decimal (e.g., ``0.005`` for 0.5%).
            Default: ``0``.
        """
        return 0

    def get_exit_load(self, fund_name) -> float:
        """Return the exit load percentage for a fund.

        Override in your data loader to provide fund-specific exit loads.

        Args:
            fund_name: Name of the fund.

        Returns:
            Exit load as a decimal (e.g., ``0.01`` for 1%).
            Default: ``0``.
        """
        return 0


class MfApiDataLoader(BaseDataLoader):
    """Data loader that fetches live NAV data from api.mfapi.in.

    Uses the AMFI mutual fund database (``mf_list.json``, bundled with
    the package) to look up scheme codes, then fetches historical NAV
    data from the public API at ``https://api.mfapi.in/mf/{schemeCode}``.

    The API provides data sourced from AMFI (amfiindia.com) — the same
    NAV values published by fund houses daily. No API key is required.

    Example::

        loader = MfApiDataLoader()
        nav_df = loader.load_nav_data("Some Fund - Direct Plan - Growth")
        print(nav_df.head())
        #         date    nav
        # 0 2013-01-02  10.00
        # 1 2013-01-03  10.05
    """

    def __init__(self, data_dir=None):
        super().__init__(data_dir)
        self.load_fund_list()

    def load_fund_list(self) -> list:
        """Load the master fund list from ``mf_list.json``.

        Populates ``self.funds_list_df`` with columns ``schemeName``
        and ``schemeCode``.

        Returns:
            List of all fund names (scheme names).

        Raises:
            FileNotFoundError: If ``mf_list.json`` cannot be read.
        """
        try:
            with open(self.fund_list_path, "r") as infile:
                data = json.load(infile)
            self.funds_list_df = pd.DataFrame.from_records(data)
            return self.funds_list_df.schemeName.tolist()
        except Exception as e:
            raise FileNotFoundError(f"Error loading fund list: {e}")

    def load_nav_data(self, fund_name) -> pd.DataFrame:
        """Fetch historical NAV data for a fund from the mfapi.in API.

        Looks up the fund's scheme code from ``mf_list.json``, then
        fetches its full NAV history from ``api.mfapi.in``.

        Args:
            fund_name: Exact scheme name as it appears in ``mf_list.json``.

        Returns:
            DataFrame with ``date`` (datetime64) and ``nav`` (float)
            columns, sorted by date ascending.

        Raises:
            FileNotFoundError: If the fund name is not found or the
                API request fails.
        """
        try:
            fund_row = self.funds_list_df.loc[
                self.funds_list_df["schemeName"] == fund_name
            ]
            url = f"http://api.mfapi.in/mf/{fund_row['schemeCode'].tolist()[0]}"
            response = requests.get(url)
            json_data = response.json()
            fund_df = pd.DataFrame.from_records(json_data["data"])
            fund_df["date"] = pd.to_datetime(fund_df["date"], format="%d-%m-%Y")
            fund_df["nav"] = fund_df["nav"].astype(float)
            return fund_df
        except Exception as e:
            raise FileNotFoundError(f"Error loading NAV data for {fund_name}: {e}")

"""
Data loader for NSE index CSV files (Price Return and Total Return Index).

NSE provides historical index data as CSV downloads from:
  https://www.nseindia.com/market-data/live-equity-market
  → Indices → Historical Data

**Preferred**: Download Total Return Index (TRI) data — it includes dividend
reinvestment and matches what an index fund actually delivers. Price Return (PR)
excludes dividends and understates long-term returns.

Expected file naming convention (NSE default):
  NIFTY 50_Historical_PR_01012013to26022026.csv
  NIFTY50 VALUE 20_Historical_TRI_01012013to26022026.csv
  NIFTY200 MOMENTUM 30_Historical_TRI_01012013to26022026.csv

The fund name used in strategies should match the index name embedded in
the CSV filename (e.g. "NIFTY 50", "NIFTY50 VALUE 20").

Usage::

    from mfsim.utils.nse_csv_loader import NseCsvLoader

    loader = NseCsvLoader("path/to/csv/files")
    loader.list_available()         # see what indices are loaded
    nav_df = loader.load_nav_data("NIFTY 50")

How to download from NSE
-------------------------
1. Go to https://www.nseindia.com
2. Market Data → Indices → choose the index → Historical Data
3. Select date range and "Total Returns Index" type
4. Download and save to a local directory

Indices needed for experiment 001:
  - NIFTY 50 (baseline)
  - NIFTY50 VALUE 20 (value factor)
  - NIFTY200 MOMENTUM 30 (momentum factor)
"""

import os
import re

import pandas as pd

from .data_loader import BaseDataLoader


class NseCsvLoader(BaseDataLoader):
    """Load NSE index data from locally-saved CSV files.

    Handles both Price Return (``_Historical_PR_``) and Total Return Index
    (``_Historical_TRI_``) file naming conventions used by NSE downloads.
    When both exist for the same index, TRI is preferred.

    Args:
        data_dir: Path to directory containing the downloaded NSE CSV files.
    """

    # Matches: "INDEX NAME_Historical_PR_..." or "INDEX NAME_Historical_TRI_..."
    _FILENAME_RE = re.compile(r"^(.+?)_Historical_(PR|TRI)_.*\.csv$", re.IGNORECASE)

    def __init__(self, data_dir: str):
        super().__init__(data_dir=data_dir)
        self.data_dir = data_dir
        self._index_data: dict[str, pd.DataFrame] = {}
        self._load_all()

    def _load_all(self):
        """Scan data_dir and load all matching NSE CSV files."""
        if not os.path.isdir(self.data_dir):
            return

        # Collect all matching files; prefer TRI over PR for the same index
        files_by_index: dict[str, tuple[str, str]] = {}  # {index_name: (path, kind)}

        for fname in sorted(os.listdir(self.data_dir)):
            m = self._FILENAME_RE.match(fname)
            if not m:
                continue
            index_name = m.group(1).strip()
            kind = m.group(2).upper()  # "PR" or "TRI"
            path = os.path.join(self.data_dir, fname)

            existing = files_by_index.get(index_name)
            if existing is None or kind == "TRI":
                files_by_index[index_name] = (path, kind)

        for index_name, (path, kind) in files_by_index.items():
            try:
                df = self._parse_nse_csv(path)
                self._index_data[index_name] = df
            except Exception as e:
                import warnings
                warnings.warn(f"Could not load {path}: {e}")

    @staticmethod
    def _parse_nse_csv(path: str) -> pd.DataFrame:
        """Parse a NSE historical index CSV into a (date, nav) DataFrame."""
        df = pd.read_csv(path)

        # Normalize column names (NSE uses inconsistent casing/spacing)
        df.columns = [c.strip() for c in df.columns]
        rename = {}
        for col in df.columns:
            cl = col.lower()
            if cl == "date":
                rename[col] = "date"
            elif cl in ("close", "closing index value"):
                rename[col] = "nav"
        df = df.rename(columns=rename)

        if "date" not in df.columns or "nav" not in df.columns:
            raise ValueError(f"Could not find 'date'/'close' columns. Got: {list(df.columns)}")

        df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
        df["nav"] = pd.to_numeric(df["nav"].astype(str).str.replace(",", ""), errors="coerce")
        df = df.dropna(subset=["date", "nav"])
        return df[["date", "nav"]].sort_values("date").reset_index(drop=True)

    def list_available(self) -> list[str]:
        """Return a list of index names that were successfully loaded."""
        return sorted(self._index_data.keys())

    def load_nav_data(self, fund_name: str) -> pd.DataFrame:
        """Return historical NAV data for an index.

        Args:
            fund_name: Index name matching the CSV filename prefix, e.g.
                ``"NIFTY 50"``, ``"NIFTY50 VALUE 20"``.

        Returns:
            DataFrame with ``date`` (datetime64) and ``nav`` (float) columns.

        Raises:
            FileNotFoundError: If no CSV was loaded for this index name.
        """
        if fund_name not in self._index_data:
            available = self.list_available()
            raise FileNotFoundError(
                f"No NSE CSV data found for '{fund_name}'. "
                f"Available: {available}. "
                f"Download the CSV from nseindia.com and place it in '{self.data_dir}'."
            )
        return self._index_data[fund_name].copy()

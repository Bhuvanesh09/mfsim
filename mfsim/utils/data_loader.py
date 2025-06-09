# mutual_fund_backtester/utils/data_loader.py

import os
import json
import pandas as pd
import importlib.resources as resourcelib
import requests
from abc import ABC, abstractmethod


def get_lowerbound_date(dates, target_date):
    return dates[dates.index >= target_date].index.min()


class BaseDataLoader(ABC):
    """
    Abstract base class for all data loaders.
    Subclass this to implement custom fund and NAV data sources.

    Fund List DataFrame (self.funds_list_df):
        - schemeName (str): Name of the fund
        - schemeCode (str or int): Unique code for the fund

    NAV Data DataFrame (returned by load_nav_data):
        - date (pandas datetime64): NAV date (should be sorted ascending)
        - nav (float): Net Asset Value for that date
        - Additional columns are allowed but not required.
    """

    def __init__(self, data_dir=None):
        self.data_dir = data_dir
        if not self.data_dir:
            # Use str() to get the path as a string
            self.data_dir = str(resourcelib.files("mfsim") / "data")
        self.fund_list_path = os.path.join(self.data_dir, "mf_list.json")
        self.nav_data_dir = os.path.join(self.data_dir, "nav_data")

    @abstractmethod
    def load_nav_data(self, fund_name) -> pd.DataFrame:
        """
        Load NAV data for a given fund. Should return a DataFrame with columns:
            - 'date': pandas datetime64 dtype (not string)
            - 'nav': float
        The DataFrame should be sorted by date ascending.
        """
        pass

    def get_expense_ratio(self, fund_name) -> float:
        """
        should return a single float value representing the expense ratio for the fund per year.
        
        """
        return 0

    def get_exit_load(self, fund_name) -> float:
        """
        should return a single float value representing the exit load for the fund.
        If no exit load is applicable, return 0.
        """
        return 0
        

class MfApiDataLoader(BaseDataLoader):
    """
    Data loader that fetches NAV data from api.mfapi.in and loads fund list from mf_list.json.
    """

    def __init__(self, data_dir=None):
        super().__init__(data_dir)
        self.load_fund_list()

    def load_fund_list(self) -> list:
        try:
            with open(self.fund_list_path, "r") as infile:
                data = json.load(infile)
            self.funds_list_df = pd.DataFrame.from_records(data)
            return self.funds_list_df.schemeName.tolist()
        except Exception as e:
            raise FileNotFoundError(f"Error loading fund list: {e}")

    def load_nav_data(self, fund_name) -> pd.DataFrame:
        try:
            fund_row = self.funds_list_df.loc[
                self.funds_list_df["schemeName"] == fund_name
            ]
            url = f"http://api.mfapi.in/mf/{fund_row['schemeCode'].tolist()[0]}"
            response = requests.get(url)
            json_data = response.json()
            fund_df = pd.DataFrame.from_records(json_data["data"])
            # Parse date column as pandas datetime (format: '%d-%m-%Y')
            fund_df["date"] = pd.to_datetime(fund_df["date"], format="%d-%m-%Y")
            fund_df["nav"] = fund_df["nav"].astype(float)
            return fund_df
        except Exception as e:
            raise FileNotFoundError(f"Error loading NAV data for {fund_name}: {e}")

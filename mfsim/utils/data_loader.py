# mutual_fund_backtester/utils/data_loader.py

import os
import json
import pandas as pd
import importlib.resources as resourcelib
import requests


def get_lowerbound_date(dates, target_date):
    return dates[dates.index >= target_date].index.min()


class DataLoader:
    def __init__(self, data_dir=None):
        self.data_dir = data_dir
        if not self.data_dir:
            self.data_dir = resourcelib.path("mfsim", "data")
        self.fund_list_path = os.path.join(self.data_dir, "mf_list.json")
        self.nav_data_dir = os.path.join(self.data_dir, "nav_data")
        self.load_fund_list()

    def load_fund_list(self):
        try:
            with open(self.fund_list_path, "r") as infile:
                data = json.load(infile)
            self.funds_list_df = pd.DataFrame.from_records(data)
            return self.funds_list_df.schemeName.tolist()
        except Exception as e:
            raise FileNotFoundError(f"Error loading fund list: {e}")

    def load_nav_data(self, fund_name):
        try:
            fund_row = self.funds_list_df.loc[
                self.funds_list_df["schemeName"] == fund_name
            ]

            url = f"http://api.mfapi.in/mf/{fund_row['schemeCode'].tolist()[0]}"
            response = requests.get(url)
            json_data = response.json()
            fund_df = pd.DataFrame.from_records(json_data["data"])

            return fund_df
        except Exception as e:
            raise FileNotFoundError(f"Error loading NAV data for {fund_name}: {e}")

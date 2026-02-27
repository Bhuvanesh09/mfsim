"""
Hydra-based backtest runner for mfsim.

Usage:
    # Run with default config (fixed allocation, index CSVs):
    uv run mfsim-backtest

    # Run a specific past experiment:
    uv run mfsim-backtest +experiment=fixed_alloc_no_rebal
    uv run mfsim-backtest +experiment=semi_annual_rebal
    uv run mfsim-backtest +experiment=nifty50_baseline
    uv run mfsim-backtest +experiment=momentum_value_short

    # Override individual params:
    uv run mfsim-backtest simulation.sip_amount=50000 simulation.start_date=2015-01-01

    # Switch strategy on the fly:
    uv run mfsim-backtest strategy=nifty50_baseline

    # Run multiple experiments (Hydra multirun):
    uv run mfsim-backtest --multirun +experiment=fixed_alloc_no_rebal,semi_annual_rebal,nifty50_baseline
"""

import logging
import os
import re

import hydra
import pandas as pd
from omegaconf import DictConfig, OmegaConf, open_dict

from mfsim.backtester.simulator import Simulator
from mfsim.strategies.base_strategy import BaseStrategy
from mfsim.strategies.custom_strategy import MomentumValueStrategy
from mfsim.utils.data_loader import BaseDataLoader, MfApiDataLoader

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Strategy builders — translate flat YAML config into Python strategy objects
# ---------------------------------------------------------------------------


class FixedAllocationStrategy(BaseStrategy):
    """Fixed allocation with optional SIP step-up. No rebalancing."""

    def __init__(self, frequency, metrics, fund_list, allocation, sip_increase_pct=0.0):
        super().__init__(frequency, metrics, fund_list)
        self.allocation = allocation
        self.sip_increase_pct = sip_increase_pct

    def allocate_money(self, money_invested, nav_data, current_date):
        return {fund: money_invested * pct for fund, pct in self.allocation.items()}

    def rebalance(self, portfolio, nav_data, current_date):
        return []

    def update_sip_amount(self, current_date, current_sip_amount):
        if self.sip_increase_pct == 0:
            return current_sip_amount
        if not hasattr(self, "_sip_start_date"):
            self._sip_start_date = current_date
            self._initial_sip = current_sip_amount
        years = current_date.year - self._sip_start_date.year
        return self._initial_sip * ((1 + self.sip_increase_pct) ** years)


class RebalancingStrategy(BaseStrategy):
    """Rebalances to target allocation on schedule, with optional SIP step-up."""

    def __init__(self, frequency, metrics, fund_list, allocation, sip_increase_pct=0.0):
        super().__init__(frequency, metrics, fund_list)
        self.allocation = allocation
        self.sip_increase_pct = sip_increase_pct

    def allocate_money(self, money_invested, nav_data, current_date):
        return {fund: money_invested * pct for fund, pct in self.allocation.items()}

    def rebalance(self, portfolio, nav_data, current_date):
        orders = []
        total_value = 0.0
        nav_on_date = {}
        for fund, units in portfolio.items():
            nav_df = nav_data[fund]
            nav_up_to_date = nav_df[nav_df.index <= current_date].sort_index()
            if nav_up_to_date.empty:
                nav_on_date[fund] = None
                continue
            nav_val = nav_up_to_date["nav"].iloc[-1]
            nav_on_date[fund] = float(nav_val)
            total_value += units * float(nav_val)

        for fund, pct in self.allocation.items():
            target_value = total_value * pct
            nav = nav_on_date.get(fund)
            if nav is None or nav == 0:
                continue
            current_value = portfolio.get(fund, 0) * nav
            diff = target_value - current_value
            if abs(diff) > 1e-6:
                orders.append({"fund_name": fund, "amount": diff})
        return orders

    def update_sip_amount(self, current_date, current_sip_amount):
        if self.sip_increase_pct == 0:
            return current_sip_amount
        if not hasattr(self, "_sip_start_date"):
            self._sip_start_date = current_date
            self._initial_sip = current_sip_amount
        years = current_date.year - self._sip_start_date.year
        return self._initial_sip * ((1 + self.sip_increase_pct) ** years)


def build_strategy(cfg: DictConfig) -> BaseStrategy:
    """Instantiate the right strategy class from the Hydra config."""
    strategy_cfg = cfg.strategy
    metrics = list(cfg.metrics)
    strategy_type = strategy_cfg.type

    sip_increase_pct = 0.0
    if cfg.sip_stepup.enabled:
        sip_increase_pct = cfg.sip_stepup.annual_increase_pct

    if strategy_type == "momentum_value":
        return MomentumValueStrategy(
            frequency=strategy_cfg.frequency,
            metrics=metrics,
            value_fund=strategy_cfg.value_fund,
            momentum_fund=strategy_cfg.momentum_fund,
            momentum_period=strategy_cfg.get("momentum_period", 180),
        )
    elif strategy_type == "fixed_allocation":
        allocation = OmegaConf.to_container(strategy_cfg.allocation, resolve=True)
        fund_list = list(strategy_cfg.fund_list)
        return FixedAllocationStrategy(
            frequency=strategy_cfg.frequency,
            metrics=metrics,
            fund_list=fund_list,
            allocation=allocation,
            sip_increase_pct=sip_increase_pct,
        )
    elif strategy_type == "rebalancing":
        allocation = OmegaConf.to_container(strategy_cfg.allocation, resolve=True)
        fund_list = list(strategy_cfg.fund_list)
        return RebalancingStrategy(
            frequency=strategy_cfg.frequency,
            metrics=metrics,
            fund_list=fund_list,
            allocation=allocation,
            sip_increase_pct=sip_increase_pct,
        )
    else:
        raise ValueError(f"Unknown strategy type: {strategy_type}")


# ---------------------------------------------------------------------------
# Data loader builder
# ---------------------------------------------------------------------------


class IndexCsvDataLoader(BaseDataLoader):
    """Load index NAV data from local CSV files with *_Historical_PR_* naming."""

    def __init__(self, data_dir):
        super().__init__(data_dir=data_dir)
        self.data_dir = data_dir
        self.index_dfs = self._load_all_csvs()

    def _load_all_csvs(self):
        dfs = {}
        csv_files = [
            f for f in os.listdir(self.data_dir) if f.endswith(".csv") and "_Historical_PR_" in f
        ]
        for file in csv_files:
            match = re.match(r"(.*?)_Historical_PR_.*\.csv", file)
            if match:
                index_name = match.group(1).strip().replace(" ", "_").replace("-", "_")
                df = pd.read_csv(os.path.join(self.data_dir, file))
                # Standardize column names
                for col in df.columns:
                    if "date" in col.lower():
                        if col != "date":
                            df.rename(columns={col: "date"}, inplace=True)
                        break
                if "Close" in df.columns:
                    df.rename(columns={"Close": "nav"}, inplace=True)
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"], errors="coerce")
                dfs[index_name] = df
        return dfs

    def load_nav_data(self, fund_name):
        key = fund_name.replace(" ", "_")
        if key not in self.index_dfs:
            raise ValueError(
                f"Index '{fund_name}' not found. Available: {list(self.index_dfs.keys())}"
            )
        df = self.index_dfs[key][["date", "nav"]].copy()
        df = df.sort_values("date")
        df["nav"] = df["nav"].astype(float)
        return df.reset_index(drop=True)


def build_data_loader(cfg: DictConfig) -> BaseDataLoader:
    """Instantiate the right data loader from the Hydra config."""
    dl_type = cfg.data_loader.type
    if dl_type == "mfapi":
        cache_ttl = cfg.data_loader.get("cache_ttl_hours", 24)
        cache_dir = cfg.data_loader.get("cache_dir", None)
        return MfApiDataLoader(cache_ttl_hours=cache_ttl, cache_dir=cache_dir)
    elif dl_type == "index_csv":
        data_dir = cfg.data_loader.get("data_dir", "./mfsim/data/")
        return IndexCsvDataLoader(data_dir)
    else:
        raise ValueError(f"Unknown data_loader type: {dl_type}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


@hydra.main(version_base=None, config_path="configs", config_name="config")
def main(cfg: DictConfig):
    # Hydra changes cwd to the output dir; resolve relative paths against original cwd
    orig_cwd = hydra.utils.get_original_cwd()
    data_dir = OmegaConf.select(cfg, "data_loader.data_dir")
    if data_dir is not None and not os.path.isabs(data_dir):
        with open_dict(cfg):
            cfg.data_loader.data_dir = os.path.join(orig_cwd, data_dir)

    log.info("Configuration:\n%s", OmegaConf.to_yaml(cfg))

    strategy = build_strategy(cfg)
    data_loader = build_data_loader(cfg)

    benchmark_fund = OmegaConf.select(cfg, "simulation.benchmark_fund", default=None)

    sim = Simulator(
        start_date=cfg.simulation.start_date,
        end_date=cfg.simulation.end_date,
        initial_investment=cfg.simulation.initial_investment,
        strategy=strategy,
        sip_amount=cfg.simulation.sip_amount,
        sip_frequency=cfg.simulation.sip_frequency,
        data_loader=data_loader,
        benchmark_fund=benchmark_fund,
    )

    results = sim.run()

    # Print results
    print("\n" + "=" * 60)
    print("BACKTEST RESULTS")
    print("=" * 60)
    print(f"Period:       {cfg.simulation.start_date} to {cfg.simulation.end_date}")
    print(f"Strategy:     {cfg.strategy.type} (rebalance: {cfg.strategy.frequency})")
    print(f"Initial:      {cfg.simulation.initial_investment:,.0f}")
    print(f"SIP:          {cfg.simulation.sip_amount:,.0f} / {cfg.simulation.sip_frequency}")
    if cfg.sip_stepup.enabled:
        print(f"SIP step-up:  {cfg.sip_stepup.annual_increase_pct * 100:.0f}% annually")
    print(f"Total invested: {sim.total_invested:,.2f}")
    print(f"Final value:    {sim.get_portfolio_value():,.2f}")
    if sim.total_stamp_duty > 0:
        print(f"Stamp duty:     {sim.total_stamp_duty:,.2f}")
    print("-" * 60)
    for metric_name, value in results.items():
        if isinstance(value, float):
            print(f"  {metric_name}: {value:.4f}")
        else:
            print(f"  {metric_name}: {value}")
    print("=" * 60)

    return results


if __name__ == "__main__":
    main()

"""
Experiment 001 (Extended): Momentum vs Value Factor Rotation — 10+ year backtest.

Uses NSE Total Return Index CSV data for longer history. The factor index funds
(Value 20, Momentum 30) only started in Feb/Mar 2021, so this experiment requires
manually-downloaded NSE index data.

HOW TO GET THE DATA
--------------------
1. Go to https://www.nseindia.com
2. Click: Market Data → Indices
3. For each index below, click the index name → Historical Data tab
4. Select type: "Total Returns Index" (preferred) or "Price Return Index"
5. Set date range: 01-Jan-2005 to today
6. Download and save to:  experiments/001_momentum_value_rotation/nse_data/

Files needed (NSE names these automatically):
  - NIFTY 50_Historical_TRI_<dates>.csv
  - NIFTY50 VALUE 20_Historical_TRI_<dates>.csv
  - NIFTY200 MOMENTUM 30_Historical_TRI_<dates>.csv       ← index name in NSE

Usage:
    uv run python experiments/001_momentum_value_rotation/run_extended.py

If data files are not found, falls back to the 5-year mfapi run with a clear warning.
"""

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from mfsim.backtester.simulator import Simulator
from mfsim.strategies.base_strategy import BaseStrategy
from mfsim.strategies.custom_strategy import MomentumValueStrategy
from mfsim.utils.data_loader import MfApiDataLoader
from mfsim.utils.nse_csv_loader import NseCsvLoader

# ---------------------------------------------------------------------------
# Paths and fund name mapping
# ---------------------------------------------------------------------------

NSE_DATA_DIR = Path(__file__).parent / "nse_data"

# NSE index name → mfapi fund name (for fallback)
NSE_TO_MFAPI = {
    "NIFTY 50": "UTI Nifty 50 Index Fund - Growth Option- Direct",
    "NIFTY50 VALUE 20": "Nippon India Nifty 50 Value 20 Index Fund - Direct Plan - Growth Option",
    "NIFTY200 MOMENTUM 30": "UTI Nifty 200 Momentum 30 Index Fund - Direct Plan - Growth Option",
}

# Short labels for display
LABELS = {
    "NIFTY 50": "Nifty 50",
    "NIFTY50 VALUE 20": "Value 20",
    "NIFTY200 MOMENTUM 30": "Momentum 30",
}

INITIAL = 100_000
SIP = 10_000
METRICS = ["Total Return", "XIRR", "Maximum Drawdown", "Sharpe Ratio", "Sortino Ratio"]

# ---------------------------------------------------------------------------
# Strategy definitions
# ---------------------------------------------------------------------------


def make_fixed_alloc(fund_list, allocation, freq="monthly"):
    class _S(BaseStrategy):
        def __init__(self):
            super().__init__(freq, METRICS, fund_list)
            self._allocation = allocation

        def allocate_money(self, money, nav_data, date):
            return {f: money * pct for f, pct in self._allocation.items()}

        def rebalance(self, portfolio, nav_data, date):
            return []

    return _S()


def make_annual_rebal(fund_list, allocation):
    class _S(BaseStrategy):
        def __init__(self):
            super().__init__("annually", METRICS, fund_list)
            self._allocation = allocation

        def allocate_money(self, money, nav_data, date):
            return {f: money * pct for f, pct in self._allocation.items()}

        def rebalance(self, portfolio, nav_data, date):
            orders = []
            total_value = 0.0
            navs = {}
            for f in self._allocation:
                if date not in nav_data[f].index:
                    continue
                nav_val = float(nav_data[f].loc[date, "nav"])
                navs[f] = nav_val
                total_value += portfolio.get(f, 0) * nav_val
            for f, pct in self._allocation.items():
                nav = navs.get(f)
                if nav is None:
                    continue
                diff = total_value * pct - portfolio.get(f, 0) * nav
                if abs(diff) > 1:
                    orders.append({"fund_name": f, "amount": diff})
            return orders

    return _S()


# ---------------------------------------------------------------------------
# Build experiment variants for a given (nifty50, value, momentum) name set
# ---------------------------------------------------------------------------


def build_variants(nifty50_name, value_name, momentum_name):
    v50 = nifty50_name
    vv = value_name
    vm = momentum_name
    return [
        ("nifty50_baseline", "Nifty 50 (buy & hold)", make_fixed_alloc([v50], {v50: 1.0})),
        ("value_only", "Value 20 (buy & hold)", make_fixed_alloc([vv], {vv: 1.0})),
        ("momentum_only", "Momentum 30 (buy & hold)", make_fixed_alloc([vm], {vm: 1.0})),
        (
            "50_50_fixed",
            "50/50 fixed",
            make_fixed_alloc([vv, vm], {vv: 0.5, vm: 0.5}),
        ),
        (
            "50_50_annual_rebal",
            "50/50 annual rebal",
            make_annual_rebal([vv, vm], {vv: 0.5, vm: 0.5}),
        ),
        (
            "dynamic_rotation",
            "Dynamic rotation (semi-annual 10%)",
            MomentumValueStrategy(
                frequency="semi-annually",
                metrics=METRICS,
                value_fund=vv,
                momentum_fund=vm,
                momentum_period=180,
            ),
        ),
    ]


# ---------------------------------------------------------------------------
# Run one variant
# ---------------------------------------------------------------------------


def run_variant(name, label, strategy, loader, start, end):
    sim = Simulator(
        start_date=start,
        end_date=end,
        initial_investment=INITIAL,
        strategy=strategy,
        sip_amount=SIP,
        sip_frequency="monthly",
        data_loader=loader,
    )
    results = sim.run()
    row = {
        "name": name,
        "label": label,
        "start": start,
        "end": end,
        "total_invested": sim.total_invested,
        "final_value": sim.get_portfolio_value(),
    }
    row.update({k: round(v, 6) if isinstance(v, float) else v for k, v in results.items()})
    return row, sim


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)

    # Detect whether NSE data is available
    nse_loader = NseCsvLoader(str(NSE_DATA_DIR)) if NSE_DATA_DIR.exists() else None
    available = nse_loader.list_available() if nse_loader else []

    nse_names = list(NSE_TO_MFAPI.keys())  # ["NIFTY 50", "NIFTY50 VALUE 20", ...]
    use_nse = all(n in available for n in nse_names)

    if use_nse:
        print("NSE data found — running extended backtest with index TRI data")
        loader = nse_loader
        fund_names = nse_names  # use NSE index names directly
        # Determine common date range from the loaded data
        dfs = [nse_loader.load_nav_data(n) for n in nse_names]
        start = max(df["date"].min() for df in dfs).strftime("%Y-%m-%d")
        end = min(df["date"].max() for df in dfs).strftime("%Y-%m-%d")
        print(f"Common period: {start} to {end}")
        suffix = "extended"
    else:
        if nse_loader and available:
            missing = [n for n in nse_names if n not in available]
            print(f"WARNING: Missing NSE files for: {missing}")
        print("NSE data not found — falling back to 5-year mfapi run")
        print(f"  Place NSE CSVs in: {NSE_DATA_DIR}/")
        print("  See docstring at top of this file for download instructions.\n")
        loader = MfApiDataLoader()
        fund_names = [NSE_TO_MFAPI[n] for n in nse_names]
        start, end = "2021-04-01", "2025-12-31"
        suffix = "mfapi"

    n50, vf, mf = fund_names
    variants = build_variants(n50, vf, mf)

    all_results = []
    for name, label, strategy in variants:
        print(f"\nRunning: {label} ...")
        try:
            row, sim = run_variant(name, label, strategy, loader, start, end)
            all_results.append(row)
            print(
                f"  TotalReturn={row.get('TotalReturn', float('nan')):.2%}  "
                f"XIRR={row.get('XIRR', float('nan')):.2%}  "
                f"MaxDD={row.get('MaximumDrawdown', float('nan')):.2%}  "
                f"Sharpe={row.get('SharpeRatio', float('nan')):.3f}"
            )
        except Exception as e:
            print(f"  ERROR: {e}")
            all_results.append({"name": name, "label": label, "error": str(e)})

    # Save
    json_path = results_dir / f"extended_{suffix}.json"
    with open(json_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to {json_path}")

    md_path = results_dir / f"extended_{suffix}.md"
    _write_markdown(all_results, start, end, md_path)
    print(f"Markdown saved to {md_path}")


def _write_markdown(results, start, end, path):
    rows = []
    for r in results:
        if "error" in r:
            rows.append({"Strategy": r["label"], "Total Return": "ERROR"})
        else:
            rows.append(
                {
                    "Strategy": r["label"],
                    "Total Invested": f"₹{r['total_invested']:,.0f}",
                    "Final Value": f"₹{r['final_value']:,.0f}",
                    "Total Return": f"{r.get('TotalReturn', float('nan')):.2%}",
                    "XIRR": f"{r.get('XIRR', float('nan')):.2%}",
                    "Max Drawdown": f"{r.get('MaximumDrawdown', float('nan')):.2%}",
                    "Sharpe": f"{r.get('SharpeRatio', float('nan')):.3f}",
                }
            )
    df = pd.DataFrame(rows)
    with open(path, "w") as f:
        f.write(f"# Experiment 001 (Extended): {start} to {end}\n\n")
        f.write(f"**Initial:** ₹{INITIAL:,} | **Monthly SIP:** ₹{SIP:,}\n\n")
        f.write(df.to_markdown(index=False))
        f.write("\n")


if __name__ == "__main__":
    main()

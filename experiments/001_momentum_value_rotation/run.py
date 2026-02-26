"""
Experiment 001: Momentum vs Value Factor Rotation (2021–2026)

Runs 6 strategy variants head-to-head over the same period and saves
results to results/summary.json and results/summary.md.

Usage:
    uv run python experiments/001_momentum_value_rotation/run.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

# Add project root to path so mfsim is importable
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from mfsim.backtester.simulator import Simulator
from mfsim.strategies.base_strategy import BaseStrategy
from mfsim.strategies.custom_strategy import MomentumValueStrategy
from mfsim.utils.data_loader import MfApiDataLoader

# ---------------------------------------------------------------------------
# Fund names
# ---------------------------------------------------------------------------

NIFTY50 = "UTI Nifty 50 Index Fund - Growth Option- Direct"
VALUE = "Nippon India Nifty 50 Value 20 Index Fund - Direct Plan - Growth Option"
MOMENTUM = "UTI Nifty 200 Momentum 30 Index Fund - Direct Plan - Growth Option"

START = "2021-04-01"
END = "2025-12-31"
INITIAL = 100_000
SIP = 10_000

# ---------------------------------------------------------------------------
# Inline strategy classes (mirrors cli.py to avoid Hydra dependency)
# ---------------------------------------------------------------------------


class FixedAlloc(BaseStrategy):
    def __init__(self, fund_list, allocation):
        super().__init__("monthly", METRICS, fund_list)
        self.allocation = allocation

    def allocate_money(self, money, nav_data, date):
        return {f: money * pct for f, pct in self.allocation.items()}

    def rebalance(self, portfolio, nav_data, date):
        return []


class AnnualRebal(BaseStrategy):
    def __init__(self, fund_list, allocation):
        super().__init__("annually", METRICS, fund_list)
        self.allocation = allocation

    def allocate_money(self, money, nav_data, date):
        return {f: money * pct for f, pct in self.allocation.items()}

    def rebalance(self, portfolio, nav_data, date):
        orders = []
        total_value = sum(
            portfolio.get(f, 0) * float(nav_data[f].loc[date, "nav"])
            for f in self.allocation
            if date in nav_data[f].index
        )
        for fund, pct in self.allocation.items():
            if date not in nav_data[fund].index:
                continue
            nav = float(nav_data[fund].loc[date, "nav"])
            current_val = portfolio.get(fund, 0) * nav
            diff = total_value * pct - current_val
            if abs(diff) > 1:
                orders.append({"fund_name": fund, "amount": diff})
        return orders


METRICS = ["Total Return", "XIRR", "Maximum Drawdown", "Sharpe Ratio", "Sortino Ratio"]

# ---------------------------------------------------------------------------
# Experiment variants
# ---------------------------------------------------------------------------

VARIANTS = [
    {
        "name": "nifty50_baseline",
        "label": "Nifty 50 (buy & hold)",
        "strategy": FixedAlloc([NIFTY50], {NIFTY50: 1.0}),
    },
    {
        "name": "value_only",
        "label": "Value 20 (buy & hold)",
        "strategy": FixedAlloc([VALUE], {VALUE: 1.0}),
    },
    {
        "name": "momentum_only",
        "label": "Momentum 30 (buy & hold)",
        "strategy": FixedAlloc([MOMENTUM], {MOMENTUM: 1.0}),
    },
    {
        "name": "50_50_fixed",
        "label": "50/50 Value+Momentum (no rebalance)",
        "strategy": FixedAlloc([VALUE, MOMENTUM], {VALUE: 0.5, MOMENTUM: 0.5}),
    },
    {
        "name": "50_50_annual_rebal",
        "label": "50/50 Value+Momentum (annual rebalance)",
        "strategy": AnnualRebal([VALUE, MOMENTUM], {VALUE: 0.5, MOMENTUM: 0.5}),
    },
    {
        "name": "dynamic_rotation",
        "label": "Dynamic rotation (semi-annual, 10% shift)",
        "strategy": MomentumValueStrategy(
            frequency="semi-annually",
            metrics=METRICS,
            value_fund=VALUE,
            momentum_fund=MOMENTUM,
            momentum_period=180,
        ),
    },
]


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def run_variant(variant: dict, loader: MfApiDataLoader) -> dict:
    sim = Simulator(
        start_date=START,
        end_date=END,
        initial_investment=INITIAL,
        strategy=variant["strategy"],
        sip_amount=SIP,
        sip_frequency="monthly",
        data_loader=loader,
    )
    results = sim.run()
    return {
        "name": variant["name"],
        "label": variant["label"],
        "total_invested": sim.total_invested,
        "final_value": sim.get_portfolio_value(),
        **{k: round(v, 6) if isinstance(v, float) else v for k, v in results.items()},
    }


def main():
    loader = MfApiDataLoader()
    all_results = []

    for variant in VARIANTS:
        print(f"\nRunning: {variant['label']} ...")
        try:
            result = run_variant(variant, loader)
            all_results.append(result)
            print(
                f"  Total Return: {result.get('TotalReturn', 'N/A'):.2%}  "
                f"XIRR: {result.get('XIRR', 'N/A'):.2%}  "
                f"Sharpe: {result.get('SharpeRatio', 'N/A'):.3f}"
            )
        except Exception as e:
            print(f"  ERROR: {e}")
            all_results.append({"name": variant["name"], "label": variant["label"], "error": str(e)})

    # Save JSON
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)

    json_path = results_dir / "summary.json"
    with open(json_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to {json_path}")

    # Save Markdown table
    _write_markdown(all_results, results_dir / "summary.md")
    print(f"Markdown table saved to {results_dir / 'summary.md'}")


def _write_markdown(results: list[dict], path: Path):
    rows = []
    for r in results:
        if "error" in r:
            rows.append(
                {
                    "Strategy": r["label"],
                    "Total Invested": "—",
                    "Final Value": "—",
                    "Total Return": "ERROR",
                    "XIRR": "—",
                    "Max Drawdown": "—",
                    "Sharpe": "—",
                    "Sortino": "—",
                }
            )
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
                    "Sortino": f"{r.get('SortinoRatio', float('nan')):.3f}",
                }
            )

    df = pd.DataFrame(rows)
    md = df.to_markdown(index=False)

    with open(path, "w") as f:
        f.write("# Experiment 001: Momentum vs Value Factor Rotation\n\n")
        f.write(f"**Period:** {START} to {END}  \n")
        f.write(f"**Initial investment:** ₹{INITIAL:,}  \n")
        f.write(f"**Monthly SIP:** ₹{SIP:,}  \n\n")
        f.write(md)
        f.write("\n\n---\n")
        f.write("*Generated by experiments/001_momentum_value_rotation/run.py*\n")


if __name__ == "__main__":
    main()

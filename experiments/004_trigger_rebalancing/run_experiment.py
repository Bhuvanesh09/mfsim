"""
Experiment 004: Trigger-Based Rebalancing with Cooldown
=======================================================

Tests whether daily signal checking with cooldown-gated mid-month rebalancing
improves adaptive strategy performance vs monthly-only rebalancing.

Uses best params from Experiment 002/003:
  - TrendFilter:       ma=100, risk_on=35%, risk_off=65%
  - RelativeStrength:  1m_only (30d horizon), sensitivity=0.5
  - DualSignal:        combines both

Comparisons:
  1. Each adaptive strategy: monthly-only vs trigger-enabled (cooldown=21)
  2. Cooldown sweep for TrendFilter: [5, 10, 15, 21, 30, 42, 63]
  3. Signal threshold sweep for RelativeStrength: [0.02, 0.05, 0.10, 0.15]
  4. Same 4 baselines as Experiment 002/003

Data: NSE PR index data from experiments/002_adaptive_factor_rotation/nse_data/

Usage:
    uv run python experiments/004_trigger_rebalancing/run_experiment.py
"""

import sys
import warnings
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

matplotlib.use("Agg")
warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from mfsim.backtester.simulator import Simulator  # noqa: E402
from mfsim.metrics.metrics_collection import (  # noqa: E402
    compute_portfolio_value_history,
)
from mfsim.strategies.adaptive_strategies import (  # noqa: E402
    DualSignalStrategy,
    RelativeStrengthStrategy,
    TrendFilterStrategy,
)
from mfsim.strategies.base_strategy import BaseStrategy  # noqa: E402
from mfsim.utils.nse_csv_loader import NseCsvLoader  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NSE_DATA_DIR = (
    Path(__file__).parent.parent
    / "002_adaptive_factor_rotation"
    / "nse_data"
)

VALUE = "Nifty50 Value 20"
MOMENTUM = "NIFTY200MOMENTM30"
NIFTY50 = "Nifty 50"

START_P1 = "2015-03-01"
START_P2 = "2020-02-01"
END = "2025-12-31"
INITIAL = 100_000
SIP = 10_000

METRICS = [
    "Total Return",
    "XIRR",
    "Maximum Drawdown",
    "Sharpe Ratio",
    "Sortino Ratio",
]

RESULTS_DIR = Path(__file__).parent / "results"
FIGURES_DIR = RESULTS_DIR / "figures"
RESULTS_DIR.mkdir(exist_ok=True)
FIGURES_DIR.mkdir(exist_ok=True)

# Best params from Experiment 002/003
BEST_MA = 100
BEST_RO = 0.35
BEST_HORIZON = {30: 1.0}
BEST_SENS = 0.5

# Sweep params
COOLDOWN_DAYS = [5, 10, 15, 21, 30, 42, 63]
SIGNAL_THRESHOLDS = [0.02, 0.05, 0.10, 0.15]


# ---------------------------------------------------------------------------
# Baseline strategy
# ---------------------------------------------------------------------------


class _FixedAlloc(BaseStrategy):
    def __init__(self, fund_list, allocation):
        super().__init__("monthly", METRICS, fund_list)
        self.allocation = allocation

    def allocate_money(self, money, nav_data, date):
        return {f: money * pct for f, pct in self.allocation.items()}

    def rebalance(self, portfolio, nav_data, date):
        return []


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _fmt_pct(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "---"
    return f"{x:.2%}"


def _fmt_f(x, decimals=3):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "---"
    return f"{x:.{decimals}f}"


# ---------------------------------------------------------------------------
# Simulation runner
# ---------------------------------------------------------------------------


def run_sim(strategy, label, loader, start, keep_sim=False):
    """Run a single backtest and return results dict."""
    sim = Simulator(
        start_date=start,
        end_date=END,
        initial_investment=INITIAL,
        strategy=strategy,
        sip_amount=SIP,
        sip_frequency="monthly",
        data_loader=loader,
    )
    results = sim.run()
    end_date = pd.to_datetime(END)
    xirr = results.get("XIRR", float("nan"))
    maxdd = results.get("MaximumDrawdown", float("nan"))
    calmar = (
        abs(xirr / maxdd)
        if not (np.isnan(xirr) or np.isnan(maxdd) or maxdd == 0)
        else float("nan")
    )
    scheduled = sum(
        1 for r in sim.rebalance_log if r["type"] == "scheduled"
    )
    triggered = sum(
        1 for r in sim.rebalance_log if r["type"] == "triggered"
    )
    row = {
        "label": label,
        "XIRR": xirr,
        "SharpeRatio": results.get("SharpeRatio", float("nan")),
        "SortinoRatio": results.get("SortinoRatio", float("nan")),
        "MaximumDrawdown": maxdd,
        "Calmar": calmar,
        "TotalReturn": results.get("TotalReturn", float("nan")),
        "total_invested": sim.total_invested,
        "final_value": sim.get_portfolio_value(end_date),
        "scheduled_rebalances": scheduled,
        "triggered_rebalances": triggered,
        "total_rebalances": scheduled + triggered,
    }
    if keep_sim:
        row["_sim"] = sim
    return row


# ---------------------------------------------------------------------------
# Strategy builders
# ---------------------------------------------------------------------------


def make_tf(trigger_enabled=False, cooldown_days=21):
    return TrendFilterStrategy(
        value_fund=VALUE,
        momentum_fund=MOMENTUM,
        trend_fund=NIFTY50,
        ma_window=BEST_MA,
        risk_on_m_weight=BEST_RO,
        risk_off_m_weight=1.0 - BEST_RO,
        trigger_enabled=trigger_enabled,
        cooldown_days=cooldown_days,
    )


def make_rs(
    trigger_enabled=False, cooldown_days=21, signal_threshold=0.05,
):
    return RelativeStrengthStrategy(
        value_fund=VALUE,
        momentum_fund=MOMENTUM,
        horizon_weights=BEST_HORIZON,
        sensitivity=BEST_SENS,
        trigger_enabled=trigger_enabled,
        cooldown_days=cooldown_days,
        signal_threshold=signal_threshold,
    )


def make_dual(
    trigger_enabled=False, cooldown_days=21, signal_threshold=0.05,
):
    return DualSignalStrategy(
        value_fund=VALUE,
        momentum_fund=MOMENTUM,
        trend_fund=NIFTY50,
        ma_window=BEST_MA,
        risk_on_m_weight=BEST_RO,
        risk_off_m_weight=1.0 - BEST_RO,
        horizon_weights=BEST_HORIZON,
        sensitivity=BEST_SENS,
        trigger_enabled=trigger_enabled,
        cooldown_days=cooldown_days,
        signal_threshold=signal_threshold,
    )


# ---------------------------------------------------------------------------
# Sweep runners
# ---------------------------------------------------------------------------


def run_baselines(loader, start, keep_sim=False):
    configs = [
        (
            "Nifty 50 (buy & hold)",
            _FixedAlloc([NIFTY50], {NIFTY50: 1.0}),
        ),
        (
            "50/50 Fixed (no rebalance)",
            _FixedAlloc(
                [VALUE, MOMENTUM], {VALUE: 0.5, MOMENTUM: 0.5}
            ),
        ),
        ("Value 20 only", _FixedAlloc([VALUE], {VALUE: 1.0})),
        (
            "Momentum 30 only",
            _FixedAlloc([MOMENTUM], {MOMENTUM: 1.0}),
        ),
    ]
    results, sims = [], []
    for label, strategy in configs:
        print(f"  Running: {label} ...")
        row = run_sim(strategy, label, loader, start, keep_sim)
        results.append({k: v for k, v in row.items() if k != "_sim"})
        if keep_sim:
            sims.append((label, row["_sim"]))
        print(
            f"    XIRR={_fmt_pct(row['XIRR'])}  "
            f"Sharpe={_fmt_f(row['SharpeRatio'])}"
        )
    return results, sims


def run_trigger_vs_monthly(loader, start):
    """Compare monthly-only vs trigger-enabled for each strategy."""
    print("\n=== TRIGGER vs MONTHLY COMPARISON ===")
    results = []
    for name, make_fn in [
        ("TrendFilter", make_tf),
        ("RelativeStrength", make_rs),
        ("DualSignal", make_dual),
    ]:
        # Monthly only
        label_m = f"{name} (monthly)"
        row_m = run_sim(
            make_fn(trigger_enabled=False),
            label_m, loader, start, keep_sim=True,
        )
        results.append(row_m)
        print(
            f"  {label_m}: XIRR={_fmt_pct(row_m['XIRR'])} "
            f"rebal={row_m['total_rebalances']}"
        )

        # Trigger enabled
        label_t = f"{name} (trigger cd=21)"
        row_t = run_sim(
            make_fn(trigger_enabled=True, cooldown_days=21),
            label_t, loader, start, keep_sim=True,
        )
        results.append(row_t)
        print(
            f"  {label_t}: XIRR={_fmt_pct(row_t['XIRR'])} "
            f"rebal={row_t['total_rebalances']} "
            f"(sched={row_t['scheduled_rebalances']}, "
            f"trig={row_t['triggered_rebalances']})"
        )
    return results


def run_cooldown_sweep(loader, start):
    """Sweep cooldown days for TrendFilter."""
    print("\n=== COOLDOWN SWEEP (TrendFilter) ===")
    results = []
    for cd in COOLDOWN_DAYS:
        label = f"TF cd={cd}"
        strategy = make_tf(trigger_enabled=True, cooldown_days=cd)
        row = run_sim(strategy, label, loader, start, keep_sim=True)
        row["cooldown_days"] = cd
        results.append(row)
        print(
            f"  cd={cd:3d}  XIRR={_fmt_pct(row['XIRR'])}  "
            f"Sharpe={_fmt_f(row['SharpeRatio'])}  "
            f"triggers={row['triggered_rebalances']}"
        )
    return results


def run_threshold_sweep(loader, start):
    """Sweep signal threshold for RelativeStrength."""
    print("\n=== SIGNAL THRESHOLD SWEEP (RelativeStrength) ===")
    results = []
    for thresh in SIGNAL_THRESHOLDS:
        label = f"RS thresh={thresh}"
        strategy = make_rs(
            trigger_enabled=True, cooldown_days=21,
            signal_threshold=thresh,
        )
        row = run_sim(strategy, label, loader, start, keep_sim=True)
        row["signal_threshold"] = thresh
        results.append(row)
        print(
            f"  thresh={thresh:.2f}  "
            f"XIRR={_fmt_pct(row['XIRR'])}  "
            f"Sharpe={_fmt_f(row['SharpeRatio'])}  "
            f"triggers={row['triggered_rebalances']}"
        )
    return results


# ---------------------------------------------------------------------------
# Figure generators
# ---------------------------------------------------------------------------


def fig_trigger_vs_monthly(results):
    """Grouped bar chart: monthly vs trigger for each strategy."""
    df = pd.DataFrame(results)
    metrics_info = [
        ("XIRR", "XIRR (%)", lambda x: x * 100),
        ("SharpeRatio", "Sharpe Ratio", lambda x: x),
        ("MaximumDrawdown", "Max DD (%)", lambda x: x * 100),
    ]
    labels = df["label"].tolist()
    n = len(labels)

    fig, axes = plt.subplots(1, 3, figsize=(16, 7))
    colors = []
    for i, lbl in enumerate(labels):
        if "monthly" in lbl:
            colors.append("steelblue")
        else:
            colors.append("coral")

    for ax, (col, xlabel, transform) in zip(axes, metrics_info):
        vals = [transform(v) for v in df[col].tolist()]
        bars = ax.barh(labels, vals, color=colors, edgecolor="white")
        ax.set_xlabel(xlabel)
        ax.axvline(0, color="black", linewidth=0.8)
        ax.grid(True, axis="x", alpha=0.3)
        for bar, v in zip(bars, vals):
            ha = "left" if v >= 0 else "right"
            fmt = f" {v:.1f}%" if "%" in xlabel else f" {v:.3f}"
            ax.text(
                v, bar.get_y() + bar.get_height() / 2,
                fmt, va="center", ha=ha, fontsize=8,
            )
        ax.set_title(xlabel)

    fig.suptitle(
        "Experiment 004 -- Trigger vs Monthly Rebalancing",
        fontsize=13, y=1.01,
    )
    fig.tight_layout()
    path = FIGURES_DIR / "trigger_vs_monthly_comparison.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


def fig_cooldown_sweep(results):
    """Line charts for XIRR, Sharpe, trigger count vs cooldown."""
    df = pd.DataFrame(results)
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(16, 5))

    ax1.plot(
        df["cooldown_days"], df["XIRR"] * 100,
        marker="o", color="steelblue",
    )
    ax1.set_xlabel("Cooldown (days)")
    ax1.set_ylabel("XIRR (%)")
    ax1.set_title("XIRR vs Cooldown")
    ax1.grid(True, alpha=0.3)

    ax2.plot(
        df["cooldown_days"], df["SharpeRatio"],
        marker="s", color="coral",
    )
    ax2.set_xlabel("Cooldown (days)")
    ax2.set_ylabel("Sharpe Ratio")
    ax2.set_title("Sharpe vs Cooldown")
    ax2.grid(True, alpha=0.3)

    ax3.bar(
        df["cooldown_days"].astype(str),
        df["triggered_rebalances"],
        color="seagreen", alpha=0.8,
    )
    ax3.set_xlabel("Cooldown (days)")
    ax3.set_ylabel("Triggered Rebalances")
    ax3.set_title("Trigger Count vs Cooldown")
    ax3.grid(True, axis="y", alpha=0.3)

    fig.suptitle(
        "TrendFilter Cooldown Sweep", fontsize=13, y=1.02,
    )
    fig.tight_layout()
    path = FIGURES_DIR / "cooldown_sweep.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


def fig_threshold_sweep(results):
    """Line charts for XIRR, Sharpe, trigger count vs threshold."""
    df = pd.DataFrame(results)
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(16, 5))

    ax1.plot(
        df["signal_threshold"], df["XIRR"] * 100,
        marker="o", color="steelblue",
    )
    ax1.set_xlabel("Signal Threshold")
    ax1.set_ylabel("XIRR (%)")
    ax1.set_title("XIRR vs Threshold")
    ax1.grid(True, alpha=0.3)

    ax2.plot(
        df["signal_threshold"], df["SharpeRatio"],
        marker="s", color="coral",
    )
    ax2.set_xlabel("Signal Threshold")
    ax2.set_ylabel("Sharpe Ratio")
    ax2.set_title("Sharpe vs Threshold")
    ax2.grid(True, alpha=0.3)

    ax3.bar(
        [str(t) for t in df["signal_threshold"]],
        df["triggered_rebalances"],
        color="seagreen", alpha=0.8,
    )
    ax3.set_xlabel("Signal Threshold")
    ax3.set_ylabel("Triggered Rebalances")
    ax3.set_title("Trigger Count vs Threshold")
    ax3.grid(True, axis="y", alpha=0.3)

    fig.suptitle(
        "RelativeStrength Signal Threshold Sweep",
        fontsize=13, y=1.02,
    )
    fig.tight_layout()
    path = FIGURES_DIR / "threshold_sweep.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


def fig_rebalance_count_comparison(trigger_results):
    """Stacked bar: scheduled vs triggered rebalance counts."""
    df = pd.DataFrame(trigger_results)
    labels = df["label"].tolist()
    x = np.arange(len(labels))

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(
        x, df["scheduled_rebalances"],
        label="Scheduled", color="steelblue", alpha=0.8,
    )
    ax.bar(
        x, df["triggered_rebalances"],
        bottom=df["scheduled_rebalances"],
        label="Triggered", color="coral", alpha=0.8,
    )
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Number of Rebalances")
    ax.set_title("Rebalance Count Breakdown")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)

    fig.tight_layout()
    path = FIGURES_DIR / "rebalance_count_comparison.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


def fig_trigger_timing_scatter(trigger_results):
    """Scatter plot of trigger dates for each strategy."""
    fig, ax = plt.subplots(figsize=(14, 5))
    colors = sns.color_palette("tab10", n_colors=len(trigger_results))

    y_offset = 0
    yticks, ylabels = [], []
    for row, color in zip(trigger_results, colors):
        sim = row.get("_sim")
        if sim is None:
            continue
        label = row["label"]
        trigger_dates = [
            r["date"]
            for r in sim.rebalance_log
            if r["type"] == "triggered"
        ]
        if not trigger_dates:
            y_offset += 1
            yticks.append(y_offset)
            ylabels.append(label)
            continue
        ax.scatter(
            trigger_dates,
            [y_offset + 1] * len(trigger_dates),
            marker="|", s=100, color=color, label=label,
        )
        y_offset += 1
        yticks.append(y_offset)
        ylabels.append(label)

    # Mark COVID crash
    ax.axvline(
        pd.Timestamp("2020-02-20"), color="red",
        linewidth=1, linestyle=":", alpha=0.7,
    )
    ax.text(
        pd.Timestamp("2020-02-20"), 0.5, "  COVID",
        fontsize=8, color="red", va="bottom",
    )

    ax.set_yticks(yticks)
    ax.set_yticklabels(ylabels, fontsize=8)
    ax.set_xlabel("Date")
    ax.set_title("Trigger Timing (each | = a triggered rebalance)")
    ax.grid(True, axis="x", alpha=0.3)
    fig.tight_layout()
    path = FIGURES_DIR / "trigger_timing_scatter.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


def fig_drawdown_during_covid(trigger_results, loader):
    """Drawdown curves during COVID period (Jan-Jun 2020)."""
    end_date = pd.to_datetime(END)
    covid_start = pd.Timestamp("2020-01-01")
    covid_end = pd.Timestamp("2020-06-30")

    fig, ax = plt.subplots(figsize=(14, 6))
    colors = sns.color_palette("tab10", n_colors=len(trigger_results))

    for row, color in zip(trigger_results, colors):
        sim = row.get("_sim")
        if sim is None:
            continue
        label = row["label"]
        hist = compute_portfolio_value_history(
            sim.portfolio_history_df, sim.nav_data, end_date,
        )
        hist = hist[hist > 0]
        # Slice to COVID window
        covid_hist = hist[
            (hist.index >= covid_start) & (hist.index <= covid_end)
        ]
        if covid_hist.empty or len(covid_hist) < 2:
            continue
        # Compute drawdown from running peak
        running_peak = covid_hist.cummax()
        drawdown = (covid_hist - running_peak) / running_peak * 100
        ax.plot(
            drawdown.index, drawdown.values,
            label=label, color=color, linewidth=1.5,
        )

    ax.set_xlabel("Date")
    ax.set_ylabel("Drawdown (%)")
    ax.set_title("Drawdown During COVID (Jan -- Jun 2020)")
    ax.legend(bbox_to_anchor=(1.01, 1), loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    path = FIGURES_DIR / "drawdown_during_covid.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _table_md(rows, columns):
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    lines = [header, sep]
    for row in rows:
        cells = []
        for c in columns:
            cells.append(str(row.get(c, "---")))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_report(
    baseline_results, trigger_results, cooldown_results,
    threshold_results,
):
    def _row(r):
        return {
            "Strategy": r["label"],
            "XIRR": _fmt_pct(r["XIRR"]),
            "Sharpe": _fmt_f(r["SharpeRatio"]),
            "Sortino": _fmt_f(r["SortinoRatio"]),
            "Calmar": _fmt_f(r["Calmar"]),
            "Max DD": _fmt_pct(r["MaximumDrawdown"]),
            "Sched": r.get("scheduled_rebalances", "---"),
            "Trig": r.get("triggered_rebalances", "---"),
            "Total": r.get("total_rebalances", "---"),
        }

    cols = [
        "Strategy", "XIRR", "Sharpe", "Sortino",
        "Calmar", "Max DD", "Sched", "Trig", "Total",
    ]

    bl_rows = [_row(r) for r in baseline_results]
    tr_rows = [_row(r) for r in trigger_results]
    cd_rows = []
    for r in cooldown_results:
        row = _row(r)
        row["Cooldown"] = r.get("cooldown_days", "---")
        cd_rows.append(row)
    th_rows = []
    for r in threshold_results:
        row = _row(r)
        row["Threshold"] = r.get("signal_threshold", "---")
        th_rows.append(row)

    report = f"""# Experiment 004 -- Trigger-Based Rebalancing

## 1. Purpose

Test whether daily signal checking with cooldown-gated mid-month
rebalancing improves adaptive strategy performance vs monthly-only
rebalancing.

## 2. Setup

| Parameter | Value |
|---|---|
| Period (P1) | {START_P1} -> {END} |
| Period (P2 stress) | {START_P2} -> {END} |
| Initial Investment | INR {INITIAL:,} |
| Monthly SIP | INR {SIP:,} |
| TrendFilter params | ma={BEST_MA}, risk_on={BEST_RO:.0%} |
| RelativeStrength params | 1m_only, sensitivity={BEST_SENS} |
| Data Source | NSE PR index data |

---

## 3. Baselines

{_table_md(bl_rows, cols)}

---

## 4. Trigger vs Monthly Comparison

{_table_md(tr_rows, cols)}

![Trigger vs Monthly](figures/trigger_vs_monthly_comparison.png)

![Rebalance Count](figures/rebalance_count_comparison.png)

---

## 5. Cooldown Sweep (TrendFilter)

Cooldown values tested: {COOLDOWN_DAYS}

{_table_md(cd_rows, ["Cooldown"] + cols)}

![Cooldown Sweep](figures/cooldown_sweep.png)

---

## 6. Signal Threshold Sweep (RelativeStrength)

Thresholds tested: {SIGNAL_THRESHOLDS}

{_table_md(th_rows, ["Threshold"] + cols)}

![Threshold Sweep](figures/threshold_sweep.png)

---

## 7. Trigger Timing

![Trigger Timing](figures/trigger_timing_scatter.png)

---

## 8. Drawdown During COVID

![COVID Drawdown](figures/drawdown_during_covid.png)
"""
    report_path = RESULTS_DIR / "REPORT.md"
    report_path.write_text(report)
    print(f"\nReport saved to {report_path}")


# ---------------------------------------------------------------------------
# Console summary
# ---------------------------------------------------------------------------


def print_summary(title, results):
    print(f"\n=== {title} ===")
    hdr = (
        f"{'Strategy':<40} {'XIRR':>8} {'Sharpe':>7} "
        f"{'Calmar':>7} {'Max DD':>9} "
        f"{'Sched':>6} {'Trig':>5} {'Total':>6}"
    )
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        print(
            f"{r['label']:<40} "
            f"{_fmt_pct(r['XIRR']):>8} "
            f"{_fmt_f(r['SharpeRatio']):>7} "
            f"{_fmt_f(r['Calmar']):>7} "
            f"{_fmt_pct(r['MaximumDrawdown']):>9} "
            f"{r.get('scheduled_rebalances', '-'):>6} "
            f"{r.get('triggered_rebalances', '-'):>5} "
            f"{r.get('total_rebalances', '-'):>6}"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    loader = NseCsvLoader(str(NSE_DATA_DIR))

    # Step 1: Baselines
    print("\n=== BASELINES (Period 1) ===")
    baseline_results, _ = run_baselines(loader, START_P1)

    # Step 2: Trigger vs Monthly comparison
    trigger_results = run_trigger_vs_monthly(loader, START_P1)

    # Step 3: Cooldown sweep
    cooldown_results = run_cooldown_sweep(loader, START_P1)

    # Step 4: Signal threshold sweep
    threshold_results = run_threshold_sweep(loader, START_P1)

    # Step 5: Figures
    print("\n=== GENERATING FIGURES ===")
    fig_trigger_vs_monthly(
        [r for r in trigger_results if "_sim" not in r or True],
    )
    fig_cooldown_sweep(cooldown_results)
    fig_threshold_sweep(threshold_results)

    # Rebalance count for trigger-enabled strategies only
    trigger_enabled = [
        r for r in trigger_results if "trigger" in r["label"]
    ]
    fig_rebalance_count_comparison(trigger_results)

    # Trigger timing scatter
    fig_trigger_timing_scatter(trigger_results)

    # COVID drawdown
    fig_drawdown_during_covid(trigger_results, loader)

    # Step 6: Report
    write_report(
        baseline_results, trigger_results,
        cooldown_results, threshold_results,
    )

    # Step 7: Summary
    print_summary("BASELINES", baseline_results)
    print_summary("TRIGGER vs MONTHLY", trigger_results)
    print_summary("COOLDOWN SWEEP", cooldown_results)
    print_summary("THRESHOLD SWEEP", threshold_results)
    print()


if __name__ == "__main__":
    main()

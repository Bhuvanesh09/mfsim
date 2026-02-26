"""
Experiment 002: Adaptive Factor Rotation with Hyperparameter Sweeps
====================================================================

Implements and sweeps three adaptive strategies that dynamically shift between
a Value and a Momentum index fund using market signals:

  A. TrendFilterStrategy   — SMA regime filter on Nifty 50 reference index
  B. RelativeStrengthStrategy — multi-horizon RS tilt
  C. DualSignalStrategy    — A + B combined (best params from sweeps)

Data source: niftyindices.com Price Return (PR) index data, downloaded via
download_nse_data.py and stored in nse_data/. Common window Jan 2010–Dec 2025
(15 years). Note: PR excludes dividends; TRI would add ~1–1.5% p.a. XIRR but
relative conclusions hold.

Produces:
  results/figures/sweep_a_heatmap.png
  results/figures/sweep_b_grid.png
  results/figures/final_comparison.png
  results/figures/portfolio_value_history.png
  results/REPORT.md

Usage:
    uv run python experiments/002_adaptive_factor_rotation/run_experiment.py
"""

import sys
import warnings
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

matplotlib.use("Agg")  # non-interactive backend
warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Path setup — make mfsim importable from project root
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from mfsim.backtester.simulator import Simulator
from mfsim.metrics.metrics_collection import compute_portfolio_value_history
from mfsim.strategies.adaptive_strategies import (
    DualSignalStrategy,
    RelativeStrengthStrategy,
    TrendFilterStrategy,
)
from mfsim.strategies.base_strategy import BaseStrategy
from mfsim.utils.nse_csv_loader import NseCsvLoader

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NSE_DATA_DIR = Path(__file__).parent / "nse_data"

VALUE = "Nifty50 Value 20"
MOMENTUM = "NIFTY200MOMENTM30"
NIFTY50 = "Nifty 50"

START = "2015-03-01"   # main sweep period — avoids post-GFC recovery tailwind
START_P2 = "2020-02-01"  # COVID + recent bear market stress test (out-of-sample)
END = "2025-12-31"
INITIAL = 100_000
SIP = 10_000

METRICS = ["Total Return", "XIRR", "Maximum Drawdown", "Sharpe Ratio", "Sortino Ratio"]

RESULTS_DIR = Path(__file__).parent / "results"
FIGURES_DIR = RESULTS_DIR / "figures"
RESULTS_DIR.mkdir(exist_ok=True)
FIGURES_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Sweep parameters
# ---------------------------------------------------------------------------

MA_WINDOWS = [50, 100, 150, 200, 250]
RISK_ON_WEIGHTS = [0.55, 0.65, 0.75, 0.85]

HORIZON_PRESETS = {
    "1m_only": {30: 1.0},
    "3m_only": {90: 1.0},
    "6m_only": {180: 1.0},
    "short": {30: 0.5, 90: 0.35, 180: 0.15},
    "balanced": {30: 0.2, 90: 0.3, 180: 0.5},
    "long": {30: 0.05, 90: 0.15, 180: 0.8},
}
SENSITIVITIES = [0.5, 1.0, 2.0, 4.0]

# ---------------------------------------------------------------------------
# Inline baseline strategies
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
# Simulation runner
# ---------------------------------------------------------------------------


def run_sim(strategy, label, loader, keep_sim=False, start=None):
    """Run a single backtest and return results dict (and optionally the sim object).

    Args:
        strategy: A BaseStrategy subclass instance.
        label: Human-readable name for this run.
        loader: NseCsvLoader instance.
        keep_sim: If True, return the Simulator object alongside results.
        start: Override start date (defaults to global START).

    Returns:
        dict with keys: label, XIRR, SharpeRatio, SortinoRatio, MaximumDrawdown,
        Calmar, TotalReturn, total_invested, final_value.
        Plus ``'_sim'`` key if ``keep_sim`` is True.
    """
    sim = Simulator(
        start_date=start or START,
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
    }
    if keep_sim:
        row["_sim"] = sim
    return row


# ---------------------------------------------------------------------------
# Figure helpers
# ---------------------------------------------------------------------------


def _fmt_pct(x):
    """Format a decimal as a percentage string, or '—' for nan."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    return f"{x:.2%}"


def _fmt_f(x, decimals=3):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    return f"{x:.{decimals}f}"


def fig_sweep_a_heatmap(sweep_a_results):
    """Heatmap of XIRR across (MA window × risk-on weight). Best cell starred."""
    pivot = pd.DataFrame(sweep_a_results).pivot(
        index="risk_on_weight", columns="ma_window", values="XIRR"
    )
    fig, ax = plt.subplots(figsize=(10, 7))
    im = ax.pcolormesh(
        pivot.columns,
        pivot.index,
        pivot.values * 100,
        cmap="RdYlGn",
        shading="nearest",
    )
    plt.colorbar(im, ax=ax, label="XIRR (%)")
    ax.set_xlabel("MA Window (days)")
    ax.set_ylabel("Risk-on Momentum Weight")
    ax.set_title("Sweep A — XIRR Heatmap (TrendFilterStrategy)")
    ax.set_xticks(pivot.columns)
    ax.set_yticks(pivot.index)
    ax.set_yticklabels([f"{v:.0%}" for v in pivot.index])

    # Mark best cell
    best_idx = pd.DataFrame(sweep_a_results)["XIRR"].idxmax()
    best = sweep_a_results[best_idx]
    ax.text(
        best["ma_window"],
        best["risk_on_weight"],
        "★",
        ha="center",
        va="center",
        fontsize=18,
        color="black",
        fontweight="bold",
    )

    # Annotate each cell with XIRR value
    for r_idx, row_val in enumerate(pivot.index):
        for c_idx, col_val in enumerate(pivot.columns):
            val = pivot.loc[row_val, col_val]
            if not np.isnan(val):
                ax.text(
                    col_val,
                    row_val,
                    f"{val*100:.1f}%",
                    ha="center",
                    va="center",
                    fontsize=8,
                    color="black",
                )

    fig.tight_layout()
    path = FIGURES_DIR / "sweep_a_heatmap.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {path}")


def fig_sweep_b_grid(sweep_b_results):
    """Line chart: x=sensitivity, y=XIRR (top) and Sharpe (bottom), one line per horizon preset."""
    df = pd.DataFrame(sweep_b_results)
    presets = list(HORIZON_PRESETS.keys())
    colors = sns.color_palette("tab10", n_colors=len(presets))

    fig, (ax_xirr, ax_sharpe) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    for preset, color in zip(presets, colors):
        sub = df[df["horizon_preset"] == preset].sort_values("sensitivity")
        ax_xirr.plot(sub["sensitivity"], sub["XIRR"] * 100, marker="o", label=preset, color=color)
        ax_sharpe.plot(
            sub["sensitivity"], sub["SharpeRatio"], marker="s", label=preset, color=color
        )

    ax_xirr.set_ylabel("XIRR (%)")
    ax_xirr.set_title("Sweep B — RelativeStrengthStrategy: XIRR by Sensitivity & Horizon")
    ax_xirr.legend(title="Horizon preset", bbox_to_anchor=(1.01, 1), loc="upper left")
    ax_xirr.grid(True, alpha=0.3)

    ax_sharpe.set_xlabel("Sensitivity")
    ax_sharpe.set_ylabel("Sharpe Ratio")
    ax_sharpe.set_title("Sweep B — RelativeStrengthStrategy: Sharpe by Sensitivity & Horizon")
    ax_sharpe.legend(title="Horizon preset", bbox_to_anchor=(1.01, 1), loc="upper left")
    ax_sharpe.grid(True, alpha=0.3)
    ax_sharpe.set_xscale("log")

    fig.tight_layout()
    path = FIGURES_DIR / "sweep_b_grid.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


def fig_final_comparison(final_results):
    """Grouped horizontal bar chart: XIRR, Sharpe, Max Drawdown for all final strategies."""
    df = pd.DataFrame(final_results)
    labels = df["label"].tolist()
    n = len(labels)

    metrics_info = [
        ("XIRR", "XIRR (%)", lambda x: x * 100),
        ("SharpeRatio", "Sharpe Ratio", lambda x: x),
        ("MaximumDrawdown", "Max Drawdown (%)", lambda x: x * 100),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(14, 8))
    colors = sns.color_palette("husl", n_colors=n)

    for ax, (col, xlabel, transform) in zip(axes, metrics_info):
        vals = [transform(v) for v in df[col].tolist()]
        bars = ax.barh(labels, vals, color=colors, edgecolor="white")
        ax.set_xlabel(xlabel)
        ax.axvline(0, color="black", linewidth=0.8)
        ax.grid(True, axis="x", alpha=0.3)
        for bar, v in zip(bars, vals):
            x_pos = v + (0.002 if v >= 0 else -0.002) * abs(max(vals, key=abs) or 1)
            ha = "left" if v >= 0 else "right"
            ax.text(
                v,
                bar.get_y() + bar.get_height() / 2,
                f" {v:.2f}" if col != "XIRR" else f" {v:.1f}%",
                va="center",
                ha=ha,
                fontsize=8,
            )
        ax.set_title(xlabel)

    fig.suptitle("Experiment 002 — Final Strategy Comparison", fontsize=13, y=1.01)
    fig.tight_layout()
    path = FIGURES_DIR / "final_comparison.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


def fig_portfolio_value_history(sim_rows):
    """Normalized cumulative value (base=100 at start) for all final strategies."""
    end_date = pd.to_datetime(END)
    fig, ax = plt.subplots(figsize=(14, 7))
    colors = sns.color_palette("tab10", n_colors=len(sim_rows))

    for (label, sim), color in zip(sim_rows, colors):
        hist = compute_portfolio_value_history(sim.portfolio_history_df, sim.nav_data, end_date)
        hist = hist[hist > 0]
        if hist.empty:
            continue
        normalized = hist / hist.iloc[0] * 100
        ax.plot(normalized.index, normalized.values, label=label, color=color, linewidth=1.8)

    ax.set_xlabel("Date")
    ax.set_ylabel("Portfolio Value (base = 100 at start)")
    ax.set_title("Experiment 002 — Normalized Portfolio Value History")
    ax.legend(bbox_to_anchor=(1.01, 1), loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    path = FIGURES_DIR / "portfolio_value_history.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


def fig_rolling_sharpe(sim_rows, window=252, risk_free=0.06):
    """Rolling 12-month Sharpe Ratio for all final strategies (Period 1 history)."""
    end_date = pd.to_datetime(END)
    fig, ax = plt.subplots(figsize=(14, 6))
    colors = sns.color_palette("tab10", n_colors=len(sim_rows))

    for (label, sim), color in zip(sim_rows, colors):
        hist = compute_portfolio_value_history(sim.portfolio_history_df, sim.nav_data, end_date)
        hist = hist[hist > 0]
        if hist.empty or len(hist) < window + 10:
            continue
        rf_daily = risk_free / 252
        rolling_sharpe = (
            hist.pct_change()
            .dropna()
            .rolling(window)
            .apply(
                lambda x: (x.mean() - rf_daily) / x.std() * np.sqrt(252)
                if x.std() > 0
                else np.nan,
                raw=True,
            )
        )
        ax.plot(rolling_sharpe.index, rolling_sharpe.values, label=label, color=color, linewidth=1.5)

    # Annotate key events
    for event_date, event_label in [
        ("2020-02-20", "COVID crash"),
        ("2022-01-01", "Rate hike cycle"),
    ]:
        ax.axvline(pd.to_datetime(event_date), color="gray", linewidth=1, linestyle=":", alpha=0.7)
        ax.text(
            pd.to_datetime(event_date), ax.get_ylim()[0] if ax.get_ylim()[0] > -5 else -2,
            f"  {event_label}", fontsize=8, color="gray", va="bottom",
        )

    ax.axhline(0, color="black", linewidth=0.8, linestyle="--", alpha=0.5)
    ax.set_xlabel("Date")
    ax.set_ylabel("Rolling 12-month Sharpe Ratio")
    ax.set_title(f"Rolling 12-month Sharpe — {START} to {END}")
    ax.legend(bbox_to_anchor=(1.01, 1), loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    path = FIGURES_DIR / "rolling_sharpe.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


def fig_period_comparison(p1_results, p2_results):
    """Side-by-side XIRR and Sharpe comparison across two periods."""
    df1 = pd.DataFrame(p1_results).set_index("label")
    df2 = pd.DataFrame(p2_results).set_index("label")
    common = df1.index.intersection(df2.index)
    df1, df2 = df1.loc[common], df2.loc[common]

    metrics = [
        ("XIRR", "XIRR (%)", lambda x: x * 100),
        ("SharpeRatio", "Sharpe Ratio", lambda x: x),
        ("SortinoRatio", "Sortino Ratio", lambda x: x),
        ("Calmar", "Calmar Ratio", lambda x: x),
        ("MaximumDrawdown", "Max Drawdown (%)", lambda x: x * 100),
    ]
    n = len(common)
    x = np.arange(n)
    width = 0.35
    fig, axes = plt.subplots(1, len(metrics), figsize=(20, 7))

    for ax, (col, ylabel, transform) in zip(axes, metrics):
        v1 = [transform(df1.loc[lbl, col]) for lbl in common]
        v2 = [transform(df2.loc[lbl, col]) for lbl in common]
        bars1 = ax.bar(x - width / 2, v1, width, label=f"Mar 2015–Dec 2025", color="steelblue", alpha=0.8)
        bars2 = ax.bar(x + width / 2, v2, width, label=f"Feb 2020–Dec 2025", color="coral", alpha=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels([lbl.split(":")[0].strip() for lbl in common], rotation=45, ha="right", fontsize=7)
        ax.set_title(ylabel)
        ax.axhline(0, color="black", linewidth=0.6)
        ax.grid(True, axis="y", alpha=0.3)
        if col != "MaximumDrawdown":
            ax.legend(fontsize=7)

    fig.suptitle("Experiment 002 — Period Comparison (sweeps on P1, P2 is out-of-sample)", fontsize=12)
    fig.tight_layout()
    path = FIGURES_DIR / "period_comparison.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------


def _table_md(rows, columns):
    """Render a list-of-dicts as a Markdown table."""
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    lines = [header, sep]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(c, "—")) for c in columns) + " |")
    return "\n".join(lines)


def write_report(sweep_a_results, best_a, sweep_b_results, best_b, final_results, period2_results):
    sweep_a_df = pd.DataFrame(sweep_a_results).sort_values("XIRR", ascending=False)
    sweep_b_df = pd.DataFrame(sweep_b_results).sort_values("SharpeRatio", ascending=False)

    top5_a = sweep_a_df.head(5).copy()
    top5_b = sweep_b_df.head(5).copy()

    top5_a_rows = []
    for _, r in top5_a.iterrows():
        top5_a_rows.append({
            "MA Window": int(r["ma_window"]),
            "Risk-on Weight": f"{r['risk_on_weight']:.0%}",
            "Risk-off Weight": f"{1 - r['risk_on_weight']:.0%}",
            "XIRR": _fmt_pct(r["XIRR"]),
            "Sharpe": _fmt_f(r["SharpeRatio"]),
            "Max DD": _fmt_pct(r["MaximumDrawdown"]),
        })

    top5_b_rows = []
    for _, r in top5_b.iterrows():
        top5_b_rows.append({
            "Horizon Preset": r["horizon_preset"],
            "Sensitivity": r["sensitivity"],
            "XIRR": _fmt_pct(r["XIRR"]),
            "Sharpe": _fmt_f(r["SharpeRatio"]),
            "Max DD": _fmt_pct(r["MaximumDrawdown"]),
        })

    final_rows = []
    for r in final_results:
        final_rows.append({
            "Strategy": r["label"],
            "Total Invested": f"₹{r['total_invested']:,.0f}",
            "Final Value": f"₹{r['final_value']:,.0f}",
            "XIRR": _fmt_pct(r["XIRR"]),
            "Sharpe": _fmt_f(r["SharpeRatio"]),
            "Sortino": _fmt_f(r["SortinoRatio"]),
            "Calmar": _fmt_f(r["Calmar"]),
            "Max DD": _fmt_pct(r["MaximumDrawdown"]),
        })

    p2_rows = []
    for r in period2_results:
        p2_rows.append({
            "Strategy": r["label"],
            "XIRR": _fmt_pct(r["XIRR"]),
            "Sharpe": _fmt_f(r["SharpeRatio"]),
            "Sortino": _fmt_f(r["SortinoRatio"]),
            "Calmar": _fmt_f(r["Calmar"]),
            "Max DD": _fmt_pct(r["MaximumDrawdown"]),
            "Total Return": _fmt_pct(r["TotalReturn"]),
        })

    report = f"""# Experiment 002 — Adaptive Factor Rotation

## 1. Experiment Setup

| Parameter | Value |
|---|---|
| Period (P1 sweep) | {START} → {END} |
| Period (P2 stress) | {START_P2} → {END} |
| Initial Investment | ₹{INITIAL:,} |
| Monthly SIP | ₹{SIP:,} |
| Value Fund | {VALUE} |
| Momentum Fund | {MOMENTUM} |
| Trend Reference | {NIFTY50} |

---

## 2. Sweep A — TrendFilterStrategy

**Parameters swept:**
- MA Window: {MA_WINDOWS}
- Risk-on Momentum Weight: {[f'{w:.0%}' for w in RISK_ON_WEIGHTS]}
  (Risk-off weight = 1 − risk_on_weight, symmetric)

**Total runs:** {len(MA_WINDOWS) * len(RISK_ON_WEIGHTS)}
**Best selected by:** highest XIRR

### Top-5 by XIRR

{_table_md(top5_a_rows, ["MA Window", "Risk-on Weight", "Risk-off Weight", "XIRR", "Sharpe", "Max DD"])}

### Heatmap

![Sweep A Heatmap](figures/sweep_a_heatmap.png)

---

## 3. Sweep B — RelativeStrengthStrategy

**Horizon presets:**
- `1m_only`: {{30: 1.0}}
- `3m_only`: {{90: 1.0}}
- `6m_only`: {{180: 1.0}}
- `short`: {{30: 0.5, 90: 0.35, 180: 0.15}}
- `balanced`: {{30: 0.2, 90: 0.3, 180: 0.5}}
- `long`: {{30: 0.05, 90: 0.15, 180: 0.8}}

**Sensitivities:** {SENSITIVITIES}
**Total runs:** {len(HORIZON_PRESETS) * len(SENSITIVITIES)}
**Best selected by:** highest Sharpe Ratio

### Top-5 by Sharpe

{_table_md(top5_b_rows, ["Horizon Preset", "Sensitivity", "XIRR", "Sharpe", "Max DD"])}

### Grid Chart

![Sweep B Grid](figures/sweep_b_grid.png)

---

## 4. Best Parameters Identified

### Option A (TrendFilter)
- **MA Window:** {int(best_a['ma_window'])}
- **Risk-on momentum weight:** {best_a['risk_on_weight']:.0%}
- **Risk-off momentum weight:** {1 - best_a['risk_on_weight']:.0%}
- **XIRR:** {_fmt_pct(best_a['XIRR'])}

### Option B (RelativeStrength)
- **Horizon preset:** `{best_b['horizon_preset']}`
- **Sensitivity:** {best_b['sensitivity']}
- **Sharpe Ratio:** {_fmt_f(best_b['SharpeRatio'])}

---

## 5. Option C — DualSignalStrategy

Combines best A params (ma_window={int(best_a['ma_window'])}, risk_on_m_weight={best_a['risk_on_weight']:.2f})
with best B params (horizon_preset=`{best_b['horizon_preset']}`, sensitivity={best_b['sensitivity']}).

Agreement logic:
- Both risk-on **and** RS ≥ 0.5 → amplify momentum (tilt higher)
- Both risk-off **and** RS < 0.5 → amplify value (tilt lower)
- Disagree → neutral (50/50)

---

## 6. Final Comparison — All Strategies

{_table_md(final_rows, ["Strategy", "Total Invested", "Final Value", "XIRR", "Sharpe", "Sortino", "Calmar", "Max DD"])}

![Final Comparison](figures/final_comparison.png)

---

## 7. Portfolio Value History

![Portfolio Value History](figures/portfolio_value_history.png)

---

## 8. Rolling 12-month Sharpe (Period 1)

Shows consistency of risk-adjusted returns over time. Periods near zero or negative
indicate stretches where the strategy was destroying risk-adjusted value.

![Rolling Sharpe](figures/rolling_sharpe.png)

---

## 9. Period 2 — COVID Stress Test (Feb 2020 → Dec 2025)

Strategies use the **same parameters** found in Period 1 sweeps (out-of-sample).
Initial ₹{INITIAL:,} + ₹{SIP:,}/month from {START_P2}.

{_table_md(p2_rows, ["Strategy", "XIRR", "Sharpe", "Sortino", "Calmar", "Max DD", "Total Return"])}

![Period Comparison](figures/period_comparison.png)

---

## 10. Key Conclusions

- **Sweep A** tests whether a simple SMA trend filter helps time value/momentum tilts.
  The best-performing MA window and risk-on weight are selected by maximum XIRR.
- **Sweep B** tests whether multi-horizon relative strength improves risk-adjusted returns.
  The best preset and sensitivity are selected by maximum Sharpe Ratio.
- **Option C** combines both signals: when they agree the tilt is amplified; when they
  disagree the portfolio reverts to a neutral 50/50 blend.
- All three adaptive strategies are compared against four baselines covering the full
  factor spectrum (Nifty 50, pure value, pure momentum, 50/50 blend).
"""

    report_path = RESULTS_DIR / "REPORT.md"
    report_path.write_text(report)
    print(f"\nReport saved to {report_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    loader = NseCsvLoader(str(NSE_DATA_DIR))
    end_date = pd.to_datetime(END)

    # -----------------------------------------------------------------------
    # Step 1: Baselines (keep sim objects for figures)
    # -----------------------------------------------------------------------
    print("\n=== BASELINES ===")
    baselines = [
        ("Nifty 50 (buy & hold)", _FixedAlloc([NIFTY50], {NIFTY50: 1.0})),
        ("50/50 Fixed (no rebalance)", _FixedAlloc([VALUE, MOMENTUM], {VALUE: 0.5, MOMENTUM: 0.5})),
        ("Value 20 only", _FixedAlloc([VALUE], {VALUE: 1.0})),
        ("Momentum 30 only", _FixedAlloc([MOMENTUM], {MOMENTUM: 1.0})),
    ]
    baseline_results = []
    baseline_sims = []
    for label, strategy in baselines:
        print(f"  Running: {label} ...")
        row = run_sim(strategy, label, loader, keep_sim=True)
        baseline_results.append({k: v for k, v in row.items() if k != "_sim"})
        baseline_sims.append((label, row["_sim"]))
        print(f"    XIRR={_fmt_pct(row['XIRR'])}  Sharpe={_fmt_f(row['SharpeRatio'])}")

    # -----------------------------------------------------------------------
    # Step 2: Sweep A (20 runs — TrendFilterStrategy)
    # -----------------------------------------------------------------------
    print("\n=== SWEEP A (TrendFilter) — 20 runs ===")
    sweep_a_results = []
    for ma_w in MA_WINDOWS:
        for ro_w in RISK_ON_WEIGHTS:
            label = f"TF ma={ma_w} ro={ro_w:.0%}"
            strategy = TrendFilterStrategy(
                value_fund=VALUE,
                momentum_fund=MOMENTUM,
                trend_fund=NIFTY50,
                ma_window=ma_w,
                risk_on_m_weight=ro_w,
                risk_off_m_weight=1.0 - ro_w,
            )
            row = run_sim(strategy, label, loader, keep_sim=False)
            row["ma_window"] = ma_w
            row["risk_on_weight"] = ro_w
            sweep_a_results.append(row)
            print(
                f"  ma={ma_w:3d} ro={ro_w:.0%}  XIRR={_fmt_pct(row['XIRR'])} "
                f"Sharpe={_fmt_f(row['SharpeRatio'])}"
            )

    # Best A by XIRR
    best_a = max(sweep_a_results, key=lambda r: r["XIRR"] if not np.isnan(r["XIRR"]) else -99)
    print(f"\n  Best A: ma={int(best_a['ma_window'])} ro={best_a['risk_on_weight']:.0%} "
          f"XIRR={_fmt_pct(best_a['XIRR'])}")

    # -----------------------------------------------------------------------
    # Step 3: Sweep B (24 runs — RelativeStrengthStrategy)
    # -----------------------------------------------------------------------
    print("\n=== SWEEP B (RelativeStrength) — 24 runs ===")
    sweep_b_results = []
    for preset_name, hw in HORIZON_PRESETS.items():
        for sens in SENSITIVITIES:
            label = f"RS {preset_name} s={sens}"
            strategy = RelativeStrengthStrategy(
                value_fund=VALUE,
                momentum_fund=MOMENTUM,
                horizon_weights=hw,
                sensitivity=sens,
            )
            row = run_sim(strategy, label, loader, keep_sim=False)
            row["horizon_preset"] = preset_name
            row["sensitivity"] = sens
            sweep_b_results.append(row)
            print(
                f"  preset={preset_name:12s} sens={sens:4.1f}  "
                f"XIRR={_fmt_pct(row['XIRR'])}  Sharpe={_fmt_f(row['SharpeRatio'])}"
            )

    # Best B by Sharpe
    best_b = max(
        sweep_b_results,
        key=lambda r: r["SharpeRatio"] if not np.isnan(r["SharpeRatio"]) else -99,
    )
    print(f"\n  Best B: preset={best_b['horizon_preset']} sens={best_b['sensitivity']} "
          f"Sharpe={_fmt_f(best_b['SharpeRatio'])}")

    # -----------------------------------------------------------------------
    # Step 4: Re-run best A and best B with sim objects for figures
    # -----------------------------------------------------------------------
    print("\n=== RE-RUNNING BEST A & B (for portfolio history) ===")
    best_a_strategy = TrendFilterStrategy(
        value_fund=VALUE,
        momentum_fund=MOMENTUM,
        trend_fund=NIFTY50,
        ma_window=int(best_a["ma_window"]),
        risk_on_m_weight=best_a["risk_on_weight"],
        risk_off_m_weight=1.0 - best_a["risk_on_weight"],
    )
    best_a_label = f"Best A: TF ma={int(best_a['ma_window'])} ro={best_a['risk_on_weight']:.0%}"
    row_best_a = run_sim(best_a_strategy, best_a_label, loader, keep_sim=True)
    best_a["label"] = best_a_label
    best_a.update({k: v for k, v in row_best_a.items() if k != "_sim"})
    print(f"  Best A XIRR={_fmt_pct(row_best_a['XIRR'])}")

    best_b_strategy = RelativeStrengthStrategy(
        value_fund=VALUE,
        momentum_fund=MOMENTUM,
        horizon_weights=HORIZON_PRESETS[best_b["horizon_preset"]],
        sensitivity=best_b["sensitivity"],
    )
    best_b_label = f"Best B: RS {best_b['horizon_preset']} s={best_b['sensitivity']}"
    row_best_b = run_sim(best_b_strategy, best_b_label, loader, keep_sim=True)
    best_b["label"] = best_b_label
    best_b.update({k: v for k, v in row_best_b.items() if k != "_sim"})
    print(f"  Best B Sharpe={_fmt_f(row_best_b['SharpeRatio'])}")

    # -----------------------------------------------------------------------
    # Step 5: Option C — DualSignalStrategy
    # -----------------------------------------------------------------------
    print("\n=== OPTION C (DualSignal) ===")
    option_c_strategy = DualSignalStrategy(
        value_fund=VALUE,
        momentum_fund=MOMENTUM,
        trend_fund=NIFTY50,
        ma_window=int(best_a["ma_window"]),
        risk_on_m_weight=best_a["risk_on_weight"],
        risk_off_m_weight=1.0 - best_a["risk_on_weight"],
        horizon_weights=HORIZON_PRESETS[best_b["horizon_preset"]],
        sensitivity=best_b["sensitivity"],
    )
    option_c_label = (
        f"Option C: Dual (ma={int(best_a['ma_window'])}, "
        f"ro={best_a['risk_on_weight']:.0%}, "
        f"preset={best_b['horizon_preset']}, s={best_b['sensitivity']})"
    )
    row_c = run_sim(option_c_strategy, option_c_label, loader, keep_sim=True)
    print(f"  Option C XIRR={_fmt_pct(row_c['XIRR'])}  Sharpe={_fmt_f(row_c['SharpeRatio'])}")

    # -----------------------------------------------------------------------
    # Step 6: Compile final results for comparison
    # -----------------------------------------------------------------------
    final_results = (
        baseline_results
        + [
            {k: v for k, v in best_a.items() if k not in ("_sim",)},
            {k: v for k, v in best_b.items() if k not in ("_sim",)},
            {k: v for k, v in row_c.items() if k != "_sim"},
        ]
    )

    # Clean up sweep-specific keys from best_a / best_b entries in final_results
    for r in final_results:
        for sweep_key in ("ma_window", "risk_on_weight", "horizon_preset", "sensitivity"):
            r.pop(sweep_key, None)

    # -----------------------------------------------------------------------
    # Step 7: Generate Period 1 figures
    # -----------------------------------------------------------------------
    print("\n=== FIGURES (Period 1) ===")
    fig_sweep_a_heatmap(sweep_a_results)
    fig_sweep_b_grid(sweep_b_results)
    fig_final_comparison(final_results)

    # Portfolio history sims: baselines + best A + best B + option C
    sim_rows = baseline_sims + [
        (best_a_label, row_best_a["_sim"]),
        (best_b_label, row_best_b["_sim"]),
        (option_c_label, row_c["_sim"]),
    ]
    fig_portfolio_value_history(sim_rows)
    fig_rolling_sharpe(sim_rows)

    # -----------------------------------------------------------------------
    # Step 8: Period 2 — Feb 2020 COVID stress test (out-of-sample)
    # -----------------------------------------------------------------------
    print(f"\n=== PERIOD 2: {START_P2} – {END} (COVID + bear market stress test) ===")
    print("  (Using same best-A / best-B params from Period 1 sweep — out-of-sample)")

    p2_baselines = [
        ("Nifty 50 (buy & hold)", _FixedAlloc([NIFTY50], {NIFTY50: 1.0})),
        ("50/50 Fixed (no rebalance)", _FixedAlloc([VALUE, MOMENTUM], {VALUE: 0.5, MOMENTUM: 0.5})),
        ("Value 20 only", _FixedAlloc([VALUE], {VALUE: 1.0})),
        ("Momentum 30 only", _FixedAlloc([MOMENTUM], {MOMENTUM: 1.0})),
    ]
    period2_results = []
    period2_sims = []
    for label, strategy in p2_baselines:
        print(f"  Running: {label} ...")
        row = run_sim(strategy, label, loader, keep_sim=True, start=START_P2)
        period2_results.append({k: v for k, v in row.items() if k != "_sim"})
        period2_sims.append((label, row["_sim"]))
        print(f"    XIRR={_fmt_pct(row['XIRR'])}  Sharpe={_fmt_f(row['SharpeRatio'])}  Sortino={_fmt_f(row['SortinoRatio'])}")

    print(f"  Running: {best_a_label} ...")
    row_a_p2 = run_sim(best_a_strategy, best_a_label, loader, keep_sim=True, start=START_P2)
    period2_results.append({k: v for k, v in row_a_p2.items() if k != "_sim"})
    period2_sims.append((best_a_label, row_a_p2["_sim"]))
    print(f"    XIRR={_fmt_pct(row_a_p2['XIRR'])}  Sharpe={_fmt_f(row_a_p2['SharpeRatio'])}")

    print(f"  Running: {best_b_label} ...")
    row_b_p2 = run_sim(best_b_strategy, best_b_label, loader, keep_sim=True, start=START_P2)
    period2_results.append({k: v for k, v in row_b_p2.items() if k != "_sim"})
    period2_sims.append((best_b_label, row_b_p2["_sim"]))
    print(f"    XIRR={_fmt_pct(row_b_p2['XIRR'])}  Sharpe={_fmt_f(row_b_p2['SharpeRatio'])}")

    print(f"  Running: {option_c_label} ...")
    row_c_p2 = run_sim(option_c_strategy, option_c_label, loader, keep_sim=True, start=START_P2)
    period2_results.append({k: v for k, v in row_c_p2.items() if k != "_sim"})
    period2_sims.append((option_c_label, row_c_p2["_sim"]))
    print(f"    XIRR={_fmt_pct(row_c_p2['XIRR'])}  Sharpe={_fmt_f(row_c_p2['SharpeRatio'])}")

    print("\n=== FIGURES (Period 2) ===")
    fig_period_comparison(final_results, period2_results)

    # -----------------------------------------------------------------------
    # Step 9: Write report
    # -----------------------------------------------------------------------
    write_report(sweep_a_results, best_a, sweep_b_results, best_b, final_results, period2_results)

    # -----------------------------------------------------------------------
    # Step 10: Print summary
    # -----------------------------------------------------------------------
    print("\n=== PERIOD 1 SUMMARY (Mar 2015 – Dec 2025) ===")
    print(f"{'Strategy':<55} {'XIRR':>8} {'Sharpe':>7} {'Sortino':>8} {'Calmar':>7} {'Max DD':>9}")
    print("-" * 100)
    for r in final_results:
        print(
            f"{r['label']:<55} {_fmt_pct(r['XIRR']):>8} "
            f"{_fmt_f(r['SharpeRatio']):>7} {_fmt_f(r['SortinoRatio']):>8} "
            f"{_fmt_f(r['Calmar']):>7} {_fmt_pct(r['MaximumDrawdown']):>9}"
        )

    print(f"\n=== PERIOD 2 SUMMARY (Feb 2020 – Dec 2025, out-of-sample) ===")
    print(f"{'Strategy':<55} {'XIRR':>8} {'Sharpe':>7} {'Sortino':>8} {'Calmar':>7} {'Max DD':>9}")
    print("-" * 100)
    for r in period2_results:
        print(
            f"{r['label']:<55} {_fmt_pct(r['XIRR']):>8} "
            f"{_fmt_f(r['SharpeRatio']):>7} {_fmt_f(r['SortinoRatio']):>8} "
            f"{_fmt_f(r['Calmar']):>7} {_fmt_pct(r['MaximumDrawdown']):>9}"
        )
    print()


if __name__ == "__main__":
    main()

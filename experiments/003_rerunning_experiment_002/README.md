# Experiment 003 — Independent Rerun of Experiment 002

## Purpose

Independent validation of Experiment 002 (Adaptive Factor Rotation). Same data,
same strategies, same parameter ranges. All numerical claims below are verified
against the actual output of this run.

## How to reproduce

```bash
uv run python experiments/003_rerunning_experiment_002/run_experiment.py
```

Data source: NSE Price Return (PR) index CSVs from
`experiments/002_adaptive_factor_rotation/nse_data/`. PR data excludes dividends;
TRI would add ~1-1.5% p.a. XIRR, but relative rankings hold.

## Setup

- **Period 1 (P1):** Mar 2015 - Dec 2025 (sweep period)
- **Period 2 (P2):** Feb 2020 - Dec 2025 (COVID stress subperiod, same params)
- **Investment:** Rs 1L initial + Rs 10K/month SIP
- **Funds:** Nifty50 Value 20, NIFTY200 Momentum 30, Nifty 50 (trend reference)

## Validation result

All values match Experiment 002 exactly. The correctness fixes applied after
Experiment 002's initial run (holiday NAV lookup, Sortino frequency) are confirmed
working. No NaN values in any metric.

## Key findings

### 1. Pure Momentum 30 dominates on most metrics

Period 1 results (verified):

| Strategy | XIRR | Sharpe | Sortino | Calmar | Max DD |
|---|---|---|---|---|---|
| Momentum 30 only | 17.35% | 1.318 | 1.458 | 0.530 | -32.75% |
| Best TrendFilter (ma=100, ro=35%) | 17.31% | 1.100 | 1.211 | 0.535 | -32.37% |
| Best RelativeStrength (1m_only, s=0.5) | 15.72% | 1.084 | 1.177 | 0.492 | -31.98% |
| DualSignal (combined) | 15.92% | 1.087 | 1.179 | 0.498 | -31.95% |

Pure Momentum 30 has the highest XIRR (17.35%), highest Sharpe (1.318), and
highest Sortino (1.458) among all strategies. The adaptive strategies do not beat
the pure momentum baseline on any risk-adjusted metric in Period 1.

### 2. Adaptive strategies reduce Sharpe and Sortino

This is the most important finding. All three adaptive strategies (TrendFilter,
RelativeStrength, DualSignal) produce **lower** Sharpe and Sortino ratios than
every baseline, including the 50/50 Fixed allocation:

- 50/50 Fixed: Sharpe 1.209, Sortino 1.286
- Best TrendFilter: Sharpe 1.100, Sortino 1.211
- Best RelativeStrength: Sharpe 1.084, Sortino 1.177
- DualSignal: Sharpe 1.087, Sortino 1.179

The rotation signal adds volatility without adding proportional return.

### 3. TrendFilter's best parameters are counter-intuitive

The best TrendFilter uses `risk_on_m_weight=0.35` (35% momentum when above SMA,
65% momentum when below SMA). This means: tilt toward **value** when the market
is above its moving average, and tilt toward **momentum** when below. This is the
opposite of the intended risk-on/risk-off logic, and suggests the optimizer found
a contrarian rotation that happened to work in this period. It may be overfit.

### 4. Drawdown protection is the adaptive strategies' one advantage

In Period 2 (COVID stress, Feb 2020-Dec 2025), the TrendFilter shows meaningful
drawdown reduction:

| Strategy | Max DD (P2) | Calmar (P2) |
|---|---|---|
| Momentum 30 only | -30.67% | 0.579 |
| Best TrendFilter | -26.91% | 0.659 |
| DualSignal | -26.49% | 0.624 |

TrendFilter reduces max drawdown by ~3.8pp vs pure Momentum in the COVID period,
producing the best Calmar ratio (0.659) across both periods. But this comes at
the cost of lower Sharpe (1.290 vs 1.514) and lower Sortino (1.413 vs 1.664).

### 5. RelativeStrength Sweep B shows minimal differentiation

All top-5 Sweep B results cluster tightly (Sharpe 1.083-1.084). The sensitivity
parameter at 0.5 (minimum tested) universally outperforms higher sensitivities,
meaning the RS signal works best when dampened — another sign that the signal
adds noise more than information.

## Honest assessment

The adaptive factor rotation strategies tested here do not improve risk-adjusted
returns vs static allocations in this 10-year backtest. Their primary value is
modest drawdown reduction (~3-4pp max DD improvement in the COVID period). A
simple buy-and-hold of the Momentum 30 index produces higher XIRR, higher Sharpe,
and higher Sortino than any adaptive strategy tested.

The TrendFilter's best-performing parameters invert the intended risk-on/risk-off
logic, suggesting the result may be period-specific rather than capturing a
robust market timing signal.

## Output files

- `results/REPORT.md` — auto-generated report with full tables
- `results/figures/sweep_a_heatmap.png` — XIRR heatmap across MA window x risk-on weight
- `results/figures/sweep_b_grid.png` — XIRR and Sharpe by horizon preset and sensitivity
- `results/figures/final_comparison.png` — bar chart comparing all strategies
- `results/figures/portfolio_value_history.png` — normalized portfolio growth
- `results/figures/rolling_sharpe.png` — rolling 12-month Sharpe
- `results/figures/period_comparison.png` — P1 vs P2 side-by-side

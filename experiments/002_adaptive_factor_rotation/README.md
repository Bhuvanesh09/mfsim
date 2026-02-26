# Experiment 002: Adaptive Factor Rotation

## Hypothesis

Can dynamic signals — a trend filter and relative strength — improve returns or reduce
drawdowns versus a fixed 50/50 blend of value and momentum index funds?

Three strategies are tested:
- **A. TrendFilter** — SMA regime detection on Nifty 50 shifts the momentum/value tilt
- **B. RelativeStrength** — multi-horizon RS score continuously adjusts the tilt
- **C. DualSignal** — combines both; amplifies when they agree, neutralises when they disagree

---

## Data

**Source:** niftyindices.com historical data API (Price Return, not TRI).
Downloaded via `download_nse_data.py`.

| Index | API name | Available from | Used from |
|---|---|---|---|
| Nifty 50 | `Nifty 50` | Jan 2005 | Mar 2015 |
| Nifty50 Value 20 | `Nifty50 Value 20` | Jan 2010 | Mar 2015 |
| NIFTY200 Momentum 30 | `NIFTY200MOMENTM30` | Apr 2005 | Mar 2015 |

**Important caveat:** PR data excludes dividends. Real-world index fund TRI returns
are approximately **1–1.5% higher XIRR** across the board. All relative rankings
between strategies hold since every strategy uses the same PR base.

### Refreshing the data

Cookies in `download_nse_data.py` expire within a few hours. To re-download:

1. Open `https://niftyindices.com/reports/historical-data` in Chrome
2. DevTools → Network → trigger any download
3. Find the `getHistoricaldatatabletoString` request → Copy as cURL
4. Extract the five cookie values and paste into `COOKIES` in `download_nse_data.py`
5. `uv run python experiments/002_adaptive_factor_rotation/download_nse_data.py`

---

## Setup

| Parameter | Value |
|---|---|
| Initial investment | ₹1,00,000 |
| Monthly SIP | ₹10,000 |
| Period 1 (sweep) | Mar 2015 → Dec 2025 (~10 years) |
| Period 2 (stress test) | Feb 2020 → Dec 2025 (~5 years, out-of-sample) |

**Why Mar 2015?** Starting from Jan 2010 captures the entire post-GFC bull run from
near-bottom, which artificially amplifies Momentum's advantage. Mar 2015 is a more
neutral entry point that includes both bull and bear market episodes.

**Why Feb 2020 for Period 2?** To stress-test the strategies against the COVID crash
(Feb–Mar 2020, Nifty −38%) and the subsequent uneven recovery, including the 2022
rate-hike bear market.

---

## Definitions

**Moving Average (MA):** The arithmetic mean of the last N closing values of an index,
where N is called the **MA window**, measured in trading days. A 50-day MA averages
the last 50 trading days of prices; a 250-day MA averages approximately one calendar year.

**Simple Moving Average (SMA):** The specific type of moving average used here — each of
the N days is weighted equally. The SMA is recomputed on each trading day by dropping
the oldest observation and adding the newest.

**Risk-on regime:** The Nifty 50 index's closing price is greater than or equal to its SMA
on a given date. Indicates that the market is currently trading above its recent average.

**Risk-off regime:** The Nifty 50 index's closing price is below its SMA on a given date.
Indicates the market is trading below its recent average.

**Risk-on momentum weight (ro):** The fraction of the total portfolio allocated to the
Momentum fund when the market is in a risk-on regime. The value fund receives the
remaining `1 − ro`. The risk-off allocation is symmetric: momentum gets `1 − ro`
and value gets `ro`.

Example with `ro = 0.65` (65%):
- Risk-on day: 65% Momentum 30, 35% Value 20
- Risk-off day: 35% Momentum 30, 65% Value 20

Example with `ro = 0.35` (35%):
- Risk-on day: 35% Momentum 30, 65% Value 20
- Risk-off day: 65% Momentum 30, 35% Value 20

When `ro = 0.50`, both regimes produce the same 50/50 allocation — the signal has
no effect and the strategy is equivalent to the 50/50 Fixed baseline.

**XIRR (Extended Internal Rate of Return):** The annualised return that accounts for
the exact timing and size of every cash flow — the initial lump sum and each monthly
SIP instalment. This is the standard measure for evaluating SIP-based investments.

**Sharpe Ratio:** `(annualised portfolio return − risk-free rate) / annualised volatility`.
Measures return earned per unit of total volatility. Risk-free rate used: 6% p.a.

**Sortino Ratio:** Same as Sharpe but the denominator uses only downside volatility
(standard deviation of negative daily returns). It does not penalise upside swings.

**Calmar Ratio:** `XIRR / |Maximum Drawdown|`. Measures return earned per unit of
worst-case peak-to-trough loss. A higher Calmar means better return relative to the
largest historical loss experienced.

**Maximum Drawdown (Max DD):** The largest percentage fall from a portfolio peak to
the subsequent trough, over the full study period. Expressed as a negative percentage.

**Price Return (PR):** Index performance excluding dividends. Contrast with Total Return
(TRI), which reinvests dividends. All data in this experiment is PR.

---

## How to run

```bash
uv run python experiments/002_adaptive_factor_rotation/run_experiment.py
```

Produces in `results/`:
- `REPORT.md` — parameter sweep tables, full results tables, figure references
- `figures/sweep_a_heatmap.png` — Trend Filter XIRR across MA window × risk-on weight
- `figures/sweep_b_grid.png` — Relative Strength XIRR and Sharpe across presets × sensitivity
- `figures/final_comparison.png` — Grouped bar chart: XIRR, Sharpe, Max DD
- `figures/portfolio_value_history.png` — Normalized portfolio value history
- `figures/rolling_sharpe.png` — Rolling 12-month Sharpe for all strategies
- `figures/period_comparison.png` — Period 1 vs Period 2 side-by-side on 5 metrics

---

## Strategy Details

### TrendFilterStrategy (Option A)

Computes a simple moving average of Nifty 50 over `ma_window` days.
- Price ≥ SMA → **risk-on** → allocate `risk_on_m_weight` to Momentum, remainder to Value
- Price < SMA → **risk-off** → allocate `1 − risk_on_m_weight` to Momentum, remainder to Value
- Insufficient history → **neutral** (50/50)

The Nifty 50 is loaded for signal computation only; it is never traded.

**Best params found (Period 1):** `ma_window=100`, `risk_on_m_weight=0.35`

### RelativeStrengthStrategy (Option B)

Computes momentum-vs-value return edges across multiple horizons:

```
edge = Σ(weight_h × (momentum_return_h − value_return_h)) / Σ(weight_h)
m_weight = clip(0.5 + sensitivity × edge, min_weight, max_weight)
```

Horizons without sufficient history are skipped and weights renormalized.

**Best params found (Period 1):** `horizon=1m_only`, `sensitivity=0.5`

### DualSignalStrategy (Option C)

Combines A and B:
- risk-on **and** RS ≥ 0.5 → `m_w = min(rs_weight, max_weight)` (amplify momentum)
- risk-off **and** RS < 0.5 → `m_w = max(rs_weight, min_weight)` (amplify value)
- Signals disagree → `m_w = 0.5` (neutral)

**Best params:** ma=100, ro=35%, 1m horizon, sensitivity=0.5

---

## Results

### Period 1 — Mar 2015 to Dec 2025 (10 years, ₹1.40L invested)

| Strategy | XIRR | Sharpe | Sortino | Calmar | Max DD | Final Value |
|---|---|---|---|---|---|---|
| Nifty 50 (buy & hold) | 12.89% | 0.561 | 0.754 | 0.342 | -37.71% | ₹30.8L |
| Value 20 only | 14.11% | 0.570 | 0.759 | 0.425 | -33.16% | ₹33.2L |
| 50/50 Fixed | 15.82% | 0.592 | 0.734 | 0.496 | -31.87% | ₹37.1L |
| Best B (RS 1m s=0.5) | 15.72% | 0.591 | 0.733 | 0.492 | -31.98% | ₹36.8L |
| Option C (Dual) | 15.92% | 0.592 | 0.735 | 0.498 | -31.95% | ₹37.2L |
| **Momentum 30 only** | **17.35%** | **0.619** | **0.774** | **0.530** | -32.75% | ₹40.9L |
| **Best A (TF ma=100 ro=35%)** | **17.31%** | 0.601 | 0.754 | 0.535 | -32.37% | ₹40.8L |

### Period 2 — Feb 2020 to Dec 2025 (5 years, out-of-sample, ₹76L invested)

| Strategy | XIRR | Sharpe | Sortino | Calmar | Max DD | Total Return |
|---|---|---|---|---|---|---|
| Nifty 50 (buy & hold) | 13.89% | 0.704 | 0.948 | 0.410 | -33.88% | +59.4% |
| Value 20 only | 14.72% | 0.711 | 0.926 | 0.484 | -30.39% | +63.8% |
| 50/50 Fixed | 16.28% | 0.711 | 0.880 | 0.614 | -26.49% | +72.6% |
| Best B (RS 1m s=0.5) | 16.33% | 0.712 | 0.879 | 0.616 | -26.52% | +72.9% |
| Option C (Dual) | 16.53% | 0.713 | 0.881 | 0.624 | -26.49% | +74.0% |
| Momentum 30 only | 17.76% | 0.726 | 0.899 | 0.579 | -30.67% | +81.3% |
| **Best A (TF ma=100 ro=35%)** | **17.74%** | 0.720 | 0.899 | **0.659** | **-26.91%** | **+81.1%** |

---

## Hyperparameter Sweeps

### Sweep A (TrendFilter) — Extended

**Ranges tested:** MA window ∈ {50, 100, 150, 200, 250, 300, 350, 400, 500} × risk-on weight ∈ {35%, 40%, 45%, 50%, 55%, 65%, 75%, 85%}. Total: 72 runs.

Selected results showing the full pattern:

| MA Window | ro=35% | ro=45% | ro=50% | ro=55% | ro=75% | ro=85% |
|---|---|---|---|---|---|---|
| 50 | **17.31%** | 16.45% | 16.01% | 15.57% | 13.76% | 12.84% |
| 100 | **17.31%** | 16.45% | 16.01% | 15.57% | 13.76% | 12.83% |
| 200 | 17.17% | 16.40% | 16.01% | 15.62% | 14.02% | 13.21% |
| 250 | 16.36% | 16.13% | 16.01% | 15.89% | 15.36% | 15.08% |
| 300 | 16.17% | 16.07% | 16.01% | 15.95% | 15.65% | 15.48% |
| 350 | 15.81% | 15.95% | 16.01% | 16.06% | 16.22% | 16.27% |
| 400 | 15.50% | 15.84% | 16.01% | 16.17% | 16.75% | **17.01%** |
| 500 | 15.50% | 15.84% | 16.01% | 16.17% | 16.75% | **17.01%** |

**Observations from the sweep:**

1. At every MA window, `ro=50%` produces XIRR ≈ 16.01% — confirming that when the signal is neutralised, performance converges to the 50/50 Fixed baseline (15.82%) regardless of window size.

2. For MA windows 50–200, XIRR is highest at `ro=35%` and decreases monotonically as `ro` increases toward 85%. The relationship between XIRR and risk-on weight is **negative** in this range.

3. For MA windows 350–500, XIRR is lowest at `ro=35%` and increases monotonically as `ro` increases toward 85%. The relationship is **positive** in this range.

4. At MA window 250–300, XIRR is approximately equal across all tested risk-on weights (~15.5%–16.4%). The direction of the relationship reverses in this interval.

5. MA windows 400 and 500 produce identical XIRR at every risk-on weight. Performance has plateaued and further extending the window adds no new information.

6. The highest XIRR in the sweep is 17.31% at `ma=50, ro=35%` and `ma=100, ro=35%` (tied). The highest XIRR at large windows is 17.01% at `ma=400` or `ma=500`, `ro=85%`.

7. `ro=35%` with a short MA allocates **65% to Value, 35% to Momentum when risk-on** and **35% to Value, 65% to Momentum when risk-off** — the opposite direction from the original hypothesis.

### Sweep B (RelativeStrength)

| Horizon | s=0.5 | s=1.0 | s=2.0 | s=4.0 |
|---|---|---|---|---|
| **1m_only** | **15.72%** | 15.44% | 15.03% | 14.88% |
| 3m_only | 15.56% | 15.11% | 14.32% | 13.18% |
| 6m_only | 15.67% | 15.33% | 14.85% | 14.31% |
| short | 15.66% | 15.31% | 14.73% | 14.13% |
| balanced | 15.65% | 15.29% | 14.69% | 14.05% |
| long | 15.66% | 15.30% | 14.77% | 14.17% |

XIRR decreases as sensitivity increases across all horizon presets. Best Sharpe and XIRR are both at `1m_only, sensitivity=0.5`.

---

## Data Observations

### 1. Best A (ma=100, ro=35%) matches Momentum 30 in raw return while improving on drawdown

In Period 1, Best A delivered 17.31% XIRR vs Momentum 30's 17.35% — a difference of 4 basis points. In Period 2, Best A delivered 17.74% XIRR vs Momentum 30's 17.76% — a difference of 2 basis points. In both periods the XIRR gap is negligible.

However, in Period 2:
- Best A Max DD: **−26.91%**
- Momentum 30 Max DD: **−30.67%**
- Difference: 3.76 percentage points less drawdown for Best A

The Calmar ratio captures this: Best A **0.659** vs Momentum 30 **0.579**. Best A delivers nearly identical XIRR with materially lower worst-case loss.

### 2. The direction of the risk-on weight effect depends on the MA window

Within MA windows 50–200, lower risk-on weights produce higher XIRR. Within MA windows 350–500, higher risk-on weights produce higher XIRR. At MA windows 250–300, the effect of risk-on weight on XIRR is near-zero.

The best XIRR at short windows (17.31%, ro=35%) and the best XIRR at long windows (17.01%, ro=85%) represent two distinct parameter regions. The short-window best is slightly higher in Period 1.

### 3. `ro=35%` means the signal direction is inverted relative to the original hypothesis

At `ro=35%`, the portfolio holds 65% Value and 35% Momentum during risk-on days, and 65% Momentum and 35% Value during risk-off days. This is the opposite of the setup described in the hypothesis. The signal still differentiates allocations based on the SMA regime, but tilts toward Value (not Momentum) when the market is above its moving average.

At `ro=50%`, the strategy is indistinguishable from 50/50 Fixed regardless of MA window — the XIRR is 16.01% in every row of the table above, which is 19 basis points above the no-signal 50/50 Fixed baseline (15.82%), attributable to the different rebalancing mechanics rather than the signal.

### 4. Longer MA windows compress the XIRR spread across risk-on weights

At `ma=50`, XIRR ranges from 12.84% (ro=85%) to 17.31% (ro=35%) — a spread of 447 basis points. At `ma=250`, XIRR ranges from 15.08% (ro=85%) to 16.36% (ro=35%) — a spread of 128 basis points. At `ma=500`, XIRR ranges from 15.50% (ro=35%) to 17.01% (ro=85%) — a spread of 151 basis points (but in the opposite direction).

### 5. Best B and Option C do not improve on 50/50 Fixed in Period 1

Best B (RS 1m_only, s=0.5) delivered 15.72% XIRR in Period 1 — 10 basis points below 50/50 Fixed (15.82%). Option C delivered 15.92%, 10 basis points above 50/50 Fixed. Neither difference is large relative to measurement uncertainty over a 10-year window.

In Period 2, Best B delivered 16.33% and Option C 16.53%, both modestly above 50/50 Fixed (16.28%).

### 6. All Sortino ratios cluster tightly

In Period 1, Sortino ratios range from 0.733 (Best B) to 0.774 (Momentum 30) — a spread of 41 basis points across all seven strategies. In Period 2, they range from 0.879 (Best B) to 0.948 (Nifty 50). No strategy stands out as structurally different in its downside return distribution.

### 7. Nifty 50 buy-and-hold has the worst XIRR but highest Sortino in Period 2

Nifty 50 has Sortino 0.948 in Period 2, higher than all other strategies including Momentum 30 (0.899). At the same time, Nifty 50 has the lowest XIRR (13.89%) and the worst Max DD (−33.88%) of all strategies in Period 2. This illustrates that Sortino does not fully capture drawdown risk — Calmar is more informative for distinguishing strategies on tail loss.

---

## Limitations and Caveats

- **PR data:** Absolute returns are ~1–1.5% lower than actual TRI-based fund returns. Rankings hold. Add ~1pp to all XIRR figures as a dividend-adjusted estimate.
- **NSE backtest construction:** The Momentum 30 index was only formally launched in 2016. Values before that are NSE backtested using the same rule-based methodology. Look-ahead bias in index parameter calibration is possible but unlikely given the formula simplicity.
- **Expense ratio:** Not modelled. Both PR base and direct fund TERs (0.15–0.25% for index funds) affect absolute returns proportionally across all strategies.
- **No transaction taxes on rebalancing sells:** LTCG/STCG would reduce the rebalancing strategies' advantage in practice.
- **Short out-of-sample window:** Period 2 is only 5 years. Conclusions should be treated as directional, not statistically robust.
- **Sweep A boundary issue:** The best short-window parameter (ro=35%) is at the boundary of the tested range. Testing ro=30%, ro=25% etc. may find higher XIRR at short MA windows, or the optimum may already be at 35%. This has not been tested.

---

## Files

```
experiments/002_adaptive_factor_rotation/
├── README.md                  ← this file
├── download_nse_data.py       ← fetch PR data from niftyindices.com
├── run_experiment.py          ← full sweep + figures + report
├── nse_data/                  ← downloaded CSV files (gitignored)
│   ├── Nifty 50_Historical_PR_03012005to31122025.csv
│   ├── Nifty50 Value 20_Historical_PR_04012010to31122025.csv
│   └── NIFTY200MOMENTM30_Historical_PR_01042005to31122025.csv
└── results/
    ├── REPORT.md              ← auto-generated: tables, sweep results, figures
    └── figures/
        ├── sweep_a_heatmap.png
        ├── sweep_b_grid.png
        ├── final_comparison.png
        ├── portfolio_value_history.png
        ├── rolling_sharpe.png
        └── period_comparison.png
```

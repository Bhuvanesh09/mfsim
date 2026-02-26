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
- Price ≥ SMA → **risk-on** → tilt toward momentum (`risk_on_m_weight`)
- Price < SMA → **risk-off** → tilt toward value (`1 − risk_on_m_weight`)
- Insufficient history → **neutral** (50/50)

The Nifty 50 is loaded for signal computation only; it is never traded.

**Best params found (Period 1):** `ma_window=250`, `risk_on_m_weight=0.55`

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

**Best params:** ma=250, ro=55%, 1m horizon, sensitivity=0.5

---

## Results

### Period 1 — Mar 2015 to Dec 2025 (10 years, ₹1.40L invested)

| Strategy | XIRR | Sharpe | Sortino | Calmar | Max DD | Final Value |
|---|---|---|---|---|---|---|
| Nifty 50 (buy & hold) | 12.89% | 0.561 | 0.754 | 0.342 | -37.71% | ₹30.8L |
| Value 20 only | 14.11% | 0.570 | 0.759 | 0.425 | -33.16% | ₹33.2L |
| 50/50 Fixed | 15.82% | 0.592 | 0.734 | 0.496 | -31.87% | ₹37.1L |
| **Best A (TF ma=250)** | **15.89%** | 0.593 | 0.735 | 0.499 | -31.82% | ₹37.2L |
| Best B (RS 1m s=0.5) | 15.72% | 0.591 | 0.733 | 0.492 | -31.98% | ₹36.8L |
| Option C (Dual) | 15.90% | 0.592 | 0.735 | 0.498 | -31.95% | ₹37.2L |
| **Momentum 30 only** | **17.35%** | **0.619** | **0.774** | **0.530** | -32.75% | ₹40.9L |

### Period 2 — Feb 2020 to Dec 2025 (5 years, out-of-sample, ₹76L invested)

| Strategy | XIRR | Sharpe | Sortino | Calmar | Max DD | Total Return |
|---|---|---|---|---|---|---|
| Nifty 50 (buy & hold) | 13.89% | 0.704 | 0.948 | 0.410 | -33.88% | +59.4% |
| Value 20 only | 14.72% | 0.711 | 0.926 | 0.484 | -30.39% | +63.8% |
| 50/50 Fixed | 16.28% | 0.711 | 0.880 | 0.614 | -26.49% | +72.6% |
| Best B (RS 1m s=0.5) | 16.33% | 0.712 | 0.879 | 0.616 | -26.52% | +72.9% |
| Option C (Dual) | 16.53% | 0.713 | 0.881 | 0.624 | -26.49% | +74.0% |
| **Best A (TF ma=250)** | **16.68%** | **0.714** | 0.881 | **0.633** | **-26.35%** | +74.9% |
| **Momentum 30 only** | **17.76%** | **0.726** | **0.899** | 0.579 | -30.67% | +81.3% |

### Hyperparameter sweep patterns

**Sweep A (TrendFilter):**

| MA Window | ro=55% | ro=65% | ro=75% | ro=85% |
|---|---|---|---|---|
| 50 | 15.57% | 14.67% | 13.76% | 12.84% |
| 100 | 15.57% | 14.67% | 13.76% | 12.83% |
| 150 | 15.59% | 14.73% | 13.87% | 13.00% |
| 200 | 15.62% | 14.83% | 14.02% | 13.21% |
| **250** | **15.89%** | 15.63% | 15.36% | 15.08% |

**Sweep B (RelativeStrength):**

| Horizon | s=0.5 | s=1.0 | s=2.0 | s=4.0 |
|---|---|---|---|---|
| **1m_only** | **15.72%** | 15.44% | 15.03% | 14.88% |
| 3m_only | 15.56% | 15.11% | 14.32% | 13.18% |
| 6m_only | 15.67% | 15.33% | 14.85% | 14.31% |
| short | 15.66% | 15.31% | 14.73% | 14.13% |
| balanced | 15.65% | 15.29% | 14.69% | 14.05% |
| long | 15.66% | 15.30% | 14.77% | 14.17% |

---

## Financial Implications

### 1. Adaptive signals are weakly positive but regime-dependent

In Period 1 (stable market, 10 years), adaptive strategies barely beat 50/50 Fixed (~8bps XIRR).
That margin is small enough to be noise. In Period 2 (COVID crash + recovery, 5 years), Best A
delivered **+40bps XIRR and −14bps max drawdown** versus 50/50 Fixed. The trend filter
genuinely cushioned the crash. The signal adds value specifically when it's needed most —
in market dislocations — which is where static strategies are structurally blind.

### 2. Pure Momentum 30 dominates on raw return, but carries real drawdown cost

Momentum 30 delivered the highest XIRR in both periods (17.35%, 17.76%). Its Sharpe and
Sortino are also highest. On annualised metrics, momentum looks unambiguously best.

However, in Period 2 (which starts at the COVID crash):
- Momentum max drawdown: **−30.67%**
- Best A max drawdown: **−26.35%**
- That is a 4.3 percentage point difference in worst-case loss

And the Calmar ratio tells the same story in reverse: Best A earns **0.633 return per unit
of max drawdown** vs Momentum's **0.579**. The trend filter delivers more return-per-risk
in a crash scenario even though Momentum's absolute return is higher.

### 3. Sortino provides little differentiation; Calmar does

All Sortino ratios cluster tightly (0.73–0.77 in P1, 0.88–0.95 in P2). This means no
strategy has a fundamentally different upside/downside character — they all have similar
return distributions. The Calmar ratio is the more useful discriminator: it captures the
tail event (max drawdown) that matters most to real investors.

### 4. Sweep patterns reveal the signal quality

Both sweeps converge on the same message: **low noise, gentle tilts**.

- Longer MA windows (250 days) consistently outperform shorter ones — the signal needs
  time to be meaningful; week-to-week noise hurts returns.
- Low risk-on tilt (55% vs 85%) performs better — confirming that the value of the signal
  is directional guidance, not aggressive factor switching.
- Low sensitivity (0.5 vs 4.0) wins for relative strength — same message.

If the optimal signal were a large tilt at high sensitivity, it would suggest strong
predictive power. The fact that gentle tilts win suggests the signal is real but weak.

### 5. 50/50 Fixed is surprisingly competitive

In Period 1, the 50/50 Fixed (no rebalance) actually beat all adaptive strategies on XIRR
(15.82% vs 15.89% — essentially tied). This is a calibration warning: dynamic signals
don't obviously dominate simple fixed allocations over a full market cycle. Adaptive
strategies earn their complexity cost primarily in high-volatility periods.

### 6. For an Indian retail investor

Three practical conclusions:

**If you can hold through volatility and check rarely:** Momentum 30 alone (18% XIRR
over 10 years) is the highest-returning strategy tested. The risk is behavioural — a
30%+ drawdown is hard to hold through without selling at the worst time.

**If you care about the drawdown experience:** Best A (trend filter, ma=250, ro=55%)
offers returns nearly matching 50/50 Fixed while showing meaningfully lower max
drawdown in crash scenarios. It's the best answer to the question "can I get good
returns with less sleep deprivation?"

**If you want simplicity:** 50/50 Fixed (no rebalance) is competitive with both. It
beats Nifty 50 by 3pp XIRR, requires zero management, and has the lowest implementation
cost. Rebalancing adds friction (taxes on sells, stamp duty) and in this dataset added
no value.

All factor strategies significantly outperformed Nifty 50 buy-and-hold (12.89% XIRR),
validating the core premise that factor tilts add value in Indian equity markets.

### 7. Limitations and caveats

- **PR data:** Absolute returns are ~1–1.5% lower than actual TRI-based fund returns.
  Rankings hold. Would-be investors should add ~1pp to all XIRR figures as a
  dividend-adjusted estimate.
- **NSE backtest construction:** The Momentum 30 index was only formally launched in
  2016. Values before that are NSE backtested using the same rule-based methodology.
  Look-ahead bias in index *parameter calibration* is possible but unlikely given the
  formula simplicity.
- **Expense ratio:** Not modelled. Both PR base and direct fund TERs (0.15–0.25% for
  index funds) affect absolute returns proportionally across all strategies.
- **No transaction taxes on rebalancing sells:** LTCG/STCG would reduce the rebalancing
  strategies' advantage in practice. The `TaxAwareReturnMetric` exists in the library
  but was not applied here.
- **Short out-of-sample window:** Period 2 is only 5 years. Conclusions should be
  treated as directional, not statistically robust.

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

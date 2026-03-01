# Experiment 001: Momentum vs Value Factor Rotation

## Setup

| Parameter          | Value                              |
|:-------------------|:-----------------------------------|
| Period             | 2021-04-01 → 2025-12-31            |
| Initial investment | ₹1,00,000                          |
| Monthly SIP        | ₹10,000                            |
| Total invested     | ₹6,69,966                          |

### Funds used

| Role      | Fund                                                            | Inception  |
|:----------|:----------------------------------------------------------------|:-----------|
| Baseline  | UTI Nifty 50 Index Fund – Direct Growth                        | Jan 2013   |
| Value     | Nippon India Nifty 50 Value 20 Index Fund – Direct Growth       | Feb 2021   |
| Momentum  | UTI Nifty 200 Momentum 30 Index Fund – Direct Growth            | Mar 2021   |

### Strategies compared

1. **Nifty 50 (buy & hold)** — baseline, 100% Nifty 50 Index Fund
2. **Value 20 (buy & hold)** — 100% Nifty 50 Value 20 Index Fund
3. **Momentum 30 (buy & hold)** — 100% Nifty 200 Momentum 30 Index Fund
4. **50/50 fixed** — equal split, SIP invested 50/50 each month, no rebalancing
5. **50/50 annual rebalance** — equal split, rebalanced back to 50/50 each January
6. **Dynamic rotation** — starts 50/50; every 6 months shifts 10% toward the outperformer

## Results

| Strategy                                  | Final Value | Total Return | XIRR   | Max Drawdown | Sharpe |
|:------------------------------------------|------------:|:-------------|:-------|:-------------|-------:|
| Nifty 50 (buy & hold)                     | ₹9,60,388   | 43.35%       | 13.20% | -9.56%       |  1.778 |
| Value 20 (buy & hold)                     | ₹9,57,926   | 42.98%       | 13.10% | -12.58%      |  1.755 |
| Momentum 30 (buy & hold)                  | ₹9,86,039   | **47.18%**   | **14.18%** | **-25.82%** | 1.496 |
| 50/50 Value+Momentum (no rebalance)       | ₹9,71,982   | 45.08%       | 13.64% | -19.69%      |  1.666 |
| 50/50 Value+Momentum (annual rebalance)   | ₹9,73,258   | 45.27%       | 13.69% | -19.42%      |  1.672 |
| Dynamic rotation (semi-annual, 10% shift) | ₹9,74,567   | 45.47%       | 13.74% | -21.05%      |  1.635 |

*Full results (including Sortino) in [results/summary.md](results/summary.md)*

## Key findings

### 1. Momentum wins on raw return — but at much higher risk

Momentum 30 delivered the highest XIRR (14.18%) and total return (47.18%), but came with a
worst-case drawdown of **-25.82%** — almost 3× deeper than the Nifty 50 (-9.56%).
This is consistent with academic literature: the momentum factor captures excess return but
also concentrates in high-velocity sectors, making it more vulnerable to sharp reversals.

### 2. Value barely justified its own existence over this period

Nifty 50 Value 20 underperformed both Nifty 50 and Momentum on total return, while having a
deeper drawdown (-12.58%) than the plain Nifty 50. This aligns with the underperformance of
the "value" factor in Indian markets during 2021–2025, where growth/momentum dominated.

### 3. Combining the two factors reduces drawdown meaningfully

The 50/50 blends brought max drawdown down to ~-19 to -21%, while still delivering 45–45.5%
total return. The blend acts as a natural hedge: when momentum corrects sharply, value tends
to hold up better.

### 4. Annual rebalancing added marginal value over fixed allocation

The 50/50 annual rebalance (₹9,73,258) slightly beat the no-rebalance 50/50 (₹9,71,982).
Rebalancing forces selling high-momentum positions that have run up, systematically capturing
mean reversion — the classic "rebalancing bonus".

### 5. Dynamic rotation: modest improvement over static blends

The 10%-per-period momentum rotation produced 45.47% total return — barely above the static
blends. The strategy's 10% shift size is conservative; larger shifts (25–50%) would increase
exposure to the winner but also increase chasing-risk. The period is also short (5 years) —
factor rotation strategies tend to need longer time horizons to demonstrate consistent alpha.

## How to reproduce

```bash
uv run python experiments/001_momentum_value_rotation/run.py
```

Or run individual variants via Hydra:

```bash
uv run mfsim-backtest +experiment=mv_nifty50_baseline
uv run mfsim-backtest +experiment=mv_momentum_only
uv run mfsim-backtest +experiment=mv_dynamic_rotation
```

## Why XIRRs converge under SIP — and why the window matters

### The SIP averaging effect

With a lump sum (no SIP), the same 5-year window shows a much larger spread:

| Strategy | Total Return (lump sum) | XIRR |
|---|---|---|
| Nifty 50 | +84.0% | 13.7% |
| Value 20 | +90.4% | 14.5% |
| Momentum 30 | **+109.1%** | **16.8%** |

Monthly SIP flattens this because it automatically buys more units during
down months (2022, 2025) and fewer during up months. The variance between
strategies collapses — hence ~13% XIRR for all three under SIP.

**Implication**: SIP rewards consistency, not factor selection. To see factor
premiums clearly in a backtest, use lump-sum or compare on Sharpe ratio and
maximum drawdown, not raw XIRR.

### The 5-year window was unusually benign

| Period | Max Drawdown | Sharpe |
|---|---|---|
| 5 years (2021–2025) | -9.6% | 1.78 |
| 7 years (2019–2025, includes COVID) | -35.0% | 1.34 |
| 10 years (2016–2025) | -36.8% | 1.17 |
| 13 years (2013–2025) | -37.5% | 1.00 |

The 5-year window had no major bear market. The COVID crash (March 2020)
falls just outside it. Over 13 years, the Nifty 50 max drawdown was **-37.5%**.
Momentum 30 in a real bear market (e.g. 2008, 2020) would likely see -50%+
drawdowns due to concentrated sector bets.

### Year-by-year: the strategies ARE different

| Year | Nifty 50 | Value 20 | Momentum 30 |
|------|----------|----------|-------------|
| 2021 | +16.4%   | +25.5%   | +40.8%      |
| 2022 | +3.8%    | +0.2%    | -6.6%       |
| 2023 | +20.4%   | +28.4%   | +40.9%      |
| 2024 | +9.7%    | +16.8%   | +20.9%      |
| 2025 | +11.2%   | +0.5%    | **-5.3%**   |

Momentum is cyclical: +40.8% in 2021, -6.6% in 2022, +40.9% in 2023,
-5.3% in 2025. SIP smooths these out but exposes you to deep intra-year
drawdowns.

### What 10+ years would show

The Nifty 50 Value 20 and Momentum 30 indices only launched in 2021 as live
funds. To backtest 10+ years, we need NSE Total Return Index (TRI) CSV data.

**To run the 10+ year experiment:**
1. Download TRI CSVs from nseindia.com (see `run_extended.py` for instructions)
2. Place in `experiments/001_momentum_value_rotation/nse_data/`
3. Run `uv run python experiments/001_momentum_value_rotation/run_extended.py`

The extended script auto-detects the NSE files and uses the full available
date range. If files are missing, it falls back to the 5-year mfapi run.

## Next steps / open questions

- **Longer back-test**: The value fund only started in Feb 2021. Using NSE index total-return
  data (going back to 2005+) would reveal how these factors behave across multiple bull/bear cycles.
- **Transaction costs**: The dynamic rotation involves selling partial positions. Adding
  realistic exit loads and STT would reduce its edge over passive blends.
- **Larger shift sizes**: Test 25% and 50% rotation steps to find the sensitivity.
- **Tax drag**: Tax-aware return (accounting for STCG/LTCG) would widen the gap between
  active rotation and passive buy-and-hold.

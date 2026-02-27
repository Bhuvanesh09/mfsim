# Experiment 004: Trigger-Based Rebalancing with Cooldown

## Hypothesis

Adaptive strategies (TrendFilter, RelativeStrength, DualSignal) compute
dynamic market signals but only act on them at monthly rebalance dates.  A
mid-month crash (e.g., COVID late Feb 2020) can go unaddressed for up to ~22
trading days.

**Question:** Does daily signal checking with a cooldown-gated trigger
mechanism reduce drawdowns or improve risk-adjusted returns compared to
monthly-only rebalancing?

## Design

### Strategies tested

All strategies use the best parameters from Experiment 002/003:

| Strategy | Key Parameters |
|---|---|
| TrendFilter | ma=100, risk_on=35%, risk_off=65% |
| RelativeStrength | 1m_only horizon, sensitivity=0.5 |
| DualSignal | Combines TF + RS params above |

### Comparisons

1. **Trigger vs Monthly**: Each adaptive strategy with `trigger_enabled=False`
   (monthly only) vs `trigger_enabled=True` (daily signal check, cooldown=21).

2. **Cooldown sweep** (TrendFilter): Cooldowns of [5, 10, 15, 21, 30, 42, 63]
   days to measure the tradeoff between responsiveness and churn.

3. **Signal threshold sweep** (RelativeStrength): Thresholds of [0.02, 0.05,
   0.10, 0.15] to test sensitivity of continuous signals.

4. **Baselines**: Nifty 50, Value 20 only, Momentum 30 only, 50/50 Fixed.

### Metrics tracked per strategy

- XIRR, Sharpe, Sortino, Calmar, Maximum Drawdown
- Scheduled rebalance count, triggered rebalance count, total rebalance count
- Trigger timing (dates of triggered rebalances)

### Data

NSE Price Return index data from `experiments/002_adaptive_factor_rotation/nse_data/`.

## Running

```bash
uv run python experiments/004_trigger_rebalancing/run_experiment.py
```

## Output

- `results/REPORT.md` -- Full results table
- `results/figures/trigger_vs_monthly_comparison.png` -- Side-by-side bars
- `results/figures/cooldown_sweep.png` -- XIRR/Sharpe/triggers vs cooldown
- `results/figures/threshold_sweep.png` -- XIRR/Sharpe/triggers vs threshold
- `results/figures/rebalance_count_comparison.png` -- Scheduled vs triggered breakdown
- `results/figures/trigger_timing_scatter.png` -- When triggers fired
- `results/figures/drawdown_during_covid.png` -- Drawdown curves Jan-Jun 2020

## Implementation

The trigger mechanism is implemented as a `_TriggerMixin` class in
`mfsim/strategies/adaptive_strategies.py`. Key design decisions:

1. **Opt-in**: `trigger_enabled=False` by default. All existing code is
   unaffected.

2. **Cooldown**: After a triggered rebalance, the strategy ignores signal
   changes for `cooldown_days` calendar days. This prevents whipsawing from
   signal flickering.

3. **Signal threshold** (RS/Dual): Continuous signals require the momentum
   weight to change by at least `signal_threshold` (default 0.05) to count
   as a material change.

4. **Simulator integration**: The `Simulator.run()` loop calls
   `strategy.should_rebalance()` on every non-scheduled trading day.
   `rebalance_log` tracks each event as "scheduled" or "triggered".

5. **State coherence**: `rebalance()` calls `_update_signal_state()` to
   keep `_last_signal` current after scheduled rebalances, preventing
   false triggers on the next trading day.

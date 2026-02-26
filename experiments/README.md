# Experiments

Structured backtesting experiments using the mfsim framework.

Each experiment lives in its own numbered directory and contains:
- `README.md` — hypothesis, setup, results, and conclusions
- `run.py` — standalone Python script to reproduce results (no Hydra needed)
- `results/summary.json` — machine-readable results
- `results/summary.md` — human-readable results table

## Index

| # | Name | Period | Status |
|---|------|--------|--------|
| [001](001_momentum_value_rotation/) | Momentum vs Value Factor Rotation | 2021–2025 | Complete |
| [002](002_adaptive_factor_rotation/) | Adaptive Factor Rotation (Trend Filter + Relative Strength) | 2015–2025 | Complete |

## Running experiments

```bash
# Run a specific experiment
uv run python experiments/001_momentum_value_rotation/run.py
uv run python experiments/002_adaptive_factor_rotation/run_experiment.py

# Or use Hydra for the same experiment
uv run mfsim-backtest +experiment=mv_nifty50_baseline
uv run mfsim-backtest +experiment=mv_value_only
uv run mfsim-backtest +experiment=mv_momentum_only
uv run mfsim-backtest +experiment=mv_50_50_fixed
uv run mfsim-backtest +experiment=mv_50_50_annual_rebal
uv run mfsim-backtest +experiment=mv_dynamic_rotation

# Sweep all variants at once
uv run mfsim-backtest --multirun +experiment=mv_nifty50_baseline,mv_value_only,mv_momentum_only,mv_50_50_fixed,mv_50_50_annual_rebal,mv_dynamic_rotation
```

## Fund discovery

Search available funds before designing experiments:

```bash
# Find all Nifty 50 momentum index funds (direct, growth only)
uv run mfsim-search "nifty 200 momentum" --direct --growth --code

# Find value factor index funds
uv run mfsim-search "nifty 50 value" --direct --growth

# Find any Mirae Asset fund
uv run mfsim-search "mirae" --direct --growth --top 10
```

# CLAUDE.md

## Project overview

mfsim is a mutual fund backtesting framework for Indian mutual funds. It simulates investment strategies against historical NAV data with SIP support, portfolio rebalancing, and performance metrics (XIRR, Sharpe, Sortino, Max Drawdown, Total Return).

## UV — the only way to run things

This project uses **uv** as its package manager and task runner. Never use bare `python`, `pip`, or `pytest` commands. Always go through uv.

```bash
# Install / sync all dependencies (reads pyproject.toml + uv.lock):
uv sync

# Run the backtest CLI:
uv run mfsim-backtest
uv run mfsim-backtest +experiment=momentum_value_short

# Run tests:
uv run pytest

# Run the linter:
uv run ruff check .

# Run any Python script:
uv run python some_script.py

# Add a new dependency:
uv add <package>

# Add a dev dependency:
uv add --dev <package>
```

### Why uv only

- `uv.lock` is committed to the repo for reproducible builds. Never gitignore it.
- `uv run` automatically creates/activates the venv and installs deps if needed — no manual `pip install` or `source .venv/bin/activate`.
- `uv sync` is the equivalent of `pip install -e ".[dev]"` but faster and deterministic.

## Hydra configs

Backtest experiments are defined as YAML configs under `mfsim/configs/`:

```
mfsim/configs/
├── config.yaml                    # base defaults
├── strategy/                      # pluggable strategy definitions
├── data_loader/                   # data source configs (mfapi, index_csv)
└── experiment/                    # preset experiments (past runs)
```

Run an experiment:
```bash
uv run mfsim-backtest +experiment=fixed_alloc_no_rebal
```

Override params from CLI:
```bash
uv run mfsim-backtest simulation.sip_amount=50000 strategy=nifty50_baseline
```

Sweep multiple strategies:
```bash
uv run mfsim-backtest --multirun strategy=fixed_allocation,semi_annual_rebalance,nifty50_baseline
```

## Project structure

- `mfsim/` — core library (backtester, strategies, metrics, data loaders, CLI, configs)
- `tests/` — pytest test suite
- `logs/` — simulation log output (gitignored)
- `outputs/` — Hydra run output (gitignored)

## Key conventions

- All dependencies are declared in `pyproject.toml` under `[project.dependencies]` (runtime) or `[tool.uv] dev-dependencies` (dev-only).
- Ruff is the linter/formatter. Config is in `pyproject.toml` under `[tool.ruff]`.
- NAV data from AMFI (the default data source) is already net of expense ratio — the simulator does not apply any additional TER deduction.

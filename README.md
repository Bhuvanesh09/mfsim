# mfsim

A programmable mutual fund simulation and backtesting framework built for Indian mutual funds. Designed to let you test investment strategies against historical NAV data, model SIPs, and compute risk-adjusted performance metrics — all from Python.

## Why mfsim

Most investors in Indian mutual funds either blindly follow SIPs into a single index fund or rely on gut-feel rebalancing between funds. There's no accessible, open-source tool that lets you rigorously backtest active-passive strategies against real historical data.

mfsim fills that gap. It's a Python library where you define your investment strategy as code, run it against years of real NAV data, and get back hard numbers: XIRR, Sharpe ratio, max drawdown, and more.

The longer-term vision is **LLM-driven portfolio management**. mfsim is being built so that an AI agent — connected via MCP (Model Context Protocol) — can analyze news, macro indicators, and fund performance, then autonomously decide how to rebalance your portfolio. The strategy interface is deliberately simple enough for an LLM to implement: receive portfolio state and market data, return buy/sell orders.

## Installation

```bash
# Using uv (recommended)
uv add mfsim

# Or from source
git clone https://github.com/Bhuvanesh09/mfsim.git
cd mfsim
uv sync
```

## Quick Start

### CLI (no Python needed)

Run pre-built experiments directly from the command line:

```bash
# Run the default backtest:
uv run mfsim-backtest

# Run a specific past experiment:
uv run mfsim-backtest +experiment=fixed_alloc_no_rebal

# Override params on the fly:
uv run mfsim-backtest simulation.sip_amount=50000 simulation.start_date=2015-01-01

# Switch strategy:
uv run mfsim-backtest strategy=nifty50_baseline

# Compare multiple strategies in one shot:
uv run mfsim-backtest --multirun strategy=fixed_allocation,semi_annual_rebalance,nifty50_baseline
```

### Python API

```python
from mfsim.backtester import Simulator
from mfsim.strategies import MomentumValueStrategy

strategy = MomentumValueStrategy(
    frequency="semi-annually",
    metrics=["Total Return", "XIRR", "Sharpe Ratio"],
    value_fund="NIPPON INDIA NIFTY 50 VALUE 20 INDEX FUND - DIRECT Plan - IDCW Option",
    momentum_fund="BANDHAN NIFTY200 MOMENTUM 30 INDEX FUND - GROWTH - DIRECT PLAN",
    momentum_period=180,
)

sim = Simulator(
    start_date="2020-01-01",
    end_date="2025-01-01",
    initial_investment=100000,
    strategy=strategy,
    sip_amount=10000,
    sip_frequency="monthly",
)

results = sim.run()
print(results)
```

## Writing Custom Strategies

Subclass `BaseStrategy` and implement `rebalance()`. That's the only requirement.

```python
from mfsim.strategies.base_strategy import BaseStrategy

class MyStrategy(BaseStrategy):
    def __init__(self, fund_list, allocation):
        super().__init__(
            frequency="quarterly",
            metrics=["Total Return", "XIRR"],
            fund_list=fund_list,
        )
        self.allocation = allocation

    def allocate_money(self, money_invested, nav_data, current_date):
        return {fund: money_invested * pct for fund, pct in self.allocation.items()}

    def rebalance(self, portfolio, nav_data, current_date):
        # Your rebalancing logic here
        # Return list of orders: [{"fund_name": "...", "amount": 1000}, ...]
        # Positive amount = buy, negative = sell
        return []
```

## Using Custom Data Sources

You're not locked into the default API. Subclass `BaseDataLoader` to use your own data.

```python
from mfsim.utils import BaseDataLoader
import pandas as pd

class CsvDataLoader(BaseDataLoader):
    def __init__(self, csv_dir):
        super().__init__(data_dir=csv_dir)
        self.csv_dir = csv_dir

    def load_nav_data(self, fund_name):
        df = pd.read_csv(f"{self.csv_dir}/{fund_name}.csv")
        df["date"] = pd.to_datetime(df["date"])
        df["nav"] = df["nav"].astype(float)
        return df.sort_values("date").reset_index(drop=True)

sim = Simulator(..., data_loader=CsvDataLoader("/path/to/csvs"))
```

## Available Metrics

| Metric | What it measures |
|--------|-----------------|
| **Total Return** | Simple `(final / invested) - 1` |
| **XIRR** | IRR accounting for irregular cash flows (SIPs, rebalancing) |
| **Sharpe Ratio** | Risk-adjusted return vs risk-free rate |
| **Sortino Ratio** | Like Sharpe, but only penalizes downside volatility |
| **Max Drawdown** | Worst peak-to-trough decline |

## Hydra Configs

Experiments are defined as composable YAML configs under `mfsim/configs/`. You can mix and match strategies, data sources, and simulation params without touching Python.

```
mfsim/configs/
├── config.yaml              # base defaults
├── strategy/                # pluggable strategy definitions
│   ├── fixed_allocation.yaml
│   ├── semi_annual_rebalance.yaml
│   ├── annual_rebalance.yaml
│   ├── momentum_value.yaml
│   └── nifty50_baseline.yaml
├── data_loader/             # data source configs
│   ├── mfapi.yaml           # live AMFI API
│   └── index_csv.yaml       # local NSE index CSVs
└── experiment/              # preset experiments (past runs)
    ├── fixed_alloc_no_rebal.yaml
    ├── semi_annual_rebal.yaml
    ├── annual_rebal.yaml
    ├── nifty50_baseline.yaml
    └── momentum_value_short.yaml
```

**Available experiments** reproduce the comparison from the project notebook:

| Experiment | Strategy | Period | Result |
|---|---|---|---|
| `fixed_alloc_no_rebal` | Fixed 4-fund factor tilt | 2010–2025 | 255% TR, 17.1% XIRR |
| `semi_annual_rebal` | Same funds, rebalance 2x/yr | 2010–2025 | 252% TR, 17.0% XIRR |
| `annual_rebal` | Same funds, rebalance 1x/yr | 2010–2025 | 251% TR, 17.0% XIRR |
| `nifty50_baseline` | NIFTY 50 buy-and-hold | 2010–2025 | 146% TR, 12.5% XIRR |
| `momentum_value_short` | Momentum vs Value rotation | 2023–2024 | 28.6% TR |

To add your own experiment, create a YAML file in `mfsim/configs/experiment/` that overrides the defaults.

## Architecture

```
mfsim/
├── backtester/       # Simulation engine — runs the day-by-day loop
├── strategies/       # Strategy interface + implementations
├── metrics/          # Performance and risk metric calculations
├── utils/            # Data loaders (API, custom) and logging
├── configs/          # Hydra YAML configs for experiments
├── cli.py            # Hydra entry point (exposed as mfsim-backtest)
└── data/             # Indian mutual fund scheme database
```

The design is intentionally modular: strategies, data sources, and metrics are all pluggable. The simulator orchestrates them but doesn't depend on any specific implementation.

## The Vision

mfsim is being built toward a future where your investment strategy isn't a static set of rules — it's an AI agent that:

1. **Reads the market** — news, macro indicators, sector rotations, fund performance
2. **Backtests ideas** — "what if I shifted 20% from large-cap to mid-cap momentum?"
3. **Decides and acts** — rebalances your portfolio based on evidence, not emotion
4. **Learns** — tracks which decisions worked and refines its approach

The library will be exposed as an MCP server, letting any LLM use it as a tool. A strategy's `rebalance()` method will be able to call an LLM internally, passing it portfolio state and market context and receiving back allocation decisions.

This is active-passive investing: broad index exposure for baseline gains, with intelligent rebalancing for alpha — automated, evidence-based, and transparent.

## Data Source

By default, mfsim fetches live NAV data from [mfapi.in](https://www.mfapi.in/), which provides historical NAV data for all AMFI-registered Indian mutual funds. No API key required.

## License

MIT

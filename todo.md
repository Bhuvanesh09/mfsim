# TODO

## P0 — Correctness (must fix before results can be trusted)

- [ ] **Fix expense ratio double-counting** — NAV from `api.mfapi.in` is already net of expense ratio. The simulator's annual unit deduction double-counts it. Disable by default for API-sourced data; keep as opt-in for custom data loaders where NAV might be gross of fees.

- [ ] **Lot-level transaction tracking** — Implement FIFO-based lot accounting. Every purchase creates a lot with `(fund, date, units, cost_per_unit)`. Sells consume lots in FIFO order, recording holding period and realized gain/loss per lot. This is prerequisite for tax modeling, correct exit load calculation, and realistic P&L.

- [ ] **Fix broken metrics** — `MaximumDrawdownMetric` and `SortinoRatioMetric` reference a `portfolio_history["total"]` column that doesn't exist. Either reconstruct portfolio value history inside these metrics (like `SharpeRatioMetric` does) or compute it once in the simulator and pass it through.

- [ ] **Handle non-trading-day rebalance dates** — When a rebalance date (1st of month, Monday, etc.) falls on a market holiday, defer to the next available trading day instead of silently skipping.

## P1 — Core Features (needed for real-world usefulness)

- [ ] **Benchmark comparison** — Accept a benchmark fund in the simulator. Compute alpha, tracking error, and information ratio. The active-passive thesis needs a baseline to compare against.

- [ ] **Tax-aware returns** — Model Indian tax rules: equity MF LTCG (>12 months, 12.5% above 1.25L), STCG (<12 months, 20%), debt fund taxation. Use lot-level holding periods. Tax rules changed in Budget 2024 — support both pre and post-2024 regimes.

- [ ] **NAV data caching** — Cache API responses locally with configurable TTL. Don't hit `api.mfapi.in` on every simulation run. Store as parquet files for fast reloads.

- [ ] **Test suite** — Write tests for: date frequency logic (`_is_sip_date`, `_is_rebalance_date`), unit calculations, lot accounting, each metric against known values, data loader contracts. Target: every public method has at least one test.

- [ ] **Stamp duty modeling** — 0.005% on all MF purchases since July 2020. Small per transaction but compounds over 15-year backtests with monthly SIPs.

## P2 — User Experience (needed for public release)

- [ ] **Visualization module** — Equity curve, drawdown chart, allocation pie over time, strategy comparison plots. Use matplotlib. People judge backtesting tools by their charts.

- [ ] **CLI interface** — `uv run mfsim backtest --strategy momentum --start 2020-01-01 --end 2025-01-01` — quick backtests without writing Python.

- [ ] **Structured result output** — Return a `SimulationResult` dataclass instead of a raw dict. Include: metrics, portfolio history, final holdings, benchmark comparison, total invested, final value.

- [ ] **Multiple data source support** — Add AMFI direct download, BSE Star MF data, CSV fallback. Implement data source failover.

- [ ] **Better error messages** — When a fund name doesn't match any scheme, suggest the closest matches. When NAV data is missing for a date range, say which dates are affected.

## P3 — LLM/MCP Integration (the long-term vision)

- [ ] **MCP server** — Expose mfsim as MCP tools: `run_backtest`, `compare_strategies`, `get_portfolio_status`, `list_available_funds`, `get_fund_performance`. An LLM should be able to use mfsim without writing Python.

- [ ] **Rich strategy context** — Extend `rebalance()` to receive more than just NAV data. Add: market breadth, macro indicators (RBI rates, inflation, FII/DII flows), sector rotation data, fund metadata (AUM, category, benchmark, expense ratio).

- [ ] **LLM strategy adapter** — A strategy subclass that calls an LLM inside `rebalance()`. Pass portfolio state + market context as a prompt, parse the LLM's response into buy/sell orders. This is the bridge between traditional backtesting and AI-driven allocation.

- [ ] **News sentiment integration** — Data loader extension that fetches financial news and computes sentiment scores. Feed into strategy context so LLM-based strategies can react to market news.

- [ ] **Paper trading mode** — Forward-test strategies with live data without executing real transactions. Log what the strategy would have done and compare against actual market outcomes.

- [ ] **Strategy comparison reporting** — Generate structured markdown/JSON reports comparing multiple strategy runs. Designed for LLM consumption: an agent should be able to run 5 strategies, read the comparison report, and recommend the best one.

## P4 — Advanced (nice to have)

- [ ] **Goal-based planning** — "I need 1Cr in 10 years, what SIP do I need given this strategy?" Solve for SIP amount given target, time horizon, and strategy parameters.

- [ ] **Risk constraints** — Max allocation per fund, max drawdown stop-loss, sector concentration limits. Strategies should be able to declare constraints that the simulator enforces.

- [ ] **Multi-asset support** — Extend beyond mutual funds to ETFs, direct equity, and fixed deposits. Different asset classes have different settlement, taxation, and data source requirements.

- [ ] **Transaction cost modeling** — STT, brokerage, and GST for equity transactions. Exit load that varies by holding period and fund type.

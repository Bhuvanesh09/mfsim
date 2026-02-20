# Agent Worklog

This file records the work done by the AI agent on the mfsim project — decisions made, problems found, and rationale behind changes.

---

## 2026-02-21 — Initial Project Assessment & Setup

### What I did

1. **Full codebase audit** — Read every Python file, the notebook, and all documentation to understand the project end-to-end.

2. **Created `pyproject.toml`** — Replaced the empty `setup.py` and `requirements.txt` with a UV-compatible `pyproject.toml` using hatchling as the build backend. Declared all four runtime dependencies (`pandas`, `numpy`, `requests`, `scipy`) and dev dependencies (`pytest`, `ruff`, `jupyter`).

3. **Created `README.md`** — Wrote a project README covering the current state, usage examples, custom strategy/data loader patterns, and the LLM-MCP vision.

4. **Created `todo.md`** — Organized all identified improvements into a prioritized task list.

5. **Updated `.gitignore`** — Added entries for UV (`.venv/`, `uv.lock`), Jupyter checkpoints, IDE files, and build artifacts.

6. **Added `mfsim/__init__.py`** — The package was missing a top-level init file, which would prevent `pip install` or `uv add` from working correctly.

### Problems identified during audit

**Critical — Expense Ratio Double Counting**
The simulator deducts expense ratio annually by removing units from holdings. But NAV data from `api.mfapi.in` is already net of expense ratio — mutual fund houses deduct it daily from AUM before publishing NAV. The current implementation double-counts the expense ratio, understating returns. For API-sourced NAV data, expense ratio deduction should be disabled by default or clearly documented as an override for custom data sources where NAV is gross of fees.

**Critical — No Lot-Level Transaction Tracking**
When `rebalance()` returns sell orders (negative amounts), the simulator removes units but doesn't track:
- Which lots were sold (no FIFO/LIFO accounting)
- Holding period per lot (needed for Indian LTCG vs STCG — 12-month boundary)
- Realized gains/losses
- Exit load applicability (which depends on holding period, not a flat rate)

Without this, post-tax return calculations are impossible, and the simulation can't model real-world sell-side behavior.

**Moderate — No Benchmark Comparison**
The "active-passive" thesis requires measuring alpha against a benchmark. Currently there's no built-in way to compare strategy returns against a benchmark index. This should be a first-class concept in the simulator.

**Moderate — Settlement/Market Microstructure Not Modeled**
- Indian MFs have T+1/T+2 settlement
- NAV cut-off times (3 PM for equity)
- Stamp duty (0.005% on purchases since July 2020)
- These compound over long backtests

**Minor — Sharpe/Sortino/MaxDrawdown metrics assume a `total` column**
`MaximumDrawdownMetric` and `SortinoRatioMetric` reference `portfolio_history["total"]`, which doesn't exist in the portfolio history DataFrame. These metrics would fail at runtime. Only `TotalReturnMetric`, `SharpeRatioMetric`, and `XIRRMetric` are currently functional.

**Minor — `_is_rebalance_date` doesn't handle market holidays**
Rebalance triggers on calendar dates (1st of month, Mondays, etc.) but these may not be trading days. If the 1st is a holiday, the rebalance is silently skipped rather than deferred to the next trading day.

### Architecture observations

The strategy pattern (`BaseStrategy` → `rebalance()`) is well-suited for the LLM-MCP vision. The `rebalance()` contract is simple: receive portfolio state + NAV data + date, return buy/sell orders. An LLM could implement this directly.

However, for LLM-driven strategies to be genuinely useful, `rebalance()` needs richer context than just NAV data. It should eventually have access to:
- Market breadth indicators
- Macro data (interest rates, inflation, FII/DII flows)
- News sentiment scores
- Sector rotation data
- Fund-level metadata (AUM, category, benchmark)

The data loader abstraction is the right place to provide this — extend `BaseDataLoader` with methods for fetching supplementary market data.

---

## 2026-02-21 — Expense Ratio Fix, Broken Metrics Fix, Comprehensive Docstrings

### What I did

1. **Removed expense ratio double-counting** (`simulator.py:232-251`) — Deleted the entire block that deducted units on Jan 1st based on expense ratios. NAV from AMFI is already net of TER (verified via SEBI regulations and AMFI documentation). The `expense_ratios` dict is retained on the simulator for informational/reporting purposes.

2. **Fixed `MaximumDrawdownMetric` and `SortinoRatioMetric`** — Both were referencing `portfolio_history["total"]` which doesn't exist. Gave both metrics their own `_compute_portfolio_value_history()` method (same approach as `SharpeRatioMetric`): reconstruct daily portfolio value from transaction history + NAV data, then compute returns from that series.

3. **Added comprehensive docstrings across the entire library** — Every class and public method now has a docstring with Args/Returns documentation, usage examples, and explanatory notes. Key things documented:
   - Why NAV is net of TER (in `Simulator`, `BaseDataLoader`, `data_loader` module docstring)
   - The strategy contract (`rebalance()` returns, `allocate_money()` expected output)
   - How each metric works (formulas, parameters, edge cases)
   - Custom data loader implementation pattern
   - Custom strategy implementation pattern

4. **Added `XIRRMetric` to `metrics/__init__.py`** — It was missing from the exports.

### Decisions made

- **Not extracting `_compute_portfolio_value_history` into a shared utility yet.** Three metrics now have identical copies of this method. This is deliberate — extracting it would be premature optimization. When we add more metrics that need it, or when we refactor to compute it once in the simulator, we'll DRY it up then.

- **Kept `expense_ratios` and `exit_loads` loading in the simulator init.** Even though expense ratio isn't used for deduction anymore, having the data available is useful for reporting and for future features (e.g., comparing strategy returns across funds with different TERs).

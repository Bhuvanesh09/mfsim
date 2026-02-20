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

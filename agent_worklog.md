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

---

## 2026-02-22 — Hydra Config System & UV-Native Setup

### What I did

1. **Added Hydra config system** (`mfsim/configs/`, `mfsim/cli.py`) — Created a YAML-based DSL for launching backtests from the CLI without writing Python. The config structure has three composable layers:
   - `strategy/` — defines fund list, allocation weights, rebalance frequency, strategy type
   - `data_loader/` — selects data source (`mfapi` for live API, `index_csv` for local files)
   - `experiment/` — preset overrides that combine strategy + data loader + simulation params

2. **Created 5 experiment presets** reproducing the notebook's past runs:
   - `fixed_alloc_no_rebal` — 15yr 4-fund factor tilt, no rebalance (255% TR, 17.1% XIRR)
   - `semi_annual_rebal` — same funds, rebalance 2x/yr (252% TR, 17.0% XIRR)
   - `annual_rebal` — same funds, rebalance 1x/yr (251% TR, 17.0% XIRR)
   - `nifty50_baseline` — NIFTY 50 buy-and-hold (146% TR, 12.5% XIRR)
   - `momentum_value_short` — 1yr momentum vs value rotation (28.6% TR)

3. **Built strategy and data loader builders** (`mfsim/cli.py`) — Translates flat YAML config into the existing Python strategy/loader objects. Added `FixedAllocationStrategy` and `RebalancingStrategy` classes with SIP step-up support and target-allocation rebalancing.

4. **Made the project UV-native:**
   - Added `[project.scripts]` entry point: `mfsim-backtest = "mfsim.cli:main"`
   - Moved `run_backtest.py` → `mfsim/cli.py` and `configs/` → `mfsim/configs/` so Hydra config resolution works when installed as a package via `uv run`
   - Added `mfsim/configs/__init__.py` for Hydra's module-based config discovery
   - Stopped gitignoring `uv.lock` — lockfile committed for reproducible builds
   - Added `hydra-core` and `omegaconf` to runtime dependencies
   - Ran `uv sync` to generate lockfile

5. **Created `CLAUDE.md`** — Establishes project conventions: always use `uv run`/`uv sync`/`uv add`, never bare `python`/`pip`/`pytest`. Documents the Hydra config structure and CLI usage.

6. **Updated `README.md`** — Added CLI Quick Start section, Hydra Configs section with full directory tree and experiment results table, updated Architecture section.

### Decisions made

- **Configs inside the package, not at repo root.** Hydra resolves `config_path` relative to the calling module's `__file__`. When running as an installed entry point via `uv run mfsim-backtest`, the module lives in `.venv/`. Keeping configs at repo root would break resolution. Moving them into `mfsim/configs/` with an `__init__.py` makes Hydra treat it as a config module, which works for both `uv run` and direct `python` invocation.

- **Strategy classes in `cli.py`, not in `strategies/`.** `FixedAllocationStrategy` and `RebalancingStrategy` are config-driven wrappers — they translate YAML params into `BaseStrategy` implementations. They're closer to CLI glue than core library code. If they get reused from Python, they should move to `strategies/`.

- **`frequency: "never"` for buy-and-hold.** The existing `_is_rebalance_date` returns `False` for any unrecognized frequency string. Using `"never"` as the frequency for fixed allocation (no-rebalance) strategies leverages this behavior. It's readable and doesn't need code changes.

- **SIP step-up via year-difference calculation, not date tracking.** The step-up logic uses `current_year - start_year` to determine the multiplier rather than tracking each annual boundary. This means the step-up applies immediately on Jan 1st rather than on the SIP anniversary. This matches the notebook's behavior.

---

## 2026-02-27 — Experiment 002: Adaptive Factor Rotation

### What I did

1. **Implemented three adaptive factor rotation strategies** in `mfsim/strategies/adaptive_strategies.py`:
   - `TrendFilterStrategy` — uses a simple moving average on Nifty 50 to detect risk-on/risk-off regimes; tilts toward momentum when price is above SMA, toward value when below. Trend fund is loaded for signal computation only — never traded.
   - `RelativeStrengthStrategy` — computes a weighted return edge (momentum vs value) across configurable lookback horizons (1m/3m/6m); maps the edge to a momentum weight via `clip(0.5 + sensitivity × edge, min_w, max_w)`.
   - `DualSignalStrategy` — combines both signals with agreement logic: both risk-on AND RS ≥ 0.5 → amplify momentum; both risk-off AND RS < 0.5 → amplify value; disagreement → neutral 50/50.
   - Shared `_to_target_orders()` helper handles hard-rebalancing to target weights using last available NAV (safe for non-trading days).

2. **Extended the framework with new risk metrics** in `run_experiment.py`:
   - Sortino Ratio (downside-only volatility, consistent with how Sharpe is already computed)
   - Calmar Ratio (XIRR ÷ |Max Drawdown| — return per unit of worst-case loss)
   - Rolling 12-month Sharpe figure — reveals consistency over time vs the snapshot Sharpe
   - Period comparison figure — side-by-side bar chart across both study periods

3. **Discovered and used niftyindices.com PR data API** for long-horizon NSE index history:
   - The API at `https://niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString` requires active browser session cookies (expire within hours). Script `download_nse_data.py` documents how to capture them via DevTools.
   - Returns up to ~1 year per call; the downloader loops year-by-year and stitches results.
   - Data is **Price Return (PR)** — dividends excluded. All TRI variants tried returned empty. ~1–1.5% XIRR lower than actual TRI-based fund performance, but relative rankings hold since all strategies use the same base.
   - Correct index names for the API: `"Nifty 50"`, `"Nifty50 Value 20"`, `"NIFTY200MOMENTM30"` (no spaces, truncated "MOMENTUM" → "MOMENTM").
   - Common window: Jan 2010–Dec 2025 (limited by Value 20 earliest availability).
   - Alternative sources explored and rejected: `jugaad-data` (broken — NSE changed API format in 2021, `KeyError: 'd'`), `yfinance` (no Indian factor indices), `stooq` (same gap).

4. **Two-period study design**:
   - Period 1 (Mar 2015 → Dec 2025, ~10 years): full hyperparameter sweeps to find best parameters.
   - Period 2 (Feb 2020 → Dec 2025, ~5 years): same parameters applied out-of-sample to stress-test against COVID crash and subsequent recovery.
   - Starting from 2010 was rejected after observing that it captured the entire post-GFC bull run from the bottom, which inflated Momentum's advantage artificially.

5. **Hyperparameter sweeps**:
   - Sweep A: 20 runs (MA windows [50,100,150,200,250] × risk-on weights [55%,65%,75%,85%])
   - Sweep B: 24 runs (6 horizon presets × sensitivities [0.5,1.0,2.0,4.0])
   - Best A selected by XIRR; Best B selected by Sharpe

### Bugs found and fixed

**Bug 1 — `XIRRMetric` and `TotalReturnMetric`: exact end-date NAV lookup fails on holidays**
- File: `mfsim/metrics/metrics_collection.py`
- Symptom: `TotalReturn = -1.0`, `XIRR = NaN` when `end_date` is a market holiday (e.g. Dec 31 2025).
- Root cause: Both metrics used exact-date matching — `nav[nav["date"] == date]` or `nav.loc[[date]]`. On a non-trading day, the lookup returns empty, so `final_value = 0`, making XIRR unsolvable and TotalReturn = (0 / invested) − 1 = −1.
- Fix: Changed to "last available NAV on or before date": `nav[nav.index <= date].iloc[-1]`. Consistent with how `TaxAwareReturnMetric` already handled this correctly.

**Bug 2 — `Simulator.get_portfolio_value()`: same exact-date issue**
- File: `mfsim/backtester/simulator.py`
- Symptom: Returns `0.0` with WARNING logs for any holiday-dated valuation call.
- Fix: `nav_on_or_before = nav_df[nav_df.index <= date]`, use `.iloc[-1]` if non-empty.

**Bug 3 — `SortinoRatioMetric`: wrong risk-free rate frequency**
- File: `mfsim/backtester/simulator.py` (`_calculate_metrics`)
- Symptom: Sortino ratio was negative for all strategies (−0.16 to −0.38) despite positive XIRR — physically impossible for a strategy with positive risk-adjusted returns.
- Root cause: `_calculate_metrics` instantiated `SortinoRatioMetric(frequency=self.strategy.frequency)`. All strategies use `frequency="monthly"`, so `rf_daily = 0.05 / 12 = 0.417%`. But portfolio value history is computed on calendar days, giving typical daily returns of ~0.03%. The monthly risk-free rate dwarfed every daily return, making all excess returns negative and invalidating the ratio.
- Fix: Hardcoded `frequency="daily"` (same as `SharpeRatioMetric`), giving `rf_daily = 0.05 / 252 = 0.020%`.

**Bug 4 — `_DEFAULT_METRICS` in `adaptive_strategies.py` missing "Sortino Ratio"**
- File: `mfsim/strategies/adaptive_strategies.py`
- Symptom: Sortino showed `—` (NaN) for all adaptive strategies in final tables while baselines showed values.
- Root cause: Adaptive strategy constructors use `_DEFAULT_METRICS` as default metrics list. This constant only contained the original 4 metrics; "Sortino Ratio" was never added when the metric was introduced.
- Fix: Added `"Sortino Ratio"` to `_DEFAULT_METRICS`.

### Decisions made

- **PR data accepted for strategy comparison.** Absolute XIRR is ~1–1.5% below real-world TRI-based fund performance (dividends excluded). Since all strategies use the same PR base, relative rankings are unaffected. Documented clearly in experiment README and REPORT.md.

- **Period 2 uses Period 1 hyperparameters.** Sweeping separately on the 2020–2025 window would be overfitting on a short, structurally unusual period (COVID crash + recovery). The correct scientific approach is to treat Period 2 as pure out-of-sample validation.

- **`_DEFAULT_METRICS` updated rather than passing metrics per-call.** Sortino is a standard risk metric that all adaptive strategies should compute by default, not an experiment-specific addition. Updating the class-level constant is cleaner than threading a metrics argument through every strategy instantiation site.

- **Rolling Sharpe uses Period 1 history (longer window).** A 252-day rolling window on the 5-year Period 2 would lose the first year of data, leaving only 4 years. Period 1's 10-year history gives a more meaningful rolling chart.

### Key findings summary

See `experiments/002_adaptive_factor_rotation/README.md` for full analysis and financial implications.

Brief summary:
- Momentum 30 (pure factor) delivered highest XIRR in both periods (17.35% and 17.76%)
- Adaptive strategies marginally beat 50/50 Fixed in Period 1 (+8bps); meaningfully beat it in Period 2 (+40bps XIRR, −14bps max drawdown for Best A)
- The trend filter's value lies in crash protection: Best A's Calmar (0.633) > Momentum (0.579) in Period 2
- Low MA window noise and low signal sensitivity consistently win across both sweeps — suggesting gradual tilts, not aggressive factor switching
- All Sortino ratios are similar across strategies (~0.73–0.77), meaning no strategy has a fundamentally different upside/downside character

---

## 2026-02-27 — Correctness Hardening (Critical Fix Pass)

### What I did

1. **Created an isolated fix branch**: `correctness-hardening`.

2. **Fixed NAV ordering and valuation correctness for MFAPI data path**:
   - Added strict NAV normalization in `MfApiDataLoader` (`date` parse with `dayfirst=True`, numeric `nav`, drop invalid rows, sort ascending).
   - Applied normalization both on cache reads and fresh API fetches before writing cache.
   - This removes dependence on MFAPI's descending raw order and prevents incorrect `iloc[-1]` valuation results.

3. **Hardened simulator execution invariants** (`mfsim/backtester/simulator.py`):
   - Normalizes/sorts NAV data for all funds at load time.
   - Builds a **common trading calendar** across all strategy funds and snaps `start_date` to first common date.
   - Runs the loop over common trading dates (not fund_list[0] dates).
   - Makes sells transactional-safe by applying lot tracker operations **before** appending to portfolio history.
   - Added metric alias support: `"Max Drawdown"` maps to `MaximumDrawdownMetric`.
   - Added guard for empty `portfolio_history` in `current_portfolio`.

4. **Fixed oversell bug in lot tracking** (`mfsim/backtester/lot_tracker.py`):
   - `sell()` now validates requested units <= available holdings and raises `ValueError` otherwise.
   - Prevents silent negative holdings and accounting corruption.

5. **Centralized robust NAV lookup in metrics** (`mfsim/metrics/metrics_collection.py`):
   - Added `latest_nav_on_or_before()` helper handling both column-based and index-based NAV frames, including unsorted input.
   - Updated `TotalReturnMetric`, `XIRRMetric`, and `TaxAwareReturnMetric` to use it.

6. **Improved risk metric time-series construction**:
   - `compute_portfolio_value_history()` now uses trading dates observed in NAV data (plus transaction dates), not calendar-expanded daily series.
   - Reduces artificial weekend/holiday zero-return distortion in Sharpe/Sortino.

7. **Improved CLI rebalance valuation fallback** (`mfsim/cli.py`):
   - Rebalancing now uses latest NAV on/before date instead of exact-date-only lookup.

8. **Added focused regression tests**:
   - `tests/test_data_loader.py`: MFAPI normalization/sort tests (cache + API path).
   - `tests/test_lot_tracker.py`: oversell raises and does not mutate holdings.
   - `tests/test_metrics.py`: unsorted NAV valuation tests and helper tests.
   - `tests/test_simulator.py`: oversell rejection, common-calendar start-date behavior, metric alias support, unsorted-loader sort behavior.

9. **Updated experiment labeling and docs for methodological correctness** (Experiment 002):
   - Replaced incorrect "out-of-sample" wording with "stress subperiod" where appropriate.
   - Corrected invested-amount labels in README (`~₹14.0L`, `~₹8.2L`).
   - Re-ran experiment script and regenerated report/figures.

### Bugs found and fixed

- **Critical**: MFAPI descending NAV order + "on-or-before + iloc[-1]" caused materially wrong end valuation.
- **Critical**: Oversell allowed negative holdings without error.
- **High**: Simulator calendar/start-date anchored to first fund could fail/misprice with non-aligned fund histories.
- **Medium**: `Max Drawdown` metric alias mismatch caused silent "Unknown metric" runs.
- **Medium**: Period-2 "out-of-sample" language in Exp 002 was methodologically incorrect (Period 2 overlaps Period 1).

### Validation run

- `uv run pytest tests/test_data_loader.py tests/test_lot_tracker.py tests/test_metrics.py tests/test_simulator.py -q`
  - **68 passed**
- `uv run pytest -q`
  - **68 passed**
- `uv run pytest --cov=mfsim --cov-report=term-missing -q`
  - **68 passed**, coverage improved from ~43% to **49%**
- Re-ran:
  - `uv run python experiments/002_adaptive_factor_rotation/run_experiment.py`
  - Regenerated `results/REPORT.md` and figure artifacts under `experiments/002_adaptive_factor_rotation/results/figures/`.

### Decisions made

- Kept fixes as **correctness-first** (data invariants + execution invariants + tests) before any reporting/app-layer work.
- Treated method-label cleanup in experiment docs as part of correctness because it affects interpretation reliability.
- Did not commit yet; changes remain staged in branch workspace for review.

"""
Built-in performance and risk metrics.

All metrics follow the :class:`~mfsim.metrics.base_metric.BaseMetric` interface:
they receive the full simulation state and return a single float.

Available metrics:
    - :class:`TotalReturnMetric` — simple return over the period
    - :class:`XIRRMetric` — IRR accounting for irregular cash flows
    - :class:`SharpeRatioMetric` — risk-adjusted return vs risk-free rate
    - :class:`SortinoRatioMetric` — like Sharpe but only penalizes downside
    - :class:`MaximumDrawdownMetric` — worst peak-to-trough decline
    - :class:`AlphaMetric` — annualized excess return over a benchmark
    - :class:`TrackingErrorMetric` — annualized std of return differences vs benchmark
    - :class:`InformationRatioMetric` — alpha / tracking error
    - :class:`TaxAwareReturnMetric` — post-tax total return using Indian MF tax rules
"""

import numpy as np
import pandas as pd
from scipy.optimize import newton

from .base_metric import BaseMetric


def compute_portfolio_value_history(portfolio_history, nav_data, current_date):
    """Reconstruct daily portfolio value from transaction history and NAV data.

    For each calendar day from the first transaction to ``current_date``,
    computes the total portfolio value by multiplying each fund's
    cumulative units held by its NAV on that day.

    Args:
        portfolio_history: Transaction DataFrame with ``date`` index and
            columns ``fund_name``, ``units``, ``amount``.
        nav_data: Fund NAV data dict.
        current_date: End date for the value history.

    Returns:
        pandas Series indexed by date with portfolio value as values.
    """
    portfolio_history = portfolio_history.sort_values("date")

    all_dates = pd.date_range(start=portfolio_history.index.min(), end=current_date, freq="D")

    holdings_df = pd.DataFrame(index=all_dates, columns=nav_data.keys()).fillna(0.0)

    for txn_date, row in portfolio_history.iterrows():
        if txn_date > current_date:
            continue
        fund = row["fund_name"]
        units = row["units"]
        holdings_df.loc[txn_date:, fund] += units

    portfolio_values = pd.Series(0.0, index=all_dates, dtype=float)
    for fund, nav_df in nav_data.items():
        nav_df = nav_df[nav_df.index <= current_date]
        # Reindex to all calendar days and forward-fill so weekends/holidays
        # carry the last known NAV instead of producing NaN/zero.
        nav_aligned = nav_df["nav"].reindex(all_dates).ffill()
        holdings = holdings_df[fund]
        portfolio_values += holdings * nav_aligned

    portfolio_values = portfolio_values.fillna(0.0)
    return portfolio_values


class XIRRMetric(BaseMetric):
    """Extended Internal Rate of Return.

    XIRR accounts for the timing of each cash flow (SIP installments,
    rebalancing buys/sells) rather than assuming uniform intervals.
    This makes it the most accurate return measure for portfolios with
    irregular investments.

    The calculation:
        1. Each investment is treated as a negative cash flow on its date.
        2. The final portfolio value is treated as a positive cash flow
           on the end date.
        3. Solves for rate ``r`` where the net present value of all
           cash flows equals zero:
           ``NPV = sum(cf_i / (1 + r) ^ ((date_i - date_0) / 365))``
        4. Uses Newton's method (``scipy.optimize.newton``) for root-finding.

    Returns ``float('nan')`` if the solver fails to converge.
    """

    def calculate(self, portfolio_history, current_portfolio, date, nav_data):
        """Compute XIRR from the portfolio's cash flow history.

        Args:
            portfolio_history: Transaction DataFrame (see :class:`BaseMetric`).
            current_portfolio: Final holdings ``{fund_name: units}``.
            date: Simulation end date.
            nav_data: Fund NAV data dict.

        Returns:
            Annualized XIRR as a decimal (e.g., ``0.12`` for 12%).
        """
        cash_flows = []
        dates = []

        # Filter out zero-amount rows (e.g., expense ratio deductions)
        portfolio_history = portfolio_history[portfolio_history["amount"].abs() > 1e-8]

        for idx, row in portfolio_history.iterrows():
            if "date" in row:
                dates.append(row["date"])
            else:
                dates.append(idx)
            cash_flows.append(-row["amount"])

        # Final portfolio value as a positive cash flow on the end date.
        # Use last available NAV on or before `date` so holidays don't zero out the value.
        final_value = 0
        for fund, units in current_portfolio.items():
            nav = nav_data[fund]
            if "date" in nav.columns:
                nav_on_or_before = nav.loc[nav["date"] <= date]
            elif nav.index.name == "date":
                nav_on_or_before = nav[nav.index <= date]
            else:
                nav_on_or_before = pd.DataFrame()
            if not nav_on_or_before.empty:
                final_value += units * float(nav_on_or_before["nav"].iloc[-1])
        if final_value != 0:
            cash_flows.append(final_value)
            dates.append(date)

        def xnpv(rate, cashflows, dates):
            t0 = dates[0]
            return sum(
                cf / (1 + rate) ** ((d - t0).days / 365.0) for cf, d in zip(cashflows, dates)
            )

        def xirr(cashflows, dates, guess=0.1):
            try:
                return newton(lambda r: xnpv(r, cashflows, dates), guess)
            except (RuntimeError, OverflowError):
                return float("nan")

        if len(cash_flows) < 2:
            return float("nan")
        return float(xirr(cash_flows, dates))


class TotalReturnMetric(BaseMetric):
    """Simple total return over the simulation period.

    Formula::

        total_return = (final_portfolio_value / total_money_invested) - 1

    This does **not** account for the timing of investments. For SIP-based
    portfolios, use :class:`XIRRMetric` for a more accurate picture.
    A total return of ``0.45`` means a 45% gain.
    """

    def calculate(self, portfolio_history, current_portfolio, date, nav_data):
        """Compute total return.

        Args:
            portfolio_history: Transaction DataFrame.
            current_portfolio: Final holdings ``{fund_name: units}``.
            date: Simulation end date.
            nav_data: Fund NAV data dict.

        Returns:
            Total return as a decimal (e.g., ``0.45`` for 45% return).
        """
        money_invested = portfolio_history["amount"].sum()
        # Use last available NAV on or before `date` so holidays don't zero out the value.
        final_value = 0
        for fund, units in current_portfolio.items():
            nav_df = nav_data[fund]
            if "date" in nav_df.columns:
                nav_on_or_before = nav_df.loc[nav_df["date"] <= date]
            elif nav_df.index.name == "date":
                nav_on_or_before = nav_df[nav_df.index <= date]
            else:
                raise ValueError(
                    f"Invalid NAV data format for fund {fund}. Expected 'date' as column or index."
                )
            if not nav_on_or_before.empty:
                final_value += units * float(nav_on_or_before["nav"].iloc[-1])
        total_return = (final_value / money_invested) - 1
        return float(total_return)


class SharpeRatioMetric(BaseMetric):
    """Risk-adjusted return using the Sharpe Ratio.

    Measures excess return per unit of total volatility. Higher is better.

    Formula::

        sharpe = (mean(excess_return) / std(excess_return))
                * sqrt(periods_per_year)

    The metric reconstructs a daily portfolio value history from the
    transaction log and NAV data, then computes returns from that series.

    Args:
        risk_free_rate: Annual risk-free rate as a decimal.
            Default ``0.06`` (6%, roughly Indian T-bill rate).
        frequency: Return frequency — ``'daily'`` (252 trading days/year)
            or ``'monthly'`` (12 periods/year). Default ``'daily'``.

    Note:
        Returns ``float('nan')`` if there are fewer than 2 data points
        or if portfolio volatility is zero.
    """

    def __init__(self, risk_free_rate=0.06, frequency="daily"):
        self.risk_free_rate = risk_free_rate
        self.frequency = frequency

    def calculate(self, portfolio_history, current_portfolio, date, nav_data):
        """Compute the annualized Sharpe Ratio.

        Args:
            portfolio_history: Transaction DataFrame.
            current_portfolio: Final holdings ``{fund_name: units}``.
            date: Simulation end date.
            nav_data: Fund NAV data dict.

        Returns:
            Annualized Sharpe Ratio as a float.
        """
        portfolio_values = compute_portfolio_value_history(portfolio_history, nav_data, date)
        if portfolio_values.empty or len(portfolio_values) < 2:
            return np.nan

        portfolio_values = portfolio_values.sort_index()
        daily_returns = portfolio_values.pct_change().dropna()

        if self.frequency == "daily":
            rf_daily = self.risk_free_rate / 252
            scaling_factor = np.sqrt(252)
        elif self.frequency == "monthly":
            rf_daily = self.risk_free_rate / 12
            scaling_factor = np.sqrt(12)
        else:
            raise ValueError("Unsupported frequency. Use 'daily' or 'monthly'.")

        excess_returns = daily_returns - rf_daily

        mean_excess_return = excess_returns.mean()
        std_excess_return = excess_returns.std()

        if std_excess_return == 0:
            return np.nan

        sharpe_ratio = (mean_excess_return / std_excess_return) * scaling_factor
        return float(sharpe_ratio)


class MaximumDrawdownMetric(BaseMetric):
    """Maximum peak-to-trough decline in portfolio value.

    Measures the worst loss from a peak before a new peak is reached.
    A max drawdown of ``-0.20`` means the portfolio dropped 20% from
    its highest point at some point during the simulation.

    This metric reconstructs the daily portfolio value history
    (same approach as :class:`SharpeRatioMetric`) to compute drawdown.
    """

    def calculate(self, portfolio_history, current_portfolio, date, nav_data):
        """Compute maximum drawdown.

        Args:
            portfolio_history: Transaction DataFrame.
            current_portfolio: Final holdings ``{fund_name: units}``.
            date: Simulation end date.
            nav_data: Fund NAV data dict.

        Returns:
            Maximum drawdown as a negative decimal (e.g., ``-0.20``
            for a 20% drawdown). Returns ``0.0`` if portfolio value
            never declined.
        """
        portfolio_values = compute_portfolio_value_history(portfolio_history, nav_data, date)
        if portfolio_values.empty or len(portfolio_values) < 2:
            return 0.0

        portfolio_values = portfolio_values.sort_index()
        rolling_max = portfolio_values.cummax()
        drawdown = (portfolio_values - rolling_max) / rolling_max
        max_drawdown = drawdown.min()
        return float(max_drawdown)


class SortinoRatioMetric(BaseMetric):
    """Downside-risk-adjusted return using the Sortino Ratio.

    Like the Sharpe Ratio, but only considers downside volatility
    (negative returns) rather than total volatility. This is more
    appropriate for portfolios with asymmetric return distributions —
    upside volatility shouldn't be penalized.

    Formula::

        sortino = (mean_excess_return / downside_deviation) * sqrt(periods_per_year)

    Args:
        risk_free_rate: Annual risk-free rate as a decimal.
            Default ``0.05`` (5%).
        frequency: Return frequency — ``'daily'``, ``'weekly'``, or
            ``'monthly'``. Default ``'daily'``.
    """

    def __init__(self, risk_free_rate=0.05, frequency="daily"):
        self.risk_free_rate = risk_free_rate
        self.frequency = frequency

    def calculate(self, portfolio_history, current_portfolio, date, nav_data):
        """Compute the annualized Sortino Ratio.

        Args:
            portfolio_history: Transaction DataFrame.
            current_portfolio: Final holdings ``{fund_name: units}``.
            date: Simulation end date.
            nav_data: Fund NAV data dict.

        Returns:
            Annualized Sortino Ratio as a float. Returns ``float('nan')``
            if there are fewer than 2 data points or no downside deviation.
        """
        portfolio_values = compute_portfolio_value_history(portfolio_history, nav_data, date)
        if portfolio_values.empty or len(portfolio_values) < 2:
            return np.nan

        portfolio_values = portfolio_values.sort_index()
        returns = portfolio_values.pct_change().dropna()

        periods_per_year = self._get_periods_per_year()
        excess_returns = returns - self.risk_free_rate / periods_per_year
        downside_returns = excess_returns[excess_returns < 0]

        if downside_returns.empty or downside_returns.std() == 0:
            return np.nan

        expected_return = excess_returns.mean()
        downside_deviation = downside_returns.std()
        sortino_ratio = (expected_return / downside_deviation) * np.sqrt(periods_per_year)
        return float(sortino_ratio)

    def _get_periods_per_year(self):
        """Return the number of periods per year for the configured frequency.

        Returns:
            ``252`` for daily, ``52`` for weekly, ``12`` for monthly.
        """
        if self.frequency == "daily":
            return 252
        elif self.frequency == "weekly":
            return 52
        elif self.frequency == "monthly":
            return 12
        else:
            return 252


class AlphaMetric(BaseMetric):
    """Annualized excess return over a benchmark (Jensen's Alpha simplified).

    Alpha = annualized_portfolio_return - annualized_benchmark_return

    Args:
        benchmark_fund: Name of the fund in ``nav_data`` to use as benchmark.
    """

    def __init__(self, benchmark_fund: str):
        self.benchmark_fund = benchmark_fund

    def calculate(self, portfolio_history, current_portfolio, date, nav_data):
        """Compute annualized alpha vs the benchmark.

        Args:
            portfolio_history: Transaction DataFrame.
            current_portfolio: Final holdings ``{fund_name: units}``.
            date: Simulation end date.
            nav_data: Fund NAV data dict.

        Returns:
            Annualized alpha as a decimal. Returns ``float('nan')`` if
            insufficient data.
        """
        portfolio_values = compute_portfolio_value_history(portfolio_history, nav_data, date)
        if portfolio_values.empty or len(portfolio_values) < 2:
            return np.nan

        portfolio_values = portfolio_values.sort_index()

        # Get benchmark values over the same period
        benchmark_nav = nav_data[self.benchmark_fund]["nav"]
        start = portfolio_values.index.min()
        end = portfolio_values.index.max()
        benchmark_nav = benchmark_nav[(benchmark_nav.index >= start) & (benchmark_nav.index <= end)]

        if benchmark_nav.empty or len(benchmark_nav) < 2:
            return np.nan

        # Annualized returns
        days = (end - start).days
        if days == 0:
            return np.nan

        port_return = (portfolio_values.iloc[-1] / portfolio_values.iloc[0]) ** (365.0 / days) - 1
        bench_return = (benchmark_nav.iloc[-1] / benchmark_nav.iloc[0]) ** (365.0 / days) - 1

        return float(port_return - bench_return)


class TrackingErrorMetric(BaseMetric):
    """Annualized standard deviation of return differences vs benchmark.

    Measures how consistently a portfolio tracks (or deviates from) a
    benchmark index. Lower tracking error means the portfolio behaves
    more like the benchmark.

    Args:
        benchmark_fund: Name of the fund in ``nav_data`` to use as benchmark.
    """

    def __init__(self, benchmark_fund: str):
        self.benchmark_fund = benchmark_fund

    def calculate(self, portfolio_history, current_portfolio, date, nav_data):
        """Compute annualized tracking error.

        Args:
            portfolio_history: Transaction DataFrame.
            current_portfolio: Final holdings ``{fund_name: units}``.
            date: Simulation end date.
            nav_data: Fund NAV data dict.

        Returns:
            Annualized tracking error as a decimal. Returns ``float('nan')``
            if insufficient data.
        """
        portfolio_values = compute_portfolio_value_history(portfolio_history, nav_data, date)
        if portfolio_values.empty or len(portfolio_values) < 2:
            return np.nan

        portfolio_values = portfolio_values.sort_index()
        port_returns = portfolio_values.pct_change().dropna()

        benchmark_nav = nav_data[self.benchmark_fund]["nav"]
        # Align to portfolio dates
        benchmark_aligned = benchmark_nav.reindex(portfolio_values.index).ffill()
        bench_returns = benchmark_aligned.pct_change().dropna()

        # Align both return series
        common_idx = port_returns.index.intersection(bench_returns.index)
        if len(common_idx) < 2:
            return np.nan

        diff = port_returns.loc[common_idx] - bench_returns.loc[common_idx]
        tracking_error = diff.std() * np.sqrt(252)
        return float(tracking_error)


class InformationRatioMetric(BaseMetric):
    """Ratio of excess return to tracking error (annualized).

    Measures risk-adjusted excess return relative to a benchmark.
    Higher values indicate the portfolio generates more excess return
    per unit of tracking risk.

    Args:
        benchmark_fund: Name of the fund in ``nav_data`` to use as benchmark.
    """

    def __init__(self, benchmark_fund: str):
        self.benchmark_fund = benchmark_fund

    def calculate(self, portfolio_history, current_portfolio, date, nav_data):
        """Compute annualized information ratio.

        Args:
            portfolio_history: Transaction DataFrame.
            current_portfolio: Final holdings ``{fund_name: units}``.
            date: Simulation end date.
            nav_data: Fund NAV data dict.

        Returns:
            Annualized information ratio as a float. Returns ``float('nan')``
            if insufficient data or zero tracking error.
        """
        portfolio_values = compute_portfolio_value_history(portfolio_history, nav_data, date)
        if portfolio_values.empty or len(portfolio_values) < 2:
            return np.nan

        portfolio_values = portfolio_values.sort_index()
        port_returns = portfolio_values.pct_change().dropna()

        benchmark_nav = nav_data[self.benchmark_fund]["nav"]
        benchmark_aligned = benchmark_nav.reindex(portfolio_values.index).ffill()
        bench_returns = benchmark_aligned.pct_change().dropna()

        common_idx = port_returns.index.intersection(bench_returns.index)
        if len(common_idx) < 2:
            return np.nan

        diff = port_returns.loc[common_idx] - bench_returns.loc[common_idx]

        mean_diff = diff.mean()
        std_diff = diff.std()

        if std_diff == 0:
            return np.nan

        ir = (mean_diff / std_diff) * np.sqrt(252)
        return float(ir)


class TaxAwareReturnMetric(BaseMetric):
    """Post-tax total return using Indian MF taxation rules.

    Models Indian mutual fund taxation (post Budget 2024) using lot-level
    holding period data from :class:`~mfsim.backtester.lot_tracker.LotTracker`.

    Equity fund tax rates:
        - LTCG (holding > 12 months): 12.5% on gains above 1.25 lakh/year
        - STCG (holding <= 12 months): 20%

    The metric computes tax on both realized gains (from sells during the
    simulation) and unrealized gains (as if the portfolio were liquidated
    at the end date).

    Args:
        lot_tracker: :class:`~mfsim.backtester.lot_tracker.LotTracker` instance
            with realized gains history.
        lots_at_end: List of open :class:`~mfsim.backtester.lot_tracker.Lot`
            instances at simulation end (for unrealized gain computation).
    """

    LTCG_RATE = 0.125  # 12.5%
    STCG_RATE = 0.20  # 20%
    LTCG_EXEMPTION = 125000  # 1.25 lakh per year
    LTCG_HOLDING_DAYS = 365  # >12 months for equity

    def __init__(self, lot_tracker, lots_at_end=None):
        self.lot_tracker = lot_tracker
        self.lots_at_end = lots_at_end or []

    def calculate(self, portfolio_history, current_portfolio, date, nav_data):
        """Compute post-tax total return.

        Args:
            portfolio_history: Transaction DataFrame.
            current_portfolio: Final holdings ``{fund_name: units}``.
            date: Simulation end date.
            nav_data: Fund NAV data dict.

        Returns:
            Post-tax total return as a decimal (e.g., ``0.35`` for 35%).
            Returns ``float('nan')`` if total invested is zero.
        """
        # Net invested = gross buys minus rebalancing sells (correct denominator)
        total_invested = portfolio_history[portfolio_history["amount"] > 0]["amount"].sum()

        # 1. Calculate final portfolio value (pre-tax), using last available NAV
        final_value = 0.0
        for fund, units in current_portfolio.items():
            nav_df = nav_data[fund]
            nav_on_or_before = nav_df[nav_df.index <= date]
            if not nav_on_or_before.empty:
                final_value += units * float(nav_on_or_before["nav"].iloc[-1])

        # 2. Calculate tax on realized gains
        realized_tax = self._compute_realized_tax(date)

        # 3. Calculate tax on unrealized gains (as if liquidated at end_date)
        unrealized_tax = self._compute_unrealized_tax(date, nav_data)

        total_tax = realized_tax + unrealized_tax
        post_tax_value = final_value - total_tax

        if total_invested == 0:
            return np.nan

        return float((post_tax_value / total_invested) - 1)

    def _compute_realized_tax(self, end_date):
        """Compute tax on all realized gains, applying the LTCG exemption per financial year.

        Indian tax rules:
        - LTCG and LTCL are netted per financial year; the ₹1.25L exemption
          applies to the net LTCG in each FY.
        - STCL offsets STCG first, then any remaining STCL offsets LTCG.
        - Losses cannot be carried forward in this simplified model.

        Args:
            end_date: Simulation end date (unused here; exemption is applied
                per financial year of the sell date).

        Returns:
            Total tax liability on realized gains across all financial years.
        """
        # Bucket gains/losses by Indian financial year (Apr–Mar)
        # fy_key: the year in which the FY starts (e.g. 2023 for FY 2023-24)
        fy_ltcg: dict[int, float] = {}
        fy_stcg: dict[int, float] = {}

        for rg in self.lot_tracker.realized_gains:
            sell_date = rg.sell_date
            fy = sell_date.year if sell_date.month >= 4 else sell_date.year - 1
            if rg.holding_days > self.LTCG_HOLDING_DAYS:
                fy_ltcg[fy] = fy_ltcg.get(fy, 0.0) + rg.gain
            else:
                fy_stcg[fy] = fy_stcg.get(fy, 0.0) + rg.gain

        total_tax = 0.0
        all_fys = set(fy_ltcg) | set(fy_stcg)
        for fy in all_fys:
            ltcg = fy_ltcg.get(fy, 0.0)
            stcg = fy_stcg.get(fy, 0.0)

            # STCL offsets STCG first, then any remaining STCL offsets LTCG
            if stcg < 0:
                ltcg += stcg  # STCL reduces LTCG
                stcg = 0.0

            # LTCL offsets LTCG within the same FY
            # (negative ltcg means net loss — no tax, no carryforward here)
            ltcg_taxable = max(0.0, ltcg - self.LTCG_EXEMPTION)
            stcg_taxable = max(0.0, stcg)

            total_tax += ltcg_taxable * self.LTCG_RATE + stcg_taxable * self.STCG_RATE

        return total_tax

    def _compute_unrealized_tax(self, end_date, nav_data):
        """Compute tax on unrealized gains (if portfolio were liquidated at end_date).

        Args:
            end_date: Date at which to value the portfolio for unrealized gains.
            nav_data: Fund NAV data dict.

        Returns:
            Total tax liability on unrealized gains.
        """
        # All unrealized lots are hypothetically sold in the same FY at end_date,
        # so gains and losses net within that single liquidation event.
        ltcg_total = 0.0
        stcg_total = 0.0

        for lot in self.lots_at_end:
            fund = lot.fund_name
            nav_df = nav_data[fund]
            nav_df_filtered = nav_df[nav_df.index <= end_date]
            if nav_df_filtered.empty:
                continue
            current_nav = float(nav_df_filtered["nav"].iloc[-1])
            gain = (current_nav - lot.cost_per_unit) * lot.units

            holding_days = (end_date - lot.purchase_date).days
            if holding_days > self.LTCG_HOLDING_DAYS:
                ltcg_total += gain  # includes losses (negative)
            else:
                stcg_total += gain

        # STCL offsets STCG first, then remaining STCL offsets LTCG
        if stcg_total < 0:
            ltcg_total += stcg_total
            stcg_total = 0.0

        ltcg_taxable = max(0.0, ltcg_total - self.LTCG_EXEMPTION)
        return ltcg_taxable * self.LTCG_RATE + max(0.0, stcg_total) * self.STCG_RATE

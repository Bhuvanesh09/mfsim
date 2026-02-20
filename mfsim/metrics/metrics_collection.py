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
"""

import numpy as np
import pandas as pd
from .base_metric import BaseMetric
from scipy.optimize import newton


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

        # Final portfolio value as a positive cash flow on the end date
        final_value = 0
        for fund, units in current_portfolio.items():
            nav = nav_data[fund]
            if "date" in nav.columns:
                nav_on_date = nav.loc[nav["date"] == date, "nav"]
            elif nav.index.name == "date":
                nav_on_date = (
                    nav.loc[[date], "nav"] if date in nav.index else pd.Series([])
                )
            else:
                nav_on_date = pd.Series([])
            if not nav_on_date.empty:
                final_value += units * nav_on_date.values[0]
        if final_value != 0:
            cash_flows.append(final_value)
            dates.append(date)

        def xnpv(rate, cashflows, dates):
            t0 = dates[0]
            return sum(
                cf / (1 + rate) ** ((d - t0).days / 365.0)
                for cf, d in zip(cashflows, dates)
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
        final_value = 0
        for fund, units in current_portfolio.items():
            nav_df = nav_data[fund]
            if "date" in nav_df.columns:
                nav_on_date = nav_df.loc[nav_df["date"] == date, "nav"]
            elif nav_df.index.name == "date":
                nav_on_date = (
                    nav_df.loc[[date], "nav"]
                    if date in nav_df.index
                    else pd.Series([])
                )
            else:
                raise ValueError(
                    f"Invalid NAV data format for fund {fund}. "
                    f"Expected 'date' as column or index."
                )
            if not nav_on_date.empty:
                final_value += units * nav_on_date.values[0]
        total_return = (final_value / money_invested) - 1
        return float(total_return)


class SharpeRatioMetric(BaseMetric):
    """Risk-adjusted return using the Sharpe Ratio.

    Measures excess return per unit of total volatility. Higher is better.

    Formula::

        sharpe = (mean(portfolio_return - risk_free_rate) / std(portfolio_return - risk_free_rate)) * sqrt(periods_per_year)

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
        portfolio_values = self._compute_portfolio_value_history(
            portfolio_history, nav_data, date
        )
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

    def _compute_portfolio_value_history(
        self, portfolio_history, nav_data, current_date
    ):
        """Reconstruct daily portfolio value from transaction history and NAV data.

        For each calendar day from the first transaction to ``current_date``,
        computes the total portfolio value by multiplying each fund's
        cumulative units held by its NAV on that day.

        Args:
            portfolio_history: Transaction DataFrame.
            nav_data: Fund NAV data dict.
            current_date: End date for the value history.

        Returns:
            pandas Series indexed by date with portfolio value as values.
        """
        portfolio_history = portfolio_history.sort_values("date")

        all_dates = pd.date_range(
            start=portfolio_history.index.min(), end=current_date, freq="D"
        )

        holdings_df = pd.DataFrame(
            index=all_dates, columns=nav_data.keys()
        ).fillna(0.0)

        for txn_date, row in portfolio_history.iterrows():
            if txn_date > current_date:
                continue
            fund = row["fund_name"]
            units = row["units"]
            holdings_df.loc[txn_date:, fund] += units

        portfolio_values = pd.Series(index=all_dates, dtype=float)
        for fund, nav_df in nav_data.items():
            nav_df = nav_df[nav_df.index <= current_date]
            holdings = holdings_df[fund]
            portfolio_values += holdings * nav_df["nav"]

        portfolio_values = portfolio_values.fillna(0.0)
        return portfolio_values


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
        portfolio_values = self._compute_portfolio_value_history(
            portfolio_history, nav_data, date
        )
        if portfolio_values.empty or len(portfolio_values) < 2:
            return 0.0

        portfolio_values = portfolio_values.sort_index()
        rolling_max = portfolio_values.cummax()
        drawdown = (portfolio_values - rolling_max) / rolling_max
        max_drawdown = drawdown.min()
        return float(max_drawdown)

    def _compute_portfolio_value_history(
        self, portfolio_history, nav_data, current_date
    ):
        """Reconstruct daily portfolio value from transaction history.

        See :meth:`SharpeRatioMetric._compute_portfolio_value_history`
        for details — uses the same approach.
        """
        portfolio_history = portfolio_history.sort_values("date")

        all_dates = pd.date_range(
            start=portfolio_history.index.min(), end=current_date, freq="D"
        )

        holdings_df = pd.DataFrame(
            index=all_dates, columns=nav_data.keys()
        ).fillna(0.0)

        for txn_date, row in portfolio_history.iterrows():
            if txn_date > current_date:
                continue
            fund = row["fund_name"]
            units = row["units"]
            holdings_df.loc[txn_date:, fund] += units

        portfolio_values = pd.Series(index=all_dates, dtype=float)
        for fund, nav_df in nav_data.items():
            nav_df = nav_df[nav_df.index <= current_date]
            holdings = holdings_df[fund]
            portfolio_values += holdings * nav_df["nav"]

        portfolio_values = portfolio_values.fillna(0.0)
        return portfolio_values


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
        portfolio_values = self._compute_portfolio_value_history(
            portfolio_history, nav_data, date
        )
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
        sortino_ratio = (expected_return / downside_deviation) * np.sqrt(
            periods_per_year
        )
        return float(sortino_ratio)

    def _compute_portfolio_value_history(
        self, portfolio_history, nav_data, current_date
    ):
        """Reconstruct daily portfolio value from transaction history.

        See :meth:`SharpeRatioMetric._compute_portfolio_value_history`
        for details — uses the same approach.
        """
        portfolio_history = portfolio_history.sort_values("date")

        all_dates = pd.date_range(
            start=portfolio_history.index.min(), end=current_date, freq="D"
        )

        holdings_df = pd.DataFrame(
            index=all_dates, columns=nav_data.keys()
        ).fillna(0.0)

        for txn_date, row in portfolio_history.iterrows():
            if txn_date > current_date:
                continue
            fund = row["fund_name"]
            units = row["units"]
            holdings_df.loc[txn_date:, fund] += units

        portfolio_values = pd.Series(index=all_dates, dtype=float)
        for fund, nav_df in nav_data.items():
            nav_df = nav_df[nav_df.index <= current_date]
            holdings = holdings_df[fund]
            portfolio_values += holdings * nav_df["nav"]

        portfolio_values = portfolio_values.fillna(0.0)
        return portfolio_values

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

"""
Simulation engine for mutual fund backtesting.

The Simulator runs a day-by-day loop over historical NAV data, applying SIP
investments and strategy-driven rebalancing at configurable frequencies.
After the simulation completes, it calculates performance metrics.

Example::

    from mfsim.backtester import Simulator
    from mfsim.strategies import MomentumValueStrategy

    strategy = MomentumValueStrategy(
        frequency="semi-annually",
        metrics=["Total Return", "XIRR"],
        value_fund="Some Value Fund - Direct Plan",
        momentum_fund="Some Momentum Fund - Direct Plan",
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
    # results = {"TotalReturn": 0.45, "XIRR": 0.12, ...}
"""

import numpy as np
import pandas as pd

from mfsim.backtester.lot_tracker import LotTracker
from mfsim.metrics.metrics_collection import (
    AlphaMetric,
    InformationRatioMetric,
    MaximumDrawdownMetric,
    SharpeRatioMetric,
    SortinoRatioMetric,
    TaxAwareReturnMetric,
    TotalReturnMetric,
    TrackingErrorMetric,
    XIRRMetric,
)
from mfsim.strategies.base_strategy import BaseStrategy
from mfsim.utils.data_loader import MfApiDataLoader, get_lowerbound_date
from mfsim.utils.logger import setup_logger


class Simulator:
    """Orchestrates mutual fund backtesting simulations.

    The simulator iterates day-by-day through a date range, checking each date
    against the strategy's rebalancing schedule and SIP schedule. It maintains
    a complete transaction history and computes performance metrics at the end.

    Args:
        start_date: Simulation start date as ``'YYYY-MM-DD'`` string.
            Adjusted forward to the first available NAV date if needed.
        end_date: Simulation end date as ``'YYYY-MM-DD'`` string.
        initial_investment: Lump sum amount invested on ``start_date``.
        strategy: A :class:`~mfsim.strategies.base_strategy.BaseStrategy` instance
            that defines fund selection, allocation, and rebalancing logic.
        sip_amount: Amount to invest on each SIP date. Set to ``0`` to disable SIP.
            The strategy's ``update_sip_amount()`` hook can modify this dynamically.
        sip_frequency: How often to apply SIP — ``'daily'``, ``'weekly'`` (Mondays),
            or ``'monthly'`` (1st of month).
        data_loader: A :class:`~mfsim.utils.data_loader.BaseDataLoader` instance
            for fetching NAV data. Defaults to ``MfApiDataLoader`` which pulls
            live data from api.mfapi.in.

    Attributes:
        nav_data: Dict mapping fund names to DataFrames with ``date`` index
            and ``nav`` column. Loaded once during init.
        portfolio_history: List of transaction dicts, each with keys
            ``fund_name``, ``date``, ``units``, ``amount``.
        metrics_results: Dict of metric name to computed value, populated
            after ``run()`` completes.

    Note:
        NAV data from AMFI (used by the default ``MfApiDataLoader``) is already
        **net of expense ratio** — the TER is deducted daily by the fund house
        before publishing NAV. The simulator does not apply any additional
        expense ratio deduction. The ``expense_ratios`` dict is retained for
        informational/reporting purposes only.
    """

    def __init__(
        self,
        start_date,
        end_date,
        initial_investment,
        strategy: BaseStrategy,
        sip_amount=0,
        sip_frequency="monthly",
        data_loader=None,
        benchmark_fund=None,
        **kwargs,
    ):
        self.start_date = pd.to_datetime(start_date)
        self.end_date = pd.to_datetime(end_date)
        self.initial_investment = initial_investment
        self.strategy = strategy
        self.sip_amount = sip_amount
        self.sip_frequency = sip_frequency
        self.benchmark_fund = benchmark_fund
        self.logger = setup_logger()
        if data_loader is None:
            self.data_loader = MfApiDataLoader()
        else:
            from mfsim.utils.data_loader import BaseDataLoader

            assert isinstance(data_loader, BaseDataLoader), (
                f"data_loader must be an instance of BaseDataLoader, got {type(data_loader)}"
            )
            self.data_loader = data_loader
        self.fund_list = self.strategy.fund_list
        self.nav_data = self._load_all_nav_data()
        self.expense_ratios = self._load_expense_ratios()
        self.exit_loads = self._get_exit_load()
        self.start_date = get_lowerbound_date(self.nav_data[self.fund_list[0]], self.start_date)
        self.portfolio_history = []
        self.metrics_results = {}
        self.lot_tracker = LotTracker()
        self.total_stamp_duty = 0.0
        self._last_sip_period = None
        self._last_rebalance_period = None

        # Load benchmark NAV data if specified and not already in nav_data
        if self.benchmark_fund and self.benchmark_fund not in self.nav_data:
            benchmark_nav = self.data_loader.load_nav_data(self.benchmark_fund)
            benchmark_nav["date"] = pd.to_datetime(benchmark_nav["date"], format="%d-%m-%Y")
            benchmark_nav["nav"] = benchmark_nav["nav"].astype(float)
            benchmark_nav.set_index("date", inplace=True)
            self.nav_data[self.benchmark_fund] = benchmark_nav

    @property
    def current_portfolio(self):
        """Current holdings as ``{fund_name: total_units}``.

        Computed by summing all units (buys positive, sells negative) from
        ``portfolio_history`` grouped by fund name.

        Returns:
            Dict mapping each fund name to total units currently held.
        """
        df = pd.DataFrame.from_records(self.portfolio_history, index="date")
        df = df.drop(columns=["amount"])
        return df.groupby("fund_name")["units"].sum().to_dict()

    @property
    def portfolio_history_df(self):
        """Transaction history as a DataFrame.

        Returns:
            DataFrame indexed by ``date`` with columns ``fund_name``,
            ``units``, and ``amount``.
        """
        return pd.DataFrame.from_records(self.portfolio_history, index="date")

    @property
    def total_invested(self):
        """Total amount of money invested across all purchases.

        Returns:
            Sum of ``amount`` across all transactions. Sell orders have
            negative amounts, so this reflects net investment.
        """
        if not self.portfolio_history:
            return 0.0
        df = pd.DataFrame.from_records(self.portfolio_history)
        return df["amount"].sum()

    @property
    def lots(self):
        """All open lots across all funds.

        Returns:
            List of :class:`~mfsim.backtester.lot_tracker.Lot` instances
            that have remaining units.
        """
        return self.lot_tracker.get_all_lots()

    @property
    def realized_gains(self):
        """All realized gains from sells.

        Returns:
            List of :class:`~mfsim.backtester.lot_tracker.RealizedGain`
            records accumulated during the simulation.
        """
        return self.lot_tracker.realized_gains

    def get_portfolio_value(self, date=None):
        """Calculate portfolio market value at a given date.

        Multiplies each fund's held units by its NAV on the given date.

        Args:
            date: Date to value the portfolio at. Defaults to ``end_date``.
                Must be a date for which NAV data exists.

        Returns:
            Total portfolio value as a float. Returns ``0.0`` if no
            transactions have been made yet.
        """
        if date is None:
            date = self.end_date

        if not self.portfolio_history:
            return 0.0

        total_value = 0.0
        current_portfolio = self.current_portfolio

        for fund_name, units in current_portfolio.items():
            try:
                nav = self.nav_data[fund_name].loc[date]["nav"]
                fund_value = units * nav
                total_value += fund_value
            except KeyError:
                self.logger.warning(f"NAV data not available for {fund_name} on {date}")
                continue

        return total_value

    def _get_exit_load(self):
        """Load exit load percentages for each fund from the data loader.

        Returns:
            Dict mapping fund names to exit load as a decimal
            (e.g., ``0.01`` for 1%). Defaults to ``0.0`` on error.
        """
        exit_loads = {}
        for fund in self.fund_list:
            try:
                exit_loads[fund] = self.data_loader.get_exit_load(fund)
            except Exception as e:
                self.logger.error(f"Error loading exit load for {fund}: {e}")
                exit_loads[fund] = 0.0
        return exit_loads

    def _load_expense_ratios(self):
        """Load expense ratios for each fund from the data loader.

        These are stored for informational purposes only. Since NAV data
        from AMFI is already net of TER, the simulator does **not** apply
        any expense ratio deduction during the simulation.

        Returns:
            Dict mapping fund names to annual expense ratio as a decimal
            (e.g., ``0.005`` for 0.5%).
        """
        expense_ratios = {}
        for fund in self.fund_list:
            try:
                expense_ratios[fund] = self.data_loader.get_expense_ratio(fund)
            except Exception as e:
                self.logger.error(f"Error loading expense ratio for {fund}: {e}")
                expense_ratios[fund] = np.nan
        return expense_ratios

    def _load_all_nav_data(self):
        """Fetch and prepare NAV data for all funds in the strategy.

        For each fund in ``strategy.fund_list``, calls the data loader's
        ``load_nav_data()`` method, converts dates to datetime, NAVs to
        float, and sets date as the DataFrame index.

        Returns:
            Dict mapping fund names to DataFrames indexed by ``date``
            with a ``nav`` column (float).
        """
        nav_data = {}
        for fund in self.fund_list:
            nav_data[fund] = self.data_loader.load_nav_data(fund)
            nav_data[fund]["date"] = pd.to_datetime(nav_data[fund]["date"], format="%d-%m-%Y")
            nav_data[fund]["nav"] = nav_data[fund]["nav"].astype(float)
            nav_data[fund].set_index("date", inplace=True)
        return nav_data

    def calculate_units_for_amount(self, fund_name, date, amount):
        """Convert a rupee amount to fund units at the NAV on a given date.

        Args:
            fund_name: Name of the fund.
            date: Date to look up NAV for.
            amount: Rupee amount to convert.

        Returns:
            Number of units that ``amount`` buys at the fund's NAV on ``date``.

        Raises:
            ValueError: If NAV data is not available for ``fund_name`` on ``date``.
        """
        try:
            nav = self.nav_data[fund_name].loc[date]["nav"]
        except KeyError:
            raise ValueError(f"NAV data not available for {fund_name} on {date}")
        units = float(amount / nav)
        return units

    def make_purchase(self, fund_name, date, amount):
        """Record a fund purchase (or sale) in the portfolio history.

        Calculates units from ``amount`` using the fund's NAV on ``date``
        and appends the transaction to ``portfolio_history``.  Buys create
        a new :class:`~mfsim.backtester.lot_tracker.Lot` in the lot tracker;
        sells consume lots in FIFO order and record realized gains.

        Since July 2020, a stamp duty of 0.005% is levied on all mutual fund
        purchases in India. This is deducted from the buy amount before
        computing units.

        Args:
            fund_name: Name of the fund to buy/sell.
            date: Transaction date.
            amount: Rupee amount. Positive for buy, negative for sell.
        """
        # Apply stamp duty on purchases (0.005% since July 2020)
        stamp_duty = 0.0
        if amount > 0 and date >= pd.Timestamp("2020-07-01"):
            stamp_duty = amount * 0.00005
            amount = amount - stamp_duty  # Effective invested amount after stamp duty
            self.total_stamp_duty += stamp_duty

        units = self.calculate_units_for_amount(fund_name, date, amount)
        nav = self.nav_data[fund_name].loc[date]["nav"]

        self.portfolio_history.append(
            {
                "fund_name": fund_name,
                "date": date,
                "units": units,
                "amount": amount,
            }
        )

        # Track in lot system
        if amount > 0:
            self.lot_tracker.buy(fund_name, date, units, float(nav))
        elif amount < 0:
            self.lot_tracker.sell(fund_name, date, abs(units), float(nav))

        if stamp_duty > 0:
            self.logger.debug(f"Stamp duty of {stamp_duty:.2f} applied on {date.date()}")
        self.logger.info(f"Purchased {units} units of {fund_name} on {date.date()} for {amount}")

    def _initialize_portfolio(self):
        """Invest the initial lump sum on the start date.

        Calls ``strategy.allocate_money()`` to determine how to split the
        initial investment across funds, then records a purchase for each.
        """
        allocation = self.strategy.allocate_money(
            self.initial_investment, self.nav_data, self.start_date
        )

        for fund, amount in allocation.items():
            self.make_purchase(fund, self.start_date, amount)

    def _apply_sip(self, current_date):
        """Apply a Systematic Investment Plan installment.

        Distributes ``sip_amount`` across funds using the strategy's
        ``allocate_money()`` method and records purchases.

        Args:
            current_date: The date on which the SIP is applied.
        """
        if self.sip_amount > 0:
            allocation = self.strategy.allocate_money(self.sip_amount, self.nav_data, current_date)
            for fund, amount in allocation.items():
                self.make_purchase(fund, current_date, amount)

            self.logger.info(f"Applied SIP of {self.sip_amount} on {current_date.date()}")

    def run(self):
        """Execute the full backtest simulation.

        Performs these steps in order:

        1. Invests ``initial_investment`` via ``strategy.allocate_money()``.
        2. Iterates day-by-day from ``start_date`` to ``end_date``.
        3. On each trading day (where NAV data exists):
           - Calls ``strategy.update_sip_amount()`` if SIP is active.
           - Applies SIP if it's a SIP date.
           - Calls ``strategy.rebalance()`` if it's a rebalance date.
        4. Computes all metrics listed in ``strategy.metrics``.

        Returns:
            Dict mapping metric names to their computed values.
            Example: ``{"TotalReturn": 0.45, "XIRR": 0.12}``
        """
        self._initialize_portfolio()

        all_dates = pd.date_range(start=self.start_date, end=self.end_date, freq="D")

        for date in all_dates:
            if date not in self.nav_data[self.fund_list[0]].index:
                continue

            # Let the strategy update the SIP amount if applicable
            if self.sip_amount > 0:
                self.sip_amount = self.strategy.update_sip_amount(date, self.sip_amount)

            # Apply SIP
            if self.sip_amount > 0:
                if self._is_sip_date(date):
                    self._apply_sip(date)

            # Rebalance if needed
            if self._is_rebalance_date(date):
                self.logger.info(f"Rebalancing on {date.date()}")
                current_portfolio = self.current_portfolio
                orders = self.strategy.rebalance(current_portfolio, self.nav_data, date)
                for order in orders:
                    fund_name = order["fund_name"]
                    amount = order["amount"]
                    self.make_purchase(fund_name, date, amount)

        # After simulation, calculate metrics
        self._calculate_metrics()

        return self.metrics_results

    def _get_period_key(self, date, freq):
        """Return a hashable key identifying the scheduling period for a date.

        Used by :meth:`_is_sip_date` and :meth:`_is_rebalance_date` to
        determine whether a new scheduling period has started.

        Args:
            date: The date to compute a period key for.
            freq: Frequency string (case-insensitive). One of ``'daily'``,
                ``'weekly'``, ``'monthly'``, ``'quarterly'``,
                ``'semi-annually'``, ``'annually'``.

        Returns:
            A hashable tuple (or date) uniquely identifying the period,
            or ``None`` if *freq* is not recognised.
        """
        freq = freq.lower()
        if freq == "daily":
            return date
        elif freq == "weekly":
            iso = date.isocalendar()
            return (iso[0], iso[1])
        elif freq == "monthly":
            return (date.year, date.month)
        elif freq == "quarterly":
            return (date.year, (date.month - 1) // 3)
        elif freq == "semi-annually":
            return (date.year, 0 if date.month <= 6 else 1)
        elif freq == "annually":
            return (date.year,)
        return None

    def _is_rebalance_date(self, date):
        """Check whether the given date is a rebalance trigger.

        Uses period-based tracking so that if the nominal trigger date
        (e.g. the 1st of the month) falls on a non-trading day, the
        rebalance fires on the first available trading day of that period
        instead of being silently skipped.

        Supported frequencies (from ``strategy.frequency``):

        - ``'daily'``: every trading day
        - ``'weekly'``: first trading day of each ISO week
        - ``'monthly'``: first trading day of each month
        - ``'quarterly'``: first trading day of each quarter
        - ``'semi-annually'``: first trading day of each half-year
        - ``'annually'``: first trading day of each year

        Args:
            date: The date to check.

        Returns:
            ``True`` if rebalancing should occur on this date.
        """
        freq = self.strategy.frequency.lower()
        if freq == "daily":
            return True

        period = self._get_period_key(date, freq)
        if period is None or period == self._last_rebalance_period:
            return False

        self._last_rebalance_period = period
        return True

    def _is_sip_date(self, date):
        """Check whether the given date is an SIP trigger.

        Uses period-based tracking so that if the nominal SIP date falls on
        a non-trading day (holiday / weekend), the SIP fires on the first
        available trading day of that period instead of being skipped.

        Supported frequencies (from ``sip_frequency``):

        - ``'daily'``: every trading day
        - ``'weekly'``: first trading day of each ISO week
        - ``'monthly'``: first trading day of each month

        Args:
            date: The date to check.

        Returns:
            ``True`` if SIP should be applied on this date.
        """
        freq = self.sip_frequency.lower()
        if freq == "daily":
            return True

        period = self._get_period_key(date, freq)
        if period is None or period == self._last_sip_period:
            return False

        self._last_sip_period = period
        return True

    def _calculate_metrics(self):
        """Compute all metrics specified in the strategy.

        Matches metric names (case-insensitive) from ``strategy.metrics``
        to metric classes and calls each one's ``calculate()`` method.

        Supported metric names:
            - ``'total return'`` → :class:`TotalReturnMetric`
            - ``'sharpe ratio'`` → :class:`SharpeRatioMetric`
            - ``'maximum drawdown'`` → :class:`MaximumDrawdownMetric`
            - ``'sortino ratio'`` → :class:`SortinoRatioMetric`
            - ``'xirr'`` → :class:`XIRRMetric`
            - ``'alpha'`` → :class:`AlphaMetric` (requires benchmark_fund)
            - ``'tracking error'`` → :class:`TrackingErrorMetric` (requires benchmark_fund)
            - ``'information ratio'`` → :class:`InformationRatioMetric` (requires benchmark_fund)
            - ``'tax-aware return'`` → :class:`TaxAwareReturnMetric`
        """
        metrics_instances = []
        for metric_name in self.strategy.metrics:
            if metric_name.lower() == "total return":
                metrics_instances.append(TotalReturnMetric())
            elif metric_name.lower() == "sharpe ratio":
                metrics_instances.append(SharpeRatioMetric(frequency="daily"))
            elif metric_name.lower() == "maximum drawdown":
                metrics_instances.append(MaximumDrawdownMetric())
            elif metric_name.lower() == "sortino ratio":
                metrics_instances.append(SortinoRatioMetric(frequency=self.strategy.frequency))
            elif metric_name.lower() == "xirr":
                metrics_instances.append(XIRRMetric())
            elif metric_name.lower() == "alpha":
                if self.benchmark_fund:
                    metrics_instances.append(AlphaMetric(benchmark_fund=self.benchmark_fund))
                else:
                    self.logger.warning("Alpha metric requires benchmark_fund parameter")
            elif metric_name.lower() == "tracking error":
                if self.benchmark_fund:
                    metrics_instances.append(
                        TrackingErrorMetric(benchmark_fund=self.benchmark_fund)
                    )
                else:
                    self.logger.warning("Tracking Error metric requires benchmark_fund parameter")
            elif metric_name.lower() == "information ratio":
                if self.benchmark_fund:
                    metrics_instances.append(
                        InformationRatioMetric(benchmark_fund=self.benchmark_fund)
                    )
                else:
                    self.logger.warning(
                        "Information Ratio metric requires benchmark_fund parameter"
                    )
            elif metric_name.lower() == "tax-aware return":
                metrics_instances.append(
                    TaxAwareReturnMetric(
                        lot_tracker=self.lot_tracker,
                        lots_at_end=self.lots,
                    )
                )
            else:
                self.logger.warning(f"Unknown metric: {metric_name}")

        for metric in metrics_instances:
            metric_name = metric.__class__.__name__.replace("Metric", "").replace("_", " ")
            self.metrics_results[metric_name] = metric.calculate(
                self.portfolio_history_df,
                self.current_portfolio,
                self.end_date,
                self.nav_data,
            )
            self.logger.info(f"{metric_name}: {self.metrics_results[metric_name]}")

    def get_portfolio_history(self):
        """Return the raw transaction history list.

        Returns:
            List of dicts, each with keys ``fund_name``, ``date``,
            ``units``, ``amount``.
        """
        return self.portfolio_history

    def get_metrics(self):
        """Return computed metrics from the last simulation run.

        Returns:
            Dict mapping metric names to values. Empty if ``run()``
            hasn't been called yet.
        """
        return self.metrics_results

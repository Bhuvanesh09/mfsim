"""FIFO lot-level transaction tracking for mutual fund portfolios.

Each purchase creates a :class:`Lot` that records the fund, date, units, and
cost basis.  When units are sold, the :class:`LotTracker` consumes lots in
FIFO (first-in-first-out) order and emits :class:`RealizedGain` records that
capture the per-lot profit/loss and holding period.

Example::

    from mfsim.backtester.lot_tracker import LotTracker

    tracker = LotTracker()
    tracker.buy("Fund A", date(2023, 1, 1), units=100, price_per_unit=10.0)
    tracker.buy("Fund A", date(2023, 6, 1), units=50, price_per_unit=12.0)

    gains = tracker.sell("Fund A", date(2024, 1, 1), units=120, price_per_unit=15.0)
    # First 100 units sold from the Jan lot, then 20 from the Jun lot (FIFO).
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Lot:
    """A single purchase lot of a mutual fund.

    Attributes:
        fund_name: Name of the fund this lot belongs to.
        purchase_date: Date when the units were purchased.
        units: Number of units remaining in this lot (decremented on sells).
        cost_per_unit: NAV at the time of purchase.
        lot_id: Auto-generated 8-character identifier.
    """

    fund_name: str
    purchase_date: datetime
    units: float
    cost_per_unit: float
    lot_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])


@dataclass
class RealizedGain:
    """Record of a realized gain/loss from selling units out of a specific lot.

    Attributes:
        lot_id: Identifier of the lot that was (partially) sold.
        fund_name: Name of the fund.
        purchase_date: Date when the original lot was purchased.
        sell_date: Date when the units were sold.
        units: Number of units sold from this lot.
        cost_per_unit: NAV at the time of original purchase.
        sell_price_per_unit: NAV at the time of sale.
        gain: ``(sell_price_per_unit - cost_per_unit) * units``.
        holding_days: Calendar days between purchase and sale.
    """

    lot_id: str
    fund_name: str
    purchase_date: datetime
    sell_date: datetime
    units: float
    cost_per_unit: float
    sell_price_per_unit: float
    gain: float  # (sell_price - cost) * units
    holding_days: int


class LotTracker:
    """Tracks fund purchases as individual lots and consumes them FIFO on sells.

    Open lots are stored per fund in insertion order so that the oldest lot is
    always consumed first when a sell occurs.  All realized gains are accumulated
    and available via :attr:`realized_gains`.
    """

    def __init__(self):
        self.lots: dict[str, list[Lot]] = {}  # fund_name -> open lots (FIFO order)
        self.realized_gains: list[RealizedGain] = []

    def buy(self, fund_name: str, date: datetime, units: float, price_per_unit: float) -> Lot:
        """Create a new lot for a purchase.

        Args:
            fund_name: Name of the fund being purchased.
            date: Purchase date.
            units: Number of units acquired.
            price_per_unit: NAV on the purchase date.

        Returns:
            The newly created :class:`Lot`.
        """
        lot = Lot(
            fund_name=fund_name,
            purchase_date=date,
            units=units,
            cost_per_unit=price_per_unit,
        )
        if fund_name not in self.lots:
            self.lots[fund_name] = []
        self.lots[fund_name].append(lot)
        return lot

    def sell(
        self, fund_name: str, date: datetime, units: float, price_per_unit: float
    ) -> list[RealizedGain]:
        """Sell units from the fund using FIFO order.

        Consumes the oldest lots first.  If a lot has fewer units than needed,
        it is fully consumed and the remainder is taken from the next lot.

        Args:
            fund_name: Name of the fund being sold.
            date: Sale date.
            units: Number of units to sell (always treated as a positive quantity).
            price_per_unit: NAV on the sale date.

        Returns:
            List of :class:`RealizedGain` records, one per lot consumed.

        Raises:
            ValueError: If no open lots exist for *fund_name*.
        """
        if fund_name not in self.lots or not self.lots[fund_name]:
            raise ValueError(f"No lots available to sell for {fund_name}")

        requested_units = abs(units)
        available_units = self.get_holdings(fund_name)
        if requested_units > available_units + 1e-10:
            raise ValueError(
                f"Cannot sell {requested_units} units of {fund_name}; only {available_units} available"
            )

        remaining = requested_units  # units to sell
        gains: list[RealizedGain] = []

        while remaining > 1e-10 and self.lots[fund_name]:
            lot = self.lots[fund_name][0]
            sell_units = min(lot.units, remaining)

            gain = RealizedGain(
                lot_id=lot.lot_id,
                fund_name=fund_name,
                purchase_date=lot.purchase_date,
                sell_date=date,
                units=sell_units,
                cost_per_unit=lot.cost_per_unit,
                sell_price_per_unit=price_per_unit,
                gain=(price_per_unit - lot.cost_per_unit) * sell_units,
                holding_days=(date - lot.purchase_date).days,
            )
            gains.append(gain)

            lot.units -= sell_units
            remaining -= sell_units

            if lot.units < 1e-10:
                self.lots[fund_name].pop(0)

        self.realized_gains.extend(gains)
        return gains

    def get_holdings(self, fund_name: str) -> float:
        """Total units held in open lots for a fund.

        Args:
            fund_name: Name of the fund.

        Returns:
            Sum of units across all open lots for the fund.
        """
        return sum(lot.units for lot in self.lots.get(fund_name, []))

    def get_all_holdings(self) -> dict[str, float]:
        """All fund holdings as ``{fund_name: total_units}``.

        Returns:
            Dict mapping each fund name to total open units.
        """
        return {fund: self.get_holdings(fund) for fund in self.lots}

    def get_lots(self, fund_name: str) -> list[Lot]:
        """Get all open lots for a fund.

        Args:
            fund_name: Name of the fund.

        Returns:
            Shallow copy of the open lot list for the fund.
        """
        return list(self.lots.get(fund_name, []))

    def get_all_lots(self) -> list[Lot]:
        """Get all open lots across all funds.

        Returns:
            Flat list of every open :class:`Lot` across every fund.
        """
        return [lot for lots in self.lots.values() for lot in lots]

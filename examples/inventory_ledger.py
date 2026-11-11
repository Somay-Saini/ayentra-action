from __future__ import annotations

from ayentra.contracts import domain, invariant


@invariant(
    "self.available >= 0 and self.reserved >= 0 and self.available + self.reserved == self.initial_total",
    description="Inventory conservation law: available and reserved units must be non-negative and sum to initial_total",
)
class InventoryLedger:
    def __init__(self, initial_total: int = 100) -> None:
        self.initial_total = initial_total
        self.available = initial_total
        self.reserved = 0

    @domain(units=(-50, 200))
    def reserve(self, units: int) -> None:
        if units <= self.available:
            self.available -= units
            self.reserved += units

    @domain(units=(-50, 200))
    def release_reservation(self, units: int) -> None:
        if units <= self.reserved:
            self.reserved -= units
            self.available += units

from __future__ import annotations

from ayentra.contracts import domain, invariant


@invariant(
    "0 <= self.allocated <= self.capacity",
    description="Allocated compute units must never be negative or exceed cluster capacity",
    check_concurrency=True,
)
class ResourceScheduler:
    def __init__(self, capacity: int = 10) -> None:
        self.capacity = capacity
        self.allocated = 0

    @domain(amount=(-20, 20))
    def allocate(self, amount: int) -> bool:
        if self.allocated + amount <= self.capacity:
            self.allocated += amount
            return True
        return False

    @domain(amount=(-20, 20))
    def release(self, amount: int) -> bool:
        if self.allocated - amount >= 0:
            self.allocated -= amount
            return True
        return False

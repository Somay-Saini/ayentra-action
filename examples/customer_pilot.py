from __future__ import annotations

from dataclasses import dataclass, field
from ayentra.contracts import domain, invariant


@invariant(
    "self.available >= 0 and self.escrow >= 0 and self.available + self.escrow == self.total_funds",
    description="Ledger conservation law: available and escrow funds must be non-negative and sum to total funds",
)
@dataclass
class EnterprisePaymentLedger:
    total_funds: int = 1000
    available: int = 1000
    escrow: int = 0
    settled_tx_ids: set[str] = field(default_factory=set)

    @domain(amount=(-100, 2000), tx_id=('tx_1', 'tx_2', 'tx_3'))
    def hold_in_escrow(self, amount: int, tx_id: str) -> bool:
        if tx_id in self.settled_tx_ids:
            return True
        if amount <= self.available:
            self.available -= amount
            self.escrow += amount
            self.settled_tx_ids.add(tx_id)
            return True
        return False

    @domain(amount=(-100, 2000))
    def release_escrow(self, amount: int) -> bool:
        if amount <= self.escrow:
            self.escrow -= amount
            self.available += amount
            return True
        return False

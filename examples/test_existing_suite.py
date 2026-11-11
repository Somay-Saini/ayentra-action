from __future__ import annotations

from examples.customer_pilot import EnterprisePaymentLedger
from examples.data_parser import parse_telemetry_payload
from examples.inventory_ledger import InventoryLedger
from examples.scheduler_race import ResourceScheduler


def test_scheduler_standard_allocation() -> None:
    scheduler = ResourceScheduler(capacity=10)
    assert scheduler.allocate(4) is True
    assert scheduler.allocate(5) is True
    assert scheduler.allocated == 9
    assert scheduler.allocate(3) is False
    assert scheduler.release(4) is True
    assert scheduler.allocated == 5


def test_inventory_ledger_happy_path() -> None:
    ledger = InventoryLedger(initial_total=100)
    ledger.reserve(30)
    assert ledger.available == 70
    assert ledger.reserved == 30
    ledger.release_reservation(10)
    assert ledger.available == 80
    assert ledger.reserved == 20


def test_data_parser_valid_metrics() -> None:
    parsed = parse_telemetry_payload("cpu=42.5,mem=78.0,latency=12.25")
    assert parsed == {"cpu": 42.5, "mem": 78.0, "latency": 12.25}
    assert parse_telemetry_payload("") == {}


def test_customer_pilot_payment_ledger_happy_path() -> None:
    ledger = EnterprisePaymentLedger(total_funds=1000)
    assert ledger.hold_in_escrow(300, "tx_1") is True
    assert ledger.available == 700
    assert ledger.escrow == 300
    # idempotent transaction check
    assert ledger.hold_in_escrow(300, "tx_1") is True
    assert ledger.available == 700
    assert ledger.escrow == 300
    assert ledger.release_escrow(100) is True
    assert ledger.available == 800
    assert ledger.escrow == 200

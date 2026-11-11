from __future__ import annotations

import json
import sys
from pathlib import Path
import pytest

from ayentra.cli import build_parser, main

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_pilot_init_with_and_without_ci(tmp_path: Path) -> None:
    repo_no_ci = tmp_path / "customer_repo_basic"
    src_a = repo_no_ci / "src"
    src_a.mkdir(parents=True)
    (src_a / "app.py").write_text("def ping() -> str:\n    return 'pong'\n", encoding="utf-8")

    rc_a = main(["init", "--path", str(repo_no_ci)])
    assert rc_a == 0

    toml_a = repo_no_ci / "ayentra.toml"
    assert toml_a.exists()
    toml_text_a = toml_a.read_text(encoding="utf-8")
    assert "\u2014" not in toml_text_a and "\u2013" not in toml_text_a
    assert 'name = "customer_repo_basic"' in toml_text_a

    ci_wf_a = repo_no_ci / ".github" / "workflows" / "ayentra.yml"
    assert not ci_wf_a.exists()

    repo_ci = tmp_path / "customer_repo_ci"
    src_b = repo_ci / "services"
    src_b.mkdir(parents=True)
    (src_b / "order.py").write_text("def checkout() -> bool:\n    return True\n", encoding="utf-8")

    rc_b = main(["init", "--path", str(repo_ci), "--ci"])
    assert rc_b == 0

    toml_b = repo_ci / "ayentra.toml"
    assert toml_b.exists()
    toml_text_b = toml_b.read_text(encoding="utf-8")
    assert "\u2014" not in toml_text_b and "\u2013" not in toml_text_b

    ci_wf_b = repo_ci / ".github" / "workflows" / "ayentra.yml"
    assert ci_wf_b.exists()
    ci_text_b = ci_wf_b.read_text(encoding="utf-8")
    assert "\u2014" not in ci_text_b and "\u2013" not in ci_text_b
    assert "ayentra check . --ci" in ci_text_b


def test_customer_pilot_end_to_end_adoption_lifecycle(tmp_path: Path) -> None:
    project_dir = tmp_path / "acme_fintech"
    services_dir = project_dir / "services"
    services_dir.mkdir(parents=True)

    ledger_file = services_dir / "ledger.py"
    original_code = (
        "from __future__ import annotations\n"
        "from dataclasses import dataclass\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.balance >= 0')\n"
        "@dataclass\n"
        "class LedgerAccount:\n"
        "    balance: int = 100\n\n"
        "    def debit(self, amount: int) -> bool:\n"
        "        self.balance -= amount\n"
        "        return True\n"
    )
    ledger_file.write_text(original_code, encoding="utf-8")

    rc_init = main(["init", "--path", str(project_dir), "--ci"])
    assert rc_init == 0
    assert (project_dir / "ayentra.toml").exists()
    assert (project_dir / ".github" / "workflows" / "ayentra.yml").exists()

    receipt_json = project_dir / "ayentra-receipt.json"
    rc_check1 = main([
        "check",
        str(ledger_file),
        "--json-out",
        str(receipt_json),
        "--seed",
        "42",
        "--max-examples",
        "30",
    ])
    assert rc_check1 == 1
    assert receipt_json.exists()

    receipt_data = json.loads(receipt_json.read_text(encoding="utf-8"))
    assert receipt_data["failed_invariants_count"] == 1
    assert len(receipt_data["violations"]) == 1
    violation = receipt_data["violations"][0]
    assert "LedgerAccount" in violation["target"]
    assert "call_sequence" in violation["counterexample"]
    call0 = violation["counterexample"]["call_sequence"][0]
    assert call0["method"] == "debit"
    assert call0["args"]["amount"] > 100

    assert len(receipt_data["candidate_patches"]) == 1
    patch_info = receipt_data["candidate_patches"][0]
    assert patch_info["status"] == "VERIFIED CANDIDATE FIX"
    assert patch_info["counterexample_check"] == "PASS"
    assert patch_info["invariant_sweep_check"] == "PASS"
    assert patch_info["regression_suite_check"] == "PASS"

    receipt_raw = receipt_json.read_text(encoding="utf-8")
    assert "\u2014" not in receipt_raw and "\u2013" not in receipt_raw

    rc_verify = main([
        "verify-patch",
        str(ledger_file),
        "--seed",
        "42",
        "--max-examples",
        "30",
    ])
    assert rc_verify == 0

    rc_dry_run = main([
        "apply-patch",
        str(ledger_file),
        "--seed",
        "42",
        "--max-examples",
        "30",
    ])
    assert rc_dry_run == 0
    assert ledger_file.read_text(encoding="utf-8") == original_code

    rc_apply = main([
        "apply-patch",
        str(ledger_file),
        "--seed",
        "42",
        "--max-examples",
        "30",
        "--yes",
    ])
    assert rc_apply == 0

    patched_code = ledger_file.read_text(encoding="utf-8")
    assert patched_code != original_code
    assert "amount > self.balance" in patched_code
    assert "raise ValueError" in patched_code
    assert "\u2014" not in patched_code and "\u2013" not in patched_code

    rc_check2 = main([
        "check",
        str(ledger_file),
        "--seed",
        "42",
        "--max-examples",
        "30",
    ])
    assert rc_check2 == 0


def test_customer_pilot_pr_mock_and_ci_diagnostics(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service_file = tmp_path / "token_bucket.py"
    service_file.write_text(
        "from __future__ import annotations\n"
        "from dataclasses import dataclass\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.tokens >= 0')\n"
        "@dataclass\n"
        "class RateLimiter:\n"
        "    tokens: int = 50\n\n"
        "    def consume(self, count: int) -> bool:\n"
        "        self.tokens -= count\n"
        "        return True\n",
        encoding="utf-8",
    )

    rc_pr = main(["pr-mock", str(service_file), "--max-examples", "30", "--seed", "42"])
    assert rc_pr == 0

    captured = capsys.readouterr()
    pr_out = captured.out
    assert "## Ayentra PR Bot: Invariant Verification Gate FAILED" in pr_out
    assert "Plain-English Bug:" in pr_out
    assert "Business Risk:" in pr_out
    assert "1-Click Merge Fix:" in pr_out
    assert "Interactive Diff Preview (Before vs After)" in pr_out
    assert "```diff" in pr_out
    assert "\u2014" not in pr_out and "\u2013" not in pr_out


def test_enterprise_customer_pilot_scenario_check_and_pr_mock(
    capsys: pytest.CaptureFixture[str],
) -> None:
    pilot_file = Path("C:/Users/Somay/Desktop/idea1/examples/customer_pilot.py")
    assert pilot_file.exists(), "examples/customer_pilot.py must exist"

    # 1. ayentra check --summary
    rc_check = main(["check", str(pilot_file), "--summary", "--max-examples", "20", "--seed", "42"])
    assert rc_check == 1

    captured_check = capsys.readouterr()
    check_out = captured_check.out
    assert "EnterprisePaymentLedger" in check_out
    assert "Financial balance corruption" in check_out
    assert "ledger drift" in check_out
    assert "ayentra apply-patch" in check_out
    assert "\u2014" not in check_out and "\u2013" not in check_out

    # 2. ayentra pr-mock
    rc_pr = main(["pr-mock", str(pilot_file), "--max-examples", "20", "--seed", "42"])
    assert rc_pr == 0

    captured_pr = capsys.readouterr()
    pr_out = captured_pr.out
    assert "## Ayentra PR Bot: Invariant Verification Gate FAILED" in pr_out
    assert "EnterprisePaymentLedger" in pr_out
    assert "Financial balance corruption" in pr_out
    assert "ledger drift" in pr_out
    assert "1-Click Merge Fix:" in pr_out
    assert "```diff" in pr_out
    assert "\u2014" not in pr_out and "\u2013" not in pr_out


def test_customer_pilot_negative_balances_and_boundary_guards(tmp_path: Path) -> None:
    from examples.customer_pilot import EnterprisePaymentLedger

    ledger = EnterprisePaymentLedger(total_funds=1000, available=1000, escrow=0)
    # Negative amount hold creates negative escrow and excess available funds
    ledger.hold_in_escrow(-50, "tx_neg")
    assert ledger.available == 1050
    assert ledger.escrow == -50
    assert ledger.escrow < 0

    pilot_file = Path(r"C:\Users\Somay\Desktop\idea1\examples\customer_pilot.py")
    receipt_out = tmp_path / "negative_balance_receipt.json"
    rc = main(["check", str(pilot_file), "--json-out", str(receipt_out), "--seed", "42", "--max-examples", "25"])
    assert rc == 1
    assert receipt_out.exists()

    receipt_data = json.loads(receipt_out.read_text(encoding="utf-8"))
    assert receipt_data["failed_invariants_count"] >= 1
    violation = receipt_data["violations"][0]
    call_seq = violation["counterexample"].get("call_sequence", [])
    assert len(call_seq) >= 1
    assert any(c["args"].get("amount", 0) < 0 for c in call_seq)


def test_customer_pilot_currency_conversion_and_zero_exchange_rates(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fx_target = tmp_path / "currency_service.py"
    fx_target.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant, domain\n\n"
        "@domain(amount_cents=(-50, 1000), exchange_rate=(0.0, 5.0))\n"
        "@invariant('result >= 0', description='Converted currency must be non-negative')\n"
        "def convert_currency(amount_cents: int, exchange_rate: float) -> int:\n"
        "    if exchange_rate == 0.0:\n"
        "        return -1\n"
        "    return int(amount_cents * exchange_rate)\n\n"
        "@domain(source_units=(1, 500), rate=(0.0, 10.0))\n"
        "@invariant('result > 0', description='Exchange result must be positive')\n"
        "def exchange_rate_division(source_units: int, rate: float) -> float:\n"
        "    if rate == 0.0:\n"
        "        return 0.0\n"
        "    return source_units / rate\n",
        encoding="utf-8",
    )

    rc_check = main(["check", str(fx_target), "--max-examples", "25", "--seed", "42"])
    assert rc_check == 1

    rc_pr = main(["pr-mock", str(fx_target), "--max-examples", "25", "--seed", "42"])
    assert rc_pr == 0

    captured = capsys.readouterr()
    pr_out = captured.out
    assert "## Ayentra PR Bot: Invariant Verification Gate FAILED" in pr_out
    assert "convert_currency" in pr_out or "exchange_rate_division" in pr_out
    assert "\u2014" not in pr_out and "\u2013" not in pr_out


def test_customer_pilot_high_concurrency_race_under_barrier_delay() -> None:
    from ayentra.concurrency import InvariantSpec, _run_single_interleaving
    from examples.customer_pilot import EnterprisePaymentLedger

    inv = InvariantSpec(
        expression="self.available >= 0 and self.escrow >= 0 and self.available + self.escrow == self.total_funds",
        target_name="EnterprisePaymentLedger",
        kind="class",
        lineno=10,
        filepath=r"C:\Users\Somay\Desktop\idea1\examples\customer_pilot.py",
        description="conservation",
        check_concurrency=True,
    )

    res = _run_single_interleaving(
        EnterprisePaymentLedger,
        "hold_in_escrow",
        EnterprisePaymentLedger.hold_in_escrow,
        (600, "tx_1"),
        "hold_in_escrow",
        EnterprisePaymentLedger.hold_in_escrow,
        (600, "tx_2"),
        invariants=[inv],
        target_file=r"C:\Users\Somay\Desktop\idea1\examples\customer_pilot.py",
        seed_val=42,
        schedules_run=1,
    )

    assert res is not None, "High-concurrency race interleaving should detect double-spend"
    assert res.state_after["available"] == -200, "Double-spend must drive available balance negative"
    assert res.state_after["escrow"] == 1200, "Escrow must exceed total funds after race condition"
    assert len(res.trace_steps) > 0, "Trace steps should record execution order"
    assert len(res.thread_calls) == 2


def test_standalone_wheel_package_contents_and_static_assets(tmp_path: Path) -> None:
    import zipfile

    whl_path = Path(r"C:\Users\Somay\Desktop\idea1\dist\ayentra-0.1.0-py3-none-any.whl")
    assert whl_path.is_file(), "Built standalone wheel must exist in dist/"
    assert whl_path.stat().st_size > 10000, "Wheel archive size should be substantial"

    with zipfile.ZipFile(whl_path, "r") as z:
        names = set(z.namelist())

        required_modules = [
            "ayentra/__init__.py",
            "ayentra/cli.py",
            "ayentra/engine.py",
            "ayentra/contracts.py",
            "ayentra/concurrency.py",
            "ayentra/repair.py",
            "ayentra/regression.py",
            "ayentra/dogfood.py",
            "ayentra/studio.py",
        ]
        for mod in required_modules:
            assert mod in names, f"Required module {mod} missing from wheel package"

        required_assets = [
            "ayentra/site/index.html",
            "ayentra/site/styles.css",
            "ayentra/site/app.js",
        ]
        for asset in required_assets:
            assert asset in names, f"Required static asset {asset} missing from wheel package"

        assert "ayentra-0.1.0.dist-info/METADATA" in names
        assert "ayentra-0.1.0.dist-info/entry_points.txt" in names

        entry_points = z.read("ayentra-0.1.0.dist-info/entry_points.txt").decode("utf-8")
        assert "ayentra = ayentra.cli:main" in entry_points

        html_bytes = z.read("ayentra/site/index.html")
        assert len(html_bytes) > 1000
        html_str = html_bytes.decode("utf-8")
        assert "\u2014" not in html_str and "\u2013" not in html_str

        # Unpack to temporary isolated directory and verify clean standalone structure
        unpack_dir = tmp_path / "wheel_unpacked"
        z.extractall(unpack_dir)
        assert (unpack_dir / "ayentra" / "site" / "index.html").is_file()
        assert (unpack_dir / "ayentra" / "cli.py").is_file()


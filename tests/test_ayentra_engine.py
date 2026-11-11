from __future__ import annotations

import json
from pathlib import Path

from ayentra.ast_analyzer import analyze_source
from ayentra.cli import main
from ayentra.contracts import load_toml_invariants
import uuid
from hypothesis import given, settings
from ayentra.engine import (
    _rehydrate_args,
    _strategy_for_annotation,
    replay_counterexample,
    run_verification_engine,
)
from ayentra.report import compute_file_sha256
from ayentra.studio import execute_full_check

ROOT = Path(__file__).resolve().parents[1]


def test_scheduler_race_detected_and_verified() -> None:
    target = ROOT / "examples" / "scheduler_race.py"
    sha_before = compute_file_sha256(target)

    report, engine_res, patches = execute_full_check(target, seed_val=42, max_examples=80)

    assert len(engine_res.violations) == 1
    assert report.failed_invariants_count == 1
    assert len(patches) == 1
    p = patches[0]
    assert p.counterexample_passed is True
    assert p.invariant_sweep_passed is True
    assert p.regression_result.passed is True
    assert p.status_label == "VERIFIED CANDIDATE FIX"
    assert compute_file_sha256(target) == sha_before


def test_inventory_ledger_detected_and_verified() -> None:
    target = ROOT / "examples" / "inventory_ledger.py"
    sha_before = compute_file_sha256(target)

    report, engine_res, patches = execute_full_check(target, seed_val=42, max_examples=80)

    assert len(engine_res.violations) == 1
    assert report.failed_invariants_count == 1
    assert len(patches) == 1
    p = patches[0]
    assert p.counterexample_passed is True
    assert p.invariant_sweep_passed is True
    assert p.regression_result.passed is True
    assert p.status_label == "VERIFIED CANDIDATE FIX"
    assert compute_file_sha256(target) == sha_before


def test_data_parser_detected_and_verified() -> None:
    target = ROOT / "examples" / "data_parser.py"
    sha_before = compute_file_sha256(target)

    report, engine_res, patches = execute_full_check(target, seed_val=42, max_examples=80)

    assert len(engine_res.violations) == 1
    assert report.failed_invariants_count == 1
    assert len(patches) == 1
    p = patches[0]
    assert p.counterexample_passed is True
    assert p.invariant_sweep_passed is True
    assert p.regression_result.passed is True
    assert p.status_label == "VERIFIED CANDIDATE FIX"
    assert compute_file_sha256(target) == sha_before


def test_ast_candidate_suggestions_labeled() -> None:
    target = ROOT / "examples" / "inventory_ledger.py"
    res = analyze_source(target)
    assert len(res.suggestions) > 0
    for s in res.suggestions:
        assert s.label == "Candidate Suggestion (Requires Developer Approval)"


def test_division_by_zero_guard_synthesis_verified(tmp_path: Path) -> None:
    target = tmp_path / "rate_calc.py"
    target.write_text(
        "from __future__ import annotations\n"
        "import math\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('math.isfinite(result)')\n"
        "def compute_unit_rate(total: int, count: int) -> float:\n"
        "    return total / count\n",
        encoding="utf-8",
    )

    report, engine_res, patches = execute_full_check(target, seed_val=42, max_examples=80)

    assert len(engine_res.violations) == 1
    assert report.failed_invariants_count == 1
    assert engine_res.violations[0].counterexample["arguments"]["count"] == 0
    assert len(patches) == 1
    p = patches[0]
    assert "if count == 0:" in p.patched_source
    assert "raise ValueError('count must be non-zero')" in p.patched_source
    assert p.counterexample_passed is True
    assert p.invariant_sweep_passed is True
    assert p.regression_result.passed is True
    assert p.status_label == "VERIFIED CANDIDATE FIX"


def test_sequence_boundary_and_off_by_one_guard_verified(tmp_path: Path) -> None:
    target = tmp_path / "seq_lookup.py"
    target.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('len(result) == 1')\n"
        "def pick_next_char(token: str, idx: int) -> str:\n"
        "    return token[idx + 1]\n",
        encoding="utf-8",
    )

    report, engine_res, patches = execute_full_check(target, seed_val=42, max_examples=80)

    assert len(engine_res.violations) == 1
    assert len(patches) == 1
    p = patches[0]
    assert p.counterexample_passed is True
    assert p.invariant_sweep_passed is True
    assert p.regression_result.passed is True
    assert p.status_label == "VERIFIED CANDIDATE FIX"


def test_toml_contract_discovery_and_verification(tmp_path: Path) -> None:
    target = tmp_path / "billing_calc.py"
    target.write_text(
        "from __future__ import annotations\n\n"
        "def compute_unit_cost(total_cents: int, units: int) -> float:\n"
        "    return total_cents / units\n",
        encoding="utf-8",
    )
    toml_file = tmp_path / "ayentra.toml"
    toml_file.write_text(
        '[[invariants]]\n'
        'file = "billing_calc.py"\n'
        'target = "compute_unit_cost"\n'
        'kind = "function"\n'
        'expression = "math.isfinite(result)"\n'
        'description = "Unit cost must be finite"\n'
        '[invariants.domain]\n'
        'total_cents = [0, 500]\n'
        'units = [-10, 10]\n',
        encoding="utf-8",
    )

    specs = load_toml_invariants(toml_file, str(target))
    assert len(specs) == 1
    assert specs[0].target_name == "compute_unit_cost"
    assert specs[0].domain_bounds == {"total_cents": [0, 500], "units": [-10, 10]}

    engine_res = run_verification_engine(target, seed_val=42, max_examples=50)
    assert len(engine_res.invariants_checked) == 1
    assert len(engine_res.violations) == 1
    assert engine_res.violations[0].failing_target == "compute_unit_cost"


def test_cli_entrypoints_and_non_destructive_apply_patch(tmp_path: Path) -> None:
    examples_list = [
        ROOT / "examples" / "scheduler_race.py",
        ROOT / "examples" / "inventory_ledger.py",
        ROOT / "examples" / "data_parser.py",
    ]
    shas_before = {p: compute_file_sha256(p) for p in examples_list}

    temp_target = tmp_path / "temp_data_parser.py"
    temp_target.write_text((ROOT / "examples" / "data_parser.py").read_text(encoding="utf-8"), encoding="utf-8")
    temp_sha = compute_file_sha256(temp_target)
    json_receipt = tmp_path / "receipt.json"

    rc_check = main(["check", str(temp_target), "--seed", "42", "--max-examples", "40", "--json-out", str(json_receipt)])
    assert rc_check == 1
    assert json_receipt.is_file()
    assert compute_file_sha256(temp_target) == temp_sha

    rc_suggest = main(["suggest-invariants", str(temp_target)])
    assert rc_suggest == 0

    rc_verify = main(["verify-patch", str(temp_target), "--seed", "42", "--max-examples", "40"])
    assert rc_verify == 0
    assert compute_file_sha256(temp_target) == temp_sha

    rc_dry = main(["apply-patch", str(temp_target), "--seed", "42", "--max-examples", "40"])
    assert rc_dry == 0
    assert compute_file_sha256(temp_target) == temp_sha

    rc_apply = main(["apply-patch", str(temp_target), "--seed", "42", "--max-examples", "40", "--yes"])
    assert rc_apply == 0
    assert compute_file_sha256(temp_target) != temp_sha

    rc_check_after = main(["check", str(temp_target), "--seed", "42", "--max-examples", "40"])
    assert rc_check_after == 0

    for p, sha in shas_before.items():
        assert compute_file_sha256(p) == sha


def test_dict_subscript_suggestion_and_guard_synthesis(tmp_path: Path) -> None:
    target = tmp_path / "dict_lookup.py"
    target.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('result >= 0')\n"
        "def extract_metric(payload: dict[str, int], key: str) -> int:\n"
        "    return payload[key]\n",
        encoding="utf-8",
    )

    ast_res = analyze_source(target)
    assert any(s.suggested_expression == "key in payload" for s in ast_res.suggestions)

    from ayentra.contracts import InvariantSpec
    from ayentra.engine import InvariantViolation
    from ayentra.repair import generate_and_verify_patch

    viol = InvariantViolation(
        invariant=InvariantSpec(
            expression="result >= 0",
            target_name="extract_metric",
            kind="function",
            lineno=4,
            filepath=str(target),
        ),
        verification_method="Property-Based Shrinking via Hypothesis",
        failing_target="extract_metric",
        counterexample={"arguments": {"payload": {}, "key": "cpu"}},
        trace_steps=["extract_metric(payload={}, key='cpu') raised KeyError: 'cpu'"],
        expected_state_desc="Postcondition invariant `result >= 0` must hold on return value `result`",
        actual_state={"arguments": {"payload": {}, "key": "cpu"}, "result": "Unhandled KeyError: 'cpu'"},
        seed=42,
        cases_evaluated=1,
        domain_bounds={"payload": "dict[str, int]", "key": "str"},
    )
    patch = generate_and_verify_patch(target, viol, max_examples=40)
    assert "if not payload:" in patch.patched_source
    assert "raise ValueError('payload must not be empty')" in patch.patched_source
    assert "if key not in payload:" in patch.patched_source
    assert "raise ValueError('Missing required key')" in patch.patched_source
    assert patch.counterexample_passed is True


def test_rich_type_strategies_and_dataclass_snapshot(tmp_path: Path) -> None:
    target = tmp_path / "rich_types_target.py"
    target.write_text(
        "from __future__ import annotations\n"
        "from dataclasses import dataclass\n"
        "from ayentra.contracts import invariant\n\n"
        "@dataclass\n"
        "class OrderBatch:\n"
        "    counts: list[int]\n"
        "    weights: dict[str, float]\n\n"
        "@invariant('result >= 0')\n"
        "def summarize_batch(batch: OrderBatch, tags: list[str], overrides: dict[str, int]) -> int:\n"
        "    return sum(batch.counts) + len(tags) + sum(overrides.values())\n",
        encoding="utf-8",
    )

    engine_res = run_verification_engine(target, seed_val=42, max_examples=50)
    assert len(engine_res.invariants_checked) == 1
    assert len(engine_res.violations) == 1
    viol = engine_res.violations[0]
    assert viol.failing_target == "summarize_batch"
    assert "OrderBatch(" in engine_res.domain_summary["summarize_batch"]["batch"]
    assert "list[str" in engine_res.domain_summary["summarize_batch"]["tags"]
    assert "dict[str, int" in engine_res.domain_summary["summarize_batch"]["overrides"]
    assert isinstance(viol.counterexample["arguments"]["batch"], dict)
    assert "counts" in viol.counterexample["arguments"]["batch"]


def test_studio_keyboard_shortcut_and_diff_copy_markup() -> None:
    from ayentra.studio import STUDIO_HTML

    assert "#F6F5F2" in STUDIO_HTML
    assert "#FCFCFA" in STUDIO_HTML
    assert "#1E232A" in STUDIO_HTML
    assert "Copy Unified Diff" in STUDIO_HTML
    assert "Export JSON Receipt" in STUDIO_HTML
    assert "Ctrl+Enter" in STUDIO_HTML
    assert "(e.ctrlKey || e.altKey) && e.key === 'Enter'" in STUDIO_HTML


def test_optional_union_and_tuple_strategies_and_none_guard(tmp_path: Path) -> None:
    target = tmp_path / "optional_tuple_target.py"
    target.write_text(
        "from __future__ import annotations\n"
        "from dataclasses import dataclass\n"
        "from typing import Optional\n"
        "from ayentra.contracts import invariant\n\n"
        "@dataclass\n"
        "class NodeConfig:\n"
        "    weight: int\n\n"
        "@invariant('result >= 0')\n"
        "def compute_weighted_pair(\n"
        "    cfg: Optional[NodeConfig],\n"
        "    bounds: tuple[int, int],\n"
        "    samples: tuple[int, ...],\n"
        "    bonus: int | None,\n"
        ") -> int:\n"
        "    return abs(cfg.weight) + abs(bounds[0]) + len(samples) + (0 if bonus is None else abs(bonus))\n",
        encoding="utf-8",
    )

    ast_res = analyze_source(target)
    assert any(
        s.target_name == "compute_weighted_pair" and s.suggested_expression == "cfg is not None"
        for s in ast_res.suggestions
    )

    report, engine_res, patches = execute_full_check(target, seed_val=42, max_examples=60)
    assert len(engine_res.violations) == 1
    assert report.failed_invariants_count == 1
    dom = engine_res.domain_summary["compute_weighted_pair"]
    assert "None" in dom["cfg"]
    assert "tuple[int" in dom["bounds"]
    assert "tuple[int" in dom["samples"]
    assert "None" in dom["bonus"]

    assert len(patches) == 1
    p = patches[0]
    assert "if cfg is None:" in p.patched_source
    assert "raise ValueError('cfg must not be None')" in p.patched_source
    assert p.counterexample_passed is True
    assert p.invariant_sweep_passed is True
    assert p.regression_result.passed is True
    assert p.status_label == "VERIFIED CANDIDATE FIX"

def test_set_literal_enum_strategies_and_studio_apply_patch(tmp_path: Path) -> None:
    from ayentra.studio import apply_verified_patch_for_target

    target = tmp_path / "set_enum_target.py"
    target.write_text(
        "from __future__ import annotations\n"
        "from enum import Enum\n"
        "from typing import Literal\n"
        "from ayentra.contracts import invariant\n\n"
        "class PolicyTier(Enum):\n"
        "    BRONZE = 1\n"
        "    GOLD = 2\n\n"
        "@invariant('result >= 0')\n"
        "def compute_set_density(\n"
        "    items: set[int],\n"
        "    frozen_tags: frozenset[int],\n"
        "    mode: Literal['fast', 'safe'],\n"
        "    tier: PolicyTier,\n"
        ") -> float:\n"
        "    return (abs(sum(items)) + len(frozen_tags) + tier.value + (1 if mode == 'fast' else 0)) / len(items)\n",
        encoding="utf-8",
    )

    report, engine_res, patches = execute_full_check(target, seed_val=42, max_examples=50)
    assert len(engine_res.violations) == 1
    assert report.failed_invariants_count == 1
    dom = engine_res.domain_summary["compute_set_density"]
    assert "set[int" in dom["items"]
    assert "frozenset[int" in dom["frozen_tags"]
    assert "Literal" in dom["mode"]
    assert "Enum(PolicyTier)" in dom["tier"]
    assert engine_res.violations[0].counterexample["arguments"]["items"] == []

    assert len(patches) == 1
    p = patches[0]
    assert "if not items:" in p.patched_source
    assert "raise ValueError('items must not be empty')" in p.patched_source
    assert p.status_label == "VERIFIED CANDIDATE FIX"

    apply_res = apply_verified_patch_for_target(target, seed_val=42, max_examples=40)
    assert apply_res["applied"] is True
    assert apply_res["status"] == "VERIFIED PATCH APPLIED"

    report_after, engine_after, _ = execute_full_check(target, seed_val=42, max_examples=40)
    assert len(engine_after.violations) == 0
    assert report_after.failed_invariants_count == 0
    assert report_after.passed_invariants_count == 1

def test_multi_arg_concurrency_race_and_directory_summary(tmp_path: Path, capsys: object) -> None:
    from ayentra.engine import load_module_from_path

    target = tmp_path / "tagged_ledger_race.py"
    target.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import domain, invariant\n\n"
        "@invariant('self.balance >= 0 and self.balance <= self.limit', check_concurrency=True)\n"
        "class TaggedBudgetPool:\n"
        "    def __init__(self, limit: int = 10) -> None:\n"
        "        self.limit = limit\n"
        "        self.balance = 0\n\n"
        "    @domain(amount=(-15, 15))\n"
        "    def allocate_tagged(self, tag: str, amount: int) -> bool:\n"
        "        if self.balance + amount <= self.limit:\n"
        "            self.balance += amount\n"
        "            return True\n"
        "        return False\n",
        encoding="utf-8",
    )

    report, engine_res, patches = execute_full_check(target, seed_val=42, max_examples=50)
    assert len(engine_res.violations) == 1
    assert report.failed_invariants_count == 1
    v = engine_res.violations[0]
    assert v.verification_method == "Deterministic Thread Interleaving Check"
    assert v.failing_target == "TaggedBudgetPool.allocate_tagged"

    assert len(patches) == 1
    p = patches[0]
    assert "with self._lock:" in p.patched_source
    assert "if amount <= 0:" in p.patched_source
    assert "if tag <= 0:" not in p.patched_source
    assert p.counterexample_passed is True
    assert p.invariant_sweep_passed is True
    assert p.regression_result.passed is True
    assert p.status_label == "VERIFIED CANDIDATE FIX"

    patched_file = tmp_path / "tagged_ledger_patched.py"
    patched_file.write_text(p.patched_source, encoding="utf-8")
    mod = load_module_from_path(patched_file)
    pool = mod.TaggedBudgetPool(limit=10)
    assert pool.allocate_tagged("gpu-cluster-a", 4) is True
    assert pool.balance == 4
    assert pool.allocate_tagged("gpu-cluster-a", -2) is False
    assert pool.balance == 4

    rc_dir = main(["check", str(ROOT / "examples"), "--max-examples", "25"])
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert rc_dir == 1
    assert "Directory Verification Summary" in captured.out


def test_async_function_and_method_verification_and_repair(tmp_path: Path) -> None:
    fn_target = tmp_path / "async_ratio_target.py"
    fn_target.write_text(
        "from __future__ import annotations\n"
        "import math\n"
        "from ayentra.contracts import domain, invariant\n\n"
        "@invariant('math.isfinite(result) and result >= 0')\n"
        "@domain(total=(0.0, 200.0), count=(-5, 5))\n"
        "async def compute_async_ratio(total: float, count: int) -> float:\n"
        "    return total / count\n",
        encoding="utf-8",
    )

    fn_report, fn_engine, fn_patches = execute_full_check(fn_target, seed_val=42, max_examples=50)
    assert len(fn_engine.violations) == 1
    assert fn_report.failed_invariants_count == 1
    assert fn_engine.violations[0].failing_target == "compute_async_ratio"
    assert len(fn_patches) == 1
    fn_p = fn_patches[0]
    assert "async def compute_async_ratio(" in fn_p.patched_source
    assert "if count == 0:" in fn_p.patched_source
    assert fn_p.counterexample_passed is True
    assert fn_p.invariant_sweep_passed is True
    assert fn_p.regression_result.passed is True
    assert fn_p.status_label == "VERIFIED CANDIDATE FIX"

    cls_target = tmp_path / "async_wallet_target.py"
    cls_target.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import domain, invariant\n\n"
        "@invariant('self.available >= 0 and self.reserved >= 0 and self.available + self.reserved == self.initial_total')\n"
        "class AsyncReserveVault:\n"
        "    def __init__(self, initial_total: int = 100) -> None:\n"
        "        self.initial_total = initial_total\n"
        "        self.available = initial_total\n"
        "        self.reserved = 0\n\n"
        "    @domain(amount=(-30, 150))\n"
        "    async def withdraw_async(self, amount: int) -> None:\n"
        "        if amount <= self.available:\n"
        "            self.available -= amount\n"
        "            self.reserved += amount\n",
        encoding="utf-8",
    )

    cls_report, cls_engine, cls_patches = execute_full_check(cls_target, seed_val=42, max_examples=50)
    assert len(cls_engine.violations) == 1
    assert cls_report.failed_invariants_count == 1
    assert cls_engine.violations[0].failing_target == "AsyncReserveVault.withdraw_async"
    assert len(cls_patches) == 1
    cls_p = cls_patches[0]
    assert "async def withdraw_async(" in cls_p.patched_source
    assert "if amount <= 0:" in cls_p.patched_source
    assert cls_p.counterexample_passed is True
    assert cls_p.invariant_sweep_passed is True
    assert cls_p.regression_result.passed is True
    assert cls_p.status_label == "VERIFIED CANDIDATE FIX"


def test_decimal_and_date_strategies_and_directory_json_receipt(tmp_path: Path) -> None:
    dec_target = tmp_path / "decimal_target.py"
    dec_target.write_text(
        "from __future__ import annotations\n"
        "from decimal import Decimal\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant(\"result >= Decimal('0')\")\n"
        "def split_ledger_amount(total: Decimal, parts: int) -> Decimal:\n"
        "    return total / parts\n",
        encoding="utf-8",
    )

    dec_report, dec_engine, dec_patches = execute_full_check(dec_target, seed_val=42, max_examples=50)
    assert len(dec_engine.violations) == 1
    assert dec_report.failed_invariants_count == 1
    assert dec_engine.violations[0].failing_target == "split_ledger_amount"
    assert json.loads(dec_report.to_json())["failed_invariants_count"] == 1
    assert len(dec_patches) == 1
    assert dec_patches[0].counterexample_passed is True
    assert dec_patches[0].invariant_sweep_passed is True
    assert dec_patches[0].regression_result.passed is True
    assert dec_patches[0].status_label == "VERIFIED CANDIDATE FIX"

    date_target = tmp_path / "date_target.py"
    date_target.write_text(
        "from __future__ import annotations\n"
        "from datetime import date\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('result >= 0')\n"
        "def billing_days(start: date, end: date) -> int:\n"
        "    return (end - start).days\n",
        encoding="utf-8",
    )

    date_report, date_engine, date_patches = execute_full_check(date_target, seed_val=42, max_examples=50)
    assert len(date_engine.violations) == 1
    assert date_report.failed_invariants_count == 1
    assert date_engine.violations[0].failing_target == "billing_days"
    assert json.loads(date_report.to_json())["failed_invariants_count"] == 1
    assert len(date_patches) == 1
    assert date_patches[0].counterexample_passed is True
    assert date_patches[0].invariant_sweep_passed is True
    assert date_patches[0].regression_result.passed is True
    assert date_patches[0].status_label == "VERIFIED CANDIDATE FIX"

    json_out = tmp_path / "dir_receipt.json"
    rc = main(["check", str(tmp_path), "--max-examples", "25", "--json-out", str(json_out)])
    assert rc == 1
    assert json_out.exists()
    dir_payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert dir_payload["total_files_checked"] == 2
    assert dir_payload["failed_files_count"] == 2
    assert len(dir_payload["reports"]) == 2


def test_cli_site_command_and_server(tmp_path: Path) -> None:
    import threading
    import urllib.request
    from ayentra.cli import build_parser, create_site_server

    parser = build_parser()
    args = parser.parse_args(["site", "--port", "8899", "--no-browser"])
    assert args.command == "site"
    assert args.port == 8899
    assert args.no_browser is True

    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "index.html").write_text("<!doctype html><html><body>Ayentra Demo Site</body></html>", encoding="utf-8")

    server = create_site_server(site_dir, port=0)
    actual_port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        url = f"http://127.0.0.1:{actual_port}/index.html"
        with urllib.request.urlopen(url, timeout=5) as resp:
            body = resp.read().decode("utf-8")
            assert "Ayentra Demo Site" in body
            assert resp.status == 200
    finally:
        server.shutdown()
        server.server_close()


def test_cli_pr_mock_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from ayentra.cli import build_parser, main

    parser = build_parser()
    args = parser.parse_args(["pr-mock", "dummy.py", "--seed", "99", "--max-examples", "50"])
    assert args.command == "pr-mock"
    assert args.target == "dummy.py"
    assert args.seed == 99
    assert args.max_examples == 50

    target = tmp_path / "pr_target.py"
    target.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.balance >= 0')\n"
        "class Account:\n"
        "    def __init__(self, balance: int = 10) -> None:\n"
        "        self.balance = balance\n"
        "    def debit(self, amount: int) -> None:\n"
        "        self.balance -= amount\n",
        encoding="utf-8",
    )

    rc = main(["pr-mock", str(target), "--max-examples", "30"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "## Ayentra PR Bot: Invariant Verification Gate FAILED" in captured.out
    assert "Plain-English Bug:" in captured.out
    assert "Business Risk:" in captured.out
    assert "1-Click Merge Fix:" in captured.out
    assert f"ayentra apply-patch {target.as_posix()} --yes" in captured.out


def test_cli_demo_and_github_step_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from ayentra.cli import build_parser, main

    parser = build_parser()
    args = parser.parse_args(["demo", "--seed", "77", "--max-examples", "15"])
    assert args.command == "demo"
    assert args.seed == 77
    assert args.max_examples == 15

    step_summary_file = tmp_path / "github_step_summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(step_summary_file))

    target = tmp_path / "summary_target.py"
    target.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.value >= 0')\n"
        "class Counter:\n"
        "    def __init__(self, value: int = 5) -> None:\n"
        "        self.value = value\n"
        "    def decrement(self, n: int) -> None:\n"
        "        self.value -= n\n",
        encoding="utf-8",
    )

    rc_check = main(["check", str(target), "--ci", "--max-examples", "20"])
    assert rc_check == 1
    assert step_summary_file.exists()
    summary_text = step_summary_file.read_text(encoding="utf-8")
    assert "### Ayentra Verification Gate: FAIL" in summary_text
    assert "Counter.decrement" in summary_text
    assert "1-Click Verified Fix" in summary_text

    rc_pr = main(["pr-mock", str(target), "--max-examples", "20"])
    assert rc_pr == 0
    updated_summary = step_summary_file.read_text(encoding="utf-8")
    assert "## Ayentra PR Bot: Invariant Verification Gate FAILED" in updated_summary
    assert "Interactive Diff Preview (Before vs After)" in updated_summary


def test_cli_init_command_and_scaffolding(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    import tomllib
    from ayentra.cli import build_parser, main
    from ayentra.contracts import load_toml_invariants

    parser = build_parser()
    args = parser.parse_args(["init", "--path", "sample_repo", "--force", "--ci"])
    assert args.command == "init"
    assert args.path == "sample_repo"
    assert args.force is True
    assert args.ci is True

    repo_dir = tmp_path / "pilot_repo"
    src_dir = repo_dir / "src"
    src_dir.mkdir(parents=True)
    sample_py = src_dir / "service.py"
    sample_py.write_text(
        "def compute_score(value: int) -> int:\n"
        "    return value * 2\n",
        encoding="utf-8",
    )

    rc = main(["init", "--path", str(repo_dir), "--ci"])
    assert rc == 0

    toml_path = repo_dir / "ayentra.toml"
    assert toml_path.exists()
    toml_text = toml_path.read_text(encoding="utf-8")
    assert "\u2014" not in toml_text
    parsed_toml = tomllib.loads(toml_text)
    assert parsed_toml["project"]["name"] == "pilot_repo"
    assert "src" in parsed_toml["project"]["target_dirs"]

    specs = load_toml_invariants(toml_path, str(sample_py))
    assert len(specs) == 1
    assert specs[0].target_name == "sample_handler"
    assert specs[0].expression == "result is not None"

    wf_path = repo_dir / ".github" / "workflows" / "ayentra.yml"
    assert wf_path.exists()
    wf_text = wf_path.read_text(encoding="utf-8")
    assert "\u2014" not in wf_text
    assert "pip install ayentra" in wf_text
    assert "ayentra check . --ci" in wf_text

    rc_conflict = main(["init", "--path", str(repo_dir)])
    assert rc_conflict == 1
    captured = capsys.readouterr()
    assert "Configuration file already exists" in captured.out

    rc_force = main(["init", "--path", str(repo_dir), "--force"])
    assert rc_force == 0

def test_zero_division_guard_template_synthesis(tmp_path: Path) -> None:
    import ast
    from ayentra.repair import synthesize_zero_division_guard_node

    early_node = synthesize_zero_division_guard_node("denom", early_return="0.0")
    assert ast.unparse(early_node).strip() == "if denom == 0:\n    return 0.0"

    target = tmp_path / "ratio_service.py"
    target.write_text(
        "from __future__ import annotations\n"
        "import math\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('math.isfinite(result)')\n"
        "def compute_ratio(numerator: int, denominator: int) -> float:\n"
        "    return numerator / denominator\n",
        encoding="utf-8",
    )

    report, engine_res, patches = execute_full_check(target, seed_val=42, max_examples=60)
    assert len(engine_res.violations) == 1
    assert report.failed_invariants_count == 1
    assert "ZeroDivisionError" in str(engine_res.violations[0].actual_state["result"])
    assert len(patches) == 1

    patch = patches[0]
    assert patch.repair_strategy == "AST Zero-Division Guard Synthesis"
    assert "if denominator == 0:" in patch.patched_source
    assert "raise ValueError('denominator must be non-zero')" in patch.patched_source
    assert patch.counterexample_passed is True
    assert patch.invariant_sweep_passed is True
    assert patch.regression_result.passed is True
    assert patch.status_label == "VERIFIED CANDIDATE FIX"


def test_none_boundary_guard_template_synthesis(tmp_path: Path) -> None:
    import ast
    from ayentra.repair import synthesize_none_guard_node

    early_node = synthesize_none_guard_node("client", early_return="None")
    assert ast.unparse(early_node).strip() == "if client is None:\n    return None"

    target = tmp_path / "client_service.py"
    target.write_text(
        "from __future__ import annotations\n"
        "from dataclasses import dataclass\n"
        "from typing import Optional\n"
        "from ayentra.contracts import invariant\n\n"
        "@dataclass\n"
        "class ClientProfile:\n"
        "    tier: int\n\n"
        "@invariant('result >= 0')\n"
        "def evaluate_tier(profile: Optional[ClientProfile]) -> int:\n"
        "    return abs(profile.tier) * 10\n",
        encoding="utf-8",
    )

    report, engine_res, patches = execute_full_check(target, seed_val=42, max_examples=60)
    assert len(engine_res.violations) == 1
    assert report.failed_invariants_count == 1
    assert "AttributeError" in str(engine_res.violations[0].actual_state["result"])
    assert len(patches) == 1

    patch = patches[0]
    assert patch.repair_strategy == "AST None-Type Boundary Guard Synthesis"
    assert "if profile is None:" in patch.patched_source
    assert "raise ValueError('profile must not be None')" in patch.patched_source
    assert patch.counterexample_passed is True
    assert patch.invariant_sweep_passed is True
    assert patch.regression_result.passed is True
    assert patch.status_label == "VERIFIED CANDIDATE FIX"



@given(
    u=_strategy_for_annotation(uuid.UUID)[0],
    u_str=_strategy_for_annotation("UUID")[0],
    b=_strategy_for_annotation(bytes)[0],
    b_str=_strategy_for_annotation("bytes")[0],
    ba=_strategy_for_annotation(bytearray)[0],
    ba_str=_strategy_for_annotation("bytearray")[0],
)
@settings(max_examples=25)
def test_uuid_bytes_and_bytearray_strategies_property_generation(
    u: uuid.UUID,
    u_str: uuid.UUID,
    b: bytes,
    b_str: bytes,
    ba: bytearray,
    ba_str: bytearray,
) -> None:
    assert isinstance(u, uuid.UUID)
    assert isinstance(u_str, uuid.UUID)
    assert isinstance(b, bytes)
    assert 0 <= len(b) <= 32
    assert isinstance(b_str, bytes)
    assert 0 <= len(b_str) <= 32
    assert isinstance(ba, bytearray)
    assert 0 <= len(ba) <= 32
    assert isinstance(ba_str, bytearray)
    assert 0 <= len(ba_str) <= 32


def test_uuid_bytes_and_bytearray_strategies_and_rehydration(tmp_path: Path) -> None:
    # 1. Test strategy descriptions
    _, u_desc = _strategy_for_annotation(uuid.UUID)
    assert u_desc == "UUID"
    _, u_str_desc = _strategy_for_annotation("UUID")
    assert u_str_desc == "UUID"

    _, b_desc = _strategy_for_annotation(bytes)
    assert b_desc == "bytes (len 0..32)"
    _, b_str_desc = _strategy_for_annotation("bytes")
    assert b_str_desc == "bytes (len 0..32)"

    _, ba_desc = _strategy_for_annotation(bytearray)
    assert ba_desc == "bytearray (len 0..32)"
    _, ba_str_desc = _strategy_for_annotation("bytearray")
    assert ba_str_desc == "bytearray (len 0..32)"

    # 2. Test rehydration from serialized representation
    def dummy_func(u: uuid.UUID, b: bytes, ba: bytearray) -> bool:
        return True

    test_uuid = uuid.UUID("12345678-1234-5678-1234-567812345678")
    test_bytes = b"hello\x00world"
    test_ba = bytearray(b"mutable\xffdata")

    rehydrated = _rehydrate_args(
        {
            "u": str(test_uuid),
            "b": test_bytes.hex(),
            "ba": test_ba.hex(),
        },
        dummy_func,
    )
    assert isinstance(rehydrated["u"], uuid.UUID)
    assert rehydrated["u"] == test_uuid
    assert isinstance(rehydrated["b"], bytes)
    assert rehydrated["b"] == test_bytes
    assert isinstance(rehydrated["ba"], bytearray)
    assert rehydrated["ba"] == test_ba

    # Adversarial edge-case: Empty binary payloads (b"", bytearray())
    empty_rehydrated = _rehydrate_args(
        {
            "u": str(test_uuid),
            "b": "",
            "ba": "",
        },
        dummy_func,
    )
    assert empty_rehydrated["b"] == b""
    assert isinstance(empty_rehydrated["b"], bytes)
    assert empty_rehydrated["ba"] == bytearray()
    assert isinstance(empty_rehydrated["ba"], bytearray)

    # Adversarial edge-case: Max boundary handling (32 bytes / 64 hex characters)
    max_b = b"\xfe" * 32
    max_ba = bytearray(b"\xca" * 32)
    max_rehydrated = _rehydrate_args(
        {
            "u": str(test_uuid),
            "b": max_b.hex(),
            "ba": max_ba.hex(),
        },
        dummy_func,
    )
    assert max_rehydrated["b"] == max_b
    assert len(max_rehydrated["b"]) == 32
    assert max_rehydrated["ba"] == max_ba
    assert len(max_rehydrated["ba"]) == 32

    # Adversarial edge-case: Bytearray mutation isolation during rehydration
    orig_ba = bytearray(b"immutable_source_buffer")
    iso_rehydrated = _rehydrate_args(
        {
            "u": test_uuid,
            "b": b"static",
            "ba": orig_ba,
        },
        dummy_func,
    )
    assert iso_rehydrated["ba"] == orig_ba
    assert iso_rehydrated["ba"] is not orig_ba
    iso_rehydrated["ba"].extend(b"_tainted")
    assert orig_ba == bytearray(b"immutable_source_buffer")

    # Adversarial edge-case: Malformed hex string handling and fallback behavior
    malformed_rehydrated = _rehydrate_args(
        {
            "u": "invalid-uuid-format-string",
            "b": "malformed_hex_chars_!?",
            "ba": "odd_hex_len_7",
        },
        dummy_func,
    )
    assert isinstance(malformed_rehydrated["b"], bytes)
    assert malformed_rehydrated["b"] == b"malformed_hex_chars_!?"
    assert isinstance(malformed_rehydrated["ba"], bytearray)
    assert malformed_rehydrated["ba"] == bytearray(b"odd_hex_len_7")
    assert malformed_rehydrated["u"] == "invalid-uuid-format-string"

    # 3. Target verification with UUID, bytes, and bytearray property-based shrinking
    target = tmp_path / "ledger_crypto.py"
    target.write_text(
        "from __future__ import annotations\n"
        "import uuid\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('result is True')\n"
        "def verify_transaction_payload(tx_id: uuid.UUID, signature: bytes, session_buf: bytearray) -> bool:\n"
        "    if len(signature) > 10:\n"
        "        return False\n"
        "    return True\n",
        encoding="utf-8",
    )

    engine_res = run_verification_engine(target, seed_val=42, max_examples=50)
    assert len(engine_res.invariants_checked) == 1
    assert len(engine_res.violations) == 1
    viol = engine_res.violations[0]
    assert viol.failing_target == "verify_transaction_payload"
    assert engine_res.domain_summary["verify_transaction_payload"]["tx_id"] == "UUID"
    assert engine_res.domain_summary["verify_transaction_payload"]["signature"] == "bytes (len 0..32)"
    assert engine_res.domain_summary["verify_transaction_payload"]["session_buf"] == "bytearray (len 0..32)"

    # Shrunk counterexample arguments
    ce_args = viol.counterexample["arguments"]
    assert "tx_id" in ce_args
    assert "signature" in ce_args
    assert "session_buf" in ce_args
    # Serialized hex length of signature > 10 bytes (i.e. > 20 hex chars)
    assert len(ce_args["signature"]) > 20

    # Counterexample JSON serialization validation
    serialized_ce = json.dumps(viol.counterexample)
    parsed_ce = json.loads(serialized_ce)
    assert parsed_ce["arguments"]["signature"] == ce_args["signature"]
    assert parsed_ce["arguments"]["tx_id"] == ce_args["tx_id"]
    assert parsed_ce["arguments"]["session_buf"] == ce_args["session_buf"]

    # Shrinkage validation: minimal boundary counterexample for length check (>10 shrinks to 11 bytes)
    shrunk_signature_bytes = bytes.fromhex(ce_args["signature"])
    assert len(shrunk_signature_bytes) == 11

    # Verify counterexample replay correctly rehydrates and confirms failure
    assert replay_counterexample(target, viol) is False

    # 4. Check class method verification with UUID, bytes, bytearray
    cls_target = tmp_path / "session_vault.py"
    cls_target.write_text(
        "from __future__ import annotations\n"
        "import uuid\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.valid is True')\n"
        "class SessionVault:\n"
        "    def __init__(self) -> None:\n"
        "        self.valid = True\n"
        "        self.item_count = 0\n\n"
        "    def record(self, token_id: uuid.UUID, salt: bytes, buffer: bytearray) -> None:\n"
        "        if len(salt) > 5:\n"
        "            self.valid = False\n"
        "        self.item_count += 1\n",
        encoding="utf-8",
    )

    cls_engine_res = run_verification_engine(cls_target, seed_val=42, max_examples=50)
    assert len(cls_engine_res.invariants_checked) == 1
    assert len(cls_engine_res.violations) == 1
    cls_viol = cls_engine_res.violations[0]
    assert cls_viol.failing_target == "SessionVault.record"
    assert cls_viol.counterexample["call_sequence"]
    call_step = cls_viol.counterexample["call_sequence"][0]
    assert call_step["method"] == "record"
    assert "token_id" in call_step["args"]
    assert "salt" in call_step["args"]
    assert "buffer" in call_step["args"]

    # JSON serialization validation for stateful class counterexample
    serialized_cls_ce = json.dumps(cls_viol.counterexample)
    parsed_cls_ce = json.loads(serialized_cls_ce)
    assert parsed_cls_ce["call_sequence"][0]["args"]["salt"] == call_step["args"]["salt"]

    # Shrinkage validation on stateful class parameter: length > 5 shrinks to 6 bytes
    shrunk_salt_bytes = bytes.fromhex(call_step["args"]["salt"])
    assert len(shrunk_salt_bytes) == 6

    # Verify stateful replay counterexample confirms failure
    assert replay_counterexample(cls_target, cls_viol) is False


def test_ast_analyzer_uuid_and_fromhex_suggestions(tmp_path: Path) -> None:
    target = tmp_path / "parsers.py"
    target.write_text(
        "from __future__ import annotations\n"
        "import uuid\n"
        "def parse_session_token(token: str) -> uuid.UUID:\n"
        "    return uuid.UUID(token)\n\n"
        "def parse_hex_buffer(payload: str) -> bytes:\n"
        "    return bytes.fromhex(payload)\n\n"
        "def safe_parse_uuid(token: str) -> uuid.UUID | None:\n"
        "    try:\n"
        "        return uuid.UUID(token)\n"
        "    except ValueError:\n"
        "        return None\n\n"
        "def validated_hex_parse(payload: str) -> bytes | None:\n"
        "    if len(payload) % 2 != 0:\n"
        "        return None\n"
        "    return bytes.fromhex(payload)\n",
        encoding="utf-8",
    )

    res = analyze_source(target)
    # Unhandled uuid.UUID parsing should emit suggestion
    uuid_suggs = [s for s in res.suggestions if s.target_name == "parse_session_token"]
    assert len(uuid_suggs) == 1
    assert "len(token.strip()) in (32, 36)" in uuid_suggs[0].suggested_expression
    assert "uuid.UUID()" in uuid_suggs[0].rationale

    # Unhandled bytes.fromhex parsing should emit suggestion
    hex_suggs = [s for s in res.suggestions if s.target_name == "parse_hex_buffer"]
    assert len(hex_suggs) == 1
    assert "len(payload.strip()) % 2 == 0" in hex_suggs[0].suggested_expression
    assert "bytes.fromhex()" in hex_suggs[0].rationale

    # Protected or validated functions should not emit unhandled suggestions
    safe_uuid_suggs = [s for s in res.suggestions if s.target_name == "safe_parse_uuid"]
    assert len(safe_uuid_suggs) == 0
    safe_hex_suggs = [s for s in res.suggestions if s.target_name == "validated_hex_parse"]
    assert len(safe_hex_suggs) == 0


def test_bytes_bytearray_zero_length_repair_synthesis_and_sandbox_gates(tmp_path: Path) -> None:
    from ayentra.repair import generate_and_verify_patch

    target = tmp_path / "packet_verifier.py"
    target.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('result is True')\n"
        "def verify_network_packet(header: bytes, payload: bytearray) -> bool:\n"
        "    if len(header) == 0 or len(payload) == 0:\n"
        "        return False\n"
        "    return True\n",
        encoding="utf-8",
    )

    engine_res = run_verification_engine(target, seed_val=42, max_examples=50)
    assert len(engine_res.violations) == 1
    viol = engine_res.violations[0]

    patch_res = generate_and_verify_patch(target, viol, max_examples=50)
    assert patch_res.counterexample_passed is True
    assert patch_res.invariant_sweep_passed is True
    assert patch_res.regression_result.passed is True
    assert patch_res.is_verified is True
    assert "not header" in patch_res.patched_source
    assert "not payload" in patch_res.patched_source


def test_uuid_nil_repair_synthesis_and_sandbox_gates(tmp_path: Path) -> None:
    from ayentra.repair import generate_and_verify_patch

    target = tmp_path / "account_validator.py"
    target.write_text(
        "from __future__ import annotations\n"
        "import uuid\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('result is True')\n"
        "def validate_account_id(acc_id: uuid.UUID) -> bool:\n"
        "    if acc_id == uuid.UUID(int=0):\n"
        "        return False\n"
        "    return True\n",
        encoding="utf-8",
    )

    engine_res = run_verification_engine(target, seed_val=42, max_examples=50)
    assert len(engine_res.violations) == 1
    viol = engine_res.violations[0]

    patch_res = generate_and_verify_patch(target, viol, max_examples=50)
    assert patch_res.counterexample_passed is True
    assert patch_res.invariant_sweep_passed is True
    assert patch_res.regression_result.passed is True
    assert patch_res.is_verified is True
    assert "uuid.UUID(int=0)" in patch_res.patched_source

def test_eval_expr_dunder_blocking_security(tmp_path: Path) -> None:
    from ayentra.engine import _eval_expr
    import pytest

    # 1. Attempt dunder attribute escape
    with pytest.raises(ValueError, match="Unsafe dunder access in invariant expression"):
        _eval_expr("().__class__.__bases__", {})

    # 2. Attempt dunder name escape
    with pytest.raises(ValueError, match="Unsafe dunder access in invariant expression"):
        _eval_expr("__import__('os').system('id')", {})

    # 3. Attempt unsafe function call escape (open, eval, exec)
    with pytest.raises(ValueError, match="Unsafe function call in invariant expression"):
        _eval_expr("open('/etc/passwd')", {})

    # 4. Attempt unsafe module call escape
    with pytest.raises(ValueError, match="Unsafe attribute call in invariant expression"):
        _eval_expr("os.system('id')", {"os": __import__('os')})

    # 5. Legitimate expressions work normally
    assert _eval_expr("x > 0 and math.sqrt(x) == 4.0", {"x": 16}) is True
    assert _eval_expr("Decimal('1.5') + Decimal('2.5') == Decimal('4.0')", {}) is True
    assert _eval_expr("result >= 0 and abs(result) == 10", {"result": 10}) is True
    assert _eval_expr("len(result) == 2", {"result": [1, 2]}) is True
    assert _eval_expr("math.isfinite(x)", {"x": 3.14}) is True



def test_run_pytest_suite_timeout_expired(monkeypatch, tmp_path: Path) -> None:
    from ayentra.regression import run_pytest_suite
    import subprocess

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=30)

    monkeypatch.setattr(subprocess, "run", fake_run)
    res = run_pytest_suite(tmp_path)
    assert res.passed is False
    assert res.passed_count == 0
    assert res.failed_count == 1
    assert res.duration_ms == 30000.0
    assert res.output_summary == "Pytest suite timed out after 30 seconds."


def test_run_pytest_suite_ignore_tests_flag(monkeypatch, tmp_path: Path) -> None:
    from ayentra.regression import run_pytest_suite
    import subprocess

    captured_cmds = []

    def fake_run(cmd, *args, **kwargs):
        captured_cmds.append(cmd)
        class DummyProc:
            returncode = 0
            stdout = "1 passed"
            stderr = ""
        return DummyProc()

    monkeypatch.setattr(subprocess, "run", fake_run)

    # 1. External customer repo without src/ayentra
    run_pytest_suite(tmp_path)
    assert not any("--ignore=tests" in arg for arg in captured_cmds[-1])

    # 2. Repo with src/ayentra
    ayentra_dir = tmp_path / "src" / "ayentra"
    ayentra_dir.mkdir(parents=True)
    run_pytest_suite(tmp_path)
    assert any("--ignore=tests" in arg for arg in captured_cmds[-1])

def test_sandbox_verification_ignore_patterns(monkeypatch, tmp_path: Path) -> None:
    import shutil
    from ayentra.repair import verify_candidate_source
    from ayentra.contracts import InvariantSpec
    from ayentra.engine import InvariantViolation

    repo_dir = tmp_path / "customer_repo"
    repo_dir.mkdir()
    target_file = repo_dir / "calc.py"
    target_file.write_text(
        "from ayentra.contracts import invariant\n"
        "@invariant('result >= 0')\n"
        "def add(a: int, b: int) -> int:\n"
        "    if a < 0:\n"
        "        return 0\n"
        "    return a + b\n",
        encoding="utf-8",
    )

    # Create ignored directories and files
    (repo_dir / "node_modules").mkdir()
    (repo_dir / "node_modules" / "pkg.js").write_text("console.log(1)", encoding="utf-8")
    (repo_dir / "build").mkdir()
    (repo_dir / "build" / "lib.so").write_text("dummy", encoding="utf-8")
    (repo_dir / "dist").mkdir()
    (repo_dir / "dist" / "bundle.tar").write_text("dummy", encoding="utf-8")
    (repo_dir / ".tox").mkdir()
    (repo_dir / ".tox" / "env.log").write_text("dummy", encoding="utf-8")
    (repo_dir / "my_pkg.egg-info").mkdir()
    (repo_dir / "my_pkg.egg-info" / "PKG-INFO").write_text("dummy", encoding="utf-8")
    (repo_dir / ".mypy_cache").mkdir()
    (repo_dir / ".mypy_cache" / "cache.db").write_text("dummy", encoding="utf-8")
    (repo_dir / ".ruff_cache").mkdir()
    (repo_dir / ".ruff_cache" / "cache.db").write_text("dummy", encoding="utf-8")

    copied_dst_contents = []
    orig_copytree = shutil.copytree

    def spy_copytree(src, dst, *args, **kwargs):
        res = orig_copytree(src, dst, *args, **kwargs)
        copied_dst_contents.append([p.name for p in Path(dst).iterdir()])
        return res

    monkeypatch.setattr(shutil, "copytree", spy_copytree)

    violation = InvariantViolation(
        invariant=InvariantSpec(
            expression="result >= 0",
            target_name="add",
            kind="function",
            lineno=3,
            filepath=str(target_file),
        ),
        verification_method="Property-Based Shrinking via Hypothesis",
        failing_target="add",
        counterexample={"arguments": {"a": -5, "b": 1}},
        trace_steps=["add(a=-5, b=1) returned -4 violating result >= 0"],
        expected_state_desc="result >= 0",
        actual_state={"arguments": {"a": -5, "b": 1}, "result": -4},
        seed=42,
        cases_evaluated=10,
        domain_bounds={},
    )

    res = verify_candidate_source(
        filepath=target_file,
        original_source="def add(a: int, b: int) -> int:\n    return a + b\n",
        candidate_source=target_file.read_text(encoding="utf-8"),
        violation=violation,
        max_examples=10,
    )

    assert len(copied_dst_contents) >= 1
    names = copied_dst_contents[0]
    for ignored in [
        "node_modules",
        "build",
        "dist",
        ".tox",
        "my_pkg.egg-info",
        ".mypy_cache",
        ".ruff_cache",
    ]:
        assert ignored not in names, f"{ignored} was not ignored during sandbox copy"
    assert "calc.py" in names
    assert res.counterexample_passed is True


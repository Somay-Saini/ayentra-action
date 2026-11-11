from __future__ import annotations

import io
from pathlib import Path
import pytest
from rich.console import Console

from ayentra.cli import build_parser, main, run_guided_demo


def test_demo_non_interactive_execution_and_card_rendering() -> None:
    output_buffer = io.StringIO()
    mock_console = Console(file=output_buffer, force_terminal=False, width=120)

    rc = run_guided_demo(console=mock_console, seed=42, max_examples=10)
    assert rc == 0

    rendered = output_buffer.getvalue()
    assert "Customer Guided Demo" in rendered
    assert "Guided Demo Complete" in rendered
    assert "Plain-English Bug:" in rendered
    assert "Business Risk:" in rendered
    assert "1-Click Fix:" in rendered
    assert "Unified Patch Diff (Verified):" in rendered
    assert "\u2014" not in rendered and "\u2013" not in rendered

    parser = build_parser()
    args = parser.parse_args(["demo", "--seed", "123", "--max-examples", "10"])
    assert args.command == "demo"
    assert args.seed == 123
    assert args.max_examples == 10


def test_github_step_summary_environment_handling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    summary_file = tmp_path / "step_summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

    target = tmp_path / "vault.py"
    target.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.balance >= 0')\n"
        "class Vault:\n"
        "    def __init__(self, balance: int = 50) -> None:\n"
        "        self.balance = balance\n"
        "    def withdraw(self, amount: int) -> None:\n"
        "        self.balance -= amount\n",
        encoding="utf-8",
    )

    rc_check = main(["check", str(target), "--ci", "--max-examples", "20", "--seed", "42"])
    assert rc_check == 1
    assert summary_file.exists()

    content_after_check = summary_file.read_text(encoding="utf-8")
    assert "### Ayentra Verification Gate: FAIL" in content_after_check
    assert "Vault.withdraw" in content_after_check
    assert "1-Click Verified Fix" in content_after_check
    assert "```diff" in content_after_check
    assert "\u2014" not in content_after_check and "\u2013" not in content_after_check

    fixture_patch = Path(r"C:\Users\Somay\Desktop\idea1\examples\fixtures\pr_diff_balance_leak.patch")
    rc_pr = main(["pr-mock", str(fixture_patch)])
    assert rc_pr == 0

    content_after_pr = summary_file.read_text(encoding="utf-8")
    assert "### Ayentra Verification Gate: FAIL" in content_after_pr
    assert "## Ayentra PR Bot: Invariant Verification Gate FAILED" in content_after_pr
    assert "Financial balance leak: transfer debits source account without crediting destination account." in content_after_pr
    assert "<details open>" in content_after_pr
    assert "\u2014" not in content_after_pr and "\u2013" not in content_after_pr


def test_resiliency_invalid_flags_and_nonexistent_targets(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--invalid-unknown-flag-xyz"])
    assert exc_info.value.code == 2

    missing_py = tmp_path / "does_not_exist_file.py"
    missing_patch = tmp_path / "does_not_exist_patch.patch"

    for cmd in ["check", "pr-mock", "suggest-invariants", "verify-patch", "apply-patch"]:
        target_arg = str(missing_patch if cmd == "pr-mock" else missing_py)
        rc = main([cmd, target_arg])
        assert rc == 2
        captured = capsys.readouterr()
        assert "not found" in captured.out or "not found" in captured.err

    syntax_bad = tmp_path / "broken_syntax.py"
    syntax_bad.write_text("def broken_func(:\n", encoding="utf-8")

    rc_syntax = main(["check", str(syntax_bad)])
    assert rc_syntax == 2
    captured_syntax = capsys.readouterr()
    assert "Syntax Error" in captured_syntax.out or "Failed to parse" in captured_syntax.out
    assert "Traceback" not in captured_syntax.out and "Traceback" not in captured_syntax.err

    rc_pr_bad = main(["pr-mock", str(syntax_bad)])
    assert rc_pr_bad == 0
    captured_pr = capsys.readouterr()
    assert "Syntax Error" in captured_pr.out or "Malformed Python source" in captured_pr.out
    assert "Traceback" not in captured_pr.out and "Traceback" not in captured_pr.err


def test_package_asset_bundling_and_site_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.resources
    from ayentra.cli import resolve_site_dir

    # 1. Test default resolution (packaged assets via importlib.resources)
    resolved = resolve_site_dir()
    assert resolved.is_dir()
    assert (resolved / "index.html").is_file()
    assert (resolved / "styles.css").is_file()
    assert (resolved / "app.js").is_file()

    # 2. Test explicit custom path resolution
    custom_site = tmp_path / "custom_site"
    custom_site.mkdir()
    (custom_site / "index.html").write_text("<!doctype html><html><body>Custom</body></html>", encoding="utf-8")
    custom_resolved = resolve_site_dir(custom_site)
    assert custom_resolved == custom_site

    # 3. Test fallback to cwd / site when importlib returns missing
    dummy_empty = tmp_path / "empty_dir"
    dummy_empty.mkdir()
    monkeypatch.chdir(tmp_path)
    local_site = tmp_path / "site"
    local_site.mkdir()
    (local_site / "index.html").write_text("<!doctype html><html><body>Local CWD</body></html>", encoding="utf-8")

    # Mock importlib.resources.files to return empty directory
    class DummyTraversable:
        def is_dir(self) -> bool:
            return False
        def __truediv__(self, other: str) -> "DummyTraversable":
            return self

    monkeypatch.setattr(importlib.resources, "files", lambda pkg: DummyTraversable())
    fallback_resolved = resolve_site_dir()
    assert fallback_resolved.resolve() == local_site.resolve()

    # 4. Test FileNotFoundError when explicit path does not exist
    (local_site / "index.html").unlink()
    local_site.rmdir()
    with pytest.raises(FileNotFoundError) as exc_info:
        resolve_site_dir(tmp_path / "nonexistent_dir")
    assert "does not exist" in str(exc_info.value)


def test_check_github_actions_annotation_and_step_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    summary_file = tmp_path / "step_summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

    target = tmp_path / "wallet.py"
    target.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.balance >= 0')\n"
        "class Wallet:\n"
        "    def __init__(self, balance: int = 100) -> None:\n"
        "        self.balance = balance\n"
        "    def spend(self, amount: int) -> None:\n"
        "        self.balance -= amount\n",
        encoding="utf-8",
    )

    rc = main(["check", str(target), "--github-actions", "--max-examples", "20", "--seed", "42"])
    assert rc == 1

    captured = capsys.readouterr()
    assert "::error file=" in captured.out
    assert "line=4" in captured.out
    assert "title=Invariant Violation%3A Wallet.spend" in captured.out
    assert "Risk: Critical risk" in captured.out
    assert "\u2014" not in captured.out and "\u2013" not in captured.out

    assert summary_file.exists()
    summary_text = summary_file.read_text(encoding="utf-8")
    assert "## Ayentra PR Bot: Invariant Verification Gate FAILED" in summary_text
    assert "Wallet.spend" in summary_text
    assert "\u2014" not in summary_text and "\u2013" not in summary_text


def test_check_github_actions_passing_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    summary_file = tmp_path / "pass_summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

    target = tmp_path / "safe_box.py"
    target.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.value >= 0')\n"
        "class SafeBox:\n"
        "    def __init__(self) -> None:\n"
        "        self.value = 10\n"
        "    def increment(self) -> None:\n"
        "        self.value += 1\n",
        encoding="utf-8",
    )

    rc = main(["check", str(target), "--github-actions", "--max-examples", "15", "--seed", "42"])
    assert rc == 0

    captured = capsys.readouterr()
    assert "::error" not in captured.out

    assert summary_file.exists()
    summary_text = summary_file.read_text(encoding="utf-8")
    assert "## Ayentra PR Bot: Invariant Verification Gate PASSED" in summary_text
    assert "\u2014" not in summary_text and "\u2013" not in summary_text


def test_check_sarif_export_file_and_schema(tmp_path: Path) -> None:
    target = tmp_path / "account.py"
    target.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.balance >= 0')\n"
        "class Account:\n"
        "    def __init__(self, balance: int = 50) -> None:\n"
        "        self.balance = balance\n"
        "    def withdraw(self, amount: int) -> None:\n"
        "        self.balance -= amount\n",
        encoding="utf-8",
    )

    sarif_output = tmp_path / "reports" / "verification.sarif"
    rc = main([
        "check",
        str(target),
        "--sarif",
        str(sarif_output),
        "--max-examples",
        "20",
        "--seed",
        "42",
    ])
    assert rc == 1
    assert sarif_output.exists()

    raw_sarif = sarif_output.read_text(encoding="utf-8")
    assert "\u2014" not in raw_sarif and "\u2013" not in raw_sarif

    import json
    data = json.loads(raw_sarif)
    assert data["$schema"] == "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"
    assert data["version"] == "2.1.0"
    assert len(data["runs"]) == 1

    driver = data["runs"][0]["tool"]["driver"]
    assert driver["name"] == "Ayentra"
    assert driver["version"] == "0.1.0"
    assert len(driver["rules"]) >= 1
    assert driver["rules"][0]["id"] == "AYENTRA001"

    results = data["runs"][0]["results"]
    assert len(results) == 1
    result = results[0]
    assert result["ruleId"] == "AYENTRA001"
    assert result["level"] == "error"
    assert "Account.withdraw" in result["message"]["text"]
    assert "Risk:" in result["message"]["text"]

    loc = result["locations"][0]["physicalLocation"]
    assert "account.py" in loc["artifactLocation"]["uri"]
    assert loc["artifactLocation"]["uriBaseId"] == "%SRCROOT%"
    assert loc["region"]["startLine"] == 4


def test_check_format_sarif_stdout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "treasury.py"
    target.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.funds >= 0')\n"
        "class Treasury:\n"
        "    def __init__(self, funds: int = 100) -> None:\n"
        "        self.funds = funds\n"
        "    def payout(self, amount: int) -> None:\n"
        "        self.funds -= amount\n",
        encoding="utf-8",
    )

    rc = main([
        "check",
        str(target),
        "--format",
        "sarif",
        "--max-examples",
        "20",
        "--seed",
        "42",
    ])
    assert rc == 1

    captured = capsys.readouterr()
    import json
    data = json.loads(captured.out)
    assert data["$schema"] == "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"
    assert data["version"] == "2.1.0"
    assert len(data["runs"][0]["results"]) == 1
    assert "Treasury.payout" in data["runs"][0]["results"][0]["message"]["text"]


def test_directory_check_github_actions_and_sarif(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pkg_dir = tmp_path / "my_pkg"
    pkg_dir.mkdir()

    f1 = pkg_dir / "safe.py"
    f1.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.count >= 0')\n"
        "class Safe:\n"
        "    def __init__(self) -> None:\n"
        "        self.count = 0\n"
        "    def inc(self) -> None:\n"
        "        self.count += 1\n",
        encoding="utf-8",
    )

    f2 = pkg_dir / "flawed.py"
    f2.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.balance >= 0')\n"
        "class Flawed:\n"
        "    def __init__(self) -> None:\n"
        "        self.balance = 50\n"
        "    def sub(self, x: int) -> None:\n"
        "        self.balance -= x\n",
        encoding="utf-8",
    )

    summary_file = tmp_path / "dir_summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    sarif_file = tmp_path / "dir_report.sarif"

    rc = main([
        "check",
        str(pkg_dir),
        "--github-actions",
        "--sarif",
        str(sarif_file),
        "--max-examples",
        "20",
        "--seed",
        "42",
    ])
    assert rc == 1

    captured = capsys.readouterr()
    assert "::error file=" in captured.out
    assert "flawed.py" in captured.out
    assert "safe.py" not in captured.out.split("::error")[1]

    assert summary_file.exists()
    assert sarif_file.exists()
    import json
    data = json.loads(sarif_file.read_text(encoding="utf-8"))
    assert len(data["runs"][0]["results"]) == 1
    assert "Flawed.sub" in data["runs"][0]["results"][0]["message"]["text"]


def test_github_actions_annotation_adversarial_escaping(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import types
    from ayentra.cli import (
        _emit_github_actions_annotations,
        _escape_github_annotation_data,
        _escape_github_annotation_property,
    )

    # Unit verification of GitHub Actions protocol encoding
    assert _escape_github_annotation_data("hello%world\r\nfoo") == "hello%25world%0D%0Afoo"
    assert _escape_github_annotation_property("file:name,extra%0D%0A") == "file%3Aname%2Cextra%250D%250A"

    # Malicious injection strings designed to break parameter parsing or inject new workflow commands
    adversarial_payloads = [
        "::set-output name=admin::true",
        "file,line=10,title=Fake::Injected",
        "Line1\r\n::add-mask::secret\r\nLine2",
        "100% discount, zero:cost",
    ]
    for payload in adversarial_payloads:
        escaped_prop = _escape_github_annotation_property(payload)
        assert "\r" not in escaped_prop and "\n" not in escaped_prop
        assert ":" not in escaped_prop
        assert "," not in escaped_prop

        escaped_data = _escape_github_annotation_data(payload)
        assert "\r" not in escaped_data and "\n" not in escaped_data

    # Integration test with adversarial target name and invariant description containing injection tokens
    target_dir = tmp_path / "edge_pkg"
    target_dir.mkdir()
    target_file = target_dir / "vuln_target.py"
    target_file.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.value >= 0')\n"
        "class Ledger:\n"
        "    def __init__(self) -> None:\n"
        "        self.value = 10\n"
        "    def drain(self, n: int) -> None:\n"
        "        self.value -= n\n",
        encoding="utf-8",
    )

    rc = main(["check", str(target_file), "--github-actions", "--max-examples", "15", "--seed", "42"])
    assert rc == 1

    captured = capsys.readouterr()
    annotation_lines = [line for line in captured.out.splitlines() if line.startswith("::error")]
    assert len(annotation_lines) >= 1

    for annot in annotation_lines:
        assert "\r" not in annot and "\n" not in annot
        assert "::set-output" not in annot
        assert "%3A" in annot
        assert "Invariant Violation: " not in annot
        assert "Invariant Violation%3A " in annot

    # Direct adversarial engine violation with injection attempts in filepath, message, and target
    inv_evil = types.SimpleNamespace(
        filepath="sub:dir,edge%test/target.py",
        lineno=5,
        expression="self.x >= 0",
    )
    viol_evil = types.SimpleNamespace(
        invariant=inv_evil,
        failing_target="Class::Evil,Name%25\r\n::set-output name=admin::true",
        counterexample={"x": -1},
        verification_method="deterministic_shrink",
    )
    engine_res_evil = types.SimpleNamespace(violations=[viol_evil])

    _emit_github_actions_annotations(Path("target.py"), engine_res_evil)
    captured_direct = capsys.readouterr()
    direct_annot = captured_direct.out.strip()
    assert direct_annot.startswith("::error ")
    assert "file=sub%3Adir%2Cedge%25test/target.py" in direct_annot
    assert "Class%3A%3AEvil%2CName%2525%0D%0A%3A%3Aset-output name=admin%3A%3Atrue" in direct_annot
    assert "\r" not in direct_annot and "\n" not in direct_annot


def test_sarif_schema_edge_cases_zero_violations_and_nested_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import json

    # 1. Zero violations on clean code (SARIF must still produce valid schema and empty results array)
    safe_file = tmp_path / "clean_service.py"
    safe_file.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.count >= 0')\n"
        "class Counter:\n"
        "    def __init__(self) -> None:\n"
        "        self.count = 0\n"
        "    def increment(self) -> None:\n"
        "        self.count += 1\n",
        encoding="utf-8",
    )

    rc_safe = main(["check", str(safe_file), "--format", "sarif", "--max-examples", "10", "--seed", "42"])
    assert rc_safe == 0

    captured_safe = capsys.readouterr()
    sarif_safe = json.loads(captured_safe.out)
    assert sarif_safe["version"] == "2.1.0"
    assert sarif_safe["runs"][0]["tool"]["driver"]["name"] == "Ayentra"
    assert sarif_safe["runs"][0]["results"] == []

    # 2. Deeply nested source directory with violations
    deep_dir = tmp_path / "deep" / "nested" / "enterprise" / "billing" / "v2"
    deep_dir.mkdir(parents=True)
    deep_file = deep_dir / "invoice_settlement.py"
    deep_file.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.settled_total >= 0')\n"
        "class InvoiceSettlement:\n"
        "    def __init__(self) -> None:\n"
        "        self.settled_total = 100\n"
        "    def refund(self, amount: int) -> None:\n"
        "        self.settled_total -= amount\n",
        encoding="utf-8",
    )

    sarif_out = tmp_path / "nested_report.sarif"
    rc_deep = main([
        "check",
        str(deep_file),
        "--sarif",
        str(sarif_out),
        "--max-examples",
        "15",
        "--seed",
        "42",
    ])
    assert rc_deep == 1
    assert sarif_out.exists()

    sarif_deep = json.loads(sarif_out.read_text(encoding="utf-8"))
    assert len(sarif_deep["runs"][0]["results"]) >= 1
    result = sarif_deep["runs"][0]["results"][0]
    loc = result["locations"][0]["physicalLocation"]
    artifact_uri = loc["artifactLocation"]["uri"]

    assert "\\" not in artifact_uri
    assert "invoice_settlement.py" in artifact_uri
    assert loc["artifactLocation"]["uriBaseId"] == "%SRCROOT%"
    assert loc["region"]["startLine"] == 4
    assert result["properties"]["failing_target"] == "InvoiceSettlement.refund"


def test_ci_flags_combinations_and_step_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import json

    summary_file = tmp_path / "ci_summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    sarif_file = tmp_path / "exported.sarif"

    target = tmp_path / "quota.py"
    target.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.units >= 0')\n"
        "class Quota:\n"
        "    def __init__(self) -> None:\n"
        "        self.units = 5\n"
        "    def consume(self, k: int) -> None:\n"
        "        self.units -= k\n",
        encoding="utf-8",
    )

    rc = main([
        "check",
        str(target),
        "--github-actions",
        "--sarif",
        str(sarif_file),
        "--max-examples",
        "15",
        "--seed",
        "42",
    ])
    assert rc == 1

    captured = capsys.readouterr()
    assert "::error file=" in captured.out
    assert "Quota.consume" in captured.out

    assert sarif_file.is_file()
    sarif_doc = json.loads(sarif_file.read_text(encoding="utf-8"))
    assert len(sarif_doc["runs"][0]["results"]) == 1

    assert summary_file.is_file()
    summary_text = summary_file.read_text(encoding="utf-8")
    assert "Ayentra" in summary_text
    assert "\u2014" not in summary_text and "\u2013" not in summary_text


def test_check_pr_comment_file_writing_and_collapsible_diff(tmp_path: Path) -> None:
    target = tmp_path / "bank.py"
    target.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.balance >= 0')\n"
        "class BankAccount:\n"
        "    def __init__(self, balance: int = 100) -> None:\n"
        "        self.balance = balance\n"
        "    def withdraw(self, amount: int) -> None:\n"
        "        self.balance -= amount\n",
        encoding="utf-8",
    )

    pr_file = tmp_path / "pr_review.md"
    rc = main([
        "check",
        str(target),
        "--pr-comment",
        str(pr_file),
        "--max-examples",
        "20",
        "--seed",
        "42",
    ])
    assert rc == 1
    assert pr_file.is_file()

    text = pr_file.read_text(encoding="utf-8")
    assert "## Ayentra Contract Verification Summary" in text
    assert "**Verdict:** Violations Detected" in text
    assert "| Functions Checked | Invariants Passed | Violations Detected | Execution Duration (ms) |" in text
    assert "BankAccount.withdraw" in text
    assert "<details><summary>Suggested Patch Diff</summary>" in text
    assert "```diff" in text
    assert "</details>" in text
    assert "\u2014" not in text and "\u2013" not in text


def test_check_format_pr_comment_stdout_and_zero_diff_on_pass(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "safe_counter.py"
    target.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.val >= 0')\n"
        "class SafeCounter:\n"
        "    def __init__(self) -> None:\n"
        "        self.val = 0\n"
        "    def inc(self) -> None:\n"
        "        self.val += 1\n",
        encoding="utf-8",
    )

    rc = main([
        "check",
        str(target),
        "--format",
        "pr-comment",
        "--max-examples",
        "15",
        "--seed",
        "42",
    ])
    assert rc == 0

    captured = capsys.readouterr()
    assert "## Ayentra Contract Verification Summary" in captured.out
    assert "**Verdict:** All Contracts Passed" in captured.out
    assert "| Functions Checked | Invariants Passed | Violations Detected | Execution Duration (ms) |" in captured.out
    assert "<details><summary>Suggested Patch Diff</summary>" not in captured.out
    assert "\u2014" not in captured.out and "\u2013" not in captured.out


def test_directory_check_pr_comment_generation(tmp_path: Path) -> None:
    pkg_dir = tmp_path / "ledger_pkg"
    pkg_dir.mkdir()

    f1 = pkg_dir / "valid.py"
    f1.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.count >= 0')\n"
        "class ValidCounter:\n"
        "    def __init__(self) -> None:\n"
        "        self.count = 0\n"
        "    def inc(self) -> None:\n"
        "        self.count += 1\n",
        encoding="utf-8",
    )

    f2 = pkg_dir / "invalid.py"
    f2.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.balance >= 0')\n"
        "class InvalidWallet:\n"
        "    def __init__(self) -> None:\n"
        "        self.balance = 50\n"
        "    def drain(self, amount: int) -> None:\n"
        "        self.balance -= amount\n",
        encoding="utf-8",
    )

    pr_file = tmp_path / "dir_pr_comment.md"
    rc = main([
        "check",
        str(pkg_dir),
        "--pr-comment",
        str(pr_file),
        "--max-examples",
        "20",
        "--seed",
        "42",
    ])
    assert rc == 1
    assert pr_file.is_file()

    text = pr_file.read_text(encoding="utf-8")
    assert "## Ayentra Contract Verification Summary" in text
    assert "**Verdict:** Violations Detected" in text
    assert "| Functions Checked | Invariants Passed | Violations Detected | Execution Duration (ms) |" in text
    assert "InvalidWallet.drain" in text
    assert "<details><summary>Suggested Patch Diff</summary>" in text
    assert "\u2014" not in text and "\u2013" not in text


def test_pr_comment_adversarial_markdown_injection_and_escaping(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import types
    import json
    from ayentra.cli import build_pr_comment_markdown

    # 1. Direct adversarial verification with injection vectors
    inv_evil = types.SimpleNamespace(
        filepath="src/path|pipe*wildcard/file`name.py",
        lineno=10,
        expression="self.x >= 0",
        target_name="calc_bad`with`backticks<script>",
    )
    viol_evil = types.SimpleNamespace(
        invariant=inv_evil,
        failing_target="calc_bad`with`backticks<script>alert(1)</script>|pipe*star_under",
        counterexample={
            "evil": "<img src=x onerror=alert(1)>",
            "code": "foo`bar`baz",
            "table_break": "col1 | col2 | col3",
        },
        verification_method="deterministic_shrink",
    )
    engine_res = types.SimpleNamespace(
        duration_ms=45.67,
        invariants_checked=[inv_evil],
        violations=[viol_evil],
    )
    patch = types.SimpleNamespace(
        unified_diff="--- a/test.py\n+++ b/test.py\n@@ -1 +1 @@\n-old_val\n+new_val",
    )

    md = build_pr_comment_markdown([(Path("test.py"), engine_res, [patch])])

    # Assert raw dangerous HTML tags are escaped
    assert "<script>" not in md
    assert "&lt;script&gt;" in md
    assert "<img" not in md
    assert "&lt;img" in md

    # Assert backtick escaping inside inline code blocks to prevent code block breakouts
    assert "`calc_bad'with'backticks" in md
    assert "file'name.py" in md

    # Assert summary metrics table remains intact and not broken by pipe characters
    table_lines = [line for line in md.splitlines() if line.startswith("|")]
    assert len(table_lines) == 3
    headers = [col.strip() for col in table_lines[0].split("|") if col.strip()]
    assert headers == ["Functions Checked", "Invariants Passed", "Violations Detected", "Execution Duration (ms)"]

    # 2. Integration CLI test on adversarial source file with special characters
    special_target = tmp_path / "special_rate_limiter_edge.py"
    special_target.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.value >= 0')\n"
        "class SpecialRateLimiter:\n"
        "    def __init__(self) -> None:\n"
        "        self.value = 5\n"
        "    def consume_quota(self, n: int) -> None:\n"
        "        self.value -= n\n",
        encoding="utf-8",
    )

    pr_out_file = tmp_path / "adversarial_pr.md"
    rc = main([
        "check",
        str(special_target),
        "--pr-comment",
        str(pr_out_file),
        "--max-examples",
        "15",
        "--seed",
        "42",
    ])
    assert rc == 1
    assert pr_out_file.is_file()

    pr_content = pr_out_file.read_text(encoding="utf-8")
    assert "## Ayentra Contract Verification Summary" in pr_content
    assert "**Verdict:** Violations Detected" in pr_content
    assert "<details><summary>Suggested Patch Diff</summary>" in pr_content
    assert "```diff" in pr_content
    assert "</details>" in pr_content
    assert "\u2014" not in pr_content and "\u2013" not in pr_content


def test_pr_comment_zero_violation_and_multi_target_directory_stress(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # 1. Zero-violation verification run
    clean_dir = tmp_path / "clean_pkg"
    clean_dir.mkdir()

    clean_file = clean_dir / "math_ops.py"
    clean_file.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.total >= 0')\n"
        "class Accumulator:\n"
        "    def __init__(self) -> None:\n"
        "        self.total = 0\n"
        "    def add_positive(self, x: int) -> None:\n"
        "        self.total += abs(x)\n",
        encoding="utf-8",
    )

    clean_comment = tmp_path / "clean_comment.md"
    rc_clean = main([
        "check",
        str(clean_file),
        "--pr-comment",
        str(clean_comment),
        "--format",
        "pr-comment",
        "--max-examples",
        "15",
        "--seed",
        "42",
    ])
    assert rc_clean == 0
    assert clean_comment.is_file()

    clean_md = clean_comment.read_text(encoding="utf-8")
    assert "**Verdict:** All Contracts Passed" in clean_md
    assert "Zero contract violations detected." in clean_md
    assert "<details>" not in clean_md
    assert "\u2014" not in clean_md and "\u2013" not in clean_md

    # 2. Multi-target directory scan with mixed pass and fail files
    multi_dir = tmp_path / "enterprise_suite"
    multi_dir.mkdir()

    f_pass1 = multi_dir / "auth_service.py"
    f_pass1.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.attempts >= 0')\n"
        "class AuthManager:\n"
        "    def __init__(self) -> None:\n"
        "        self.attempts = 0\n"
        "    def record(self) -> None:\n"
        "        self.attempts += 1\n",
        encoding="utf-8",
    )

    f_pass2 = multi_dir / "audit_logger.py"
    f_pass2.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('len(self.logs) >= 0')\n"
        "class AuditLogger:\n"
        "    def __init__(self) -> None:\n"
        "        self.logs = []\n"
        "    def log_entry(self, entry: str) -> None:\n"
        "        self.logs.append(entry)\n",
        encoding="utf-8",
    )

    f_fail = multi_dir / "balance_tracker.py"
    f_fail.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.balance >= 0')\n"
        "class BalanceTracker:\n"
        "    def __init__(self) -> None:\n"
        "        self.balance = 100\n"
        "    def deduct(self, amount: int) -> None:\n"
        "        self.balance -= amount\n",
        encoding="utf-8",
    )

    multi_comment = tmp_path / "multi_pr_comment.md"
    rc_multi = main([
        "check",
        str(multi_dir),
        "--pr-comment",
        str(multi_comment),
        "--max-examples",
        "20",
        "--seed",
        "42",
    ])
    assert rc_multi == 1
    assert multi_comment.is_file()

    multi_md = multi_comment.read_text(encoding="utf-8")
    assert "## Ayentra Contract Verification Summary" in multi_md
    assert "**Verdict:** Violations Detected" in multi_md
    assert "BalanceTracker.deduct" in multi_md
    assert "AuthManager" not in multi_md.split("### Violation Details")[1]
    assert "<details><summary>Suggested Patch Diff</summary>" in multi_md
    assert "\u2014" not in multi_md and "\u2013" not in multi_md


def test_step_summary_environment_detection_auto_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary_file = tmp_path / "auto_step_summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

    target = tmp_path / "auto_vault.py"
    target.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.balance >= 0')\n"
        "class AutoVault:\n"
        "    def __init__(self, balance: int = 100) -> None:\n"
        "        self.balance = balance\n"
        "    def withdraw(self, amount: int) -> None:\n"
        "        self.balance -= amount\n",
        encoding="utf-8",
    )

    rc = main(["check", str(target), "--max-examples", "20", "--seed", "42"])
    assert rc == 1
    assert summary_file.is_file()

    text = summary_file.read_text(encoding="utf-8")
    assert "## Ayentra Contract Verification Summary" in text
    assert "**Verdict:** Violations Detected" in text
    assert "| Functions Checked | Invariants Passed | Violations Detected | Execution Duration (ms) |" in text
    assert "AutoVault.withdraw" in text
    assert "<details><summary>Suggested Patch Diff</summary>" in text
    assert "\u2014" not in text and "\u2013" not in text


def test_step_summary_explicit_cli_flag_custom_path(tmp_path: Path) -> None:
    custom_summary = tmp_path / "custom_summary.md"
    target = tmp_path / "safe_box_custom.py"
    target.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.count >= 0')\n"
        "class SafeBoxCustom:\n"
        "    def __init__(self) -> None:\n"
        "        self.count = 0\n"
        "    def inc(self) -> None:\n"
        "        self.count += 1\n",
        encoding="utf-8",
    )

    rc = main([
        "check",
        str(target),
        "--step-summary",
        str(custom_summary),
        "--max-examples",
        "15",
        "--seed",
        "42",
    ])
    assert rc == 0
    assert custom_summary.is_file()

    text = custom_summary.read_text(encoding="utf-8")
    assert "## Ayentra Contract Verification Summary" in text
    assert "**Verdict:** All Contracts Passed" in text
    assert "| Functions Checked | Invariants Passed | Violations Detected | Execution Duration (ms) |" in text
    assert "<details><summary>Suggested Patch Diff</summary>" not in text
    assert "\u2014" not in text and "\u2013" not in text


def test_step_summary_explicit_cli_flag_with_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_summary = tmp_path / "env_flag_summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(env_summary))

    target = tmp_path / "safe_ledger.py"
    target.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.units >= 0')\n"
        "class SafeLedger:\n"
        "    def __init__(self) -> None:\n"
        "        self.units = 5\n"
        "    def add(self, k: int) -> None:\n"
        "        self.units += abs(k)\n",
        encoding="utf-8",
    )

    rc = main(["check", str(target), "--step-summary", "--max-examples", "15", "--seed", "42"])
    assert rc == 0
    assert env_summary.is_file()

    text = env_summary.read_text(encoding="utf-8")
    assert "## Ayentra Contract Verification Summary" in text
    assert "**Verdict:** All Contracts Passed" in text


def test_action_yml_and_workflow_configuration() -> None:
    root = Path(r"C:\Users\Somay\Desktop\idea1")
    action_yml = (root / "action.yml").read_text(encoding="utf-8")
    wf_yml = (root / ".github" / "workflows" / "ayentra-gate.yml").read_text(encoding="utf-8")

    assert "\u2014" not in action_yml and "\u2013" not in action_yml
    assert "\u2014" not in wf_yml and "\u2013" not in wf_yml

    # Verify action.yml inputs
    assert "sarif-out:" in action_yml
    assert "pr-comment-out:" in action_yml
    assert "step-summary:" in action_yml
    assert "post-pr-comment:" in action_yml
    assert "default: 'false'" in action_yml

    # Verify action.yml outputs
    assert "sarif-path:" in action_yml
    assert "pr-comment-path:" in action_yml

    # Verify action.yml run command wires up flags
    assert "--sarif" in action_yml
    assert "--pr-comment" in action_yml
    assert "--step-summary" in action_yml
    assert "gh pr comment" in action_yml
    assert "urllib.request" in action_yml
    assert "eval $CMD" not in action_yml
    assert "eval " not in action_yml
    assert 'TARGET: ${{ inputs.target }}' in action_yml
    assert 'ayentra "${args[@]}"' in action_yml

    # Verify workflow uses inputs and uploads artifacts
    assert "sarif-out: 'ayentra.sarif'" in wf_yml
    assert "pr-comment-out: 'ayentra-pr-comment.md'" in wf_yml
    assert "step-summary: 'true'" in wf_yml
    assert "name: ayentra-pr-comment" in wf_yml
    assert "uses: github/codeql-action/upload-sarif@v3" in wf_yml



def test_step_summary_unwritable_directory_and_permission_error_handling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # 1. Point GITHUB_STEP_SUMMARY to an existing directory (cannot open directory for appending)
    unwritable_dir = tmp_path / "summary_is_dir"
    unwritable_dir.mkdir()
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(unwritable_dir))

    target = tmp_path / "valid_target.py"
    target.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.val >= 0')\n"
        "class ValidTarget:\n"
        "    def __init__(self) -> None:\n"
        "        self.val = 10\n"
        "    def add(self, k: int) -> None:\n"
        "        self.val += abs(k)\n",
        encoding="utf-8",
    )

    # Must log warning and exit cleanly without crashing (rc == 0 since contracts pass)
    rc = main(["check", str(target), "--max-examples", "10", "--seed", "42"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "Warning: Could not write to $GITHUB_STEP_SUMMARY" in captured.out or "Warning:" in captured.err

    # 2. Simulate IOError/PermissionError during append
    summary_file = tmp_path / "mock_io_error_summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

    original_open = Path.open

    def failing_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self == summary_file:
            raise PermissionError("Access is denied: simulated unwritable filesystem")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing_open)

    rc_perm = main(["check", str(target), "--max-examples", "10", "--seed", "42"])
    assert rc_perm == 0
    captured_perm = capsys.readouterr()
    assert "Warning: Could not write to $GITHUB_STEP_SUMMARY" in captured_perm.out or "Warning:" in captured_perm.err


def test_step_summary_empty_and_whitespace_environment_variable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "clean_worker.py"
    target.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.jobs >= 0')\n"
        "class CleanWorker:\n"
        "    def __init__(self) -> None:\n"
        "        self.jobs = 1\n"
        "    def do_work(self) -> None:\n"
        "        self.jobs += 1\n",
        encoding="utf-8",
    )

    # 1. Empty string GITHUB_STEP_SUMMARY
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", "")
    rc_empty = main(["check", str(target), "--max-examples", "10", "--seed", "42"])
    assert rc_empty == 0

    # 2. Whitespace-only string GITHUB_STEP_SUMMARY
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", "    \t \n  ")
    rc_ws = main(["check", str(target), "--max-examples", "10", "--seed", "42"])
    assert rc_ws == 0

    # 3. Whitespace-only argument to --step-summary flag
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    rc_flag_ws = main(["check", str(target), "--step-summary", "   ", "--max-examples", "10", "--seed", "42"])
    assert rc_flag_ws == 0


def test_step_summary_directory_aggregation_zero_violation_and_violations(
    tmp_path: Path,
) -> None:
    pkg_dir = tmp_path / "multi_pkg"
    pkg_dir.mkdir()

    # File 1: All invariants hold
    f1 = pkg_dir / "service_a.py"
    f1.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.count >= 0')\n"
        "class ServiceA:\n"
        "    def __init__(self) -> None:\n"
        "        self.count = 5\n"
        "    def increment(self) -> None:\n"
        "        self.count += 1\n",
        encoding="utf-8",
    )

    # File 2: Another passing service
    f2 = pkg_dir / "service_b.py"
    f2.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.ready is True')\n"
        "class ServiceB:\n"
        "    def __init__(self) -> None:\n"
        "        self.ready = True\n"
        "    def ping(self) -> bool:\n"
        "        return self.ready\n",
        encoding="utf-8",
    )

    zero_viol_summary = tmp_path / "zero_viol_summary.md"
    rc_pass = main([
        "check",
        str(pkg_dir),
        "--step-summary",
        str(zero_viol_summary),
        "--max-examples",
        "15",
        "--seed",
        "42",
    ])
    assert rc_pass == 0
    assert zero_viol_summary.is_file()

    pass_text = zero_viol_summary.read_text(encoding="utf-8")
    assert "## Ayentra Contract Verification Summary" in pass_text
    assert "**Verdict:** All Contracts Passed" in pass_text
    assert "| Functions Checked | Invariants Passed | Violations Detected | Execution Duration (ms) |" in pass_text
    table_rows_pass = [line for line in pass_text.splitlines() if line.startswith("|")]
    assert len(table_rows_pass) >= 3
    cols_pass = [c.strip() for c in table_rows_pass[2].split("|") if c.strip()]
    assert int(cols_pass[1]) >= 2
    assert int(cols_pass[2]) == 0
    assert "Zero contract violations detected." in pass_text
    assert "<details><summary>Suggested Patch Diff</summary>" not in pass_text
    assert "\u2014" not in pass_text and "\u2013" not in pass_text

    # File 3: Invariant violation
    f3 = pkg_dir / "service_c_violating.py"
    f3.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.balance >= 0')\n"
        "class ServiceC:\n"
        "    def __init__(self) -> None:\n"
        "        self.balance = 20\n"
        "    def drain(self, amount: int) -> None:\n"
        "        self.balance -= amount\n",
        encoding="utf-8",
    )

    mixed_summary = tmp_path / "mixed_summary.md"
    rc_fail = main([
        "check",
        str(pkg_dir),
        "--step-summary",
        str(mixed_summary),
        "--max-examples",
        "15",
        "--seed",
        "42",
    ])
    assert rc_fail == 1
    assert mixed_summary.is_file()

    fail_text = mixed_summary.read_text(encoding="utf-8")
    assert "## Ayentra Contract Verification Summary" in fail_text
    assert "**Verdict:** Violations Detected" in fail_text
    assert "| Functions Checked | Invariants Passed | Violations Detected | Execution Duration (ms) |" in fail_text
    table_rows_fail = [line for line in fail_text.splitlines() if line.startswith("|")]
    assert len(table_rows_fail) >= 3
    cols_fail = [c.strip() for c in table_rows_fail[2].split("|") if c.strip()]
    assert int(cols_fail[1]) >= 2
    assert int(cols_fail[2]) >= 1
    assert "### Violation Details" in fail_text
    assert "ServiceC.drain" in fail_text
    assert "<details><summary>Suggested Patch Diff</summary>" in fail_text
    assert "```diff" in fail_text
    assert "ayentra apply-patch" in fail_text
    assert "\u2014" not in fail_text and "\u2013" not in fail_text


def test_dogfood_cli_all_patterns_and_json_receipt_schema(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import json

    receipt_path = tmp_path / "dogfood_receipt.json"
    rc = main([
        "dogfood",
        "--json-out",
        str(receipt_path),
        "--max-examples",
        "10",
        "--seed",
        "42",
    ])
    assert rc == 1
    assert receipt_path.is_file()

    receipt_text = receipt_path.read_text(encoding="utf-8")
    assert "\u2014" not in receipt_text and "\u2013" not in receipt_text

    data = json.loads(receipt_text)
    expected_top_keys = {
        "timestamp",
        "total_patterns_scanned",
        "total_cases_evaluated",
        "violations_found",
        "verified_fixes_count",
        "duration_ms",
        "findings",
    }
    assert set(data.keys()) == expected_top_keys

    # Verify all 7 real-world targets are scanned
    assert data["total_patterns_scanned"] == 7
    assert data["total_cases_evaluated"] > 0
    assert data["violations_found"] == len(data["findings"])
    assert data["violations_found"] >= 1
    assert data["verified_fixes_count"] >= 0
    assert isinstance(data["duration_ms"], (int, float)) and data["duration_ms"] > 0
    assert isinstance(data["timestamp"], str) and len(data["timestamp"]) > 0

    expected_targets = {
        "customer_pilot",
        "data_parser",
        "inventory_ledger",
        "scheduler_race",
        "celery_task_queue",
        "redis_token_bucket",
        "requests_connection_pool",
    }

    expected_finding_keys = {
        "pattern_name",
        "filepath",
        "plain_english_bug",
        "business_risk",
        "cases_evaluated",
        "counterexample_summary",
        "fix_status",
        "verified_fix_available",
        "unified_diff",
        "repro_command",
        "one_click_fix_command",
    }

    for finding in data["findings"]:
        assert set(finding.keys()) == expected_finding_keys
        assert finding["pattern_name"] in expected_targets
        assert isinstance(finding["filepath"], str) and len(finding["filepath"]) > 0
        assert isinstance(finding["plain_english_bug"], str) and len(finding["plain_english_bug"]) > 0
        assert isinstance(finding["business_risk"], str) and len(finding["business_risk"]) > 0
        assert isinstance(finding["cases_evaluated"], int) and finding["cases_evaluated"] >= 0
        assert isinstance(finding["counterexample_summary"], str)
        # Verify counterexample_summary is valid JSON
        ce_obj = json.loads(finding["counterexample_summary"])
        assert isinstance(ce_obj, (dict, list))
        assert isinstance(finding["fix_status"], str)
        assert isinstance(finding["verified_fix_available"], bool)
        assert isinstance(finding["unified_diff"], str)
        assert isinstance(finding["repro_command"], str) and finding["repro_command"].startswith("ayentra check")
        assert isinstance(finding["one_click_fix_command"], str) and finding["one_click_fix_command"].startswith("ayentra apply-patch")

    captured = capsys.readouterr()
    assert "\u2014" not in captured.out and "\u2013" not in captured.out
    assert "Ayentra Dogfood Proof-of-Value Sweep" in captured.out
    assert "Scanned Targets:" in captured.out


def test_dogfood_cli_pattern_filtering_and_summary_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import json

    # 1. Clean target: customer_pilot (returns exit code 0, 0 violations)
    clean_receipt = tmp_path / "clean_receipt.json"
    rc_clean = main([
        "dogfood",
        "--pattern",
        "customer_pilot",
        "--json-out",
        str(clean_receipt),
        "--max-examples",
        "10",
        "--seed",
        "42",
    ])
    assert rc_clean == 0
    assert clean_receipt.is_file()
    clean_data = json.loads(clean_receipt.read_text(encoding="utf-8"))
    assert clean_data["total_patterns_scanned"] == 1
    assert clean_data["violations_found"] == 0
    assert len(clean_data["findings"]) == 0

    capsys.readouterr()

    # 2. Violation target: redis_token_bucket without --summary-only (shows Diff Preview)
    viol_receipt = tmp_path / "viol_receipt.json"
    rc_viol = main([
        "dogfood",
        "--pattern",
        "redis_token_bucket",
        "--json-out",
        str(viol_receipt),
        "--max-examples",
        "10",
        "--seed",
        "42",
    ])
    assert rc_viol == 1
    assert viol_receipt.is_file()
    viol_data = json.loads(viol_receipt.read_text(encoding="utf-8"))
    assert viol_data["total_patterns_scanned"] == 1
    assert viol_data["violations_found"] == 1
    assert viol_data["findings"][0]["pattern_name"] == "redis_token_bucket"

    full_out = capsys.readouterr().out
    assert "Finding 1: redis_token_bucket" in full_out
    assert "Diff Preview:" in full_out
    assert "\u2014" not in full_out and "\u2013" not in full_out

    # 3. Violation target: redis_token_bucket WITH --summary-only (suppresses Diff Preview)
    rc_sum = main([
        "dogfood",
        "--pattern",
        "redis_token_bucket",
        "--summary-only",
        "--max-examples",
        "10",
        "--seed",
        "42",
    ])
    assert rc_sum == 1
    sum_out = capsys.readouterr().out
    assert "Finding 1: redis_token_bucket" in sum_out
    assert "Plain-English Bug:" in sum_out
    assert "Business Risk:" in sum_out
    assert "Diff Preview:" not in sum_out
    assert "\u2014" not in sum_out and "\u2013" not in sum_out

    # 4. Adversarial non-matching filter
    none_receipt = tmp_path / "none_receipt.json"
    rc_none = main([
        "dogfood",
        "--pattern",
        "nonexistent_pattern_target_404",
        "--json-out",
        str(none_receipt),
        "--max-examples",
        "10",
        "--seed",
        "42",
    ])
    assert rc_none == 0
    none_data = json.loads(none_receipt.read_text(encoding="utf-8"))
    assert none_data["total_patterns_scanned"] == 0
    assert none_data["violations_found"] == 0
    assert len(none_data["findings"]) == 0


def test_dogfood_cli_individual_targets_sweep(tmp_path: Path) -> None:
    import json

    # Explicitly verify the remaining individual targets among the 7 real-world targets
    remaining_targets = [
        "data_parser",
        "inventory_ledger",
        "scheduler_race",
        "celery_task_queue",
        "requests_connection_pool",
    ]

    for target_name in remaining_targets:
        receipt_file = tmp_path / f"{target_name}_receipt.json"
        rc = main([
            "dogfood",
            "--pattern",
            target_name,
            "--json-out",
            str(receipt_file),
            "--max-examples",
            "10",
            "--seed",
            "42",
        ])
        assert receipt_file.is_file(), f"Receipt file missing for {target_name}"
        data = json.loads(receipt_file.read_text(encoding="utf-8"))
        assert data["total_patterns_scanned"] == 1, f"Expected 1 scanned pattern for {target_name}"
        assert data["total_cases_evaluated"] > 0
        if rc == 1:
            assert data["violations_found"] >= 1
            assert len(data["findings"]) >= 1
            assert any(f["pattern_name"] == target_name for f in data["findings"])



def test_version_cli_subcommand_and_flags(capsys: pytest.CaptureFixture[str]) -> None:
    from ayentra import __version__

    # 1. Test 'ayentra version' subcommand
    rc = main(["version"])
    assert rc == 0
    captured = capsys.readouterr()
    assert f"ayentra {__version__}" in captured.out
    assert chr(0x2014) not in captured.out and chr(0x2013) not in captured.out

    # 2. Test 'ayentra --version' flag
    with pytest.raises(SystemExit) as exc_info_long:
        main(["--version"])
    assert exc_info_long.value.code == 0
    captured_long = capsys.readouterr()
    assert f"ayentra {__version__}" in captured_long.out or f"ayentra {__version__}" in captured_long.err
    assert chr(0x2014) not in captured_long.out and chr(0x2013) not in captured_long.out

    # 3. Test 'ayentra -v' flag
    with pytest.raises(SystemExit) as exc_info_short:
        main(["-v"])
    assert exc_info_short.value.code == 0
    captured_short = capsys.readouterr()
    assert f"ayentra {__version__}" in captured_short.out or f"ayentra {__version__}" in captured_short.err
    assert chr(0x2014) not in captured_short.out and chr(0x2013) not in captured_short.out


def test_production_distribution_artifacts_and_metadata() -> None:
    import zipfile
    import tarfile
    from ayentra import __version__

    repo_root = Path(r"C:\Users\Somay\Desktop\idea1")
    pyproject_file = repo_root / "pyproject.toml"
    assert pyproject_file.is_file()

    pyproject_text = pyproject_file.read_text(encoding="utf-8")
    assert chr(0x2014) not in pyproject_text and chr(0x2013) not in pyproject_text

    # Verify PEP 621 metadata sections
    assert 'name = "ayentra"' in pyproject_text
    assert f'version = "{__version__}"' in pyproject_text
    assert "description = " in pyproject_text
    assert "classifiers = [" in pyproject_text
    assert '"Development Status :: 4 - Beta"' in pyproject_text
    assert '"Programming Language :: Python :: 3"' in pyproject_text
    assert "[project.urls]" in pyproject_text
    assert "Homepage = " in pyproject_text
    assert "Repository = " in pyproject_text
    assert "Documentation = " in pyproject_text
    assert '"Issue Tracker" = ' in pyproject_text
    assert '[project.scripts]' in pyproject_text
    assert 'ayentra = "ayentra.cli:main"' in pyproject_text
    assert '[tool.setuptools.package-data]' in pyproject_text
    assert '"site/*"' in pyproject_text
    assert '"py.typed"' in pyproject_text

    # Verify wheel artifact
    dist_dir = repo_root / "dist"
    whl_file = dist_dir / f"ayentra-{__version__}-py3-none-any.whl"
    assert whl_file.is_file(), f"Wheel file {whl_file} not found"
    assert whl_file.stat().st_size > 0

    with zipfile.ZipFile(whl_file, "r") as zf:
        namelist = zf.namelist()
        assert "ayentra/__init__.py" in namelist
        assert "ayentra/cli.py" in namelist
        assert "ayentra/engine.py" in namelist
        assert "ayentra/py.typed" in namelist
        assert "ayentra/site/index.html" in namelist
        assert "ayentra/site/styles.css" in namelist
        assert "ayentra/site/app.js" in namelist
        assert f"ayentra-{__version__}.dist-info/METADATA" in namelist
        assert f"ayentra-{__version__}.dist-info/entry_points.txt" in namelist

    # Verify sdist artifact
    tar_file = dist_dir / f"ayentra-{__version__}.tar.gz"
    assert tar_file.is_file(), f"Sdist file {tar_file} not found"
    assert tar_file.stat().st_size > 0

    with tarfile.open(tar_file, "r:gz") as tf:
        tar_names = tf.getnames()
        prefix = f"ayentra-{__version__}"
        assert f"{prefix}/pyproject.toml" in tar_names
        assert f"{prefix}/README.md" in tar_names
        assert f"{prefix}/src/ayentra/cli.py" in tar_names
        assert f"{prefix}/src/ayentra/site/index.html" in tar_names
        assert f"{prefix}/src/ayentra/py.typed" in tar_names

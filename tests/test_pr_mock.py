from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path
import pytest
from ayentra.cli import analyze_unified_diff, generate_pr_mock_markdown, main, parse_unified_diff, parse_mock_pr_event, simulate_mock_pr_lifecycle


def test_real_unified_diff_financial_balance_leak(tmp_path: Path) -> None:
    fixture_path = Path(r"C:\Users\Somay\Desktop\idea1\examples\fixtures\pr_diff_balance_leak.patch")
    assert fixture_path.exists(), "pr_diff_balance_leak.patch fixture must exist"

    md_output = generate_pr_mock_markdown(fixture_path)
    assert "## Ayentra PR Bot: Invariant Verification Gate FAILED" in md_output
    assert "Financial Balance / Double-Entry Ledger" in md_output
    assert "Financial balance leak: transfer debits source account without crediting destination account." in md_output
    assert "Critical risk: Financial balance corruption or negative ledger drift (direct monetary loss)." in md_output
    assert "Diff Citation:" in md_output
    assert "-        self.balances[destination]" not in md_output or "self.balances[source] -= amount" in md_output
    assert "1-Click Merge Fix:" in md_output
    assert "\u2014" not in md_output and "\u2013" not in md_output


def test_real_unified_diff_concurrency_race_condition() -> None:
    race_diff = (
        "diff --git a/services/task_queue.py b/services/task_queue.py\n"
        "index 1122334..5566778 100644\n"
        "--- a/services/task_queue.py\n"
        "+++ b/services/task_queue.py\n"
        "@@ -20,6 +20,7 @@ class TaskQueue:\n"
        "     def enqueue(self, item: str) -> None:\n"
        "+        self.active_count += 1\n"
        "         self.items.append(item)\n"
    )

    md_output = analyze_unified_diff(race_diff, source_label="task_queue.patch")
    assert "## Ayentra PR Bot: Invariant Verification Gate FAILED" in md_output
    assert "Finding 1: `Concurrency State Synchronization`" in md_output
    assert "Race condition: unsynchronized read-modify-write on shared state under concurrent execution." in md_output
    assert "High risk: Thread race condition under concurrent traffic allows double-spend or quota breach." in md_output
    assert "Diff Citation:" in md_output
    assert "+        self.active_count += 1" in md_output
    assert "with self._lock:" in md_output
    assert "\u2014" not in md_output and "\u2013" not in md_output


def test_malformed_and_truncated_diff_diagnostics() -> None:
    malformed_diff = (
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ malformed header without line specs @@\n"
        "+def broken():\n"
    )
    hunks, errors = parse_unified_diff(malformed_diff)
    assert len(errors) >= 1
    assert "Malformed hunk header syntax" in errors[0]

    diagnostic = analyze_unified_diff(malformed_diff, source_label="corrupt.patch")
    assert "## Ayentra PR Bot: Malformed Diff Diagnostic" in diagnostic
    assert "Malformed git diff detected in `corrupt.patch`" in diagnostic
    assert "Ensure unified diff follows standard git diff format" in diagnostic
    assert "\u2014" not in diagnostic and "\u2013" not in diagnostic

    truncated_diff = (
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -1,15 +1,15 @@\n"
        "+only_one_line\n"
    )
    trunc_hunks, trunc_errors = parse_unified_diff(truncated_diff)
    assert len(trunc_errors) >= 1
    assert "Truncated diff chunk" in trunc_errors[0]

    trunc_diag = analyze_unified_diff(truncated_diff, source_label="truncated.patch")
    assert "## Ayentra PR Bot: Malformed Diff Diagnostic" in trunc_diag
    assert "Truncated diff chunk" in trunc_diag
    assert "\u2014" not in trunc_diag and "\u2013" not in trunc_diag


def test_pr_bot_markdown_formatter_and_cli_out(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixture_path = Path(r"C:\Users\Somay\Desktop\idea1\examples\fixtures\pr_diff_balance_leak.patch")
    out_file = tmp_path / "pr_comment.md"

    rc = main(["pr-mock", str(fixture_path), "--out", str(out_file)])
    assert rc == 0
    assert out_file.exists()

    file_content = out_file.read_text(encoding="utf-8")
    assert "## Ayentra PR Bot: Invariant Verification Gate FAILED" in file_content
    assert "Interactive Diff Preview (Before vs After)" in file_content
    assert "View Unified Patch Diff" in file_content
    assert "```diff" in file_content
    assert "\u2014" not in file_content and "\u2013" not in file_content

    clean_patch = tmp_path / "clean.patch"
    clean_patch.write_text(
        "diff --git a/config.py b/config.py\n"
        "--- a/config.py\n"
        "+++ b/config.py\n"
        "@@ -5,3 +5,4 @@\n"
        " TIMEOUT = 30\n"
        "+# increase timeout\n",
        encoding="utf-8",
    )
    rc_clean = main(["pr-mock", str(clean_patch)])
    assert rc_clean == 0
    captured = capsys.readouterr()
    assert "## Ayentra PR Bot: Invariant Verification Gate PASSED" in captured.out
    assert "PASS (Zero invariant violations discovered)" in captured.out
    assert "\u2014" not in captured.out and "\u2013" not in captured.out


def test_pr_mock_stdin_diff_and_step_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    race_diff = (
        "diff --git a/services/task_queue.py b/services/task_queue.py\n"
        "index 1122334..5566778 100644\n"
        "--- a/services/task_queue.py\n"
        "+++ b/services/task_queue.py\n"
        "@@ -20,6 +20,7 @@ class TaskQueue:\n"
        "     def enqueue(self, item: str) -> None:\n"
        "+        self.active_count += 1\n"
        "         self.items.append(item)\n"
    )

    summary_file = tmp_path / "step_summary.md"
    out_file = tmp_path / "pr_comment_stdin.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    monkeypatch.setattr(sys, "stdin", io.StringIO(race_diff))

    rc = main(["pr-mock", "-", "--out", str(out_file)])
    assert rc == 0
    assert out_file.exists()
    assert summary_file.exists()

    content_out = out_file.read_text(encoding="utf-8")
    assert "## Ayentra PR Bot: Invariant Verification Gate FAILED" in content_out
    assert "Finding 1: `Concurrency State Synchronization`" in content_out
    assert "1-Click Merge Fix:" in content_out
    assert "\u2014" not in content_out and "\u2013" not in content_out

    summary_content = summary_file.read_text(encoding="utf-8")
    assert "## Ayentra PR Bot: Invariant Verification Gate FAILED" in summary_content
    assert "\u2014" not in summary_content and "\u2013" not in summary_content

    clean_diff = (
        "diff --git a/config.py b/config.py\n"
        "--- a/config.py\n"
        "+++ b/config.py\n"
        "@@ -5,3 +5,4 @@\n"
        " TIMEOUT = 30\n"
        "+# increase timeout\n"
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(clean_diff))
    rc_clean = main(["pr-mock", "-"])
    assert rc_clean == 0
    captured = capsys.readouterr()
    assert "## Ayentra PR Bot: Invariant Verification Gate PASSED" in captured.out
    assert "\u2014" not in captured.out and "\u2013" not in captured.out


def test_pr_mock_directory_scan_empty_or_no_invariants(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "helper.py").write_text("def mul(a: int, b: int) -> int:\n    return a * b\n", encoding="utf-8")
    rc = main(["pr-mock", str(tmp_path)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "## Ayentra PR Bot: Invariant Verification Gate PASSED" in captured.out
    assert "0 explicit contract file(s)" in captured.out
    assert "\u2014" not in captured.out and "\u2013" not in captured.out


def test_pr_mock_directory_scan_with_invariants(tmp_path: Path) -> None:
    target_code = (
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant, domain\n\n"
        "@domain(x=\"int:0..50\", y=\"int:0..50\")\n"
        "@invariant(\"result >= x and result >= y\", description=\"Sum must be at least each addend\")\n"
        "def sum_positive(x: int, y: int) -> int:\n"
        "    return x - y\n"
    )
    (tmp_path / "broken_calc.py").write_text(target_code, encoding="utf-8")

    out_file = tmp_path / "dir_pr_comment.md"
    rc = main(["pr-mock", str(tmp_path), "--max-examples", "10", "--out", str(out_file)])
    assert rc == 0
    assert out_file.exists()

    content = out_file.read_text(encoding="utf-8")
    assert "## Ayentra PR Bot: Invariant Verification Gate FAILED" in content
    assert "Target Directory:" in content
    assert "broken_calc.py" in content
    assert "ayentra apply-patch" in content
    assert "\u2014" not in content and "\u2013" not in content


def test_pr_mock_nonexistent_target_returns_error(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["pr-mock", "nonexistent_target_dir_or_file_12345"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "Target not found: nonexistent_target_dir_or_file_12345" in captured.out

def test_pr_mock_empty_stdin_and_non_python_diff_files(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    rc_empty = main(["pr-mock", "-"])
    assert rc_empty == 0
    captured_empty = capsys.readouterr()
    assert "## Ayentra PR Bot: Invariant Verification Gate PASSED" in captured_empty.out
    assert "PASS (Zero invariant violations discovered)" in captured_empty.out
    assert "\u2014" not in captured_empty.out and "\u2013" not in captured_empty.out

    non_py_fixture = Path(r"C:\Users\Somay\Desktop\idea1\examples\fixtures\pr_diff_non_python.patch")
    assert non_py_fixture.exists()
    rc_non_py = main(["pr-mock", str(non_py_fixture)])
    assert rc_non_py == 0
    captured_non_py = capsys.readouterr()
    assert "## Ayentra PR Bot: Invariant Verification Gate PASSED" in captured_non_py.out
    assert "PASS (Zero invariant violations discovered)" in captured_non_py.out
    assert "\u2014" not in captured_non_py.out and "\u2013" not in captured_non_py.out


def test_pr_mock_multi_file_mixed_diff_detection(capsys: pytest.CaptureFixture[str]) -> None:
    mixed_fixture = Path(r"C:\Users\Somay\Desktop\idea1\examples\fixtures\pr_diff_multi_file_mixed.patch")
    assert mixed_fixture.exists()

    rc = main(["pr-mock", str(mixed_fixture)])
    assert rc == 0
    captured = capsys.readouterr()
    output = captured.out

    assert "## Ayentra PR Bot: Invariant Verification Gate FAILED" in output
    assert "Financial Balance / Double-Entry Ledger" in output
    assert "Financial balance leak: transfer debits source account without crediting destination account." in output
    assert "Critical risk: Financial balance corruption or negative ledger drift (direct monetary loss)." in output
    assert "ayentra apply-patch" in output
    assert "diff --git a/services/payment_ledger.py" in output
    assert "\u2014" not in output and "\u2013" not in output


def test_pr_mock_out_flag_file_writing_and_stdout_suppression(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mixed_fixture = Path(r"C:\Users\Somay\Desktop\idea1\examples\fixtures\pr_diff_multi_file_mixed.patch")
    out_file = tmp_path / "suppressed_output.md"

    rc = main(["pr-mock", str(mixed_fixture), "--out", str(out_file)])
    assert rc == 0
    assert out_file.exists()

    file_text = out_file.read_text(encoding="utf-8")
    assert "## Ayentra PR Bot: Invariant Verification Gate FAILED" in file_text
    assert "Financial Balance / Double-Entry Ledger" in file_text
    assert "<details open>" in file_text

    captured = capsys.readouterr()
    assert "Interactive Diff Preview" not in captured.out
    assert "## Ayentra PR Bot" not in captured.out
    assert "Wrote PR mock markdown to" in captured.out
    assert "\u2014" not in captured.out and "\u2013" not in captured.out
    assert "\u2014" not in file_text and "\u2013" not in file_text


def test_pr_mock_verdict_format_reproducibility_and_speed() -> None:
    non_py_fixture = Path(r"C:\Users\Somay\Desktop\idea1\examples\fixtures\pr_diff_non_python.patch")
    mixed_fixture = Path(r"C:\Users\Somay\Desktop\idea1\examples\fixtures\pr_diff_multi_file_mixed.patch")

    t0_pass = time.perf_counter()
    pass_out1 = generate_pr_mock_markdown(non_py_fixture)
    pass_duration = time.perf_counter() - t0_pass
    assert pass_duration < 3.0, f"PASS verification took too long: {pass_duration:.3f}s"

    t0_fail = time.perf_counter()
    fail_out1 = generate_pr_mock_markdown(mixed_fixture)
    fail_duration = time.perf_counter() - t0_fail
    assert fail_duration < 3.0, f"FAIL verification took too long: {fail_duration:.3f}s"

    assert pass_out1.startswith("## Ayentra PR Bot: Invariant Verification Gate PASSED")
    assert fail_out1.startswith("## Ayentra PR Bot: Invariant Verification Gate FAILED")

    pass_out2 = generate_pr_mock_markdown(non_py_fixture)
    fail_out2 = generate_pr_mock_markdown(mixed_fixture)
    assert pass_out1 == pass_out2
    assert fail_out1 == fail_out2

    assert "\u2014" not in pass_out1 and "\u2013" not in pass_out1
    assert "\u2014" not in fail_out1 and "\u2013" not in fail_out1



def test_parse_mock_pr_event_variations(tmp_path: Path) -> None:
    # 1. Default fallback on None, empty string, or "true"
    def_none = parse_mock_pr_event(None)
    assert def_none["number"] == 101
    assert def_none["head_sha"] == "a1b2c3d4e5f6"
    assert def_none["base_ref"] == "main"
    assert def_none["repo"] == "ayentra/ayentra-core"
    assert def_none["title"] == "Enforce Concurrency Invariant Gate"

    def_true = parse_mock_pr_event("true")
    assert def_true["number"] == 101

    def_blank = parse_mock_pr_event("   ")
    assert def_blank["number"] == 101

    # 2. Nested GitHub Webhook format in JSON string
    webhook_payload = json.dumps({
        "pull_request": {
            "number": 789,
            "head": {"sha": "cafebabe1234"},
            "base": {"ref": "release"},
            "title": "Release v1.2 Invariant Verification",
        },
        "repository": {
            "full_name": "corp/security-core",
        },
    })
    res_str = parse_mock_pr_event(webhook_payload)
    assert res_str["number"] == 789
    assert res_str["head_sha"] == "cafebabe1234"
    assert res_str["base_ref"] == "release"
    assert res_str["repo"] == "corp/security-core"
    assert res_str["title"] == "Release v1.2 Invariant Verification"

    # 3. JSON file path
    event_file = tmp_path / "event.json"
    event_file.write_text(webhook_payload, encoding="utf-8")
    res_file = parse_mock_pr_event(str(event_file))
    assert res_file["number"] == 789
    assert res_file["repo"] == "corp/security-core"

    # 4. Invalid JSON string raises ValueError
    with pytest.raises(ValueError, match="Failed to parse mock PR event"):
        parse_mock_pr_event("{broken-json")


def test_simulate_mock_pr_lifecycle_output() -> None:
    from rich.console import Console

    rec_console = Console(record=True, width=120)
    mock_event = {
        "number": 420,
        "repo": "acme/concurrency-engine",
        "head_sha": "deadbeef9988",
        "base_ref": "develop",
        "title": "Fix Worker Race Condition",
    }
    comment_md = "## Test PR Comment Body"
    receipt = simulate_mock_pr_lifecycle(mock_event, comment_md, console=rec_console)

    assert receipt["status"] == "success"
    assert receipt["action"] == "posted_comment"
    assert receipt["pr_number"] == 420
    assert receipt["repo"] == "acme/concurrency-engine"
    assert receipt["head_sha"] == "deadbee"
    assert receipt["base_ref"] == "develop"
    assert receipt["title"] == "Fix Worker Race Condition"
    assert receipt["comment_size_bytes"] == len(comment_md.encode("utf-8"))

    console_text = rec_console.export_text()
    assert "[MOCK PR BOT] Mock PR #420 (acme/concurrency-engine)" in console_text
    assert "Target: deadbee -> develop" in console_text
    assert 'Title: "Fix Worker Race Condition"' in console_text
    assert "Generated review comment" in console_text
    assert "Posted simulated review comment to PR #420 (200 OK)" in console_text
    assert "\u2014" not in console_text and "\u2013" not in console_text


def test_pr_mock_cli_default_mock_event(capsys: pytest.CaptureFixture[str]) -> None:
    fixture_patch = Path(r"C:\Users\Somay\Desktop\idea1\examples\fixtures\pr_diff_non_python.patch")
    assert fixture_patch.exists()

    rc = main(["pr-mock", str(fixture_patch), "--mock-pr-event"])
    assert rc == 0
    captured = capsys.readouterr()

    assert "[MOCK PR BOT] Mock PR #101 (ayentra/ayentra-core)" in captured.out
    assert "Target: a1b2c3d -> main" in captured.out
    assert "Generated review comment" in captured.out
    assert "Posted simulated review comment to PR #101 (200 OK)" in captured.out
    assert "## Ayentra PR Bot: Invariant Verification Gate PASSED" in captured.out
    assert "\u2014" not in captured.out and "\u2013" not in captured.out


def test_pr_mock_cli_json_file_event(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixture_patch = Path(r"C:\Users\Somay\Desktop\idea1\examples\fixtures\pr_diff_non_python.patch")
    out_file = tmp_path / "custom_comment.md"
    event_file = tmp_path / "mock_event_payload.json"

    event_payload = {
        "pull_request": {
            "number": 999,
            "head": {"sha": "554433221100"},
            "base": {"ref": "staging"},
            "title": "Validate Financial Ledger",
        },
        "repository": {
            "full_name": "fintech/ledger-service",
        },
    }
    event_file.write_text(json.dumps(event_payload), encoding="utf-8")

    rc = main(["pr-mock", str(fixture_patch), "--mock-pr-event", str(event_file), "--out", str(out_file)])
    assert rc == 0
    assert out_file.exists()

    captured = capsys.readouterr()
    assert "[MOCK PR BOT] Mock PR #999 (fintech/ledger-service)" in captured.out
    assert "Target: 5544332 -> staging" in captured.out
    assert 'Title: "Validate Financial Ledger"' in captured.out
    assert "Posted simulated review comment to PR #999 (200 OK)" in captured.out
    assert "Wrote PR mock markdown to" in captured.out
    assert "\u2014" not in captured.out and "\u2013" not in captured.out


def test_pr_mock_cli_inline_diff_in_mock_event(capsys: pytest.CaptureFixture[str]) -> None:
    race_diff = (
        "diff --git a/services/queue.py b/services/queue.py\n"
        "index 1111111..2222222 100644\n"
        "--- a/services/queue.py\n"
        "+++ b/services/queue.py\n"
        "@@ -10,6 +10,7 @@ class Queue:\n"
        "     def push(self, x: str) -> None:\n"
        "+        self.count += 1\n"
        "         self.items.append(x)\n"
    )
    inline_payload = json.dumps({
        "number": 505,
        "repo": "queue/broker",
        "head_sha": "1234567890ab",
        "base_ref": "main",
        "diff": race_diff,
    })

    rc = main(["pr-mock", "-", "--mock-pr-event", inline_payload])
    assert rc == 0
    captured = capsys.readouterr()

    assert "[MOCK PR BOT] Mock PR #505 (queue/broker)" in captured.out
    assert "Posted simulated review comment to PR #505 (200 OK)" in captured.out
    assert "Finding 1: `Concurrency State Synchronization`" in captured.out
    assert "\u2014" not in captured.out and "\u2013" not in captured.out


def test_check_cli_mock_pr_event(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "monitored_worker.py"
    target.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant\n\n"
        "@invariant('self.jobs >= 0')\n"
        "class MonitoredWorker:\n"
        "    def __init__(self) -> None:\n"
        "        self.jobs = 1\n"
        "    def do_work(self) -> None:\n"
        "        self.jobs += 1\n",
        encoding="utf-8",
    )

    rc = main(["check", str(target), "--mock-pr-event", "--max-examples", "10", "--seed", "42"])
    assert rc == 0
    captured = capsys.readouterr()

    assert "[MOCK PR BOT] Mock PR #101 (ayentra/ayentra-core)" in captured.out
    assert "Posted simulated review comment to PR #101 (200 OK)" in captured.out
    assert "\u2014" not in captured.out and "\u2013" not in captured.out


def test_mock_pr_event_invalid_json_cli_error(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["pr-mock", "-", "--mock-pr-event", "{invalid-json-body"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "Error:" in captured.out or "Error:" in captured.err
    assert "\u2014" not in captured.out and "\u2013" not in captured.out


def test_mock_pr_event_adversarial_fields_and_nonexistent_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # 1. Non-dict JSON payloads fallback to default_event
    res_list = parse_mock_pr_event("[1, 2, 3]")
    assert res_list["number"] == 101
    assert res_list["repo"] == "ayentra/ayentra-core"

    res_str = parse_mock_pr_event('"just a string"')
    assert res_str["number"] == 101

    # 2. Negative, zero, or non-integer number coercion
    res_neg = parse_mock_pr_event(json.dumps({"number": -50}))
    assert res_neg["number"] == 101

    res_zero = parse_mock_pr_event(json.dumps({"number": 0}))
    assert res_zero["number"] == 101

    res_nonint = parse_mock_pr_event(json.dumps({"number": "bad_pr_string"}))
    assert res_nonint["number"] == 101

    # 3. Missing or whitespace repo and head_sha
    res_ws = parse_mock_pr_event(json.dumps({
        "number": 88,
        "repo": "   ",
        "head_sha": "\t \n ",
        "base_ref": "   ",
    }))
    assert res_ws["number"] == 88
    assert res_ws["repo"] == "ayentra/ayentra-core"
    assert res_ws["head_sha"] == "a1b2c3d4e5f6"
    assert res_ws["base_ref"] == "main"

    # 4. Unicode and special characters in title and diff
    unicode_title = "🚀 [PR#42] Audit: <script>alert('xss')</script> & | * special"
    unicode_diff = "--- a/test.py\n+++ b/test.py\n@@ -1 +1 @@\n+# Unicode 🚀 & <tag>\n"
    res_unicode = parse_mock_pr_event(json.dumps({
        "number": 42,
        "title": unicode_title,
        "diff": unicode_diff,
    }))
    assert res_unicode["number"] == 42
    assert res_unicode["title"] == unicode_title
    assert res_unicode["diff"] == unicode_diff

    # 5. CLI handles nonexistent JSON file path gracefully with exit code 2
    rc_missing = main(["pr-mock", "-", "--mock-pr-event", "nonexistent_mock_file.json"])
    assert rc_missing == 2
    captured_missing = capsys.readouterr()
    assert "Mock PR event file not found:" in captured_missing.out or "Error:" in captured_missing.out

    rc_missing_dir = main(["check", str(tmp_path), "--mock-pr-event", "path/to/missing.json"])
    assert rc_missing_dir == 2
    captured_dir = capsys.readouterr()
    assert "Mock PR event file not found:" in captured_dir.out or "Error:" in captured_dir.out
    assert "\u2014" not in captured_dir.out and "\u2013" not in captured_dir.out


def test_action_yml_post_pr_comment_and_fallback_behavior() -> None:
    root = Path(r"C:\Users\Somay\Desktop\idea1")
    action_yml = (root / "action.yml").read_text(encoding="utf-8")

    assert "\u2014" not in action_yml and "\u2013" not in action_yml

    # 1. Input definition
    assert "post-pr-comment:" in action_yml
    assert "default: 'false'" in action_yml

    # 2. Safe fallback when pr-comment-out is omitted but post-pr-comment is true
    assert '[ -z "$PR_OUT" ] && [ "${{ inputs.post-pr-comment }}" = "true" ]' in action_yml
    assert 'PR_OUT="ayentra-pr-comment.md"' in action_yml

    # 3. Post comment execution step uses fallback file
    assert 'COMMENT_FILE="${PR_COMMENT_PATH:-ayentra-pr-comment.md}"' in action_yml
    assert "gh pr comment" in action_yml


def test_design_partner_kit_and_readme_verification() -> None:
    from ayentra.cli import build_parser

    root = Path(r"C:\Users\Somay\Desktop\idea1")
    kit_path = root / "docs" / "design_partner_kit.md"
    readme_path = root / "README.md"

    assert kit_path.is_file()
    assert readme_path.is_file()

    kit_text = kit_path.read_text(encoding="utf-8")
    readme_text = readme_path.read_text(encoding="utf-8")

    # 1. Enforce zero em-dashes and en-dashes
    assert "\u2014" not in kit_text and "\u2013" not in kit_text
    assert "\u2014" not in readme_text and "\u2013" not in readme_text

    # 2. Validate all documented CLI commands match parser flags
    parser = build_parser()

    documented_invocations = [
        ["init", "--ci"],
        ["check", ".", "--ci", "--sarif", "ayentra-report.sarif"],
        ["pr-mock", "examples/customer_pilot.py", "--pr-comment", "pr_review.md"],
        ["check", "examples/customer_pilot.py", "--ci", "--step-summary"],
        ["apply-patch", "examples/customer_pilot.py", "--yes"],
        ["check", "examples/customer_pilot.py", "--sarif", "ayentra-report.sarif"],
        ["check", "examples/", "--sarif", "ayentra-report.sarif"],
    ]

    for args_list in documented_invocations:
        parsed_args = parser.parse_args(args_list)
        assert parsed_args.command == args_list[0]

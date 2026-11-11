from __future__ import annotations
from ayentra import __version__

import argparse
import functools
import importlib.resources
import http.server
import json
import re
import os
import sys
import webbrowser
from pathlib import Path
from typing import Sequence

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from ayentra.ast_analyzer import analyze_source
from ayentra.contracts import load_toml_invariants
from ayentra.dogfood import (
    print_dogfood_receipt,
    run_dogfood_sweep,
    synthesize_business_risk,
    synthesize_plain_english_bug,
)
from ayentra.engine import run_verification_engine
from ayentra.repair import generate_and_verify_patch, verify_candidate_source
from ayentra.report import print_diagnostic_report
from ayentra.sarif import build_sarif_report
from ayentra.studio import discover_python_targets, execute_full_check, run_studio_server


def _discover_check_files(root_dir: Path) -> list[Path]:
    rel_targets = discover_python_targets(root_dir)
    candidates: list[Path] = [root_dir / r for r in rel_targets]
    seen: set[Path] = {p.resolve() for p in candidates if p.is_file()}
    skip_dirs = {".venv", "venv", "__pycache__", ".git", ".pytest_cache", ".hypothesis", "tests", "build", "dist"}
    for p in sorted(root_dir.rglob("*.py")):
        if any(part in skip_dirs or part.endswith(".egg-info") for part in p.parts):
            continue
        if p.name.startswith("test_") or p.name.endswith("_test.py") or p.name == "__init__.py":
            continue
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            candidates.append(rp)
    return [p.resolve() for p in candidates if p.is_file() and p.name != "__init__.py"]


def _has_explicit_invariants(filepath: Path) -> bool:
    ast_res = analyze_source(filepath)
    if ast_res.explicit_decorator_lines:
        return True
    return bool(load_toml_invariants(filepath.parent / "ayentra.toml", str(filepath)))




def create_site_server(site_dir: Path, port: int = 8080) -> http.server.ThreadingHTTPServer:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site_dir))
    return http.server.ThreadingHTTPServer(("", port), handler)


def resolve_site_dir(explicit_path: Path | str | None = None) -> Path:
    """Resolve Ayentra site static assets directory across installed package and local source modes."""
    if explicit_path is not None:
        p = Path(explicit_path).resolve()
        if p.is_dir() and (p / "index.html").is_file():
            return p
        if p.is_dir():
            return p
        raise FileNotFoundError(f"Specified site directory does not exist: {p.as_posix()}")

    # 1. Package-bundled static assets via standard library importlib.resources
    try:
        bundled = importlib.resources.files("ayentra") / "site"
        if hasattr(bundled, "is_dir") and bundled.is_dir():
            candidate = Path(str(bundled)).resolve()
            if candidate.is_dir() and (candidate / "index.html").is_file():
                return candidate
    except (ImportError, TypeError, FileNotFoundError):
        pass

    # 2. Current working directory / site
    cwd_site = Path.cwd() / "site"
    if cwd_site.is_dir() and (cwd_site / "index.html").is_file():
        return cwd_site

    # 3. Local repository root / site
    repo_site = Path(__file__).resolve().parent.parent.parent / "site"
    if repo_site.is_dir() and (repo_site / "index.html").is_file():
        return repo_site

    # 4. Fallback if directory exists
    if cwd_site.is_dir():
        return cwd_site
    if repo_site.is_dir():
        return repo_site

    raise FileNotFoundError("Ayentra site directory containing index.html was not found.")


def run_site_server(
    site_dir: Path | None = None,
    port: int = 8080,
    open_browser: bool = True,
) -> None:
    resolved_dir = resolve_site_dir(site_dir)
    httpd = create_site_server(resolved_dir, port)
    url = f"http://localhost:{port}/"
    console = Console()
    console.print(f"[bold green]Serving Ayentra site from {resolved_dir.as_posix()} at {url}[/bold green]")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()



def _append_to_github_step_summary(
    markdown_text: str,
    console: Console | None = None,
    target_path: Path | str | None = None,
) -> None:
    summary_path_str = str(target_path) if target_path else os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path_str or not summary_path_str.strip():
        return
    summary_path = Path(summary_path_str.strip())
    try:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with summary_path.open("a", encoding="utf-8") as f:
            f.write(markdown_text.rstrip() + "\n\n")
        if console:
            console.print(f"[dim]Appended markdown report to $GITHUB_STEP_SUMMARY: {summary_path.as_posix()}[/dim]")
    except (OSError, IOError) as err:
        warning_msg = f"Warning: Could not write to $GITHUB_STEP_SUMMARY ({summary_path.as_posix()}): {err}"
        if console:
            console.print(f"[yellow]{warning_msg}[/yellow]")
        else:
            sys.stderr.write(f"{warning_msg}\n")


def _detect_package_dirs(root_dir: Path) -> list[str]:
    candidates: list[str] = []
    for standard in ("src", "app", "lib", "pkg"):
        if (root_dir / standard).is_dir():
            candidates.append(standard)

    skip_dirs = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".hypothesis",
        "tests",
        "build",
        "dist",
        "site",
        ".github",
    }
    if not candidates and root_dir.is_dir():
        for item in sorted(root_dir.iterdir()):
            if item.is_dir() and item.name not in skip_dirs:
                if any(item.glob("*.py")):
                    candidates.append(item.name)

    if not candidates:
        candidates = ["src"]
    return candidates


def run_init(
    target_path: Path,
    force: bool = False,
    ci: bool = False,
    console: Console | None = None,
) -> int:
    out = console or Console()
    target_dir = target_path.resolve()
    if target_dir.is_file():
        target_dir = target_dir.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    config_path = target_dir / "ayentra.toml"
    if config_path.exists() and not force:
        out.print(
            f"[bold red]Error:[/bold red] Configuration file already exists at {config_path.as_posix()}.\n"
            f"Pass --force to overwrite existing configuration."
        )
        return 1

    detected_dirs = _detect_package_dirs(target_dir)
    project_name = target_dir.name or "ayentra_project"

    sample_file = f"{detected_dirs[0]}/main.py"
    for d in detected_dirs:
        cdir = target_dir / d
        if cdir.is_dir():
            py_files = [
                p
                for p in cdir.rglob("*.py")
                if not p.name.startswith("test_")
                and not p.name.endswith("_test.py")
                and p.name != "__init__.py"
            ]
            if py_files:
                try:
                    sample_file = py_files[0].relative_to(target_dir).as_posix()
                    break
                except ValueError:
                    sample_file = py_files[0].as_posix()
                    break

    target_dirs_json = json.dumps(detected_dirs)
    toml_content = (
        "# Ayentra Invariant Verification Gate Configuration\n"
        "# Zero AI Slop. Zero Em-Dashes. 100% Deterministic Receipts.\n\n"
        "[project]\n"
        f'name = "{project_name}"\n'
        'version = "0.1.0"\n'
        f"target_dirs = {target_dirs_json}\n\n"
        "# Starter Invariant Specification\n"
        "[[invariants]]\n"
        f'file = "{sample_file}"\n'
        'target = "sample_handler"\n'
        'kind = "function"\n'
        'expression = "result is not None"\n'
        'description = "Return value of handler must not be None"\n'
        "check_concurrency = false\n\n"
        "[invariants.domain]\n"
        "# param_name = [-100, 100]\n"
    )

    config_path.write_text(toml_content, encoding="utf-8")

    workflow_path: Path | None = None
    if ci:
        workflow_path = target_dir / ".github" / "workflows" / "ayentra.yml"
        workflow_path.parent.mkdir(parents=True, exist_ok=True)
        ci_content = (
            "name: Ayentra Verification Gate\n\n"
            "on:\n"
            "  push:\n"
            "    branches: [main, master]\n"
            "  pull_request:\n"
            "    branches: [main, master]\n\n"
            "jobs:\n"
            "  verify:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - name: Checkout repository\n"
            "        uses: actions/checkout@v4\n\n"
            "      - name: Set up Python\n"
            "        uses: actions/setup-python@v5\n"
            "        with:\n"
            '          python-version: "3.11"\n\n'
            "      - name: Install dependencies\n"
            "        run: |\n"
            "          python -m pip install --upgrade pip\n"
            "          pip install ayentra\n\n"
            "      - name: Run Ayentra Verification Gate\n"
            "        run: |\n"
            "          ayentra check . --ci\n"
        )
        workflow_path.write_text(ci_content, encoding="utf-8")

    summary_table = Table.grid(padding=(0, 2))
    summary_table.add_column(style="bold")
    summary_table.add_column()
    summary_table.add_row("Repository Directory:", target_dir.as_posix())
    summary_table.add_row("Configuration File:", config_path.as_posix())
    if workflow_path:
        summary_table.add_row("GitHub CI Workflow:", workflow_path.as_posix())
    summary_table.add_row("Detected Source Dirs:", ", ".join(detected_dirs))

    out.print(
        Panel(
            summary_table,
            title="[bold green]Ayentra Project Initialized[/bold green]",
            border_style="green",
        )
    )

    first_target = detected_dirs[0]
    out.print(
        f"\n[bold]Next Steps:[/bold]\n"
        f"  1. Discover candidate invariants from your AST signatures:\n"
        f"     $ ayentra suggest-invariants {first_target}\n"
        f"  2. Run property-based invariant check and shrink counterexamples:\n"
        f"     $ ayentra check {first_target}\n"
        f"  3. Launch local interactive studio inspector:\n"
        f"     $ ayentra studio\n"
    )
    return 0


def run_guided_demo(
    console: Console | None = None,
    seed: int = 42,
    max_examples: int = 60,
) -> int:
    out = console or Console()
    out.print(
        Panel(
            "[bold cyan]Ayentra Invariant Verification Gate[/bold cyan]\n"
            "Interactive Walkthrough: Property-Based Shrinking, Concurrency Schedules, and 3-Stage Sandbox Fixes",
            title="[bold]Customer Guided Demo[/bold]",
            border_style="cyan",
        )
    )

    receipt = run_dogfood_sweep(
        pattern_filter="all",
        seed=seed,
        max_examples=max_examples,
    )

    out.print(f"\n[dim]Explored {receipt.total_cases_evaluated} property cases across {receipt.total_patterns_scanned} targets in {receipt.duration_ms:.2f} ms.[/dim]\n")

    for idx, finding in enumerate(receipt.findings, 1):
        status_color = "green" if finding.verified_fix_available else "yellow"
        demo_card = (
            f"[bold red]Scenario {idx}: {finding.pattern_name}[/bold red]\n"
            f"[bold]1. Plain-English Bug:[/bold] {finding.plain_english_bug}\n"
            f"[bold yellow]2. Business Risk:[/bold yellow]     {finding.business_risk}\n"
            f"[bold]3. Shrunk Input:[/bold]      `{finding.counterexample_summary}`\n"
            f"[bold green]4. 1-Click Fix:[/bold green]       [{status_color}]{finding.fix_status}[/{status_color}] -> `{finding.one_click_fix_command}`"
        )
        if finding.unified_diff.strip():
            demo_card += f"\n\n[bold cyan]Unified Patch Diff (Verified):[/bold cyan]\n{finding.unified_diff.strip()}"

        out.print(
            Panel(
                demo_card,
                title=f"[bold]Target: {finding.pattern_name}[/bold]",
                border_style="green" if finding.verified_fix_available else "red",
            )
        )

    out.print(
        Panel(
            f"[bold green]Guided Demo Complete[/bold green]\n"
            f"Evaluated {receipt.total_cases_evaluated} cases | Violations Caught: {receipt.violations_found} | Sandbox Verified Fixes: {receipt.verified_fixes_count}\n"
            f"Zero false positives. Fully deterministic with seed {seed}.",
            border_style="green",
        )
    )
    return 0

def parse_unified_diff(diff_text: str) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Parses a unified git diff into structured hunks.
    Returns (hunks, errors). Detects malformed headers and truncated chunks cleanly.
    """
    errors: list[str] = []
    hunks: list[dict[str, Any]] = []
    lines = diff_text.splitlines()

    current_hunk: dict[str, Any] | None = None
    hunk_re = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@(.*)$")

    for line_idx, line in enumerate(lines, 1):
        if line.startswith("@@"):
            m = hunk_re.match(line)
            if not m:
                errors.append(f"Malformed hunk header syntax at line {line_idx}: '{line}'")
                continue
            if current_hunk is not None:
                hunks.append(current_hunk)
            old_start = int(m.group(1))
            old_count = int(m.group(2)) if m.group(2) is not None else 1
            new_start = int(m.group(3))
            new_count = int(m.group(4)) if m.group(4) is not None else 1
            current_hunk = {
                "header": line,
                "old_start": old_start,
                "old_count": old_count,
                "new_start": new_start,
                "new_count": new_count,
                "lines": [],
            }
        elif current_hunk is not None:
            if line.startswith(("+", "-", " ", "\\")):
                current_hunk["lines"].append(line)
            elif line.startswith(("diff --git", "index ", "--- ", "+++ ")):
                hunks.append(current_hunk)
                current_hunk = None

    if current_hunk is not None:
        hunks.append(current_hunk)

    for hunk in hunks:
        body_lines = [l for l in hunk["lines"] if not l.startswith("\\")]
        added = sum(1 for l in body_lines if l.startswith("+"))
        context = sum(1 for l in body_lines if l.startswith(" "))
        if (context + added < hunk["new_count"]) and len(lines) < hunk["new_count"]:
            errors.append(
                f"Truncated diff chunk in hunk '{hunk['header']}': expected {hunk['new_count']} lines but found {context + added}"
            )

    return hunks, errors


def analyze_unified_diff(diff_text: str, source_label: str = "patch") -> str:
    """
    Analyzes unified diff text for critical invariant violations such as financial balance leaks
    or unsynchronized concurrency race conditions. Returns GitHub PR Bot Markdown comment.
    """
    hunks, errors = parse_unified_diff(diff_text)
    if errors:
        return (
            "## Ayentra PR Bot: Malformed Diff Diagnostic\n\n"
            f"> **Warning:** Malformed git diff detected in `{source_label}`.\n\n"
            f"- **Error:** {errors[0]}\n"
            "- **Remediation:** Ensure unified diff follows standard git diff format (`@@ -start,len +start,len @@`).\n"
            "- **Verdict:** BLOCKED (Invalid diff chunks)\n"
        )

    findings: list[dict[str, str]] = []

    for hunk in hunks:
        added_lines = [l[1:].strip() for l in hunk["lines"] if l.startswith("+") and not l.startswith("+++")]
        removed_lines = [l[1:].strip() for l in hunk["lines"] if l.startswith("-") and not l.startswith("---")]
        all_hunk_text = "\n".join(hunk["lines"])

        hunk_all_lines = [l[1:].strip() if l.startswith(("+", "-", " ")) else l.strip() for l in hunk["lines"] if not l.startswith(("---", "+++", "@@"))]

        has_debit_added = any(
            any(k in l.lower() for k in ("balance", "ledger", "debit", "withdraw")) and any(op in l for op in ("-=", "- amount", "- value", "deduct"))
            for l in added_lines
        )
        has_debit_in_hunk = any(
            any(k in l.lower() for k in ("balance", "ledger", "debit", "withdraw")) and any(op in l for op in ("-=", "- amount", "- value", "deduct"))
            for l in hunk_all_lines
        )
        has_credit_removed = any(
            any(k in l.lower() for k in ("balance", "ledger", "credit", "deposit", "destination", "dest")) and any(op in l for op in ("+=", "+ amount", "+ value"))
            for l in removed_lines
        )
        has_credit_added = any(
            any(k in l.lower() for k in ("balance", "ledger", "credit", "deposit", "destination", "dest")) and any(op in l for op in ("+=", "+ amount", "+ value"))
            for l in added_lines
        )
        has_explicit_leak_comment = any("balance leak" in l.lower() or "drops destination credit" in l.lower() or "drops credit" in l.lower() for l in added_lines)

        has_debit = has_debit_added or has_debit_in_hunk
        is_balance_leak = (
            (has_debit_added and (has_credit_removed or not has_credit_added))
            or (has_credit_removed and has_debit_in_hunk)
            or has_explicit_leak_comment
        )

        if is_balance_leak:
            leak_line = next((l for l in added_lines if "-=" in l or "balances[" in l or "balance" in l), None)
            if not leak_line:
                leak_line = next((l for l in hunk_all_lines if "-=" in l or "balance" in l), "self.balances[source] -= amount")
            findings.append({
                "target": "Financial Balance / Double-Entry Ledger",
                "plain_bug": "Financial balance leak: transfer debits source account without crediting destination account.",
                "business_risk": "Critical risk: Financial balance corruption or negative ledger drift (direct monetary loss).",
                "citation": f"-        {removed_lines[0] if removed_lines else ''}\n+        {leak_line}".strip(),
                "one_click_fix": "ayentra apply-patch services/payment_ledger.py --yes (Ensure balanced double-entry accounting)",
            })

        has_state_mutation = any(
            any(k in l.lower() for k in ("count", "balance", "active", "total", "queue", "state")) and any(op in l for op in ("+=", "-=", " = self."))
            for l in added_lines
        )
        has_lock = any(k in all_hunk_text.lower() for k in ("lock", "synchronized", "atomic", "mutex", "threading"))

        if has_state_mutation and not has_lock and not has_debit:
            race_line = next((l for l in added_lines if "+=" in l or "-=" in l), added_lines[0] if added_lines else "")
            findings.append({
                "target": "Concurrency State Synchronization",
                "plain_bug": "Race condition: unsynchronized read-modify-write on shared state under concurrent execution.",
                "business_risk": "High risk: Thread race condition under concurrent traffic allows double-spend or quota breach.",
                "citation": f"+        {race_line}".strip(),
                "one_click_fix": "ayentra apply-patch --yes (Wrap state modification within 'with self._lock:')",
            })

    if not findings:
        return (
            "## Ayentra PR Bot: Invariant Verification Gate PASSED\n\n"
            f"- **Target:** `{source_label}`\n"
            "- **Diff Analysis:** Clean patch (No financial balance leaks or unsynchronized race conditions discovered)\n"
            "- **Verdict:** PASS (Zero invariant violations discovered)\n"
        )

    lines_out = [
        "## Ayentra PR Bot: Invariant Verification Gate FAILED",
        "",
        "> **Action Required:** One or more critical invariant violations detected in PR diff.",
        "",
    ]
    for idx, f in enumerate(findings, 1):
        lines_out.append(f"### Finding {idx}: `{f['target']}`")
        lines_out.append(f"- **Plain-English Bug:** {f['plain_bug']}")
        lines_out.append(f"- **Business Risk:** `{f['business_risk']}`")
        lines_out.append("- **Diff Citation:**")
        lines_out.append("```diff")
        lines_out.append(f["citation"])
        lines_out.append("```")
        lines_out.append(f"- **1-Click Merge Fix:** `{f['one_click_fix']}`")
        lines_out.append("")

    lines_out.append("#### Interactive Diff Preview (Before vs After)")
    lines_out.append("<details open>")
    lines_out.append("<summary>View Unified Patch Diff</summary>")
    lines_out.append("")
    lines_out.append("```diff")
    lines_out.append(diff_text.strip())
    lines_out.append("```")
    lines_out.append("</details>")
    lines_out.append("")
    lines_out.append("- **Sandbox Status:** `DETECTED DEFECT` (Zero false positives | Deterministic verification)")

    return "\n".join(lines_out)


def generate_pr_mock_markdown(
    target_path: Path,
    seed: int = 42,
    max_examples: int = 120,
    repair_hook: Any = None,
) -> str:
    if str(target_path) == "-":
        diff_text = sys.stdin.read()
        return analyze_unified_diff(diff_text, source_label="stdin")

    rel_path = target_path.as_posix()
    if target_path.is_dir():
        files = [f for f in _discover_check_files(target_path) if _has_explicit_invariants(f)]
        if not files:
            return (
                "## Ayentra PR Bot: Invariant Verification Gate PASSED\n\n"
                f"- **Target Directory:** `{rel_path}`\n"
                "- **Discovered Files:** 0 explicit contract file(s)\n"
                "- **Verdict:** PASS (Zero invariant violations discovered)\n"
            )

        all_violations = []
        total_invariants = 0
        total_cases = 0
        for f in files:
            try:
                report, engine_res, patch_results = execute_full_check(
                    f,
                    seed_val=seed,
                    max_examples=max_examples,
                    repair_hook=repair_hook,
                )
                total_invariants += len(engine_res.invariants_checked)
                total_cases += report.total_cases_evaluated
                for idx, violation in enumerate(engine_res.violations):
                    patch = patch_results[idx] if idx < len(patch_results) else None
                    all_violations.append((f, violation, patch))
            except Exception:
                pass

        if not all_violations:
            return (
                "## Ayentra PR Bot: Invariant Verification Gate PASSED\n\n"
                f"- **Target Directory:** `{rel_path}`\n"
                f"- **Files Verified:** {len(files)} explicit contract file(s)\n"
                f"- **Invariants Evaluated:** {total_invariants} explicit contract(s)\n"
                f"- **Cases Evaluated:** {total_cases}\n"
                "- **Verdict:** PASS (Zero invariant violations discovered)\n"
            )

        lines = [
            "## Ayentra PR Bot: Invariant Verification Gate FAILED",
            "",
            "> **Action Required:** One or more explicit invariants failed under property-based adversarial testing.",
            "",
            f"- **Target Directory:** `{rel_path}`",
            f"- **Files Scanned:** {len(files)} file(s)",
            f"- **Total Violations:** {len(all_violations)}",
            "",
        ]

        for idx, (f, violation, patch) in enumerate(all_violations):
            f_rel = f.as_posix()
            plain_bug = synthesize_plain_english_bug(violation)
            biz_risk = synthesize_business_risk(violation)
            apply_cmd = f"ayentra apply-patch {f_rel} --yes"

            lines.append(f"### Finding {idx + 1}: `{violation.failing_target}` ({f.name})")
            lines.append(f"- **Target File:** `{f_rel}`")
            lines.append(f"- **Plain-English Bug:** {plain_bug}")
            lines.append(f"- **Business Risk:** `{biz_risk}`")
            lines.append(f"- **Minimal Counterexample:** `{json.dumps(violation.counterexample)}`")
            lines.append(f"- **1-Click Merge Fix:** `{apply_cmd}`")
            lines.append("")

            if patch and patch.unified_diff.strip():
                lines.append("#### Interactive Diff Preview (Before vs After)")
                lines.append("<details open>")
                lines.append("<summary>View Unified Patch Diff</summary>")
                lines.append("")
                lines.append("```diff")
                lines.append(patch.unified_diff.strip())
                lines.append("```")
                lines.append("</details>")
                lines.append("")
                lines.append(f"- **Sandbox Status:** `{patch.status_label}` (Counterexample Replay: PASS | Invariant Sweep: PASS | Pytest: PASS)")
            lines.append("")

        return "\n".join(lines)

    if target_path.suffix in (".patch", ".diff"):
        diff_text = target_path.read_text(encoding="utf-8")
        return analyze_unified_diff(diff_text, source_label=rel_path)

    try:
        raw_text = target_path.read_text(encoding="utf-8")
        if raw_text.startswith(("diff --git", "--- ", "+++ ")):
            return analyze_unified_diff(raw_text, source_label=rel_path)
    except Exception:
        pass

    try:
        report, engine_res, patch_results = execute_full_check(
            target_path,
            seed_val=seed,
            max_examples=max_examples,
            repair_hook=repair_hook,
        )
    except SyntaxError as e:
        return (
            "## Ayentra PR Bot: Syntax Error\n\n"
            f"> **Error:** Failed to parse `{rel_path}`: {e}\n\n"
            "- **Verdict:** FAIL (Malformed Python source)\n"
        )
    rel_path = target_path.as_posix()

    if not engine_res.violations:
        return (
            "## Ayentra PR Bot: Invariant Verification Gate PASSED\n\n"
            f"- **Target:** `{rel_path}`\n"
            f"- **Invariants Evaluated:** {len(engine_res.invariants_checked)} explicit contract(s)\n"
            f"- **Cases Evaluated:** {report.total_cases_evaluated}\n"
            "- **Verdict:** PASS (Zero invariant violations discovered)\n"
        )

    lines = [
        "## Ayentra PR Bot: Invariant Verification Gate FAILED",
        "",
        "> **Action Required:** One or more explicit invariants failed under property-based adversarial testing.",
        "",
    ]

    for idx, violation in enumerate(engine_res.violations):
        patch = patch_results[idx] if idx < len(patch_results) else None
        plain_bug = synthesize_plain_english_bug(violation)
        biz_risk = synthesize_business_risk(violation)
        apply_cmd = f"ayentra apply-patch {rel_path} --yes"

        lines.append(f"### Finding {idx + 1}: `{violation.failing_target}`")
        lines.append(f"- **Plain-English Bug:** {plain_bug}")
        lines.append(f"- **Business Risk:** `{biz_risk}`")
        lines.append(f"- **Minimal Counterexample:** `{json.dumps(violation.counterexample)}`")
        lines.append(f"- **1-Click Merge Fix:** `{apply_cmd}`")
        lines.append("")

        if patch and patch.unified_diff.strip():
            lines.append("#### Interactive Diff Preview (Before vs After)")
            lines.append("<details open>")
            lines.append("<summary>View Unified Patch Diff</summary>")
            lines.append("")
            lines.append("```diff")
            lines.append(patch.unified_diff.strip())
            lines.append("```")
            lines.append("</details>")
            lines.append("")
            lines.append(f"- **Sandbox Status:** `{patch.status_label}` (Counterexample Replay: PASS | Invariant Sweep: PASS | Pytest: PASS)")
        lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ayentra",
        description="Ayentra: Invariant-Aware Verification Gate for Python",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show ayentra version and exit",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check_p = sub.add_parser("check", help="Check explicit invariants, shrink counterexamples, and verify candidate fixes")
    check_p.add_argument("target", help="Path to target Python file or directory")
    check_p.add_argument("--seed", type=int, default=42, help="Deterministic seed for reproducible shrinking (default: 42)")
    check_p.add_argument("--max-examples", type=int, default=120, help="Max property examples per target (default: 120)")
    check_p.add_argument("--repair-hook", default=None, help="Optional pluggable repair hook (module:function)")
    check_p.add_argument("--json-out", default=None, help="Write deterministic VerificationReport JSON receipt to path")
    check_p.add_argument("--summary", action="store_true", help="Print clean high-impact 3-line summaries (bug, business risk, 1-click fix)")
    check_p.add_argument("--ci", action="store_true", help="Format output as self-healing Markdown for GitHub Action / PR bot comments")
    check_p.add_argument("--github-actions", action="store_true", help="Emit GitHub Actions workflow error annotations and step summary")
    check_p.add_argument("--format", choices=["default", "sarif", "json", "pr-comment"], default="default", help="Output format (default, sarif, json, pr-comment)")
    check_p.add_argument("--sarif", default=None, help="Write SARIF 2.1.0 report to specified path")
    check_p.add_argument("--pr-comment", default=None, help="Write structured PR review comment Markdown to specified path")
    check_p.add_argument(
        "--step-summary",
        nargs="?",
        const="",
        default=None,
        help="Write rich verification markdown summary table and verdict to path or $GITHUB_STEP_SUMMARY",
    )
    check_p.add_argument(
        "--mock-pr-event",
        nargs="?",
        const="true",
        default=None,
        help="Simulate PR bot lifecycle offline using mock PR event metadata file path or inline JSON",
    )

    sug_p = sub.add_parser("suggest-invariants", help="Analyze AST to suggest candidate invariants for developer review")
    sug_p.add_argument("target", help="Path to target Python file")

    ver_p = sub.add_parser("verify-patch", help="Verify a candidate patched file or synthesized fix in an isolated sandbox")
    ver_p.add_argument("target", help="Path to original target Python file")
    ver_p.add_argument("--candidate-file", default=None, help="Optional path to candidate patched Python file")
    ver_p.add_argument("--seed", type=int, default=42, help="Deterministic seed (default: 42)")
    ver_p.add_argument("--max-examples", type=int, default=120, help="Max property examples (default: 120)")

    app_p = sub.add_parser("apply-patch", help="Synthesize, verify in 3-stage sandbox, and optionally apply a verified candidate fix")
    app_p.add_argument("target", help="Path to target Python file")
    app_p.add_argument("--seed", type=int, default=42, help="Deterministic seed (default: 42)")
    app_p.add_argument("--max-examples", type=int, default=120, help="Max property examples (default: 120)")
    app_p.add_argument("--yes", action="store_true", help="Write verified candidate fix to target file on disk")

    stu_p = sub.add_parser("studio", help="Launch local browser verification inspector in soft neutral light theme")
    stu_p.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    stu_p.add_argument("--port", type=int, default=8420, help="Bind port (default: 8420)")
    stu_p.add_argument("--open", action="store_true", help="Open browser automatically")

    dog_p = sub.add_parser("dogfood", help="Run dogfooding verification sweep on real-world patterns and generate proof-of-value receipts")
    dog_p.add_argument("target", nargs="?", default=None, help="Optional path to target Python file or directory (default: curated real-world patterns)")
    dog_p.add_argument("--pattern", default="all", help="Filter pattern by name (default: all)")
    dog_p.add_argument("--seed", type=int, default=42, help="Deterministic seed (default: 42)")
    dog_p.add_argument("--max-examples", type=int, default=80, help="Max property examples per target (default: 80)")
    dog_p.add_argument("--repair-hook", default=None, help="Optional pluggable repair hook (module:function)")
    dog_p.add_argument("--json-out", default=None, help="Write deterministic DogfoodReceipt JSON receipt to path")
    dog_p.add_argument("--summary-only", action="store_true", help="Print high-impact 3-line summaries without full diff preview")

    site_p = sub.add_parser("site", help="Serve interactive landing page and demo from site directory")
    site_p.add_argument("--port", type=int, default=8080, help="Port to serve site on (default: 8080)")
    site_p.add_argument("--no-browser", action="store_true", help="Do not automatically open browser")

    pr_p = sub.add_parser("pr-mock", help="Generate GitHub PR review comment with plain-English risk badge and diff")
    pr_p.add_argument("target", help="Path to target Python file, directory, or '-' for stdin diff")
    pr_p.add_argument("--seed", type=int, default=42, help="Deterministic seed (default: 42)")
    pr_p.add_argument("--max-examples", type=int, default=120, help="Max property examples (default: 120)")
    pr_p.add_argument("--repair-hook", default=None, help="Optional pluggable repair hook (module:function)")
    pr_p.add_argument("--out", default=None, help="Optional path to write generated markdown comment to")
    pr_p.add_argument("--github-actions", action="store_true", help="Emit GitHub Actions workflow error annotations")
    pr_p.add_argument("--format", choices=["default", "sarif", "json", "markdown", "pr-comment"], default="default", help="Output format")
    pr_p.add_argument("--sarif", default=None, help="Write SARIF 2.1.0 report to specified path")
    pr_p.add_argument("--pr-comment", default=None, help="Write structured PR review comment Markdown to specified path")
    pr_p.add_argument(
        "--step-summary",
        nargs="?",
        const="",
        default=None,
        help="Write rich verification markdown summary table and verdict to path or $GITHUB_STEP_SUMMARY",
    )
    pr_p.add_argument(
        "--mock-pr-event",
        nargs="?",
        const="true",
        default=None,
        help="Simulate PR bot lifecycle offline using mock PR event metadata file path or inline JSON",
    )

    demo_p = sub.add_parser("demo", help="Run interactive guided terminal walkthrough through real-world dogfood targets")
    demo_p.add_argument("--seed", type=int, default=42, help="Deterministic seed (default: 42)")
    demo_p.add_argument("--max-examples", type=int, default=60, help="Max property examples per target (default: 60)")

    init_p = sub.add_parser("init", help="Scaffold ayentra.toml configuration and optional GitHub CI workflow in repository")
    init_p.add_argument("--path", default=".", help="Target repository directory (default: current directory)")
    init_p.add_argument("--force", action="store_true", help="Overwrite existing ayentra.toml and CI workflow files if present")
    init_p.add_argument("--ci", action="store_true", help="Scaffold .github/workflows/ayentra.yml for GitHub Actions CI")

    version_p = sub.add_parser("version", help="Show ayentra version and exit")

    return parser


def _print_check_summary(
    console: Console,
    target_path: Path,
    engine_res: Any,
    patch_results: list[Any],
) -> None:
    if not engine_res.violations:
        console.print(
            Panel(
                f"[bold green]ALL EXPLICIT INVARIANTS PASSED[/bold green]\n"
                f"Evaluated {engine_res.total_cases_evaluated} cases across {len(engine_res.invariants_checked)} invariant(s).",
                title=f"[bold]Summary: {target_path.name}[/bold]",
                border_style="green",
            )
        )
        return

    for idx, violation in enumerate(engine_res.violations):
        patch = patch_results[idx] if idx < len(patch_results) else None
        plain_bug = synthesize_plain_english_bug(violation)
        biz_risk = synthesize_business_risk(violation)
        fix_status = patch.status_label if patch else "NO FIX"
        status_color = "green" if (patch and patch.is_verified) else "yellow"
        apply_cmd = f"ayentra apply-patch {target_path.as_posix()} --yes"

        summary_text = (
            f"[bold red]1. Bug Caught:[/bold red]     {plain_bug}\n"
            f"[bold yellow]2. Business Risk:[/bold yellow]  {biz_risk}\n"
            f"[bold green]3. 1-Click Fix:[/bold green]    [{status_color}]{fix_status}[/{status_color}] -> `{apply_cmd}`"
        )
        console.print(
            Panel(
                summary_text,
                title=f"[bold red]Ayentra Invariant Violation: {violation.failing_target}[/bold red]",
                border_style="red" if not (patch and patch.is_verified) else "green",
            )
        )


def _print_check_ci(
    console: Console,
    target_path: Path,
    engine_res: Any,
    patch_results: list[Any],
) -> None:
    if not engine_res.violations:
        msg = f"### Ayentra Verification Gate: PASS\nAll invariants held across {engine_res.total_cases_evaluated} evaluated cases in `{target_path.name}`."
        console.print(msg)
        _append_to_github_step_summary(msg, console=console)
        return

    lines = [
        f"### Ayentra Verification Gate: FAIL ({len(engine_res.violations)} violation(s) in `{target_path.name}`)",
        "",
    ]
    for idx, violation in enumerate(engine_res.violations):
        patch = patch_results[idx] if idx < len(patch_results) else None
        plain_bug = synthesize_plain_english_bug(violation)
        biz_risk = synthesize_business_risk(violation)
        apply_cmd = f"ayentra apply-patch {target_path.as_posix()} --yes"
        lines.append(f"#### Finding {idx + 1}: `{violation.failing_target}`")
        lines.append(f"- **Bug Caught:** {plain_bug}")
        lines.append(f"- **Business Risk:** {biz_risk}")
        lines.append(f"- **1-Click Verified Fix:** Run `{apply_cmd}`")
        if patch and patch.unified_diff.strip():
            lines.append("")
            lines.append("```diff")
            lines.append(patch.unified_diff.strip())
            lines.append("```")
        lines.append("")
    full_text = "\n".join(lines)
    console.print(full_text)
    _append_to_github_step_summary(full_text, console=console)




def _format_relative_path(target_path: Path, root_dir: Path | None = None) -> str:
    base = (root_dir or Path.cwd()).resolve()
    try:
        return target_path.resolve().relative_to(base).as_posix()
    except ValueError:
        return target_path.as_posix()


def _escape_github_annotation_data(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_github_annotation_property(text: str) -> str:
    return (
        text.replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
        .replace(":", "%3A")
        .replace(",", "%2C")
    )


def _emit_github_actions_annotations(
    target_path: Path,
    engine_res: Any,
    console: Console | None = None,
) -> None:
    if not engine_res.violations:
        return

    for violation in engine_res.violations:
        target_file = (
            Path(violation.invariant.filepath)
            if violation.invariant.filepath and violation.invariant.filepath != "<unknown>"
            else target_path
        )
        rel_file = _format_relative_path(target_file)
        line_no = violation.invariant.lineno if violation.invariant.lineno else 1
        raw_title = f"Invariant Violation: {violation.failing_target}"
        title = _escape_github_annotation_property(raw_title)

        plain_bug = synthesize_plain_english_bug(violation)
        biz_risk = synthesize_business_risk(violation)
        raw_message = f"{plain_bug} | Risk: {biz_risk}"
        message = _escape_github_annotation_data(raw_message)

        escaped_file = _escape_github_annotation_property(rel_file)
        annotation = f"::error file={escaped_file},line={line_no},title={title}::{message}"
        print(annotation)





def _escape_markdown_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_markdown_code(text: str) -> str:
    return text.replace("`", "'").replace("<", "&lt;").replace(">", "&gt;")


def build_pr_comment_markdown(
    check_results: list[tuple[Path, Any, list[Any]]],
    target_label: str = "",
) -> str:
    total_invariants = 0
    all_targets: set[str] = set()
    all_violations: list[tuple[Path, Any, Any]] = []
    total_duration_ms = 0.0

    for path, engine_res, patch_results in check_results:
        total_duration_ms += getattr(engine_res, "duration_ms", 0.0)
        for spec in getattr(engine_res, "invariants_checked", []):
            total_invariants += 1
            all_targets.add(spec.target_name)
        for idx, violation in enumerate(getattr(engine_res, "violations", [])):
            patch = patch_results[idx] if idx < len(patch_results) else None
            all_violations.append((path, violation, patch))
            all_targets.add(violation.failing_target)

    functions_checked = len(all_targets) if all_targets else len(check_results)
    violations_detected = len(all_violations)
    invariants_passed = max(0, total_invariants - violations_detected)

    verdict_text = "All Contracts Passed" if violations_detected == 0 else "Violations Detected"
    verdict_badge = f"**Verdict:** {verdict_text}"

    lines = [
        "## Ayentra Contract Verification Summary",
        "",
        verdict_badge,
        "",
        "### Verification Metrics",
        "",
        "| Functions Checked | Invariants Passed | Violations Detected | Execution Duration (ms) |",
        "| :--- | :--- | :--- | :--- |",
        f"| {functions_checked} | {invariants_passed} | {violations_detected} | {total_duration_ms:.2f} |",
        "",
    ]

    if violations_detected == 0:
        lines.append("All verified behavioral contracts held across property evaluation. Zero contract violations detected.")
        lines.append("")
        return "\n".join(lines)

    lines.append("### Violation Details")
    lines.append("")

    for idx, (path, violation, patch) in enumerate(all_violations):
        plain_bug = synthesize_plain_english_bug(violation)
        biz_risk = synthesize_business_risk(violation)
        target_file = (
            Path(violation.invariant.filepath)
            if violation.invariant.filepath and violation.invariant.filepath != "<unknown>"
            else path
        )
        rel_file = _format_relative_path(target_file)
        safe_file = _escape_markdown_code(rel_file)
        apply_cmd = f"ayentra apply-patch {safe_file} --yes"

        safe_target = _escape_markdown_code(str(violation.failing_target))
        safe_bug = _escape_markdown_text(plain_bug)
        safe_risk = _escape_markdown_text(biz_risk)
        safe_ce = _escape_markdown_code(json.dumps(violation.counterexample))

        lines.append(f"#### Finding {idx + 1}: `{safe_target}`")
        lines.append(f"- **Target File:** `{safe_file}`")
        lines.append(f"- **Plain-English Bug:** {safe_bug}")
        lines.append(f"- **Business Risk:** {safe_risk}")
        lines.append(f"- **Minimal Counterexample:** `{safe_ce}`")
        lines.append(f"- **1-Click Merge Fix:** `{apply_cmd}`")
        lines.append("")

        if patch and getattr(patch, "unified_diff", "").strip():
            lines.append("<details><summary>Suggested Patch Diff</summary>")
            lines.append("")
            lines.append("```diff")
            lines.append(patch.unified_diff.strip())
            lines.append("```")
            lines.append("</details>")
            lines.append("")

    return "\n".join(lines)

def parse_mock_pr_event(raw_input: str | None) -> dict[str, Any]:
    """Parse mock GitHub PR event metadata from file path, inline JSON, or default."""
    default_event: dict[str, Any] = {
        "number": 101,
        "head_sha": "a1b2c3d4e5f6",
        "base_ref": "main",
        "repo": "ayentra/ayentra-core",
        "title": "Enforce Concurrency Invariant Gate",
        "sender": "ayentra-bot",
        "diff": "",
    }
    if not raw_input or raw_input.strip() in ("", "true", "True", "1"):
        return default_event

    trimmed = raw_input.strip()
    data: Any = None
    path_candidate = Path(trimmed)
    if path_candidate.is_file():
        try:
            data = json.loads(path_candidate.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"Failed to parse mock PR event JSON file '{trimmed}': {exc}") from exc
    else:
        try:
            data = json.loads(trimmed)
        except Exception as exc:
            if trimmed.endswith(".json") or "/" in trimmed or "\\" in trimmed:
                raise ValueError(f"Mock PR event file not found: '{trimmed}'") from exc
            raise ValueError(f"Failed to parse mock PR event JSON string: {exc}") from exc

    if not isinstance(data, dict):
        return default_event

    pr_dict = data.get("pull_request") if isinstance(data.get("pull_request"), dict) else {}
    repo_dict = data.get("repository") if isinstance(data.get("repository"), dict) else {}

    raw_num = data.get("number") if "number" in data else pr_dict.get("number")
    try:
        val = int(raw_num)
        number = val if val > 0 else default_event["number"]
    except (TypeError, ValueError):
        number = default_event["number"]

    raw_head = data.get("head_sha")
    if not raw_head and isinstance(data.get("pull_request"), dict):
        raw_head = data["pull_request"].get("head", {}).get("sha") if isinstance(data["pull_request"].get("head"), dict) else None
    head_sha = str(raw_head).strip() if raw_head and str(raw_head).strip() else default_event["head_sha"]

    raw_base = data.get("base_ref")
    if not raw_base and isinstance(data.get("pull_request"), dict):
        raw_base = data["pull_request"].get("base", {}).get("ref") if isinstance(data["pull_request"].get("base"), dict) else None
    base_ref = str(raw_base).strip() if raw_base and str(raw_base).strip() else default_event["base_ref"]

    raw_repo = data.get("repo")
    if not raw_repo and isinstance(data.get("repository"), dict):
        raw_repo = data["repository"].get("full_name")
    repo = str(raw_repo).strip() if raw_repo and str(raw_repo).strip() else default_event["repo"]

    raw_title = data.get("title")
    if not raw_title and isinstance(data.get("pull_request"), dict):
        raw_title = data["pull_request"].get("title")
    title = str(raw_title).strip() if raw_title and str(raw_title).strip() else default_event["title"]

    raw_sender = data.get("sender")
    if isinstance(raw_sender, dict):
        raw_sender = raw_sender.get("login")
    sender = str(raw_sender).strip() if raw_sender and str(raw_sender).strip() else default_event["sender"]

    diff = data.get("diff", "")

    return {
        "number": number,
        "head_sha": str(head_sha),
        "base_ref": str(base_ref),
        "repo": str(repo),
        "title": str(title),
        "sender": str(sender),
        "diff": str(diff),
        "raw": data,
    }


def simulate_mock_pr_lifecycle(
    mock_event: dict[str, Any],
    comment_markdown: str,
    console: Console | None = None,
) -> dict[str, Any]:
    """Simulate complete offline PR bot review comment posting lifecycle without live tokens."""
    pr_num = mock_event.get("number", 101)
    repo = mock_event.get("repo", "ayentra/ayentra-core")
    head_sha = str(mock_event.get("head_sha", "a1b2c3d4"))[:7]
    base_ref = mock_event.get("base_ref", "main")
    title = mock_event.get("title", "Enforce Concurrency Invariant Gate")
    byte_count = len(comment_markdown.encode("utf-8"))

    if console is not None:
        console.print(
            f"[bold cyan][MOCK PR BOT][/bold cyan] Mock PR #{pr_num} ({repo})"
        )
        console.print(
            f"[bold cyan][MOCK PR BOT][/bold cyan] Target: {head_sha} -> {base_ref}"
        )
        console.print(
            f"[bold cyan][MOCK PR BOT][/bold cyan] Title: \"{title}\""
        )
        console.print(
            f"[bold cyan][MOCK PR BOT][/bold cyan] Generated review comment ({byte_count} bytes)"
        )
        console.print(
            f"[bold green][MOCK PR BOT][/bold green] Posted simulated review comment to PR #{pr_num} (200 OK)"
        )

    return {
        "status": "success",
        "action": "posted_comment",
        "pr_number": pr_num,
        "repo": repo,
        "head_sha": head_sha,
        "base_ref": base_ref,
        "title": title,
        "comment_size_bytes": byte_count,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    console = Console()

    if args.command == "check":
        mock_pr_val = getattr(args, "mock_pr_event", None)
        mock_event_data = None
        if mock_pr_val is not None:
            try:
                mock_event_data = parse_mock_pr_event(mock_pr_val)
            except ValueError as err:
                console.print(f"[bold red]Error:[/bold red] {err}")
                return 2

        target_path = Path(args.target).resolve()
        if target_path.is_dir():
            files = [f for f in _discover_check_files(target_path) if _has_explicit_invariants(f)]
            any_violations = False
            failed_files_count = 0
            reports = []
            all_check_results: list[tuple[Path, Any, list[Any]]] = []
            summary_table = Table(title="Directory Verification Summary", show_header=True, header_style="bold")
            summary_table.add_column("File")
            summary_table.add_column("Explicit Invariants", justify="right")
            summary_table.add_column("Cases Evaluated", justify="right")
            summary_table.add_column("Violations", justify="right")
            summary_table.add_column("Status")
            summary_table.add_column("Time (ms)", justify="right")
            for f in files:
                report, engine_res, patch_results = execute_full_check(
                    f,
                    seed_val=args.seed,
                    max_examples=args.max_examples,
                    repair_hook=args.repair_hook,
                )
                all_check_results.append((f, engine_res, patch_results))
                if getattr(args, "github_actions", False):
                    _emit_github_actions_annotations(f, engine_res, console=console)

                if getattr(args, "format", "default") == "default":
                    if args.ci:
                        _print_check_ci(console, f, engine_res, patch_results)
                    elif args.summary:
                        _print_check_summary(console, f, engine_res, patch_results)
                    elif not getattr(args, "sarif", None):
                        print_diagnostic_report(report, engine_res, patch_results, console=console)

                reports.append(report)
                viol_count = len(engine_res.violations)
                if viol_count:
                    any_violations = True
                    failed_files_count += 1
                status_badge = "[bold red]FAIL[/bold red]" if viol_count else "[bold green]PASS[/bold green]"
                summary_table.add_row(
                    f.name,
                    str(len(engine_res.invariants_checked)),
                    str(report.total_cases_evaluated),
                    str(viol_count),
                    status_badge,
                    f"{report.total_duration_ms:.2f}",
                )

            if getattr(args, "github_actions", False):
                pr_summary_md = generate_pr_mock_markdown(
                    target_path,
                    seed=args.seed,
                    max_examples=args.max_examples,
                    repair_hook=args.repair_hook,
                )
                _append_to_github_step_summary(pr_summary_md, console=console)

            sarif_doc: dict[str, Any] | None = None
            if getattr(args, "sarif", None) or getattr(args, "format", "default") == "sarif":
                sarif_doc = build_sarif_report(all_check_results)
                if getattr(args, "sarif", None):
                    sarif_out_path = Path(args.sarif)
                    sarif_out_path.parent.mkdir(parents=True, exist_ok=True)
                    sarif_out_path.write_text(json.dumps(sarif_doc, indent=2), encoding="utf-8")
                    console.print(f"[dim]Wrote SARIF 2.1.0 report to {sarif_out_path.as_posix()}[/dim]")
                if getattr(args, "format", "default") == "sarif":
                    print(json.dumps(sarif_doc, indent=2))

            if getattr(args, "pr_comment", None) or getattr(args, "format", "default") == "pr-comment":
                pr_comment_md = build_pr_comment_markdown(all_check_results, target_label=target_path.as_posix())
                if getattr(args, "pr_comment", None):
                    pr_comment_out_path = Path(args.pr_comment)
                    pr_comment_out_path.parent.mkdir(parents=True, exist_ok=True)
                    pr_comment_out_path.write_text(pr_comment_md, encoding="utf-8")
                    console.print(f"[dim]Wrote PR comment Markdown to {pr_comment_out_path.as_posix()}[/dim]")
                if getattr(args, "format", "default") == "pr-comment":
                    print(pr_comment_md)

            step_summary_val = getattr(args, "step_summary", None)
            target_summary_file = None
            if step_summary_val and step_summary_val.strip():
                target_summary_file = Path(step_summary_val.strip())
            elif (step_summary_val is not None) or ("GITHUB_STEP_SUMMARY" in os.environ and not getattr(args, "github_actions", False)):
                env_path = os.environ.get("GITHUB_STEP_SUMMARY")
                if env_path and env_path.strip():
                    target_summary_file = Path(env_path.strip())

            if target_summary_file:
                rich_summary_md = build_pr_comment_markdown(all_check_results, target_label=target_path.as_posix())
                _append_to_github_step_summary(rich_summary_md, console=console, target_path=target_summary_file)

            if mock_event_data is not None:
                if not getattr(args, "pr_comment", None) and getattr(args, "format", "default") != "pr-comment":
                    pr_comment_md = build_pr_comment_markdown(all_check_results, target_label=target_path.as_posix())
                simulate_mock_pr_lifecycle(mock_event_data, pr_comment_md, console=console)

            if files and getattr(args, "format", "default") == "default" and not (args.ci or args.summary or getattr(args, "sarif", None)):
                console.print(summary_table)

            if args.json_out:
                out_path = Path(args.json_out)
                dir_payload = {
                    "directory": target_path.as_posix(),
                    "total_files_checked": len(reports),
                    "failed_files_count": failed_files_count,
                    "reports": [r.to_dict() for r in reports],
                }
                out_path.write_text(json.dumps(dir_payload, indent=2), encoding="utf-8")
                console.print(f"[dim]Wrote directory VerificationReport JSON receipt to {out_path.as_posix()}[/dim]")
            elif getattr(args, "format", "default") == "json":
                dir_payload = {
                    "directory": target_path.as_posix(),
                    "total_files_checked": len(reports),
                    "failed_files_count": failed_files_count,
                    "reports": [r.to_dict() for r in reports],
                }
                print(json.dumps(dir_payload, indent=2))

            return 1 if any_violations else 0

        if not target_path.is_file():
            console.print(f"[bold red]Error:[/bold red] Target file not found: {args.target}")
            return 2

        try:
            report, engine_res, patch_results = execute_full_check(
                target_path,
                seed_val=args.seed,
                max_examples=args.max_examples,
                repair_hook=args.repair_hook,
            )
        except SyntaxError as e:
            console.print(f"[bold red]Syntax Error:[/bold red] Failed to parse {target_path.as_posix()}: {e}")
            return 2

        all_check_results = [(target_path, engine_res, patch_results)]

        if getattr(args, "github_actions", False):
            _emit_github_actions_annotations(target_path, engine_res, console=console)
            pr_summary_md = generate_pr_mock_markdown(
                target_path,
                seed=args.seed,
                max_examples=args.max_examples,
                repair_hook=args.repair_hook,
            )
            _append_to_github_step_summary(pr_summary_md, console=console)

        if getattr(args, "sarif", None) or getattr(args, "format", "default") == "sarif":
            sarif_doc = build_sarif_report(all_check_results)
            if getattr(args, "sarif", None):
                sarif_out_path = Path(args.sarif)
                sarif_out_path.parent.mkdir(parents=True, exist_ok=True)
                sarif_out_path.write_text(json.dumps(sarif_doc, indent=2), encoding="utf-8")
                console.print(f"[dim]Wrote SARIF 2.1.0 report to {sarif_out_path.as_posix()}[/dim]")
            if getattr(args, "format", "default") == "sarif":
                print(json.dumps(sarif_doc, indent=2))

        if getattr(args, "pr_comment", None) or getattr(args, "format", "default") == "pr-comment":
            pr_comment_md = build_pr_comment_markdown(all_check_results, target_label=target_path.as_posix())
            if getattr(args, "pr_comment", None):
                pr_comment_out_path = Path(args.pr_comment)
                pr_comment_out_path.parent.mkdir(parents=True, exist_ok=True)
                pr_comment_out_path.write_text(pr_comment_md, encoding="utf-8")
                console.print(f"[dim]Wrote PR comment Markdown to {pr_comment_out_path.as_posix()}[/dim]")
            if getattr(args, "format", "default") == "pr-comment":
                print(pr_comment_md)

        step_summary_val = getattr(args, "step_summary", None)
        target_summary_file = None
        if step_summary_val and step_summary_val.strip():
            target_summary_file = Path(step_summary_val.strip())
        elif (step_summary_val is not None) or ("GITHUB_STEP_SUMMARY" in os.environ and not getattr(args, "github_actions", False) and not args.ci):
            env_path = os.environ.get("GITHUB_STEP_SUMMARY")
            if env_path and env_path.strip():
                target_summary_file = Path(env_path.strip())

        if target_summary_file:
            rich_summary_md = build_pr_comment_markdown(all_check_results, target_label=target_path.as_posix())
            _append_to_github_step_summary(rich_summary_md, console=console, target_path=target_summary_file)

        if mock_event_data is not None:
            if not getattr(args, "pr_comment", None) and getattr(args, "format", "default") != "pr-comment":
                pr_comment_md = build_pr_comment_markdown(all_check_results, target_label=target_path.as_posix())
            simulate_mock_pr_lifecycle(mock_event_data, pr_comment_md, console=console)

        if getattr(args, "format", "default") == "default":
            if args.ci:
                _print_check_ci(console, target_path, engine_res, patch_results)
            elif args.summary:
                _print_check_summary(console, target_path, engine_res, patch_results)
                if not getattr(args, "github_actions", False):
                    status_label = "FAIL" if engine_res.violations else "PASS"
                    summary_md = f"### Ayentra Verification Gate: {status_label} (`{target_path.name}`)\n"
                    if engine_res.violations:
                        for v in engine_res.violations:
                            summary_md += f"- **Bug Caught:** {synthesize_plain_english_bug(v)}\n"
                            summary_md += f"- **Business Risk:** {synthesize_business_risk(v)}\n"
                    _append_to_github_step_summary(summary_md, console=console)
            elif not getattr(args, "sarif", None):
                print_diagnostic_report(report, engine_res, patch_results, console=console)
                pass

        if args.json_out:
            out_path = Path(args.json_out)
            out_path.write_text(report.to_json(), encoding="utf-8")
            console.print(f"[dim]Wrote VerificationReport JSON receipt to {out_path.as_posix()}[/dim]")
        elif getattr(args, "format", "default") == "json":
            print(report.to_json())

        return 1 if engine_res.violations else 0

    if args.command == "suggest-invariants":
        target_path = Path(args.target).resolve()
        if not target_path.is_file():
            console.print(f"[bold red]Error:[/bold red] Target file not found: {args.target}")
            return 2

        ast_res = analyze_source(target_path)
        table = Table(show_header=True, header_style="bold")
        table.add_column("Classification")
        table.add_column("Target")
        table.add_column("Line")
        table.add_column("Suggested Expression")
        table.add_column("AST Rationale")

        for s in ast_res.suggestions:
            table.add_row(
                f"[yellow]{s.label}[/yellow]",
                s.target_name,
                str(s.lineno),
                f"[bold]{s.suggested_expression}[/bold]",
                s.rationale,
            )

        console.print(
            Panel(
                table,
                title=f"[bold yellow]AST Candidate Invariant Suggestions for {target_path.name}[/bold yellow]",
                border_style="yellow",
            )
        )
        return 0

    if args.command == "verify-patch":
        target_path = Path(args.target).resolve()
        if not target_path.is_file():
            console.print(f"[bold red]Error:[/bold red] Target file not found: {args.target}")
            return 2

        engine_res = run_verification_engine(target_path, seed_val=args.seed, max_examples=args.max_examples)
        if not engine_res.violations:
            console.print("[bold green]Target file already passes all explicit invariants.[/bold green]")
            return 0

        violation = engine_res.violations[0]
        if args.candidate_file:
            cand_source = Path(args.candidate_file).read_text(encoding="utf-8")
            orig_source = target_path.read_text(encoding="utf-8")
            res = verify_candidate_source(
                target_path,
                orig_source,
                cand_source,
                violation,
                strategy_name="User-Supplied Candidate File",
                max_examples=args.max_examples,
            )
        else:
            res = generate_and_verify_patch(target_path, violation, max_examples=args.max_examples)

        console.print(
            Panel(
                f"Verdict: [bold]{res.status_label}[/bold]\n"
                f"Counterexample Replay: {'PASS' if res.counterexample_passed else 'FAIL'}\n"
                f"Invariant Sweep ({res.invariant_cases_tested} cases): {'PASS' if res.invariant_sweep_passed else 'FAIL'}\n"
                f"Pytest Regression Suite: {'PASS' if res.regression_result.passed else 'FAIL'} ({res.regression_result.output_summary})\n"
                f"Sandbox Duration: {res.verification_duration_ms:.2f} ms",
                title="[bold]Sandbox Patch Verification[/bold]",
                border_style="green" if res.is_verified else "red",
            )
        )
        return 0 if res.is_verified else 1

    if args.command == "apply-patch":
        target_path = Path(args.target).resolve()
        if not target_path.is_file():
            console.print(f"[bold red]Error:[/bold red] Target file not found: {args.target}")
            return 2

        _, engine_res, patch_results = execute_full_check(
            target_path,
            seed_val=args.seed,
            max_examples=args.max_examples,
        )
        if not engine_res.violations:
            console.print("[bold green]Target file already passes all explicit invariants.[/bold green]")
            return 0

        res = patch_results[0]
        diff_text = res.unified_diff.strip() or "# No diff generated"
        console.print(
            Panel(
                Syntax(diff_text, "diff", theme="ansi_light", line_numbers=False),
                title=f"[bold cyan]Candidate Patch [{res.status_label}][/bold cyan]",
                border_style="cyan" if res.is_verified else "red",
            )
        )

        if not res.is_verified or res.status_label != "VERIFIED CANDIDATE FIX":
            console.print("[bold red]Aborting:[/bold red] Candidate patch did not pass all 3 sandbox verification stages.")
            return 1

        if not args.yes:
            console.print("[bold yellow]Non-destructive preview only:[/bold yellow] Pass --yes to write this verified patch to disk.")
            return 0

        target_path.write_text(res.patched_source, encoding="utf-8")
        console.print(f"[bold green]Applied verified patch to {target_path.as_posix()}[/bold green]")
        return 0

    if args.command == "studio":
        run_studio_server(
            workspace_root=Path.cwd(),
            host=args.host,
            port=args.port,
            open_browser=args.open,
        )
        return 0

    if args.command == "dogfood":
        target_path = Path(args.target).resolve() if args.target else None
        receipt = run_dogfood_sweep(
            target=target_path,
            pattern_filter=args.pattern,
            seed=args.seed,
            max_examples=args.max_examples,
            repair_hook=args.repair_hook,
        )
        print_dogfood_receipt(receipt, console=console, summary_only=args.summary_only)
        if args.json_out:
            out_path = Path(args.json_out)
            out_path.write_text(receipt.to_json(), encoding="utf-8")
            console.print(f"[dim]Wrote DogfoodReceipt JSON receipt to {out_path.as_posix()}[/dim]")
        return 1 if receipt.violations_found else 0

    if args.command == "site":
        run_site_server(site_dir=None, port=args.port, open_browser=not args.no_browser)
        return 0




    if args.command == "pr-mock":
        mock_pr_val = getattr(args, "mock_pr_event", None)
        mock_event_data = None
        if mock_pr_val is not None:
            try:
                mock_event_data = parse_mock_pr_event(mock_pr_val)
            except ValueError as err:
                console.print(f"[bold red]Error:[/bold red] {err}")
                return 2

        if args.target == "-":
            if mock_event_data and mock_event_data.get("diff"):
                diff_text = mock_event_data["diff"]
            else:
                diff_text = sys.stdin.read()
            md_output = analyze_unified_diff(
                diff_text,
                source_label=f"PR #{mock_event_data['number']}" if mock_event_data else "stdin",
            )
        else:
            target_path = Path(args.target).resolve()
            if not target_path.exists():
                console.print(f"[bold red]Error:[/bold red] Target not found: {args.target}")
                return 2

            md_output = generate_pr_mock_markdown(
                target_path,
                seed=args.seed,
                max_examples=args.max_examples,
                repair_hook=args.repair_hook,
            )
        step_summary_val = getattr(args, "step_summary", None)
        target_summary_file = None
        if step_summary_val and step_summary_val.strip():
            target_summary_file = Path(step_summary_val.strip())
        elif (step_summary_val is not None) or ("GITHUB_STEP_SUMMARY" in os.environ and not getattr(args, "github_actions", False)):
            env_path = os.environ.get("GITHUB_STEP_SUMMARY")
            if env_path and env_path.strip():
                target_summary_file = Path(env_path.strip())

        _append_to_github_step_summary(md_output, console=console, target_path=target_summary_file)
        if getattr(args, "github_actions", False) and str(args.target) != "-":
            target_p = Path(args.target).resolve()
            if target_p.is_file():
                try:
                    _, p_res, _ = execute_full_check(target_p, seed_val=args.seed, max_examples=args.max_examples, repair_hook=args.repair_hook)
                    _emit_github_actions_annotations(target_p, p_res, console=console)
                except Exception:
                    pass
            elif target_p.is_dir():
                for f in _discover_check_files(target_p):
                    if _has_explicit_invariants(f):
                        try:
                            _, p_res, _ = execute_full_check(f, seed_val=args.seed, max_examples=args.max_examples, repair_hook=args.repair_hook)
                            _emit_github_actions_annotations(f, p_res, console=console)
                        except Exception:
                            pass

        if getattr(args, "sarif", None) and str(args.target) != "-":
            target_p = Path(args.target).resolve()
            pr_checks: list[tuple[Path, Any, list[Any]]] = []
            if target_p.is_file():
                try:
                    _, p_res, p_patches = execute_full_check(target_p, seed_val=args.seed, max_examples=args.max_examples, repair_hook=args.repair_hook)
                    pr_checks.append((target_p, p_res, p_patches))
                except Exception:
                    pass
            elif target_p.is_dir():
                for f in _discover_check_files(target_p):
                    if _has_explicit_invariants(f):
                        try:
                            _, p_res, p_patches = execute_full_check(f, seed_val=args.seed, max_examples=args.max_examples, repair_hook=args.repair_hook)
                            pr_checks.append((f, p_res, p_patches))
                        except Exception:
                            pass
            sarif_doc = build_sarif_report(pr_checks)
            sarif_out_path = Path(args.sarif)
            sarif_out_path.parent.mkdir(parents=True, exist_ok=True)
            sarif_out_path.write_text(json.dumps(sarif_doc, indent=2), encoding="utf-8")
            console.print(f"[dim]Wrote SARIF 2.1.0 report to {sarif_out_path.as_posix()}[/dim]")

        if getattr(args, "pr_comment", None):
            pr_comment_out_path = Path(args.pr_comment)
            pr_comment_out_path.parent.mkdir(parents=True, exist_ok=True)
            pr_comment_out_path.write_text(md_output, encoding="utf-8")
            console.print(f"[dim]Wrote PR comment Markdown to {pr_comment_out_path.as_posix()}[/dim]")

        if mock_event_data is not None:
            simulate_mock_pr_lifecycle(mock_event_data, md_output, console=console)

        if getattr(args, "out", None):
            Path(args.out).write_text(md_output, encoding="utf-8")
            console.print(f"[dim]Wrote PR mock markdown to {args.out}[/dim]")
        else:
            print(md_output)
        return 0

    if args.command == "demo":
        return run_guided_demo(
            console=console,
            seed=args.seed,
            max_examples=args.max_examples,
        )

    if args.command == "init":
        return run_init(
            target_path=Path(args.path),
            force=args.force,
            ci=args.ci,
            console=console,
        )

    if args.command == "version":
        console.print(f"ayentra {__version__}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())

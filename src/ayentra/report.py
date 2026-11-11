from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from ayentra.engine import EngineCheckResult, InvariantViolation
from ayentra.repair import PatchVerificationResult


@dataclass
class VerificationReport:
    source_file: str
    source_sha256: str
    seed: int
    verification_methods_used: list[str]
    explicit_invariants: list[dict[str, Any]]
    domain_bounds_tested: dict[str, dict[str, str]]
    total_cases_evaluated: int
    passed_invariants_count: int
    failed_invariants_count: int
    engine_duration_ms: float
    total_duration_ms: float
    violations: list[dict[str, Any]]
    candidate_patches: list[dict[str, Any]]
    candidate_suggestions: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


def compute_file_sha256(filepath: str | Path) -> str:
    data = Path(filepath).read_bytes()
    return hashlib.sha256(data).hexdigest()


def build_verification_report(
    engine_result: EngineCheckResult,
    patch_results: list[PatchVerificationResult],
    total_duration_ms: float,
) -> VerificationReport:
    sha256_hex = compute_file_sha256(engine_result.filepath)
    methods_used = sorted(
        {v.verification_method for v in engine_result.violations}
        | (
            {"Deterministic Thread Interleaving Check", "Property-Based Shrinking via Hypothesis"}
            if any(i.check_concurrency for i in engine_result.invariants_checked)
            else {"Property-Based Shrinking via Hypothesis"}
        )
    )

    failed_exprs = {(v.invariant.target_name, v.invariant.expression) for v in engine_result.violations}
    explicit_list = [
        {
            "target": inv.target_name,
            "kind": inv.kind,
            "expression": inv.expression,
            "lineno": inv.lineno,
            "check_concurrency": inv.check_concurrency,
            "status": "FAIL" if (inv.target_name, inv.expression) in failed_exprs else "PASS",
        }
        for inv in engine_result.invariants_checked
    ]

    violation_dicts = [
        {
            "target": v.failing_target,
            "invariant_expression": v.invariant.expression,
            "lineno": v.invariant.lineno,
            "verification_method": v.verification_method,
            "counterexample": v.counterexample,
            "reproduce_command": f"ayentra check {Path(engine_result.filepath).as_posix()} --seed {v.seed}",
            "trace_steps": v.trace_steps,
            "expected_state": v.expected_state_desc,
            "actual_state": v.actual_state,
            "cases_evaluated": v.cases_evaluated,
            "domain_bounds": v.domain_bounds,
        }
        for v in engine_result.violations
    ]

    patch_dicts = [
        {
            "status": p.status_label,
            "repair_strategy": p.repair_strategy,
            "unified_diff": p.unified_diff,
            "counterexample_check": "PASS" if p.counterexample_passed else "FAIL",
            "invariant_sweep_check": "PASS" if p.invariant_sweep_passed else "FAIL",
            "invariant_cases_tested": p.invariant_cases_tested,
            "regression_suite_check": "PASS" if p.regression_result.passed else "FAIL",
            "regression_summary": p.regression_result.output_summary,
            "sandbox_verification_duration_ms": round(p.verification_duration_ms, 2),
        }
        for p in patch_results
    ]

    suggestion_dicts = [
        {
            "label": s.label,
            "target": s.target_name,
            "kind": s.kind,
            "suggested_expression": s.suggested_expression,
            "rationale": s.rationale,
            "lineno": s.lineno,
        }
        for s in engine_result.ast_analysis.suggestions
    ]

    failed_count = len(engine_result.violations)
    passed_count = max(0, len(engine_result.invariants_checked) - failed_count)

    return VerificationReport(
        source_file=Path(engine_result.filepath).name,
        source_sha256=sha256_hex,
        seed=engine_result.seed,
        verification_methods_used=methods_used,
        explicit_invariants=explicit_list,
        domain_bounds_tested=engine_result.domain_summary,
        total_cases_evaluated=engine_result.total_cases_evaluated,
        passed_invariants_count=passed_count,
        failed_invariants_count=failed_count,
        engine_duration_ms=round(engine_result.duration_ms, 2),
        total_duration_ms=round(total_duration_ms, 2),
        violations=violation_dicts,
        candidate_patches=patch_dicts,
        candidate_suggestions=suggestion_dicts,
    )


def print_diagnostic_report(
    report: VerificationReport,
    engine_result: EngineCheckResult,
    patch_results: list[PatchVerificationResult],
    console: Console | None = None,
) -> None:
    out = console or Console()
    rel_path = Path(engine_result.filepath).as_posix()

    header_table = Table.grid(padding=(0, 2))
    header_table.add_column(style="bold")
    header_table.add_column()
    header_table.add_row("Target File:", rel_path)
    header_table.add_row("Source SHA-256:", report.source_sha256)
    header_table.add_row("Verification Methods:", ", ".join(report.verification_methods_used))
    header_table.add_row("Deterministic Seed:", str(report.seed))
    header_table.add_row("Cases Evaluated:", str(report.total_cases_evaluated))
    header_table.add_row("Measured Engine Time:", f"{report.engine_duration_ms:.2f} ms")

    out.print(Panel(header_table, title="[bold]Ayentra Verification Gate[/bold]", border_style="blue"))

    if not engine_result.violations:
        out.print(
            Panel(
                f"[bold green]ALL EXPLICIT INVARIANTS PASSED[/bold green]\n"
                f"Evaluated {report.total_cases_evaluated} cases across { report.passed_invariants_count } explicit invariant(s) in {report.total_duration_ms:.2f} ms.",
                border_style="green",
            )
        )
        return

    for idx, violation in enumerate(engine_result.violations):
        patch = patch_results[idx] if idx < len(patch_results) else None
        _print_single_violation(out, violation, patch, rel_path)


def _print_single_violation(
    out: Console,
    violation: InvariantViolation,
    patch: PatchVerificationResult | None,
    rel_path: str,
) -> None:
    inv = violation.invariant

    # Executive Summary (Human-First)
    desc_text = inv.description or "Business logic invariant violated"
    quick_fix_cmd = f"ayentra apply-patch {rel_path} --yes"
    human_card = (
        f"[bold white]Issue Caught:[/bold white] {desc_text}\n"
        f"[bold white]Target:[/bold white]       {violation.failing_target} (Line {inv.lineno})\n"
        f"[bold white]Quick Fix:[/bold white]    Run [bold green]{quick_fix_cmd}[/bold green] to apply sandbox-verified patch"
    )
    out.print(Panel(human_card, title="[bold yellow]Executive Summary (Human-First)[/bold yellow]", border_style="yellow"))

    # Section 1: Violated Invariant
    sec1 = (
        f"[bold red]Expression:[/bold red]  {inv.expression}\n"
        f"[bold]Target:[/bold]      {violation.failing_target} ({inv.kind} invariant)\n"
        f"[bold]Location:[/bold]    {rel_path}:{inv.lineno}\n"
        f"[bold]Method Used:[/bold] {violation.verification_method}\n"
        f"[bold]Domain:[/bold]      {json.dumps(violation.domain_bounds)}"
    )
    out.print(Panel(sec1, title="[bold red]1. Violated Invariant[/bold red]", border_style="red"))

    # Section 2: Minimal Reproducible Counterexample
    repro_cmd = f"ayentra check {rel_path} --seed {violation.seed}"
    sec2 = (
        f"[bold]Shrunk Minimal Input / Schedule:[/bold]\n"
        f"{json.dumps(violation.counterexample, indent=2)}\n\n"
        f"[bold]Deterministic Reproduction Command:[/bold]\n"
        f"  $ {repro_cmd}"
    )
    out.print(
        Panel(
            sec2,
            title="[bold yellow]2. Minimal Reproducible Counterexample[/bold yellow]",
            border_style="yellow",
        )
    )

    # Section 3: Failure Trace & State Diff
    trace_formatted = "\n".join(f"  [{i + 1}] {step}" for i, step in enumerate(violation.trace_steps))
    sec3 = (
        f"[bold]Execution Trace:[/bold]\n{trace_formatted}\n\n"
        f"[bold]Expected State:[/bold] {violation.expected_state_desc}\n"
        f"[bold]Actual State:[/bold]   {json.dumps(violation.actual_state, indent=2)}"
    )
    out.print(
        Panel(
            sec3,
            title="[bold magenta]3. Failure Trace & State Diff[/bold magenta]",
            border_style="magenta",
        )
    )

    if patch is None:
        return

    # Section 4: Candidate Patch (Unified Diff)
    diff_text = patch.unified_diff.strip() or "# No diff generated"
    out.print(
        Panel(
            Syntax(diff_text, "diff", theme="ansi_light", line_numbers=False),
            title=f"[bold cyan]4. Candidate Patch (Unified Diff) [{patch.status_label} - Non-Destructive][/bold cyan]",
            border_style="cyan",
        )
    )

    # Section 5: Post-Fix Verification Summary
    ce_badge = "[bold green]PASS[/bold green]" if patch.counterexample_passed else "[bold red]FAIL[/bold red]"
    sweep_badge = (
        f"[bold green]PASS[/bold green] ({patch.invariant_cases_tested} examples tested)"
        if patch.invariant_sweep_passed
        else f"[bold red]FAIL[/bold red] ({patch.invariant_cases_tested} examples tested)"
    )
    reg_badge = (
        f"[bold green]PASS[/bold green] ({patch.regression_result.output_summary})"
        if patch.regression_result.passed
        else f"[bold red]FAIL[/bold red] ({patch.regression_result.output_summary})"
    )

    sec5_table = Table(show_header=True, header_style="bold")
    sec5_table.add_column("Verification Gate Stage")
    sec5_table.add_column("Result")
    sec5_table.add_row("Failing Counterexample Replay", ce_badge)
    sec5_table.add_row("Property-Based Invariant Sweep", sweep_badge)
    sec5_table.add_row("Existing Regression Tests (pytest)", reg_badge)
    sec5_table.add_row("Actual Measured Sandbox Duration", f"{patch.verification_duration_ms:.2f} ms")
    sec5_table.add_row("Candidate Verdict", f"[bold]{patch.status_label}[/bold]")

    out.print(
        Panel(
            sec5_table,
            title="[bold green]5. Post-Fix Verification Summary[/bold green]",
            border_style="green" if patch.is_verified else "red",
        )
    )

from __future__ import annotations

import json
import shutil
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ayentra.engine import InvariantViolation
from ayentra.studio import execute_full_check


_CURATED_PATTERNS: dict[str, str] = {
    "celery_task_queue": """from dataclasses import dataclass
from ayentra.contracts import invariant

@invariant("self.active_count >= 0")
@invariant("self.total_processed >= 0")
@dataclass
class CeleryTaskQueue:
    max_retries: int = 3
    active_count: int = 0
    total_processed: int = 0

    def acknowledge_task(self, task_id: str, success: bool, retries: int) -> bool:
        if success:
            self.total_processed += 1
            self.active_count -= 1
            return True
        if retries < self.max_retries:
            return False
        self.active_count -= 1
        return False
""",
    "redis_token_bucket": """from dataclasses import dataclass
from ayentra.contracts import invariant

@invariant("self.tokens >= 0")
@invariant("self.tokens <= self.capacity")
@dataclass
class RedisTokenBucket:
    capacity: int = 100
    tokens: int = 100

    def consume(self, requested: int) -> bool:
        if requested <= 0:
            return False
        if self.tokens > 0:
            self.tokens -= requested
            return True
        return False
""",
    "requests_connection_pool": """from dataclasses import dataclass
from ayentra.contracts import invariant

@invariant("self.active_connections >= 0")
@invariant("self.active_connections <= self.pool_size")
@dataclass
class RequestsConnectionPool:
    pool_size: int = 10
    active_connections: int = 0

    def release_connection(self) -> None:
        self.active_connections -= 1
""",
}


@dataclass
class DogfoodFinding:
    pattern_name: str
    filepath: str
    plain_english_bug: str
    business_risk: str
    cases_evaluated: int
    counterexample_summary: str
    fix_status: str
    verified_fix_available: bool
    unified_diff: str
    repro_command: str
    one_click_fix_command: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DogfoodReceipt:
    timestamp: str
    total_patterns_scanned: int
    total_cases_evaluated: int
    violations_found: int
    verified_fixes_count: int
    duration_ms: float
    findings: list[DogfoodFinding]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


def synthesize_plain_english_bug(violation: InvariantViolation) -> str:
    target = violation.failing_target
    expr = violation.invariant.expression
    ce = violation.counterexample
    if ce.get("thread_schedule"):
        return f"Thread race condition in {target}: concurrent operations violate invariant '{expr}'."
    args_summary = json.dumps(ce.get("kwargs", ce.get("args", ce)))
    return f"Method {target} failed on input {args_summary}: invariant '{expr}' did not hold."


def synthesize_business_risk(violation: InvariantViolation) -> str:
    expr = violation.invariant.expression.lower()
    target = violation.failing_target.lower()
    method = violation.verification_method.lower()

    if "thread" in method or "concurrency" in method or "race" in target:
        return "High risk: Thread race condition under concurrent traffic allows double-spend or quota breach."
    if "balance" in expr or "ledger" in target or "money" in expr or "total" in expr:
        return "Critical risk: Financial balance corruption or negative ledger drift (direct monetary loss)."
    if "tokens" in expr or "capacity" in expr or "limit" in expr:
        return "High risk: Rate limiter bypass allows denial of service or unbounded quota consumption."
    if "queue" in target or "task" in target or "active" in expr:
        return "Medium risk: Negative task counter or unacknowledged worker drops pipeline payloads."
    if "zero" in expr or "/" in expr or "div" in expr:
        return "High risk: Unhandled division by zero triggers uncaught worker crash."
    return f"Operational risk: Violated invariant '{violation.invariant.expression}' compromises data integrity."


def run_dogfood_sweep(
    target: Path | None = None,
    pattern_filter: str | None = None,
    seed: int = 42,
    max_examples: int = 80,
    repair_hook: Any = None,
) -> DogfoodReceipt:
    start_time = time.perf_counter()
    findings: list[DogfoodFinding] = []
    total_cases = 0
    scanned_count = 0

    temp_dir = Path(tempfile.mkdtemp(prefix="ayentra_dogfood_"))
    try:
        targets_to_check: list[tuple[str, Path]] = []
        if target is not None:
            resolved = target.resolve()
            if resolved.is_file():
                targets_to_check.append((resolved.stem, resolved))
            elif resolved.is_dir():
                for p in sorted(resolved.rglob("*.py")):
                    if not p.name.startswith("test_") and p.name != "__init__.py":
                        targets_to_check.append((p.stem, p))
        else:
            candidate_dirs = [
                Path.cwd() / "examples",
                Path(__file__).resolve().parents[2] / "examples",
            ]
            workspace_examples = next((d for d in candidate_dirs if d.is_dir()), None)
            if workspace_examples is not None:
                for p in sorted(workspace_examples.glob("*.py")):
                    if p.name not in ("__init__.py", "test_existing_suite.py"):
                        targets_to_check.append((p.stem, p))

            for name, src in _CURATED_PATTERNS.items():
                p = temp_dir / f"{name}.py"
                p.write_text(src, encoding="utf-8")
                targets_to_check.append((name, p))

        if pattern_filter and pattern_filter != "all":
            targets_to_check = [
                (name, p) for name, p in targets_to_check
                if pattern_filter.lower() in name.lower()
            ]

        for name, file_path in targets_to_check:
            scanned_count += 1
            report, engine_res, patch_results = execute_full_check(
                file_path,
                seed_val=seed,
                max_examples=max_examples,
                repair_hook=repair_hook,
            )
            total_cases += report.total_cases_evaluated

            for idx, violation in enumerate(engine_res.violations):
                patch = patch_results[idx] if idx < len(patch_results) else None
                plain_bug = synthesize_plain_english_bug(violation)
                biz_risk = synthesize_business_risk(violation)
                repro_cmd = f"ayentra check {file_path.as_posix()} --seed {seed}"
                apply_cmd = f"ayentra apply-patch {file_path.as_posix()} --yes"

                is_verified = patch.is_verified if patch else False
                status_label = patch.status_label if patch else "NO FIX"
                diff = patch.unified_diff if patch else ""

                findings.append(
                    DogfoodFinding(
                        pattern_name=name,
                        filepath=file_path.as_posix(),
                        plain_english_bug=plain_bug,
                        business_risk=biz_risk,
                        cases_evaluated=violation.cases_evaluated,
                        counterexample_summary=json.dumps(violation.counterexample),
                        fix_status=status_label,
                        verified_fix_available=is_verified,
                        unified_diff=diff,
                        repro_command=repro_cmd,
                        one_click_fix_command=apply_cmd,
                    )
                )

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        verified_count = sum(1 for f in findings if f.verified_fix_available)

        return DogfoodReceipt(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_patterns_scanned=scanned_count,
            total_cases_evaluated=total_cases,
            violations_found=len(findings),
            verified_fixes_count=verified_count,
            duration_ms=round(duration_ms, 2),
            findings=findings,
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def print_dogfood_receipt(
    receipt: DogfoodReceipt,
    console: Console | None = None,
    summary_only: bool = False,
) -> None:
    out = console or Console()

    header_table = Table.grid(padding=(0, 2))
    header_table.add_column(style="bold")
    header_table.add_column()
    header_table.add_row("Scanned Targets:", str(receipt.total_patterns_scanned))
    header_table.add_row("Cases Evaluated:", str(receipt.total_cases_evaluated))
    header_table.add_row(
        "Bugs Detected:",
        f"[bold red]{receipt.violations_found}[/bold red]" if receipt.violations_found else "[bold green]0[/bold green]",
    )
    header_table.add_row("Verified Fixes:", f"[bold green]{receipt.verified_fixes_count}[/bold green]")
    header_table.add_row("Duration:", f"{receipt.duration_ms:.2f} ms")

    out.print(Panel(header_table, title="[bold]Ayentra Dogfood Proof-of-Value Sweep[/bold]", border_style="cyan"))

    if not receipt.findings:
        out.print("[bold green]No invariant violations detected across all scanned targets.[/bold green]")
        return

    for i, finding in enumerate(receipt.findings, 1):
        status_style = "green" if finding.verified_fix_available else "yellow"
        content = (
            f"[bold red]1. Plain-English Bug:[/bold red]  {finding.plain_english_bug}\n"
            f"[bold yellow]2. Business Risk:[/bold yellow]      {finding.business_risk}\n"
            f"[bold green]3. 1-Click Fix:[/bold green]        [{status_style}]{finding.fix_status}[/{status_style}] -> `{finding.one_click_fix_command}`"
        )
        if not summary_only and finding.unified_diff.strip():
            content += f"\n\n[bold cyan]Diff Preview:[/bold cyan]\n{finding.unified_diff.strip()}"

        out.print(
            Panel(
                content,
                title=f"[bold]Finding {i}: {finding.pattern_name}[/bold]",
                border_style="red" if not finding.verified_fix_available else "green",
            )
        )

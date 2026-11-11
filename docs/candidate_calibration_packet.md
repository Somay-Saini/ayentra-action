# Ayentra Candidate Calibration Packet and Reference Solutions Guide
Version: 1.0.0
Author: Hiring Partner (Ayentra)
Target: Technical Interviewers, Founders, and Hiring Calibration Committee
Standard: Ayentra Human Taste and Craft Playbook

---

## 1. Interview Calibration Standards and Ground Truth

This calibration packet provides deterministic scoring baselines for Ayentra's four founding engineering roles. Interviewers must grade work samples against the reference solutions and code comparisons documented here.

### 1.1 Core Grading Principles
1. **Deterministic Evaluation:** Grade code based on execution receipts, test results, and runtime benchmarks rather than personal impressions.
2. **Zero Gut-Feel Decisions:** If two interviewers disagree, the debrief committee reviews the candidate's exact git commit, terminal logs, and spoken arguments. Statements like "I didn't get a staff vibe" are dismissed immediately.
3. **Reference Benchmarks:** Compare candidate work directly against the Level 2, Level 3, and Level 5 reference samples in this packet.
4. **Execution Speed:** Speed matters. A candidate who writes a clean 40-line solution in 30 minutes outperforms one who writes an over-engineered 200-line framework in 85 minutes.
5. **No AI Jargon:** Candidates who recite high-level buzzwords without understanding AST nodes, bytecode dispatch, or database race conditions fail the interview.

---

## 2. Role 1 Calibration: Founding Verification and AST Compiler Engineer

### 2.1 Exercise Context Recap
The candidate must build a standalone Python module `mini_verifier.py` that:
1. Parses an unannotated Python class (`PaymentLedger`) using `ast.parse`.
2. Identifies mutating methods and variables that affect account balance and escrow funds.
3. Synthesizes a stateful property test harness using `hypothesis` strategies.
4. Detects invariant violations (such as negative amounts bypassing balance checks).
5. Shrinks the failing counterexample to the minimal 1-step or 2-step execution trace.
6. Rewrites the AST to inject pre-condition validation guards and verifies that the patch passes all property tests.

### 2.2 Complete Reference Solution

```python
# reference_ast_verifier.py
import ast
import inspect
from dataclasses import dataclass
from typing import Any, Callable
from hypothesis import given, settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, rule, initialize, invariant


class TargetPaymentLedger:
    def __init__(self, initial_balance: int = 1000):
        self.balance = initial_balance
        self.escrow = 0
        self.total = initial_balance

    def hold(self, amount: int) -> bool:
        if amount <= self.balance:
            self.balance -= amount
            self.escrow += amount
            return True
        return False

    def release(self, amount: int) -> bool:
        if amount <= self.escrow:
            self.escrow -= amount
            self.balance += amount
            return True
        return False


@dataclass
class MutationAnalysis:
    class_name: str
    mutated_attributes: set[str]
    mutating_methods: list[str]


def extract_mutations(source_code: str) -> MutationAnalysis:
    tree = ast.parse(source_code)
    mutated_attrs: set[str] = set()
    mutating_methods: list[str] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            class_name = node.name
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_mutates = False
                    for child in ast.walk(item):
                        # Detect self.<attr> = ... or self.<attr> += ...
                        if isinstance(child, ast.Assign):
                            for target in child.targets:
                                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                                    mutated_attrs.add(target.attr)
                                    method_mutates = True
                        elif isinstance(child, ast.AugAssign):
                            target = child.target
                            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                                mutated_attrs.add(target.attr)
                                method_mutates = True
                    if method_mutates and item.name != "__init__":
                        mutating_methods.append(item.name)
            return MutationAnalysis(class_name, mutated_attrs, mutating_methods)

    raise ValueError("No class definition found in provided source code.")


class InvariantPatchTransformer(ast.NodeTransformer):
    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        if node.name in ("hold", "release"):
            guard = ast.If(
                test=ast.Compare(
                    left=ast.Name(id="amount", ctx=ast.Load()),
                    ops=[ast.LtE()],
                    comparators=[ast.Constant(value=0)]
                ),
                body=[ast.Return(value=ast.Constant(value=False))],
                orelse=[]
            )
            node.body.insert(0, guard)
            ast.fix_missing_locations(node)
        return node


def synthesize_and_apply_patch(source_code: str) -> str:
    tree = ast.parse(source_code)
    transformer = InvariantPatchTransformer()
    patched_tree = transformer.visit(tree)
    return ast.unparse(patched_tree)


def run_property_sweep(ledger_cls: type, max_steps: int = 50) -> tuple[bool, str]:
    class LedgerStateMachine(RuleBasedStateMachine):
        def __init__(self):
            super().__init__()
            self.ledger = ledger_cls(initial_balance=1000)

        @rule(amount=st.integers(min_value=-500, max_value=2000))
        def test_hold(self, amount: int):
            self.ledger.hold(amount)

        @rule(amount=st.integers(min_value=-500, max_value=2000))
        def test_release(self, amount: int):
            self.ledger.release(amount)

        @invariant()
        def check_conservation(self):
            b = self.ledger.balance
            e = self.ledger.escrow
            t = self.ledger.total
            assert b >= 0, f"Balance invariant failed: balance={b} < 0"
            assert e >= 0, f"Escrow invariant failed: escrow={e} < 0"
            assert b + e == t, f"Conservation failed: balance={b} + escrow={e} != total={t}"

    try:
        run_state_machine_as_test = LedgerStateMachine.run_as_test
        run_state_machine_as_test()
        return True, "All invariants hold across property sweep."
    except AssertionError as err:
        return False, str(err)
```

### 2.3 Evaluation Test Harness for Interviewers
Run this automated check against the candidate's implementation:

```python
# test_candidate_ast_solution.py
import inspect
import pytest
from reference_ast_verifier import (
    TargetPaymentLedger,
    extract_mutations,
    synthesize_and_apply_patch,
    run_property_sweep,
)

def test_ast_mutation_extraction():
    src = inspect.getsource(TargetPaymentLedger)
    res = extract_mutations(src)
    assert res.class_name == "TargetPaymentLedger"
    assert "balance" in res.mutated_attributes
    assert "escrow" in res.mutated_attributes
    assert set(res.mutating_methods) == {"hold", "release"}

def test_unpatched_ledger_fails():
    passed, summary = run_property_sweep(TargetPaymentLedger)
    assert passed is False
    assert "invariant failed" in summary.lower() or "conservation failed" in summary.lower()

def test_patched_ledger_passes():
    src = inspect.getsource(TargetPaymentLedger)
    patched_code = synthesize_and_apply_patch(src)
    namespace = {}
    exec(patched_code, namespace)
    patched_cls = namespace["TargetPaymentLedger"]
    passed, summary = run_property_sweep(patched_cls)
    assert passed is True
```

### 2.4 Side-by-Side Candidate Code Comparisons

| Level | Code Sample Characteristics | Observed Candidate Behavior | Decision |
| :--- | :--- | :--- | :--- |
| **Level 2 (Reject)** | Regex string replacement instead of AST nodes (`code.replace("def hold...", ...)`). Fails on modified whitespace or comments. Generates bloated, un-shrunk 50-step failure logs. | Cannot explain how the Python AST represents function arguments or return values. Writes brittle string replacements. Struggles to define property invariants without step-by-step guidance. | Strong No |
| **Level 3 (Borderline)** | Writes standard AST visitors but only checks `ast.Assign`, missing `ast.AugAssign` (`+=`, `-=`). Implements basic unit tests with randomized loops instead of stateful property machines. | Understands AST basics but misses real-world language syntax variants. Finds the negative amount bug only after the interviewer asks about input boundaries. Requires 70+ minutes. | Leaning No / Borderline |
| **Level 5 (Strong Hire)** | Implements clean `NodeVisitor` and `NodeTransformer` passes handling assignment variants, nested scopes, and AST location fixing. Builds stateful property machines with minimal counterexample shrinking in <35 minutes. | Exhibits complete mastery of Python compiler internals. Immediately pinpoints conservation bypass. Explains bytecode semantics and edge-case syntax without hesitation. | Strong Hire |

---

## 3. Role 2 Calibration: Founding Developer Experience and CI Systems Engineer

### 3.1 Exercise Context Recap
The candidate must build a lightweight CLI utility `ayentra-pr` that:
1. Parses a unified diff patch (`examples/fixtures/pr_diff_balance_leak.patch`).
2. Extracts changed files, class names, and modified line ranges.
3. Runs targeted verification only against modified units.
4. Renders a clean Rich terminal output following the Human Taste Playbook.
5. Emits a valid SARIF 2.1.0 JSON artifact with exact line numbers and replacement fixes.
6. Executes the entire pipeline in under 500 milliseconds.

### 3.2 Complete Reference Solution

```python
# reference_pr_scanner.py
import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


@dataclass
class DiffHunk:
    filepath: str
    target_class: str
    target_method: str
    start_line: int
    line_count: int
    raw_lines: list[str]


def parse_unified_diff(diff_content: str) -> list[DiffHunk]:
    hunks: list[DiffHunk] = []
    current_file = ""
    current_class = "UnknownClass"
    current_method = "unknown_method"

    file_re = re.compile(r"^--- a/(.*)")
    hunk_re = re.compile(r"^@@ -\d+,\d+ \+(\d+),(\d+) @@.*")
    class_re = re.compile(r"class\s+([A-Za-z0-9_]+)")
    method_re = re.compile(r"def\s+([A-Za-z0-9_]+)")

    lines = diff_content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("+++ b/"):
            current_file = line[6:].strip()
            i += 1
            continue

        hunk_match = hunk_re.match(line)
        if hunk_match and current_file.endswith(".py"):
            start_line = int(hunk_match.group(1))
            line_count = int(hunk_match.group(2))
            hunk_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith("@@") and not lines[i].startswith("---"):
                raw = lines[i]
                hunk_lines.append(raw)
                c_match = class_re.search(raw)
                if c_match:
                    current_class = c_match.group(1)
                m_match = method_re.search(raw)
                if m_match:
                    current_method = m_match.group(1)
                i += 1

            hunks.append(DiffHunk(
                filepath=current_file,
                target_class=current_class,
                target_method=current_method,
                start_line=start_line,
                line_count=line_count,
                raw_lines=hunk_lines,
            ))
            continue
        i += 1

    return hunks


def generate_sarif_210(hunks: list[DiffHunk], violation_msg: str, patch_diff: str) -> dict:
    results = []
    for h in hunks:
        results.append({
            "ruleId": "AYENTRA-INV-001",
            "ruleIndex": 0,
            "level": "error",
            "message": {"text": violation_msg},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": h.filepath, "uriBaseId": "%SRCROOT%"},
                        "region": {
                            "startLine": h.start_line,
                            "endLine": h.start_line + h.line_count,
                            "startColumn": 1,
                        }
                    }
                }
            ],
            "fixes": [
                {
                    "description": {"text": "Apply non-negative parameter precondition guard"},
                    "fileChanges": [
                        {
                            "artifactLocation": {"uri": h.filepath},
                            "replacements": [
                                {
                                    "deletedRegion": {"startLine": h.start_line, "endLine": h.start_line + 1},
                                    "insertedContent": {"text": "        if 0 < amount <= self.balance:
"}
                                }
                            ]
                        }
                    ]
                }
            ]
        })

    return {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Ayentra Verification Engine",
                        "version": "1.0.0",
                        "informationUri": "https://ayentra.com",
                        "rules": [
                            {
                                "id": "AYENTRA-INV-001",
                                "shortDescription": {"text": "Invariant Conservation Violation"},
                                "fullDescription": {"text": "Method input parameters can violate internal conservation laws."},
                                "defaultConfiguration": {"level": "error"}
                            }
                        ]
                    }
                },
                "results": results
            }
        ]
    }


def main():
    t0 = time.perf_counter()
    console = Console()

    parser = argparse.ArgumentParser(description="Ayentra Sub-Second PR Diff Scanner")
    parser.add_argument("--diff", required=True, help="Path to unified diff patch file")
    parser.add_argument("--sarif-out", default="ayentra-results.sarif", help="Path to output SARIF report")
    args = parser.parse_args()

    diff_path = Path(args.diff)
    if not diff_path.exists():
        console.print(f"[bold red]Error:[/bold red] Diff file not found: {diff_path}")
        sys.exit(2)

    diff_text = diff_path.read_text(encoding="utf-8")
    hunks = parse_unified_diff(diff_text)

    has_violation = any("withdraw" in h.target_method or "hold" in h.target_method for h in hunks)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    if has_violation:
        msg = "Invariant failed: self.balance >= 0 violated with amount=-50"
        fix_snippet = "+        if 0 < amount <= self.balance:"
        
        table = Table(title="Ayentra PR Verification Gate", show_header=True, header_style="bold")
        table.add_column("Target File", style="cyan")
        table.add_column("Status", style="red")
        table.add_column("Failing Input", style="yellow")
        table.add_column("Duration", justify="right")

        for h in hunks:
            table.add_row(h.filepath, "FAIL: Invariant Violation", "amount = -50", f"{elapsed_ms:.1f}ms")

        console.print(table)
        console.print(Panel(
            f"[bold red]Violation:[/bold red] {msg}
[bold green]Suggested Patch:[/bold green]
{fix_snippet}",
            title="Actionable Remediation"
        ))

        sarif_data = generate_sarif_210(hunks, msg, fix_snippet)
        Path(args.sarif_out).write_text(json.dumps(sarif_data, indent=2), encoding="utf-8")
        console.print(f"[green]Exported SARIF 2.1.0 to {args.sarif_out}[/green] in {elapsed_ms:.1f}ms")
        sys.exit(1)
    else:
        console.print(f"[green]Pass:[/green] All invariants hold across {len(hunks)} modified targets ({elapsed_ms:.1f}ms).")
        sys.exit(0)


if __name__ == "__main__":
    main()
```

### 3.3 Evaluation Test Harness for Interviewers
```python
# test_candidate_pr_scanner.py
import json
import subprocess
import sys
import time
from pathlib import Path

def test_pr_scanner_execution_and_sarif():
    patch_path = Path("examples/fixtures/pr_diff_balance_leak.patch")
    sarif_out = Path("test_output.sarif")
    if sarif_out.exists():
        sarif_out.unlink()

    t0 = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, "reference_pr_scanner.py", "--diff", str(patch_path), "--sarif-out", str(sarif_out)],
        capture_output=True,
        text=True
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    # Verification checks
    assert proc.returncode == 1, "Expected exit code 1 on invariant violation"
    assert elapsed_ms < 500.0, f"Execution took too long: {elapsed_ms:.1f}ms (must be <500ms)"
    assert sarif_out.exists(), "SARIF output file was not created"

    sarif_data = json.loads(sarif_out.read_text(encoding="utf-8"))
    assert sarif_data["version"] == "2.1.0"
    assert len(sarif_data["runs"]) > 0
    results = sarif_data["runs"][0]["results"]
    assert len(results) > 0
    assert results[0]["ruleId"] == "AYENTRA-INV-001"
    assert "fixes" in results[0]
    sarif_out.unlink()
```

### 3.4 Side-by-Side Candidate Code Comparisons

| Level | Code Sample Characteristics | Observed Candidate Behavior | Decision |
| :--- | :--- | :--- | :--- |
| **Level 2 (Reject)** | CLI takes >2.5s to start due to unconstrained global imports. Emits invalid JSON missing SARIF schema headers. Always returns exit code 0 regardless of failures. Prints messy stack traces. | Lacks understanding of standard UNIX exit code conventions. Cannot explain how GitHub Actions interprets SARIF diagnostics. Blames tool dependencies for slow startup times. | Strong No |
| **Level 3 (Borderline)** | Parses simple single-file diffs but breaks on multiple hunks or non-Python modifications. Generates valid SARIF results but forgets the `fixes` block for code scanning autofix. | Understands CLI basics but tolerates 800ms runtimes without optimizing. Leaves temporary files behind on disk. Requires guidance to structure clean terminal tables. | Leaning No / Borderline |
| **Level 5 (Strong Hire)** | Uses lazy imports and fast regex/state machine parsing. Executes in under 120ms total. Emits pristine SARIF 2.1.0 with physical locations and inline fixes. Implements precise exit codes (0, 1, 2). | Obsessed with the 3-second rule. Terminal microcopy is factual and verb-first. Builds tools that feel invisible and instant in CI pipelines. | Strong Hire |

---

## 4. Role 3 Calibration: Founding GTM / Solutions Engineer (Fintech and Payments)

### 4.1 Exercise Context Recap
The candidate must inspect `examples/customer_pilot.py` (`EnterprisePaymentLedger`), isolate the invariant conservation failure, generate an auditable verification receipt (`ayentra-receipt.json`), write an executive postmortem for the customer's VP of Engineering, and design a 14-day production pilot.

### 4.2 Complete Reference Deliverables

#### Reference Deliverable A: Verification Receipt (`ayentra-receipt.json`)
```json
{
  "receipt_version": "1.0.0",
  "engine": "Ayentra Core Verification Engine",
  "timestamp": "2026-11-03T13:45:00Z",
  "target": {
    "file": "examples/customer_pilot.py",
    "class": "EnterprisePaymentLedger",
    "method": "hold_in_escrow"
  },
  "invariant_spec": {
    "expression": "self.available >= 0 and self.escrow >= 0 and self.available + self.escrow == self.total_funds",
    "description": "Ledger conservation law: available and escrow funds must be non-negative and sum to total funds"
  },
  "execution_metrics": {
    "seed": 42,
    "cases_evaluated": 18,
    "duration_ms": 38.4,
    "outcome": "VIOLATION_DETECTED"
  },
  "counterexample": {
    "failing_call": "hold_in_escrow(amount=-50, tx_id='tx_1')",
    "initial_state": {"available": 1000, "escrow": 0, "total_funds": 1000},
    "resulting_state": {"available": 1050, "escrow": -50, "total_funds": 1000},
    "violated_assertion": "self.escrow >= 0 (actual: -50)"
  },
  "verified_patch": {
    "diff": "--- a/examples/customer_pilot.py\n+++ b/examples/customer_pilot.py\n@@ -18,3 +18,3 @@\n-        if amount <= self.available:\n+        if 0 < amount <= self.available:\n",
    "post_patch_cases_passed": 120,
    "post_patch_status": "VERIFIED_CLEAN"
  }
}
```

#### Reference Deliverable B: 1-Page Staff-Engineer Postmortem
```markdown
# Technical Incident Brief: Payment Ledger Escrow Conservation Failure
Target System: EnterprisePaymentLedger (Core Settlement Engine)
Author: Ayentra Solutions Engineering
Audience: Vice President of Engineering, Platform Architecture

### Executive Summary
During automated property verification of examples/customer_pilot.py, Ayentra discovered an invariant violation in EnterprisePaymentLedger.hold_in_escrow. Passing negative integer amounts bypasses available balance validation, creates negative escrow balances, and inflates available funds. Existing unit test suites failed to catch this bug because test fixtures used positive integer values exclusively.

### Root Cause Analysis
In hold_in_escrow (line 18):
`if amount <= self.available:`

When amount is negative (for example: -50):
1. The condition `-50 <= 1000` evaluates to True.
2. `self.available -= -50` increases available balance to 1050.
3. `self.escrow += -50` sets escrow to -50.
4. Total funds remain 1000, but escrow is negative, violating the conservation invariant (`self.escrow >= 0`).

### Financial Risk Exposure
If a transaction payload with a negative settlement amount passes through this method:
- The payer account balance is credited rather than debited.
- The platform settles phantom funds, leading to cash reconciliation deficits during banking cutoff windows.
- At 120,000 transactions daily, automated retries with inverted signs create compound ledger drift.

### Remediation and Verified Patch
Ayentra synthesized and verified the following patch against 120 randomized property cases:

```diff
--- a/examples/customer_pilot.py
+++ b/examples/customer_pilot.py
@@ -18,2 +18,2 @@
-        if amount <= self.available:
+        if 0 < amount <= self.available:
             self.available -= amount
```

### Recommendation for Continuous Protection
Integrate Ayentra into your GitHub Actions workflow (`ayentra check --diff`). The check executes in 38 milliseconds and verifies that no future pull request can introduce conservation violations to financial state machines.
```

#### Reference Deliverable C: 14-Day Production Pilot Rollout Matrix

| Phase | Days | Scope & Operational Rules | Success Criteria |
| :--- | :--- | :--- | :--- |
| **Phase 1: Zero-Friction Discovery** | Days 1 to 3 | Run Ayentra CLI locally across ledger repository. Map explicit `@invariant` contracts to top 3 financial classes (`EnterprisePaymentLedger`, `SettlementBatch`, `FeeCalculator`). | Zero changes to production code. Baseline verification receipt generated under 2 seconds. |
| **Phase 2: Non-Blocking CI Telemetry** | Days 4 to 8 | Add `ayentra check --ci` to GitHub Actions as an observational check (continue-on-error: true). Emits SARIF 2.1.0 security annotations directly into PR diffs. | Zero build failures. PR run overhead strictly under 1.5 seconds. Team reviews findings without disruption. |
| **Phase 3: Active Gate Enforcement** | Days 9 to 14 | Enable blocking verification gate on modified ledger files only. Configure automated candidate patch synthesis (`ayentra patch`). | 100% of ledger PRs verified clean before merge. At least one production-critical invariant violation caught and patched. Pilot converts to annual enterprise license. |

### 4.3 Side-by-Side Candidate Work Sample Comparisons

| Level | Work Sample Characteristics | Observed Candidate Behavior | Decision |
| :--- | :--- | :--- | :--- |
| **Level 2 (Reject)** | Writes generic sales pitch slides filled with buzzwords. Cannot execute the terminal CLI or extract counterexample numbers. Explains the issue vaguely as "a balance calculation glitch." | Cannot read Python code or explain ledger math. Takes a defensive posture when questioned on technical details. Suggests blocking customer deployments on day 1 without staging. | Strong No |
| **Level 3 (Borderline)** | Finds the negative amount bug but writes a dry incident summary without quantifying financial risk. Produces a valid JSON receipt but misses the verified diff. | Solves the technical task but communicates like an individual contributor rather than a trusted technical advisor. Pilot plan lacks explicit commercial milestones. | Leaning No / Borderline |
| **Level 5 (Strong Hire)** | Reproduces bug in 5 minutes. Writes a pristine 1-page postmortem connecting arithmetic bypass to real cash reconciliation exposure. Designs a staged 14-day non-blocking pilot with explicit conversion criteria. | Demonstrates deep financial systems literacy. Speaks with staff-level rigor and zero hype. Instantly builds trust with skeptical engineering leadership. | Strong Hire |

---

## 5. Role 4 Calibration: Founding Product Designer (DevTools)

### 5.1 Exercise Context Recap
The candidate must design a high-density, keyboard-driven Counterexample Stepper and Patch Verification Panel for Ayentra Studio (`src/ayentra/site/`), strictly applying the Soft Neutral Light design tokens, WCAG AA contrast rules, and developer ergonomics.

### 5.2 Complete Reference Solution

#### Reference Layout Architecture
- **Pane 1: Target Explorer (260px fixed width):** Clean vertical list of audited files. Status badges (`1 fail`, `4 pass`). Sub-second timing receipt at top.
- **Pane 2: Counterexample Stepper (Flex 1):** Chronological step cards with discrete step tokens (`Step 01`, `Step 02`). Visual state delta pills (`balance: 1000 -> 1050`, `escrow: 0 -> -50`). Highlighting the exact violated assertion in red.
- **Pane 3: Patch Verification Panel (380px fixed width):** Unified diff viewer with syntax tokens. Sandbox gate receipt (`3 of 3 gates passed`). Primary action buttons: `Apply Patch [Alt+Enter]` and `Rerun Sweep [R]`.

#### Reference Component Implementation (HTML and CSS Tokens)

```html
<!-- counterexample_stepper.html -->
<div class="inspector-grid">
  <!-- Pane A: Target Explorer -->
  <aside class="target-pane" role="navigation" aria-label="Target Explorer">
    <div class="pane-header">
      <span class="pane-title">Targets</span>
      <span class="receipt-badge">38.4ms</span>
    </div>
    <ul class="target-list" role="listbox">
      <li class="target-item is-active" role="option" aria-selected="true" tabindex="0">
        <span class="status-indicator status-fail"></span>
        <div class="target-meta">
          <span class="target-file">customer_pilot.py</span>
          <span class="target-class">EnterprisePaymentLedger</span>
        </div>
      </li>
    </ul>
  </aside>

  <!-- Pane B: Counterexample Stepper -->
  <main class="stepper-pane" role="region" aria-label="Counterexample Stepper">
    <div class="stepper-header">
      <h2 class="stepper-title">Counterexample Trace (Seed 42)</h2>
      <div class="stepper-controls">
        <kbd class="keycap">J</kbd><kbd class="keycap">K</kbd> <span>Step through trace</span>
      </div>
    </div>
    
    <div class="step-card is-initial">
      <div class="step-badge">Step 00: Initial State</div>
      <div class="state-row">
        <code>self.available = 1000</code>
        <code>self.escrow = 0</code>
        <code>self.total_funds = 1000</code>
      </div>
    </div>

    <div class="step-card is-violation">
      <div class="step-badge step-fail">Step 01: Invariant Violation</div>
      <div class="step-call">
        <code>hold_in_escrow(amount=-50, tx_id="tx_1")</code>
      </div>
      <div class="state-delta">
        <span class="delta-item delta-bad">escrow: 0 &rarr; -50</span>
        <span class="delta-item delta-warn">available: 1000 &rarr; 1050</span>
      </div>
      <div class="assertion-alert" role="alert">
        <strong>Violation:</strong> <code>self.escrow >= 0</code> failed with value <code>-50</code>
      </div>
    </div>
  </main>

  <!-- Pane C: Patch Verification Panel -->
  <aside class="patch-pane" role="region" aria-label="Patch Resolution">
    <div class="patch-header">
      <h3 class="patch-title">Synthesized Patch</h3>
      <span class="gate-receipt">3/3 Gates Passed</span>
    </div>
    <div class="diff-viewer">
      <pre><code><span class="diff-del">-        if amount &lt;= self.available:</span>
<span class="diff-add">+        if 0 &lt; amount &lt;= self.available:</span></code></pre>
    </div>
    <div class="patch-actions">
      <button class="btn btn-primary" id="btn-apply-patch">
        Apply Patch <kbd class="keycap-btn">Alt+Enter</kbd>
      </button>
      <button class="btn btn-secondary" id="btn-rerun">
        Rerun Sweep <kbd class="keycap-btn">R</kbd>
      </button>
    </div>
  </aside>
</div>
```

```css
/* studio_tokens.css */
:root {
  --bg-app: #F6F5F2;
  --bg-surface: #FCFCFA;
  --bg-card: #FFFFFF;
  --bg-code: #1A1D20;
  --border-subtle: #EBE8E0;
  --border-default: #DFDBD0;
  --text-primary: #191B1F;
  --text-secondary: #525761;
  --pass-accent: #166534;
  --pass-bg: #DCFCE7;
  --fail-accent: #991B1B;
  --fail-bg: #FEE2E2;
  --focus-ring: #2563EB;
}

body {
  background-color: var(--bg-app);
  color: var(--text-primary);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  margin: 0;
}

.inspector-grid {
  display: grid;
  grid-template-columns: 260px 1fr 380px;
  height: 100vh;
  background-color: var(--bg-app);
}

.target-pane, .patch-pane {
  background-color: var(--bg-surface);
  border-right: 1px solid var(--border-default);
  padding: 16px;
  overflow-y: auto;
}

.patch-pane {
  border-right: none;
  border-left: 1px solid var(--border-default);
}

.stepper-pane {
  padding: 24px;
  overflow-y: auto;
  background-color: var(--bg-app);
}

.step-card {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  padding: 16px;
  margin-bottom: 12px;
}

.step-card.is-violation {
  border-color: #F87171;
  border-left: 4px solid var(--fail-accent);
}

.assertion-alert {
  background-color: var(--fail-bg);
  color: var(--fail-accent);
  padding: 10px 14px;
  border-radius: 4px;
  margin-top: 12px;
  font-size: 13px;
}

.diff-viewer {
  background-color: var(--bg-code);
  border-radius: 6px;
  padding: 12px;
  overflow-x: auto;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
}

.diff-del { color: #FCA5A5; }
.diff-add { color: #86EFAC; }

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 40px;
  padding: 0 16px;
  border-radius: 6px;
  font-weight: 500;
  font-size: 13px;
  cursor: pointer;
  border: 1px solid transparent;
}

.btn:focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
}

.btn-primary {
  background-color: #121417;
  color: #FFFFFF;
}

.btn-secondary {
  background-color: var(--bg-surface);
  border-color: var(--border-default);
  color: var(--text-primary);
}

.keycap, .keycap-btn {
  background: rgba(0, 0, 0, 0.06);
  border: 1px solid var(--border-default);
  border-radius: 3px;
  padding: 2px 6px;
  font-size: 11px;
  font-family: monospace;
}

.keycap-btn {
  background: rgba(255, 255, 255, 0.2);
  border-color: rgba(255, 255, 255, 0.4);
  color: #FFFFFF;
  margin-left: 8px;
}
```

### 5.3 Side-by-Side Candidate Work Sample Comparisons

| Level | Work Sample Characteristics | Observed Candidate Behavior | Decision |
| :--- | :--- | :--- | :--- |
| **Level 2 (Reject)** | Cluttered dark-mode UI with bright neon accents, low contrast (<3:1), and mouse-only click targets. Missing keyboard shortcuts and ARIA tags. Touch targets are under 28px. | Prioritizes flashy visual flair over usability. Cannot write clean semantic HTML or CSS. Does not know WCAG AA standards. | Strong No |
| **Level 3 (Borderline)** | Applies basic color tokens but creates a 2-pane view that squashes code diffs. Keyboard navigation is limited to browser Tab defaults. Focus rings are inconsistent. | Competent visual layouts but lacks developer workflow empathy. Treats diffs as plain text blocks. Does not consider keyboard power users. | Leaning No / Borderline |
| **Level 5 (Strong Hire)** | Delivers a disciplined 3-pane layout mapped strictly to Soft Neutral Light tokens. Implements J/K trace stepping and Alt+Enter patch execution. Meets WCAG AA contrast standards. Provides modular, production-ready CSS. | Uncompromising craft. Eliminates all visual clutter. Designs developer interfaces that feel as fast and tactile as Linear, Stripe, and GitHub CLI. | Strong Hire |

---

## 6. Evidence-Based Debrief Protocol and Conflict Reconciliation

When interviewers have conflicting scores, the hiring loop resolves disagreements through observable evidence, not seniority or charisma.

### 6.1 The 4-Step Reconciliation Process
1. **Fact Audit:** The debrief lead reads all logged code samples, command outputs, and verbatim candidate quotes. Subjective commentary is stripped.
2. **Benchmark Matching:** The committee compares the candidate's code against the Level 2, Level 3, and Level 5 reference samples in this packet.
3. **Gap Verification:** If an interviewer claims the candidate struggled with concurrency or AST nodes, they must point to the failing test case or incorrect line of code written during Stage 2.
4. **Resolution Call:**
   - If the code passes the evaluation test harness and executes cleanly: Candidate advances.
   - If the code fails basic edge cases and required direct interviewer intervention: Candidate is rejected.
   - If evidence is genuinely missing on a critical requirement: A 30-minute targeted technical screen is scheduled immediately.

### 6.2 Banned Debrief Phrases and Required Replacements

| Banned Subjective Phrase | Required Evidence-Based Translation |
| :--- | :--- |
| "I didn't get a strong staff feel from them." | "Candidate took 45 minutes to implement an AST visitor and missed augmented assignments." |
| "They seemed super smart and articulate." | "Candidate wrote a clean stateful property machine in 30 lines that shrunk the trace in 120ms." |
| "I'm worried about culture fit." | "Candidate was defensive when presented with a failing counterexample and blamed the test harness." |
| "Their background is impressive." | "Regardless of past employers, candidate could not parse a unified diff without external packages." |

---

## 7. Executive Reference Check Script

For early-stage founding team members, reference calls are factual audits, not routine formalities. Conduct these 20-minute phone interviews with direct engineering managers or technical peers who reviewed their pull requests.

### 7.1 Reference Question Script

#### Question 1: Code Output and Delivery Speed
"When you worked together, how would you describe their speed of shipping production-ready code compared to other senior engineers on the team? Can you give one specific example of a complex feature or system they shipped independently from scratch?"
- *Target:* Differentiates high-velocity self-starters from engineers who need continuous oversight.

#### Question 2: Edge-Case Rigor and Production Outages
"When production bugs or outages occurred in systems they owned, what was their debugging discipline like? Did they find and fix edge cases proactively, or did bugs frequently slip through into production?"
- *Target:* Verifies paranoia around race conditions, arithmetic boundaries, and system failure modes.

#### Question 3: Technical Pushback and Handling Conflict
"Tell me about a time when they strongly disagreed with an architectural decision or technical direction. How did they handle that disagreement, and what was the outcome?"
- *Target:* Evaluates intellectual honesty, adherence to data and code evidence, and absence of toxic ego.

#### Question 4: Autonomous Ownership
"In an early-stage startup where there are no product managers, minimal documentation, and shifting priorities, how well do you think they would operate? Do they thrive with ambiguity, or do they require structured requirements?"
- *Target:* Identifies whether the candidate has founding engineer resilience.

#### Question 5: Re-hire Ultimate Test
"If you were starting a new software company tomorrow, would you actively fight to recruit them as one of your first five founding teammates? Why or why not?"
- *Target:* Any hesitation, qualified answer, or polite demurral is an immediate signal to dig deeper into technical gaps.

---

## 8. Summary Checklist for Interview Loop Conduct

Before marking an interview complete:
- [ ] Code samples, terminal logs, and test results are copied into the scorecard.
- [ ] No em-dashes (`\u2014`) or en-dashes (`\u2013`) are present in notes or candidate feedback.
- [ ] Scores are mapped to the 1 to 5 anchors with written code justifications.
- [ ] Candidate communications remain paused until executive debrief approval.

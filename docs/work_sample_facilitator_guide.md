# Ayentra Founding Engineer Live Work-Sample and Pair-Debugging Facilitator Guide
Version: 1.0.0
Author: Hiring Partner (Ayentra)
Target: Technical Interview Facilitators and Founding Engineering Leads
Standard: Ayentra Human Taste and Craft Playbook

---

## 1. Facilitator Principles and Session Structure

This guide defines the standardized 60-minute live pair-debugging session for Ayentra founding engineering candidates. The objective is to evaluate how a candidate thinks, inspects unfamiliar code, runs terminal diagnostics, and isolates bugs under realistic conditions.

We do not test algorithmic puzzles or whiteboard trivia. We evaluate working code on real Ayentra targets using actual repository commands:
- `ayentra check`
- `ayentra dogfood`
- `ayentra pr-mock`

### 1.1 Core Rules for the Interview Facilitator
1. **Act as a Collaborative Peer:** Treat the candidate like a peer on their first week. You are pairing on a real bug, not proctoring an exam.
2. **Observe Terminal and Tool Hygiene:** Watch how the candidate operates the terminal, reads stack traces, and runs tests. Do they use clean flags? Do they inspect exit codes?
3. **Strict Hint Discipline:** Adhere strictly to the Allowed Hints protocol. Disqualifying hints immediately mark the candidate below bar on autonomous problem solving.
4. **Log Verbatim Code Evidence:** Transcribe exact commands executed, test durations, and specific candidate statements. Never write subjective impressions like "good communication."
5. **Enforce the 3-Second Rule:** The candidate must care about execution speed. Slow implementations or unconstrained search spaces must be questioned directly.

### 1.2 The Standard 60-Minute Session Timeline

```
+-------------------------------------------------------------------------------+
| Minute 00 to 15: Target Reproduction & Initial Inspection                      |
| - Candidate clones repo, runs basic check commands, and inspects targets.     |
| - Reproduces invariant violation using deterministic seed.                   |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| Minute 15 to 30: Invariant Formulation & Root Cause Analysis                  |
| - Candidate traces counterexample execution through target state machine.     |
| - Explains exact mathematical or concurrency bypass mechanism.                |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| Minute 30 to 45: Live Pair-Debugging & Patch Construction                     |
| - Candidate writes guard logic, AST transform, or CLI enhancement.           |
| - Verifies fix against candidate counterexample trace.                        |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| Minute 45 to 60: Regression Sweep, Performance Verification & Debrief         |
| - Runs full test suite and checks for regression escapes.                     |
| - Verifies sub-second execution budget. Completes BARS evidence table.        |
+-------------------------------------------------------------------------------+
```

---

## 2. Track 1: Founding Verification Engine Engineer

- **Core Focus:** Property-based testing, Hypothesis strategy mapping, counterexample shrinking, and thread interleaving exploration.
- **Relevant Source Files:** `src/ayentra/engine.py`, `src/ayentra/contracts.py`, `src/ayentra/concurrency.py`.
- **Target Exercise Code:** `examples/scheduler_race.py` and `examples/customer_pilot.py`.

### 2.1 Live Scenario and Repository Commands
The facilitator shares their screen or provides repository access. The candidate is tasked with running the verification engine against `examples/scheduler_race.py`, where multi-threaded compute allocation causes intermittent capacity leaks.

```bash
# Command 1: Run standard verification sweep
ayentra check examples/scheduler_race.py --seed 42 --max-examples 120

# Command 2: Inspect execution trace and counterexample output
ayentra check examples/scheduler_race.py --json-out receipt.json --summary
```

### 2.2 Timed 15-Minute Checkpoints

#### Minute 00 to 15: Setup and Reproduction
- **Task:** Candidate inspects `examples/scheduler_race.py`, runs `ayentra check`, and observes the interleaving invariant violation.
- **What to Observe:** Does the candidate check the invariant definition (`0 <= self.allocated <= self.capacity`)? Do they observe that `check_concurrency=True` is enabled?
- **Allowed Hint:** "Take a look at how `ResourceScheduler.allocate` modifies `self.allocated` when multiple threads execute concurrently."
- **Disqualifying Hint:** "You need to add a threading lock to line 18 because `allocate` lacks mutex synchronization."

#### Minute 15 to 30: Root Cause Analysis
- **Task:** Candidate explains why the race condition occurs: read-modify-write without memory barriers allows two threads to read `self.allocated` simultaneously and over-allocate capacity.
- **What to Observe:** Can the candidate explain the thread scheduling sequence that triggers the counterexample? Do they recognize the state space explosion in thread interleaving?
- **Allowed Hint:** "How does Python thread scheduling behave between bytecode instructions when modifying instance attributes?"
- **Disqualifying Hint:** "The bug is on line 21: `self.allocated += amount` is not an atomic operation in Python bytecode."

#### Minute 30 to 45: Pair-Debugging and Implementation
- **Task:** Candidate modifies `examples/scheduler_race.py` or `src/ayentra/engine.py` to handle thread synchronization or implement bounded interleaving checks.
- **What to Observe:** Does the candidate introduce a clean `threading.Lock`? Do they ensure `release()` is also protected by the same mutex?
- **Allowed Hint:** "Consider how `concurrency.py` detects context switches around mutable attributes."
- **Disqualifying Hint:** "Write `with self._lock:` inside both allocate and release methods."

#### Minute 45 to 60: Regression Sweep and Performance Verification
- **Task:** Re-run verification sweep across 120 generated cases. Confirm that the race condition is resolved and execution completes in under 800 milliseconds.
- **What to Observe:** Does the candidate test negative allocation amounts? Do they check boundary capacity limits?
- **Allowed Hint:** "Run `ayentra check` with `--seed 99` to verify that the fix holds across different seeds."
- **Disqualifying Hint:** "Now test `amount=-1` because negative allocations can cause underflow."

---

## 3. Track 2: Founding AST and Sandbox Repair Engineer

- **Core Focus:** Abstract Syntax Tree analysis, code transformation passes, automated patch synthesis, and isolated sandbox regression testing.
- **Relevant Source Files:** `src/ayentra/ast_analyzer.py`, `src/ayentra/repair.py`, `src/ayentra/regression.py`.
- **Target Exercise Code:** `examples/inventory_ledger.py` and `src/ayentra/repair.py`.

### 3.1 Live Scenario and Repository Commands
The candidate must inspect `examples/inventory_ledger.py`, run `ayentra check` to trigger a conservation invariant violation, and then implement an AST transformation pass in `repair.py` that automatically synthesizes a verified fix.

```bash
# Command 1: Check inventory ledger invariant violation
ayentra check examples/inventory_ledger.py --seed 42

# Command 2: Run dogfood pattern verification sweep
ayentra dogfood --pattern inventory --summary-only
```

### 3.2 Timed 15-Minute Checkpoints

#### Minute 00 to 15: Setup and Reproduction
- **Task:** Candidate inspects `examples/inventory_ledger.py` and runs `ayentra check`. Observes that `reserve()` allows negative units, which inflates available inventory and violates conservation laws.
- **What to Observe:** Does the candidate inspect the AST structure of `InventoryLedger`? Do they notice how `self.available` and `self.reserved` are modified?
- **Allowed Hint:** "Look at how `reserve` validates incoming unit parameters before updating state."
- **Disqualifying Hint:** "Negative unit inputs bypass the check: you need to disallow `units <= 0`."

#### Minute 15 to 30: AST Analysis and Mutation Extraction
- **Task:** Candidate reviews `src/ayentra/repair.py` (`_apply_class_conservation_transform`). Explains how the AST visitor identifies mutating methods and generates candidate preconditions.
- **What to Observe:** Can the candidate work with `ast.NodeTransformer`? Do they understand `ast.Compare`, `ast.LtE`, and `ast.Constant` nodes?
- **Allowed Hint:** "In `repair.py`, look at how `_synthesize_function_preconditions` constructs comparison nodes."
- **Disqualifying Hint:** "Just use `ast.parse('if units <= 0: return False')` and insert it into node.body[0]."

#### Minute 30 to 45: Live Patch Synthesis Pass
- **Task:** Candidate extends or refines the AST transformer to generate a clean non-negative guard condition and preserves source code formatting.
- **What to Observe:** Does the candidate call `ast.fix_missing_locations(node)`? Does the transformed source code compile cleanly without syntax errors?
- **Allowed Hint:** "Check how line numbers and AST parent references are preserved after inserting nodes."
- **Disqualifying Hint:** "Call `ast.fix_missing_locations` right here, or `compile()` will raise an exception."

#### Minute 45 to 60: Sandbox Verification and Regression Check
- **Task:** Candidate executes `ayentra check examples/inventory_ledger.py` to confirm that the synthesized patch passes all 3 sandbox gates (counterexample check, invariant sweep, regression test).
- **What to Observe:** Does the candidate inspect the unified diff generated by `difflib`? Is the diff minimal and readable?
- **Allowed Hint:** "Check whether `tests/test_pilot_workflow.py` passes with your synthesized patch."
- **Disqualifying Hint:** "Your diff modified 5 unnecessary lines; revert lines 40 to 45."

---

## 4. Track 3: Founding Developer Experience and CI Systems Engineer

- **Core Focus:** CLI performance, sub-second execution, SARIF 2.1.0 output formatting, and GitHub Actions PR comment generation.
- **Relevant Source Files:** `src/ayentra/cli.py`, `src/ayentra/report.py`, `src/ayentra/dogfood.py`.
- **Target Exercise Code:** `examples/customer_pilot.py` and `examples/fixtures/pr_diff_balance_leak.patch`.

### 4.1 Live Scenario and Repository Commands
The candidate is tasked with running `ayentra pr-mock` and `ayentra check` against PR diff fixtures, diagnosing a slow CLI path, and generating valid SARIF 2.1.0 telemetry for GitHub Code Scanning.

```bash
# Command 1: Generate PR review comment mockup
ayentra pr-mock examples/customer_pilot.py --sarif test.sarif --pr-comment pr_comment.md

# Command 2: Run CI verification with timing output
ayentra check examples/customer_pilot.py --ci --summary
```

### 4.2 Timed 15-Minute Checkpoints

#### Minute 00 to 15: Setup and CLI Performance Audit
- **Task:** Candidate runs `ayentra pr-mock` and profiles startup latency. Notes any unnecessary top-level module imports that increase boot time.
- **What to Observe:** Does the candidate measure wall-clock time (`time.perf_counter()`)? Do they inspect CLI argument parsing speed?
- **Allowed Hint:** "Check the startup time of `cli.py` when running with the `--help` flag."
- **Disqualifying Hint:** "Move the `import pandas` and `import requests` inside the command handler to make it faster."

#### Minute 15 to 30: SARIF 2.1.0 Schema Verification
- **Task:** Candidate inspects `test.sarif` generated by `ayentra pr-mock`. Verifies that physical location line numbers, rule IDs, and artifact URIs comply with SARIF 2.1.0 specifications.
- **What to Observe:** Does the candidate check the `$schema` URL? Do they verify that `region.startLine` points to the exact failing method?
- **Allowed Hint:** "How does GitHub Code Scanning display inline suggested fixes from the `fixes` block in a SARIF report?"
- **Disqualifying Hint:** "The `artifactLocation.uri` must be relative to the repository root, not an absolute path."

#### Minute 30 to 45: PR Comment Microcopy and Formatting
- **Task:** Candidate reviews the generated markdown comment (`pr_comment.md`). Cleans up any verbose output, removes marketing words, and ensures the diff is clearly rendered.
- **What to Observe:** Does the candidate adhere to the Human Taste Playbook? Are messages verb-first, direct, and factual?
- **Allowed Hint:** "Review the PR comment text against the microcopy principles in `human_taste_playbook.md`."
- **Disqualifying Hint:** "Remove the buzzwords from the table header."

#### Minute 45 to 60: End-to-End Pipeline Verification
- **Task:** Candidate runs the entire pipeline end-to-end on `examples/fixtures/pr_diff_balance_leak.patch` and confirms that execution completes in under 400 milliseconds.
- **What to Observe:** Does the command exit with status code 1 on invariant failure? Does it exit with 0 on clean code?
- **Allowed Hint:** "Check the process return code in your shell after running the check."
- **Disqualifying Hint:** "You forgot to call `sys.exit(1)` when violations are present."

---

## 5. Behaviorally Anchored Rating Scale (BARS) 1 to 4 Master Rubric

The facilitator must evaluate candidate performance across 4 explicit behavioral anchors. Half-scores (such as 2.5 or 3.5) are strictly prohibited.

| Rating Level | Definition | Observable Behavioral Evidence |
| :--- | :--- | :--- |
| **1 - Below Basic (Disqualified)** | Fails foundational prerequisites; writes non-functional or unsafe code. | Cannot run basic CLI commands without constant guidance. Proposes string replacements instead of AST operations. Ignores obvious failure modes. Blames tools or dependencies. |
| **2 - Basic (Marginal / Reject)** | Solves basic paths but requires significant hints; misses subtle edge cases. | Identifies invariant failure only after direct hints. Struggles to inspect AST nodes or thread interleavings. Produces working code but leaves unhandled edge cases (negative numbers, NoneType). Tolerates 3+ second execution times without concern. |
| **3 - Proficient (Meets Founding Bar)** | Autonomously solves target problem; writes clean, verified, performant code. | Reproduces bugs independently in under 10 minutes. Explains exact mathematical or concurrency root causes. Implements clean AST transforms or CLI logic with proper location fixing. Respects sub-second performance budgets. Communicates clearly and factually. |
| **4 - Advanced (Exceeds Bar / Staff Lead)** | Exceptional speed, system paranoia, and craft; spots architectural implications. | Pinpoints root cause in under 5 minutes. Proactively checks arithmetic overflow, re-entrancy, and thread boundaries without prompting. Writes minimal, self-documenting code. Identifies broader architectural improvements in `src/ayentra`. Demonstrates exemplary staff-level craft. |

---

## 6. Facilitator Evidence-Capture Sheet

The facilitator must complete this sheet within 15 minutes of session completion. All ratings must be justified by verbatim code evidence and command output.

```markdown
# Live Work-Sample Evidence Capture Sheet

## Session Metadata
- Candidate Name: [Full Name]
- Role Track: [Verification Engine / AST Repair / DX & CI]
- Facilitator: [Facilitator Name]
- Date: [YYYY-MM-DD]
- Git Commit / Target SHA: [Commit SHA]

## 1. Concrete Observed Evidence Log
- Minute 00-15 (Reproduction): [Exact command run, exit code, time taken]
- Minute 15-30 (Root Cause): [Verbatim explanation given by candidate]
- Minute 30-45 (Implementation): [Number of lines written, AST nodes used, syntax checks]
- Minute 45-60 (Verification): [Final sweep result, duration in ms, test status]

## 2. Hints Provided Log
- Hint 1: [Time: MM:SS] - [Exact words spoken by facilitator] (Category: Allowed / Disqualifying)
- Hint 2: [Time: MM:SS] - [Exact words spoken by facilitator] (Category: Allowed / Disqualifying)

## 3. BARS 1-4 Competency Ratings

| Competency Dimension | BARS (1-4) | Concrete Code Evidence Justifying Rating |
| :--- | :---: | :--- |
| **1. Diagnostic & Terminal Hygiene** | [ ] | [Log command line proficiency, flags used, exit code checks] |
| **2. Domain Mechanics (AST/Engine/CLI)** | [ ] | [Log code correctness, node manipulation, thread handling] |
| **3. Edge-Case Paranoia** | [ ] | [Log handling of negative numbers, boundaries, races] |
| **4. Speed & Performance Discipline** | [ ] | [Log measured execution time, latency profiling, imports] |
| **5. Technical Communication & Craft** | [ ] | [Log absence of fluff, direct factual explanations] |
| **Overall Work-Sample Score** | **[ ]** | *(Arithmetic average of 5 dimensions)* |

## 4. Final Recommendation
Select exactly one:
- [ ] **Strong Hire (Score 3.8 - 4.0):** World-class founding engineer; immediately raises the technical bar.
- [ ] **Hire (Score 3.0 - 3.7):** Proficient founding engineer; writes verified code autonomously.
- [ ] **Reject (Score 1.0 - 2.9):** Below bar on technical depth, edge-case rigor, or execution speed.

**Facilitator Signature:** ___________________________  **Date:** ______________
```

# Ayentra: Invariant-Aware Verification Gate

Ayentra checks whether your Python code violates explicitly defined behavioral invariants, finds minimal reproducible counterexamples using property-based shrinking and deterministic thread interleaving, and verifies candidate fixes in an isolated sandbox against both the invariant and your existing `pytest` regression suite before merge.

[![Live Showcase](https://img.shields.io/badge/Live_Showcase-ayentra.openbot.site-0F766E?style=flat-square)](https://ayentra-self-healing-ci-gate-for-python-ayentra-gekf76yujn.openbot.site)
[![Verification Engine](https://img.shields.io/badge/Verification_Gate-Invariant--Aware-1E232A?style=flat-square)](https://ayentra-self-healing-ci-gate-for-python-ayentra-gekf76yujn.openbot.site#demo)
[![Enterprise Pilot](https://img.shields.io/badge/Enterprise_Pilot-docs%2Fdesign__partner__kit.md-2563EB?style=flat-square)](docs/design_partner_kit.md)
[![Security Policy](https://img.shields.io/badge/Security_Policy-SECURITY.md-166534?style=flat-square)](SECURITY.md)

- **Live Public Showcase**: [https://ayentra-self-healing-ci-gate-for-python-ayentra-gekf76yujn.openbot.site](https://ayentra-self-healing-ci-gate-for-python-ayentra-gekf76yujn.openbot.site)
- **Interactive Verification Studio**: [Live Invariant Inspector & PR Bot Simulator](https://ayentra-self-healing-ci-gate-for-python-ayentra-gekf76yujn.openbot.site#demo)
- **Enterprise Design Partner Pilot Guide**: [docs/design_partner_kit.md](docs/design_partner_kit.md)
- **Design Partner Executive ROI & CI Time-Saved Calculator**: [docs/design_partner_roi_calculator.md](docs/design_partner_roi_calculator.md)

## Design Principles & Technical Boundaries

1. **Explicit Invariants First**: AST analysis cannot guess intended business rules. Invariants are declared explicitly via `@invariant(...)` decorators or workspace `ayentra.toml` contracts. Structural hints extracted by the AST analyzer are always labeled `Candidate Suggestion (Requires Developer Approval)` and never enforced automatically.
2. **Exact Verification Reporting, Strategy Synthesis & Async Coroutine Support**: Ayentra synthesizes property strategies from Python type annotations (including primitives, `decimal.Decimal`, `datetime.date`, `datetime.datetime`, `Optional`/`Union`, `list`, `dict`, `tuple`, `set`, `frozenset`, `Literal`, `Enum`, and nested `@dataclass` types), executes both synchronous callables and `async def` coroutine functions and methods (including AST candidate invariant extraction and sandbox guard repair for `async def`, `Decimal` zero-division, and date/datetime order bounds), and reports the exact verification method (`Property-Based Shrinking via Hypothesis` or `Deterministic Thread Interleaving Check`), the exact number of cases or schedules evaluated, the tested input domain bounds, and the deterministic `--seed`.
3. **Minimal Reproducible Counterexamples & Concurrency Interleaving**: When an invariant fails, Ayentra shrinks the failing input vector or concurrent schedule to its smallest reproducible form. For `@invariant(..., check_concurrency=True)` class invariants, Ayentra explores barrier-synchronized thread schedules with line-level preemption (`sys.settrace`) across single-argument, multi-argument, and cross-method calls (e.g., concurrent `deposit`/`withdraw` or `reserve`/`release` pairs) to expose TOCTOU race conditions.
4. **Non-Destructive Sandbox Patch Verification**: Ayentra never overwrites source files silently. It synthesizes a candidate unified diff, applies it inside an isolated temporary directory copy, and runs three checks:
   - Replay of the exact failing counterexample
   - Full property-based and concurrency invariant sweep
   - The project's existing `pytest` regression suite
5. **Deterministic Execution Receipts**: Outputs a `VerificationReport` JSON receipt containing the SHA-256 digest of the source file, seed, domain bounds, pass/fail counts, and actual measured execution time in milliseconds.

## CLI Reference

### `ayentra check <target>`

Accepts either a single Python file or a directory (`ayentra check <dir/>`). When passed a directory, Ayentra discovers all non-test `.py` files with explicit `@invariant` decorators or matching `ayentra.toml` rules, runs the verification gate on each target, prints a `Directory Verification Summary` table (`File`, `Explicit Invariants`, `Cases Evaluated`, `Violations`, `Status`, `Time (ms)`), and exits with code `1` if any invariant fails (`0` if all pass). Passing `--json-out <path.json>` with a directory target writes an aggregate JSON receipt containing `"directory"`, `"total_files_checked"`, `"failed_files_count"`, and `"reports"`.

```bash
# Check a single module with a deterministic seed
ayentra check examples/scheduler_race.py --seed 42

# Check an entire directory of modules and write a JSON receipt
ayentra check examples/ --seed 42 --json-out report.json
```

### `ayentra apply-patch <target> [--yes]`

Synthesizes a candidate repair for a failing target, runs the 3-stage sandbox verification gate (counterexample replay, property-based/concurrency sweep, and `pytest` regression suite), and prints the unified diff. By default, `apply-patch` runs in non-destructive preview mode. Pass `--yes` to write the patch to disk only after all three sandbox stages pass (`VERIFIED CANDIDATE FIX`).

```bash
# Preview the verified unified diff without modifying the file
ayentra apply-patch examples/inventory_ledger.py --seed 42

# Write the patch to disk if and only if all 3 sandbox checks pass
ayentra apply-patch examples/inventory_ledger.py --seed 42 --yes
```

### `ayentra suggest-invariants <target>`

Analyzes the module AST and outputs candidate invariant expressions labeled `Candidate Suggestion (Requires Developer Approval)`.

```bash
ayentra suggest-invariants examples/inventory_ledger.py
```

### `ayentra verify-patch <target> [--candidate-file <path>]`

Verifies either a user-supplied candidate file (`--candidate-file`) or a synthesized patch inside an isolated sandbox copy without modifying the target file.

### `ayentra studio`

Launches the local browser verification inspector in the Soft Neutral Light theme (`#F6F5F2` background, `#FCFCFA` surface, `#FFFFFF` panels, `#1E232A` text).

- **Status Filter Bar**: Filter the workspace view across `All Invariants`, `Violations Only`, and `Candidate Suggestions`.
- **Keyboard Shortcut**: Press `Ctrl+Enter` or `Alt+Enter` from anywhere in the inspector to trigger `Run Verification Gate`.
- **Copy Unified Diff**: Section 4 (`4. Candidate Patch (Unified Diff)`) includes a one-click `Copy Unified Diff` button to copy the verified patch diff directly to the clipboard.
- **Apply Verified Patch**: When a candidate patch passes all 3 sandbox verification gates (`VERIFIED CANDIDATE FIX`), Section 4 renders a gated `Apply Verified Patch` button (`POST /api/apply-patch`) to write the verified fix to disk and update the state to `Verified Patch Applied`.
- **Export JSON Receipt**: Section 5 (`5. Post-Fix Verification Summary & Execution Receipt`) includes a one-click `Export JSON Receipt` button to download `ayentra-receipt.json` directly from the browser.

```bash
ayentra studio --port 8420
```

### `ayentra init [--ci] [--path <dir>]`

Scaffolds `ayentra.toml` configuration and optional `.github/workflows/ayentra.yml` for GitHub Actions CI.

```bash
# Initialize local configuration and GitHub Actions CI workflow
ayentra init --ci
```

### `ayentra pr-mock <target> [--pr-comment <path.md>] [--sarif <path.sarif>]`

Generates a structured GitHub pull request review comment with plain-English risk categorization, minimal shrunk counterexample, collapsible unified diff, and 1-click merge command.

```bash
# Generate simulated PR review comment for customer pilot ledger
ayentra pr-mock examples/customer_pilot.py --pr-comment pr_review.md
```

## Workspace `ayentra.toml` Contract Discovery

Invariants can be declared inline with `@invariant(...)` and `@domain(...)` decorators or externally in `ayentra.toml`. When checking a target file, Ayentra checks the target's directory and walks up parent directories (up to the workspace root containing `ayentra.toml` or `pyproject.toml`) to discover `ayentra.toml` contract rules matching the target filename:

```toml
[[invariants]]
file = "inventory_ledger.py"
target = "InventoryLedger"
kind = "class"
expression = "self.available >= 0 and self.reserved >= 0"
check_concurrency = false
domain = { qty = { min = 1, max = 500 } }
```

## Enterprise Design Partner Pilot Guide

Grounded in `examples/customer_pilot.py`, this workflow demonstrates how engineering teams catch domain-level invariant violations before code reaches production.

### 1. Two-Command Zero-Config CI Onboarding

```bash
pip install ayentra
ayentra init --ci
```

Scaffolds `.github/workflows/ayentra.yml` and workspace `ayentra.toml`, running verification on push and pull request without cloud account setup.

### 2. Automated PR Review Comments and Collapsible Unidiff Workflow

```bash
ayentra pr-mock examples/customer_pilot.py --pr-comment pr_review.md
```

Generates a GitHub-native review comment with:
- Plain-English bug explanation
- Business risk rating (for example: `Critical risk: Financial balance corruption`)
- Shrunk minimal counterexample (`amount = -1`)
- Collapsible interactive unidiff `<details open><summary>View Unified Patch Diff</summary>...`
- Single-command remediation: `ayentra apply-patch examples/customer_pilot.py --yes`

### 3. GitHub Advanced Security SARIF 2.1.0 Code Scanning

```bash
ayentra check examples/customer_pilot.py --ci --sarif ayentra-report.sarif
```

Exports OASIS SARIF 2.1.0 compliant findings to GitHub Advanced Security code scanning, pinpointing the failing line and attaching the verified fix.

For the full enterprise pilot kit, ledger walkthrough, and direct outreach templates, see [docs/design_partner_kit.md](docs/design_partner_kit.md).

## Quickstart Benchmarks & Production Verification Metrics

Ayentra was verified against 7 real-world architectural patterns spanning financial ledgers, distributed rate limiters, thread barriers, and worker queues (`dogfood_receipt.json`).

| Target Architecture | Target Module | Evaluated Cases | Caught Violation | Sandbox Status |
| :--- | :--- | :--- | :--- | :--- |
| **Financial Escrow Ledger** | `examples/customer_pilot.py` | 69 cases | Negative balance drift | `VERIFIED CANDIDATE FIX` (100%) |
| **Distributed Rate Limiter** | `redis_token_bucket.py` | 37 cases | Token underflow DoS | `VERIFIED CANDIDATE FIX` (100%) |
| **Thread Task Scheduler** | `examples/scheduler_race.py` | 1 schedule | TOCTOU preemption race | `VERIFIED CANDIDATE FIX` (100%) |
| **Inventory Ledger** | `examples/inventory_ledger.py` | 23 cases | Negative stock overdraft | `VERIFIED CANDIDATE FIX` (100%) |
| **Async Task Pipeline** | `celery_task_queue.py` | 25 cases | Dropped active tasks | `VERIFIED CANDIDATE FIX` (100%) |
| **HTTP Connection Pool** | `requests_connection_pool.py` | 6 cases | Socket exhaustion leak | `VERIFIED CANDIDATE FIX` (100%) |
| **Telemetry Sensor Parser** | `examples/data_parser.py` | 12 cases | NaN / Inf float pass-through | `VERIFIED CANDIDATE FIX` (100%) |

**Summary**: 7 production targets scanned, 173 adversarial property cases evaluated, 7 invariant violations detected, and 7 candidate AST repairs verified through all 3 sandbox gates (replay, sweep, and pytest) with zero regressions.

Explore the interactive metrics directly on the [Live Public Showcase](https://ayentra-self-healing-ci-gate-for-python-ayentra-gekf76yujn.openbot.site#dogfood).

## Quickstart

```bash
# 1. Run existing unit tests (passes on standard happy-path inputs)
pytest examples/test_existing_suite.py

# 2. Run Ayentra verification gate across the examples directory or individual files
ayentra check examples/ --seed 42
ayentra check examples/scheduler_race.py --seed 42
ayentra check examples/inventory_ledger.py --seed 42
ayentra check examples/data_parser.py --seed 42

# 3. Preview or apply a sandbox-verified patch
ayentra apply-patch examples/data_parser.py --seed 42

# 4. Inspect AST candidate invariant suggestions
ayentra suggest-invariants examples/inventory_ledger.py

# 5. Launch the local browser verification inspector
ayentra studio --port 8420
```

## Public Showcase & Enterprise Documentation Suite

### Live Showcase & Demonstrations

- **Live Web Showcase**: [https://ayentra-self-healing-ci-gate-for-python-ayentra-gekf76yujn.openbot.site](https://ayentra-self-healing-ci-gate-for-python-ayentra-gekf76yujn.openbot.site)
- **Interactive Verification Demo**: [Ayentra Studio & PR Review Bot Simulator](https://ayentra-self-healing-ci-gate-for-python-ayentra-gekf76yujn.openbot.site#demo)
- **Production Wheel & Smoke Test Benchmarks**: [docs/benchmarks.md](docs/benchmarks.md)
- **Real-World Repair Benchmark & Latency Matrix**: [docs/repair_benchmark_matrix.md](docs/repair_benchmark_matrix.md)
- **Open-Source Trojan Horse Invariant Audit Pack**: [docs/oss_trojan_horse_audits.md](docs/oss_trojan_horse_audits.md)
- **Ground Truth Customer Pilot Ledger**: [examples/customer_pilot.py](examples/customer_pilot.py)

### Enterprise Security & Architecture

- **Security Policy & Vulnerability Reporting**: [SECURITY.md](SECURITY.md)
- **Enterprise Security Pack & CISO Architecture Review**: [docs/enterprise_security_pack.md](docs/enterprise_security_pack.md)
- **Security Audit & Invariant Verification Review**: [docs/security_audit.md](docs/security_audit.md)
- **SARIF 2.1.0 & GitHub Code Scanning Guide**: [docs/sarif_github_security_guide.md](docs/sarif_github_security_guide.md)
- **Software Bill of Materials (SBOM) & Provenance Manifest**: [docs/sbom_and_provenance_manifest.md](docs/sbom_and_provenance_manifest.md)
- **Enterprise Air-Gapped & Self-Hosted Runner Hardening**: [docs/airgapped_runner_hardening.md](docs/airgapped_runner_hardening.md)
- **Pre-Release Code Review Sign-Off**: [docs/code_review_signoff.md](docs/code_review_signoff.md)
- **Human-Craft & UI/UX Taste Audit Report**: [docs/taste_and_ui_audit_report.md](docs/taste_and_ui_audit_report.md)
- **Human-Craft, Voice & Zero-Buzzword Audit**: [docs/human_craft_voice_audit.md](docs/human_craft_voice_audit.md)

### Enterprise Pilot & Operations

- **Enterprise Design Partner Pilot Guide**: [docs/design_partner_kit.md](docs/design_partner_kit.md)
- **Design Partner Executive ROI & CI Time-Saved Calculator**: [docs/design_partner_roi_calculator.md](docs/design_partner_roi_calculator.md)
- **Pilot Onboarding Service Level Agreement**: [docs/pilot_onboarding_sla.md](docs/pilot_onboarding_sla.md)
- **Founding Team 30-60-90 Day Onboarding & Performance Scorecard**: [docs/onboarding_30_60_90_scorecard.md](docs/onboarding_30_60_90_scorecard.md)
- **Master Release Readiness & Go/No-Go Sign-Off Dossier**: [docs/release_go_no_go_dossier.md](docs/release_go_no_go_dossier.md)
- **Post-Launch 30-Day Engineering & GTM Execution Roadmap**: [docs/post_launch_30_day_roadmap.md](docs/post_launch_30_day_roadmap.md)
- **Launch Day Technical FAQ**: [docs/launch_day_faq.md](docs/launch_day_faq.md)
- **Launch War Room Incident Runbook**: [docs/launch_war_room_runbook.md](docs/launch_war_room_runbook.md)
- **Open-Source Maintainer PR Templates & Outreach**: [docs/oss_maintainer_pr_templates.md](docs/oss_maintainer_pr_templates.md)

### Engineering Hiring & Calibration

- **Hiring Committee Decision & Debrief Protocol**: [docs/hiring_committee_decision_protocol.md](docs/hiring_committee_decision_protocol.md)
- **Candidate Calibration & Assessment Packet**: [docs/candidate_calibration_packet.md](docs/candidate_calibration_packet.md)
- **Engineering Hiring Kit & Interview Rubrics**: [docs/hiring_kit.md](docs/hiring_kit.md)
- **Live Work-Sample & Pair-Debugging Facilitator Guide**: [docs/work_sample_facilitator_guide.md](docs/work_sample_facilitator_guide.md)
- **Founding Team Offer Letter, Equity & Reference Playbook**: [docs/founding_offer_and_reference_kit.md](docs/founding_offer_and_reference_kit.md)
- **Public Launch Kit & Outreach Strategy**: [docs/public_launch_kit.md](docs/public_launch_kit.md)

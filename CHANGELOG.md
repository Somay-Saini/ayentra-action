# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to Semantic Versioning.

## [0.1.0] - 2026-11-03

### Added

- **Invariant Verification Engine**:
  - Declarative `@invariant(...)` decorators and `ayentra.toml` workspace contract configuration.
  - Automatic hypothesis strategy synthesis from Python type annotations (primitives, `decimal.Decimal`, `datetime.date`, `datetime.datetime`, `Optional`, `Union`, `list`, `dict`, `tuple`, `set`, `frozenset`, `Literal`, `Enum`, and nested `@dataclass`).
  - Support for synchronous functions and `async def` coroutines.
  - Property-based adversarial input shrinking to isolate minimal counterexample vectors.
  - Machine-readable JSON execution receipts (`ayentra-receipt.json`) with target file SHA-256 digests, seeds, case counts, and execution metrics.

- **Deterministic Concurrency Exploration**:
  - `@invariant(..., check_concurrency=True)` decorator support for state machines.
  - Thread preemption with line-level execution tracing using `sys.settrace`.
  - Barrier synchronization across concurrent single-method, multi-argument, and cross-method invocation sequences (such as `reserve` and `release`).
  - Automated detection and trace shrinking for time-of-check to time-of-use (TOCTOU) race conditions.

- **Three-Stage Sandbox Auto-Patch Verification**:
  - Non-destructive candidate patch synthesis generating unified diffs.
  - Isolated temporary directory sandbox verification executing three sequential gates:
    1. Replay of minimal failing counterexample.
    2. Full property-based and concurrency invariant test sweep.
    3. Project existing pytest regression test execution.
  - Safe patch application to disk via `ayentra apply-patch <target> --yes`.

- **Security & CI Integrations**:
  - Native OASIS SARIF 2.1.0 report generation (`ayentra check --sarif <path.sarif>`) compatible with GitHub Advanced Security code scanning.
  - GitHub Actions composite action (`action.yml`) with automated `GITHUB_STEP_SUMMARY` generation and PR review commenting.
  - Plain-English business risk categorization: Critical (financial drift), High (operational integrity), and Medium (logic discrepancies).
  - Mock PR review generator (`ayentra pr-mock`) for local preview of bot feedback and unified diffs.

- **Ayentra Studio Local Inspector**:
  - Offline browser-based verification interface (`ayentra studio --port 8420`).
  - Soft Neutral Light design system: `#F6F5F2` base parchment, `#FCFCFA` cards, `#FFFFFF` panels, `#1E232A` slate text.
  - Status filtering by `All Invariants`, `Violations Only`, and `Candidate Suggestions`.
  - Global keyboard shortcuts (`Ctrl+Enter` and `Alt+Enter`) to trigger verification gates.
  - One-click unified diff clipboard export and gated patch application via `POST /api/apply-patch`.
  - One-click receipt export to download `ayentra-receipt.json`.

- **Dogfood Hub & Production Failure Patterns**:
  - Curated pattern repository in `dogfood_receipt.json` covering Celery queues, Redis token buckets, Requests connection pools, escrow payment ledgers, telemetry parsers, inventory ledgers, and scheduler race conditions.
  - Full reproducible CLI verification and auto-patch commands for all reference patterns.

- **Test Suite & Verification**:
  - 106 automated tests covering engine invariants, AST extraction, concurrency exploration, sandbox repairs, CLI subcommands, PR mock lifecycle, and studio web endpoints.

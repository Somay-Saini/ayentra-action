# Ayentra Founding Team 30-60-90 Day Onboarding and Performance Scorecard Playbook
Version: 1.0.0
Author: Hiring Partner (Ayentra)
Target: Founding Engineering Hires, Technical Leads, and CEO
Standard: Ayentra Human Taste and Craft Playbook

---

## 1. Founding Engineering Onboarding Philosophy and Operational Cadence

At Ayentra, onboarding is not an administrative orientation. It is a high-velocity sprint designed to build autonomous ownership within 72 hours. 

Founding team members do not read stale documentation for two weeks. They set up their local environments on Day 1, ship their first production pull request by Day 3, and take complete architectural ownership of core systems within 30 days.

### 1.1 The Core Operating Rules
1. **Ship on Day 3:** Every engineer merges a verified, tested pull request to production within their first 72 hours.
2. **Deterministic Calibration:** Performance is evaluated against observable metrics: test coverage, execution latency budgets, zero regression escapes, and PR velocity.
3. **Paranoia for Edge Cases:** We build verification tools for critical software. A silent false negative or unhandled race condition destroys developer trust. Paranoia is an explicit job requirement.
4. **The 3-Second Rule:** Everything we build must be fast. CLI commands run under 2 seconds; local AST scans complete under 100 milliseconds.
5. **No Corporate Jargon:** We communicate with direct staff-engineer precision. No fluff, no excuses, and zero marketing adjectives.

---

## 2. Role 1: Founding Verification Engine Engineer
- **Core Systems Owned:** `src/ayentra/engine.py`, `src/ayentra/contracts.py`, `src/ayentra/concurrency.py`.
- **Primary Mission:** Build and scale Ayentra's dynamic property verification, Hypothesis strategy synthesis, and concurrency interleaving exploration engines.

### 2.1 Day-1 Setup Protocol
1. Clone the repository and configure Python 3.11+ virtual environment:
   ```bash
   git clone git@github.com:ayentra/ayentra.git
   cd ayentra
   python -m venv .venv
   source .venv/bin/activate  # or .venv\Scripts\Activate.ps1 on Windows
   pip install -e ".[dev]"
   ```
2. Run the core verification test suite and benchmark execution time:
   ```bash
   pytest tests/test_ayentra_engine.py -v
   ayentra check examples/customer_pilot.py --seed 42
   ```
3. Audit `src/ayentra/engine.py` (Hypothesis strategy mapping) and `src/ayentra/concurrency.py` (thread schedule recording).

### 2.2 First-PR Day-3 Deliverable
- **Objective:** Add dynamic type strategy synthesis for `typing.Literal` and `uuid.UUID` parameters in `src/ayentra/engine.py`.
- **Execution Target:** When a function accepts `Literal["active", "pending", "closed"]`, the engine must generate a constrained `st.sampled_from(...)` strategy without developer configuration.
- **Verification Gate:** Write unit tests in `tests/test_ayentra_engine.py` proving that property generation evaluates all literal variants and shrinks failing cases deterministically. Merged by 5:00 PM on Day 3.

### 2.3 30-Day Measurable KPIs
- **Strategy Coverage:** Expand automated strategy synthesis to cover recursive dataclasses, `datetime.datetime`, and `decimal.Decimal` with precision limits.
- **Execution Speed:** Ensure property sweeps across 120 generated test cases complete in under 250 milliseconds per class.
- **Concurrency Exploration:** Implement bounded thread interleaving schedule exploration in `src/ayentra/concurrency.py` capable of detecting race conditions in `examples/scheduler_race.py` in under 800 milliseconds.
- **Zero Flakiness:** Eliminate all non-deterministic test failures in CI through seed derivation from commit SHAs.

### 2.4 60-Day Measurable KPIs
- **State Machine Synthesis:** Build automated rule-based state machine generation for stateful Python classes, detecting multi-step ledger conservation violations without manual test writing.
- **Shrinking Optimization:** Improve counterexample shrinking algorithms to isolate minimal 1-step or 2-step failing traces within 10 search iterations.
- **Enterprise Ledger Benchmarking:** Validate verification engine across 5 tier-1 fintech pilot codebases with zero false positives on standard double-entry bookkeeping models.

### 2.5 90-Day Measurable KPIs
- **Autonomous Architecture Ownership:** Full architectural authority over `engine.py` and `concurrency.py`. Able to onboard and review PRs from new engine contributors.
- **Formal Contract Expansion:** Design and implement class invariant inheritance and method post-condition assertions (`@postcondition`) with minimal runtime overhead.
- **Zero-Regression Record:** Maintain zero customer-reported verification crashes or unhandled engine exceptions across all pilot deployments.

---

## 3. Role 2: Founding AST Synthesis and Repair Engineer
- **Core Systems Owned:** `src/ayentra/ast_analyzer.py`, `src/ayentra/repair.py`, `src/ayentra/regression.py`.
- **Primary Mission:** Build automated AST static inspection, invariant candidate inference, and verified patch synthesis passes that eliminate developer remediation friction.

### 3.1 Day-1 Setup Protocol
1. Verify AST analyzer and repair test suites:
   ```bash
   pytest tests/test_pilot_workflow.py -v
   ayentra check examples/inventory_ledger.py
   ```
2. Inspect AST transformation passes in `src/ayentra/repair.py`:
   - `_apply_zero_division_guard_transform`
   - `_apply_class_conservation_transform`
   - `_apply_concurrency_lock_transform`
3. Audit `src/ayentra/ast_analyzer.py` for class attribute mutation tracking and candidate invariant suggestion logic.

### 3.2 First-PR Day-3 Deliverable
- **Objective:** Implement an AST transformation pass in `src/ayentra/repair.py` that synthesizes non-negative boundary guards (`if amount <= 0: return False`) for numerical balance mutation methods.
- **Execution Target:** When an invariant violation shows negative integer bypass, `ayentra patch` automatically produces a clean unified diff and verifies that 3 of 3 sandbox gates pass.
- **Verification Gate:** Tested on `examples/customer_pilot.py` and `examples/inventory_ledger.py`. Merged by 5:00 PM on Day 3.

### 3.3 30-Day Measurable KPIs
- **AST Mutation Precision:** Upgrade `ast_analyzer.py` to detect augmented assignments (`+=`, `-=`, `*=`, `/=`) and dictionary mutations (`self.balances[k] = v`) with 100% accuracy.
- **Patch Synthesis Reliability:** Achieve >85% first-pass verification rate for synthesized patches across arithmetic and boundary invariant violations in the regression test suite.
- **Source Code Formatting Preservation:** Ensure synthesized patches preserve existing line comments, indentation style, and docstrings using AST location fixing and formatting tools.

### 3.4 60-Day Measurable KPIs
- **Concurrency Mutex Synthesis:** Implement automatic threading lock injection (`threading.Lock` / `with self._lock:`) for classes identified with unsynchronized mutations in `concurrency.py`.
- **Sandbox Regression Isolation:** Integrate `src/ayentra/regression.py` with isolated sub-processes, ensuring candidate patches run against full test suites without leaking mutated module state.
- **Patch Verification Speed:** Ensure patch generation, AST rewriting, and regression sweep complete in under 1.2 seconds total.

### 3.5 90-Day Measurable KPIs
- **Autonomous Architecture Ownership:** Complete authority over `ast_analyzer.py` and `repair.py`. Authors the RFC for multi-file invariant propagation.
- **Complex Pattern Synthesis:** Extend repair transformations to handle NoneType guard assertions, list boundary bounds, and enum state transitions.
- **Customer Patch Adoption:** Over 75% of Ayentra-synthesized patches accepted and merged without modification by enterprise design partner teams.

---

## 4. Role 3: Founding Developer Experience and Studio Engineer
- **Core Systems Owned:** `src/ayentra/cli.py`, `src/ayentra/studio.py`, `src/ayentra/report.py`, `src/ayentra/site/`.
- **Primary Mission:** Build blisteringly fast, tactile developer interfaces across terminal CLI and local Studio web surfaces, adhering strictly to the Soft Neutral Light design system.

### 4.1 Day-1 Setup Protocol
1. Launch local Ayentra Studio and verify HTTP endpoints:
   ```bash
   ayentra studio --port 8765 examples/customer_pilot.py
   ```
2. Inspect local web assets in `src/ayentra/site/`:
   - `index.html` (semantic layout, ARIA attributes)
   - `styles.css` (Soft Neutral Light design tokens, CSS custom properties)
   - `app.js` (vanilla DOM updates, keyboard shortcuts, SSE stream handler)
3. Audit `src/ayentra/cli.py` command dispatching and Rich console rendering logic.

### 4.2 First-PR Day-3 Deliverable
- **Objective:** Add keyboard shortcuts (`J`/`K` for step navigation, `Alt+Enter` to apply patch) and visible focus rings in `src/ayentra/site/app.js` and `styles.css`.
- **Execution Target:** Ensure Studio inspector is fully usable without touching the mouse. All interactive elements must maintain WCAG AA compliant 2px focus outlines (`#2563EB`).
- **Verification Gate:** Tested on Chromium, Firefox, and Safari with zero JavaScript console warnings. Merged by 5:00 PM on Day 3.

### 4.3 30-Day Measurable KPIs
- **Sub-100ms CLI Startup:** Profile and refactor `src/ayentra/cli.py` to ensure cold boot time is strictly under 80 milliseconds using lazy module loading.
- **High-Density Studio UI:** Deliver redesigned 3-pane Studio inspector (Target Explorer, Counterexample Stepper, Patch Resolution Panel) adhering to Soft Neutral Light tokens (`#F6F5F2`, `#FCFCFA`, `#191B1F`).
- **WCAG AA Compliance:** 100% of text and control surfaces meet minimum 4.5:1 text contrast and 3:1 UI element contrast. Touch and click targets meet 36px to 44px standards.

### 4.4 60-Day Measurable KPIs
- **Live Terminal Stepper:** Implement an interactive terminal counterexample stepper using Rich and curses, allowing developers to step through failing execution states directly in their shell.
- **Real-Time Studio Hot-Reload:** Implement WebSocket or Server-Sent Events (SSE) file watching in `studio.py` that reruns verification under 300 milliseconds on file save.
- **Unified Diff Ergonomics:** Build one-click copy and terminal patch execution commands (`ayentra patch --apply`) with visual execution receipts.

### 4.5 90-Day Measurable KPIs
- **Autonomous Architecture Ownership:** Complete ownership of Ayentra CLI and Studio UI. Sets design and frontend craft standards across all developer-facing touchpoints.
- **Enterprise Design Partner NPS:** Achieve >70 Net Promoter Score on developer usability from design partner engineers during production pilots.
- **Zero-Friction Discovery:** Ensure zero-configuration setup works out of the box across 95% of tested open-source Python repositories.

---

## 5. Role 4: Founding Applied Security and CI Systems Engineer
- **Core Systems Owned:** Sandbox isolation, SARIF 2.1.0 reporting pipeline, GitHub Actions / GitLab CI integrations, and zero-egress runner security.
- **Primary Mission:** Build bulletproof CI integrations, automated pull request analysis gates, and hermetic sandbox execution environments that protect enterprise credentials.

### 5.1 Day-1 Setup Protocol
1. Run and audit the CI workflows and SARIF generators:
   ```bash
   ayentra init --ci
   pytest tests/test_cli_distribution.py -v
   pytest tests/test_pr_mock.py -v
   ```
2. Inspect SARIF 2.1.0 schema compliance and GitHub Code Scanning upload pipeline in `src/ayentra/report.py`.
3. Audit sandbox execution boundaries in `src/ayentra/regression.py` for environment variable leaks.

### 5.2 First-PR Day-3 Deliverable
- **Objective:** Add environment variable sanitization and execution isolation to `src/ayentra/regression.py`.
- **Execution Target:** When running candidate patches in the verification sandbox, the runner must strip sensitive tokens (`GITHUB_TOKEN`, `AWS_*`, `SSH_*`) before spawning child Python processes.
- **Verification Gate:** Write an adversarial unit test in `tests/test_pilot_workflow.py` attempting to read parent environment secrets, proving the child sandbox is isolated. Merged by 5:00 PM on Day 3.

### 5.3 30-Day Measurable KPIs
- **Sub-Second PR Diff Scanning:** Build and release `ayentra check --diff <patch_file>` capable of parsing unified git diffs and verifying modified targets in under 400 milliseconds.
- **Strict SARIF 2.1.0 Compliance:** Ensure 100% of emitted SARIF reports validate cleanly against official OASIS schemas with accurate physical location regions and inline autofix patches.
- **Hermetic Sandbox Execution:** Enforce strict CPU time and memory caps on subprocess execution to prevent runaway property tests from locking CI runners.

### 5.4 60-Day Measurable KPIs
- **Zero-Egress CI Runners:** Architect and package containerized, network-isolated GitHub Action runners that execute property verification without outbound internet access.
- **Monorepo Caching Architecture:** Implement content-addressable caching for invariant verification results (`.ayentra/cache/`), cutting repeat CI runtimes to under 80 milliseconds.
- **Multi-CI Platform Support:** Deliver verified, battle-tested integrations for GitLab CI, CircleCI, and Buildkite alongside GitHub Actions.

### 5.5 90-Day Measurable KPIs
- **Autonomous Architecture Ownership:** Full authority over CI/CD pipelines, security sandboxing, and enterprise deployment infrastructure.
- **Enterprise Security Clearance:** Pass rigorous enterprise security and compliance reviews (SOC 2, ISO 27001 readiness) for Fortune 500 fintech design partners.
- **Zero CI Outage Escapes:** Maintain 99.99% reliability across all CI verification gates with zero blocking pipeline false positives.

---

## 6. Objective 30/60/90-Day Retention and Calibration Rubric

Performance reviews at Ayentra are conducted on Day 30, Day 60, and Day 90. Evaluations use objective code evidence, latency receipts, and peer feedback.

### 6.1 Calibration Scoring Levels

| Outcome Level | Action Plan | Criteria and Observable Evidence |
| :--- | :--- | :--- |
| **Exceeds Bar (Top 10%)** | Accelerated equity vesting, increased ownership scope, immediate technical lead assignment. | Consistently delivers PRs ahead of timeline. Proactively identifies and fixes architectural risks across other systems. Code is minimal, elegant, and self-documenting. Sub-second execution budgets respected without exception. |
| **Meets Bar (Target)** | Confirmed retention, continued standard sprint cadence. | Delivers on all role-specific 30/60/90-day KPIs. Writes verified, well-tested code. Shows strong edge-case paranoia and handles critical bugs promptly. Operates autonomously with minimal supervision. |
| **Below Bar (Action Needed)** | Immediate 14-day performance correction plan or transition out. | Misses key PR deliverables. Writes unverified or brittle code with regression escapes. Shows low urgency or resists staff-level craft standards. Relies on excuses or buzzwords instead of code receipts. |

### 6.2 30-Day Evaluation Milestone
- **Core Question:** "Can this engineer independently design, build, and ship production-ready features in their subsystem with zero hand-holding?"
- **Required Evidence:**
  - Day-3 PR merged on schedule.
  - At least 8 production pull requests merged with verified test coverage.
  - Zero regression escapes in production.
  - Active participation in architecture RFCs.

### 6.3 60-Day Evaluation Milestone
- **Core Question:** "Is this engineer raising the bar for the team in terms of code quality, speed, and edge-case paranoia?"
- **Required Evidence:**
  - Met or exceeded all 60-day KPIs.
  - Reduced latency or memory footprint in their primary module.
  - Direct contribution to solving an enterprise design partner blocker.
  - Mentors and pair-programs effectively with peers.

### 6.4 90-Day Evaluation Milestone
- **Core Question:** "Is this engineer an indispensable founding pillar who will help recruit and scale the next 20 engineers?"
- **Required Evidence:**
  - Complete autonomous ownership of their systems.
  - Proven track record of shipping zero-defect software under tight deadlines.
  - Trusted technical advisor to founders and customers.
  - Unanimous "Strong Retain" decision from the founding team.

---

## 7. Weekly 1:1 Cadence and Calibration Review Form

Founders and technical leads conduct weekly 30-minute 1:1 check-ins focused on code output, blockers, and craft calibration.

```markdown
# Founding Engineer Milestone Review Form
Review Period: [Day 30 / Day 60 / Day 90]
Engineer Name: [Full Name]
Role: [Role Title]
Manager / Founder: [Full Name]
Date: [YYYY-MM-DD]

### 1. Concrete Code Deliverables Shipped
- List major PRs merged during this period:
  1. PR #[Number]: [Brief factual description with test results]
  2. PR #[Number]: [Brief factual description with test results]

### 2. Observable Metrics & Execution Receipts
- Execution speed / latency achieved: [e.g. 180ms sweep on 120 cases]
- Test coverage / new invariant tests added: [e.g. 42 new unit tests]
- Regression escapes: [Must be 0]

### 3. Edge-Case Paranoia & Craft Assessment
- Concrete examples where engineer caught subtle bugs proactively:
  - [Factual incident 1]
  - [Factual incident 2]

### 4. Milestone Decision
- [ ] Exceeds Bar (Strong Retain / Acceleration)
- [ ] Meets Bar (Retain)
- [ ] Below Bar (14-Day Performance Plan / Exit)

**Founder Signature:** ___________________________  **Date:** ______________
```

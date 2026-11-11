# Ayentra Founding Team Hiring Kit and Technical Interview Scorecards
Version: 1.0.0
Author: Hiring Partner (Ayentra)
Target: Ayentra Founding Engineering Loop, Technical Interviewers, and Founders
Standard: Ayentra Human Taste and Craft Playbook

---

## 1. Founding Engineering Interview Principles and Craft Protocol

Ayentra builds software that verifies explicit behavioral contracts in Python codebases, isolates reproducible counterexamples through property-based shrinking, and validates candidate fixes in an isolated sandbox before merge. 

We evaluate candidates on observable engineering evidence, working code samples, and precise technical communication. We do not use whiteboard trivia, algorithmic puzzle inversions, or pedigree proxies.

### 1.1 Core Assessment Rules
1. **Direct Code Evidence:** Base evaluations solely on code written, bugs identified, tests executed, and design tradeoffs defended during the interview.
2. **Observable Behaviors vs Impressions:** Record observable facts instead of subjective impressions. Write "Candidate identified race condition in hold_in_escrow on line 18 and wrote a multi-threaded test that reproduced it in 4 runs." Do not write "Candidate seemed smart and confident."
3. **Edge-Case Paranoia:** Great founding engineers look for arithmetic overflow, state pollution, mutation of shared instances, unhandled None types, and concurrency deadlocks without prompting.
4. **The Three-Second Rule and Developer Empathy:** Every tool we build must respect developer time. CLI operations must start under 100ms and complete under 2 seconds. Candidate solutions must reflect this bias for speed and minimal cognitive overhead.
5. **No AI Filler or Fluff:** We speak and write in direct staff-engineer terms. Explanations must focus on exact failure modes, line numbers, and concrete tradeoffs.

### 1.2 The Standard 1 to 5 Scoring Scale
Every technical competency is scored using these fixed anchors:

- **1 = Unacceptable / Critical Failure:** Candidate fails basic technical prerequisites. Writes non-functional or unsafe code. Cannot explain fundamental language or system mechanics. Ignores major failure modes even after direct hints.
- **2 = Below Standard / Incomplete:** Candidate produces partial solutions with unhandled edge cases. Struggles with core domain concepts. Requires substantial guidance to identify obvious bugs or complete basic implementations.
- **3 = Meets Bar / Competent:** Candidate delivers a fully working solution matching requirements. Handles standard edge cases, writes clean tests, and communicates design choices clearly. Capable of shipping production code independently.
- **4 = Exceeds Bar / Strong Staff-Level:** Candidate produces production-grade implementations with minimal complexity. Identifies subtle concurrency, memory, or compiler edge cases proactively. Demonstrates exceptional taste in API design, performance, and developer ergonomics.
- **5 = Exceptional / World-Class Founding Contributor:** Candidate delivers an elegant, minimal solution with remarkable speed. Identifies system-wide implications beyond the immediate prompt. Writes self-documenting code with zero friction. Immediately sets the technical standard for the company.

---

## 2. Role 1: Founding Verification and AST Compiler Engineer

### 2.1 Role Profile and Requirements
The Founding Verification and AST Compiler Engineer owns Ayentra's core static analysis, AST mutation, and dynamic property verification engines (`src/ayentra/ast_analyzer.py`, `src/ayentra/engine.py`, `src/ayentra/concurrency.py`, and `src/ayentra/repair.py`).

**Key Responsibilities:**
- Develop and optimize AST analysis visitors to detect missing invariants, attribute mutations, and unhandled branch conditions.
- Design automated property-based test generation using Hypothesis strategies derived dynamically from type signatures and domain constraints.
- Build AST-based program synthesis passes to generate verified patches for invariant violations.
- Maintain deterministic, sub-second execution speeds across thousands of generated test cases.

**Hard Prerequisites:**
- Production expertise in Python internals: the `ast` module, NodeVisitor, NodeTransformer, bytecode inspection, and execution frames.
- Practical experience with property-based testing engines (Hypothesis, QuickCheck), state shrinking algorithms, and coverage-guided generation.
- Strong grounding in formal contracts: pre-conditions, post-conditions, class invariants, and loop variants.
- Understanding of multi-threaded concurrency models, memory barriers, thread scheduling, and race condition reproduction.

### 2.2 Hands-On Technical Exercise: AST Invariant Synthesis and Counterexample Shrinker
- **Time Allocated:** 90 minutes.
- **Environment:** Local Python 3.11+ environment with `hypothesis` and `pytest` installed.
- **Grounded Codebase:** `src/ayentra/ast_analyzer.py` and `src/ayentra/engine.py`.

#### Problem Prompt for Candidate
You are provided with an unannotated Python class representing an in-memory payment ledger:

```python
# target_ledger.py
class PaymentLedger:
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
```

The code contains a critical invariant vulnerability: negative integer inputs allow an attacker to bypass checks, siphon funds into escrow, and violate the fundamental conservation law:
`self.balance >= 0 and self.escrow >= 0 and self.balance + self.escrow == self.total`

**Candidate Tasks:**
1. Write an AST analyzer (`analyze_and_extract_mutations(source_code: str)`) that walks the class AST, identifies all methods mutating `self.balance` and `self.escrow`, and infers candidate conservation invariants.
2. Build an automated test generator using Hypothesis strategies that instantiates `PaymentLedger`, executes random sequences of `hold` and `release` with integer amounts (including negative values), and checks the conservation invariant after every method call.
3. When an invariant violation occurs, implement a custom shrinking routine or configure Hypothesis to shrink the failing execution sequence to the minimal 1-step or 2-step counterexample trace.
4. Synthesize an AST transformation using `ast.NodeTransformer` that automatically injects non-negative guard clauses (`if amount <= 0: return False`) at the entry of mutating methods, and re-verify the transformed code against the property test harness.

#### Evaluation Benchmarks and Expected Outcomes
- **AST Correctness:** The AST transformer must preserve line numbers, docstrings, and handle nested statement blocks correctly.
- **Shrinking Precision:** The counterexample must produce the exact failing input (such as `hold(amount=-1)`) rather than a bloated 50-step trace.
- **Execution Speed:** The full verification sweep (100 generated cases) plus AST rewriting must execute in under 400 milliseconds.

### 2.3 Behavioral and Architectural Probing Questions
1. **AST Node Transformation vs Source Patching:** "In `src/ayentra/repair.py`, we must produce unified diffs for developers to inspect. How do you transform an AST while preserving original formatting, comments, and whitespace without introducing subtle syntax bugs?"
   - *Good response:* Mentions tools like `libcst` or `ast.unparse` with AST token mapping; discusses round-trip formatters (such as `black` or `ruff`) and how to isolate diffs to only modified nodes.
   - *Red flag:* Proposes regular expression string replacement on source code instead of structured AST manipulation.

2. **Managing State Explosion in Property Testing:** "When testing classes with 10 mutating methods and complex internal state graphs, Hypothesis can get trapped in unshrinkable states or hit recursion limits. How do you structure your state machines to guarantee fast convergence and minimal counterexamples?"
   - *Good response:* Discusses state-machine testing patterns (`RuleBasedStateMachine`), explicit precondition filtering (`precondition()`), deterministic seed generation, and bounding state depth.
   - *Red flag:* Suggests increasing max_examples to 10,000 without constraining parameter domains or state space.

3. **Concurrency and Interleaving Verification:** "Static AST analysis can check if a method acquires a threading lock, but cannot prove freedom from race conditions. How does dynamic interleaving exploration work, and where does it fail?"
   - *Good response:* Details trace-based schedule recording, thread interruption points at bytecode boundaries, and acknowledges the exponential cost of thread schedules requiring bounded search depths.
   - *Red flag:* Believes static AST checking of `with self._lock:` guarantees absence of deadlocks or races.

### 2.4 Strict 1 to 5 Scoring Rubric for Role 1

| Evaluation Dimension | 1 - Unacceptable | 2 - Below Standard | 3 - Meets Bar | 4 - Exceeds Bar | 5 - Exceptional |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **AST & Compiler Mechanics** | Cannot construct or walk an AST using standard library `ast`. | Constructs basic AST visitors but fails to extract target variable assignments or mutations. | Implements clean `NodeVisitor` and `NodeTransformer` passes; extracts mutated attributes accurately. | Preserves source spans, handles nested scopes and class inheritance; implements clean node replacements. | Writes elegant, high-speed AST rewriting passes; handles complex control flows, context managers, and edge-case syntax. |
| **Property-Based Testing** | Does not understand property testing; writes hardcoded unit tests. | Uses Hypothesis but struggles to define strategies or state transitions. | Builds stateful property tests with valid Hypothesis strategies; captures invariant failures reliably. | Configures targeted strategies with domain bounds; prevents flaky examples and handles shrinking cleanly. | Designs minimal state-machine verification harnesses; implements custom shrinkers for multi-step execution traces. |
| **Edge-Case Paranoia** | Misses negative numbers, NoneType, and zero division. | Finds negative inputs only when prompted; overlooks conservation law math. | Checks boundary conditions (zero, negative, maxint) and state invariants systematically. | Identifies aliasing risks, re-entrancy, and unexpected float conversions proactively. | Exhaustively tests arithmetic boundaries, type coercion, concurrency hazards, and internal state pollution. |
| **Execution Performance** | Test harness takes >5 seconds or hangs indefinitely. | Harness takes 2 to 5 seconds; unconstrained test generation. | Completes verification sweep within 1 to 2 seconds. | Completes verification sweep under 500ms through disciplined strategy sizing. | Completes verification and AST synthesis under 250ms with zero memory bloat. |
| **Staff-Level Communication** | Uses vague generalizations; cannot explain code logic. | Explains code with difficulty; relies on corporate buzzwords. | Explains AST and verification logic directly and clearly. | Articulates precise tradeoffs between static AST checking and runtime verification. | Explains complex compiler and formal verification concepts with total clarity and zero fluff. |

---

## 3. Role 2: Founding Developer Experience and CI Systems Engineer

### 3.1 Role Profile and Requirements
The Founding Developer Experience and CI Systems Engineer owns Ayentra's CLI tools, GitHub Actions workflows, PR analysis bots, SARIF 2.1.0 reporting pipelines, and isolated sandbox execution environments (`src/ayentra/cli.py`, `src/ayentra/regression.py`, and `src/ayentra/dogfood.py`).

**Key Responsibilities:**
- Engineer a fast, zero-config CLI (`ayentra check`, `ayentra init --ci`, `ayentra pr-review`) adhering to the 3-second rule.
- Build production GitHub Actions and GitLab CI integrations that run targeted property verification on pull request diffs.
- Generate valid SARIF 2.1.0 telemetry for GitHub Code Scanning with inline fix suggestions.
- Implement isolated, hermetic execution sandboxes for running property tests and applying candidate patches safely.

**Hard Prerequisites:**
- Deep experience engineering developer CLI tools in Python using Rich, Click, or Argparse with sub-100ms startup times.
- Extensive production knowledge of GitHub Actions internals, workflow triggers, PR comment bots, and GitHub API rate limits.
- Complete mastery of the SARIF 2.1.0 specification and GitHub Security Code Scanning integration.
- Expertise in subprocess management, virtualenv isolation, tempfile hygiene, and cross-platform terminal control (POSIX and Windows).

### 3.2 Hands-On Technical Exercise: Sub-Second PR Diff Analyzer and SARIF 2.1.0 Pipeline
- **Time Allocated:** 90 minutes.
- **Environment:** Local Python 3.11+ environment with `rich`, `pytest`, and `git`.
- **Grounded Codebase:** `src/ayentra/cli.py` and `examples/fixtures/pr_diff_balance_leak.patch`.

#### Problem Prompt for Candidate
In continuous integration pipelines, running full test suites across an entire repository on every commit causes developer friction and slow feedback loops. 

You must build a standalone Python CLI tool `ayentra-pr` that accepts a unified git diff patch file (such as `pr_diff_balance_leak.patch`), selectively targets only the modified Python classes and methods, executes invariant verification, and formats the result as both a concise terminal status panel and a SARIF 2.1.0 JSON report.

```patch
# pr_diff_balance_leak.patch
--- a/models/account.py
+++ b/models/account.py
@@ -14,6 +14,8 @@ class BankAccount:
     def withdraw(self, amount: int) -> bool:
-        if 0 < amount <= self.balance:
+        if amount <= self.balance:
             self.balance -= amount
             return True
         return False
```

**Candidate Tasks:**
1. Parse the unified diff to extract modified file paths, target class names, and affected line ranges.
2. Filter out non-Python files and unmodified classes automatically without loading external dependencies.
3. Run verification against the modified target, verifying the invariant `self.balance >= 0`.
4. Render a clean terminal output using Rich: display the file name, evaluated invariant, failing input (`amount=-50`), and the unified diff of the suggested fix.
5. Export a compliant SARIF 2.1.0 report (`ayentra-results.sarif`) containing:
   - `runs[0].tool.driver.name = "Ayentra Engine"`
   - `runs[0].results[0].ruleId = "AYENTRA-INV-001"`
   - `runs[0].results[0].level = "error"`
   - `runs[0].results[0].locations` pointing to the exact line number of `withdraw`.
   - `runs[0].results[0].fixes` containing the proposed replacement diff.
6. Meet strict execution constraints: the entire CLI execution must finish in under 500 milliseconds and exit with code 1 on invariant failure, code 0 on clean pass.

#### Evaluation Benchmarks and Expected Outcomes
- **Diff Parsing Precision:** Accurately extracts hunk line numbers and handles multi-file diffs containing non-Python files.
- **SARIF Standard Compliance:** The output JSON must pass strict SARIF 2.1.0 schema validation.
- **Microcopy Discipline:** Terminal output must avoid all marketing adjectives and follow the Human Taste Playbook ("Checking models/account.py: 1 invariant evaluated").
- **Speed:** Execution completes in under 500ms on local test files.

### 3.3 Behavioral and Systems Design Questions
1. **The 3-Second Rule and Monorepo Scalability:** "If an enterprise repository has 40,000 files and a PR modifies 2 files, how do you discover project configuration and verify contracts without scanning the whole filesystem?"
   - *Good response:* Uses upward directory traversal to locate `ayentra.toml` from the modified file's path; parses `git diff --name-only origin/main...HEAD` directly; avoids heavy global AST scans.
   - *Red flag:* Proposes running `os.walk` from repository root on every run.

2. **Flakiness in CI Property Testing:** "Property-based tests with randomized inputs can occasionally fail on a specific seed after 50 green runs. How do you prevent developer distrust in CI?"
   - *Good response:* Explains fixed pseudorandom seed derivation per commit SHA; persisting failing counterexamples into a local regression cache (`.ayentra/reproducers/`); replaying known failures before running randomized sweeps.
   - *Red flag:* Suggests lowering test example counts or ignoring failures that only happen once.

3. **Safe Sandbox Execution of Untrusted Pull Requests:** "When Ayentra CI runs on public fork pull requests, how do you isolate test execution to prevent malicious code from exfiltrating CI environment tokens?"
   - *Good response:* Mentions running verification in unprivileged sub-processes, stripping sensitive environment variables (`GITHUB_TOKEN`, cloud credentials) before spawning runners, and executing in ephemeral Docker containers or gVisor sandboxes.
   - *Red flag:* Executes untrusted candidate PR code directly in the main CI process with access to all secrets.

### 3.4 Strict 1 to 5 Scoring Rubric for Role 2

| Evaluation Dimension | 1 - Unacceptable | 2 - Below Standard | 3 - Meets Bar | 4 - Exceeds Bar | 5 - Exceptional |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **CLI Architecture & Speed** | CLI takes >3s to boot; heavy imports at module root. | CLI runs between 1 to 3 seconds; lacks clear argument handling. | Boots under 200ms; clean argument parsing; handles signals and exit codes. | Boots under 80ms; uses lazy imports; handles pipe redirects and CI flags cleanly. | Boots under 30ms; instant response; pristine keyboard and terminal control. |
| **CI & SARIF Compliance** | Output JSON is invalid or does not match SARIF schema. | Produces basic JSON but omits physical locations or fix objects. | Produces valid SARIF 2.1.0 JSON matching GitHub Code Scanning requirements. | Includes precise artifact locations, rule descriptions, and patch replacements. | Flawless SARIF 2.1.0 export; supports inline code annotations and multithreaded CI runs. |
| **Terminal UI & Microcopy** | Prints messy stack traces or uses corporate filler text. | Terminal UI is cluttered; uses colored text without visual hierarchy. | Clean Rich output with factual status messages; verbs first. | Disciplined output with exact line numbers, counterexamples, and patch diffs. | Exceptional terminal aesthetic; crisp alignment, zero noise, sub-second execution receipt. |
| **Sandbox & Isolation** | Leaves leftover temp files; crashes on unwriteable directories. | Basic tempdir usage but leaks files on uncaught exceptions. | Reliable cleanup with context managers; isolates execution environment. | Handles permissions, timeouts, and process terminations cleanly. | Implements fully hermetic sandbox execution with memory and CPU bounds. |
| **Developer Empathy** | Blames developer for misconfiguration; cryptic errors. | Error messages are generic and require consulting documentation. | Actionable error messages with file paths and fix suggestions. | Anticipates developer mistakes; suggests flags and auto-discovers configuration. | Zero-configuration by default; feels invisible and straightforward to run in any repository. |

---

## 4. Role 3: Founding GTM / Solutions Engineer (Fintech and Payments)

### 4.1 Role Profile and Requirements
The Founding GTM / Solutions Engineer bridges Ayentra's engineering engine with enterprise design partners in fintech, banking, payments, and infrastructure.

**Key Responsibilities:**
- Lead technical discovery and 14-day production pilot deployments with engineering leadership (VPs of Engineering, Staff Architects, Heads of QA).
- Inspect prospective customers' Python codebases, identify invariant gaps in ledger accounting and transaction state machines, and demonstrate Ayentra's verification capabilities.
- Translate formal verification receipts into quantifiable business risk and ROI for executive decision-makers.
- Guide enterprise customers through zero-config CI onboarding without disrupting their active sprint workflows.

**Hard Prerequisites:**
- Working technical background in software engineering: ability to read, run, and debug production Python code.
- Domain expertise in financial engineering: double-entry bookkeeping, ledger conservation laws, settlement lifecycles, and transaction idempotency.
- Proven experience running technical proofs-of-concept (POCs) for developer tools or security infrastructure.
- High-integrity communication style: speaks with technical rigor, avoids sales hype, and builds trust with staff-level engineers.

### 4.2 Hands-On Technical Exercise: Pilot Diagnosis, Verification Receipt, and 14-Day Pilot Plan
- **Time Allocated:** 90 minutes.
- **Environment:** Local terminal with Python 3.11+, Ayentra CLI, and text editor.
- **Grounded Codebase:** `examples/customer_pilot.py` and `docs/design_partner_kit.md`.

#### Problem Prompt for Candidate
A high-growth payments processor handles 40 million dollars in daily settlement volume. During peak transaction bursts, their reconciliation job occasionally reports negative available balances and unallocated funds. Their VP of Engineering believes their existing test suite (95% unit test coverage) is sufficient and is skeptical of third-party verification tools.

You are provided with `customer_pilot.py`:

```python
# customer_pilot.py
from dataclasses import dataclass, field
from ayentra.contracts import domain, invariant

@invariant(
    "self.available >= 0 and self.escrow >= 0 and self.available + self.escrow == self.total_funds",
    description="Ledger conservation law: available and escrow funds must be non-negative and sum to total funds",
)
@dataclass
class EnterprisePaymentLedger:
    total_funds: int = 1000
    available: int = 1000
    escrow: int = 0
    settled_tx_ids: set[str] = field(default_factory=set)

    @domain(amount=(-100, 2000), tx_id=('tx_1', 'tx_2', 'tx_3'))
    def hold_in_escrow(self, amount: int, tx_id: str) -> bool:
        if tx_id in self.settled_tx_ids:
            return True
        if amount <= self.available:
            self.available -= amount
            self.escrow += amount
            return True
        return False
```

**Candidate Tasks:**
1. Run Ayentra verification against `customer_pilot.py` from the terminal. Identify the exact counterexample that breaks the ledger conservation law.
2. Produce an auditable verification receipt (`ayentra-receipt.json`) detailing the target file, evaluated invariants, seed value, counterexample inputs, and duration.
3. Write a 1-page staff-engineer technical postmortem addressed to the customer's VP of Engineering:
   - Explain the root cause of the bug in plain engineering terms.
   - Quantify the financial risk if this code runs in production with negative withdrawal amounts.
   - Present the exact unified diff patch synthesized by Ayentra to resolve the violation.
4. Outline a 14-day production pilot plan showing how Ayentra will be introduced into their GitHub CI pipeline without blocking deployments or generating false-positive alert fatigue.

#### Evaluation Benchmarks and Expected Outcomes
- **Technical Accuracy:** Accurately isolates the bug (negative `amount` parameter bypasses `amount <= self.available`, inflates `escrow`, and causes balance corruption).
- **Executive Communication:** Postmortem must be direct, respectful, and free of sales buzzwords. It must clearly explain why unit tests failed to catch the bug (unit tests used positive test fixtures).
- **Pilot Architecture:** Proposes a phased CI integration (non-blocking observation mode for week 1, blocking gate on modified files for week 2).

### 4.3 Behavioral and Customer Discovery Probing Questions
1. **Handling Developer Skepticism:** "The lead architect says: 'We already have 95% test coverage and our senior engineers do strict code reviews. Why should we slow down our CI pipeline with Ayentra?' How do you respond?"
   - *Good response:* Acknowledges the value of high test coverage; explains that unit tests verify expected known paths while property-based verification explores unexpected combinations and edge cases; demonstrates how Ayentra runs in under 2 seconds on changed files only.
   - *Red flag:* Disparages their current engineering practices or claims unit tests are useless.

2. **Managing False Positives During a Pilot:** "During day 3 of an enterprise pilot, Ayentra flags an invariant failure on an internal cache class. The customer insists the code is correct and considers canceling the pilot. What do you do?"
   - *Good response:* Reproduces the counterexample locally with the customer; examines whether the invariant expression was misconfigured or if the counterexample represents a true state violation; refines domain bounds or contract definitions transparently.
   - *Red flag:* Argues with the customer or blames their code without investigating the contract definition.

3. **Commercial Conversion Criteria:** "How do you define clear success criteria before the pilot begins so the enterprise does not stall at the end of the 14 days?"
   - *Good response:* Establishes 3 explicit written criteria before kickoff: (1) Zero false positive blocks, (2) Under 2 seconds CI execution overhead, and (3) At least one verified contract on a critical financial state machine.
   - *Red flag:* Starts pilots without defined metrics, hoping the customer will be impressed and ask to buy.

### 4.4 Strict 1 to 5 Scoring Rubric for Role 3

| Evaluation Dimension | 1 - Unacceptable | 2 - Below Standard | 3 - Meets Bar | 4 - Exceeds Bar | 5 - Exceptional |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Fintech Systems Knowledge** | Does not understand ledgers, escrow, or double-entry rules. | Basic knowledge but cannot articulate why conservation laws matter. | Explains double-entry conservation, balance invariants, and settlement states clearly. | Deep domain mastery; explains race hazards, ACH reconciliation, and idempotency nuances. | Authoritative fintech expertise; instantly diagnoses complex transaction and ledger failure modes. |
| **Technical Diagnosis** | Cannot run the CLI or reproduce the failure. | Runs CLI with guidance; struggles to interpret the counterexample. | Reproduces the counterexample independently; explains the exact failure trace. | Identifies both the arithmetic bypass and downstream state corruption implications. | Pinpoints root cause, synthesizes verified patch, and audits neighboring methods for similar flaws. |
| **Engineering Writing Craft** | Uses marketing fluff; writes long, confusing summaries. | Clinical report but lacks clear business risk quantification. | Clear, factual postmortem; explains bug, financial risk, and patch diff. | Direct, staff-level tone; zero buzzwords; builds immediate technical trust. | Pristine executive communication; balances deep technical precision with clear financial risk framing. |
| **Pilot Architecture** | Suggests blocking all CI immediately without staging. | Suggests a pilot plan but lacks concrete timelines or milestone checks. | Solid 14-day phased plan with clear gating and evaluation checkpoints. | Pragmatic pilot design; includes non-blocking observation, custom rules, and telemetry. | Flawless rollout playbook; anticipates enterprise security reviews, CI flakiness, and team onboarding. |
| **Objection Handling** | Becomes defensive when questioned; pushes sales talk. | Struggles to address technical skepticism directly. | Answers technical questions calmly with concrete examples and data. | Reframes objections constructively; demonstrates respect for customer engineering time. | Turns skeptical staff engineers into passionate internal champions through factual demonstration. |

---

## 5. Role 4: Founding Product Designer (DevTools)

### 5.1 Role Profile and Requirements
The Founding Product Designer owns Ayentra's developer interfaces, including the local Studio inspector (`src/ayentra/studio.py` and `src/ayentra/site/`), terminal visual hierarchy, and web reporting surfaces.

**Key Responsibilities:**
- Design developer tools adhering strictly to Ayentra's Soft Neutral Light design philosophy.
- Create fast, high-density interfaces for inspecting complex invariant violations, execution step traces, and unified diff patches.
- Maintain strict keyboard-first navigation patterns across all interactive surfaces.
- Enforce uncompromising accessibility standards (WCAG AA contrast ratios, minimum 36px touch targets, visible focus indicators).

**Hard Prerequisites:**
- Proven portfolio of developer tools, IDE interfaces, data-dense dashboards, or engineering infrastructure applications.
- Deep visual craft: restrained typography, subtle border treatments, disciplined whitespace, and zero decorative noise.
- Complete understanding of keyboard navigation, ARIA landmarks, focus management, and accessible color systems.
- Working competence in modern frontend implementation: HTML5, CSS custom properties, and vanilla JavaScript or lightweight UI frameworks.

### 5.2 Hands-On Design and Frontend Exercise: Studio Counterexample Stepper and Patch Verification Panel
- **Time Allocated:** 90 minutes.
- **Environment:** Code editor, browser, and Figma or direct HTML/CSS prototype.
- **Grounded Codebase:** `src/ayentra/site/index.html`, `src/ayentra/site/styles.css`, and `src/ayentra/site/app.js`.

#### Problem Prompt for Candidate
In Ayentra Studio (`ayentra studio`), developers inspect code targets, evaluate invariants locally, and review candidate fixes. 

The current violation inspection panel must be redesigned to provide a clean, high-density review experience for a complex invariant failure.

**Candidate Tasks:**
1. Design a 3-pane split layout for the violation inspector:
   - **Pane A (Target Explorer):** Compact list of inspected files, evaluated classes, invariant status badges (pass/fail count), and total execution time.
   - **Pane B (Counterexample Stepper):** Chronological step-by-step trace showing the initial state, the injected inputs (e.g. `amount = -50`), the failing assertion, and the state delta. Must support keyboard navigation (J/K keys to step through history).
   - **Pane C (Patch Verification and Action Panel):** Unified diff showing the proposed fix, sandbox verification receipts (e.g. "3 of 3 gates passed"), and keyboard shortcuts (Alt+Enter to apply patch, R to rerun verification).
2. Apply Ayentra's Soft Neutral Light design tokens strictly:
   - App Background: `#F6F5F2`
   - Surface / Cards: `#FCFCFA`
   - Panel Background: `#FFFFFF`
   - Monospace Code Background: `#1A1D20`
   - Border Subtle: `#EBE8E0`
   - Border Default: `#DFDBD0`
   - Text Primary: `#191B1F` (meets 15.8:1 contrast ratio)
   - Text Secondary: `#525761` (meets 5.9:1 contrast ratio)
   - Pass Pill: `#166534` on `#DCFCE7`
   - Fail Pill: `#991B1B` on `#FEE2E2`
   - Focus Ring: `#2563EB` (2px solid outline)
3. Provide production-ready HTML structure and CSS token implementations for the Counterexample Stepper component.
4. Specify accessibility behaviors: focus-visible outlines, ARIA roles (`role="region"`, `role="listbox"`, `aria-selected`), and screen reader announcements.

#### Evaluation Benchmarks and Expected Outcomes
- **Visual Restraint:** The design must eliminate visual clutter, cartoon badges, and unnecessary gradients.
- **Density and Readability:** The interface must handle 10-step execution traces and 40-line code diffs without broken scrolling or layout shifts.
- **Accessibility:** All text and interactive controls must pass WCAG AA contrast standards. Interactive elements must maintain minimum 36px hit targets.
- **Keyboard Ergonomics:** Every primary action must have an intuitive shortcut clearly indicated in the microcopy.

### 5.3 Behavioral and Design Craft Probing Questions
1. **Designing for Low-Patience Engineers:** "Developers are notoriously cynical of web UI wrappers around CLI tools. How do you design Studio so that a terminal-first engineer genuinely prefers using it over raw terminal output?"
   - *Good response:* Focuses on instant local startup (under 100ms), zero login prompts, keyboard shortcuts matching terminal conventions, instant diff copy, and side-by-side state inspection that the terminal cannot render cleanly.
   - *Red flag:* Proposes adding gamification, onboarding tooltips, or cloud social sharing features.

2. **Visual Restraint and Saying No to Clutter:** "A founder suggests adding colorful severity badges, animated progress rings, and a radar chart of codebase health to the Studio homepage. How do you evaluate and respond to this request?"
   - *Good response:* Evaluates whether the requested element helps the developer fix an invariant violation faster; demonstrates how decorative charts create visual noise and distract from actionable errors; proposes clean numeric receipts instead.
   - *Red flag:* Agrees to add the decorative elements without questioning their utility.

3. **Accessibility in Dark and Light Code Surfaces:** "Ayentra uses a Soft Neutral Light theme for the interface but a dark theme for monospace code blocks (`#1A1D20`). How do you maintain visual harmony and WCAG compliance across contrasting adjacent surfaces?"
   - *Good response:* Establishes disciplined border transitions (`#DFDBD0`), uses consistent syntax highlighting tokens that maintain at least 4.5:1 contrast against dark backgrounds, and avoids stark unsoftened black-and-white borders.
   - *Red flag:* Treats code blocks as standard text without verifying token contrast.

### 5.4 Strict 1 to 5 Scoring Rubric for Role 4

| Evaluation Dimension | 1 - Unacceptable | 2 - Below Standard | 3 - Meets Bar | 4 - Exceeds Bar | 5 - Exceptional |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Information Architecture** | Disorganized layout; diffs and traces are cramped and unreadable. | Cluttered layout; requires excessive scrolling; confusing hierarchy. | Clear 3-pane structure; intuitive placement of stepper and diff. | Optimal density; information flows logically from failure to fix. | Masterful layout; intuitive and frictionless; handles complex nested state traces with absolute clarity. |
| **Visual Craft & Tokens** | Uses arbitrary colors; ignores Soft Neutral Light palette. | Follows palette loosely; inconsistent borders and spacing. | Strictly applies design tokens; clean spacing and crisp typography. | Subtle elevations, disciplined borders, and elegant monospace hierarchy. | Flawless craft; feels on par with Stripe and Linear; zero visual clutter or AI slop. |
| **Keyboard Ergonomics** | Mouse-only interface; no keyboard navigation. | Basic Tab navigation; lacks hotkeys for stepping or applying patches. | Standard shortcuts supported (J/K, Enter); visible focus states. | Full keyboard shortcut coverage; intuitive modal and focus traps. | Complete keyboard fluidity; power users can inspect and patch bugs without touching the mouse. |
| **Accessibility & Standards** | Fails contrast checks; missing focus rings; broken ARIA. | Some controls fail 4.5:1 contrast; inconsistent hit targets. | Passes WCAG AA contrast; visible focus outlines; proper ARIA tags. | Full WCAG AA compliance; polished :focus-visible states; 40px hit targets. | WCAG AAA contrast where feasible; screen-reader tested; exemplary accessible devtool. |
| **Frontend Code Literacy** | Cannot write semantic HTML or CSS; depends entirely on UI tools. | Writes basic HTML/CSS but struggles with flexbox/grid layout bugs. | Writes clean, semantic HTML and modular CSS custom properties. | Implements responsive, fluid CSS grid layouts with zero layout shifts. | Produces production-ready frontend code; understands rendering performance and DOM efficiency. |

---

## 6. Standard Interview Loops, Evidence Logging, and Debrief Protocol

### 6.1 The 4-Stage Technical Interview Loop
Every founding candidate goes through four structured stages:

1. **Stage 1: Technical & Systems Screen (45 Minutes)**
   - Focus: Domain fundamentals, architectural choices, and past project deep-dives.
   - Conducted by: Hiring Partner or Domain Lead.
2. **Stage 2: Hands-On Technical Work-Sample (90 Minutes)**
   - Focus: Solving the role-specific coding or design exercise grounded in Ayentra.
   - Conducted by: Technical Teammate (Pairs on the problem, evaluates code in real-time).
3. **Stage 3: Deep-Dive Systems & Edge-Case Architecture (60 Minutes)**
   - Focus: Probing failure modes, scalability limits, security boundaries, and tradeoffs.
   - Conducted by: Core Architecture Lead / Staff Engineer.
4. **Stage 4: Founder & Team Calibration (45 Minutes)**
   - Focus: Founding ownership, communication rigor, speed of iteration, and human craft.
   - Conducted by: CEO / Founders.

### 6.2 Evidence-Based Candidate Scorecard Template
Interviewers must complete this debrief form within 2 hours of interview completion.

```markdown
# Candidate Technical Scorecard

## Candidate Information
- Candidate Name: [Full Name]
- Role: [Role 1 / 2 / 3 / 4]
- Interview Stage: [Stage 1 / 2 / 3 / 4]
- Interviewer: [Interviewer Name]
- Date: [YYYY-MM-DD]

## 1. Concrete Observed Evidence (Verbatim facts, code behavior, exact statements)
- Example: "Candidate wrote a recursive AST visitor in 42 lines that extracted 3 mutated attributes."
- Example: "When prompted with negative integers, candidate immediately identified the conservation bypass without hints."
- [Log observed fact 1]
- [Log observed fact 2]
- [Log observed fact 3]

## 2. Interviewer Interpretation & Risk Analysis (Clearly separated from facts)
- Example: "Candidate demonstrates strong intuition for AST manipulations, but their initial property test lacked domain constraints."
- [Log interpretation 1]
- [Log interpretation 2]

## 3. Missing Evidence & Unanswered Questions
- Example: "Did not evaluate candidate on multithreaded race condition exploration due to time constraints."
- [Log missing check 1]

## 4. Technical Competency Scoring (1 to 5 Anchors)
| Dimension | Score (1-5) | Justification (Grounded in Observed Evidence) |
| :--- | :---: | :--- |
| Core Technical Competence | [ ] | |
| Edge-Case Rigor & Paranoia | [ ] | |
| Execution Speed & Efficiency | [ ] | |
| Craft & Developer Empathy | [ ] | |
| Technical Communication | [ ] | |
| **Overall Score** | **[ ]** | *(Arithmetic average of dimensions)* |

## 5. Final Hiring Recommendation
Select exactly one:
- [ ] **Strong Hire:** Candidate sets a new technical bar; exceptional founding engineer.
- [ ] **Hire:** Meets all technical bars with verified working code and solid craft.
- [ ] **Leaning No:** Lacks depth in key requirements or missed significant edge cases.
- [ ] **Strong No:** Produced broken code, showed poor debugging discipline, or used empty buzzwords.

**One-Line Decision Summary:**
[Single clear sentence stating the exact technical justification for the decision.]
```

### 6.3 Debrief Meeting Rules
1. All scorecards must be submitted independently before any discussion begins.
2. The debrief starts by reviewing the concrete code written in Stage 2.
3. If an interviewer gives a score of 4 or 5, they must cite specific lines of code or architectural decisions that justify exceeding the bar.
4. If missing evidence is identified on a critical requirement, a focused 30-minute follow-up session is scheduled rather than guessing ability.
5. External candidate outreach and communication remain strictly within the authorized executive workflow.

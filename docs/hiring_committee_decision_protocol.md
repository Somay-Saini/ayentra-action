# Ayentra Founding Engineering Debrief and Hiring Committee Decision Protocol
Version: 1.1.0
Author: Hiring Partner (Ayentra)
Target: CEO, Hiring Committee Members, and Technical Interview Facilitators
Standard: Ayentra Human Taste and Craft Playbook

---

## 1. Executive Purpose and Committee Governance

This protocol governs the final decision-making stage of Ayentra's founding engineering hiring process. The hiring committee exists to make binary, evidence-based hiring decisions (Hire or No-Hire) without relying on gut feel, subjective impressions, or seniority bias.

Every decision directly references artifacts produced during the candidate loop:
- Working code samples and AST transformers from `docs/hiring_kit.md`
- Calibration benchmarks from `docs/candidate_calibration_packet.md`
- Live terminal execution logs from `docs/work_sample_facilitator_guide.md`
- First-PR Day-3 commitments from `docs/onboarding_30_60_90_scorecard.md`
- Compensation options and reference audits from `docs/founding_offer_and_reference_kit.md`

---

## 2. The Written Independent Score Submission Rule

To prevent anchoring bias, conformity cascades, and dominance by senior interviewers, Ayentra enforces a strict blind submission protocol.

### 2.1 The Blind Submission Protocol
1. **Mandatory Pre-Meeting Submission:** Every interviewer must submit their completed BARS 1 to 4 scores, terminal execution logs, and code evidence at least 30 minutes before the debrief meeting begins.
2. **Access Lock:** Interviewers cannot view colleagues' scorecards or written comments until their own scorecard is submitted.
3. **No-Edit Law:** Scores cannot be revised after peer feedback is revealed, unless a clear factual error in code execution or test output is proven using terminal receipts.
4. **Immediate Dismissal of Gut Feel:** Subjective statements (such as "I didn't get a strong staff feel" or "They seemed very smart") are stricken from the official record. All evaluations must cite line numbers, test outputs, or exact candidate statements.

---

## 3. The 30-Minute Structured Hiring Committee Agenda

Committee debriefs are time-boxed to exactly 30 minutes. The meeting is chaired by the Hiring Lead or CEO.

```
+-------------------------------------------------------------------------------+
| Minute 00 to 05: Silent Read of Submitted Artifacts                           |
| - Committee members read the candidate's submitted work-sample code,          |
|   terminal logs, and BARS score cards in complete silence.                    |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| Minute 05 to 15: Technical Facilitator Work-Sample Review                     |
| - Facilitator walks through the 60-minute pair-debugging session.             |
| - Reviews exact commands executed (ayentra check, ayentra apply-patch).       |
| - Reports whether allowed hints or disqualifying hints were given.            |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| Minute 15 to 22: Cross-Interviewer Evidence Audit                             |
| - Interviewers compare observations against the role-specific rubric.         |
| - Identifies gaps, contradictions, or missed edge cases.                      |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| Minute 22 to 27: Evidence-Resolution Matrix for Split Scores                  |
| - Resolves any split scores (e.g. BARS 2 vs BARS 3) using concrete code       |
|   receipts rather than verbal debates.                                        |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| Minute 27 to 30: Binary Vote and Handoff Trigger                              |
| - Committee takes final vote: Hire or No-Hire.                                |
| - If Hire: Triggers the 48-hour closing sequence and reference check audit.   |
+-------------------------------------------------------------------------------+
```

### 3.1 Role-Specific Debrief Focus Areas

#### 1. Founding Verification Engine Engineer (`engine.py`, `contracts.py`, `concurrency.py`)
- **Key Artifact:** `receipt.json` from `ayentra check examples/scheduler_race.py --seed 42`.
- **Primary Debrief Question:** Did the candidate identify the multi-threaded read-modify-write race condition autonomously, and did their solution execute in under 800 milliseconds?
- **Disqualification Check:** Did the candidate fail to protect `release()` with the same mutex used in `allocate()`?

#### 2. Founding AST Synthesis & Repair Engineer (`ast_analyzer.py`, `repair.py`, `regression.py`)
- **Key Artifact:** Unified diff generated by `ayentra apply-patch examples/inventory_ledger.py`.
- **Primary Debrief Question:** Did the synthesized AST transformation preserve source code comments, call `ast.fix_missing_locations`, and pass all 3 sandbox verification gates?
- **Disqualification Check:** Did the candidate resort to string replacement instead of manipulating AST nodes?

#### 3. Founding Developer Experience & Studio Engineer (`cli.py`, `studio.py`, `report.py`, `site/`)
- **Key Artifact:** Cold startup profile of `ayentra --help` and Soft Neutral Light component CSS tokens.
- **Primary Debrief Question:** Did the candidate achieve sub-80ms CLI startup time using lazy imports, and are all interactive controls keyboard-accessible with WCAG AA compliant 2px focus rings?
- **Disqualification Check:** Did the candidate introduce heavy global imports that pushed CLI startup past 300 milliseconds?

#### 4. Founding Enterprise Solutions Architect (`customer_pilot.py`, `design_partner_kit.md`)
- **Key Artifact:** Auditable `ayentra-receipt.json` and 1-page staff-engineer postmortem.
- **Primary Debrief Question:** Did the candidate explain the mathematical ledger conservation bypass in clear financial terms without academic buzzwords, and did they structure a pragmatic 14-day non-blocking CI pilot?
- **Disqualification Check:** Did the candidate recommend blocking production CI on day 1 of an enterprise pilot?

#### 5. Founding Systems Engineer (Sandboxing, Hermetic Execution, Zero-Egress Subprocesses)
- **Key Artifact:** Subprocess sandbox runner benchmark, environment variable scrub receipts, and resource limit enforcement logs (`tests/test_ayentra_engine.py`, `docs/airgapped_runner_hardening.md`, `docs/sbom_and_provenance_manifest.md`).
- **Primary Debrief Question:** Did the candidate demonstrate strict POSIX and Windows subprocess isolation with zero external network socket calls, verified CPU and memory quota constraints, and clean process tree teardown under 100 milliseconds?
- **Disqualification Check:** Did the candidate use shell string interpolation (`shell=True`), permit parent environment inheritance (`GITHUB_TOKEN`, `AWS_*`), or allow unconstrained subprocess fork bombs?

#### 6. Founding Developer Advocate (Technical Documentation, Reproducible Invariant Cookbooks, OSS Community PRs)
- **Key Artifact:** Executable bug reproduction walkthrough, 1-page domain invariant cookbook, and clean GitHub PR review comment diff (`docs/oss_trojan_horse_audits.md`, `docs/oss_maintainer_pr_templates.md`, `examples/fixtures/pr_diff_balance_leak.patch`).
- **Primary Debrief Question:** Did the candidate explain AST invariant verification and counterexample shrinking with concrete, reproducible Python code snippets rather than promotional marketing buzzwords, and could a developer run the reproduction in under 60 seconds?
- **Disqualification Check:** Did the candidate rely on marketing buzzwords or fail to explain the mechanical difference between property testing and unit testing?

---

### 3.2 Candidate Prep Packs and Anchored BARS Scorecards (Post-Launch Roles)

#### Role A: Founding Systems Engineer (Airgapped Sandboxing and CI Systems)

**Competencies and Coverage Matrix:**
| Competency | Source Requirement | Primary Interviewer | Secondary Interviewer |
| :--- | :--- | :--- | :--- |
| 1. Subprocess Isolation & Hermetic Environment | Airgapped runner security (`docs/airgapped_runner_hardening.md`) | Systems Lead | Security Lead |
| 2. Deterministic Concurrency & Timeout Control | Subprocess tree teardown and deadlocks (`concurrency.py`) | Systems Lead | Verification Lead |
| 3. Zero-Egress Security & Credential Hygiene | Parent environment scrub (`docs/sbom_and_provenance_manifest.md`) | Security Lead | Systems Lead |
| 4. Runner Performance & Resource Accounting | Sub-25ms process invocation and memory caps | Systems Lead | CEO |

**Interviewer Prep Pack (Systems Lead):**
- **Focus:** Subprocess Isolation, Process Tree Teardown, and Execution Overhead.
- **Primary Question:** "Walk me through how you isolate an untrusted Python execution runner in an air-gapped CI runner without relying on heavy container runtimes like Docker."
- **Follow-up Probes:**
  1. "How do you ensure parent environment tokens (such as CI secrets or cloud API keys) never leak into the child verification environment?"
  2. "When an invariant check times out on Windows versus Linux, how do you guarantee all child threads and sub-processes are terminated without leaving orphan processes?"
- **Behavioral Anchors (BARS 1 to 4):**
  - **1 (Unacceptable / No Evidence):** Suggests `shell=True`, relies on manual process inspection, or cannot explain how environment variables leak to child processes.
  - **2 (Marginal / Needs Guidance):** Suggests Docker or basic `subprocess.run` but struggles with cross-platform differences (Windows Job Objects vs POSIX process groups); requires multiple hints on clean teardown.
  - **3 (Meets Bar / Solid):** Autonomously writes hermetic subprocess invocation with explicit environment whitelist, closed file descriptors, strict timeout enforcement, and sub-25ms measured overhead.
  - **4 (Exceeds Bar / Staff Caliber):** Proactively addresses OS-level resource limits (cgroups, Job Objects), implements zero-egress socket prevention checks, provides clean terminal trace logs, and benchmarks runner overhead under 15ms.
- **What NOT to Ask:** Personal traits, non-work hobbies, or open-ended theoretical trivia unrelated to systems execution.

#### Role B: Founding Developer Advocate (Developer Friction and OSS Integrations)

**Competencies and Coverage Matrix:**
| Competency | Source Requirement | Primary Interviewer | Secondary Interviewer |
| :--- | :--- | :--- | :--- |
| 1. Minimal Bug Reproduction Synthesis | 10-line reproducible invariant test cases | Devtool Lead | Product Lead |
| 2. Minimal Friction Technical Writing | Staff-engineer tone, zero marketing filler | Devtool Lead | CEO |
| 3. Open Source Community Code Review | Constructive, empathetic PR stewardship | Product Lead | Devtool Lead |
| 4. Empirical Product Differentiation | Property testing vs unit testing differentiation | Devtool Lead | Verification Lead |

**Interviewer Prep Pack (Devtool Lead):**
- **Focus:** Concrete Bug Reproduction, Technical Writing Discipline, and OSS Pull Request Stewardship.
- **Primary Question:** "Take this customer bug report describing an intermittent ledger balance leak in an async payment handler. How do you extract and publish a minimal, reproducible counterexample that any developer can run locally in 30 seconds?"
- **Follow-up Probes:**
  1. "How do you explain to a senior backend engineer why property-based shrinking found an invariant bug that their 100 percent unit test suite missed?"
  2. "When submitting a proactive bug fix to a skeptical open source maintainer, how do you format the PR description to build immediate technical trust?"
- **Behavioral Anchors (BARS 1 to 4):**
  - **1 (Unacceptable / No Evidence):** Uses promotional marketing buzzwords, cannot write working Python reproduction code, or treats developer advocacy as social media hype.
  - **2 (Marginal / Needs Guidance):** Writes acceptable prose but cannot reduce counterexamples to clean minimal scripts; relies on generic blog post templates; defensive when technical assumptions are questioned.
  - **3 (Meets Bar / Solid):** Independently crafts reproducible 10-line property test fixtures, explains shrinking mechanics clearly without jargon, writes crisp documentation with zero filler, and demonstrates empathetic OSS review.
  - **4 (Exceeds Bar / Staff Caliber):** Creates complete interactive terminal workflows, writes publishable invariant cookbooks with quantitative benchmarks, demonstrates track record of merged PRs in tier-1 OSS repos, and coaches team on developer friction telemetry.
- **What NOT to Ask:** Social media follower count, personal demographic background, or general marketing platitudes.

---

## 4. The Evidence-Resolution Matrix: Resolving Split Scores

When interviewers assign differing BARS ratings, the committee resolves disagreements by auditing concrete artifacts, not by debating opinions.

| Split Scenario | Core Point of Disagreement | Deterministic Evidence Check | Final Ruling |
| :--- | :--- | :--- | :--- |
| **BARS 2 vs BARS 3** | Interviewer A believes candidate needed too much guidance; Interviewer B believes candidate solved the core bug. | Review the Facilitator Evidence Capture Sheet. Check if any **Disqualifying Hint** was spoken during Minutes 15 to 45. | If a disqualifying hint was given: **Score is 2 (Reject)**.<br>If only allowed hints were given and code passed: **Score is 3 (Hire)**. |
| **BARS 3 vs BARS 4** | Interviewer A views solution as standard; Interviewer B views candidate as staff-level. | Check the measured execution time and proactive edge-case testing. Did candidate test negative amounts, boundary limits, and concurrency without prompting? | If candidate checked edge cases proactively and code ran in <250ms: **Score is 4 (Strong Hire)**.<br>If candidate required prompting for edge cases: **Score is 3 (Hire)**. |
| **Pass on Logic, Fail on Taste** | Candidate solved the algorithmic problem but introduced heavy third-party dependencies or wrote complex 200-line code. | Apply the Law of Least Effort and YAGNI principle. Could the problem be solved in 35 lines using standard Python library tools (`ast`, `dataclasses`, `typing`)? | If candidate introduced unnecessary external libraries or excessive abstraction: **Taste score capped at 2 (Reject)**. |
| **Split on Communication** | One interviewer felt candidate was defensive; another felt candidate was merely passionate. | Review candidate's verbatim responses when presented with failing counterexamples or test breakages. | If candidate blamed tools, test suites, or peers: **Automatic Disqualification**.<br>If candidate acknowledged the failing receipt and adapted: **Score stands on technical merit**. |
| **Systems Engineer: Isolation vs Latency** | Interviewer A prioritizes ultra-fast execution; Interviewer B insists on complete environment scrubbing. | Audit candidate's runner benchmark. Did the sandbox achieve complete environment variable sanitization and zero-egress enforcement in under 25 milliseconds? | If runner passed zero-egress audit and executed in <25ms: **Score is 4 (Strong Hire)**.<br>If environment scrub was bypassed to achieve speed: **Score is 2 (Reject)**. |
| **Developer Advocate: Polish vs Rigor** | Interviewer A values writing tone; Interviewer B questions depth of AST engine understanding. | Run candidate's submitted reproduction code in terminal (`python reproduction.py`). Does it produce a reproducible failing invariant trace with zero manual setup? | If reproduction script executes and demonstrates invariant failure directly: **Score is 4 (Strong Hire)**.<br>If script is non-functional or requires extensive manual configuration: **Score is 2 (Reject)**. |

---

## 5. Explicit Veto and Disqualification Triggers

Any of the following five conditions results in an immediate, non-negotiable **No-Hire** decision, regardless of candidate pedigree, past employers, or personal likability:

1. **Zero-Egress Security Violation:** Candidate code or proposed architecture attempts to make external network calls during local verification or sandbox execution runs. Ayentra is an air-gapped, zero-egress local verification tool.
2. **Non-Consensual Source Mutation:** Candidate writes patch logic that mutates the user's source files on disk without explicit confirmation (bypassing the `--yes` safety gate in `apply-patch`).
3. **Failing to Verify Regression Gates:** Candidate proposes or applies a patch that resolves the target invariant but causes existing tests in `pytest` to fail or skip.
4. **AI-Slop and Buzzword Padding:** Candidate uses marketing buzzwords (such as unquantified corporate jargon) in technical postmortems or CLI help text instead of direct, staff-engineer microcopy.
5. **Defensive Debugging Posture:** Candidate becomes defensive, uncommunicative, or argumentative when presented with a reproducible failing counterexample, rather than investigating the root cause factually.

---

## 6. Offer-Packet and Reference-Check Handoff Protocol

When the hiring committee reaches a unanimous **Hire** decision, the meeting immediately transitions into the 48-Hour Closing Sequence:

```markdown
# Hiring Committee Offer Handoff Checklist
Candidate Name: [Full Name]
Role: [Verification Engine / Repair & AST / Devtool UI/UX / Enterprise Solutions / Systems Engineer / Developer Advocate]
Date of Decision: [YYYY-MM-DD]
Committee Chair: [CEO Name]

- [ ] 1. Committee Consensus: Unanimous Hire vote recorded with zero unresolved BARS 2 ratings.
- [ ] 2. Assigned Closing Lead: CEO assigned as primary closer; technical lead assigned for peer deep-dive.
- [ ] 3. Compensation Track Selected:
      [ ] Option A (High Equity / Founder Track)
      [ ] Option B (Balanced Track)
      [ ] Option C (Market Specialist Track)
- [ ] 4. Reference Check Handoff: Trigger the 6-question structured reference check script in docs/founding_offer_and_reference_kit.md.
- [ ] 5. Onboarding Bridge Attached: Attach docs/onboarding_30_60_90_scorecard.md to the offer packet to confirm Day-3 First-PR scope.
- [ ] 6. 12-Hour Offer Delivery: Formal offer letter delivered to candidate within 12 hours of committee adjournment.

Approved by CEO: ___________________________  Date: ______________
```

---

## 7. Founding Engineer Day-1 Verification Checklist (Wave 9 Calibration)

Following a unanimous hiring decision and accepted offer, the founding engineer enters Day-1 technical onboarding. Before writing production code or opening the Day-3 First-PR, the hire must complete this deterministic verification checklist grounded in the 25-guide documentation corpus (including `docs/taste_and_ui_audit_report.md`) and the 129-test verification baseline (125 in `tests/` + 4 in `examples/`).

```markdown
# Founding Engineer Day-1 Verification Checklist
Engineer Name: [Full Name]
Role: [Founding Verification / AST Repair / Devtool DX / Solutions / Systems / Dev Advocate]
Date Completed: [YYYY-MM-DD]
Supervising Lead: [CEO / Technical Lead]

- [ ] 1. 129-Test Baseline Execution:
      - Command: pytest -q --tb=short
      - Target: 129 passed tests (125 in tests/ + 4 in examples/) across engine, contracts, concurrency, repair, report, and CLI.
      - Gate: Zero failures, zero warnings, zero skipped invariant assertions.

- [ ] 2. SBOM Provenance and Zero-Egress Audit:
      - Document: docs/sbom_and_provenance_manifest.md
      - Verification: Inspect CycloneDX 1.5 JSON and SPDX 2.3 compatible manifests.
      - Gate: Confirm hermetic offline execution and verify zero network socket imports in core verification paths.

- [ ] 3. 15-Target Repair Benchmark Calibration:
      - Document: docs/repair_benchmark_matrix.md
      - Verification: Replay 15/15 benchmark repair targets across numerical balance, AST mutation, and concurrency races.
      - Gate: Validate Gate 1 counterexample replay under 30 milliseconds and 100% 3-gate sandbox patch pass rate.

- [ ] 4. Design Partner ROI & Customer Value Validation:
      - Document: docs/design_partner_roi_calculator.md
      - Verification: Audit quantitative value formulas for domain invariant drift and TOCTOU concurrency hazards.
      - Gate: Confirm understanding of financial impact metrics and Day 11 to 14 pilot acceptance criteria.

- [ ] 5. 25-Guide Documentation Corpus Cross-Reference:
      - Scope: All 25 markdown guides in docs/
      - Verification: Review architecture, security pack, airgapped runner hardening, triage runbooks, and taste audit.
      - Gate: Confirm 100% documentation coverage with zero missing cross-references or broken anchors.

- [ ] 6. Human Taste and Code Review Signoff Audit:
      - Documents: docs/taste_and_ui_audit_report.md and docs/code_review_signoff.md
      - Verification: Review UI token discipline (Soft Neutral Light), zero AI slop, zero em/en-dash rules, and signoff criteria.
      - Gate: Confirm complete compliance with taste standards and architectural invariants before opening the Day-3 production PR.
```

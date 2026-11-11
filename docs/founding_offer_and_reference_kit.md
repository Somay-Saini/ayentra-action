# Ayentra Founding Team Offer Letter, Equity and Reference Check Playbook
Version: 1.0.0
Author: Hiring Partner (Ayentra)
Target: CEO, Founders, and Engineering Hiring Committee
Standard: Ayentra Human Taste and Craft Playbook

---

## 1. Closing Philosophy and Cap Table Transparency

Founding engineers join Ayentra because they want to build tools they use themselves, take direct architectural ownership, and solve hard verification problems in production codebases.

We do not use aggressive countdown deadlines, artificial exploding bonuses, or obscure clawback clauses. Instead, we close exceptional founding talent through radical transparency, rapid decision-making, and alignment on long-term ownership.

### 1.1 Core Principles of the Offer Process
1. **Radical Transparency:** We share company runway, capitalization structure, investor terms, enterprise pilot metrics, and current code debt openly before an offer is signed.
2. **24-Hour Debrief Turnaround:** We conduct the candidate debrief within 24 hours of the final interview and issue offers immediately to top-tier talent.
3. **The 48-Hour Closing Sprint:** Offers are accompanied by direct founder access and structured peer conversations to resolve questions within two business days.
4. **Direct Bridge to Day-1:** Every offer letter references the concrete 30-60-90 day roadmap defined in `docs/onboarding_30_60_90_scorecard.md`.
5. **No Corporate Jargon:** We communicate with staff-engineer clarity. We do not use corporate buzzwords or vague promises.

---

## 2. Structured Backchannel and Reference Check Interview Guide

Reference checks at Ayentra are technical audits, not routine administrative formalities. Conduct these 20-minute phone interviews with direct engineering managers, staff technical leads, or close peers who reviewed the candidate's pull requests daily.

### 2.1 Formal References vs Backchannel Inquiries
- **Formal References:** Provided by the candidate. Useful for confirming project scope, timeline, and employment dates.
- **Backchannel Inquiries:** Conducted through mutual trusted colleagues in our network. Essential for discovering how the candidate operates under real pressure, their edge-case discipline, and their technical honesty. Always request candidate consent before contacting current colleagues.

### 2.2 The 6 Core Evidence-Based Questions

#### Question 1: Technical Velocity and Autonomous Execution
"When you worked together, how quickly did they ship production-ready code compared to other senior engineers on your team? Can you describe a specific complex feature or system they designed and shipped completely on their own?"
- *Target:* Separates independent self-starters who ship within 72 hours from engineers who require constant direction.
- *Observable Evidence:* Look for specific system names, lines of code, and measured delivery timelines.

#### Question 2: Debugging Under Pressure and Edge-Case Paranoia
"When severe production outages or subtle bugs occurred (such as race conditions, memory leaks, or arithmetic errors), what was their debugging discipline like? Did they catch edge cases proactively, or did bugs slip past them into production?"
- *Target:* Verifies paranoia around software correctness. Ayentra builds verification engines; candidates must care deeply about edge cases.
- *Observable Evidence:* Look for examples of root-cause analyses, regression test additions, and post-mortem contributions.

#### Question 3: Simplicity and Code Craft Discipline
"Do they write minimal, maintainable solutions, or do they tend to introduce heavy abstractions and unnecessary third-party dependencies? Can you give an example of a time they chose a simple solution over a complex one?"
- *Target:* Evaluates adherence to the Law of Least Effort and YAGNI (You Aren't Gonna Need It).
- *Observable Evidence:* Look for evidence of using the Python standard library, deleting dead code, and keeping dependencies lean.

#### Question 4: Technical Pushback and Handling Disagreement
"Can you share an instance where they strongly disagreed with an architectural choice or technical roadmap? How did they present their counterargument, and how did they react if the team decided to move in a different direction?"
- *Target:* Tests intellectual honesty, data-backed reasoning, and absence of toxic ego.
- *Observable Evidence:* Look for respectful, code-backed arguments and commitment to team execution once a decision was made.

#### Question 5: Communication Precision vs Noise
"How would you rate their written and verbal technical communication? Do they explain complex engineering tradeoffs directly and factually, or do they rely on vague generalizations?"
- *Target:* Verifies alignment with the Human Taste Playbook (zero fluff, direct staff-engineer tone).
- *Observable Evidence:* Look for clear pull request descriptions, factual incident reports, and concise Slack communication.

#### Question 6: The Re-hire Ultimate Test
"If you were starting a new software company tomorrow, would you actively recruit them as one of your first five founding teammates? Why or why not?"
- *Target:* The definitive calibration check. Any hesitation or qualified answer is a signal to examine technical gaps closely.

### 2.3 Disqualifying Red Flags Cheat Sheet

| Observed Behavior During Reference Call | Underlying Risk to Ayentra | Action Required |
| :--- | :--- | :--- |
| **Blaming Others for Outages** | Reference notes candidate blamed junior engineers or external tools when production broke. | Immediate Disqualification |
| **Credit Inflation** | Reference clarifies that a claimed project was actually designed and built by someone else. | Immediate Disqualification |
| **Resistance to Code Reviews** | Candidate reacted defensively or became uncommunicative when PRs received critical feedback. | Immediate Disqualification |
| **Over-Engineering Bias** | Candidate repeatedly introduced complex microservices or frameworks for simple problems. | Score 2 or Below on Taste |
| **Polite Hesitation on Re-hire** | Reference pauses, uses diplomatic language, or says "it depends on the role." | Deep-Dive on Specific Gaps |

---

## 3. Founding Offer Architecture and Compensation Models

Founding engineers at Ayentra receive competitive compensation packages consisting of cash salary and meaningful equity ownership. We offer three distinct equity and cash combinations per role so candidates can choose their preferred risk profile.

### 3.1 Standard Founding Equity Terms
- **Option Type:** Incentive Stock Options (ISOs) where applicable.
- **Vesting Schedule:** Standard 4-year vesting with a 1-year cliff (25% vests after 12 months, monthly linear vesting thereafter).
- **Extended Exercise Window:** 10-year post-termination exercise window for early departures after 2 years of service, preventing golden handcuffs.
- **Acceleration:** Double-trigger acceleration upon change of control where unassumed by an acquirer.
- **Transparency Package:** Every candidate receives total outstanding share count, latest 409A valuation, current cash balance, and monthly burn rate in writing.

### 3.2 Role-by-Role Compensation Frameworks

#### 1. Founding Verification Engine Engineer (`engine.py`, `contracts.py`, `concurrency.py`)
- **Option A (High Equity / Founder Track):** $145,000 base salary + 1.75% equity (175,000 shares / 10M pool).
- **Option B (Balanced Track):** $175,000 base salary + 1.10% equity (110,000 shares / 10M pool).
- **Option C (Market Specialist Track):** $205,000 base salary + 0.60% equity (60,000 shares / 10M pool).

#### 2. Founding AST Synthesis & Repair Engineer (`ast_analyzer.py`, `repair.py`, `regression.py`)
- **Option A (High Equity / Founder Track):** $145,000 base salary + 1.75% equity (175,000 shares / 10M pool).
- **Option B (Balanced Track):** $175,000 base salary + 1.10% equity (110,000 shares / 10M pool).
- **Option C (Market Specialist Track):** $205,000 base salary + 0.60% equity (60,000 shares / 10M pool).

#### 3. Founding Developer Experience & Studio Engineer (`cli.py`, `studio.py`, `report.py`, `site/`)
- **Option A (High Equity / Founder Track):** $140,000 base salary + 1.60% equity (160,000 shares / 10M pool).
- **Option B (Balanced Track):** $170,000 base salary + 1.00% equity (100,000 shares / 10M pool).
- **Option C (Market Specialist Track):** $195,000 base salary + 0.55% equity (55,000 shares / 10M pool).

#### 4. Founding Applied Security & CI Systems Engineer (Sandboxing, SARIF, Zero-Egress CI)
- **Option A (High Equity / Founder Track):** $145,000 base salary + 1.65% equity (165,000 shares / 10M pool).
- **Option B (Balanced Track):** $175,000 base salary + 1.05% equity (105,000 shares / 10M pool).
- **Option C (Market Specialist Track):** $200,000 base salary + 0.55% equity (55,000 shares / 10M pool).

---

## 4. Pre-Offer Executive Decision Checklist

Before extending a formal offer, the CEO and hiring leads must verify every item on this 10-point checklist. If any check fails, the offer must not be extended.

```markdown
# Ayentra Pre-Offer Verification Checklist
Candidate Name: [Full Name]
Target Role: [Role 1 / 2 / 3 / 4]
Date: [YYYY-MM-DD]

- [ ] 1. Code Correctness: Candidate produced working, functional code during the hands-on exercise.
- [ ] 2. Edge-Case Paranoia: Candidate proactively spotted boundary inputs (negative numbers, NoneType, race conditions).
- [ ] 3. Speed & Performance: Candidate solution ran within sub-second execution limits (<500ms for CLI/AST sweeps).
- [ ] 4. Code Simplicity: Candidate wrote clean, minimal code using standard libraries rather than bloated dependencies.
- [ ] 5. Scorecard Calibration: Candidate received scores of 3 or higher across all dimensions, with at least one 5.
- [ ] 6. Reference Validation: Completed 2+ reference checks confirming technical velocity and high ownership.
- [ ] 7. Red Flag Audit: No instances of credit inflation, defensive communication, or blaming past teammates.
- [ ] 8. Roadmap Alignment: Candidate reviewed docs/onboarding_30_60_90_scorecard.md and agreed to the Day-3 PR goal.
- [ ] 9. Culture & Taste Check: Candidate communicates with direct staff-engineer precision and zero AI filler.
- [ ] 10. Founder Unanimity: CEO and all interviewing technical leads unanimously approve extending the offer.

Sign-off: ___________________________ (CEO, Ayentra)
```

---

## 5. The 48-Hour High-Touch Closing Sequence

Top founding engineers receive multiple competitive offers. Closing them requires high velocity, personal respect, and immediate answers to difficult questions.

```
+-------------------------------------------------------------------------------+
| Hour 0 to 4: Founder Offer Call                                               |
| - CEO walks through the equity grant, compensation options, and vision.       |
| - Explains why the candidate specifically is chosen to own this subsystem.   |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| Hour 4 to 12: Written Offer Packet Delivered                                  |
| - Formal offer letter with clear equity mechanics.                            |
| - Detailed cap table summary and runway disclosure.                           |
| - docs/onboarding_30_60_90_scorecard.md attached for Day-1 alignment.         |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| Hour 12 to 24: Technical Peer Deep-Dive Call                                  |
| - 30-minute informal chat with an Ayentra engineering lead.                   |
| - Thorough walk-through of actual codebase architecture, open PRs, and near-term debt.  |
| - Candidate speaks directly with future daily collaborators.                  |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| Hour 24 to 36: Diligence & Question Resolution                                |
| - Address equity tax questions (83b election, ISO vs NSO, 10-year exercise).  |
| - Resolve hardware, home office, or remote setup preferences.                 |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| Hour 36 to 48: Signed Offer & Onboarding Handshake                            |
| - Offer countersigned. Hardware ordered immediately.                          |
| - Calendar invites sent for Day-1 setup protocol.                             |
| - Candidate receives welcome message from the entire founding team.           |
+-------------------------------------------------------------------------------+
```

---

## 6. Standard Ayentra Founding Offer Letter Template

```markdown
# Ayentra Founding Team Employment Offer

Date: [Date]
To: [Candidate Name]
Position: [Role Title: e.g. Founding Verification Engine Engineer]
Location: [Remote / Office Location]
Reports to: Chief Executive Officer, Ayentra

Dear [Candidate First Name],

On behalf of Ayentra, I am proud to offer you a founding position on our core team. We build software that brings formal behavioral verification to production systems, and we believe your technical skills, edge-case paranoia, and code taste make you the right engineer to own [Subsystem Name: e.g. the core verification and property testing engine].

### 1. Position and Scope of Ownership
As [Role Title], you will have direct architectural authority over [Core Files: e.g. src/ayentra/engine.py, contracts.py, and concurrency.py]. You will report directly to the CEO and work closely with our founding engineering loop. Your operational roadmap and performance milestones are defined in our 30-60-90 Day Scorecard Playbook.

### 2. Compensation Options
You may select one of the following three compensation and equity packages:

- Option A (High Equity / Founder Track): $[Amount] base salary + [Number] shares ([Percentage]% of fully diluted equity).
- Option B (Balanced Track): $[Amount] base salary + [Number] shares ([Percentage]% of fully diluted equity).
- Option C (Market Specialist Track): $[Amount] base salary + [Number] shares ([Percentage]% of fully diluted equity).

Base salary is paid semi-monthly in accordance with Ayentra's standard payroll schedule.

### 3. Equity Terms
Subject to approval by the Ayentra Board of Directors, your stock options will be issued under our 2026 Equity Incentive Plan with the following terms:
- 4-year vesting schedule with a 1-year cliff (25% vests at 12 months, followed by 1/48th monthly).
- 10-year exercise window post-termination for early departures after 24 months of service.
- Standard double-trigger acceleration upon a change of control.
- ISO tax treatment to the maximum extent permitted by law.

### 4. Benefits and Equipment
- Health, Dental, and Vision coverage (100% covered for employee, 75% for dependents).
- Hardware budget: Choice of top-spec developer laptop (MacBook Pro M-series or Linux workstation) plus two 4K displays.
- Home office / workspace stipend: $1,500 initial setup budget.
- Flexible paid time off and standard company holidays.

### 5. Start Date and Day-1 Protocol
Your scheduled start date is [Start Date]. On Day 1, you will clone the repository, run the verification test suite, and begin work on your Day-3 First-PR deliverable as outlined in docs/onboarding_30_60_90_scorecard.md.

### 6. Acceptance and Expiration
This offer remains open until [Date, 48 hours from issuance], at 5:00 PM Pacific Time.

To accept, please sign and return this letter. We are eager to build the future of verified software with you.

Sincerely,

__________________________________________
[CEO Name], Chief Executive Officer
Ayentra

### Candidate Acceptance
I accept the offer of employment as set forth above:

Selected Option: [ Option A / Option B / Option C ]
Signature: _______________________________
Name: [Candidate Name]
Date: ___________________________________
```

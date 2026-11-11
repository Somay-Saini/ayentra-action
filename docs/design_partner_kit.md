# Enterprise Design Partner Pilot Guide

Ayentra verifies explicit behavioral contracts in Python codebases, finds minimal reproducible counterexamples using property-based shrinking, and verifies candidate fixes in an isolated sandbox before merge.

This guide walks through onboarding, CI integration, SARIF 2.1.0 security scanning, and automated PR reviews for enterprise design partners, grounded in the financial ledger implementation in `examples/customer_pilot.py`.

---

## 1. Two-Command Zero-Config CI Onboarding

Enterprise engineering teams adopt Ayentra without writing custom workflow scripts or configuring cloud accounts.

```bash
# 1. Install Ayentra in your environment
pip install ayentra

# 2. Scaffold workspace configuration and GitHub Actions workflow
ayentra init --ci
```

### What `ayentra init --ci` Does

1. **Creates `ayentra.toml`**: Detects project layout and sets contract defaults for your workspace.
2. **Creates `.github/workflows/ayentra.yml`**: Generates a standard GitHub Actions workflow that runs on push and pull request events to `main` and `master`.

```yaml
name: Ayentra Verification Gate

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install ayentra

      - name: Run Ayentra Verification Gate
        run: |
          ayentra check . --ci --sarif ayentra-report.sarif

      - name: Upload SARIF to GitHub Code Scanning
        uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: ayentra-report.sarif
```

---

## 2. Automated PR Review Comment and Collapsible Unidiff Workflow

When a pull request introduces an invariant violation, Ayentra posts a clear review comment to the pull request. It explains the exact business risk, prints the shrunk counterexample vector, renders a collapsible unified diff, and provides a single command to apply the verified fix.

### Running PR Review Mode

```bash
# Generate GitHub PR review comment markdown to a file
ayentra pr-mock examples/customer_pilot.py --pr-comment pr_review.md

# Emit GitHub Actions step summary markdown table and annotations
ayentra check examples/customer_pilot.py --ci --step-summary
```

### Output Example: Financial Ledger Pull Request Comment

```markdown
## Ayentra PR Bot: Invariant Verification Gate FAILED

> Action Required: One or more explicit invariants failed under property-based adversarial testing.

### Finding 1: `EnterprisePaymentLedger.hold_in_escrow`
- Plain-English Bug: Method EnterprisePaymentLedger.hold_in_escrow failed on input {"amount": -1, "tx_id": "tx_1"}: invariant 'self.available >= 0 and self.escrow >= 0 and self.available + self.escrow == self.total_funds' did not hold.
- Business Risk: Critical risk: Financial balance corruption or negative ledger drift (direct monetary loss).
- Minimal Counterexample: `{"amount": -1, "tx_id": "tx_1"}`
- 1-Click Merge Fix: `ayentra apply-patch examples/customer_pilot.py --yes`

#### Interactive Diff Preview (Before vs After)
<details open>
<summary>View Unified Patch Diff</summary>

```diff
--- a/customer_pilot.py
+++ b/customer_pilot.py
@@ -17,7 +17,11 @@ class EnterprisePaymentLedger:
     def hold_in_escrow(self, amount: int, tx_id: str) -> bool:
+        if amount <= 0:
+            raise ValueError('amount must be positive')
+        if amount > self.available:
+            raise ValueError('Insufficient available for operation')
         if tx_id in self.settled_tx_ids:
             return True
         self.available -= amount
         self.escrow += amount
         self.settled_tx_ids.add(tx_id)
         return True
```
</details>

- Sandbox Status: `VERIFIED CANDIDATE FIX` (Counterexample Replay: PASS | Invariant Sweep: PASS | Pytest: PASS)
```

---

## 3. GitHub Advanced Security SARIF 2.1.0 Code Scanning

Ayentra generates OASIS SARIF 2.1.0 compliant JSON reports. GitHub Advanced Security ingests these reports natively into repository Security tabs, displaying file paths, exact line numbers, and rule metadata.

### Generating SARIF Reports

```bash
# Generate SARIF report for a single module
ayentra check examples/customer_pilot.py --sarif ayentra-report.sarif

# Generate SARIF report across an entire directory
ayentra check examples/ --sarif ayentra-report.sarif
```

### SARIF 2.1.0 Payload Structure

The generated report complies with the official OASIS schema:

```json
{
  "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
  "version": "2.1.0",
  "runs": [
    {
      "tool": {
        "driver": {
          "name": "Ayentra",
          "version": "0.1.0",
          "informationUri": "https://github.com/ayentra/ayentra",
          "rules": [
            {
              "id": "AYENTRA001",
              "name": "InvariantViolation",
              "shortDescription": {
                "text": "Explicit behavioral invariant violated under property-based testing"
              },
              "defaultConfiguration": {
                "level": "error"
              }
            }
          ]
        }
      },
      "results": [
        {
          "ruleId": "AYENTRA001",
          "ruleIndex": 0,
          "level": "error",
          "message": {
            "text": "Invariant violation in EnterprisePaymentLedger.hold_in_escrow: balance conservation violated on amount=-1."
          },
          "locations": [
            {
              "physicalLocation": {
                "artifactLocation": {
                  "uri": "examples/customer_pilot.py",
                  "uriBaseId": "%SRCROOT%"
                },
                "region": {
                  "startLine": 18,
                  "startColumn": 1
                }
              }
            }
          ]
        }
      ]
    }
  ]
}
```

---

## 4. Grounded Pilot Target: Financial Ledger Invariant Verification

The pilot scenario in `examples/customer_pilot.py` demonstrates how Ayentra catches domain bugs that standard unit tests miss.

### The Contract

```python
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
            self.settled_tx_ids.add(tx_id)
            return True
        return False
```

### The Bug Unit Tests Miss

A developer writes unit tests using clean positive values like `hold_in_escrow(100, 'tx_1')`. The test passes.

In production, an upstream parser accepts a negative integer (`amount = -1`).
Because `-1 <= 1000` evaluates to `True`, the code runs:
- `self.available -= -1` (available becomes 1001)
- `self.escrow += -1` (escrow becomes -1)

Total funds are no longer conserved. Escrow becomes negative. Money is created out of nowhere.

### How Ayentra Solves It

1. **Adversarial Shrinking**: Ayentra tests domain bounds and shrinks the failing input directly to `amount = -1`.
2. **Sandbox Patch Synthesis**: Ayentra synthesizes guard conditions (`if amount <= 0: raise ValueError(...)`).
3. **Triple-Stage Verification**:
   - Replays `amount = -1` (now raises ValueError and handles cleanly).
   - Sweeps 120 random test cases across the domain bounds.
   - Runs the existing `pytest` test suite to verify zero regressions.
4. **One-Command Fix**: Run `ayentra apply-patch examples/customer_pilot.py --yes` to write the verified fix to disk.

---

## 5. Direct Outreach Templates for Design Partners

Use these three direct, fluff-free templates when initiating pilot conversations with engineering leaders.

### Template 1: For Fintech and Payments Staff Engineers

**Subject:** Invariant verification for Python payment ledgers

```text
Hi [Name],

I saw your team handles core payment settlements and ledger balances in Python.

We built Ayentra, a local verification gate that catches domain invariant violations before code merges. For example, in an escrow ledger where `available + escrow == total_funds`, standard unit tests pass on clean positive values, but negative amounts or race conditions corrupt the ledger state.

Ayentra synthesizes inputs against explicit type and domain bounds, shrinks edge cases down to the exact minimal failing input (like amount = -1), and tests a verified patch in an isolated sandbox.

Onboarding takes two commands:
$ pip install ayentra
$ ayentra init --ci

Can I share a 3-minute reproducible demo on examples/customer_pilot.py?

Best,
[Your Name]
```

### Template 2: For VP of Engineering

**Subject:** Pre-merge invariant verification for critical Python services

```text
Hi [Name],

Engineering teams often face production incidents caused by edge-case business logic errors that unit tests and type checkers miss, such as double-allocations or state drift.

Ayentra adds an automated verification gate to your GitHub pull requests:
1. Two-command onboarding: `pip install ayentra && ayentra init --ci` scaffolds configuration and CI in seconds.
2. Zero cloud lock-in: Everything runs locally or within your existing GitHub Actions runners.
3. Automated PR reviews: Comments on pull requests with plain-English risk ratings and collapsible unified diffs.
4. Non-destructive fixes: Synthesized fixes are verified against your existing pytest suite before anything touches disk.

We are selecting four enterprise design partners for our pilot program. Would you have 10 minutes this week to discuss whether your team fits?

Best,
[Your Name]
```

### Template 3: For DevSecOps and AppSec Leads

**Subject:** SARIF 2.1.0 invariant scanning for GitHub Actions

```text
Hi [Name],

Static analysis tools (SAST) flag known syntactic CVE patterns, but they cannot verify whether business logic invariants hold under unexpected inputs.

Ayentra exports native OASIS SARIF 2.1.0 reports directly into GitHub Advanced Security code scanning:
- Command: `ayentra check . --ci --sarif ayentra-report.sarif`
- Direct integration: Uploads via `github/codeql-action/upload-sarif@v3`
- High precision: Every finding includes the failing input vector, exact file location, and sandbox-verified fix diff.
- Zero false alarms on style: Flags only reproducible violations of explicit contracts.

I would like to show you our security scan output on our enterprise ledger pilot. Do you have time for a quick technical look on Thursday?

Best,
[Your Name]
```

# Ayentra SARIF 2.1.0 & Supply-Chain Integrity Verification Guide

**Classification:** Enterprise AppSec & CI/CD Hardening Guide  
**Release Version:** Ayentra v0.1.0  
**Effective Date:** 2026-11-03  
**Compatibility:** GitHub Advanced Security (GHAS), GitLab Security Dashboard, Air-Gapped / Zero-Egress CI Runners  

---

## 1. Verified Release Artifact Hashes & Air-Gapped Installation

Ayentra adheres to SLSA-compatible build provenance standards. All release wheels and source distributions are cryptographically fingerprinted to enable hermetic, hash-pinned installations in high-security enterprise environments.

### 1.1 Release Artifact Digests (v0.1.0)

| Distribution File | Size (Bytes) | SHA-256 Cryptographic Checksum |
| :--- | :--- | :--- |
| `ayentra-0.1.0-py3-none-any.whl` | 108,791 | `c6e91a15798e0c419c91a6657fd92e901865ed219dc0a0409271723e733a7e73` |
| `ayentra-0.1.0.tar.gz` | 143,855 | `2c72fdf4719f51c28e87b96808ff8e9b30c9310842316611d9ae58ac0b65de0c` |

### 1.2 Hash-Pinned Enterprise Installation Snippet

In zero-trust or air-gapped CI runner environments where external package indices are restricted or proxied via internal mirrors (JFrog Artifactory, Sonatype Nexus, AWS CodeArtifact), enforce strict SHA-256 verification via pip `--require-hashes`.

#### Option A: Requirements File with Hashes (`requirements-security.txt`)
```txt
# Ayentra v0.1.0 Cryptographically Pinned Distribution
ayentra==0.1.0 \
    --hash=sha256:c6e91a15798e0c419c91a6657fd92e901865ed219dc0a0409271723e733a7e73 \
    --hash=sha256:2c72fdf4719f51c28e87b96808ff8e9b30c9310842316611d9ae58ac0b65de0c
```

Install command in runner:
```bash
pip install --require-hashes -r requirements-security.txt
```

#### Option B: Direct Air-Gapped Wheel Installation
If caching distribution wheels directly within an enterprise repository or artifact cache:
```bash
# Verify wheel hash before execution
echo "c6e91a15798e0c419c91a6657fd92e901865ed219dc0a0409271723e733a7e73 *dist/ayentra-0.1.0-py3-none-any.whl" | sha256sum -c -
pip install dist/ayentra-0.1.0-py3-none-any.whl --no-index --find-links=dist/
```

---

## 2. SARIF 2.1.0 Schema Mapping to GitHub Code Scanning

Ayentra exports findings directly to OASIS Static Analysis Results Interchange Format (SARIF) v2.1.0. This allows native alert ingestion into GitHub Advanced Security (GHAS) and GitLab Security Center without requiring proprietary agents or cloud connectors.

### 2.1 Schema Mapping Table

| Ayentra Diagnostic Entity | SARIF 2.1.0 Field | GitHub Code Scanning Surface |
| :--- | :--- | :--- |
| Engine Rule Definition | `runs[0].tool.driver.rules[0].id` | Rule ID: `AYENTRA001` (InvariantViolation) |
| Rule Category Tags | `rules[0].properties.tags` | Filter Badges: `correctness`, `security`, `invariants` |
| Precision Rating | `rules[0].properties.precision` | Confidence Rating: `very-high` |
| Failure Severity | `results[i].level` | GHAS Alert Severity: `error` |
| Target Code Location | `results[i].locations[0].physicalLocation` | Exact file link and line marker in PR diff view |
| Human-Readable Finding | `results[i].message.text` | Alert title and expanded description |
| Reproducible Counterexample | `results[i].properties.counterexample` | Shrunk property test failure arguments |
| Synthesized Patch Fix | `results[i].fixes[0]` | Suggested 1-click diff in GitHub Code Scanning |

### 2.2 Concrete SARIF 2.1.0 Output Structure

When running `ayentra check src/ --sarif ayentra.sarif`, Ayentra outputs valid SARIF 2.1.0 JSON structured as follows:

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
              "fullDescription": {
                "text": "An explicit behavioral contract or domain invariant failed verification under deterministic shrinking."
              },
              "defaultConfiguration": {
                "level": "error"
              },
              "help": {
                "text": "Inspect counterexample. Run 'ayentra apply-patch <file> --yes' to apply fix.",
                "markdown": "Inspect counterexample. Run `ayentra apply-patch <file> --yes` to apply fix."
              },
              "properties": {
                "tags": ["correctness", "security", "invariants"],
                "precision": "very-high"
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
            "text": "Invariant violation in Vault.withdraw: Balance must not drop below zero. Risk: Ledger deficit."
          },
          "locations": [
            {
              "physicalLocation": {
                "artifactLocation": {
                  "uri": "services/vault.py",
                  "uriBaseId": "%SRCROOT%"
                },
                "region": {
                  "startLine": 42,
                  "startColumn": 1
                }
              }
            }
          ],
          "properties": {
            "failing_target": "Vault.withdraw",
            "counterexample": {"amount": 100},
            "seed": 42
          }
        }
      ]
    }
  ]
}
```

---

## 3. GitHub Advanced Security (GHAS) Production Workflow

This hardened workflow demonstrates the least-privilege configuration for running Ayentra and uploading SARIF reports to GitHub Code Scanning.

### 3.1 Least-Privilege Permissions Model

The workflow requests only the minimum scopes required:
- `contents: read`: Checks out the repository files.
- `security-events: write`: Uploads `ayentra.sarif` to GitHub Advanced Security.
- `pull-requests: write`: Posts or updates PR review comments.

### 3.2 Production Workflow File: `.github/workflows/ayentra-security-gate.yml`

```yaml
name: Ayentra Invariant & Security Gate

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

permissions:
  contents: read
  security-events: write
  pull-requests: write

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  verify:
    name: Verify Invariants & Export SARIF
    runs-on: ubuntu-latest
    timeout-minutes: 15

    steps:
      - name: Checkout Source Code
        uses: actions/checkout@v4
        with:
          persist-credentials: false

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install Pinned Ayentra Package
        run: |
          python -m pip install --upgrade pip
          pip install --require-hashes -r - << 'EOF'
          ayentra==0.1.0               --hash=sha256:c6e91a15798e0c419c91a6657fd92e901865ed219dc0a0409271723e733a7e73               --hash=sha256:2c72fdf4719f51c28e87b96808ff8e9b30c9310842316611d9ae58ac0b65de0c
          EOF

      - name: Run Ayentra Verification Gate
        env:
          TARGET: 'src'
          SEED: '42'
          MAX_EXAMPLES: '120'
          JSON_OUT: 'ayentra-receipt.json'
          SARIF_OUT: 'ayentra.sarif'
          PR_COMMENT_OUT: 'ayentra-pr-comment.md'
        run: |
          ayentra check "$TARGET" \
            --seed "$SEED" \
            --max-examples "$MAX_EXAMPLES" \
            --json-out "$JSON_OUT" \
            --sarif "$SARIF_OUT" \
            --pr-comment "$PR_COMMENT_OUT" \
            --step-summary

      - name: Upload SARIF Report to GitHub Advanced Security
        if: always() && hashFiles('ayentra.sarif') != ''
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: ayentra.sarif
          category: ayentra-invariants

      - name: Post PR Review Comment
        if: always() && github.event_name == 'pull_request' && hashFiles('ayentra-pr-comment.md') != ''
        env:
          GH_TOKEN: ${{ github.token }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
        run: |
          if [ -s ayentra-pr-comment.md ] && [ -n "$PR_NUMBER" ]; then
            gh pr comment "$PR_NUMBER" --body-file ayentra-pr-comment.md --edit-last || \
            gh pr comment "$PR_NUMBER" --body-file ayentra-pr-comment.md
          fi

      - name: Archive Verification Receipt Artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: ayentra-verification-artifacts
          path: |
            ayentra-receipt.json
            ayentra-pr-comment.md
            ayentra.sarif
          retention-days: 90
```

---

## 4. Fork Pull Request Isolation Guarantees

When evaluating pull requests from public or untrusted forks, enforce structural boundary isolation:

### 4.1 Strict Trigger Separation
- **Trigger on `pull_request`:** The runner executes code submitted in the fork without access to repository secrets. The default `GITHUB_TOKEN` is read-only.
- **Never trigger on `pull_request_target`:** Workflows using `pull_request_target` grant fork code access to base repository secrets and write tokens. Ayentra should never execute untrusted code in a `pull_request_target` context.

### 4.2 Two-Stage Comment Posting for Public Repositories
If your repository does not grant write tokens to fork PR workflows, split verification into two jobs:
1. **Verification Job (`pull_request`):** Runs `ayentra check` under read-only permissions and uploads `ayentra-pr-comment.md` as a GitHub Actions artifact.
2. **Comment Posting Job (`workflow_run` on `main`):** Triggers upon completion of the verification job, downloads the artifact, and posts the comment using `pull-requests: write`, without ever executing fork code.

---

## 5. GitLab Security Dashboard Integration

GitLab Ultimate customers can import Ayentra SARIF reports into the GitLab Vulnerability Report.

### 5.1 GitLab CI Pipeline Configuration (`.gitlab-ci.yml`)

```yaml
stages:
  - test

ayentra_gate:
  stage: test
  image: python:3.11-slim
  variables:
    PIP_REQUIRE_HASHES: "true"
  before_script:
    - pip install --upgrade pip
    - |
      pip install --require-hashes -r - << 'EOF'
      ayentra==0.1.0           --hash=sha256:c6e91a15798e0c419c91a6657fd92e901865ed219dc0a0409271723e733a7e73           --hash=sha256:2c72fdf4719f51c28e87b96808ff8e9b30c9310842316611d9ae58ac0b65de0c
      EOF
  script:
    - ayentra check src/ --seed 42 --max-examples 120 --sarif ayentra.sarif --json-out ayentra-receipt.json
  artifacts:
    when: always
    reports:
      sast: ayentra.sarif
    paths:
      - ayentra-receipt.json
      - ayentra.sarif
    expire_in: 90 days
```

---

## 6. Audit & Verification Summary

- **Package Version:** `ayentra==0.1.0`
- **Wheel SHA-256:** `c6e91a15798e0c419c91a6657fd92e901865ed219dc0a0409271723e733a7e73`
- **Source Archive SHA-256:** `2c72fdf4719f51c28e87b96808ff8e9b30c9310842316611d9ae58ac0b65de0c`
- **Standard Conformance:** OASIS SARIF 2.1.0 / GitHub Advanced Security Schema
- **Air-Gap Capability:** 100% offline execution; zero external network egress required.

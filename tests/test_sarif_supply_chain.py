from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from ayentra.ast_analyzer import ASTAnalysisResult
from ayentra.contracts import InvariantSpec
from ayentra.engine import EngineCheckResult, InvariantViolation
from ayentra.regression import RegressionRunResult
from ayentra.repair import PatchVerificationResult
from ayentra.sarif import build_sarif_report, to_sarif


def test_supply_chain_artifact_digests_and_sizes_match_security_guide() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    dist_dir = repo_root / "dist"
    guide_path = repo_root / "docs" / "sarif_github_security_guide.md"

    assert guide_path.is_file(), f"Security guide not found at {guide_path}"
    guide_text = guide_path.read_text(encoding="utf-8")

    # Match rows: | `filename` | size | `sha256` |
    pattern = re.compile(
        r"\|\s*`([^`]+)`\s*\|\s*([0-9,]+)\s*\|\s*`([a-f0-9]{64})`\s*\|"
    )
    matches = pattern.findall(guide_text)
    assert len(matches) >= 2, f"Expected at least 2 artifact table entries in {guide_path}, found {len(matches)}"

    for filename, size_str, sha in matches:
        artifact_path = dist_dir / filename
        assert artifact_path.is_file(), f"Built artifact not found: {artifact_path}"

        raw_bytes = artifact_path.read_bytes()
        actual_size = len(raw_bytes)
        actual_sha = hashlib.sha256(raw_bytes).hexdigest()
        documented_size = int(size_str.replace(",", ""))

        assert actual_size == documented_size, (
            f"{filename} size mismatch: documented {documented_size}, actual {actual_size}"
        )
        assert actual_sha == sha, (
            f"{filename} sha256 mismatch: documented {sha}, actual {actual_sha}"
        )
        assert sha in guide_text, f"{filename} sha256 {sha} missing from guide snippets"


def test_ayentra_sarif_to_sarif_schema_structure_and_fixes(tmp_path: Path) -> None:
    test_src = tmp_path / "payments.py"
    test_src.write_text("def process(amount: int) -> int:\n    return amount\n", encoding="utf-8")

    dummy_invariant = InvariantSpec(
        expression="amount >= 0",
        target_name="process",
        kind="function",
        lineno=1,
        filepath=str(test_src),
        description="non_negative_amount",
    )

    violation = InvariantViolation(
        invariant=dummy_invariant,
        verification_method="hypothesis",
        failing_target="process",
        counterexample={"amount": -50},
        trace_steps=["process(-50) -> -50"],
        expected_state_desc="amount >= 0",
        actual_state={"result": -50},
        seed=1337,
        cases_evaluated=10,
        domain_bounds={"amount": "int(-100, 100)"},
    )

    ast_analysis = ASTAnalysisResult(
        filepath=str(test_src),
        explicit_decorator_lines={},
        mutated_attributes={},
        has_lock_synchronization={},
        suggestions=[],
    )

    engine_res = EngineCheckResult(
        filepath=str(test_src),
        invariants_checked=[dummy_invariant],
        violations=[violation],
        ast_analysis=ast_analysis,
        total_cases_evaluated=10,
        seed=1337,
        duration_ms=2.5,
        domain_summary={},
    )

    reg_res = RegressionRunResult(
        passed=True,
        passed_count=1,
        failed_count=0,
        duration_ms=1.0,
        output_summary="1 passed",
    )

    patch_res = PatchVerificationResult(
        original_filepath=str(test_src),
        patched_source="def process(amount: int) -> int:\n    return max(0, amount)\n",
        unified_diff="--- a/payments.py\n+++ b/payments.py\n@@ -1,2 +1,2 @@\n-def process(amount: int) -> int:\n-    return amount\n+def process(amount: int) -> int:\n+    return max(0, amount)\n",
        counterexample_passed=True,
        invariant_sweep_passed=True,
        invariant_cases_tested=10,
        regression_result=reg_res,
        verification_duration_ms=1.5,
        repair_strategy="clamp",
    )

    sarif_doc = to_sarif([(test_src, engine_res, [patch_res])], root_dir=tmp_path)

    json_str = json.dumps(sarif_doc, indent=2)
    assert json_str

    assert sarif_doc["$schema"] == "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"
    assert sarif_doc["version"] == "2.1.0"
    assert len(sarif_doc["runs"]) == 1

    run = sarif_doc["runs"][0]
    assert run["tool"]["driver"]["name"] == "Ayentra"
    assert run["tool"]["driver"]["version"] == "0.1.0"
    assert len(run["tool"]["driver"]["rules"]) == 1
    assert run["tool"]["driver"]["rules"][0]["id"] == "AYENTRA001"

    assert len(run["results"]) == 1
    result = run["results"][0]
    assert result["ruleId"] == "AYENTRA001"
    assert result["level"] == "error"
    assert "payments.py" in result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    assert result["locations"][0]["physicalLocation"]["artifactLocation"]["uriBaseId"] == "%SRCROOT%"
    assert result["locations"][0]["physicalLocation"]["region"]["startLine"] == 1
    assert result["properties"]["failing_target"] == "process"
    assert result["properties"]["counterexample"] == {"amount": -50}
    assert result["properties"]["seed"] == 1337

    assert "fixes" in result
    assert len(result["fixes"]) == 1
    fix = result["fixes"][0]
    assert fix["artifactChanges"][0]["artifactLocation"]["uriBaseId"] == "%SRCROOT%"

    alias_doc = build_sarif_report([(test_src, engine_res, [patch_res])], root_dir=tmp_path)
    assert alias_doc == sarif_doc


def test_ayentra_sarif_clean_target_zero_violations(tmp_path: Path) -> None:
    test_src = tmp_path / "clean.py"
    test_src.write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")

    ast_analysis = ASTAnalysisResult(
        filepath=str(test_src),
        explicit_decorator_lines={},
        mutated_attributes={},
        has_lock_synchronization={},
        suggestions=[],
    )

    clean_engine_res = EngineCheckResult(
        filepath=str(test_src),
        invariants_checked=[],
        violations=[],
        ast_analysis=ast_analysis,
        total_cases_evaluated=25,
        seed=42,
        duration_ms=1.2,
        domain_summary={},
    )

    sarif_doc = to_sarif([(test_src, clean_engine_res, [])], root_dir=tmp_path)
    assert sarif_doc["version"] == "2.1.0"
    assert len(sarif_doc["runs"]) == 1
    assert sarif_doc["runs"][0]["results"] == []
    assert sarif_doc["runs"][0]["tool"]["driver"]["name"] == "Ayentra"


def test_documentation_and_shared_markdown_character_hygiene() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    docs_dir = repo_root / "docs"

    markdown_files: list[Path] = list(docs_dir.glob("*.md"))

    shared_dir = Path(r"C:\Users\Somay\OpenBot\Shared")
    if shared_dir.is_dir():
        markdown_files.extend(shared_dir.glob("*.md"))

    assert len(markdown_files) >= 5, f"Expected at least 5 markdown docs, found {len(markdown_files)}"

    offending_files: list[str] = []
    for md_path in markdown_files:
        md_text = md_path.read_text(encoding="utf-8")
        if "\u2014" in md_text or "\u2013" in md_text:
            offending_files.append(str(md_path))

    assert not offending_files, f"Found em-dashes or en-dashes in: {offending_files}"


def test_onboarding_and_benchmark_documents_exist() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    docs_dir = repo_root / "docs"

    required_docs = [
        "repair_benchmark_matrix.md",
        "onboarding_30_60_90_scorecard.md",
        "sarif_github_security_guide.md",
    ]

    for doc_name in required_docs:
        doc_path = docs_dir / doc_name
        assert doc_path.is_file(), f"Required doc missing: {doc_path}"
        assert len(doc_path.read_text(encoding="utf-8").strip()) > 100, f"Doc appears empty: {doc_path}"

def test_site_directories_and_sbom_panel_parity() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    site_dirs = [
        repo_root / "site",
        repo_root / "src" / "ayentra" / "site",
        Path(r"C:\Users\Somay\OpenBot\Shared\ayentra-site"),
    ]
    assets = ["index.html", "app.js", "styles.css"]

    canonical_hashes: dict[str, str] = {}
    for asset in assets:
        primary_file = site_dirs[0] / asset
        assert primary_file.is_file(), f"Primary asset missing: {primary_file}"
        canonical_hashes[asset] = hashlib.sha256(primary_file.read_bytes()).hexdigest()

    for s_dir in site_dirs:
        if not s_dir.is_dir():
            continue
        for asset in assets:
            asset_path = s_dir / asset
            assert asset_path.is_file(), f"Asset {asset} missing in {s_dir}"
            actual_sha = hashlib.sha256(asset_path.read_bytes()).hexdigest()
            assert actual_sha == canonical_hashes[asset], f"Hash mismatch for {asset} in {s_dir}"

    html = (site_dirs[0] / "index.html").read_text(encoding="utf-8")
    assert 'id="sbom"' in html
    assert "CycloneDX" in html
    assert "c6e91a15798e0c419c91a6657fd92e901865ed219dc0a0409271723e733a7e73" in html
    assert "2c72fdf4719f51c28e87b96808ff8e9b30c9310842316611d9ae58ac0b65de0c" in html


def test_readme_and_release_dossier_link_all_24_docs() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    docs_dir = repo_root / "docs"
    doc_files = list(docs_dir.glob("*.md"))
    assert len(doc_files) == 26, f"Expected 26 markdown docs in {docs_dir}, found {len(doc_files)}"

    readme_text = (repo_root / "README.md").read_text(encoding="utf-8")
    dossier_file = docs_dir / "release_go_no_go_dossier.md"
    dossier_text = dossier_file.read_text(encoding="utf-8")

    shared_dossier = Path(r"C:\Users\Somay\OpenBot\Shared\ayentra_release_go_no_go_dossier.md")
    assert shared_dossier.is_file(), f"Shared dossier missing at {shared_dossier}"
    assert dossier_text == shared_dossier.read_text(encoding="utf-8")

    for doc in doc_files:
        assert doc.name in readme_text, f"{doc.name} not linked in README.md"
        assert doc.name in dossier_text, f"{doc.name} not linked in release_go_no_go_dossier.md"

def test_wave_9_taste_report_and_code_review_signoff_parity() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    docs_dir = repo_root / "docs"
    shared_dir = Path(r"C:\Users\Somay\OpenBot\Shared")

    taste_local = docs_dir / "taste_and_ui_audit_report.md"
    taste_shared = shared_dir / "ayentra_taste_and_ui_audit_report.md"
    assert taste_local.is_file(), f"Missing local taste report: {taste_local}"
    assert taste_shared.is_file(), f"Missing shared taste report: {taste_shared}"
    assert taste_local.stat().st_size > 0, "Local taste report is empty"
    assert taste_local.read_bytes() == taste_shared.read_bytes(), "Taste reports are not byte-identical"

    code_review_local = docs_dir / "code_review_signoff.md"
    code_review_shared = shared_dir / "ayentra_code_review_signoff.md"
    assert code_review_local.is_file(), f"Missing local code review signoff: {code_review_local}"
    assert code_review_shared.is_file(), f"Missing shared code review signoff: {code_review_shared}"
    assert code_review_local.stat().st_size > 0, "Local code review signoff is empty"
    assert code_review_local.read_bytes() == code_review_shared.read_bytes(), "Code review signoffs are not byte-identical"
    assert "Wave 8 Delta Review" in code_review_local.read_text(encoding="utf-8")

    doc_files = list(docs_dir.glob("*.md"))
    assert len(doc_files) == 26, f"Expected 26 docs, found {len(doc_files)}"
    readme_text = (repo_root / "README.md").read_text(encoding="utf-8")
    dossier_text = (docs_dir / "release_go_no_go_dossier.md").read_text(encoding="utf-8")

    for doc in doc_files:
        assert doc.name in readme_text, f"{doc.name} missing from README.md"
        assert doc.name in dossier_text, f"{doc.name} missing from release_go_no_go_dossier.md"

def test_wave_11_governance_hash_pinning_and_all_25_shared_docs_parity() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    docs_dir = repo_root / "docs"
    shared_dir = Path(r"C:\Users\Somay\OpenBot\Shared")

    doc_files = sorted(docs_dir.glob("*.md"))
    assert len(doc_files) == 26, f"Expected 26 docs, found {len(doc_files)}"

    for doc in doc_files:
        shared_doc = shared_dir / f"ayentra_{doc.name}"
        assert shared_doc.is_file(), f"Missing shared mirror for {doc.name}: {shared_doc}"
        assert doc.read_bytes() == shared_doc.read_bytes(), f"Byte parity mismatch for {doc.name}"

    sbom_text = (docs_dir / "sbom_and_provenance_manifest.md").read_text(encoding="utf-8")
    for gov_name in ("release_go_no_go_dossier.md", "code_review_signoff.md", "taste_and_ui_audit_report.md"):
        gov_path = docs_dir / gov_name
        digest = hashlib.sha256(gov_path.read_bytes()).hexdigest()
        size_str = f"{gov_path.stat().st_size:,}"
        assert digest in sbom_text, f"SHA-256 digest {digest} for {gov_name} not pinned in sbom_and_provenance_manifest.md"
        assert size_str in sbom_text, f"Byte size {size_str} for {gov_name} not pinned in sbom_and_provenance_manifest.md"
    runbook_text = (docs_dir / "launch_war_room_runbook.md").read_text(encoding="utf-8")
    assert "c6e91a15798e0c419c91a6657fd92e901865ed219dc0a0409271723e733a7e73" in runbook_text
    assert "2c72fdf4719f51c28e87b96808ff8e9b30c9310842316611d9ae58ac0b65de0c" in runbook_text
    assert "7aa9684b18bb4e0527260eb88c69bd15ee1c556a6f7340de1e12127adcfdb34b" in runbook_text

def test_wave_12_release_kit_and_roi_calculator_baseline_parity() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    docs_dir = repo_root / "docs"
    shared_dir = Path(r"C:\Users\Somay\OpenBot\Shared")

    launch_kit = (docs_dir / "public_launch_kit.md").read_text(encoding="utf-8")
    assert "Verified 128-Case Test Suite" in launch_kit
    assert "128 tests passing" in launch_kit
    assert (docs_dir / "public_launch_kit.md").read_bytes() == (shared_dir / "ayentra_public_launch_kit.md").read_bytes()

    roi_calc = (docs_dir / "design_partner_roi_calculator.md").read_text(encoding="utf-8")
    assert "128 / 128" in roi_calc
    assert (docs_dir / "design_partner_roi_calculator.md").read_bytes() == (shared_dir / "ayentra_design_partner_roi_calculator.md").read_bytes()

    taste_report = (docs_dir / "taste_and_ui_audit_report.md").read_text(encoding="utf-8")
    assert "25 / 25 linked" in taste_report
    assert "| 25 | `work_sample_facilitator_guide.md`" in taste_report

    hiring_proto = (docs_dir / "hiring_committee_decision_protocol.md").read_text(encoding="utf-8")
    assert ("128-Test Baseline Execution" in hiring_proto or "129-Test Baseline Execution" in hiring_proto)

def test_wave_13_airgapped_runner_and_enterprise_security_pack_hash_pinning() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    docs_dir = repo_root / "docs"
    shared_dir = Path(r"C:\Users\Somay\OpenBot\Shared")

    airgap_local = docs_dir / "airgapped_runner_hardening.md"
    airgap_shared = shared_dir / "ayentra_airgapped_runner_hardening.md"
    assert airgap_local.read_bytes() == airgap_shared.read_bytes()
    airgap_text = airgap_local.read_text(encoding="utf-8")
    assert "108,791" in airgap_text
    assert "143,855" in airgap_text
    assert "c6e91a15798e0c419c91a6657fd92e901865ed219dc0a0409271723e733a7e73" in airgap_text
    assert "2c72fdf4719f51c28e87b96808ff8e9b30c9310842316611d9ae58ac0b65de0c" in airgap_text

    sec_local = docs_dir / "enterprise_security_pack.md"
    sec_shared = shared_dir / "ayentra_enterprise_security_pack.md"
    assert sec_local.read_bytes() == sec_shared.read_bytes()
    sec_text = sec_local.read_text(encoding="utf-8")
    assert "--require-hashes" in sec_text
    assert "c6e91a15798e0c419c91a6657fd92e901865ed219dc0a0409271723e733a7e73" in sec_text
    assert "2c72fdf4719f51c28e87b96808ff8e9b30c9310842316611d9ae58ac0b65de0c" in sec_text
def test_wave_14_launch_kit_chk01_and_code_review_delta_sync() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    docs_dir = repo_root / "docs"
    shared_dir = Path(r"C:\Users\Somay\OpenBot\Shared")

    launch_kit = (docs_dir / "public_launch_kit.md").read_text(encoding="utf-8")
    assert "128 passing tests (124 in `tests/` and 4 in `examples/`)" in launch_kit
    assert "passed 128/128 tests (124 in `tests/` + 4 in `examples/`)" in launch_kit
    assert "123 passing tests" not in launch_kit
    assert "123/123" not in launch_kit

    crs_local = docs_dir / "code_review_signoff.md"
    crs_shared = shared_dir / "ayentra_code_review_signoff.md"
    assert crs_local.read_bytes() == crs_shared.read_bytes()
    crs_text = crs_local.read_text(encoding="utf-8")
    assert "Wave 9 to Wave 17 Delta Review: 128-Test Suite" in crs_text
    assert "`15/15` passing tests" in crs_text
    assert "`128/128` passing tests: `124` in `tests/` and `4` in `examples/`" in crs_text
    assert "Wave 17 Sign-Off Complete" in crs_text

    dossier_local = docs_dir / "release_go_no_go_dossier.md"
    dossier_shared = shared_dir / "ayentra_release_go_no_go_dossier.md"
    assert dossier_local.read_bytes() == dossier_shared.read_bytes()
    dossier_text = dossier_local.read_text(encoding="utf-8")
    assert "128 tests collected and passing (124 in tests/, 4 in examples/)" in dossier_text
    assert "128/128 passing tests" in dossier_text


def test_wave_15_benchmarks_and_repair_matrix_receipt_parity() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    docs_dir = repo_root / "docs"
    shared_dir = Path(r"C:\Users\Somay\OpenBot\Shared")

    bm_local = docs_dir / "benchmarks.md"
    bm_shared = shared_dir / "ayentra_benchmarks.md"
    assert bm_local.read_bytes() == bm_shared.read_bytes()
    bm_text = bm_local.read_text(encoding="utf-8")
    assert "108,791 bytes / 106.24 KB" in bm_text
    assert "143,855 bytes / 140.48 KB" in bm_text
    assert "c6e91a15798e0c419c91a6657fd92e901865ed219dc0a0409271723e733a7e73" in bm_text
    assert "2c72fdf4719f51c28e87b96808ff8e9b30c9310842316611d9ae58ac0b65de0c" in bm_text
    assert "128 / 128 tests passing (100.0%: 124 in `tests/` + 4 in `examples/`)" in bm_text
    assert "108 / 108" not in bm_text

    rm_local = docs_dir / "repair_benchmark_matrix.md"
    rm_shared = shared_dir / "ayentra_repair_benchmark_matrix.md"
    assert rm_local.read_bytes() == rm_shared.read_bytes()
    rm_text = rm_local.read_text(encoding="utf-8")
    assert "15 / 15 (100.0%)" in rm_text
    assert "2,734.07 ms" in rm_text

def test_wave_16_oss_trojan_horse_and_pilot_onboarding_sla_parity() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    docs_dir = repo_root / "docs"
    shared_dir = Path(r"C:\Users\Somay\OpenBot\Shared")

    oss_local = docs_dir / "oss_trojan_horse_audits.md"
    oss_shared = shared_dir / "ayentra_oss_trojan_horse_audits.md"
    assert oss_local.read_bytes() == oss_shared.read_bytes()
    oss_text = oss_local.read_text(encoding="utf-8")
    for target_idx in range(1, 9):
        assert f"## Target {target_idx}:" in oss_text
    assert "py-moneyed" in oss_text
    assert "django-money" in oss_text
    assert "stripe-python" in oss_text
    assert "pyrate-limiter" in oss_text
    assert "beancount" in oss_text
    assert "python-escrow" in oss_text

    sla_local = docs_dir / "pilot_onboarding_sla.md"
    sla_shared = shared_dir / "ayentra_pilot_onboarding_sla.md"
    assert sla_local.read_bytes() == sla_shared.read_bytes()
    sla_text = sla_local.read_text(encoding="utf-8")
    assert "< 15 minutes (24/7)" in sla_text
    assert '"sandbox_status": "VERIFIED CANDIDATE FIX"' in sla_text
    assert '"counterexample_replay": "PASS"' in sla_text
    assert '"property_sweep_120": "PASS"' in sla_text
    assert '"pytest_regression": "PASS"' in sla_text
    for bp in ("Blueprint 1: Ramp", "Blueprint 2: Brex", "Blueprint 3: Razorpay", "Blueprint 4: Deel", "Blueprint 5: Mercury"):
        assert bp in sla_text

    sec_local = docs_dir / "security_audit.md"
    sec_shared = shared_dir / "ayentra_security_audit.md"
    assert sec_local.read_bytes() == sec_shared.read_bytes()
    sec_text = sec_local.read_text(encoding="utf-8")
    assert "128 passed (100% pass rate: 124 in `tests/` + 4 in `examples/`)" in sec_text
    assert "102 passed" not in sec_text

def test_wave_17_launch_faq_oss_pr_templates_and_design_partner_kit_parity() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    docs_dir = repo_root / "docs"
    shared_dir = Path(r"C:\Users\Somay\OpenBot\Shared")

    faq_local = docs_dir / "launch_day_faq.md"
    faq_shared = shared_dir / "ayentra_launch_day_faq.md"
    assert faq_local.read_bytes() == faq_shared.read_bytes()
    faq_text = faq_local.read_text(encoding="utf-8")
    assert "https://ayentra-self-healing-ci-gate-for-python-ayentra-gekf76yujn.openbot.site" in faq_text
    for q_idx in range(1, 19):
        assert f"### Q{q_idx}:" in faq_text

    pr_local = docs_dir / "oss_maintainer_pr_templates.md"
    pr_shared = shared_dir / "ayentra_oss_maintainer_pr_templates.md"
    assert pr_local.read_bytes() == pr_shared.read_bytes()
    pr_text = pr_local.read_text(encoding="utf-8")
    for t_idx in range(1, 9):
        assert f"### Target {t_idx}:" in pr_text
    assert "0 em-dashes, 0 en-dashes, 0 AI buzzwords." in pr_text

    dpk_local = docs_dir / "design_partner_kit.md"
    dpk_shared = shared_dir / "ayentra_design_partner_kit.md"
    assert dpk_local.read_bytes() == dpk_shared.read_bytes()
    dpk_text = dpk_local.read_text(encoding="utf-8")
    assert "ayentra init --ci" in dpk_text
    assert "EnterprisePaymentLedger.hold_in_escrow" in dpk_text
    assert "VERIFIED CANDIDATE FIX" in dpk_text

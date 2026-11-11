from __future__ import annotations

from ayentra.ast_analyzer import ASTAnalysisResult, CandidateSuggestion, analyze_source
from ayentra.contracts import InvariantSpec, domain, invariant
from ayentra.engine import EngineCheckResult, InvariantViolation, run_verification_engine
from ayentra.repair import PatchVerificationResult, generate_and_verify_patch
from ayentra.report import VerificationReport, build_verification_report
from ayentra.sarif import build_sarif_report, to_sarif
from ayentra.studio import StudioHandler, create_studio_server, execute_full_check, run_studio_server

__version__ = "0.1.0"

__all__ = [
    "ASTAnalysisResult",
    "CandidateSuggestion",
    "EngineCheckResult",
    "InvariantSpec",
    "InvariantViolation",
    "PatchVerificationResult",
    "VerificationReport",
    "analyze_source",
    "build_verification_report",
    "StudioHandler",
    "create_studio_server",
    "domain",
    "execute_full_check",
    "run_studio_server",
    "generate_and_verify_patch",
    "invariant",
    "run_verification_engine",
    "build_sarif_report",
    "to_sarif",
]

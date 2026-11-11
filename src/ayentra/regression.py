from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RegressionRunResult:
    passed: bool
    passed_count: int
    failed_count: int
    duration_ms: float
    output_summary: str


def run_pytest_suite(
    working_dir: str | Path,
    test_target: str | Path | None = None,
) -> RegressionRunResult:
    t0 = time.perf_counter()
    cwd = Path(working_dir).resolve()

    target = str(test_target) if test_target is not None else ("examples" if (cwd / "examples").is_dir() else ".")
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        target,
        "-q",
        "--tb=short",
        "--no-header",
    ]
    if Path(cwd, "src", "ayentra").exists():
        cmd.append("--ignore=tests")

    env = dict(os.environ)
    src_dir = str(Path(__file__).resolve().parents[1])
    existing_pp = env.get("PYTHONPATH", "")
    parts = [str(cwd), src_dir]
    if existing_pp:
        parts.append(existing_pp)
    env["PYTHONPATH"] = os.pathsep.join(parts)

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return RegressionRunResult(
            passed=False,
            passed_count=0,
            failed_count=1,
            duration_ms=30000.0,
            output_summary="Pytest suite timed out after 30 seconds.",
        )
    duration_ms = (time.perf_counter() - t0) * 1000.0
    stdout = (proc.stdout or "") + "\n" + (proc.stderr or "")

    passed_match = re.search(r"(\d+)\s+passed", stdout)
    failed_match = re.search(r"(\d+)\s+(?:failed|error)", stdout)
    passed_count = int(passed_match.group(1)) if passed_match else 0
    failed_count = int(failed_match.group(1)) if failed_match else 0

    if proc.returncode == 5:
        # pytest exit code 5: no tests collected
        return RegressionRunResult(
            passed=True,
            passed_count=0,
            failed_count=0,
            duration_ms=duration_ms,
            output_summary="No existing pytest tests collected (0 failed)",
        )

    ok = proc.returncode == 0 and failed_count == 0
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    summary = lines[-1] if lines else ("PASSED" if ok else "FAILED")
    return RegressionRunResult(
        passed=ok,
        passed_count=passed_count,
        failed_count=failed_count,
        duration_ms=duration_ms,
        output_summary=summary,
    )

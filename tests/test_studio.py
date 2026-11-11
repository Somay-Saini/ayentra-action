from __future__ import annotations

import json
from pathlib import Path
import threading
import urllib.error
import urllib.request
from typing import Generator

import pytest

from ayentra.regression import RegressionRunResult
from ayentra.studio import STUDIO_HTML, StudioHandler, create_studio_server


@pytest.fixture(scope="module")
def studio_env(tmp_path_factory: pytest.TempPathFactory) -> Generator[tuple[str, Path], None, None]:
    mp = pytest.MonkeyPatch()
    mp.setattr(
        "ayentra.repair.run_pytest_suite",
        lambda *args, **kwargs: RegressionRunResult(
            passed=True,
            passed_count=1,
            failed_count=0,
            duration_ms=1.0,
            output_summary="1 passed",
        ),
    )

    tmp_path = tmp_path_factory.mktemp("studio_workspace")
    target = tmp_path / "calc_target.py"
    target.write_text(
        "from __future__ import annotations\n"
        "from ayentra.contracts import invariant, domain\n\n"
        "@domain(x='int:0..20', y='int:0..20')\n"
        "@invariant('result >= x and result >= y', description='Sum must be at least each addend')\n"
        "def sum_positive(x: int, y: int) -> int:\n"
        "    return x - y\n",
        encoding="utf-8",
    )

    enum_target = tmp_path / "set_enum_target.py"
    enum_target.write_text(
        "from __future__ import annotations\n"
        "from enum import Enum\n"
        "from typing import Literal\n"
        "from ayentra.contracts import invariant\n\n"
        "class PolicyTier(Enum):\n"
        "    BRONZE = 1\n"
        "    GOLD = 2\n\n"
        "@invariant('result >= 0')\n"
        "def compute_set_density(\n"
        "    items: set[int],\n"
        "    frozen_tags: frozenset[int],\n"
        "    mode: Literal['fast', 'safe'],\n"
        "    tier: PolicyTier,\n"
        ") -> float:\n"
        "    return (abs(sum(items)) + len(frozen_tags) + tier.value + (1 if mode == 'fast' else 0)) / len(items)\n",
        encoding="utf-8",
    )

    server = create_studio_server(workspace_root=tmp_path, host="127.0.0.1", port=0)
    server_port = server.server_port
    base_url = f"http://127.0.0.1:{server_port}"

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield base_url, tmp_path

    server.shutdown()
    server.server_close()
    mp.undo()


def _request_json(
    url: str,
    method: str = "GET",
    data: dict | None = None,
) -> tuple[int, dict]:
    payload = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"error": body}
        return err.code, parsed
    except (ConnectionResetError, ConnectionAbortedError):
        return 400, {"error": "Connection reset by server due to oversized payload"}


def _request_raw(
    url: str,
    method: str = "POST",
    raw_bytes: bytes | None = None,
    content_type: str = "application/json",
) -> tuple[int, dict]:
    headers = {"Content-Type": content_type} if content_type else {}
    req = urllib.request.Request(url, data=raw_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"error": body}
        return err.code, parsed


def test_studio_get_index_serves_html(studio_env: tuple[str, Path]) -> None:
    base_url, _ = studio_env
    req = urllib.request.Request(f"{base_url}/", method="GET")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        content_type = resp.headers.get("Content-Type", "")
        assert "text/html" in content_type
        html = resp.read().decode("utf-8")

    assert "Ayentra Studio" in html
    assert "#F6F5F2" in html
    assert "#FCFCFA" in html
    assert "Export JSON Receipt" in html
    assert "Copy Unified Diff" in html
    assert "Download SARIF" in html
    assert "Copy CI Summary" in html
    assert "\u2014" not in html and "\u2013" not in html


def test_studio_get_targets_list(studio_env: tuple[str, Path]) -> None:
    base_url, _ = studio_env
    status, data = _request_json(f"{base_url}/api/targets")
    assert status == 200
    assert "targets" in data
    assert isinstance(data["targets"], list)
    assert any("calc_target.py" in t for t in data["targets"])
    assert any("set_enum_target.py" in t for t in data["targets"])


def test_studio_post_check_validation_and_report(studio_env: tuple[str, Path]) -> None:
    base_url, _ = studio_env

    status, report = _request_json(
        f"{base_url}/api/check",
        method="POST",
        data={"file": "calc_target.py", "seed": 42, "max_examples": 5},
    )
    assert status == 200
    assert "total_cases_evaluated" in report
    assert report["total_cases_evaluated"] >= 1
    assert "total_duration_ms" in report
    assert report["total_duration_ms"] >= 0
    assert "engine_duration_ms" in report
    assert report["engine_duration_ms"] >= 0
    assert "violations" in report
    assert len(report["violations"]) >= 1

    status_missing, err_missing = _request_json(
        f"{base_url}/api/check",
        method="POST",
        data={},
    )
    assert status_missing == 400
    assert "Missing target file" in err_missing.get("error", "")

    status_nonexistent, err_nonexistent = _request_json(
        f"{base_url}/api/check",
        method="POST",
        data={"file": "missing_file_xyz.py"},
    )
    assert status_nonexistent == 404
    assert "Target file not found" in err_nonexistent.get("error", "")


def test_studio_post_suggest_route(studio_env: tuple[str, Path]) -> None:
    base_url, _ = studio_env

    status, data = _request_json(
        f"{base_url}/api/suggest",
        method="POST",
        data={"file": "calc_target.py"},
    )
    assert status == 200
    assert data.get("filepath") == "calc_target.py"
    assert "suggestions" in data
    assert isinstance(data["suggestions"], list)

    status_missing, err_missing = _request_json(
        f"{base_url}/api/suggest",
        method="POST",
        data={},
    )
    assert status_missing == 400
    assert "Missing target file" in err_missing.get("error", "")

    status_nonexistent, err_nonexistent = _request_json(
        f"{base_url}/api/suggest",
        method="POST",
        data={"file": "does_not_exist.py"},
    )
    assert status_nonexistent == 404
    assert "Target file not found" in err_nonexistent.get("error", "")


def test_studio_post_apply_patch_valid_and_invalid(studio_env: tuple[str, Path]) -> None:
    base_url, tmp_path = studio_env

    status_empty, err_empty = _request_json(
        f"{base_url}/api/apply-patch",
        method="POST",
        data={},
    )
    assert status_empty == 400
    assert err_empty.get("applied") is False
    assert "Missing target file" in err_empty.get("error", "")

    status_missing, err_missing = _request_json(
        f"{base_url}/api/apply-patch",
        method="POST",
        data={"file": "ghost_target.py"},
    )
    assert status_missing == 400
    assert err_missing.get("applied") is False
    assert "Target file not found" in err_missing.get("error", "")

    status_apply, res_apply = _request_json(
        f"{base_url}/api/apply-patch",
        method="POST",
        data={"file": "set_enum_target.py", "seed": 42, "max_examples": 10},
    )
    assert status_apply == 200
    assert res_apply.get("applied") is True
    assert res_apply.get("status") == "VERIFIED PATCH APPLIED"

    patched_content = (tmp_path / "set_enum_target.py").read_text(encoding="utf-8")
    assert "if not items:" in patched_content


def test_studio_backward_compat_get_routes_and_unknown(studio_env: tuple[str, Path]) -> None:
    base_url, _ = studio_env

    status, report = _request_json(f"{base_url}/api/check?file=calc_target.py&seed=42&max_examples=5")
    assert status == 200
    assert "total_cases_evaluated" in report

    status_missing, _ = _request_json(f"{base_url}/api/check")
    assert status_missing == 400

    status_sug, sug_data = _request_json(f"{base_url}/api/suggest?file=calc_target.py")
    assert status_sug == 200
    assert "suggestions" in sug_data

    req = urllib.request.Request(f"{base_url}/api/unknown_endpoint", method="GET")
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == 404


def test_studio_malformed_json_and_bad_request_bodies(studio_env: tuple[str, Path]) -> None:
    base_url, _ = studio_env

    endpoints = ["/api/check", "/api/suggest", "/api/apply-patch", "/api/sarif"]
    malformed_payloads = [
        b"{invalid json here",
        b"not json at all",
        b'{"unclosed": ',
        b"{",
        b"}",
    ]
    for endpoint in endpoints:
        for payload in malformed_payloads:
            status, data = _request_raw(f"{base_url}{endpoint}", method="POST", raw_bytes=payload)
            assert status == 400
            assert "error" in data

    non_dict_payloads = [
        b"[1, 2, 3]",
        b'"a standalone string"',
        b"12345",
        b"true",
        b"null",
    ]
    for endpoint in endpoints:
        for payload in non_dict_payloads:
            status, data = _request_raw(f"{base_url}{endpoint}", method="POST", raw_bytes=payload)
            assert status == 400
            assert "error" in data

    status_chk, data_chk = _request_json(f"{base_url}/api/check", method="POST", data={"seed": 42})
    assert status_chk == 400
    assert "Missing target file" in data_chk.get("error", "")

    status_sug, data_sug = _request_json(f"{base_url}/api/suggest", method="POST", data={"seed": 42})
    assert status_sug == 400
    assert "Missing target file" in data_sug.get("error", "")

    status_patch, data_patch = _request_json(f"{base_url}/api/apply-patch", method="POST", data={"seed": 42})
    assert status_patch == 400
    assert data_patch.get("applied") is False
    assert "Missing target file" in data_patch.get("error", "")

    status_bad_seed, data_bad_seed = _request_json(
        f"{base_url}/api/check",
        method="POST",
        data={"file": "calc_target.py", "seed": "not_an_int"},
    )
    assert status_bad_seed == 400
    assert "Invalid seed or max_examples" in data_bad_seed.get("error", "")

    status_bad_max, data_bad_max = _request_json(
        f"{base_url}/api/check",
        method="POST",
        data={"file": "calc_target.py", "max_examples": "unlimited"},
    )
    assert status_bad_max == 400
    assert "Invalid seed or max_examples" in data_bad_max.get("error", "")

    status_bad_patch_seed, data_bad_patch_seed = _request_json(
        f"{base_url}/api/apply-patch",
        method="POST",
        data={"file": "calc_target.py", "seed": "bad_seed"},
    )
    assert status_bad_patch_seed == 400
    assert data_bad_patch_seed.get("applied") is False
    assert "Invalid seed or max_examples" in data_bad_patch_seed.get("error", "")


def test_studio_path_traversal_and_unusual_query_strings(studio_env: tuple[str, Path]) -> None:
    base_url, _ = studio_env

    safe_get_queries = [
        "/?file=../../../../etc/passwd",
        "/?file=..%2F..%2Fwindows%2Fwin.ini",
        "/?x=1&inject=<script>alert('xss')</script>&unicode=%F0%9F%92%A9",
        "/?&&&key=value&&",
        "/?seed=not_num&max=99999999999999999999",
    ]
    for query in safe_get_queries:
        req = urllib.request.Request(f"{base_url}{query}", method="GET")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            content = resp.read().decode("utf-8")
            assert "Ayentra Studio" in content

    traversal_files = [
        "../../outside.py",
        r"..\..\windows\system32\calc.exe",
        "..%2F..%2Foutside.py",
        "/etc/passwd",
        r"C:\Windows\System32\drivers\etc\hosts",
    ]
    for bad_file in traversal_files:
        status_get_chk, _ = _request_json(f"{base_url}/api/check?file={urllib.parse.quote(bad_file)}")
        assert status_get_chk in (400, 404)

        status_post_chk, _ = _request_json(
            f"{base_url}/api/check",
            method="POST",
            data={"file": bad_file},
        )
        assert status_post_chk in (400, 404)

        status_post_sug, _ = _request_json(
            f"{base_url}/api/suggest",
            method="POST",
            data={"file": bad_file},
        )
        assert status_post_sug in (400, 404)

        status_post_patch, data_post_patch = _request_json(
            f"{base_url}/api/apply-patch",
            method="POST",
            data={"file": bad_file},
        )
        assert status_post_patch in (400, 404)
        assert data_post_patch.get("applied") is False

        status_get_sarif, _ = _request_json(f"{base_url}/api/sarif?file={urllib.parse.quote(bad_file)}")
        assert status_get_sarif in (400, 404)

        status_post_sarif, _ = _request_json(
            f"{base_url}/api/sarif",
            method="POST",
            data={"file": bad_file},
        )
        assert status_post_sarif in (400, 404)


def test_studio_nonexistent_routes_clean_404(studio_env: tuple[str, Path]) -> None:
    base_url, _ = studio_env

    nonexistent_routes = [
        ("GET", "/api/nonexistent"),
        ("POST", "/api/nonexistent"),
        ("GET", "/ghost_page"),
        ("POST", "/ghost_page"),
        ("POST", "/"),
        ("GET", "/api/check/subpath/not/found"),
        ("POST", "/api/suggest/extra"),
    ]
    for method, route in nonexistent_routes:
        req = urllib.request.Request(f"{base_url}{route}", method=method, data=b"{}" if method == "POST" else None)
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req)
        assert exc_info.value.code == 404


def test_studio_sarif_export_get_and_post(studio_env: tuple[str, Path]) -> None:
    base_url, _ = studio_env

    # 1. Test GET /api/sarif with specific target file
    req_get = urllib.request.Request(
        f"{base_url}/api/sarif?file=calc_target.py&seed=42&max_examples=5",
        method="GET",
    )
    with urllib.request.urlopen(req_get) as resp:
        assert resp.status == 200
        content_type = resp.headers.get("Content-Type", "")
        assert "application/json" in content_type
        content_disp = resp.headers.get("Content-Disposition", "")
        assert "attachment" in content_disp
        assert 'filename="ayentra-report.sarif"' in content_disp
        sarif_data = json.loads(resp.read().decode("utf-8"))

    assert sarif_data.get("$schema") == "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"
    assert sarif_data.get("version") == "2.1.0"
    assert "runs" in sarif_data and len(sarif_data["runs"]) == 1
    run = sarif_data["runs"][0]
    assert run["tool"]["driver"]["name"] == "Ayentra"
    assert len(run["results"]) >= 1
    first_res = run["results"][0]
    assert first_res["ruleId"] == "AYENTRA001"
    assert first_res["level"] == "error"

    # 2. Test POST /api/sarif with specific target file
    post_payload = json.dumps({"file": "calc_target.py", "seed": 42, "max_examples": 5}).encode("utf-8")
    req_post = urllib.request.Request(
        f"{base_url}/api/sarif",
        data=post_payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req_post) as resp_post:
        assert resp_post.status == 200
        assert "application/json" in resp_post.headers.get("Content-Type", "")
        assert 'filename="ayentra-report.sarif"' in resp_post.headers.get("Content-Disposition", "")
        sarif_post_data = json.loads(resp_post.read().decode("utf-8"))

    assert sarif_post_data.get("version") == "2.1.0"
    assert len(sarif_post_data["runs"][0]["results"]) >= 1

    # 3. Test GET /api/sarif workspace-wide (no file parameter)
    req_ws = urllib.request.Request(
        f"{base_url}/api/sarif?seed=42&max_examples=5",
        method="GET",
    )
    with urllib.request.urlopen(req_ws) as resp_ws:
        assert resp_ws.status == 200
        assert 'filename="ayentra-report.sarif"' in resp_ws.headers.get("Content-Disposition", "")
        sarif_ws = json.loads(resp_ws.read().decode("utf-8"))
    assert sarif_ws.get("version") == "2.1.0"

    # 4. Test nonexistent file error status (404)
    req_nonexistent = urllib.request.Request(f"{base_url}/api/sarif?file=nonexistent_file.py", method="GET")
    with pytest.raises(urllib.error.HTTPError) as exc_nonexistent:
        urllib.request.urlopen(req_nonexistent)
    assert exc_nonexistent.value.code == 404

    # 5. Test invalid parameter status (400)
    req_bad_param = urllib.request.Request(f"{base_url}/api/sarif?file=calc_target.py&seed=invalid_seed", method="GET")
    with pytest.raises(urllib.error.HTTPError) as exc_bad_param:
        urllib.request.urlopen(req_bad_param)
    assert exc_bad_param.value.code == 400


def test_studio_server_lifecycle_clean_shutdown(tmp_path: Path) -> None:
    dummy_target = tmp_path / "sample.py"
    dummy_target.write_text("def hello() -> str:\n    return 'world'\n", encoding="utf-8")

    server = create_studio_server(workspace_root=tmp_path, host="127.0.0.1", port=0)
    server_port = server.server_port
    assert server_port > 0

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    req = urllib.request.Request(f"http://127.0.0.1:{server_port}/api/targets", method="GET")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "targets" in data

    server.shutdown()
    server.server_close()
    thread.join(timeout=3.0)

    assert not thread.is_alive(), "Studio server thread did not terminate within timeout"

    with pytest.raises((urllib.error.URLError, ConnectionRefusedError, OSError)):
        req_after = urllib.request.Request(f"http://127.0.0.1:{server_port}/api/targets", method="GET")
        urllib.request.urlopen(req_after, timeout=0.5)



def test_studio_pilot_kit_endpoint(studio_env: tuple[str, Path]) -> None:
    base_url, _ = studio_env
    req = urllib.request.Request(f"{base_url}/api/pilot-kit", method="GET")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))

    assert data.get("onboarding_command") == "pip install ayentra && ayentra init --ci"
    assert data.get("sarif_version") == "2.1.0"
    assert data.get("workflow_path") == ".github/workflows/ayentra.yml"
    assert "checklist" in data and len(data["checklist"]) == 4


def test_studio_pr_mock_endpoint_get_and_post(studio_env: tuple[str, Path]) -> None:
    base_url, _ = studio_env

    # 1. GET /api/pr-mock with scenario
    status_get, data_get = _request_json(f"{base_url}/api/pr-mock?scenario=balance_leak&seed=42")
    assert status_get == 200
    assert data_get.get("status") == "success"
    assert "Ayentra PR Bot" in data_get.get("markdown", "")
    assert "lifecycle" in data_get

    # 2. POST /api/pr-mock with custom diff from balance leak fixture
    fixture_path = Path(__file__).resolve().parent.parent / "examples" / "fixtures" / "pr_diff_balance_leak.patch"
    sample_diff = fixture_path.read_text(encoding="utf-8")
    status_post, data_post = _request_json(
        f"{base_url}/api/pr-mock",
        method="POST",
        data={"scenario": "custom", "diff": sample_diff, "seed": 42},
    )
    assert status_post == 200
    assert data_post.get("status") == "success"
    assert "Financial balance leak" in data_post.get("markdown", "")

    # 3. Path traversal protection on file parameter
    req_bad = urllib.request.Request(f"{base_url}/api/pr-mock?file=../../outside.py", method="GET")
    with pytest.raises(urllib.error.HTTPError) as exc_bad:
        urllib.request.urlopen(req_bad)
    assert exc_bad.value.code in (400, 404)

    # 4. Invalid seed rejection
    req_seed = urllib.request.Request(f"{base_url}/api/pr-mock?seed=not_a_number", method="GET")
    with pytest.raises(urllib.error.HTTPError) as exc_seed:
        urllib.request.urlopen(req_seed)
    assert exc_seed.value.code == 400


def test_studio_unsupported_http_methods(studio_env: tuple[str, Path]) -> None:
    base_url, _ = studio_env

    # 1. Test PUT, DELETE, PATCH against /api/pr-mock
    for verb in ("PUT", "DELETE", "PATCH"):
        status, data = _request_json(f"{base_url}/api/pr-mock", method=verb, data={"dummy": True})
        assert status == 405
        assert data.get("error") == "Method Not Allowed"
        assert "allowed" in data

    # 2. Test PUT, DELETE, PATCH against /api/pilot-kit
    for verb in ("PUT", "DELETE", "PATCH"):
        status, data = _request_json(f"{base_url}/api/pilot-kit", method=verb, data={"dummy": True})
        assert status == 405
        assert data.get("error") == "Method Not Allowed"

    # 3. Test POST against /api/pilot-kit succeeds
    status_post, data_post = _request_json(f"{base_url}/api/pilot-kit", method="POST", data={})
    assert status_post == 200
    assert data_post.get("sarif_version") == "2.1.0"


def test_studio_fuzzing_payloads_oversized_and_base64_diff(studio_env: tuple[str, Path]) -> None:
    import base64
    base_url, _ = studio_env

    # 1. Corrupted non-JSON syntax body
    status_corrupt, data_corrupt = _request_raw(
        f"{base_url}/api/pr-mock",
        method="POST",
        raw_bytes=b"{invalid: syntax, broken...",
    )
    assert status_corrupt == 400
    assert "error" in data_corrupt

    # 2. Oversized payload (> 5MB)
    huge_bytes = b'{"diff": "' + (b"A" * (6 * 1024 * 1024)) + b'"}'
    status_oversized, data_oversized = _request_raw(
        f"{base_url}/api/pr-mock",
        method="POST",
        raw_bytes=huge_bytes,
    )
    assert status_oversized == 400
    assert "error" in data_oversized

    # 3. Malformed base64 diff payload
    status_bad_b64, data_bad_b64 = _request_json(
        f"{base_url}/api/pr-mock",
        method="POST",
        data={"scenario": "custom", "diff": "!!!not_valid_b64!!!", "encoding": "base64"},
    )
    assert status_bad_b64 == 400
    assert "Malformed base64 diff payload" in data_bad_b64.get("error", "")

    # 4. Valid base64 encoded diff payload
    raw_diff = (
        "diff --git a/wallet.py b/wallet.py\n"
        "--- a/wallet.py\n"
        "+++ b/wallet.py\n"
        "@@ -5,3 +5,2 @@\n"
        "     self.balance -= amount\n"
        "-    dest.balance += amount\n"
    )
    encoded_b64 = base64.b64encode(raw_diff.encode("utf-8")).decode("ascii")
    status_valid_b64, data_valid_b64 = _request_json(
        f"{base_url}/api/pr-mock",
        method="POST",
        data={"scenario": "custom", "diff": encoded_b64, "encoding": "base64"},
    )
    assert status_valid_b64 == 200
    assert data_valid_b64.get("status") == "success"
    assert "Financial balance leak" in data_valid_b64.get("markdown", "")

    # 5. Unicode diff payload (emojis, unicode code comments)
    unicode_diff = (
        "diff --git a/services.py b/services.py\n"
        "--- a/services.py\n"
        "+++ b/services.py\n"
        "@@ -1,2 +1,3 @@\n"
        "+# Unicode note: 🚀 check invariant and boundary safety\n"
        " def check():\n"
    )
    status_uni, data_uni = _request_json(
        f"{base_url}/api/pr-mock",
        method="POST",
        data={"scenario": "custom", "diff": unicode_diff},
    )
    assert status_uni == 200
    assert data_uni.get("status") == "success"


def test_studio_concurrent_stress_and_socket_cleanup(studio_env: tuple[str, Path]) -> None:
    from concurrent.futures import ThreadPoolExecutor
    import time
    base_url, _ = studio_env

    endpoints = [
        f"{base_url}/api/pilot-kit",
        f"{base_url}/api/pr-mock?scenario=balance_leak&seed=42",
        f"{base_url}/api/pr-mock?scenario=concurrency&seed=42",
        f"{base_url}/api/targets",
    ]

    def hit_endpoint(url: str) -> int:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read()
            assert len(data) > 0
            return resp.status

    start_time = time.perf_counter()
    tasks = endpoints * 6  # 24 rapid requests
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(hit_endpoint, tasks))

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    assert all(code == 200 for code in results)
    assert len(results) == 24
    assert elapsed_ms < 5000.0


def test_studio_dogfood_endpoint_structure_and_metrics(studio_env: tuple[str, Path]) -> None:
    base_url, _ = studio_env
    req = urllib.request.Request(f"{base_url}/api/dogfood", method="GET")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        assert "application/json" in resp.headers.get("Content-Type", "")
        data = json.loads(resp.read().decode("utf-8"))

    # Verify root fields
    for field in ("total_patterns_scanned", "total_cases_evaluated", "violations_found", "verified_fixes_count", "duration_ms", "findings"):
        assert field in data, f"Missing {field} in /api/dogfood response"

    assert data["total_patterns_scanned"] == 7
    assert data["total_cases_evaluated"] >= 100
    assert data["violations_found"] == 7
    assert data["verified_fixes_count"] == 7
    assert len(data["findings"]) == 7

    # Verify structured fields in findings
    first_finding = data["findings"][0]
    for key in ("pattern_name", "filepath", "plain_english_bug", "business_risk", "cases_evaluated", "fix_status", "unified_diff", "repro_command", "one_click_fix_command"):
        assert key in first_finding, f"Missing {key} in dogfood finding"

    assert first_finding["fix_status"] == "VERIFIED CANDIDATE FIX"
    assert "diff --git" in first_finding["unified_diff"] or "@@" in first_finding["unified_diff"]


def test_studio_dogfood_endpoint_pattern_filtering_and_summary(studio_env: tuple[str, Path]) -> None:
    base_url, _ = studio_env

    # 1. Filter by specific pattern: redis_token_bucket
    status_redis, data_redis = _request_json(f"{base_url}/api/dogfood?pattern=redis_token_bucket")
    assert status_redis == 200
    assert data_redis["total_patterns_scanned"] == 1
    assert data_redis["violations_found"] == 1
    assert len(data_redis["findings"]) == 1
    assert data_redis["findings"][0]["pattern_name"] == "redis_token_bucket"
    assert "Rate limiter bypass" in data_redis["findings"][0]["business_risk"]

    # 2. Filter by customer_pilot
    status_pilot, data_pilot = _request_json(f"{base_url}/api/dogfood?pattern=customer_pilot")
    assert status_pilot == 200
    assert data_pilot["total_patterns_scanned"] == 1
    assert data_pilot["findings"][0]["pattern_name"] == "customer_pilot"

    # 3. Request summary_only
    status_sum, data_sum = _request_json(f"{base_url}/api/dogfood?summary_only=true")
    assert status_sum == 200
    assert data_sum.get("summary_only") is True
    assert len(data_sum.get("findings", [])) == 0
    assert data_sum["total_patterns_scanned"] == 7
    assert data_sum["violations_found"] == 7

    # 4. Pattern + summary_only combo
    status_combo, data_combo = _request_json(f"{base_url}/api/dogfood?pattern=celery_task_queue&summary_only=1")
    assert status_combo == 200
    assert data_combo.get("summary_only") is True
    assert data_combo["total_patterns_scanned"] == 1
    assert len(data_combo.get("findings", [])) == 0

    # 5. Nonexistent pattern
    status_none, data_none = _request_json(f"{base_url}/api/dogfood?pattern=nonexistent_pattern_xyz")
    assert status_none == 200
    assert data_none["total_patterns_scanned"] == 0
    assert len(data_none.get("findings", [])) == 0

def test_studio_security_headers_and_origin_validation(studio_env: tuple[str, Path]) -> None:
    base_url, tmp_path = studio_env

    # 1. Verify defensive response headers on GET
    req = urllib.request.Request(f"{base_url}/")
    with urllib.request.urlopen(req) as resp:
        headers = dict(resp.headers)
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("X-Frame-Options") == "DENY"

    # 2. Verify Host header validation rejects external / rebinding hosts
    bad_host_req = urllib.request.Request(
        f"{base_url}/api/status",
        headers={"Host": "attacker-dns-rebind.com:8420"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc_host:
        urllib.request.urlopen(bad_host_req)
    assert exc_host.value.code == 403
    host_body = json.loads(exc_host.value.read().decode("utf-8"))
    assert "Invalid Host header" in host_body.get("error", "")

    # 3. Verify Cross-Origin POST rejection
    post_payload = json.dumps({"file": "calc_target.py", "seed": 42, "max_examples": 5}).encode("utf-8")
    evil_req = urllib.request.Request(
        f"{base_url}/api/check",
        data=post_payload,
        headers={"Content-Type": "application/json", "Origin": "https://evil-attacker.com"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(evil_req)
    assert exc_info.value.code == 403
    resp_body = json.loads(exc_info.value.read().decode("utf-8"))
    assert "Cross-origin POST forbidden" in resp_body.get("error", "")

    # 4. Verify Localhost Origin POST allowed
    local_req = urllib.request.Request(
        f"{base_url}/api/check",
        data=post_payload,
        headers={"Content-Type": "application/json", "Origin": "http://127.0.0.1:8420"},
        method="POST",
    )
    with urllib.request.urlopen(local_req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "violations" in data

    # 5. Verify max_examples clamping when excessively large
    clamp_req = urllib.request.Request(
        f"{base_url}/api/check?file=calc_target.py&seed=42&max_examples=999999",
        method="GET",
    )
    with urllib.request.urlopen(clamp_req) as resp:
        assert resp.status == 200


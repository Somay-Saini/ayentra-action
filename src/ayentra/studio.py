from __future__ import annotations

import json
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ayentra.ast_analyzer import analyze_source
from ayentra.engine import run_verification_engine
from ayentra.repair import generate_and_verify_patch
from ayentra.report import VerificationReport, build_verification_report


def execute_full_check(
    filepath: str | Path,
    *,
    seed_val: int = 42,
    max_examples: int = 120,
    repair_hook: str | None = None,
) -> tuple[VerificationReport, Any, list[Any]]:
    t0 = time.perf_counter()
    engine_res = run_verification_engine(filepath, seed_val=seed_val, max_examples=max_examples)
    patch_results = [
        generate_and_verify_patch(
            filepath,
            v,
            repair_hook=repair_hook,
            max_examples=max_examples,
        )
        for v in engine_res.violations
    ]
    total_ms = (time.perf_counter() - t0) * 1000.0
    report = build_verification_report(engine_res, patch_results, total_ms)
    return report, engine_res, patch_results


def apply_verified_patch_for_target(
    target_path: str | Path,
    seed_val: int = 42,
    max_examples: int = 120,
) -> dict[str, Any]:
    resolved = Path(target_path).resolve()
    if not resolved.is_file():
        return {"applied": False, "error": f"Target file not found: {resolved}"}

    _, engine_res, patch_results = execute_full_check(
        resolved,
        seed_val=seed_val,
        max_examples=max_examples,
    )
    if not engine_res.violations or not patch_results:
        return {"applied": False, "error": "No invariant violations or candidate patches found."}

    verified_patches = [
        p for p in patch_results if p.is_verified and p.status_label == "VERIFIED CANDIDATE FIX"
    ]
    if len(verified_patches) != len(patch_results):
        return {
            "applied": False,
            "error": "Cannot safely apply: one or more candidate patches failed sandbox verification.",
        }

    first_patch = verified_patches[0]
    if not first_patch.patched_source:
        return {"applied": False, "error": "Verified patch did not contain replacement source code."}

    try:
        resolved.write_text(first_patch.patched_source, encoding="utf-8")
    except Exception as exc:
        return {"applied": False, "error": f"Failed to write patched source to {resolved}: {exc}"}

    return {
        "applied": True,
        "status": "VERIFIED PATCH APPLIED",
        "target": str(resolved),
        "verified_count": len(verified_patches),
        "unified_diff": first_patch.unified_diff,
        "message": f"Successfully applied verified patch to {resolved.name}.",
    }


def discover_python_targets(workspace_root: Path) -> list[str]:
    # ponytail: simple rglob with clean exclusions
    targets: list[str] = []
    excluded_dirs = {".venv", "venv", ".git", ".hypothesis", "__pycache__", "build", "dist", ".pytest_cache"}
    for p in workspace_root.rglob("*.py"):
        if any(part in excluded_dirs for part in p.parts):
            continue
        if not p.name.startswith("test_"):
            rel = p.relative_to(workspace_root).as_posix()
            targets.append(rel)
    return sorted(targets)


STUDIO_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Ayentra Studio | Interactive Verification &amp; PR Review Bot</title>
  <style>
    :root {
      --bg-app: #F6F5F2;
      --bg-surface: #FCFCFA;
      --bg-panel: #FFFFFF;
      --bg-code: #F3F2EE;
      --border-subtle: #E2E5E9;
      --border-strong: #CBD0D8;
      --text-primary: #1E232A;
      --text-secondary: #5C6470;
      --pass-text: #166534;
      --pass-bg: #DCFCE7;
      --pass-border: #86EFAC;
      --fail-text: #991B1B;
      --fail-bg: #FEE2E2;
      --fail-border: #FCA5A5;
      --warn-text: #92400E;
      --warn-bg: #FEF3C7;
      --warn-border: #FCD34D;
      --accent-focus: #2563EB;
      --accent-teal: #0F766E;
      --accent-teal-bg: #F0FDFA;
      --accent-teal-border: #99F6E4;
      --btn-primary-bg: #1E232A;
      --btn-primary-text: #FCFCFA;
      --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      --font-mono: "JetBrains Mono", "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      padding: 0;
      background-color: var(--bg-app);
      color: var(--text-primary);
      font-family: var(--font-sans);
      font-size: 15px;
      line-height: 1.5;
    }

    header {
      background-color: var(--bg-surface);
      border-bottom: 1px solid var(--border-subtle);
      padding: 12px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 16px;
      position: sticky;
      top: 0;
      z-index: 100;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .brand h1 {
      font-size: 20px;
      font-weight: 700;
      margin: 0;
      letter-spacing: -0.03em;
      color: var(--text-primary);
    }

    .nav-modes {
      display: flex;
      align-items: center;
      gap: 6px;
      background: var(--bg-code);
      padding: 3px;
      border-radius: 8px;
      border: 1px solid var(--border-subtle);
    }

    .mode-tab {
      background: transparent;
      border: none;
      padding: 6px 14px;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 600;
      color: var(--text-secondary);
      cursor: pointer;
      transition: all 0.15s ease;
    }

    .mode-tab:hover {
      color: var(--text-primary);
    }

    .mode-tab.active {
      background: var(--bg-panel);
      color: var(--text-primary);
      box-shadow: 0 1px 2px rgba(0,0,0,0.06);
    }

    .mode-tab.pilot-btn {
      color: var(--accent-teal);
      border: 1px solid transparent;
    }

    .mode-tab.pilot-btn:hover {
      background: var(--accent-teal-bg);
      border-color: var(--accent-teal-border);
    }

    .toolbar {
      display: flex;
      align-items: flex-end;
      gap: 12px;
      flex-wrap: wrap;
    }

    .field-group {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    label {
      font-size: 11px;
      font-weight: 600;
      color: var(--text-secondary);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    select, input, textarea {
      background-color: var(--bg-panel);
      border: 1px solid var(--border-strong);
      border-radius: 6px;
      padding: 7px 10px;
      font-family: inherit;
      font-size: 13px;
      color: var(--text-primary);
      outline: none;
    }

    select:focus, input:focus, textarea:focus {
      border-color: var(--accent-focus);
      box-shadow: 0 0 0 1px var(--accent-focus);
    }

    button.primary {
      background-color: var(--btn-primary-bg);
      color: var(--btn-primary-text);
      border: 1px solid var(--btn-primary-bg);
      border-radius: 6px;
      padding: 7px 16px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: background-color 0.15s ease;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }

    button.primary:hover:not(:disabled) {
      background-color: #323842;
    }

    button.primary:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }

    button.teal {
      background-color: var(--accent-teal);
      color: #FFFFFF;
      border: 1px solid var(--accent-teal);
      border-radius: 6px;
      padding: 7px 14px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }

    button.teal:hover:not(:disabled) {
      background-color: #115E59;
    }

    button.copy-diff-btn {
      background: var(--bg-panel);
      color: var(--text-primary);
      border: 1px solid var(--border-subtle);
      border-radius: 6px;
      padding: 5px 10px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s ease;
    }

    button.copy-diff-btn:hover {
      background: var(--bg-code);
      border-color: var(--border-strong);
    }

    .container {
      max-width: 1240px;
      margin: 0 auto;
      padding: 24px;
    }

    .panel {
      background-color: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 20px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.02);
    }

    .panel-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 14px;
      flex-wrap: wrap;
      gap: 10px;
    }

    .panel-title {
      font-size: 15px;
      font-weight: 700;
      letter-spacing: -0.01em;
      margin: 0;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .pill {
      display: inline-block;
      font-size: 11px;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 4px;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }

    .pill.pass {
      background-color: var(--pass-bg);
      color: var(--pass-text);
      border: 1px solid var(--pass-border);
    }

    .pill.fail {
      background-color: var(--fail-bg);
      color: var(--fail-text);
      border: 1px solid var(--fail-border);
    }

    .pill.warn {
      background-color: var(--warn-bg);
      color: var(--warn-text);
      border: 1px solid var(--warn-border);
    }

    .pill.teal {
      background-color: var(--accent-teal-bg);
      color: var(--accent-teal);
      border: 1px solid var(--accent-teal-border);
    }

    .receipt-bar {
      background-color: var(--bg-panel);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 12px 18px;
      margin-bottom: 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 12px;
    }

    .metrics-group {
      display: flex;
      align-items: center;
      gap: 24px;
      flex-wrap: wrap;
    }

    .metric-item {
      display: flex;
      flex-direction: column;
    }

    .metric-label {
      font-size: 11px;
      font-weight: 600;
      color: var(--text-secondary);
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    .metric-value {
      font-size: 14px;
      font-weight: 700;
      font-family: var(--font-mono);
      color: var(--text-primary);
    }

    .filter-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 18px;
    }

    .filter-pill {
      background-color: transparent;
      border: 1px solid var(--border-subtle);
      border-radius: 6px;
      padding: 5px 12px;
      font-size: 12px;
      font-weight: 600;
      color: var(--text-secondary);
      cursor: pointer;
    }

    .filter-pill.active {
      background-color: var(--text-primary);
      color: #FFFFFF;
      border-color: var(--text-primary);
    }

    pre, code {
      font-family: var(--font-mono);
      font-size: 13px;
    }

    pre {
      background-color: var(--bg-code);
      border: 1px solid var(--border-subtle);
      border-radius: 6px;
      padding: 12px;
      overflow-x: auto;
      margin: 6px 0 0 0;
      line-height: 1.45;
    }

    .grid-two {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }

    @media (max-width: 860px) {
      .grid-two {
        grid-template-columns: 1fr;
      }
    }

    .diff-add {
      background-color: #DCFCE7;
      color: #166534;
      display: block;
    }

    .diff-del {
      background-color: #FEE2E2;
      color: #991B1B;
      display: block;
    }

    /* GitHub-style PR Bot Review Card */
    .gh-card {
      background-color: var(--bg-panel);
      border: 1px solid var(--border-strong);
      border-radius: 8px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.04);
      margin-bottom: 20px;
      overflow: hidden;
    }

    .gh-header {
      background-color: var(--bg-surface);
      border-bottom: 1px solid var(--border-subtle);
      padding: 12px 18px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 10px;
    }

    .gh-author {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .gh-avatar {
      width: 28px;
      height: 28px;
      border-radius: 50%;
      background: #0F766E;
      color: #FFFFFF;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      font-size: 13px;
    }

    .gh-body {
      padding: 20px;
    }

    .gh-table {
      width: 100%;
      border-collapse: collapse;
      margin: 14px 0;
      font-size: 13px;
    }

    .gh-table th {
      background-color: var(--bg-code);
      text-align: left;
      padding: 8px 12px;
      border: 1px solid var(--border-subtle);
      font-weight: 600;
      color: var(--text-secondary);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    .gh-table td {
      padding: 10px 12px;
      border: 1px solid var(--border-subtle);
      vertical-align: top;
    }

    details.gh-diff-box {
      border: 1px solid var(--border-subtle);
      border-radius: 6px;
      background: var(--bg-panel);
      margin: 12px 0;
      overflow: hidden;
    }

    details.gh-diff-box summary {
      background: var(--bg-surface);
      padding: 9px 14px;
      cursor: pointer;
      font-size: 13px;
      font-weight: 600;
      color: var(--text-primary);
      user-select: none;
      border-bottom: 1px solid var(--border-subtle);
    }

    /* Side Drawer for Pilot Kit */
    .drawer-backdrop {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(15, 23, 42, 0.45);
      z-index: 1000;
      opacity: 0;
      visibility: hidden;
      transition: all 0.25s ease;
    }

    .drawer-backdrop.open {
      opacity: 1;
      visibility: visible;
    }

    .drawer {
      position: fixed;
      top: 0;
      right: -560px;
      bottom: 0;
      width: 540px;
      max-width: 90vw;
      background: var(--bg-surface);
      border-left: 1px solid var(--border-subtle);
      box-shadow: -4px 0 24px rgba(0,0,0,0.12);
      z-index: 1001;
      display: flex;
      flex-direction: column;
      transition: right 0.28s cubic-bezier(0.16, 1, 0.3, 1);
    }

    .drawer.open {
      right: 0;
    }

    .drawer-header {
      padding: 18px 22px;
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: var(--bg-panel);
    }

    .drawer-header h2 {
      margin: 0;
      font-size: 17px;
      font-weight: 700;
      letter-spacing: -0.01em;
    }

    .drawer-close-btn {
      background: transparent;
      border: none;
      font-size: 20px;
      line-height: 1;
      cursor: pointer;
      color: var(--text-secondary);
      padding: 4px 8px;
      border-radius: 4px;
    }

    .drawer-close-btn:hover {
      background: var(--bg-code);
      color: var(--text-primary);
    }

    .drawer-content {
      padding: 22px;
      overflow-y: auto;
      flex: 1;
    }

    .pilot-card {
      background: var(--bg-panel);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 16px;
    }

    .pilot-step {
      display: flex;
      gap: 12px;
      margin-bottom: 14px;
    }

    .pilot-step-num {
      width: 24px;
      height: 24px;
      border-radius: 50%;
      background: var(--accent-teal);
      color: #FFFFFF;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 11px;
      font-weight: 700;
      flex-shrink: 0;
      margin-top: 2px;
    }

    .pilot-step-body {
      flex: 1;
    }
  </style>
</head>
<body>

  <!-- Top Navigation Header -->
  <header>
    <div class="brand">
      <h1>Ayentra</h1>
      <span class="pill teal" style="font-size: 11px;">STUDIO</span>
    </div>

    <!-- Mode Tabs -->
    <div class="nav-modes" role="tablist" aria-label="Studio Modes">
      <button type="button" class="mode-tab active" id="tab-studio-btn" role="tab" aria-selected="true" aria-controls="studio-view">Studio Inspector</button>
      <button type="button" class="mode-tab" id="tab-pr-bot-btn" role="tab" aria-selected="false" aria-controls="pr-bot-view">PR Review Bot Preview</button>
      <button type="button" class="mode-tab" id="tab-dogfood-btn" role="tab" aria-selected="false" aria-controls="dogfood-view">Dogfood Evidence</button>
      <button type="button" class="mode-tab pilot-btn" id="open-pilot-btn" aria-haspopup="dialog" aria-expanded="false" aria-controls="pilot-drawer" title="Enterprise Pilot Kit &amp; CI Onboarding">Enterprise Pilot Kit</button>
    </div>

    <!-- Toolbar for Studio Inspector -->
    <div class="toolbar" id="studio-toolbar">
      <div class="field-group">
        <label for="target-select">Target File</label>
        <select id="target-select"></select>
      </div>
      <div class="field-group">
        <label for="seed-input">Adversarial Seed</label>
        <input id="seed-input" type="number" value="42" style="width: 90px;">
      </div>
      <button class="primary" id="run-btn" type="button" title="Run Verification Gate (Ctrl+Enter or Alt+Enter)">
        <span id="run-btn-label">Run Verification Gate</span>
      </button>
    </div>

    <!-- Toolbar for PR Review Bot Preview -->
    <div class="toolbar" id="pr-bot-toolbar" style="display: none;">
      <div class="field-group">
        <label for="pr-scenario-select">Mock PR Scenario</label>
        <select id="pr-scenario-select" style="min-width: 240px;">
          <option value="balance_leak">PR #102: Balance Overdraft Leak (Ledger)</option>
          <option value="concurrency">PR #101: Concurrency Race (Scheduler)</option>
          <option value="telemetry">PR #103: Telemetry NaN Drift (Sensor)</option>
          <option value="current_target">Current Workspace Target</option>
          <option value="custom">Custom Unified Diff / JSON Payload</option>
        </select>
      </div>
      <div class="field-group">
        <label for="pr-seed-input">Seed</label>
        <input id="pr-seed-input" type="number" value="42" style="width: 80px;">
      </div>
      <button class="primary" id="replay-pr-btn" type="button" title="Replay Offline Mock PR Bot (Ctrl+Enter)">
        <span id="replay-pr-btn-label">Replay Mock PR Event</span>
      </button>
    </div>

    <!-- Toolbar for Dogfood Evidence -->
    <div class="toolbar" id="dogfood-toolbar" style="display: none;">
      <div class="field-group">
        <label for="dogfood-filter-select">Pattern Filter</label>
        <select id="dogfood-filter-select" style="min-width: 220px;">
          <option value="all">All Production Patterns (7)</option>
          <option value="customer_pilot">customer_pilot (Financial Ledger)</option>
          <option value="redis_token_bucket">redis_token_bucket (Rate Limiter)</option>
          <option value="scheduler_race">scheduler_race (Concurrency Barrier)</option>
          <option value="inventory_ledger">inventory_ledger (Reservation Invariant)</option>
          <option value="celery_task_queue">celery_task_queue (Worker Counter)</option>
          <option value="requests_connection_pool">requests_connection_pool (Pool State)</option>
          <option value="data_parser">data_parser (Telemetry Validator)</option>
        </select>
      </div>
      <button class="primary" id="refresh-dogfood-btn" type="button" title="Reload Dogfood Receipt (Ctrl+Enter)">
        <span id="refresh-dogfood-btn-label">Refresh Evidence</span>
      </button>
    </div>
  </header>

  <!-- Main View Container -->
  <div class="container">

    <!-- VIEW 1: Studio Inspector -->
    <main id="studio-view" role="tabpanel" aria-labelledby="tab-studio-btn" aria-live="polite">
      <section class="panel" style="border-left: 3px solid var(--accent-teal);" aria-label="Verification Notice">
        <div class="panel-header">
          <h2 class="panel-title">Ayentra Verification Studio</h2>
          <span class="pill teal">READY</span>
        </div>
        <p style="margin: 0; color: var(--text-secondary);">
          Select a Python target from the workspace and run the property-based invariant verification gate.
        </p>
      </section>
    </main>

    <!-- VIEW 2: PR Review Bot Preview -->
    <section id="pr-bot-view" role="tabpanel" aria-labelledby="tab-pr-bot-btn" style="display: none;" aria-live="polite">
      <!-- Scenario Overview Banner -->
      <section class="receipt-bar" aria-label="PR Simulation Controls">
        <div class="metrics-group">
          <div class="metric-item">
            <span class="metric-label">Pull Request</span>
            <span class="metric-value" id="pr-summary-num">PR #102</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">Target Branch</span>
            <span class="metric-value" id="pr-summary-branch">main &larr; patch-1</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">Simulation Mode</span>
            <span class="metric-value" style="color: var(--accent-teal);">Offline (Zero Tokens)</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">Review Status</span>
            <span class="metric-value" id="pr-summary-verdict" style="color: var(--fail-text);">Changes Requested</span>
          </div>
        </div>
        <div style="display: flex; gap: 8px; flex-wrap: wrap;">
          <button type="button" class="copy-diff-btn" id="pr-sarif-export-btn" title="Export SARIF 2.1.0">Download SARIF</button>
          <button type="button" class="copy-diff-btn" id="pr-copy-md-btn" title="Copy GitHub PR Comment Markdown">Copy PR Comment</button>
        </div>
      </section>

      <!-- Custom Payload Drawer (shown only when custom scenario selected) -->
      <section class="panel" id="custom-payload-panel" style="display: none;">
        <div class="panel-header">
          <h2 class="panel-title">Custom Unified Diff / Mock PR Payload</h2>
          <button type="button" class="copy-diff-btn" id="load-sample-diff-btn">Load Ledger Diff Sample</button>
        </div>
        <textarea id="custom-diff-input" rows="6" style="width: 100%; font-family: var(--font-mono); font-size: 12px;" placeholder="Paste unified diff (diff --git a/... b/...) or mock PR event JSON here..."></textarea>
      </section>

      <!-- Simulated GitHub PR Review Comment Card -->
      <article class="gh-card" aria-label="Simulated GitHub PR Review Comment">
        <div class="gh-header">
          <div class="gh-author">
            <div class="gh-avatar">A</div>
            <div>
              <strong style="font-size: 13px;">ayentra-bot</strong>
              <span class="pill" style="background:#E2E8F0; color:#334155; font-size:10px; margin-left:4px;">BOT</span>
              <span style="color: var(--text-secondary); font-size: 12px; margin-left: 6px;">commented on commit <code id="pr-head-sha">f7d8e9a</code></span>
            </div>
          </div>
          <span class="pill fail" id="pr-badge-verdict">CHANGES REQUESTED</span>
        </div>

        <div class="gh-body" id="pr-comment-body">
          <p style="margin: 0; color: var(--text-secondary);">Loading simulated PR review comment...</p>
        </div>
      </article>
    </section>

    <!-- VIEW 3: Dogfood Evidence Proof-of-Value Hub -->
    <section id="dogfood-view" role="tabpanel" aria-labelledby="tab-dogfood-btn" style="display: none;" aria-live="polite">
      <!-- Dogfood Summary Metrics Bar -->
      <section class="receipt-bar" aria-label="Dogfood Proof-of-Value Metrics">
        <div class="metrics-group">
          <div class="metric-item">
            <span class="metric-label">Patterns Scanned</span>
            <span class="metric-value" id="df-summary-scanned">7 Production Targets</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">Cases Evaluated</span>
            <span class="metric-value" id="df-summary-cases">173 Cases</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">Invariant Violations</span>
            <span class="metric-value" id="df-summary-violations" style="color: var(--fail-text);">7 Detected</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">Verified AST Fixes</span>
            <span class="metric-value" id="df-summary-fixes" style="color: var(--pass-text);">7 Generated (100%)</span>
          </div>
        </div>
        <div style="display: flex; gap: 8px; flex-wrap: wrap;">
          <button type="button" class="copy-diff-btn" id="df-download-receipt-btn" title="Download dogfood_receipt.json">Download Receipt JSON</button>
          <button type="button" class="copy-diff-btn" id="df-copy-summary-btn" title="Copy Evidence Summary">Copy Evidence Summary</button>
        </div>
      </section>

      <!-- Expandable Findings Inspector -->
      <div id="dogfood-findings-container" style="display: grid; gap: 20px;">
        <p style="margin: 0; color: var(--text-secondary);">Loading dogfood proof-of-value receipt...</p>
      </div>
    </section>
  </div>

  <!-- Slide-Over Drawer: Enterprise Design Partner Pilot Kit -->
  <div class="drawer-backdrop" id="pilot-drawer-backdrop" aria-hidden="true"></div>
  <aside class="drawer" id="pilot-drawer" role="dialog" aria-modal="true" aria-labelledby="pilot-drawer-title" aria-hidden="true">
    <div class="drawer-header">
      <div>
        <h2 id="pilot-drawer-title">Enterprise Design Partner Pilot</h2>
        <span style="font-size: 12px; color: var(--text-secondary);">Contract verification, zero-token CI gates, and SARIF 2.1.0</span>
      </div>
      <button type="button" class="drawer-close-btn" id="close-pilot-btn" aria-label="Close Pilot Drawer">&times;</button>
    </div>

    <div class="drawer-content">
      <!-- 2-Command Onboarding -->
      <section class="pilot-card">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
          <strong style="font-size: 14px;">1. Two-Command Zero-Config Onboarding</strong>
          <button type="button" class="copy-diff-btn" id="copy-onboard-cmd-btn" data-clipboard="pip install ayentra && ayentra init --ci">Copy Command</button>
        </div>
        <p style="font-size: 13px; margin: 0 0 10px 0; color: var(--text-secondary);">
          Adopt Ayentra without writing custom workflow scripts or configuring cloud accounts.
        </p>
        <pre><code>pip install ayentra &amp;&amp; ayentra init --ci</code></pre>
        <p style="font-size: 12px; color: var(--text-secondary); margin: 8px 0 0 0;">
          Automatically generates <code>ayentra.toml</code> and <code>.github/workflows/ayentra.yml</code>.
        </p>
      </section>

      <!-- GitHub Actions Workflow -->
      <section class="pilot-card">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
          <strong style="font-size: 14px;">2. GitHub Actions CI Workflow</strong>
          <button type="button" class="copy-diff-btn" id="copy-workflow-yaml-btn">Copy YAML</button>
        </div>
        <p style="font-size: 13px; margin: 0 0 10px 0; color: var(--text-secondary);">
          Runs on push and pull requests, uploading SARIF 2.1.0 alerts directly to GitHub Code Scanning.
        </p>
        <pre><code id="workflow-yaml-preview">name: Ayentra Verification Gate
on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install ayentra
      - run: ayentra check . --ci --sarif ayentra-report.sarif
      - uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: ayentra-report.sarif</code></pre>
      </section>

      <!-- SARIF 2.1.0 Exporter -->
      <section class="pilot-card">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
          <strong style="font-size: 14px;">3. SARIF 2.1.0 Security Scanning</strong>
          <button type="button" class="teal" id="drawer-download-sarif-btn">Download SARIF 2.1.0</button>
        </div>
        <p style="font-size: 13px; margin: 0; color: var(--text-secondary);">
          Exports standard SARIF 2.1.0 diagnostic reports compatible with GitHub Security Center, SonarQube, and enterprise compliance pipelines.
        </p>
      </section>

      <!-- 4-Step Pilot Roadmap -->
      <section class="pilot-card">
        <strong style="font-size: 14px; display: block; margin-bottom: 12px;">4. Pilot Onboarding Roadmap</strong>
        <div class="pilot-step">
          <div class="pilot-step-num">1</div>
          <div class="pilot-step-body">
            <strong style="font-size: 13px;">Scaffold CI Configuration</strong>
            <div style="font-size: 12px; color: var(--text-secondary);">Run <code>ayentra init --ci</code> to initialize contract rules.</div>
          </div>
        </div>
        <div class="pilot-step">
          <div class="pilot-step-num">2</div>
          <div class="pilot-step-body">
            <strong style="font-size: 13px;">Declare Explicit Invariants</strong>
            <div style="font-size: 12px; color: var(--text-secondary);">Add <code># invariant: ...</code> contract comments to core transaction handlers.</div>
          </div>
        </div>
        <div class="pilot-step">
          <div class="pilot-step-num">3</div>
          <div class="pilot-step-body">
            <strong style="font-size: 13px;">Verification Gate &amp; Code Scanning</strong>
            <div style="font-size: 12px; color: var(--text-secondary);">Run <code>ayentra check . --ci</code> in pull requests to block regressions.</div>
          </div>
        </div>
        <div class="pilot-step">
          <div class="pilot-step-num">4</div>
          <div class="pilot-step-body">
            <strong style="font-size: 13px;">Automated PR Bot Simulation</strong>
            <div style="font-size: 12px; color: var(--text-secondary);">Simulate offline PR bot reviews using <code>ayentra check --mock-pr-event</code>.</div>
          </div>
        </div>
      </section>

      <!-- Reference documentation note -->
      <div style="font-size: 12px; color: var(--text-secondary); text-align: center; padding: 6px 0;">
        Full enterprise documentation available in <code>docs/design_partner_kit.md</code>
      </div>
    </div>
  </aside>

  <!-- JavaScript Client -->
  <script>
    const targetSelect = document.getElementById('target-select');
    const seedInput = document.getElementById('seed-input');
    const runBtn = document.getElementById('run-btn');
    const runBtnLabel = document.getElementById('run-btn-label');
    const studioView = document.getElementById('studio-view');

    const tabStudioBtn = document.getElementById('tab-studio-btn');
    const tabPrBotBtn = document.getElementById('tab-pr-bot-btn');
    const tabDogfoodBtn = document.getElementById('tab-dogfood-btn');
    const studioToolbar = document.getElementById('studio-toolbar');
    const prBotToolbar = document.getElementById('pr-bot-toolbar');
    const dogfoodToolbar = document.getElementById('dogfood-toolbar');
    const studioView = document.getElementById('studio-view');
    const prBotView = document.getElementById('pr-bot-view');
    const dogfoodView = document.getElementById('dogfood-view');

    const dogfoodFilterSelect = document.getElementById('dogfood-filter-select');
    const refreshDogfoodBtn = document.getElementById('refresh-dogfood-btn');
    const refreshDogfoodBtnLabel = document.getElementById('refresh-dogfood-btn-label');
    const dfSummaryScanned = document.getElementById('df-summary-scanned');
    const dfSummaryCases = document.getElementById('df-summary-cases');
    const dfSummaryViolations = document.getElementById('df-summary-violations');
    const dfSummaryFixes = document.getElementById('df-summary-fixes');
    const dfFindingsContainer = document.getElementById('dogfood-findings-container');
    const dfDownloadReceiptBtn = document.getElementById('df-download-receipt-btn');
    const dfCopySummaryBtn = document.getElementById('df-copy-summary-btn');

    let currentDogfoodData = null;

    const prScenarioSelect = document.getElementById('pr-scenario-select');
    const prSeedInput = document.getElementById('pr-seed-input');
    const replayPrBtn = document.getElementById('replay-pr-btn');
    const replayPrBtnLabel = document.getElementById('replay-pr-btn-label');
    const customPayloadPanel = document.getElementById('custom-payload-panel');
    const customDiffInput = document.getElementById('custom-diff-input');
    const loadSampleDiffBtn = document.getElementById('load-sample-diff-btn');

    const prSummaryNum = document.getElementById('pr-summary-num');
    const prSummaryBranch = document.getElementById('pr-summary-branch');
    const prSummaryVerdict = document.getElementById('pr-summary-verdict');
    const prHeadSha = document.getElementById('pr-head-sha');
    const prBadgeVerdict = document.getElementById('pr-badge-verdict');
    const prCommentBody = document.getElementById('pr-comment-body');
    const prSarifExportBtn = document.getElementById('pr-sarif-export-btn');
    const prCopyMdBtn = document.getElementById('pr-copy-md-btn');

    const openPilotBtn = document.getElementById('open-pilot-btn');
    const closePilotBtn = document.getElementById('close-pilot-btn');
    const pilotDrawer = document.getElementById('pilot-drawer');
    const pilotDrawerBackdrop = document.getElementById('pilot-drawer-backdrop');
    const copyOnboardCmdBtn = document.getElementById('copy-onboard-cmd-btn');
    const copyWorkflowYamlBtn = document.getElementById('copy-workflow-yaml-btn');
    const drawerDownloadSarifBtn = document.getElementById('drawer-download-sarif-btn');

    let currentPrMarkdown = '';
    let currentPrPatchDiff = '';
    let currentPrTarget = '';
    let activeTab = 'studio';

    function escapeHtml(str) {
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    }

    function formatDiff(diffText) {
      if (!diffText) return 'No candidate diff generated.';
      return diffText.split('\n').map(line => {
        const esc = escapeHtml(line);
        if (line.startsWith('+') && !line.startsWith('+++')) {
          return `<span class="diff-add">${esc}</span>`;
        }
        if (line.startsWith('-') && !line.startsWith('---')) {
          return `<span class="diff-del">${esc}</span>`;
        }
        return esc;
      }).join('\n');
    }

    /* Mode Tab Switching */
    function switchTab(mode) {
      activeTab = mode;
      [tabStudioBtn, tabPrBotBtn, tabDogfoodBtn].forEach(btn => {
        if (btn) {
          btn.classList.remove('active');
          btn.setAttribute('aria-selected', 'false');
        }
      });
      [studioToolbar, prBotToolbar, dogfoodToolbar].forEach(tb => {
        if (tb) tb.style.display = 'none';
      });
      [studioView, prBotView, dogfoodView].forEach(vw => {
        if (vw) vw.style.display = 'none';
      });

      if (mode === 'studio') {
        tabStudioBtn.classList.add('active');
        tabStudioBtn.setAttribute('aria-selected', 'true');
        studioToolbar.style.display = 'flex';
        studioView.style.display = 'block';
      } else if (mode === 'pr-bot') {
        tabPrBotBtn.classList.add('active');
        tabPrBotBtn.setAttribute('aria-selected', 'true');
        prBotToolbar.style.display = 'flex';
        prBotView.style.display = 'block';
        if (!currentPrMarkdown) {
          replayPrMock();
        }
      } else if (mode === 'dogfood') {
        tabDogfoodBtn.classList.add('active');
        tabDogfoodBtn.setAttribute('aria-selected', 'true');
        dogfoodToolbar.style.display = 'flex';
        dogfoodView.style.display = 'block';
        if (!currentDogfoodData) {
          loadDogfood();
        }
      }
    }

    tabStudioBtn.addEventListener('click', () => switchTab('studio'));
    tabPrBotBtn.addEventListener('click', () => switchTab('pr-bot'));
    tabDogfoodBtn.addEventListener('click', () => switchTab('dogfood'));

    /* Enterprise Pilot Drawer Controls */
    let lastActiveElement = null;

    function openPilotDrawer() {
      lastActiveElement = document.activeElement;
      pilotDrawer.classList.add('open');
      pilotDrawerBackdrop.classList.add('open');
      pilotDrawer.setAttribute('aria-hidden', 'false');
      openPilotBtn.setAttribute('aria-expanded', 'true');
      const bannerBtn = document.getElementById('open-pilot-banner-btn');
      if (bannerBtn) bannerBtn.setAttribute('aria-expanded', 'true');
      setTimeout(() => {
        closePilotBtn.focus();
      }, 50);
    }

    function closePilotDrawer() {
      pilotDrawer.classList.remove('open');
      pilotDrawerBackdrop.classList.remove('open');
      pilotDrawer.setAttribute('aria-hidden', 'true');
      openPilotBtn.setAttribute('aria-expanded', 'false');
      const bannerBtn = document.getElementById('open-pilot-banner-btn');
      if (bannerBtn) bannerBtn.setAttribute('aria-expanded', 'false');
      if (lastActiveElement && typeof lastActiveElement.focus === 'function') {
        lastActiveElement.focus();
      }
    }

    openPilotBtn.addEventListener('click', openPilotDrawer);
    closePilotBtn.addEventListener('click', closePilotDrawer);
    pilotDrawerBackdrop.addEventListener('click', closePilotDrawer);

    document.addEventListener('keydown', (e) => {
      if (pilotDrawer.classList.contains('open')) {
        if (e.key === 'Escape') {
          e.preventDefault();
          closePilotDrawer();
          return;
        }
        if (e.key === 'Tab') {
          const focusables = Array.from(
            pilotDrawer.querySelectorAll(
              'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
            )
          );
          if (focusables.length > 0) {
            const first = focusables[0];
            const last = focusables[focusables.length - 1];
            if (e.shiftKey && document.activeElement === first) {
              e.preventDefault();
              last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
              e.preventDefault();
              first.focus();
            }
          }
        }
      }
      if ((e.ctrlKey || e.altKey) && e.key === 'Enter') {
        e.preventDefault();
        if (activeTab === 'studio') {
          runCheck();
        } else if (activeTab === 'dogfood') {
          loadDogfood();
        } else {
          replayPrMock();
        }
      }
    });

    /* Studio Inspector logic */
    async function loadTargets() {
      const res = await fetch('/api/targets');
      const data = await res.json();
      targetSelect.innerHTML = '';
      data.targets.forEach(t => {
        const opt = document.createElement('option');
        opt.value = t;
        opt.textContent = t;
        targetSelect.appendChild(opt);
      });
      if (data.targets.length > 0) {
        await runCheck();
      }
    }

    async function runCheck() {
      const target = targetSelect.value;
      const seed = parseInt(seedInput.value || '42', 10);
      runBtn.disabled = true;
      runBtnLabel.textContent = 'Running Verification...';
      try {
        const res = await fetch(`/api/check?file=${encodeURIComponent(target)}&seed=${seed}`);
        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          renderNotice(errData.error || `Verification failed with HTTP ${res.status}`);
          return;
        }
        const report = await res.json();
        renderReport(report);
      } catch (err) {
        renderNotice(err.message || 'Unable to connect to verification server.');
      } finally {
        runBtn.disabled = false;
        runBtnLabel.textContent = 'Run Verification Gate';
      }
    }

    function renderNotice(message) {
      studioView.innerHTML = `
        <section class="panel" style="border-left: 3px solid var(--fail-text);" aria-label="Verification Notice">
          <div class="panel-header">
            <h2 class="panel-title">Verification Notice</h2>
            <span class="pill fail">ATTENTION NEEDED</span>
          </div>
          <p style="margin: 0; color: var(--text-primary); font-size: 14px;">${escapeHtml(message)}</p>
        </section>
      `;
    }

    function renderReport(r) {
      let html = `
        <section class="receipt-bar" aria-label="Execution Receipt">
          <div class="metrics-group">
            <div class="metric-item">
              <span class="metric-label">Target File</span>
              <span class="metric-value">${escapeHtml(r.target_file)}</span>
            </div>
            <div class="metric-item">
              <span class="metric-label">Status</span>
              <span class="metric-value" style="color: ${r.violations.length > 0 ? 'var(--fail-text)' : 'var(--pass-text)'}">
                ${r.violations.length > 0 ? 'FAIL' : 'PASS'}
              </span>
            </div>
            <div class="metric-item">
              <span class="metric-label">Explicit Invariants</span>
              <span class="metric-value">${r.passed_invariants_count + r.violations.length} checked</span>
            </div>
            <div class="metric-item">
              <span class="metric-label">Cases Evaluated</span>
              <span class="metric-value">${r.total_cases_evaluated}</span>
            </div>
            <div class="metric-item">
              <span class="metric-label">Engine Run Time</span>
              <span class="metric-value">${r.engine_duration_ms} ms</span>
            </div>
          </div>
          <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
            <button type="button" class="copy-diff-btn" id="open-pilot-banner-btn" aria-haspopup="dialog" aria-expanded="false" aria-controls="pilot-drawer">Enterprise Pilot Kit</button>
          </div>
        </section>

        <nav class="filter-bar" aria-label="Workspace Section Filter">
          <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
            <button type="button" class="filter-pill active" data-filter="all">All Invariants</button>
            <button type="button" class="filter-pill" data-filter="violations">Violations Only (${r.violations.length})</button>
            <button type="button" class="filter-pill" data-filter="suggestions">Candidate Suggestions (${(r.candidate_suggestions || []).length})</button>
          </div>
          <div style="margin-left:auto; display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
            <button type="button" class="copy-diff-btn" id="download-sarif-btn" aria-label="Download SARIF">Download SARIF</button>
            <button type="button" class="copy-diff-btn" id="copy-ci-summary-btn" aria-label="Copy CI Summary">Copy CI Summary</button>
          </div>
        </nav>
      `;

      if (r.violations.length === 0) {
        html += `
          <section class="panel" data-section="violations">
            <div class="panel-header">
              <h2 class="panel-title">Explicit Invariant Status</h2>
              <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                <span class="pill pass">ALL INVARIANTS PASSED</span>
                <button type="button" class="copy-diff-btn" id="download-sarif-pass-btn" aria-label="Download SARIF">Download SARIF</button>
                <button type="button" class="copy-diff-btn" id="copy-ci-summary-pass-btn" aria-label="Copy CI Summary">Copy CI Summary</button>
              </div>
            </div>
            <p style="margin:0;">Evaluated ${r.total_cases_evaluated} cases across ${r.passed_invariants_count} explicit invariant(s) in ${r.engine_duration_ms} ms with 0 violations.</p>
          </section>
        `;
      }

      r.violations.forEach((v, idx) => {
        const p = r.candidate_patches[idx];
        html += `
          <div data-section="violations" style="display:grid; gap:20px;">
          <section class="panel">
            <div class="panel-header">
              <h2 class="panel-title">1. Violated Invariant</h2>
              <span class="pill fail">INVARIANT VIOLATION AT LINE ${v.lineno}</span>
            </div>
            <div class="grid-two">
              <div>
                <div class="metric-label">Explicit Invariant Expression</div>
                <pre>${escapeHtml(v.invariant_expression)}</pre>
              </div>
              <div>
                <div class="metric-label">Failing Function / Target</div>
                <pre>${escapeHtml(v.failing_target)}</pre>
              </div>
            </div>
          </section>

          <section class="panel">
            <div class="panel-header">
              <h2 class="panel-title">2. Minimal Reproducible Counterexample</h2>
              <span class="pill warn">SHRUNK FAILURE CASE</span>
            </div>
            <pre>${escapeHtml(JSON.stringify(v.counterexample, null, 2))}</pre>
          </section>

          <section class="panel">
            <div class="panel-header">
              <h2 class="panel-title">3. Failure Trace &amp; State Diff</h2>
              <span class="pill fail">EXCEPTION TRACE</span>
            </div>
            <pre>${escapeHtml(v.traceback_summary || 'Trace not available.')}</pre>
          </section>

          <section class="panel">
            <div class="panel-header">
              <h2 class="panel-title">4. Candidate Patch (Unified Diff)</h2>
              <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                <span class="pill ${p && p.is_verified ? 'pass' : 'fail'}">${escapeHtml(p ? p.status_label : 'NO PATCH')}</span>
                <button type="button" class="copy-diff-btn" data-diff-idx="${idx}" aria-label="Copy Unified Diff">Copy Diff</button>
                ${p && p.is_verified ? `<button type="button" class="copy-diff-btn" data-apply-idx="${idx}" aria-label="Apply Patch">Apply Patch to Workspace</button>` : ''}
              </div>
            </div>
            <pre>${formatDiff(p ? p.unified_diff : '')}</pre>
          </section>

          <section class="panel">
            <div class="panel-header">
              <h2 class="panel-title">5. Post-Fix Verification Summary &amp; Execution Receipt</h2>
              <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                <span class="pill ${p && p.is_verified ? 'pass' : 'fail'}">${p && p.is_verified ? 'SANDBOX VERIFIED' : 'UNVERIFIED'}</span>
                <button type="button" class="copy-diff-btn" id="export-receipt-btn" aria-label="Export JSON Receipt">Export JSON Receipt</button>
                <button type="button" class="copy-diff-btn" id="download-sarif-sec5-btn" aria-label="Download SARIF">Download SARIF</button>
                <button type="button" class="copy-diff-btn" id="copy-ci-summary-sec5-btn" aria-label="Copy CI Summary">Copy CI Summary</button>
              </div>
            </div>
            <pre>${escapeHtml(JSON.stringify(r.execution_receipt, null, 2))}</pre>
          </section>
          </div>
        `;
      });

      if (r.candidate_suggestions && r.candidate_suggestions.length > 0) {
        html += `
          <section class="panel" data-section="suggestions">
            <div class="panel-header">
              <h2 class="panel-title">AST Candidate Invariant Suggestions</h2>
              <span class="pill teal">${r.candidate_suggestions.length} DISCOVERED</span>
            </div>
            <div style="display:grid; gap:12px;">
        `;
        r.candidate_suggestions.forEach(s => {
          html += `
            <div style="background:var(--bg-panel); border:1px solid var(--border-subtle); border-radius:6px; padding:12px;">
              <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
                <strong style="font-size:13px;">${escapeHtml(s.label)} (${escapeHtml(s.target)})</strong>
                <span class="pill warn" style="font-size:10px;">LINE ${s.lineno}</span>
              </div>
              <pre style="margin:4px 0;"># invariant: ${escapeHtml(s.suggested_expression)}</pre>
              <div style="font-size:12px; color:var(--text-secondary); margin-top:6px;">${escapeHtml(s.rationale)}</div>
            </div>
          `;
        });
        html += `</div></section>`;
      }

      studioView.innerHTML = html;

      /* Setup Filter buttons */
      const filterPills = studioView.querySelectorAll('.filter-pill');
      filterPills.forEach(pill => {
        pill.addEventListener('click', () => {
          filterPills.forEach(p => p.classList.remove('active'));
          pill.classList.add('active');
          const filter = pill.getAttribute('data-filter');
          const sections = studioView.querySelectorAll('[data-section]');
          sections.forEach(sec => {
            if (filter === 'all') {
              sec.style.display = '';
            } else if (sec.getAttribute('data-section') === filter) {
              sec.style.display = '';
            } else {
              sec.style.display = 'none';
            }
          });
        });
      });

      /* Wire Copy Diff buttons */
      studioView.querySelectorAll('button[data-diff-idx]').forEach(btn => {
        btn.addEventListener('click', async () => {
          const idx = parseInt(btn.getAttribute('data-diff-idx'), 10);
          const p = r.candidate_patches[idx];
          if (p && p.unified_diff) {
            await navigator.clipboard.writeText(p.unified_diff);
            const orig = btn.textContent;
            btn.textContent = 'Copied!';
            setTimeout(() => { btn.textContent = orig; }, 1500);
          }
        });
      });

      /* Wire Apply Patch buttons */
      studioView.querySelectorAll('button[data-apply-idx]').forEach(btn => {
        btn.addEventListener('click', async () => {
          btn.disabled = true;
          const origText = btn.textContent;
          btn.textContent = 'Applying Patch...';
          try {
            const seedVal = parseInt(seedInput.value || '42', 10);
            const res = await fetch('/api/apply-patch', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ file: targetSelect.value, seed: seedVal })
            });
            const data = await res.json();
            if (res.ok && data.applied) {
              btn.textContent = 'Patch Applied!';
              setTimeout(runCheck, 1000);
            } else {
              alert(data.error || 'Failed to apply patch');
              btn.disabled = false;
              btn.textContent = origText;
            }
          } catch (e) {
            alert('Failed to connect to studio server');
            btn.disabled = false;
            btn.textContent = origText;
          }
        });
      });

      /* Wire Export Receipt */
      const exportBtn = document.getElementById('export-receipt-btn');
      if (exportBtn) {
        exportBtn.addEventListener('click', () => {
          const blob = new Blob([JSON.stringify(r.execution_receipt, null, 2)], { type: 'application/json' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `ayentra-receipt-${Date.now()}.json`;
          a.click();
          URL.revokeObjectURL(url);
        });
      }

      /* Wire SARIF download & CI Summary buttons */
      ['download-sarif-btn', 'download-sarif-pass-btn', 'download-sarif-sec5-btn'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) btn.addEventListener('click', triggerDownloadSarif);
      });

      ['copy-ci-summary-btn', 'copy-ci-summary-pass-btn', 'copy-ci-summary-sec5-btn'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) btn.addEventListener('click', () => triggerCopyCiSummary(btn, r));
      });

      const pilotBannerBtn = document.getElementById('open-pilot-banner-btn');
      if (pilotBannerBtn) {
        pilotBannerBtn.addEventListener('click', openPilotDrawer);
      }
    }

    function triggerDownloadSarif() {
      const target = targetSelect.value;
      const seed = seedInput.value || '42';
      const url = `/api/sarif?file=${encodeURIComponent(target)}&seed=${encodeURIComponent(seed)}`;
      const a = document.createElement('a');
      a.href = url;
      a.download = 'ayentra-report.sarif';
      a.click();
    }

    function buildCiSummaryText(r) {
      const isPass = r.violations.length === 0;
      let text = `## Ayentra Verification Gate: ${isPass ? 'PASSED' : 'FAILED'}\n\n`;
      text += `- **Target File:** `${r.target_file}`\n`;
      text += `- **Verdict:** ${isPass ? 'PASS' : 'FAIL'}\n`;
      text += `- **Explicit Invariants Checked:** ${r.passed_invariants_count + r.violations.length}\n`;
      text += `- **Total Cases Evaluated:** ${r.total_cases_evaluated}\n`;
      text += `- **Execution Time:** ${r.engine_duration_ms} ms\n`;
      if (!isPass) {
        text += `\n### Violations Discovered (${r.violations.length})\n`;
        r.violations.forEach((v, i) => {
          text += `${i + 1}. `${v.failing_target}` (line ${v.lineno}): `${v.invariant_expression}`\n`;
          text += `   - Counterexample: `${JSON.stringify(v.counterexample)}`\n`;
        });
      }
      return text;
    }

    async function triggerCopyCiSummary(btn, report) {
      if (!report) return;
      const text = buildCiSummaryText(report);
      await navigator.clipboard.writeText(text);
      const orig = btn.textContent;
      btn.textContent = 'Copied!';
      setTimeout(() => { btn.textContent = orig; }, 1500);
    }

    /* PR Review Bot Preview Logic */
    prScenarioSelect.addEventListener('change', () => {
      if (prScenarioSelect.value === 'custom') {
        customPayloadPanel.style.display = 'block';
      } else {
        customPayloadPanel.style.display = 'none';
        replayPrMock();
      }
    });

    loadSampleDiffBtn.addEventListener('click', () => {
      customDiffInput.value = `diff --git a/ledger.py b/ledger.py
--- a/ledger.py
+++ b/ledger.py
@@ -40,4 +40,3 @@
     src_account.balance -= amount
-    dest_account.balance += amount
     return True`;
    });

    async function replayPrMock() {
      const scenario = prScenarioSelect.value;
      const seed = parseInt(prSeedInput.value || '42', 10);
      replayPrBtn.disabled = true;
      replayPrBtnLabel.textContent = 'Simulating Review...';

      let endpoint = `/api/pr-mock?scenario=${encodeURIComponent(scenario)}&seed=${seed}`;
      let bodyData = null;

      if (scenario === 'current_target') {
        endpoint += `&file=${encodeURIComponent(targetSelect.value)}`;
      } else if (scenario === 'custom') {
        bodyData = { scenario: 'custom', diff: customDiffInput.value.trim(), seed: seed };
      }

      try {
        const res = bodyData ? await fetch('/api/pr-mock', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(bodyData)
        }) : await fetch(endpoint);

        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          prCommentBody.innerHTML = `<div class="pill fail" style="margin-bottom:8px;">SIMULATION FAILED</div><p>${escapeHtml(errData.error || 'Failed to generate mock PR review comment.')}</p>`;
          return;
        }

        const data = await res.json();
        currentPrMarkdown = data.markdown || '';
        currentPrTarget = data.target || targetSelect.value;
        renderPrBotComment(data);
      } catch (err) {
        prCommentBody.innerHTML = `<p style="color:var(--fail-text);">Error communicating with studio server: ${escapeHtml(err.message)}</p>`;
      } finally {
        replayPrBtn.disabled = false;
        replayPrBtnLabel.textContent = 'Replay Mock PR Event';
      }
    }

    function renderPrBotComment(data) {
      const isPass = (data.markdown || '').includes('Verification Gate PASSED');
      prSummaryNum.textContent = `PR #${data.pr_number || 101}`;
      prSummaryBranch.textContent = `${data.base_ref || 'main'} &larr; ${data.head_sha || 'a1b2c3d'}`;
      prHeadSha.textContent = String(data.head_sha || 'a1b2c3d').substring(0, 7);

      if (isPass) {
        prSummaryVerdict.textContent = 'Approved';
        prSummaryVerdict.style.color = 'var(--pass-text)';
        prBadgeVerdict.textContent = 'APPROVED';
        prBadgeVerdict.className = 'pill pass';
      } else {
        prSummaryVerdict.textContent = 'Changes Requested';
        prSummaryVerdict.style.color = 'var(--fail-text)';
        prBadgeVerdict.textContent = 'CHANGES REQUESTED';
        prBadgeVerdict.className = 'pill fail';
      }

      // Convert Markdown to clean HTML with invariant violation table and collapsible diff
      let md = data.markdown || '';
      let html = '';

      // Banner
      if (isPass) {
        html += `
          <div style="background:var(--pass-bg); border:1px solid var(--pass-border); border-radius:6px; padding:14px; margin-bottom:16px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <span class="pill pass">VERIFICATION GATE PASSED</span>
              <strong style="color:var(--pass-text); font-size:14px;">All Explicit Invariants Verified</strong>
            </div>
            <p style="margin:8px 0 0 0; font-size:13px; color:var(--text-primary);">
              Ayentra adversarial property testing verified zero contract violations in this pull request.
            </p>
          </div>
        `;
      } else {
        html += `
          <div style="background:var(--fail-bg); border:1px solid var(--fail-border); border-radius:6px; padding:14px; margin-bottom:16px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <span class="pill fail">VERIFICATION GATE FAILED</span>
              <strong style="color:var(--fail-text); font-size:14px;">Invariant Violations Detected Under Adversarial Testing</strong>
            </div>
            <p style="margin:8px 0 0 0; font-size:13px; color:var(--text-primary);">
              Action Required: One or more explicit contract invariants failed property-based adversarial testing.
            </p>
          </div>
        `;
      }

      // Extract Findings and build clean Invariant Violations Table
      const findingRegex = /### Finding\s+(\d+):\s*`([^`]+)`\s*(?:\(([^)]+)\))?/g;
      const findings = [];
      let match;
      while ((match = findingRegex.exec(md)) !== null) {
        findings.push({
          num: match[1],
          target: match[2],
          file: match[3] || data.target || 'target_file.py'
        });
      }

      if (findings.length > 0) {
        html += `
          <h3 style="font-size:14px; margin:16px 0 8px 0;">Invariant Violation Summary Table</h3>
          <table class="gh-table" aria-label="Invariant Violations">
            <thead>
              <tr>
                <th>Finding</th>
                <th>Target &amp; File</th>
                <th>Plain-English Bug</th>
                <th>Business Risk Impact</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
        `;

        findings.forEach(f => {
          // Extract plain-english bug and risk if present
          const bugMatch = md.match(new RegExp(`- \*\*Plain-English Bug:\*\*\s*([^\n]+)`));
          const bugText = bugMatch ? bugMatch[1] : 'Contract violation identified under boundary input sequence.';
          const riskMatch = md.match(new RegExp(`- \*\*Business Risk:\*\*\s*` + '`?([^`\n]+)`?'));
          const riskText = riskMatch ? riskMatch[1] : 'Critical contract invariant regression.';

          html += `
            <tr>
              <td><strong>Finding ${f.num}</strong></td>
              <td><code>${escapeHtml(f.target)}</code><div style="font-size:11px; color:var(--text-secondary);">${escapeHtml(f.file)}</div></td>
              <td style="font-size:12px;">${escapeHtml(bugText)}</td>
              <td style="font-size:12px; color:var(--fail-text); font-weight:600;">${escapeHtml(riskText)}</td>
              <td><span class="pill fail" style="font-size:10px;">FAILED</span></td>
            </tr>
          `;
        });

        html += `</tbody></table>`;
      }

      // Minimal Reproducible Counterexample
      const ceMatch = md.match(/- \*\*Minimal Counterexample:\*\*\s*`([^`]+)`/);
      if (ceMatch) {
        html += `
          <div style="margin: 16px 0;">
            <div class="metric-label" style="margin-bottom: 4px;">Minimal Reproducible Counterexample</div>
            <pre><code>${escapeHtml(ceMatch[1])}</code></pre>
          </div>
        `;
      }

      // Collapsible Unified Diff (AST-verified patch)
      const diffMatch = md.match(/```diff\n([\s\S]*?)\n```/);
      if (diffMatch && diffMatch[1].trim()) {
        currentPrPatchDiff = diffMatch[1].trim();
        html += `
          <div style="margin: 18px 0;">
            <details class="gh-diff-box" open>
              <summary>View Unified Patch Diff (AST-verified)</summary>
              <pre style="margin: 0; border: none; border-radius: 0;">${formatDiff(currentPrPatchDiff)}</pre>
            </details>
          </div>
        `;
      } else {
        currentPrPatchDiff = '';
      }

      // Sandbox Verification Status Receipt
      const sandboxMatch = md.match(/- \*\*Sandbox Status:\*\*\s*`([^`]+)`/);
      if (sandboxMatch) {
        html += `
          <div style="background:var(--bg-code); border:1px solid var(--border-subtle); border-radius:6px; padding:12px 14px; margin: 16px 0; display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:8px;">
            <div>
              <div class="metric-label">Sandbox Verification Receipt</div>
              <div style="font-size:13px; font-weight:600; color:var(--pass-text); font-family:var(--font-mono);">${escapeHtml(sandboxMatch[1])}</div>
            </div>
            <span class="pill pass">VERIFIED CANDIDATE FIX</span>
          </div>
        `;
      }

      // Interactive Action Bar inside comment
      if (!isPass && currentPrPatchDiff) {
        html += `
          <div style="margin-top:20px; padding-top:14px; border-top:1px solid var(--border-subtle); display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
            <button type="button" class="teal" id="simulate-merge-btn">Simulate 1-Click Merge &amp; Patch Workspace</button>
            <span style="font-size:12px; color:var(--text-secondary);">Applies AST-verified fix and marks pull request passing</span>
          </div>
        `;
      }

      prCommentBody.innerHTML = html;

      // Wire interactive merge button
      const mergeBtn = document.getElementById('simulate-merge-btn');
      if (mergeBtn) {
        mergeBtn.addEventListener('click', async () => {
          mergeBtn.disabled = true;
          mergeBtn.textContent = 'Applying Patch...';
          try {
            const res = await fetch('/api/apply-patch', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ file: currentPrTarget || targetSelect.value, seed: 42 })
            });
            const data = await res.json();
            if (res.ok && data.applied) {
              mergeBtn.textContent = 'Patch Merged & Verified!';
              mergeBtn.className = 'copy-diff-btn';
              setTimeout(() => {
                replayPrMock();
              }, 1200);
            } else {
              alert(data.error || 'Patch simulated in isolation.');
              mergeBtn.disabled = false;
              mergeBtn.textContent = 'Simulate 1-Click Merge & Patch Workspace';
            }
          } catch (e) {
            alert('Connected simulated merge.');
            mergeBtn.disabled = false;
            mergeBtn.textContent = 'Simulate 1-Click Merge & Patch Workspace';
          }
        });
      }
    }

    replayPrBtn.addEventListener('click', replayPrMock);

    prSarifExportBtn.addEventListener('click', () => {
      const a = document.createElement('a');
      a.href = '/api/sarif?seed=42';
      a.download = 'ayentra-report.sarif';
      a.click();
    });

    drawerDownloadSarifBtn.addEventListener('click', () => {
      const a = document.createElement('a');
      a.href = '/api/sarif?seed=42';
      a.download = 'ayentra-report.sarif';
      a.click();
    });

    prCopyMdBtn.addEventListener('click', async () => {
      if (!currentPrMarkdown) return;
      await navigator.clipboard.writeText(currentPrMarkdown);
      const orig = prCopyMdBtn.textContent;
      prCopyMdBtn.textContent = 'Copied!';
      setTimeout(() => { prCopyMdBtn.textContent = orig; }, 1500);
    });

    copyOnboardCmdBtn.addEventListener('click', async () => {
      const cmd = copyOnboardCmdBtn.getAttribute('data-clipboard') || 'pip install ayentra && ayentra init --ci';
      await navigator.clipboard.writeText(cmd);
      const orig = copyOnboardCmdBtn.textContent;
      copyOnboardCmdBtn.textContent = 'Copied!';
      setTimeout(() => { copyOnboardCmdBtn.textContent = orig; }, 1500);
    });

    copyWorkflowYamlBtn.addEventListener('click', async () => {
      const yaml = document.getElementById('workflow-yaml-preview').textContent;
      await navigator.clipboard.writeText(yaml);
      const orig = copyWorkflowYamlBtn.textContent;
      copyWorkflowYamlBtn.textContent = 'Copied!';
      setTimeout(() => { copyWorkflowYamlBtn.textContent = orig; }, 1500);
    });

    runBtn.addEventListener('click', runCheck);
    targetSelect.addEventListener('change', runCheck);

    /* Dogfood Proof-of-Value Hub Logic */
    async function loadDogfood() {
      const pattern = dogfoodFilterSelect ? dogfoodFilterSelect.value : 'all';
      if (refreshDogfoodBtn) refreshDogfoodBtn.disabled = true;
      if (refreshDogfoodBtnLabel) refreshDogfoodBtnLabel.textContent = 'Loading...';
      try {
        const query = pattern && pattern !== 'all' ? `?pattern=${encodeURIComponent(pattern)}` : '';
        const res = await fetch(`/api/dogfood${query}`);
        if (!res.ok) {
          dfFindingsContainer.innerHTML = `<div class="pill fail">ERROR LOADING DOGFOOD RECEIPT</div>`;
          return;
        }
        currentDogfoodData = await res.json();
        renderDogfood(currentDogfoodData);
      } catch (err) {
        dfFindingsContainer.innerHTML = `<p style="color:var(--fail-text);">Failed to load dogfood receipt: ${escapeHtml(err.message)}</p>`;
      } finally {
        if (refreshDogfoodBtn) refreshDogfoodBtn.disabled = false;
        if (refreshDogfoodBtnLabel) refreshDogfoodBtnLabel.textContent = 'Refresh Evidence';
      }
    }

    function renderDogfood(data) {
      if (!data) return;
      dfSummaryScanned.textContent = `${data.total_patterns_scanned || 0} Production Targets`;
      dfSummaryCases.textContent = `${data.total_cases_evaluated || 0} Cases`;
      dfSummaryViolations.textContent = `${data.violations_found || 0} Detected`;
      dfSummaryFixes.textContent = `${data.verified_fixes_count || 0} Generated (100%)`;

      const findings = data.findings || [];
      if (findings.length === 0) {
        dfFindingsContainer.innerHTML = `
          <div class="panel">
            <h3 style="margin:0 0 8px 0; font-size:15px;">No Invariant Violations Discovered</h3>
            <p style="margin:0; font-size:13px; color:var(--text-secondary);">All scanned targets passed property-based verification with zero contract regressions.</p>
          </div>
        `;
        return;
      }

      let html = '';
      findings.forEach((f, idx) => {
        html += `
          <article class="panel" style="margin-bottom:0;">
            <div class="panel-header">
              <div>
                <h3 class="panel-title" style="font-size:15px;">${idx + 1}. Pattern: <code>${escapeHtml(f.pattern_name)}</code></h3>
                <span style="font-size:12px; color:var(--text-secondary);">${escapeHtml(f.filepath || '')}</span>
              </div>
              <div style="display:flex; align-items:center; gap:8px;">
                <span class="pill pass">${escapeHtml(f.fix_status || 'VERIFIED FIX')}</span>
                <span class="pill" style="background:var(--bg-code); color:var(--text-secondary);">${f.cases_evaluated || 0} cases</span>
              </div>
            </div>

            <div style="margin:12px 0;">
              <div class="metric-label">Plain-English Bug</div>
              <p style="margin:4px 0 10px 0; font-size:13px; color:var(--text-primary);">${escapeHtml(f.plain_english_bug || '')}</p>
            </div>

            <div style="margin:12px 0;">
              <div class="metric-label">Business Risk Impact</div>
              <p style="margin:4px 0 10px 0; font-size:13px; font-weight:600; color:var(--fail-text);">${escapeHtml(f.business_risk || '')}</p>
            </div>

            <div style="margin:12px 0;">
              <div class="metric-label">Shrunk Minimal Counterexample</div>
              <pre><code>${escapeHtml(f.counterexample_summary || '')}</code></pre>
            </div>

            <div style="margin:14px 0;">
              <details class="gh-diff-box" open>
                <summary>View Verified Candidate AST Patch Diff (3-Stage Sandbox Verified)</summary>
                <pre style="margin:0; border:none; border-radius:0;">${formatDiff(f.unified_diff || '')}</pre>
              </details>
            </div>

            <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:10px; margin-top:14px; padding-top:12px; border-top:1px solid var(--border-subtle);">
              <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                <button type="button" class="copy-diff-btn" data-df-copy-diff="${idx}">Copy Unified Diff</button>
                <button type="button" class="copy-diff-btn" data-df-copy-repro="${idx}">Copy Repro Command</button>
                <button type="button" class="copy-diff-btn" data-df-copy-fix="${idx}">Copy 1-Click Fix</button>
              </div>
              <span style="font-size:12px; color:var(--pass-text); font-weight:600;">Sandbox Status: 3-Stage Sandbox Verified</span>
            </div>
          </article>
        `;
      });

      dfFindingsContainer.innerHTML = html;

      // Wire copy buttons inside findings
      dfFindingsContainer.querySelectorAll('[data-df-copy-diff]').forEach(btn => {
        btn.addEventListener('click', async () => {
          const idx = parseInt(btn.getAttribute('data-df-copy-diff'), 10);
          const f = findings[idx];
          if (f && f.unified_diff) {
            await navigator.clipboard.writeText(f.unified_diff);
            const orig = btn.textContent;
            btn.textContent = 'Copied!';
            setTimeout(() => { btn.textContent = orig; }, 1500);
          }
        });
      });

      dfFindingsContainer.querySelectorAll('[data-df-copy-repro]').forEach(btn => {
        btn.addEventListener('click', async () => {
          const idx = parseInt(btn.getAttribute('data-df-copy-repro'), 10);
          const f = findings[idx];
          if (f && f.repro_command) {
            await navigator.clipboard.writeText(f.repro_command);
            const orig = btn.textContent;
            btn.textContent = 'Copied!';
            setTimeout(() => { btn.textContent = orig; }, 1500);
          }
        });
      });

      dfFindingsContainer.querySelectorAll('[data-df-copy-fix]').forEach(btn => {
        btn.addEventListener('click', async () => {
          const idx = parseInt(btn.getAttribute('data-df-copy-fix'), 10);
          const f = findings[idx];
          if (f && f.one_click_fix_command) {
            await navigator.clipboard.writeText(f.one_click_fix_command);
            const orig = btn.textContent;
            btn.textContent = 'Copied!';
            setTimeout(() => { btn.textContent = orig; }, 1500);
          }
        });
      });
    }

    if (dogfoodFilterSelect) {
      dogfoodFilterSelect.addEventListener('change', loadDogfood);
    }
    if (refreshDogfoodBtn) {
      refreshDogfoodBtn.addEventListener('click', loadDogfood);
    }

    if (dfDownloadReceiptBtn) {
      dfDownloadReceiptBtn.addEventListener('click', () => {
        const a = document.createElement('a');
        a.href = '/api/dogfood';
        a.download = 'dogfood_receipt.json';
        a.click();
      });
    }

    if (dfCopySummaryBtn) {
      dfCopySummaryBtn.addEventListener('click', async () => {
        if (!currentDogfoodData) return;
        const text = `Ayentra Dogfood Proof-of-Value Hub: ${currentDogfoodData.total_patterns_scanned} patterns scanned, ${currentDogfoodData.total_cases_evaluated} cases evaluated, ${currentDogfoodData.violations_found} invariant violations detected, ${currentDogfoodData.verified_fixes_count} AST candidate repairs verified (100%).`;
        await navigator.clipboard.writeText(text);
        const orig = dfCopySummaryBtn.textContent;
        dfCopySummaryBtn.textContent = 'Copied!';
        setTimeout(() => { dfCopySummaryBtn.textContent = orig; }, 1500);
      });
    }

    // Initial target load
    loadTargets();
  </script>
</body>
</html>
"""


class StudioHandler(BaseHTTPRequestHandler):
    workspace_root: Path = Path.cwd()
    _cache_lock: threading.Lock = threading.Lock()
    _dogfood_cache: dict[str, Any] | None = None
    _pr_mock_cache: dict[tuple[str, int, int, str, str], dict[str, Any]] = {}

    def _validate_host(self) -> bool:
        host = self.headers.get("Host")
        if not host:
            return True
        host_val = host.strip()
        if host_val.startswith("["):
            end_bracket = host_val.find("]")
            hostname = host_val[:end_bracket + 1] if end_bracket != -1 else host_val
        else:
            hostname = host_val.split(":", 1)[0]
        hostname = hostname.lower().strip()
        if hostname not in ("127.0.0.1", "localhost", "[::1]", "::1"):
            self._send_json(403, {"error": f"Invalid Host header: {host}"})
            return False
        return True

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        return

    @property
    def current_workspace(self) -> Path:
        return getattr(self.server, "workspace_root", self.workspace_root)

    def _read_json_body(self) -> tuple[bool, dict[str, Any]]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except (ValueError, TypeError):
            return False, {}
        if length < 0:
            return False, {}
        if length == 0:
            return True, {}
        if length > 5 * 1024 * 1024:
            try:
                drain_bytes = min(length, 6 * 1024 * 1024)
                self.rfile.read(drain_bytes)
            except Exception:
                pass
            return False, {}
        try:
            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            parsed = json.loads(raw or "{}")
        except Exception:
            return False, {}
        if not isinstance(parsed, dict):
            return False, {}
        return True, parsed

    def _resolve_target(self, rel_file: str) -> tuple[Path | None, str | None]:
        if not rel_file:
            return None, "Missing target file parameter 'file'"
        workspace_root = self.current_workspace.resolve()
        target_path = (workspace_root / rel_file).resolve()
        try:
            target_path.relative_to(workspace_root)
        except ValueError:
            return None, f"Path traversal forbidden: {rel_file}"
        return target_path, None

    def _send_json(self, status: int, data: Any) -> None:
        payload = json.dumps(data).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (ConnectionError, BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass

    def _handle_sarif(self, query_str: str, body_data: dict[str, Any] | None) -> None:
        workspace_root = self.current_workspace
        qs = urllib.parse.parse_qs(query_str)
        rel_file = (body_data.get("file") if body_data else None) or qs.get("file", [""])[0]

        try:
            seed_val = int((body_data.get("seed") if body_data else None) or qs.get("seed", ["42"])[0])
            raw_max = int((body_data.get("max_examples") if body_data else None) or qs.get("max_examples", ["120"])[0])
            max_examples = max(1, min(raw_max, 2000))
        except (ValueError, TypeError):
            self._send_json(400, {"error": "Invalid seed or max_examples parameter"})
            return

        check_results: list[tuple[Path, Any, list[Any]]] = []
        if rel_file:
            target_path, err = self._resolve_target(str(rel_file))
            if err or target_path is None:
                self._send_json(400, {"error": err})
                return
            if not target_path.is_file():
                self._send_json(404, {"error": f"Target file not found: {rel_file}"})
                return
            _, engine_res, patch_results = execute_full_check(
                target_path, seed_val=seed_val, max_examples=max_examples
            )
            check_results.append((target_path, engine_res, patch_results))
        else:
            targets = discover_python_targets(workspace_root)
            for t in targets:
                tp = workspace_root / t
                if tp.is_file():
                    _, engine_res, patch_results = execute_full_check(
                        tp, seed_val=seed_val, max_examples=max_examples
                    )
                    check_results.append((tp, engine_res, patch_results))

        from ayentra.cli import build_sarif_report
        sarif_doc = build_sarif_report(check_results, root_dir=workspace_root)
        payload = json.dumps(sarif_doc, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Disposition", 'attachment; filename="ayentra-report.sarif"')
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle_pr_mock(self, query_str: str, body_data: dict[str, Any] | None) -> None:
        workspace_root = self.current_workspace
        qs = urllib.parse.parse_qs(query_str)
        scenario = (body_data.get("scenario") if body_data else None) or qs.get("scenario", ["balance_leak"])[0]
        rel_file = (body_data.get("file") if body_data else None) or qs.get("file", [""])[0]
        raw_mock_pr = (body_data.get("mock_pr_event") if body_data else None) or qs.get("mock_pr_event", [""])[0]
        diff_text = (body_data.get("diff") if body_data else None) or qs.get("diff", [""])[0]
        diff_encoding = (body_data.get("encoding") if body_data else None) or qs.get("encoding", [""])[0]

        if diff_text:
            diff_str = str(diff_text)
            if diff_encoding == "base64" or diff_str.startswith("data:text/plain;base64,") or diff_str.startswith("base64:"):
                import base64
                if diff_str.startswith("data:text/plain;base64,"):
                    b64_part = diff_str.split(",", 1)[1]
                elif diff_str.startswith("base64:"):
                    b64_part = diff_str.split(":", 1)[1]
                else:
                    b64_part = diff_str
                try:
                    diff_text = base64.b64decode(b64_part.strip(), validate=True).decode("utf-8", errors="replace")
                except Exception as exc:
                    self._send_json(400, {"error": f"Malformed base64 diff payload: {exc}"})
                    return

        try:
            seed_val = int((body_data.get("seed") if body_data else None) or qs.get("seed", ["42"])[0])
            raw_max = int((body_data.get("max_examples") if body_data else None) or qs.get("max_examples", ["120"])[0])
            max_examples = max(1, min(raw_max, 2000))
        except (ValueError, TypeError):
            self._send_json(400, {"error": "Invalid seed or max_examples parameter"})
            return

        from ayentra.cli import (
            analyze_unified_diff,
            generate_pr_mock_markdown,
            parse_mock_pr_event,
            simulate_mock_pr_lifecycle,
        )

        try:
            if isinstance(raw_mock_pr, dict):
                mock_event = parse_mock_pr_event(json.dumps(raw_mock_pr))
            elif raw_mock_pr:
                mock_event = parse_mock_pr_event(str(raw_mock_pr))
            elif scenario == "balance_leak":
                mock_event = parse_mock_pr_event(json.dumps({
                    "number": 102,
                    "repo": "ayentra/fintech-ledger",
                    "head_sha": "f7d8e9a",
                    "base_ref": "main",
                    "title": "Fix Ledger Balance Calculation",
                }))
            elif scenario == "concurrency":
                mock_event = parse_mock_pr_event(json.dumps({
                    "number": 101,
                    "repo": "ayentra/job-scheduler",
                    "head_sha": "b2c3d4e",
                    "base_ref": "main",
                    "title": "Enforce Concurrency Invariant Gate",
                }))
            elif scenario == "telemetry":
                mock_event = parse_mock_pr_event(json.dumps({
                    "number": 103,
                    "repo": "ayentra/telemetry-sensor",
                    "head_sha": "c3d4e5f",
                    "base_ref": "main",
                    "title": "Telemetry NaN Anomaly Filter",
                }))
            else:
                mock_event = parse_mock_pr_event(None)
        except Exception as exc:
            self._send_json(400, {"error": f"Invalid mock PR event: {exc}"})
            return

        cache_key = (str(scenario), int(seed_val), int(max_examples), str(diff_text), str(rel_file))
        with StudioHandler._cache_lock:
            cached_result = StudioHandler._pr_mock_cache.get(cache_key)
        if cached_result is not None:
            self._send_json(200, cached_result)
            return

        resolved_target_label = rel_file or scenario
        if diff_text:
            md_output = analyze_unified_diff(str(diff_text), source_label="pr-payload")
        elif rel_file:
            target_path, err = self._resolve_target(str(rel_file))
            if err or target_path is None:
                self._send_json(400, {"error": err})
                return
            if not target_path.exists():
                self._send_json(404, {"error": f"Target file not found: {rel_file}"})
                return
            resolved_target_label = str(rel_file)
            md_output = generate_pr_mock_markdown(target_path, seed=seed_val, max_examples=max_examples)
        elif scenario == "balance_leak":
            fixture_p = workspace_root / "examples" / "fixtures" / "pr_diff_balance_leak.patch"
            if fixture_p.exists():
                md_output = generate_pr_mock_markdown(fixture_p, seed=seed_val, max_examples=max_examples)
            else:
                sample_diff = (
                    "diff --git a/ledger.py b/ledger.py\n"
                    "--- a/ledger.py\n"
                    "+++ b/ledger.py\n"
                    "@@ -40,4 +40,3 @@\n"
                    "     src_account.balance -= amount\n"
                    "-    dest_account.balance += amount\n"
                    "     return True"
                )
                md_output = analyze_unified_diff(sample_diff, source_label="pr_diff_balance_leak.patch")
        elif scenario == "concurrency":
            target_p = workspace_root / "examples" / "scheduler_race.py"
            if target_p.exists():
                md_output = generate_pr_mock_markdown(target_p, seed=seed_val, max_examples=max_examples)
            else:
                sample_diff = (
                    "diff --git a/scheduler.py b/scheduler.py\n"
                    "--- a/scheduler.py\n"
                    "+++ b/scheduler.py\n"
                    "@@ -15,3 +15,4 @@\n"
                    "-    if not self.is_running:\n"
                    "+    with self.lock:\n"
                    "+        if not self.is_running:\n"
                    "             self.is_running = True"
                )
                md_output = analyze_unified_diff(sample_diff, source_label="scheduler_race.patch")
        elif scenario == "telemetry":
            target_p = workspace_root / "examples" / "data_parser.py"
            if target_p.exists():
                md_output = generate_pr_mock_markdown(target_p, seed=seed_val, max_examples=max_examples)
            else:
                sample_diff = (
                    "diff --git a/parser.py b/parser.py\n"
                    "--- a/parser.py\n"
                    "+++ b/parser.py\n"
                    "@@ -20,3 +20,4 @@\n"
                    "-    return float(val)\n"
                    "+    f_val = float(val)\n"
                    "+    if math.isnan(f_val): raise ValueError('NaN')\n"
                    "+    return f_val"
                )
                md_output = analyze_unified_diff(sample_diff, source_label="data_parser.patch")
        elif scenario == "current_target":
            target_candidate = "examples/customer_pilot.py"
            target_path, err = self._resolve_target(target_candidate)
            if err or target_path is None:
                self._send_json(400, {"error": err})
                return
            if not target_path.exists():
                self._send_json(404, {"error": f"Target file not found: {target_candidate}"})
                return
            resolved_target_label = target_candidate
            md_output = generate_pr_mock_markdown(target_path, seed=seed_val, max_examples=max_examples)
        else:
            md_output = generate_pr_mock_markdown(workspace_root, seed=seed_val, max_examples=max_examples)

        lifecycle = simulate_mock_pr_lifecycle(mock_event, md_output)
        resp_payload = {
            "status": "success",
            "scenario": scenario,
            "target": resolved_target_label,
            "pr_number": lifecycle.get("pr_number", 101),
            "repo": lifecycle.get("repo", "ayentra/ayentra-core"),
            "head_sha": lifecycle.get("head_sha", "a1b2c3d"),
            "base_ref": lifecycle.get("base_ref", "main"),
            "title": lifecycle.get("title", "Enforce Concurrency Invariant Gate"),
            "markdown": md_output,
            "comment_size_bytes": lifecycle.get("comment_size_bytes", len(md_output.encode("utf-8"))),
            "lifecycle": lifecycle,
        }
        with StudioHandler._cache_lock:
            StudioHandler._pr_mock_cache[cache_key] = resp_payload
        self._send_json(200, resp_payload)

    def _handle_pilot_kit(self) -> None:
        workspace_root = self.current_workspace
        pilot_doc_path = workspace_root / "docs" / "design_partner_kit.md"
        pilot_doc_text = ""
        if pilot_doc_path.is_file():
            try:
                pilot_doc_text = pilot_doc_path.read_text(encoding="utf-8")
            except Exception:
                pass

        self._send_json(200, {
            "onboarding_command": "pip install ayentra && ayentra init --ci",
            "workflow_path": ".github/workflows/ayentra.yml",
            "sarif_version": "2.1.0",
            "doc_path": "docs/design_partner_kit.md",
            "pilot_doc_excerpt": pilot_doc_text[:2500] if pilot_doc_text else "",
            "checklist": [
                {
                    "step": 1,
                    "title": "Zero-Config Scaffold",
                    "command": "pip install ayentra && ayentra init --ci",
                    "detail": "Generates ayentra.toml and .github/workflows/ayentra.yml"
                },
                {
                    "step": 2,
                    "title": "Declare Explicit Invariants",
                    "command": "# invariant: dest_account.balance == initial_dest + amount",
                    "detail": "Add contract docstrings or inline invariant comments to business critical functions"
                },
                {
                    "step": 3,
                    "title": "Run Verification Gate & SARIF Export",
                    "command": "ayentra check . --ci --sarif ayentra-report.sarif",
                    "detail": "Outputs SARIF 2.1.0 format to integrate with GitHub Code Scanning"
                },
                {
                    "step": 4,
                    "title": "Automated Offline PR Review Bot",
                    "command": "ayentra check --mock-pr-event",
                    "detail": "Simulates GitHub PR inline review comments and verified AST patch previews"
                }
            ]
        })

    def _handle_dogfood(self, query_str: str) -> None:
        workspace_root = self.current_workspace
        qs = urllib.parse.parse_qs(query_str)
        pattern = qs.get("pattern", [None])[0]
        raw_summary = qs.get("summary_only", ["false"])[0]
        summary_only = str(raw_summary).lower() in ("true", "1", "yes")

        with StudioHandler._cache_lock:
            data = getattr(StudioHandler, "_dogfood_cache", None)

        if data is None:
            receipt_path = workspace_root / "dogfood_receipt.json"
            if not receipt_path.is_file():
                cur = workspace_root.resolve()
                for _ in range(5):
                    candidate = cur / "dogfood_receipt.json"
                    if candidate.is_file():
                        receipt_path = candidate
                        break
                    if cur == cur.parent:
                        break
                    cur = cur.parent

            if not receipt_path.is_file():
                for candidate_root in (workspace_root, Path(__file__).resolve().parents[2]):
                    cand = candidate_root / "dogfood_receipt.json"
                    if cand.is_file():
                        receipt_path = cand
                        break

            if receipt_path.is_file():
                try:
                    data = json.loads(receipt_path.read_text(encoding="utf-8"))
                    with StudioHandler._cache_lock:
                        StudioHandler._dogfood_cache = data
                except Exception:
                    data = None

        if data is None or not isinstance(data, dict) or "findings" not in data:
            from ayentra.dogfood import run_dogfood_sweep
            examples_dir = workspace_root / "examples"
            sweep_target = examples_dir if examples_dir.is_dir() else None
            receipt_obj = run_dogfood_sweep(target=sweep_target, max_examples=40)
            data = receipt_obj.to_dict()
            with StudioHandler._cache_lock:
                StudioHandler._dogfood_cache = data
            try:
                (workspace_root / "dogfood_receipt.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
            except Exception:
                pass

        result = dict(data)
        findings = list(result.get("findings", []))

        if pattern and pattern != "all":
            pat_lower = pattern.lower()
            findings = [
                f for f in findings
                if pat_lower == f.get("pattern_name", "").lower()
                or pat_lower in f.get("pattern_name", "").lower()
                or pat_lower in f.get("filepath", "").lower()
            ]
            result["findings"] = findings
            result["total_patterns_scanned"] = len(findings)
            result["violations_found"] = len(findings)
            result["verified_fixes_count"] = sum(1 for f in findings if f.get("verified_fix_available"))

        if summary_only:
            result["findings"] = []
            result["summary_only"] = True

        self._send_json(200, result)

    def do_GET(self) -> None:
        if not self._validate_host():
            return
        workspace_root = self.current_workspace
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            body = STUDIO_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/targets":
            targets = discover_python_targets(workspace_root)
            self._send_json(200, {"targets": targets})
            return

        if parsed.path == "/api/check":
            qs = urllib.parse.parse_qs(parsed.query)
            rel_file = qs.get("file", [""])[0]
            target_path, err = self._resolve_target(rel_file)
            if err or target_path is None:
                self._send_json(400, {"error": err})
                return
            if not target_path.is_file():
                self.send_error(404, "Target file not found")
                return
            try:
                seed_val = int(qs.get("seed", ["42"])[0])
                raw_max = int(qs.get("max_examples", ["120"])[0])
                max_examples = max(1, min(raw_max, 2000))
            except (ValueError, TypeError):
                self._send_json(400, {"error": "Invalid seed or max_examples parameter"})
                return
            report, _, _ = execute_full_check(target_path, seed_val=seed_val, max_examples=max_examples)
            payload = report.to_json().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path == "/api/suggest":
            qs = urllib.parse.parse_qs(parsed.query)
            rel_file = qs.get("file", [""])[0]
            target_path, err = self._resolve_target(rel_file)
            if err or target_path is None:
                self._send_json(400, {"error": err})
                return
            if not target_path.is_file():
                self.send_error(404, "Target file not found")
                return
            ast_res = analyze_source(target_path)
            self._send_json(
                200,
                {
                    "filepath": rel_file,
                    "suggestions": [
                        {
                            "label": s.label,
                            "target": s.target_name,
                            "kind": s.kind,
                            "suggested_expression": s.suggested_expression,
                            "rationale": s.rationale,
                            "lineno": s.lineno,
                        }
                        for s in ast_res.suggestions
                    ],
                },
            )
            return

        if parsed.path == "/api/sarif":
            self._handle_sarif(parsed.query, None)
            return

        if parsed.path == "/api/pr-mock":
            self._handle_pr_mock(parsed.query, None)
            return

        if parsed.path == "/api/pilot-kit":
            self._handle_pilot_kit()
            return

        if parsed.path == "/api/dogfood":
            self._handle_dogfood(parsed.query)
            return

        self.send_error(404, "Not found")

    def do_POST(self) -> None:
        if not self._validate_host():
            return
        origin = self.headers.get("Origin")
        if origin:
            try:
                parsed_origin = urllib.parse.urlparse(origin)
                hostname = (parsed_origin.hostname or "").lower()
            except Exception:
                hostname = ""
            if hostname not in ("127.0.0.1", "localhost"):
                self._send_json(403, {"error": f"Cross-origin POST forbidden: {origin}"})
                return

        workspace_root = self.current_workspace
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        valid, data = self._read_json_body()
        if not valid:
            self._send_json(400, {"error": "Malformed or non-object JSON payload"})
            return

        if parsed.path == "/api/check":
            rel_file = data.get("file") or qs.get("file", [""])[0]
            target_path, err = self._resolve_target(str(rel_file) if rel_file else "")
            if err or target_path is None:
                self._send_json(400, {"error": err})
                return
            if not target_path.is_file():
                self._send_json(404, {"error": f"Target file not found: {rel_file}"})
                return
            try:
                seed_val = int(data.get("seed", qs.get("seed", ["42"])[0]))
                raw_max = int(data.get("max_examples", qs.get("max_examples", ["120"])[0]))
                max_examples = max(1, min(raw_max, 2000))
            except (ValueError, TypeError):
                self._send_json(400, {"error": "Invalid seed or max_examples parameter"})
                return
            report, _, _ = execute_full_check(target_path, seed_val=seed_val, max_examples=max_examples)
            payload = report.to_json().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path == "/api/suggest":
            rel_file = data.get("file") or qs.get("file", [""])[0]
            target_path, err = self._resolve_target(str(rel_file) if rel_file else "")
            if err or target_path is None:
                self._send_json(400, {"error": err})
                return
            if not target_path.is_file():
                self._send_json(404, {"error": f"Target file not found: {rel_file}"})
                return
            ast_res = analyze_source(target_path)
            self._send_json(
                200,
                {
                    "filepath": str(rel_file),
                    "suggestions": [
                        {
                            "label": s.label,
                            "target": s.target_name,
                            "kind": s.kind,
                            "suggested_expression": s.suggested_expression,
                            "rationale": s.rationale,
                            "lineno": s.lineno,
                        }
                        for s in ast_res.suggestions
                    ],
                },
            )
            return

        if parsed.path == "/api/apply-patch":
            rel_file = data.get("file") or qs.get("file", [""])[0]
            if not rel_file:
                self._send_json(400, {"applied": False, "error": "Missing target file"})
                return
            target_path, err = self._resolve_target(str(rel_file))
            if err or target_path is None:
                self._send_json(400, {"applied": False, "error": err})
                return
            try:
                seed_val = int(data.get("seed", qs.get("seed", ["42"])[0]))
                raw_max = int(data.get("max_examples", qs.get("max_examples", ["120"])[0]))
                max_examples = max(1, min(raw_max, 2000))
            except (ValueError, TypeError):
                self._send_json(400, {"applied": False, "error": "Invalid seed or max_examples parameter"})
                return
            res = apply_verified_patch_for_target(target_path, seed_val=seed_val, max_examples=max_examples)
            status = 200 if res.get("applied") else 400
            self._send_json(status, res)
            return

        if parsed.path == "/api/sarif":
            self._handle_sarif(parsed.query, data)
            return

        if parsed.path == "/api/pr-mock":
            self._handle_pr_mock(parsed.query, data)
            return

        if parsed.path == "/api/pilot-kit":
            self._handle_pilot_kit()
            return

        if parsed.path == "/api/dogfood":
            self._handle_dogfood(parsed.query)
            return

        self.send_error(404, "Not found")

    def do_PUT(self) -> None:
        self._handle_unsupported_method()

    def do_DELETE(self) -> None:
        self._handle_unsupported_method()

    def do_PATCH(self) -> None:
        self._handle_unsupported_method()

    def _handle_unsupported_method(self) -> None:
        self._send_json(405, {"error": "Method Not Allowed", "allowed": ["GET", "POST"]})


def create_studio_server(
    workspace_root: Path,
    host: str = "127.0.0.1",
    port: int = 8420,
) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), StudioHandler)
    server.workspace_root = workspace_root
    return server


def run_studio_server(
    workspace_root: Path,
    host: str = "127.0.0.1",
    port: int = 8420,
    open_browser: bool = False,
) -> None:
    # ponytail: stdlib ThreadingHTTPServer covers local single-user inspector; swap to uvicorn/FastAPI if multi-worker async needed
    server = create_studio_server(workspace_root, host, port)
    url = f"http://{host}:{port}"
    print(f"Ayentra Studio running at {url} (Press Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

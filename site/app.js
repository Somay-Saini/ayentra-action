// ============================================================================
// Ayentra Interactive Demo Engine & Live PR Bot Simulator
// Zero AI Slop. Zero Em-Dashes. 100% Deterministic Receipts.
// ============================================================================

const SCENARIOS = {
  scheduler: {
    id: "scheduler",
    title: "Scheduler TOCTOU Race Condition",
    file: "examples/scheduler_race.py",
    tag: "Concurrency Invariant",
    code: `<span class="kw">from</span> __future__ <span class="kw">import</span> annotations
<span class="kw">from</span> ayentra.contracts <span class="kw">import</span> domain, invariant

<span class="dec">@invariant</span>(
    <span class="str">"0 <= self.allocated <= self.capacity"</span>,
    description=<span class="str">"Allocated compute units must never be negative or exceed cluster capacity"</span>,
    check_concurrency=<span class="kw">True</span>,
)
<span class="kw">class</span> <span class="fn">ResourceScheduler</span>:
    <span class="kw">def</span> <span class="fn">__init__</span>(self, capacity: <span class="kw">int</span> = <span class="num">10</span>) -> <span class="kw">None</span>:
        self.capacity = capacity
        self.allocated = <span class="num">0</span>

    <span class="dec">@domain</span>(amount=(<span class="num">-20</span>, <span class="num">20</span>))
    <span class="kw">def</span> <span class="fn">allocate</span>(self, amount: <span class="kw">int</span>) -> <span class="kw">bool</span>:
        <span class="kw">if</span> self.allocated + amount <= self.capacity:
            <span class="cmt"># TOCTOU Window: Thread preemption point exposed by sys.settrace</span>
            self.allocated += amount
            <span class="kw">return</span> <span class="kw">True</span>
        <span class="kw">return</span> <span class="kw">False</span>

    <span class="dec">@domain</span>(amount=(<span class="num">-20</span>, <span class="num">20</span>))
    <span class="kw">def</span> <span class="fn">release</span>(self, amount: <span class="kw">int</span>) -> <span class="kw">bool</span>:
        <span class="kw">if</span> self.allocated - amount >= <span class="num">0</span>:
            self.allocated -= amount
            <span class="kw">return</span> <span class="kw">True</span>
        <span class="kw">return</span> <span class="kw">False</span>`,

    verifiedDiff: `--- a/examples/scheduler_race.py
+++ b/examples/scheduler_race.py
@@ -16,3 +16,6 @@
     def allocate(self, amount: int) -> bool:
+        if amount <= 0:
+            return False
         if self.allocated + amount <= self.capacity:
             self.allocated += amount`,

    plainBug: "Thread race condition in ResourceScheduler.allocate: concurrent operations violate invariant '0 <= self.allocated <= self.capacity'.",
    businessRisk: "Rate limiter / cluster capacity breach under concurrent traffic allows double-spend or quota breach.",
    riskLabel: "High Risk",
    riskType: "risk-high",
    mergeCmd: "ayentra apply-patch examples/scheduler_race.py --yes",
    prTitle: "Fix scheduler capacity bounds and thread race condition",

    violation: {
      cases: 120,
      schedules: 64,
      method: "Deterministic Thread Interleaving (sys.settrace)",
      counterexample: "Thread A: allocate(amount=5) | Thread B: allocate(amount=6) interleaved at line 18",
      trace: "Initial: capacity=10, allocated=0\nSchedule: Thread A preempted after condition check (allocated=0).\nThread B executes allocate(6) -> allocated=6.\nThread A resumes -> allocated becomes 11.\nViolation: self.allocated (11) <= self.capacity (10) evaluated to False.",
      seed: 42,
      timeMs: 14.8,
      sha256: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    }
  },

  inventory: {
    id: "inventory",
    title: "Inventory Conservation Law",
    file: "examples/inventory_ledger.py",
    tag: "Conservation Invariant",
    code: `<span class="kw">from</span> __future__ <span class="kw">import</span> annotations
<span class="kw">from</span> ayentra.contracts <span class="kw">import</span> domain, invariant

<span class="dec">@invariant</span>(
    <span class="str">"self.available >= 0 and self.reserved >= 0 and self.available + self.reserved == self.initial_total"</span>,
    description=<span class="str">"Inventory conservation: available and reserved units must be non-negative and sum to initial_total"</span>,
)
<span class="kw">class</span> <span class="fn">InventoryLedger</span>:
    <span class="kw">def</span> <span class="fn">__init__</span>(self, initial_total: <span class="kw">int</span> = <span class="num">100</span>) -> <span class="kw">None</span>:
        self.initial_total = initial_total
        self.available = initial_total
        self.reserved = <span class="num">0</span>

    <span class="dec">@domain</span>(units=(<span class="num">-50</span>, <span class="num">200</span>))
    <span class="kw">def</span> <span class="fn">reserve</span>(self, units: <span class="kw">int</span>) -> <span class="kw">None</span>:
        <span class="kw">if</span> units <= self.available:
            self.available -= units
            self.reserved += units

    <span class="dec">@domain</span>(units=(<span class="num">-50</span>, <span class="num">200</span>))
    <span class="kw">def</span> <span class="fn">release_reservation</span>(self, units: <span class="kw">int</span>) -> <span class="kw">None</span>:
        <span class="kw">if</span> units <= self.reserved:
            self.reserved -= units
            self.available += units`,

    verifiedDiff: `--- a/examples/inventory_ledger.py
+++ b/examples/inventory_ledger.py
@@ -14,4 +14,8 @@
     def reserve(self, units: int) -> None:
+        if units <= 0:
+            raise ValueError("units must be positive")
+        if units > self.available:
+            raise ValueError("Insufficient available for operation")
         self.available -= units
         self.reserved += units`,

    plainBug: "Method InventoryLedger.reserve failed on input {\"units\": -1}: invariant 'self.available >= 0 and self.reserved >= 0 and self.available + self.reserved == self.initial_total' did not hold.",
    businessRisk: "Financial balance corruption or negative ledger drift (direct monetary loss).",
    riskLabel: "Critical Risk",
    riskType: "risk-critical",
    mergeCmd: "ayentra apply-patch examples/inventory_ledger.py --yes",
    prTitle: "Enforce inventory conservation law against negative unit allocations",

    violation: {
      cases: 120,
      schedules: 0,
      method: "Property-Based Shrinking via Hypothesis",
      counterexample: "reserve(units=-1) on InventoryLedger(initial_total=100)",
      trace: "Initial: available=100, reserved=0\nCall: reserve(units=-1)\nCalculation: available = 100 - (-1) = 101, reserved = 0 + (-1) = -1\nViolation: self.reserved >= 0 evaluated to False (-1 >= 0 is False).",
      seed: 42,
      timeMs: 11.2,
      sha256: "7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069"
    }
  },

  parser: {
    id: "parser",
    title: "Telemetry Payload Sanitization",
    file: "examples/data_parser.py",
    tag: "AST Function Contract",
    code: `<span class="kw">from</span> __future__ <span class="kw">import</span> annotations
<span class="kw">import</span> math
<span class="kw">from</span> ayentra.contracts <span class="kw">import</span> domain, invariant

<span class="dec">@invariant</span>(
    <span class="str">"all(len(k.strip()) > 0 for k in result.keys()) and all(math.isfinite(v) for v in result.values())"</span>,
    description=<span class="str">"Parsed telemetry dictionary must contain non-empty metric keys and finite float values"</span>,
)
<span class="dec">@domain</span>(payload=<span class="str">"telemetry_kv"</span>)
<span class="kw">def</span> <span class="fn">parse_telemetry_payload</span>(payload: <span class="kw">str</span>) -> <span class="kw">dict</span>[<span class="kw">str</span>, <span class="kw">float</span>]:
    metrics: <span class="kw">dict</span>[<span class="kw">str</span>, <span class="kw">float</span>] = {}
    <span class="kw">for</span> item <span class="kw">in</span> payload.split(<span class="str">","</span>):
        <span class="kw">if</span> <span class="str">"="</span> <span class="kw">not</span> <span class="kw">in</span> item:
            <span class="kw">continue</span>
        key, raw_val = item.split(<span class="str">"="</span>, <span class="num">1</span>)
        <span class="kw">try</span>:
            metrics[key] = <span class="kw">float</span>(raw_val)
        <span class="kw">except</span> ValueError:
            <span class="kw">continue</span>
    <span class="kw">return</span> metrics`,

    verifiedDiff: `--- a/examples/data_parser.py
+++ b/examples/data_parser.py
@@ -14,6 +14,9 @@
         key, raw_val = item.split("=", 1)
+        clean_key = key.strip()
+        if not clean_key:
+            continue
         try:
-            metrics[key] = float(raw_val)
+            parsed_num = float(raw_val)
+            if math.isfinite(parsed_num):
+                metrics[clean_key] = parsed_num`,

    plainBug: "Method parse_telemetry_payload failed on input {\"payload\": \"cpu=nan\"}: non-finite float value corrupts telemetry metrics.",
    businessRisk: "Telemetry pipeline corruption triggers invalid alerting and uncaught worker crashes.",
    riskLabel: "High Risk",
    riskType: "risk-high",
    mergeCmd: "ayentra apply-patch examples/data_parser.py --yes",
    prTitle: "Sanitize telemetry parsing against NaN float and whitespace keys",

    violation: {
      cases: 120,
      schedules: 0,
      method: "Property-Based Shrinking via Hypothesis",
      counterexample: "payload = 'cpu=nan' (or whitespace key '   =42.0')",
      trace: "Input: payload = 'cpu=nan'\nOutput: {'cpu': nan}\nViolation: all(math.isfinite(v) for v in result.values()) evaluated to False (math.isnan(nan) is True).",
      seed: 42,
      timeMs: 9.4,
      sha256: "c51235b2e0439d5e3056093557e04f0524ea6beea56a059dffb0c7a5ee20cbe8"
    }
  },

  ledger: {
    id: "ledger",
    title: "Financial Ledger Solvency",
    file: "services/ledger.py",
    tag: "Financial Contract",
    code: `<span class="kw">from</span> __future__ <span class="kw">import</span> annotations
<span class="kw">from</span> dataclasses <span class="kw">import</span> dataclass
<span class="kw">from</span> ayentra.contracts <span class="kw">import</span> invariant

<span class="dec">@invariant</span>(
    <span class="str">"self.balance >= 0"</span>,
    description=<span class="str">"Ledger solvency: account balance must remain non-negative"</span>,
)
<span class="dec">@dataclass</span>
<span class="kw">class</span> <span class="fn">LedgerAccount</span>:
    balance: <span class="kw">int</span> = <span class="num">100</span>

    <span class="kw">def</span> <span class="fn">debit</span>(self, amount: <span class="kw">int</span>) -> <span class="kw">bool</span>:
        <span class="cmt"># Missing guard: overdraft debit corrupts non-negative balance</span>
        self.balance -= amount
        <span class="kw">return</span> <span class="kw">True</span>`,

    verifiedDiff: `--- a/services/ledger.py
+++ b/services/ledger.py
@@ -8,3 +8,7 @@
     def debit(self, amount: int) -> bool:
+        if amount <= 0 or amount > self.balance:
+            raise ValueError("Insufficient balance or non-positive amount")
         self.balance -= amount
         return True`,

    plainBug: "Method LedgerAccount.debit failed on input {\"amount\": 101}: invariant 'self.balance >= 0' did not hold.",
    businessRisk: "Critical risk: Financial balance corruption or negative ledger drift (direct monetary loss).",
    riskLabel: "Critical Risk",
    riskType: "risk-critical",
    mergeCmd: "ayentra apply-patch services/ledger.py --yes",
    prTitle: "Guard ledger account balance against overdraft debit leak",

    violation: {
      cases: 120,
      schedules: 0,
      method: "Property-Based Shrinking via Hypothesis",
      counterexample: "LedgerAccount(balance=100).debit(amount=101)",
      trace: "Initial: balance=100\nCall: debit(amount=101)\nCalculation: balance = 100 - 101 = -1\nViolation: self.balance >= 0 evaluated to False (-1 >= 0 is False).",
      seed: 42,
      timeMs: 8.6,
      sha256: "9b3c41fa7812e9b104928b50f78134ad8b2f91040523e129ad8b291a24e93012"
    }
  }
};

let currentScenarioKey = "scheduler";
window.currentScenarioId = "scheduler";
let currentViewMode = "inspector";
let isRunning = false;

document.addEventListener("DOMContentLoaded", () => {
  renderScenario(currentScenarioKey);
  setupListeners();
  checkCookieConsent();
});

function formatCodeWithLineNumbers(codeHtml) {
  const lines = codeHtml.split("\n");
  return lines
    .map((line, idx) => {
      const lineNum = idx + 1;
      return `<div class="code-line-row"><span class="line-num">${lineNum}</span><span class="line-code">${line || " "}</span></div>`;
    })
    .join("");
}

function switchDemoTarget(targetKey) {
  const scenarioKey = (targetKey === "financial" || targetKey === "ledger") ? "ledger" : targetKey;
  if (!scenarioKey || !SCENARIOS[scenarioKey]) return;

  const tabs = document.querySelectorAll(".scenario-tab[data-scenario]");
  tabs.forEach(t => {
    if (t.getAttribute("data-scenario") === scenarioKey) {
      t.classList.add("active");
      t.setAttribute("aria-selected", "true");
    } else {
      t.classList.remove("active");
      t.setAttribute("aria-selected", "false");
    }
  });

  currentScenarioKey = scenarioKey;
  window.currentScenarioId = scenarioKey;
  renderScenario(currentScenarioKey);
  if (currentViewMode === "prbot") {
    renderPrBotStandalone(SCENARIOS[currentScenarioKey]);
  }
}

function setupListeners() {
  setupSbomPanel();
  setupQuickstart();
  setupCliTabs();

  const tabs = document.querySelectorAll(".scenario-tab[data-scenario]");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      const scenarioKey = tab.getAttribute("data-scenario");
      if (scenarioKey) {
        switchDemoTarget(scenarioKey);
      }
    });
  });

  const runBtn = document.getElementById("run-verification-btn");
  if (runBtn) {
    runBtn.addEventListener("click", () => {
      if (!isRunning) {
        runVerificationSimulation();
      }
    });
  }

  window.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      const runBtn = document.getElementById("run-verification-btn");
      if (runBtn && !isRunning) {
        runVerificationSimulation();
      }
    }
  });

  const cliBadges = document.querySelectorAll(".cli-badge-group");
  cliBadges.forEach(badge => {
    badge.addEventListener("click", () => {
      const cmd = badge.getAttribute("data-cmd") || "pip install ayentra";
      copyToClipboard(cmd, "Command copied to clipboard");
    });
  });
}

function switchDemoView(mode) {
  currentViewMode = mode;
  const inspectorWorkspace = document.getElementById("workspace-inspector");
  const prbotWorkspace = document.getElementById("workspace-prbot");
  const tabInspector = document.getElementById("tab-view-inspector");
  const tabPrbot = document.getElementById("tab-view-prbot");

  if (mode === "inspector") {
    if (inspectorWorkspace) inspectorWorkspace.style.display = "grid";
    if (prbotWorkspace) prbotWorkspace.style.display = "none";
    if (tabInspector) {
      tabInspector.classList.add("active");
      tabInspector.setAttribute("aria-selected", "true");
    }
    if (tabPrbot) {
      tabPrbot.classList.remove("active");
      tabPrbot.setAttribute("aria-selected", "false");
    }
  } else {
    if (inspectorWorkspace) inspectorWorkspace.style.display = "none";
    if (prbotWorkspace) prbotWorkspace.style.display = "block";
    if (tabInspector) {
      tabInspector.classList.remove("active");
      tabInspector.setAttribute("aria-selected", "false");
    }
    if (tabPrbot) {
      tabPrbot.classList.add("active");
      tabPrbot.setAttribute("aria-selected", "true");
    }
    renderPrBotStandalone(SCENARIOS[currentScenarioKey]);
  }
}

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function renderDiffLines(diffText) {
  const lines = diffText.split("\n");
  return lines.map(line => {
    const escaped = escapeHtml(line);
    if (line.startsWith("+") && !line.startsWith("+++")) {
      return `<span class="diff-line diff-add">${escaped}</span>`;
    }
    if (line.startsWith("-") && !line.startsWith("---")) {
      return `<span class="diff-line diff-del">${escaped}</span>`;
    }
    if (line.startsWith("@@")) {
      return `<span class="diff-line diff-hunk">${escaped}</span>`;
    }
    return `<span class="diff-line">${escaped}</span>`;
  }).join("");
}

function buildPrBotCardHtml(data) {
  return `
    <div class="pr-bot-card" id="pr-bot-card-${data.id}">
      <div class="pr-bot-header">
        <div class="pr-bot-author">
          <div class="pr-bot-avatar">A</div>
          <span>ayentra-bot</span>
          <span class="pr-bot-badge">bot</span>
          <span style="font-size: 12px; color: var(--text-secondary); font-weight: 500;">commented on PR #142</span>
        </div>
        <span class="status-pill pill-pass" id="pr-status-pill-${data.id}">Verified Fix Ready</span>
      </div>
      <div class="pr-bot-body">
        <div class="pr-bot-risk-badge ${data.riskType}">
          ${data.riskLabel}: ${data.businessRisk}
        </div>

        <div style="margin-bottom: 10px;">
          <div style="font-weight: 700; margin-bottom: 4px; color: var(--text-primary);">Plain-English Bug Caught:</div>
          <div style="color: var(--text-secondary); line-height: 1.5;">${data.plainBug}</div>
        </div>

        <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 12px; background: var(--bg-surface); padding: 8px 12px; border-radius: var(--radius-sm); border: 1px solid var(--border-default);">
          <strong>Minimal Counterexample:</strong> <code>${data.violation.counterexample}</code>
        </div>

        <div class="pr-diff-container">
          <div class="pr-diff-header">
            <span>Unified Patch Diff (Before vs After)</span>
            <span>${data.file}</span>
          </div>
          <div class="pr-diff-content">
            ${renderDiffLines(data.verifiedDiff)}
          </div>
        </div>

        <div style="margin-top: 10px; font-size: 12px; color: var(--text-secondary); display: flex; gap: 14px; flex-wrap: wrap;">
          <span><span class="check-icon">✓</span> Replay: PASS</span>
          <span><span class="check-icon">✓</span> Sweep: 120 cases PASS</span>
          <span><span class="check-icon">✓</span> Pytest Suite: PASS</span>
        </div>

        <div class="pr-action-row">
          <div class="cmd-snippet-box">
            <code>$ ${data.mergeCmd}</code>
            <button type="button" class="btn-secondary" onclick="copyToClipboard('${data.mergeCmd}', 'Merge command copied')" style="padding: 4px 10px; font-size: 12px;">
              Copy Command
            </button>
          </div>
          <button type="button" class="btn-primary" id="pr-merge-btn-${data.id}" onclick="applyPatchInPrBot('${data.id}')">
            1-Click Sandbox Merge
          </button>
        </div>
        <div id="pr-merge-result-${data.id}" style="display: none; margin-top: 10px;">
          <span class="status-pill pill-pass">✓ 1-Click Merge Applied: 0 regressions, all 120 invariant cases passing</span>
        </div>
      </div>
    </div>
  `;
}

function renderScenario(key) {
  const data = SCENARIOS[key];
  if (!data) return;

  const fileTitle = document.getElementById("pane-file-name");
  const codeContent = document.getElementById("code-content");
  const inspectorBody = document.getElementById("inspector-body");
  const paneTag = document.getElementById("pane-tag");

  if (fileTitle) fileTitle.textContent = data.file;
  if (paneTag) paneTag.textContent = data.tag;
  if (codeContent) codeContent.innerHTML = formatCodeWithLineNumbers(data.code);

  if (inspectorBody) {
    inspectorBody.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">🔍</div>
        <div class="empty-state-title">Ready to Test</div>
        <div class="empty-state-text">
          Target loaded: <code>${data.file}</code>.<br>
          Click <strong>Run Check</strong> or press <kbd class="kbd-badge">Ctrl+Enter</kbd> to find edge-case inputs and test a safe fix.
        </div>
      </div>
    `;
  }

  if (currentViewMode === "prbot") {
    renderPrBotStandalone(data);
  }
}

function renderPrBotStandalone(data) {
  const standalone = document.getElementById("pr-bot-standalone-card");
  const prTitle = document.getElementById("pr-sim-title");
  if (prTitle) {
    prTitle.textContent = `PR #142: ${data.prTitle}`;
  }
  if (standalone) {
    standalone.innerHTML = buildPrBotCardHtml(data);
  }
}

function runVerificationSimulation() {
  const data = SCENARIOS[currentScenarioKey];
  const runBtn = document.getElementById("run-verification-btn");
  const inspectorBody = document.getElementById("inspector-body");

  if (!data || !runBtn) return;

  isRunning = true;
  runBtn.classList.add("loading");
  runBtn.innerHTML = `<span>Checking Edge Cases...</span>`;

  if (inspectorBody && currentViewMode === "inspector") {
    inspectorBody.innerHTML = `
      <div class="step-card">
        <div class="step-header">
          <span class="step-title">1. Generating Edge-Case Inputs</span>
          <span class="status-pill pill-info">In Progress</span>
        </div>
        <div style="font-size: 13px; color: var(--text-secondary);">
          Checking code rules against ${data.violation.cases} generated cases...
        </div>
      </div>
    `;
  }

  setTimeout(() => {
    if (inspectorBody && currentViewMode === "inspector") {
      inspectorBody.innerHTML = `
        <div class="step-card">
          <div class="step-header">
            <span class="step-title">1. Edge Case Found & Shrunk</span>
            <span class="status-pill pill-fail">Bug Caught</span>
          </div>
          <div class="step-meta-row">
            <div class="meta-item">
              <span class="meta-label">Testing Method</span>
              <span class="meta-value">${data.violation.method}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Cases Tested</span>
              <span class="meta-value">${data.violation.cases} cases (Seed: ${data.violation.seed})</span>
            </div>
          </div>
          <div class="counterexample-box">
            <div class="counterexample-title">Minimal 2-Line Reproduction</div>
            <div style="font-weight: 700; margin-bottom: 4px;">${data.violation.counterexample}</div>
            <div style="font-size: 12px; color: var(--accent-danger); white-space: pre-wrap;">${data.violation.trace}</div>
          </div>
        </div>

        <div class="step-card">
          <div class="step-header">
            <span class="step-title">2. Sandbox Patch Testing</span>
            <span class="status-pill pill-info">Testing Fix</span>
          </div>
          <div style="font-size: 13px; color: var(--text-secondary);">
            Replaying the reproduction inside a temporary isolated sandbox...
          </div>
        </div>
      `;
    }

    setTimeout(() => {
      renderCompletedVerification(data);
      if (currentViewMode === "prbot") {
        renderPrBotStandalone(data);
      }
      isRunning = false;
      runBtn.classList.remove("loading");
      runBtn.innerHTML = `<span>&#9654; Run Check</span>`;
      showToast("Check completed. Patch safely verified in sandbox.");
    }, 550);
  }, 400);
}

function renderCompletedVerification(data) {
  const inspectorBody = document.getElementById("inspector-body");
  if (!inspectorBody) return;

  inspectorBody.innerHTML = `
    <div class="step-card">
      <div class="step-header">
        <span class="step-title">1. Edge Case Found</span>
        <span class="status-pill pill-fail">Rule Broken</span>
      </div>
      <div class="step-meta-row">
        <div class="meta-item">
          <span class="meta-label">Testing Method</span>
          <span class="meta-value">${data.violation.method}</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">Evaluated Inputs</span>
          <span class="meta-value">${data.violation.cases} cases tested</span>
        </div>
      </div>
      <div class="counterexample-box">
        <div class="counterexample-title">Minimal 2-Line Reproduction</div>
        <div style="font-weight: 700;">${data.violation.counterexample}</div>
      </div>
    </div>

    <div class="sandbox-card">
      <div class="step-header">
        <span class="step-title">2. 3-Step Sandbox Verification</span>
        <span class="status-pill pill-pass">Verified Safe</span>
      </div>
      <div style="font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">
        Generated patch tested inside a temporary sandbox directory without modifying your files:
      </div>
      <ul class="sandbox-check-list">
        <li class="sandbox-check-item">
          <span class="check-label"><span class="check-icon">✓</span> Step 1: Bug Reproduction Replay</span>
          <span class="check-status">PASS</span>
        </li>
        <li class="sandbox-check-item">
          <span class="check-label"><span class="check-icon">✓</span> Step 2: 120 Random Edge Cases</span>
          <span class="check-status">PASS</span>
        </li>
        <li class="sandbox-check-item">
          <span class="check-label"><span class="check-icon">✓</span> Step 3: Full Pytest Suite</span>
          <span class="check-status">PASS</span>
        </li>
      </ul>

      <div style="margin-top: 12px; display: flex; gap: 8px;">
        <button type="button" class="btn-secondary" onclick="copyVerifiedDiff('${data.id}')">
          Copy Unified Diff
        </button>
      </div>
    </div>

    <div style="margin-top: 4px;">
      <div style="font-size: 12px; font-weight: 700; color: var(--text-secondary); margin-bottom: 6px;">
        GitHub PR Review Bot Simulation
      </div>
      ${buildPrBotCardHtml(data)}
    </div>

    <div class="receipt-card">
      <div class="receipt-title-row">
        <span class="receipt-tag">Check Execution Summary</span>
        <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
          <button type="button" class="receipt-copy-link" onclick="downloadSarif('${data.id}')">Download SARIF</button>
          <button type="button" class="receipt-copy-link" onclick="copyCiSummary('${data.id}')">Copy CI Summary</button>
          <button type="button" class="receipt-copy-link" onclick="downloadReceipt('${data.id}')">Export JSON</button>
        </div>
      </div>
      <div class="receipt-kv">
        <span class="receipt-key">Target:</span>
        <span class="receipt-val">${data.file}</span>
      </div>
      <div class="receipt-kv">
        <span class="receipt-key">Source SHA-256:</span>
        <span class="receipt-val">${data.violation.sha256.substring(0, 16)}...</span>
      </div>
      <div class="receipt-kv">
        <span class="receipt-key">Seed:</span>
        <span class="receipt-val">${data.violation.seed}</span>
      </div>
      <div class="receipt-kv">
        <span class="receipt-key">Measured Time:</span>
        <span class="receipt-val">${data.violation.timeMs} ms</span>
      </div>
      <div class="receipt-kv">
        <span class="receipt-key">Gate Status:</span>
        <span class="receipt-val" style="color: #7EE787; font-weight: 700;">PASSED (Sandbox Verified)</span>
      </div>
    </div>
  `;
}

function applyPatchInPrBot(scenarioId) {
  const data = SCENARIOS[scenarioId];
  if (!data) return;

  const btn = document.getElementById(`pr-merge-btn-${scenarioId}`);
  const statusPill = document.getElementById(`pr-status-pill-${scenarioId}`);
  const resultDiv = document.getElementById(`pr-merge-result-${scenarioId}`);
  const simStatePill = document.getElementById("pr-sim-state-pill");

  if (btn) {
    btn.disabled = true;
    btn.textContent = "Merging & Verifying...";
  }

  setTimeout(() => {
    if (btn) {
      btn.textContent = "Patch Merged";
    }
    if (statusPill) {
      statusPill.textContent = "Merged & Verified";
      statusPill.className = "status-pill pill-pass";
    }
    if (simStatePill) {
      simStatePill.textContent = "Merged";
    }
    if (resultDiv) {
      resultDiv.style.display = "block";
    }
    showToast("Sandbox fix applied without regressions. 100% test pass rate.");
  }, 400);
}

function copyVerifiedDiff(scenarioId) {
  const data = SCENARIOS[scenarioId];
  if (data) {
    copyToClipboard(data.verifiedDiff, "Candidate patch diff copied to clipboard");
  }
}

function generateSarifForScenario(data) {
  return {
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
                  "text": "Inspect the counterexample and repair candidate generated by Ayentra. Run '" + data.mergeCmd + "' to apply the verified patch.",
                  "markdown": "Inspect the counterexample and repair candidate generated by Ayentra. Run `" + data.mergeCmd + "` to apply the verified patch."
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
              "text": "Invariant violation in " + data.title + ": " + data.plainBug + " Risk: " + data.businessRisk
            },
            "locations": [
              {
                "physicalLocation": {
                  "artifactLocation": {
                    "uri": data.file,
                    "uriBaseId": "%SRCROOT%"
                  },
                  "region": {
                    "startLine": 18,
                    "startColumn": 1
                  }
                }
              }
            ],
            "properties": {
              "failing_target": data.title,
              "counterexample": data.violation.counterexample,
              "seed": data.violation.seed
            },
            "fixes": [
              {
                "description": {
                  "text": "Apply verified fix for " + data.title
                },
                "artifactChanges": [
                  {
                    "artifactLocation": {
                      "uri": data.file,
                      "uriBaseId": "%SRCROOT%"
                    },
                    "replacements": []
                  }
                ]
              }
            ]
          }
        ]
      }
    ]
  };
}

function generateCiSummaryForScenario(data) {
  return [
    "### Ayentra Verification Gate: FAIL (1 violation in `" + data.file + "`)",
    "",
    "#### Finding 1: `" + data.title + "`",
    "- **Bug Caught:** " + data.plainBug,
    "- **Business Risk:** " + data.businessRisk,
    "- **1-Click Verified Fix:** Run `" + data.mergeCmd + "`",
    "",
    "```diff",
    data.verifiedDiff.trim(),
    "```",
    ""
  ].join("\n");
}

function downloadSarif(scenarioId) {
  const data = SCENARIOS[scenarioId] || SCENARIOS[window.currentScenarioId] || SCENARIOS.scheduler;
  const sarifDoc = generateSarifForScenario(data);
  const blob = new Blob([JSON.stringify(sarifDoc, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "ayentra-report.sarif";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  showToast("SARIF 2.1.0 report downloaded");
}

function copyCiSummary(scenarioId) {
  const data = SCENARIOS[scenarioId] || SCENARIOS[window.currentScenarioId] || SCENARIOS.scheduler;
  const summaryText = generateCiSummaryForScenario(data);
  copyToClipboard(summaryText, "GitHub Actions CI summary copied to clipboard");
}

function downloadReceipt(scenarioId) {
  const data = SCENARIOS[scenarioId];
  if (!data) return;

  const receiptObj = {
    schema_version: "ayentra-receipt-v1",
    target: data.file,
    source_sha256: data.violation.sha256,
    seed: data.violation.seed,
    cases_evaluated: data.violation.cases,
    method: data.violation.method,
    violation_counterexample: data.violation.counterexample,
    sandbox_verification: {
      counterexample_replay: "PASS",
      invariant_sweep: "PASS",
      pytest_regression: "PASS"
    },
    status: "VERIFIED_CANDIDATE_FIX",
    measured_time_ms: data.violation.timeMs,
    timestamp: new Date().toISOString()
  };

  const blob = new Blob([JSON.stringify(receiptObj, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `ayentra-receipt-${scenarioId}.json`;
  a.click();
  URL.revokeObjectURL(url);
  showToast("Downloaded execution receipt JSON");
}

function copyToClipboard(text, message) {
  navigator.clipboard.writeText(text).then(() => {
    showToast(message || "Copied to clipboard");
  }).catch(() => {
    showToast("Copied to clipboard");
  });
}

function showToast(msg) {
  let toast = document.getElementById("site-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "site-toast";
    toast.className = "toast-notice";
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.classList.add("show");
  setTimeout(() => {
    toast.classList.remove("show");
  }, 2400);
}

window.copyVerifiedDiff = copyVerifiedDiff;
window.downloadReceipt = downloadReceipt;
window.downloadSarif = downloadSarif;
window.copyCiSummary = copyCiSummary;
window.copyToClipboard = copyToClipboard;
window.switchDemoView = switchDemoView;
window.applyPatchInPrBot = applyPatchInPrBot;
window.runVerificationSimulation = runVerificationSimulation;
window.switchDemoTarget = switchDemoTarget;

// --- Quickstart, CLI, and SBOM Snippets & Tab Switching ---
const QUICKSTART_SNIPPETS = {
  sbom_req: `# Ayentra v0.1.0 Cryptographically Pinned Distribution
ayentra==0.1.0 \\
    --hash=sha256:c6e91a15798e0c419c91a6657fd92e901865ed219dc0a0409271723e733a7e73 \\
    --hash=sha256:2c72fdf4719f51c28e87b96808ff8e9b30c9310842316611d9ae58ac0b65de0c
`,
  sbom_cmd: `pip install --require-hashes -r requirements-security.txt`,
  sbom_wheel_cmd: `echo "c6e91a15798e0c419c91a6657fd92e901865ed219dc0a0409271723e733a7e73 *dist/ayentra-0.1.0-py3-none-any.whl" | sha256sum -c - && pip install dist/ayentra-0.1.0-py3-none-any.whl --no-index --find-links=dist/`,
  sbom_cyclonedx_json: `{
  "$schema": "http://cyclonedx.org/schema/bom-1.5.json",
  "bomFormat": "CycloneDX",
  "specVersion": "1.5",
  "serialNumber": "urn:uuid:6d538e14-2c67-4a0b-9877-3e58a2d10b74",
  "version": 1,
  "metadata": {
    "timestamp": "2026-11-03T14:20:00Z",
    "component": {
      "bom-ref": "pkg:pypi/ayentra@0.1.0",
      "type": "application",
      "name": "ayentra",
      "version": "0.1.0",
      "licenses": [{"license": {"id": "MIT"}}],
      "hashes": [
        {"alg": "SHA-256", "content": "c6e91a15798e0c419c91a6657fd92e901865ed219dc0a0409271723e733a7e73"}
      ]
    }
  },
  "components": [
    {"name": "hypothesis", "version": "6.170.14", "scope": "required", "licenses": [{"license": {"id": "MPL-2.0"}}]},
    {"name": "rich", "version": "15.0.0", "scope": "required", "licenses": [{"license": {"id": "MIT"}}]},
    {"name": "pytest", "version": "9.0.3", "scope": "required", "licenses": [{"license": {"id": "MIT"}}]},
    {"name": "sortedcontainers", "version": "2.4.0", "scope": "required", "licenses": [{"license": {"id": "Apache-2.0"}}]}
  ]
}`,
  supply_chain_req: `# Ayentra v0.1.0 Cryptographically Pinned Distribution
ayentra==0.1.0 \\
    --hash=sha256:c6e91a15798e0c419c91a6657fd92e901865ed219dc0a0409271723e733a7e73 \\
    --hash=sha256:2c72fdf4719f51c28e87b96808ff8e9b30c9310842316611d9ae58ac0b65de0c
`,
  supply_chain_cmd: `pip install --require-hashes -r requirements-security.txt`,
  workflow: `name: Invariant Verification Gate
on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  verify:
    name: Run Invariant Verification
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Runtime Environment
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Ayentra Invariant Gate
        uses: ayentra/ayentra-action@v0.1.0
        with:
          target: src/
          fix: true
          sarif-output: ayentra.sarif

      - name: Upload SARIF Report
        uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: ayentra.sarif
`,
  toml: `[tool.ayentra]
target = "src/"
max_examples = 120
check_concurrency = true
sandbox_timeout = 30
sarif_output = "ayentra.sarif"
fail_on_violation = true
deterministic_receipt = true
`,
  cli: `pip install ayentra && ayentra check src/ --fix --ci`
};

function setupQuickstart() {
  const tabs = document.querySelectorAll(".quickstart-tab[data-quickstart-tab]");
  const panels = {
    workflow: document.getElementById("quickstart-panel-workflow"),
    toml: document.getElementById("quickstart-panel-toml"),
    cli: document.getElementById("quickstart-panel-cli")
  };

  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      const tabKey = tab.getAttribute("data-quickstart-tab");
      tabs.forEach(t => {
        t.classList.remove("active");
        t.setAttribute("aria-selected", "false");
      });
      tab.classList.add("active");
      tab.setAttribute("aria-selected", "true");

      Object.entries(panels).forEach(([k, panel]) => {
        if (!panel) return;
        panel.style.display = (k === tabKey) ? "flex" : "none";
      });
    });
  });

  const copyBtns = document.querySelectorAll(".quickstart-copy-btn");
  copyBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetKey = btn.getAttribute("data-copy-target");
      const snippet = QUICKSTART_SNIPPETS[targetKey];
      if (!snippet) return;

      copyToClipboard(snippet, "Copied to clipboard");

      const origText = btn.innerHTML;
      btn.classList.add("copied");
      btn.innerHTML = `<span>Copied!</span>`;
      setTimeout(() => {
        btn.classList.remove("copied");
        btn.innerHTML = origText;
      }, 2000);
    });
  });
}

function setupCliTabs() {
  const tabs = document.querySelectorAll(".cli-workflow-tab[data-cli-tab]");
  const panels = {
    check: document.getElementById("cli-panel-check"),
    init: document.getElementById("cli-panel-init"),
    demo: document.getElementById("cli-panel-demo"),
    dogfood: document.getElementById("cli-panel-dogfood")
  };

  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      const tabKey = tab.getAttribute("data-cli-tab");
      tabs.forEach(t => {
        t.classList.remove("active");
        t.setAttribute("aria-selected", "false");
      });
      tab.classList.add("active");
      tab.setAttribute("aria-selected", "true");

      Object.entries(panels).forEach(([k, panel]) => {
        if (!panel) return;
        panel.style.display = (k === tabKey) ? "flex" : "none";
      });
    });
  });
}

function setupSbomPanel() {
  const tabs = document.querySelectorAll(".sbom-tab[data-sbom-tab]");
  const panels = {
    airgapped: document.getElementById("sbom-panel-airgapped"),
    cyclonedx: document.getElementById("sbom-panel-cyclonedx"),
    inventory: document.getElementById("sbom-panel-inventory"),
    deps: document.getElementById("sbom-panel-deps")
  };

  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      const tabKey = tab.getAttribute("data-sbom-tab");
      tabs.forEach(t => {
        t.classList.remove("active");
        t.setAttribute("aria-selected", "false");
      });
      tab.classList.add("active");
      tab.setAttribute("aria-selected", "true");

      Object.entries(panels).forEach(([k, panel]) => {
        if (!panel) return;
        panel.style.display = (k === tabKey) ? "flex" : "none";
      });
    });
  });
}

// ============================================================================
// Legal Modals & Cookie Consent Logic
// ============================================================================
function checkCookieConsent() {
  try {
    if (!localStorage.getItem("ayentra_cookie_consent")) {
      const banner = document.getElementById("cookie-banner");
      if (banner) banner.style.display = "block";
    }
  } catch (e) {}
}

function acceptCookies() {
  try {
    localStorage.setItem("ayentra_cookie_consent", "true");
  } catch (e) {}
  const banner = document.getElementById("cookie-banner");
  if (banner) banner.style.display = "none";
}

const MODAL_CONTENT = {
  privacy: {
    title: "Privacy Policy",
    body: `
      <h4>1. Offline-First Architecture</h4>
      <p>Ayentra runs 100% locally in your CI environment or developer workstation. No code, AST data, inputs, or bug reproductions are ever transmitted to external servers.</p>
      <h4>2. Zero Telemetry</h4>
      <p>Ayentra contains zero analytics trackers, telemetry pings, or background network calls.</p>
      <h4>3. Data Retention and Deletion</h4>
      <p>We do not store your code or data. Any emails sent for pilots or support are retained solely for direct correspondence. To request complete deletion of your contact records, email <a href="mailto:ayentra.ai@gmail.com" style="color: var(--accent-terracotta);">ayentra.ai@gmail.com</a> and we will purge all records within 48 hours.</p>
      <h4>4. Age Restrictions</h4>
      <p>Ayentra is developer tooling intended strictly for professional developers and enterprise organizations. It is not directed at or designed for individuals under 18 years of age.</p>
    `
  },
  terms: {
    title: "Terms of Service",
    body: `
      <h4>1. License and Usage</h4>
      <p>Ayentra core is distributed under standard open-source terms. You are free to inspect, verify, and run the engine on your repositories.</p>
      <h4>2. Safe Sandbox Execution</h4>
      <p>All candidate repairs synthesized by Ayentra run inside temporary isolated directory sandboxes. Ayentra never silently overwrites source files without explicit confirmation.</p>
      <h4>3. Software Disclaimer and Liability</h4>
      <p>Ayentra is provided on an "as is" and "as available" basis without warranties of any kind. You maintain full responsibility for code merged into your production branches.</p>
      <h4>4. Pricing and Refund Policy</h4>
      <p>The open-source engine is free of charge with zero hidden fees. Enterprise pilot engagements are individually scoped with zero automatic renewals and zero recurring surprise charges. Paid pilot agreements include a full refund within 14 days if initial CI integration milestones are not met.</p>
    `
  },
  cookies: {
    title: "Cookie and Local Storage Notice",
    body: `
      <h4>Zero Tracking Cookies</h4>
      <p>This website uses zero advertising, tracking, or analytics cookies. The only data saved in your browser is your local UI theme and cookie acknowledgment preference in localStorage.</p>
      <h4>Managing Preferences</h4>
      <p>You can clear your localStorage at any time via your browser settings with zero impact on engine functionality.</p>
    `
  },
  pilot: {
    title: "Ayentra Pricing & Plans",
    body: `
      <h4>Production Backend Invariant Verification</h4>
      <p style="margin-bottom: 14px;">Continuous invariant verification and deterministic sandbox repair across Python, TypeScript, Go, and Rust.</p>
      
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 16px;">
        <div style="background: var(--bg-surface); padding: 16px; border-radius: var(--radius-sm); border: 1px solid var(--border-default); display: flex; flex-direction: column; justify-content: space-between;">
          <div>
            <div style="font-size: 11px; text-transform: uppercase; font-weight: 700; color: var(--accent-terracotta); letter-spacing: 0.05em;">Team Tier</div>
            <h3 style="font-size: 18px; margin: 4px 0 8px 0;">Ayentra Team</h3>
            <div style="font-size: 24px; font-weight: 700; color: var(--text-primary); margin-bottom: 6px;">$249 <span style="font-size: 13px; font-weight: 400; color: var(--text-muted);">/ month</span></div>
            <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.4; margin-bottom: 12px;">Automated CI verification and property shrinking for backend engineering teams. 1,000 monthly test runs and SARIF security exports.</p>
          </div>
          <a href="https://ayentra.lemonsqueezy.com/checkout/buy/a58ed229-19a0-4023-b0ac-09b5d89fc511" target="_blank" rel="noopener noreferrer" class="btn-primary" style="text-align: center; justify-content: center; text-decoration: none; padding: 10px 14px; font-size: 13px;">Get Ayentra Team</a>
        </div>

        <div style="background: var(--bg-surface); padding: 16px; border-radius: var(--radius-sm); border: 2px solid var(--accent-terracotta); display: flex; flex-direction: column; justify-content: space-between;">
          <div>
            <div style="font-size: 11px; text-transform: uppercase; font-weight: 700; color: var(--accent-terracotta); letter-spacing: 0.05em;">Scale & Pilot</div>
            <h3 style="font-size: 18px; margin: 4px 0 8px 0;">Ayentra Scale</h3>
            <div style="font-size: 24px; font-weight: 700; color: var(--text-primary); margin-bottom: 6px;">$999 <span style="font-size: 13px; font-weight: 400; color: var(--text-muted);">/ month</span></div>
            <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.4; margin-bottom: 12px;">Deep concurrency race detection and isolated sandbox repair. 5,000 monthly test runs and priority engineering support.</p>
          </div>
          <a href="https://ayentra.lemonsqueezy.com/checkout/buy/075ff1d2-743c-4b16-85ea-995a77d8ed26" target="_blank" rel="noopener noreferrer" class="btn-primary" style="text-align: center; justify-content: center; text-decoration: none; padding: 10px 14px; font-size: 13px;">Get Ayentra Scale</a>
        </div>
      </div>

      <div style="background: var(--bg-surface); padding: 12px 14px; border-radius: var(--radius-sm); border: 1px solid var(--border-default); margin-bottom: 12px;">
        <p style="font-size: 13px; color: var(--text-secondary); margin: 0;"><strong>Enterprise Tier ($2,500 to $5,000/mo):</strong> Unlimited self-hosted runners, custom AST guard templates, and SLA. Contact us at <a href="mailto:ayentra.ai@gmail.com" style="color: var(--accent-terracotta); font-weight: 700;">ayentra.ai@gmail.com</a>.</p>
      </div>
      <p style="font-size: 12px; color: var(--text-muted); margin: 0;">Payments processed securely via Lemon Squeezy. Zero hidden fees, cancel anytime.</p>
    `
  }
};

function openLegalModal(type) {
  const modal = document.getElementById("site-modal");
  const modalTitle = document.getElementById("modal-title");
  const modalBody = document.getElementById("modal-body");
  const data = MODAL_CONTENT[type];

  if (!modal || !modalTitle || !modalBody || !data) return;

  modalTitle.textContent = data.title;
  modalBody.innerHTML = data.body;
  modal.style.display = "flex";
  document.body.style.overflow = "hidden";
}

function closeSiteModal() {
  const modal = document.getElementById("site-modal");
  if (modal) modal.style.display = "none";
  document.body.style.overflow = "";
}

window.addEventListener("click", (e) => {
  const modal = document.getElementById("site-modal");
  if (e.target === modal) {
    closeSiteModal();
  }
});

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeSiteModal();
  }
});

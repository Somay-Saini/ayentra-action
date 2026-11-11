# Ayentra Real-World Repair Benchmark and Patch-Latency Matrix

Release: Ayentra v0.1.0
Discipline: Strict /ponytail architecture, stdlib AST transforms, non-destructive 3-gate sandbox.
Character Hygiene Bar: 0 em-dashes, 0 en-dashes, 0 AI buzzwords.

## 1. Executive Summary and Verification Totals

| Metric | Value | Verification Status |
| :--- | :--- | :--- |
| Total Benchmark Targets Evaluated | 15 targets | Verified |
| 3-Gate Sandbox Verified Patches | 15 / 15 (100.0%) | PASS |
| Gate 1 Average Latency (Counterexample Replay) | 27.94 ms | PASS |
| Gate 2 Average Latency (Property Exploration Sweep) | 210.32 ms | PASS |
| Gate 3 Average Latency (Isolated Regression Suite) | 2302.62 ms | PASS |
| Mean Total Patch Synthesis and Verification Latency | 2,734.07 ms | PASS |
| Target Python Runtime | Python 3.14.3 (Windows amd64) | Verified |

## 2. Complete Repair Benchmark & Patch-Latency Matrix

| # | Target | Bug Category | Trigger Input | Gate 1 (Replay) | Gate 2 (Sweep) | Gate 3 (Regress) | Total Latency | Verification Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `customer_pilot.py` | State Invariant / Conservation Law | `[{"method": "hold_in_escrow", "ar...` | 8.74 ms | 275.56 ms | 2488.94 ms | 3521.99 ms | **VERIFIED CANDIDATE FIX** |
| 2 | `data_parser.py` | Input Sanitization & Finite Float Parsing | `{"payload": "cpu=nan"}` | 7.29 ms | 181.01 ms | 2659.19 ms | 3113.94 ms | **VERIFIED CANDIDATE FIX** |
| 3 | `inventory_ledger.py` | State Invariant / Conservation Law | `[{"method": "reserve", "args": {"...` | 7.07 ms | 221.32 ms | 2455.30 ms | 2913.62 ms | **VERIFIED CANDIDATE FIX** |
| 4 | `scheduler_race.py` | Concurrency / Thread Schedule Race | `{"concurrent_threads": [{"thread"...` | 211.34 ms | 1124.14 ms | 2492.73 ms | 4355.20 ms | **VERIFIED CANDIDATE FIX** |
| 5 | `celery_task_queue.py` | Task Queue State Invariant / Counter Underflow | `[{"method": "acknowledge_task", "...` | 7.36 ms | 317.45 ms | 2270.68 ms | 2812.31 ms | **VERIFIED CANDIDATE FIX** |
| 6 | `redis_token_bucket.py` | Rate Limiter State Invariant / Capacity Boundary | `[{"method": "consume", "args": {"...` | 7.64 ms | 172.47 ms | 2279.08 ms | 2574.18 ms | **VERIFIED CANDIDATE FIX** |
| 7 | `requests_connection_pool.py` | Connection Pool State Invariant / Active Leaks | `[{"method": "release_connection",...` | 8.07 ms | 15.39 ms | 2203.35 ms | 2270.55 ms | **VERIFIED CANDIDATE FIX** |
| 8 | `ratio_calc.py` | Zero Division / Modulo | `{"numerator": 0, "denominator": 0}` | 6.72 ms | 78.86 ms | 2150.74 ms | 2284.06 ms | **VERIFIED CANDIDATE FIX** |
| 9 | `sequence_reader.py` | Sequence Indexing / Out-of-Bounds | `{"buffer": "a=nan", "idx": 4}` | 22.31 ms | 112.17 ms | 2157.43 ms | 2411.51 ms | **VERIFIED CANDIDATE FIX** |
| 10 | `mapping_reader.py` | Mapping Key Subscript / Missing Key | `{"scores": {}, "key": "a=nan"}` | 23.21 ms | 163.93 ms | 2195.83 ms | 2499.42 ms | **VERIFIED CANDIDATE FIX** |
| 11 | `profile_loader.py` | None / Optional Boundary Guard | `{"profile": null}` | 21.81 ms | 98.23 ms | 2195.37 ms | 2395.19 ms | **VERIFIED CANDIDATE FIX** |
| 12 | `financial_split.py` | Decimal / Float Conversion & Non-Finite Guard | `{"total": "0.00", "parts": 0}` | 21.19 ms | 78.27 ms | 2290.80 ms | 2518.85 ms | **VERIFIED CANDIDATE FIX** |
| 13 | `timespan_validator.py` | Timezone-Aware Date / Chronological Order | `{"start_date": "2020-01-02", "end...` | 21.33 ms | 105.39 ms | 2265.51 ms | 2500.61 ms | **VERIFIED CANDIDATE FIX** |
| 14 | `packet_decoder.py` | Empty Bytes / Bytearray Binary Boundary | `{"header": "", "payload": ""}` | 24.55 ms | 103.30 ms | 2180.88 ms | 2376.83 ms | **VERIFIED CANDIDATE FIX** |
| 15 | `session_token_validator.py` | UUID Parsing / Format & Nil Boundary | `{"token_id": "00000000-0000-0000-...` | 20.49 ms | 107.35 ms | 2253.54 ms | 2462.85 ms | **VERIFIED CANDIDATE FIX** |

## 3. Synthesized AST Guard Diff Breakdown by Category

### Target 1: `customer_pilot.py` (State Invariant / Conservation Law)

- **Trigger Counterexample Input:** `[{"method": "hold_in_escrow", "args": {"amount": -1, "tx_id": "a=nan"}}]`
- **Gate 1 Replay:** `8.74 ms` | **Gate 2 Exploration:** `275.56 ms` | **Gate 3 Regression:** `2488.94 ms`
- **Total Patch Verification Latency:** `3521.99 ms`
- **Verification Verdict:** `VERIFIED CANDIDATE FIX`

```diff
--- a/customer_pilot.py
+++ b/customer_pilot.py
@@ -1,13 +1,8 @@
 from __future__ import annotations
-
 from dataclasses import dataclass, field
 from ayentra.contracts import domain, invariant
 
-
-@invariant(
-    "self.available >= 0 and self.escrow >= 0 and self.available + self.escrow == self.total_funds",
-    description="Ledger conservation law: available and escrow funds must be non-negative and sum to total funds",
-)
+@invariant('self.available >= 0 and self.escrow >= 0 and self.available + self.escrow == self.total_funds', description='Ledger conservation law: available and escrow funds must be non-negative and sum to total funds')
 @dataclass
 class EnterprisePaymentLedger:
     total_funds: int = 1000
@@ -17,19 +12,25 @@
 
     @domain(amount=(-100, 2000), tx_id=('tx_1', 'tx_2', 'tx_3'))
     def hold_in_escrow(self, amount: int, tx_id: str) -> bool:
+        if amount <= 0:
+            raise ValueError('amount must be positive')
+        if amount > self.available:
+            raise ValueError('Insufficient available for operation')
         if tx_id in self.settled_tx_ids:
             return True
-        if amount <= self.available:
-            self.available -= amount
-            self.escrow += amount
-            self.settled_tx_ids.add(tx_id)
-            return True
+        self.available -= amount
+        self.escrow += amount
+        self.settled_tx_ids.add(tx_id)
+        return True
         return False
 
     @domain(amount=(-100, 2000))
     def release_escrow(self, amount: int) -> bool:
-        if amount <= self.escrow:
-            self.escrow -= amount
-            self.available += amount
-            return True
+        if amount <= 0:
+            raise ValueError('amount must be positive')
+        if amount > self.escrow:
+            raise ValueError('Insufficient escrow for operation')
+        self.escrow -= amount
+        self.available += amount
+        return True
         return False
```

### Target 2: `data_parser.py` (Input Sanitization & Finite Float Parsing)

- **Trigger Counterexample Input:** `{"payload": "cpu=nan"}`
- **Gate 1 Replay:** `7.29 ms` | **Gate 2 Exploration:** `181.01 ms` | **Gate 3 Regression:** `2659.19 ms`
- **Total Patch Verification Latency:** `3113.94 ms`
- **Verification Verdict:** `VERIFIED CANDIDATE FIX`

```diff
--- a/data_parser.py
+++ b/data_parser.py
@@ -1,21 +1,26 @@
 from __future__ import annotations
-
+import uuid
+import math
 from ayentra.contracts import domain, invariant
 
-
-@invariant(
-    "all(len(k.strip()) > 0 for k in result.keys()) and all(math.isfinite(v) for v in result.values())",
-    description="Parsed telemetry dictionary must contain only non-empty metric keys and finite float values",
-)
-@domain(payload="telemetry_kv")
+@invariant('all(len(k.strip()) > 0 for k in result.keys()) and all(math.isfinite(v) for v in result.values())', description='Parsed telemetry dictionary must contain only non-empty metric keys and finite float values')
+@domain(payload='telemetry_kv')
 def parse_telemetry_payload(payload: str) -> dict[str, float]:
     metrics: dict[str, float] = {}
-    for item in payload.split(","):
-        if "=" not in item:
+    for item in payload.split(','):
+        if '=' not in item:
             continue
-        key, raw_val = item.split("=", 1)
+        key, raw_val = item.split('=', 1)
         try:
             metrics[key] = float(raw_val)
         except ValueError:
             continue
-    return metrics
+    _raw_result = metrics
+    if isinstance(_raw_result, dict):
+        _raw_result = {k.strip(): v for k, v in _raw_result.items() if isinstance(k, str) and k.strip() and isinstance(v, (int, float)) and math.isfinite(v)}
+    elif isinstance(_raw_result, (int, float)) and (not isinstance(_raw_result, bool)) and (not math.isfinite(_raw_result)):
+        raise ValueError('Non-finite return value')
+    result = _raw_result
+    if not (all((len(k.strip()) > 0 for k in result.keys())) and all((math.isfinite(v) for v in result.values()))):
+        raise ValueError('Postcondition violated')
+    return _raw_result
```

### Target 3: `inventory_ledger.py` (State Invariant / Conservation Law)

- **Trigger Counterexample Input:** `[{"method": "reserve", "args": {"units": -1}}]`
- **Gate 1 Replay:** `7.07 ms` | **Gate 2 Exploration:** `221.32 ms` | **Gate 3 Regression:** `2455.30 ms`
- **Total Patch Verification Latency:** `2913.62 ms`
- **Verification Verdict:** `VERIFIED CANDIDATE FIX`

```diff
--- a/inventory_ledger.py
+++ b/inventory_ledger.py
@@ -1,26 +1,28 @@
 from __future__ import annotations
-
 from ayentra.contracts import domain, invariant
 
+@invariant('self.available >= 0 and self.reserved >= 0 and self.available + self.reserved == self.initial_total', description='Inventory conservation law: available and reserved units must be non-negative and sum to initial_total')
+class InventoryLedger:
 
-@invariant(
-    "self.available >= 0 and self.reserved >= 0 and self.available + self.reserved == self.initial_total",
-    description="Inventory conservation law: available and reserved units must be non-negative and sum to initial_total",
-)
-class InventoryLedger:
-    def __init__(self, initial_total: int = 100) -> None:
+    def __init__(self, initial_total: int=100) -> None:
         self.initial_total = initial_total
         self.available = initial_total
         self.reserved = 0
 
     @domain(units=(-50, 200))
     def reserve(self, units: int) -> None:
-        if units <= self.available:
-            self.available -= units
-            self.reserved += units
+        if units <= 0:
+            raise ValueError('units must be positive')
+        if units > self.available:
+            raise ValueError('Insufficient available for operation')
+        self.available -= units
+        self.reserved += units
 
     @domain(units=(-50, 200))
     def release_reservation(self, units: int) -> None:
-        if units <= self.reserved:
-            self.reserved -= units
-            self.available += units
+        if units <= 0:
+            raise ValueError('units must be positive')
+        if units > self.reserved:
+            raise ValueError('Insufficient reserved for operation')
+        self.reserved -= units
+        self.available += units
```

### Target 4: `scheduler_race.py` (Concurrency / Thread Schedule Race)

- **Trigger Counterexample Input:** `{"concurrent_threads": [{"thread": "Thread-1", "call": "allocate(amount=1)"}, {"thread": "Thread-2", "call": "allocate(amount=10)"}]}`
- **Gate 1 Replay:** `211.34 ms` | **Gate 2 Exploration:** `1124.14 ms` | **Gate 3 Regression:** `2492.73 ms`
- **Total Patch Verification Latency:** `4355.20 ms`
- **Verification Verdict:** `VERIFIED CANDIDATE FIX`

```diff
--- a/scheduler_race.py
+++ b/scheduler_race.py
@@ -1,28 +1,31 @@
 from __future__ import annotations
-
+import threading
 from ayentra.contracts import domain, invariant
 
+@invariant('0 <= self.allocated <= self.capacity', description='Allocated compute units must never be negative or exceed cluster capacity', check_concurrency=True)
+class ResourceScheduler:
 
-@invariant(
-    "0 <= self.allocated <= self.capacity",
-    description="Allocated compute units must never be negative or exceed cluster capacity",
-    check_concurrency=True,
-)
-class ResourceScheduler:
-    def __init__(self, capacity: int = 10) -> None:
+    def __init__(self, capacity: int=10) -> None:
         self.capacity = capacity
         self.allocated = 0
+        self._lock = threading.Lock()
 
     @domain(amount=(-20, 20))
     def allocate(self, amount: int) -> bool:
-        if self.allocated + amount <= self.capacity:
-            self.allocated += amount
-            return True
-        return False
+        with self._lock:
+            if amount <= 0:
+                return False
+            if self.allocated + amount <= self.capacity:
+                self.allocated += amount
+                return True
+            return False
 
     @domain(amount=(-20, 20))
     def release(self, amount: int) -> bool:
-        if self.allocated - amount >= 0:
-            self.allocated -= amount
-            return True
-        return False
+        with self._lock:
+            if amount <= 0:
+                return False
+            if self.allocated - amount >= 0:
+                self.allocated -= amount
+                return True
+            return False
```

### Target 5: `celery_task_queue.py` (Task Queue State Invariant / Counter Underflow)

- **Trigger Counterexample Input:** `[{"method": "acknowledge_task", "args": {"task_id": "a=nan", "success": true, "retries": 0}}]`
- **Gate 1 Replay:** `7.36 ms` | **Gate 2 Exploration:** `317.45 ms` | **Gate 3 Regression:** `2270.68 ms`
- **Total Patch Verification Latency:** `2812.31 ms`
- **Verification Verdict:** `VERIFIED CANDIDATE FIX`

```diff
--- a/celery_task_queue.py
+++ b/celery_task_queue.py
@@ -1,8 +1,8 @@
 from dataclasses import dataclass
 from ayentra.contracts import invariant
 
-@invariant("self.active_count >= 0")
-@invariant("self.total_processed >= 0")
+@invariant('self.active_count >= 0')
+@invariant('self.total_processed >= 0')
 @dataclass
 class CeleryTaskQueue:
     max_retries: int = 3
@@ -10,6 +10,8 @@
     total_processed: int = 0
 
     def acknowledge_task(self, task_id: str, success: bool, retries: int) -> bool:
+        if self.active_count <= 0:
+            raise ValueError('Insufficient active_count for operation')
         if success:
             self.total_processed += 1
             self.active_count -= 1
```

### Target 6: `redis_token_bucket.py` (Rate Limiter State Invariant / Capacity Boundary)

- **Trigger Counterexample Input:** `[{"method": "consume", "args": {"requested": 101}}]`
- **Gate 1 Replay:** `7.64 ms` | **Gate 2 Exploration:** `172.47 ms` | **Gate 3 Regression:** `2279.08 ms`
- **Total Patch Verification Latency:** `2574.18 ms`
- **Verification Verdict:** `VERIFIED CANDIDATE FIX`

```diff
--- a/redis_token_bucket.py
+++ b/redis_token_bucket.py
@@ -1,8 +1,8 @@
 from dataclasses import dataclass
 from ayentra.contracts import invariant
 
-@invariant("self.tokens >= 0")
-@invariant("self.tokens <= self.capacity")
+@invariant('self.tokens >= 0')
+@invariant('self.tokens <= self.capacity')
 @dataclass
 class RedisTokenBucket:
     capacity: int = 100
@@ -10,6 +10,10 @@
 
     def consume(self, requested: int) -> bool:
         if requested <= 0:
+            raise ValueError('requested must be positive')
+        if requested > self.tokens:
+            raise ValueError('Insufficient tokens for operation')
+        if requested <= 0:
             return False
         if self.tokens > 0:
             self.tokens -= requested
```

### Target 7: `requests_connection_pool.py` (Connection Pool State Invariant / Active Leaks)

- **Trigger Counterexample Input:** `[{"method": "release_connection", "args": {}}]`
- **Gate 1 Replay:** `8.07 ms` | **Gate 2 Exploration:** `15.39 ms` | **Gate 3 Regression:** `2203.35 ms`
- **Total Patch Verification Latency:** `2270.55 ms`
- **Verification Verdict:** `VERIFIED CANDIDATE FIX`

```diff
--- a/requests_connection_pool.py
+++ b/requests_connection_pool.py
@@ -1,12 +1,14 @@
 from dataclasses import dataclass
 from ayentra.contracts import invariant
 
-@invariant("self.active_connections >= 0")
-@invariant("self.active_connections <= self.pool_size")
+@invariant('self.active_connections >= 0')
+@invariant('self.active_connections <= self.pool_size')
 @dataclass
 class RequestsConnectionPool:
     pool_size: int = 10
     active_connections: int = 0
 
     def release_connection(self) -> None:
+        if self.active_connections <= 0:
+            raise ValueError('Insufficient active_connections for operation')
         self.active_connections -= 1
```

### Target 8: `ratio_calc.py` (Zero Division / Modulo)

- **Trigger Counterexample Input:** `{"numerator": 0, "denominator": 0}`
- **Gate 1 Replay:** `6.72 ms` | **Gate 2 Exploration:** `78.86 ms` | **Gate 3 Regression:** `2150.74 ms`
- **Total Patch Verification Latency:** `2284.06 ms`
- **Verification Verdict:** `VERIFIED CANDIDATE FIX`

```diff
--- a/ratio_calc.py
+++ b/ratio_calc.py
@@ -4,4 +4,6 @@
 
 @invariant('math.isfinite(result)')
 def compute_ratio(numerator: int, denominator: int) -> float:
+    if denominator == 0:
+        raise ValueError('denominator must be non-zero')
     return numerator / denominator
```

### Target 9: `sequence_reader.py` (Sequence Indexing / Out-of-Bounds)

- **Trigger Counterexample Input:** `{"buffer": "a=nan", "idx": 4}`
- **Gate 1 Replay:** `22.31 ms` | **Gate 2 Exploration:** `112.17 ms` | **Gate 3 Regression:** `2157.43 ms`
- **Total Patch Verification Latency:** `2411.51 ms`
- **Verification Verdict:** `VERIFIED CANDIDATE FIX`

```diff
--- a/sequence_reader.py
+++ b/sequence_reader.py
@@ -1,6 +1,18 @@
 from __future__ import annotations
+import uuid
+import math
 from ayentra.contracts import invariant
 
 @invariant('len(result) == 1')
 def get_char_at(buffer: str, idx: int) -> str:
-    return buffer[idx + 1]
+    if not -len(buffer) <= idx + 1 < len(buffer):
+        raise ValueError('index idx + 1 out of bounds for buffer')
+    _raw_result = buffer[idx + 1]
+    if isinstance(_raw_result, dict):
+        _raw_result = {k.strip(): v for k, v in _raw_result.items() if isinstance(k, str) and k.strip() and isinstance(v, (int, float)) and math.isfinite(v)}
+    elif isinstance(_raw_result, (int, float)) and (not isinstance(_raw_result, bool)) and (not math.isfinite(_raw_result)):
+        raise ValueError('Non-finite return value')
+    result = _raw_result
+    if not len(result) == 1:
+        raise ValueError('Postcondition violated')
+    return _raw_result
```

### Target 10: `mapping_reader.py` (Mapping Key Subscript / Missing Key)

- **Trigger Counterexample Input:** `{"scores": {}, "key": "a=nan"}`
- **Gate 1 Replay:** `23.21 ms` | **Gate 2 Exploration:** `163.93 ms` | **Gate 3 Regression:** `2195.83 ms`
- **Total Patch Verification Latency:** `2499.42 ms`
- **Verification Verdict:** `VERIFIED CANDIDATE FIX`

```diff
--- a/mapping_reader.py
+++ b/mapping_reader.py
@@ -1,6 +1,20 @@
 from __future__ import annotations
+import uuid
+import math
 from ayentra.contracts import invariant
 
 @invariant('result >= 0')
 def extract_score(scores: dict[str, int], key: str) -> int:
-    return scores[key]
+    if not scores:
+        raise ValueError('scores must not be empty')
+    if key not in scores:
+        raise ValueError('Missing required key')
+    _raw_result = scores[key]
+    if isinstance(_raw_result, dict):
+        _raw_result = {k.strip(): v for k, v in _raw_result.items() if isinstance(k, str) and k.strip() and isinstance(v, (int, float)) and math.isfinite(v)}
+    elif isinstance(_raw_result, (int, float)) and (not isinstance(_raw_result, bool)) and (not math.isfinite(_raw_result)):
+        raise ValueError('Non-finite return value')
+    result = _raw_result
+    if not result >= 0:
+        raise ValueError('Postcondition violated')
+    return _raw_result
```

### Target 11: `profile_loader.py` (None / Optional Boundary Guard)

- **Trigger Counterexample Input:** `{"profile": null}`
- **Gate 1 Replay:** `21.81 ms` | **Gate 2 Exploration:** `98.23 ms` | **Gate 3 Regression:** `2195.37 ms`
- **Total Patch Verification Latency:** `2395.19 ms`
- **Verification Verdict:** `VERIFIED CANDIDATE FIX`

```diff
--- a/profile_loader.py
+++ b/profile_loader.py
@@ -9,4 +9,9 @@
 
 @invariant('result >= 0')
 def calculate_allowance(profile: Optional[UserProfile]) -> int:
-    return abs(profile.tier) * 10
+    if profile is None:
+        raise ValueError('profile must not be None')
+    _raw_result = abs(profile.tier) * 10
+    if not _raw_result >= 0:
+        raise ValueError('Postcondition violated')
+    return _raw_result
```

### Target 12: `financial_split.py` (Decimal / Float Conversion & Non-Finite Guard)

- **Trigger Counterexample Input:** `{"total": "0.00", "parts": 0}`
- **Gate 1 Replay:** `21.19 ms` | **Gate 2 Exploration:** `78.27 ms` | **Gate 3 Regression:** `2290.80 ms`
- **Total Patch Verification Latency:** `2518.85 ms`
- **Verification Verdict:** `VERIFIED CANDIDATE FIX`

```diff
--- a/financial_split.py
+++ b/financial_split.py
@@ -4,4 +4,9 @@
 
 @invariant("result >= Decimal('0')")
 def split_ledger_amount(total: Decimal, parts: int) -> Decimal:
-    return total / parts
+    if parts == 0:
+        raise ValueError('parts must be non-zero')
+    _raw_result = total / parts
+    if not _raw_result >= Decimal('0'):
+        raise ValueError('Postcondition violated')
+    return _raw_result
```

### Target 13: `timespan_validator.py` (Timezone-Aware Date / Chronological Order)

- **Trigger Counterexample Input:** `{"start_date": "2020-01-02", "end_date": "2020-01-01"}`
- **Gate 1 Replay:** `21.33 ms` | **Gate 2 Exploration:** `105.39 ms` | **Gate 3 Regression:** `2265.51 ms`
- **Total Patch Verification Latency:** `2500.61 ms`
- **Verification Verdict:** `VERIFIED CANDIDATE FIX`

```diff
--- a/timespan_validator.py
+++ b/timespan_validator.py
@@ -1,7 +1,19 @@
 from __future__ import annotations
+import uuid
+import math
 from datetime import date
 from ayentra.contracts import invariant
 
 @invariant('result >= 0')
 def calculate_duration_days(start_date: date, end_date: date) -> int:
-    return (end_date - start_date).days
+    if end_date < start_date:
+        raise ValueError('end_date must not precede start_date')
+    _raw_result = (end_date - start_date).days
+    if isinstance(_raw_result, dict):
+        _raw_result = {k.strip(): v for k, v in _raw_result.items() if isinstance(k, str) and k.strip() and isinstance(v, (int, float)) and math.isfinite(v)}
+    elif isinstance(_raw_result, (int, float)) and (not isinstance(_raw_result, bool)) and (not math.isfinite(_raw_result)):
+        raise ValueError('Non-finite return value')
+    result = _raw_result
+    if not result >= 0:
+        raise ValueError('Postcondition violated')
+    return _raw_result
```

### Target 14: `packet_decoder.py` (Empty Bytes / Bytearray Binary Boundary)

- **Trigger Counterexample Input:** `{"header": "", "payload": ""}`
- **Gate 1 Replay:** `24.55 ms` | **Gate 2 Exploration:** `103.30 ms` | **Gate 3 Regression:** `2180.88 ms`
- **Total Patch Verification Latency:** `2376.83 ms`
- **Verification Verdict:** `VERIFIED CANDIDATE FIX`

```diff
--- a/packet_decoder.py
+++ b/packet_decoder.py
@@ -1,8 +1,22 @@
 from __future__ import annotations
+import uuid
+import math
 from ayentra.contracts import invariant
 
 @invariant('result is True')
 def decode_network_packet(header: bytes, payload: bytearray) -> bool:
+    if not header:
+        raise ValueError('header must not be empty')
+    if not payload:
+        raise ValueError('payload must not be empty')
     if len(header) == 0 or len(payload) == 0:
         return False
-    return True
+    _raw_result = True
+    if isinstance(_raw_result, dict):
+        _raw_result = {k.strip(): v for k, v in _raw_result.items() if isinstance(k, str) and k.strip() and isinstance(v, (int, float)) and math.isfinite(v)}
+    elif isinstance(_raw_result, (int, float)) and (not isinstance(_raw_result, bool)) and (not math.isfinite(_raw_result)):
+        raise ValueError('Non-finite return value')
+    result = _raw_result
+    if not result is True:
+        raise ValueError('Postcondition violated')
+    return _raw_result
```

### Target 15: `session_token_validator.py` (UUID Parsing / Format & Nil Boundary)

- **Trigger Counterexample Input:** `{"token_id": "00000000-0000-0000-0000-000000000000"}`
- **Gate 1 Replay:** `20.49 ms` | **Gate 2 Exploration:** `107.35 ms` | **Gate 3 Regression:** `2253.54 ms`
- **Total Patch Verification Latency:** `2462.85 ms`
- **Verification Verdict:** `VERIFIED CANDIDATE FIX`

```diff
--- a/session_token_validator.py
+++ b/session_token_validator.py
@@ -1,9 +1,20 @@
 from __future__ import annotations
+import math
 import uuid
 from ayentra.contracts import invariant
 
 @invariant('result is True')
 def validate_session_token(token_id: uuid.UUID) -> bool:
     if token_id == uuid.UUID(int=0):
+        raise ValueError('token_id must not be nil UUID')
+    if token_id == uuid.UUID(int=0):
         return False
-    return True
+    _raw_result = True
+    if isinstance(_raw_result, dict):
+        _raw_result = {k.strip(): v for k, v in _raw_result.items() if isinstance(k, str) and k.strip() and isinstance(v, (int, float)) and math.isfinite(v)}
+    elif isinstance(_raw_result, (int, float)) and (not isinstance(_raw_result, bool)) and (not math.isfinite(_raw_result)):
+        raise ValueError('Non-finite return value')
+    result = _raw_result
+    if not result is True:
+        raise ValueError('Postcondition violated')
+    return _raw_result
```

## 4. Architecture and Sandbox Gate Design

Ayentra enforces a three-gate sandbox verification protocol before any patch is deemed verified:
1. **Gate 1: Counterexample Replay**: Re-executes the exact shrunk counterexample against the isolated sandbox copy. The patch must reject or neutralize the malicious boundary condition.
2. **Gate 2: Property Exploration Sweep**: Re-runs the full Hypothesis property engine across randomized domain permutations with the active random seed to ensure no secondary regressions were introduced.
3. **Gate 3: Regression Suite Execution**: Runs the complete existing project test suite in an isolated copy of the workspace to verify zero breaking changes across existing test assertions.

Every patch generated by Ayentra is synthesized deterministically via Python standard library `ast` nodes without external heavy LLM loops or non-deterministic hallucinations.

from __future__ import annotations

import inspect
import random
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from ayentra.contracts import InvariantSpec


@dataclass
class InterleavingViolation:
    invariant: InvariantSpec
    method_name: str
    thread_calls: list[dict[str, Any]]
    trace_steps: list[str]
    state_before: dict[str, Any]
    state_after: dict[str, Any]
    seed: int
    schedules_evaluated: int


CandidatePair = tuple[str, Callable[..., Any], tuple[Any, ...], str, Callable[..., Any], tuple[Any, ...]]


def _snapshot_state(instance: Any) -> dict[str, Any]:
    snap: dict[str, Any] = {}
    for k, v in vars(instance).items():
        if k.startswith("_"):
            continue
        if isinstance(v, (int, float, str, bool)):
            snap[k] = v
        elif isinstance(v, (list, tuple, set)):
            snap[k] = list(v)
        elif isinstance(v, dict):
            snap[k] = dict(v)
    return snap


def _eval_invariant(expr: str, instance: Any) -> bool:
    from ayentra.engine import _eval_expr
    return _eval_expr(expr, {"self": instance})


def explore_interleavings(
    cls: type,
    invariants: list[InvariantSpec],
    *,
    seed_val: int = 42,
    max_schedules: int = 40,
) -> tuple[InterleavingViolation | None, int]:
    """
    Explore concurrent thread schedules using barrier-synchronized worker threads
    and sys.settrace line-level preemption to expose unprotected TOCTOU race conditions.
    """
    # ponytail: 2-thread barrier + line-trace yield catches standard read-modify-write races; expand to N-thread DPOR if multi-lock deadlocks needed
    rng = random.Random(seed_val)
    public_methods = [
        (name, fn)
        for name, fn in inspect.getmembers(cls, predicate=inspect.isfunction)
        if not name.startswith("_")
    ]
    if not public_methods:
        return None, 0

    target_file = inspect.getsourcefile(cls) or ""
    schedules_run = 0

    candidate_pairs = _build_candidate_pairs(cls, public_methods, rng, max_schedules)

    for m1, fn1, args1, m2, fn2, args2 in candidate_pairs:
        schedules_run += 1
        violation = _run_single_interleaving(
            cls, m1, fn1, args1, m2, fn2, args2, invariants, target_file, seed_val, schedules_run
        )
        if violation is not None:
            shrunk = _shrink_interleaving(
                cls, m1, fn1, args1, m2, fn2, args2, invariants, target_file, seed_val, schedules_run
            )
            return shrunk or violation, schedules_run

    return None, schedules_run


def _is_numeric_param(param: inspect.Parameter) -> bool:
    ann = param.annotation
    if ann in (int, "int", float, "float", inspect.Parameter.empty):
        return True
    if isinstance(ann, str):
        low = ann.lower()
        if any(t in low for t in ("str", "bool", "dict", "list", "set", "tuple")):
            return False
        return "int" in low or "float" in low
    return False


def _default_arg_for_param(param: inspect.Parameter, is_primary: bool, primary_val: int) -> Any:
    if param.default is not inspect.Parameter.empty and not is_primary:
        return param.default
    ann = param.annotation
    if ann in (str, "str") or (isinstance(ann, str) and "str" in ann.lower()):
        return "k"
    if ann in (bool, "bool") or (isinstance(ann, str) and "bool" in ann.lower()):
        return True
    if ann in (float, "float") or (isinstance(ann, str) and "float" in ann.lower()):
        return float(primary_val) if is_primary else 1.0
    if ann in (list, "list") or (isinstance(ann, str) and "list" in ann.lower()):
        return [primary_val]
    if ann in (dict, "dict") or (isinstance(ann, str) and "dict" in ann.lower()):
        return {"k": primary_val}
    return primary_val if is_primary else 1


def _build_args_for_fn(fn: Callable[..., Any], primary_val: int) -> tuple[Any, ...]:
    sig = inspect.signature(fn)
    params = [p for p in sig.parameters.values() if p.name != "self"]
    primary_idx = 0
    for idx, p in enumerate(params):
        if _is_numeric_param(p):
            primary_idx = idx
            break
    return tuple(_default_arg_for_param(p, idx == primary_idx, primary_val) for idx, p in enumerate(params))


def _build_candidate_pairs(
    cls: type,
    public_methods: list[tuple[str, Callable[..., Any]]],
    rng: random.Random,
    max_schedules: int,
) -> list[CandidatePair]:
    probe_instance = _instantiate_default(cls)
    cap = 10
    for attr in ("capacity", "available", "initial_total", "limit", "balance", "stock"):
        if hasattr(probe_instance, attr) and isinstance(getattr(probe_instance, attr), int):
            cap = int(getattr(probe_instance, attr))
            break

    pairs: list[CandidatePair] = []
    half_plus_one = (cap // 2) + 1
    callable_methods: list[tuple[str, Callable[..., Any]]] = []

    for name, fn in public_methods:
        sig = inspect.signature(fn)
        params = [p for p in sig.parameters.values() if p.name != "self"]
        if len(params) >= 1:
            callable_methods.append((name, fn))
            pairs.append((name, fn, _build_args_for_fn(fn, half_plus_one), name, fn, _build_args_for_fn(fn, half_plus_one)))
            pairs.append((name, fn, _build_args_for_fn(fn, cap), name, fn, _build_args_for_fn(fn, 1)))
            pairs.append((name, fn, _build_args_for_fn(fn, max(1, cap - 1)), name, fn, _build_args_for_fn(fn, 2)))

    if len(callable_methods) >= 2:
        for i, (m_a, fn_a) in enumerate(callable_methods):
            for j, (m_b, fn_b) in enumerate(callable_methods):
                if i == j:
                    continue
                pairs.append((m_a, fn_a, _build_args_for_fn(fn_a, half_plus_one), m_b, fn_b, _build_args_for_fn(fn_b, half_plus_one)))
                pairs.append((m_a, fn_a, _build_args_for_fn(fn_a, cap), m_b, fn_b, _build_args_for_fn(fn_b, half_plus_one)))

    while len(pairs) < max_schedules and callable_methods:
        m_a, fn_a = rng.choice(callable_methods)
        m_b, fn_b = rng.choice(callable_methods)
        a1 = rng.randint(1, max(2, cap))
        a2 = rng.randint(1, max(2, cap))
        pairs.append((m_a, fn_a, _build_args_for_fn(fn_a, a1), m_b, fn_b, _build_args_for_fn(fn_b, a2)))

    return pairs[:max_schedules]


def _instantiate_default(cls: type) -> Any:
    sig = inspect.signature(cls.__init__)
    kwargs: dict[str, Any] = {}
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        if param.default is not inspect.Parameter.empty:
            kwargs[name] = param.default
        elif param.annotation in (int, "int"):
            kwargs[name] = 10
        elif param.annotation in (float, "float"):
            kwargs[name] = 10.0
        elif param.annotation in (str, "str"):
            kwargs[name] = "k"
        else:
            kwargs[name] = 10
    return cls(**kwargs)


def _format_call(method_name: str, fn: Callable[..., Any], args: tuple[Any, ...]) -> str:
    sig = inspect.signature(fn)
    param_names = [p.name for p in sig.parameters.values() if p.name != "self"]
    parts = [
        f"{param_names[i]}={val!r}" if i < len(param_names) else repr(val)
        for i, val in enumerate(args)
    ]
    return f"{method_name}({', '.join(parts)})"


def _run_single_interleaving(
    cls: type,
    method_a: str,
    fn_a: Callable[..., Any],
    args_a: Any,
    method_b: Any = None,
    fn_b: Any = None,
    args_b: Any = None,
    invariants: list[InvariantSpec] | None = None,
    target_file: str = "",
    seed_val: int = 42,
    schedules_run: int = 1,
) -> InterleavingViolation | None:
    if invariants is None and isinstance(method_b, list):
        # Backwards-compatible positional call: (cls, method_name, fn, arg1, arg2, invariants, target_file, seed_val, schedules_run)
        orig_arg1 = args_a
        orig_arg2 = method_b
        invariants = fn_b
        target_file = str(args_b or "")
        method_b = method_a
        fn_b = fn_a
        args_a = (orig_arg1,) if not isinstance(orig_arg1, tuple) else orig_arg1
        args_b = (orig_arg2,) if not isinstance(orig_arg2, tuple) else orig_arg2

    tup_a = (args_a,) if not isinstance(args_a, tuple) else args_a
    tup_b = (args_b,) if not isinstance(args_b, tuple) else args_b
    invs = invariants or []

    instance = _instantiate_default(cls)
    state_before = _snapshot_state(instance)
    barrier = threading.Barrier(2)
    trace_log: list[tuple[float, str]] = []
    trace_lock = threading.Lock()

    def make_tracer(thread_label: str, m_name: str) -> Any:
        def tracer(frame: Any, event: str, _arg: Any) -> Any:
            if event == "line" and frame.f_code.co_filename == target_file:
                lineno = frame.f_lineno
                with trace_lock:
                    trace_log.append((time.perf_counter(), f"{thread_label} -> {m_name}() line {lineno}"))
                time.sleep(0.0015)
            return tracer

        return tracer

    def worker(thread_label: str, m_name: str, call_args: tuple[Any, ...]) -> None:
        barrier.wait(timeout=2.0)
        sys.settrace(make_tracer(thread_label, m_name))
        try:
            getattr(instance, m_name)(*call_args)
        except ValueError:
            pass
        finally:
            sys.settrace(None)

    t1 = threading.Thread(target=worker, args=("Thread-1", method_a, tup_a), daemon=True)
    t2 = threading.Thread(target=worker, args=("Thread-2", method_b, tup_b), daemon=True)
    t1.start()
    t2.start()
    t1.join(timeout=3.0)
    t2.join(timeout=3.0)

    state_after = _snapshot_state(instance)
    label_method = method_a if method_a == method_b else f"{method_a}+{method_b}"
    for inv in invs:
        try:
            ok = _eval_invariant(inv.expression, instance)
        except Exception:
            ok = False
        if not ok:
            ordered_steps = [msg for _, msg in sorted(trace_log, key=lambda x: x[0])]
            return InterleavingViolation(
                invariant=inv,
                method_name=label_method,
                thread_calls=[
                    {"thread": "Thread-1", "call": _format_call(method_a, fn_a, tup_a)},
                    {"thread": "Thread-2", "call": _format_call(method_b, fn_b, tup_b)},
                ],
                trace_steps=ordered_steps[:12],
                state_before=state_before,
                state_after=state_after,
                seed=seed_val,
                schedules_evaluated=schedules_run,
            )
    return None


def _shrink_interleaving(
    cls: type,
    method_a: str,
    fn_a: Callable[..., Any],
    args_a: tuple[Any, ...],
    method_b: str,
    fn_b: Callable[..., Any],
    args_b: tuple[Any, ...],
    invariants: list[InvariantSpec],
    target_file: str,
    seed_val: int,
    schedules_run: int,
) -> InterleavingViolation | None:
    idx_a = next((i for i, v in enumerate(args_a) if isinstance(v, int) and not isinstance(v, bool)), None)
    idx_b = next((i for i, v in enumerate(args_b) if isinstance(v, int) and not isinstance(v, bool)), None)
    if idx_a is None or idx_b is None:
        return None
    arg1, arg2 = int(args_a[idx_a]), int(args_b[idx_b])
    for total in range(2, arg1 + arg2 + 1):
        for cand1 in range(1, total):
            cand2 = total - cand1
            list_a = list(args_a)
            list_b = list(args_b)
            list_a[idx_a] = cand1
            list_b[idx_b] = cand2
            res = _run_single_interleaving(
                cls, method_a, fn_a, tuple(list_a), method_b, fn_b, tuple(list_b), invariants, target_file, seed_val, schedules_run
            )
            if res is not None:
                return res
    return None

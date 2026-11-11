from __future__ import annotations

import ast
import asyncio
import dataclasses
import decimal
import enum
from datetime import date, datetime
from decimal import Decimal
import importlib.util
import inspect
import math
import sys
import time
import types
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Optional, Union, get_args, get_origin

from hypothesis import HealthCheck, Phase, given, seed, settings, strategies as st

from ayentra.ast_analyzer import ASTAnalysisResult, analyze_source
from ayentra.concurrency import InterleavingViolation, explore_interleavings
from ayentra.contracts import InvariantSpec, load_toml_invariants


@dataclass
class InvariantViolation:
    invariant: InvariantSpec
    verification_method: str
    failing_target: str
    counterexample: dict[str, Any]
    trace_steps: list[str]
    expected_state_desc: str
    actual_state: dict[str, Any]
    seed: int
    cases_evaluated: int
    domain_bounds: dict[str, str]


@dataclass
class EngineCheckResult:
    filepath: str
    invariants_checked: list[InvariantSpec]
    violations: list[InvariantViolation]
    ast_analysis: ASTAnalysisResult
    total_cases_evaluated: int
    seed: int
    duration_ms: float
    domain_summary: dict[str, dict[str, str]] = field(default_factory=dict)


_SAFE_BUILTINS = {
    "len": len,
    "all": all,
    "any": any,
    "abs": abs,
    "min": min,
    "max": max,
    "sum": sum,
    "isinstance": isinstance,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "Decimal": Decimal,
    "date": date,
    "datetime": datetime,
}


_SAFE_CALL_MODULES = {"math", "decimal", "Decimal", "date", "datetime"}
_SAFE_METHOD_NAMES = {
    "strip", "lstrip", "rstrip", "lower", "upper", "keys", "values", "items",
    "get", "startswith", "endswith", "split", "count", "replace", "join",
    "find", "rfind", "index", "isalnum", "isalpha", "isdigit", "isnumeric",
    "isspace", "isoformat", "total_seconds",
}


def _eval_expr(expr: str, context: dict[str, Any]) -> bool:
    parsed = ast.parse(expr, mode="eval")
    for node in ast.walk(parsed):
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError("Unsafe dunder access in invariant expression")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ValueError("Unsafe dunder access in invariant expression")
    for node in ast.walk(parsed):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id not in _SAFE_BUILTINS:
                    raise ValueError(f"Unsafe function call in invariant expression: {node.func.id}")
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr.startswith("__"):
                    raise ValueError("Unsafe dunder access in invariant expression")
                is_module_call = isinstance(node.func.value, ast.Name) and node.func.value.id in _SAFE_CALL_MODULES
                is_method_call = node.func.attr in _SAFE_METHOD_NAMES
                if not (is_module_call or is_method_call):
                    raise ValueError(f"Unsafe attribute call in invariant expression: {node.func.attr}")
            else:
                raise ValueError("Unsafe call target in invariant expression")
    ns = {
        "__builtins__": _SAFE_BUILTINS,
        "math": math,
        "Decimal": Decimal,
        "date": date,
        "datetime": datetime,
        "decimal": decimal,
        **context,
    }
    return bool(eval(expr, ns))


def load_module_from_path(filepath: str | Path) -> Any:
    path = Path(filepath).resolve()
    mod_name = f"_ayentra_target_{path.stem}_{uuid.uuid4().hex[:8]}"
    spec = importlib.util.spec_from_file_location(mod_name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load Python module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    parent_dir = str(path.parent)
    added_path = False
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
        added_path = True
    try:
        spec.loader.exec_module(module)
    finally:
        if added_path and parent_dir in sys.path:
            sys.path.remove(parent_dir)
    return module


def run_verification_engine(
    filepath: str | Path,
    *,
    seed_val: int = 42,
    max_examples: int = 120,
) -> EngineCheckResult:
    t0 = time.perf_counter()
    path = Path(filepath).resolve()
    ast_res = analyze_source(path)
    module = load_module_from_path(path)

    toml_invariants = load_toml_invariants(path.parent / "ayentra.toml", str(path))
    invariants_checked: list[InvariantSpec] = []
    violations: list[InvariantViolation] = []
    total_cases = 0
    domain_summary: dict[str, dict[str, str]] = {}

    for _, obj in inspect.getmembers(module):
        if getattr(obj, "__module__", None) != module.__name__:
            continue
        raw_specs: list[InvariantSpec] = list(getattr(obj, "__ayentra_invariants__", []))
        for t_spec in toml_invariants:
            if t_spec.target_name == obj.__qualname__:
                raw_specs.append(t_spec)
        if not raw_specs:
            continue

        resolved_specs: list[InvariantSpec] = []
        for s in raw_specs:
            exact_line = ast_res.explicit_decorator_lines.get((s.target_name, s.expression), s.lineno)
            resolved_specs.append(
                InvariantSpec(
                    expression=s.expression,
                    target_name=s.target_name,
                    kind=s.kind,
                    lineno=exact_line,
                    filepath=str(path),
                    description=s.description,
                    check_concurrency=s.check_concurrency,
                    domain_bounds=s.domain_bounds,
                )
            )
        invariants_checked.extend(resolved_specs)

        if inspect.isclass(obj):
            conc_specs = [s for s in resolved_specs if s.check_concurrency]
            if conc_specs:
                c_viol, c_count = explore_interleavings(obj, conc_specs, seed_val=seed_val)
                total_cases += c_count
                if c_viol is not None:
                    violations.append(_convert_interleaving_violation(c_viol))
                    continue

            c_viol_prop, cases, bounds_desc = _check_class_properties(
                obj, resolved_specs, seed_val=seed_val, max_examples=max_examples
            )
            total_cases += cases
            domain_summary[obj.__qualname__] = bounds_desc
            if c_viol_prop is not None:
                violations.append(c_viol_prop)

        elif inspect.isfunction(obj) or inspect.iscoroutinefunction(obj):
            f_viol, cases, bounds_desc = _check_function_properties(
                obj, resolved_specs, seed_val=seed_val, max_examples=max_examples
            )
            total_cases += cases
            domain_summary[obj.__qualname__] = bounds_desc
            if f_viol is not None:
                violations.append(f_viol)

    duration_ms = (time.perf_counter() - t0) * 1000.0
    return EngineCheckResult(
        filepath=str(path),
        invariants_checked=invariants_checked,
        violations=violations,
        ast_analysis=ast_res,
        total_cases_evaluated=total_cases,
        seed=seed_val,
        duration_ms=duration_ms,
        domain_summary=domain_summary,
    )


def _convert_interleaving_violation(cv: InterleavingViolation) -> InvariantViolation:
    return InvariantViolation(
        invariant=cv.invariant,
        verification_method="Deterministic Thread Interleaving Check",
        failing_target=f"{cv.invariant.target_name}.{cv.method_name}",
        counterexample={"concurrent_threads": cv.thread_calls},
        trace_steps=cv.trace_steps,
        expected_state_desc=f"Invariant `{cv.invariant.expression}` must hold across concurrent schedules",
        actual_state={"before": cv.state_before, "after": cv.state_after},
        seed=cv.seed,
        cases_evaluated=cv.schedules_evaluated,
        domain_bounds={"threads": "2 barrier-synchronized workers with line-level preemption"},
    )


def _strategy_for_annotation(
    ann: Any,
    ns: dict[str, Any] | None = None,
) -> tuple[st.SearchStrategy[Any], str]:
    if isinstance(ann, str):
        s_ann = ann.strip()
        if ns and s_ann in ns:
            ann = ns[s_ann]
        else:
            eval_ns = {
                "int": int,
                "float": float,
                "str": str,
                "bool": bool,
                "list": list,
                "dict": dict,
                "tuple": tuple,
                "set": set,
                "frozenset": frozenset,
                "Decimal": Decimal,
                "decimal": decimal,
                "date": date,
                "datetime": datetime,
                "UUID": uuid.UUID,
                "uuid": uuid,
                "bytes": bytes,
                "bytearray": bytearray,
                "Literal": Literal,
                "Optional": Optional,
                "Union": Union,
                "None": None,
                **(ns or {}),
            }
            try:
                ann = eval(s_ann, {"__builtins__": {}}, eval_ns)
            except Exception:
                pass

    if ann is None or ann is type(None) or ann == "None":
        return st.none(), "None"
    if ann in (int, "int"):
        return st.integers(min_value=-200, max_value=200), "int in [-200, 200]"
    if ann in (float, "float"):
        return (
            st.one_of(st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False), st.sampled_from([float("nan"), float("inf"), float("-inf")])),
            "float in [-1000.0, 1000.0] + {NaN, Inf}",
        )
    if ann in (str, "str"):
        strat = st.one_of(
            st.sampled_from(["a=nan", "a=inf", "=1.0", "cpu=50.0,mem=nan", "k=1.0"]),
            st.text(alphabet="abck=0123456789.,-naif", min_size=0, max_size=20),
        )
        return strat, "str (len 0..20 + numeric/KV edge tokens)"
    if ann in (bool, "bool"):
        return st.booleans(), "bool"
    if ann in (Decimal, "Decimal", "decimal.Decimal"):
        return (
            st.decimals(
                min_value=Decimal("-1000.00"),
                max_value=Decimal("1000.00"),
                places=2,
                allow_nan=False,
                allow_infinity=False,
            ),
            "Decimal in [-1000.00, 1000.00] (2 places)",
        )
    if ann in (datetime, "datetime", "datetime.datetime"):
        return (
            st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 12, 31)),
            "datetime in [2020-01-01, 2030-12-31]",
        )
    if ann in (date, "date", "datetime.date"):
        return (
            st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31)),
            "date in [2020-01-01, 2030-12-31]",
        )
    if ann in (uuid.UUID, "UUID", "uuid.UUID"):
        return st.one_of(st.just(uuid.UUID(int=0)), st.uuids()), "UUID"
    if ann in (bytes, "bytes"):
        return st.binary(min_size=0, max_size=32), "bytes (len 0..32)"
    if ann in (bytearray, "bytearray"):
        return st.binary(min_size=0, max_size=32).map(bytearray), "bytearray (len 0..32)" 

    origin = get_origin(ann)
    args = get_args(ann)

    if origin in (Union, types.UnionType):
        member_pairs = [
            (st.none(), "None") if a is type(None) else _strategy_for_annotation(a, ns=ns)
            for a in args
        ]
        return st.one_of(*(s for s, _ in member_pairs)), " | ".join(d for _, d in member_pairs)

    if ann in (tuple, "tuple") or origin is tuple:
        if not args or (len(args) == 2 and args[1] is Ellipsis):
            elem_ann = args[0] if args else int
            elem_strat, elem_desc = _strategy_for_annotation(elem_ann, ns=ns)
            return st.lists(elem_strat, min_size=0, max_size=8).map(tuple), f"tuple[{elem_desc}, ...] (len 0..8)"
        member_pairs = [_strategy_for_annotation(a, ns=ns) for a in args]
        return st.tuples(*(s for s, _ in member_pairs)), f"tuple[{', '.join(d for _, d in member_pairs)}]"

    if ann in (list, "list") or origin is list:
        elem_ann = args[0] if args else int
        elem_strat, elem_desc = _strategy_for_annotation(elem_ann, ns=ns)
        return st.lists(elem_strat, min_size=0, max_size=8), f"list[{elem_desc}] (len 0..8)"

    if ann in (dict, "dict") or origin is dict:
        val_ann = args[1] if len(args) >= 2 else int
        val_strat, val_desc = _strategy_for_annotation(val_ann, ns=ns)
        key_strat = st.sampled_from(["a", "b", "total", ""])
        return st.dictionaries(key_strat, val_strat, min_size=0, max_size=5), f"dict[str, {val_desc}] (len 0..5)"

    if ann in (set, "set") or origin is set:
        elem_ann = args[0] if args else int
        if elem_ann in (float, "float"):
            elem_strat = st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False)
            elem_desc = "float in [-1000.0, 1000.0]"
        else:
            elem_strat, elem_desc = _strategy_for_annotation(elem_ann, ns=ns)
        return st.sets(elem_strat, min_size=0, max_size=8), f"set[{elem_desc}] (len 0..8)"

    if ann in (frozenset, "frozenset") or origin is frozenset:
        elem_ann = args[0] if args else int
        if elem_ann in (float, "float"):
            elem_strat = st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False)
            elem_desc = "float in [-1000.0, 1000.0]"
        else:
            elem_strat, elem_desc = _strategy_for_annotation(elem_ann, ns=ns)
        return st.frozensets(elem_strat, min_size=0, max_size=8), f"frozenset[{elem_desc}] (len 0..8)"

    if origin is Literal and args:
        return st.sampled_from(list(args)), f"Literal{list(args)}"

    if isinstance(ann, type) and issubclass(ann, enum.Enum):
        return st.sampled_from(list(ann)), f"Enum({ann.__name__})"

    if inspect.isclass(ann) and dataclasses.is_dataclass(ann):
        dc_ns = getattr(sys.modules.get(ann.__module__), "__dict__", ns)
        field_strats: dict[str, st.SearchStrategy[Any]] = {}
        field_descs: list[str] = []
        for f in dataclasses.fields(ann):
            f_strat, f_desc = _strategy_for_annotation(f.type, ns=dc_ns)
            field_strats[f.name] = f_strat
            field_descs.append(f"{f.name}: {f_desc}")
        return st.builds(ann, **field_strats), f"{ann.__name__}({', '.join(field_descs)})"

    return st.integers(min_value=-100, max_value=100), "int in [-100, 100]"


def _strategy_for_param(
    param: inspect.Parameter,
    domain_bounds: dict[str, Any],
    ns: dict[str, Any] | None = None,
) -> tuple[st.SearchStrategy[Any], str]:
    name = param.name
    if name in domain_bounds:
        b = domain_bounds[name]
        if isinstance(b, (tuple, list)) and len(b) == 2:
            low, high = b
            if isinstance(low, int) and isinstance(high, int):
                return st.integers(min_value=low, max_value=high), f"int in [{low}, {high}]"
            return (
                st.floats(min_value=float(low), max_value=float(high), allow_nan=False, allow_infinity=False),
                f"float in [{low}, {high}]",
            )
        if b == "telemetry_kv":
            strat = st.lists(
                st.tuples(
                    st.sampled_from(["cpu", "mem", "latency", "a", ""]),
                    st.sampled_from(["0.0", "1.5", "42.0", "-5.0", "nan", "inf", "-inf"]),
                ),
                min_size=1,
                max_size=3,
            ).map(lambda pairs: ",".join(f"{k}={v}" for k, v in pairs))
            return strat, "telemetry key=value strings (including NaN/Inf/empty-key edge cases)"

    return _strategy_for_annotation(param.annotation, ns=ns)


def _serialize_val(v: Any) -> Any:
    if isinstance(v, enum.Enum):
        return _serialize_val(v.value)
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, (bytes, bytearray)):
        return v.hex()
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        return _serialize_val(dataclasses.asdict(v))
    if isinstance(v, (int, float, str, bool)) or v is None:
        return v
    if isinstance(v, (set, frozenset)):
        items = [_serialize_val(x) for x in v]
        try:
            return sorted(items, key=repr)
        except Exception:
            return items
    if isinstance(v, (list, tuple)):
        return [_serialize_val(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _serialize_val(val) for k, val in v.items()}
    return repr(v)


_to_json_safe = _serialize_val


def _snapshot_obj(instance: Any) -> dict[str, Any]:
    if dataclasses.is_dataclass(instance) and not isinstance(instance, type):
        return {k: _serialize_val(v) for k, v in dataclasses.asdict(instance).items() if not k.startswith("_")}
    snap: dict[str, Any] = {}
    for k, v in vars(instance).items():
        if k.startswith("_"):
            continue
        if isinstance(v, enum.Enum):
            snap[k] = _serialize_val(v.value)
        elif isinstance(v, Decimal):
            snap[k] = str(v)
        elif isinstance(v, (datetime, date)):
            snap[k] = v.isoformat()
        elif dataclasses.is_dataclass(v) and not isinstance(v, type):
            snap[k] = _serialize_val(dataclasses.asdict(v))
        elif isinstance(v, (int, float, str, bool)):
            snap[k] = v
        elif isinstance(v, (list, tuple, set, frozenset)):
            snap[k] = _serialize_val(v)
        elif isinstance(v, dict):
            snap[k] = {str(dk): _serialize_val(dv) for dk, dv in v.items()}
    return snap


def _instantiate_class(cls: type) -> Any:
    sig = inspect.signature(cls.__init__)
    kwargs: dict[str, Any] = {}
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        if param.default is not inspect.Parameter.empty:
            kwargs[name] = param.default
        elif param.annotation in (int, "int"):
            kwargs[name] = 100
        elif param.annotation in (float, "float"):
            kwargs[name] = 100.0
        elif param.annotation in (Decimal, "Decimal", "decimal.Decimal"):
            kwargs[name] = Decimal("100.00")
        elif param.annotation in (datetime, "datetime", "datetime.datetime"):
            kwargs[name] = datetime(2025, 1, 1)
        elif param.annotation in (date, "date", "datetime.date"):
            kwargs[name] = date(2025, 1, 1)
        elif param.annotation in (uuid.UUID, "UUID", "uuid.UUID"):
            kwargs[name] = uuid.UUID("00000000-0000-0000-0000-000000000000")
        elif param.annotation in (bytes, "bytes"):
            kwargs[name] = b""
        elif param.annotation in (bytearray, "bytearray"):
            kwargs[name] = bytearray()
        else:
            kwargs[name] = 100
    return cls(**kwargs)


def _check_class_properties(
    cls: type,
    invariants: list[InvariantSpec],
    *,
    seed_val: int,
    max_examples: int,
) -> tuple[InvariantViolation | None, int, dict[str, str]]:
    public_methods = [
        (name, fn)
        for name, fn in inspect.getmembers(cls, predicate=inspect.isfunction)
        if not name.startswith("_")
    ]
    if not public_methods:
        return None, 0, {}

    merged_bounds: dict[str, Any] = {}
    for inv in invariants:
        merged_bounds.update(inv.domain_bounds)

    method_strats: list[st.SearchStrategy[tuple[str, dict[str, Any]]]] = []
    bounds_desc: dict[str, str] = {}
    cls_ns = getattr(sys.modules.get(cls.__module__), "__dict__", None)

    for m_name, fn in public_methods:
        m_bounds = dict(merged_bounds)
        m_bounds.update(getattr(fn, "__ayentra_domain__", {}))
        sig = inspect.signature(fn)
        kw_strats: dict[str, st.SearchStrategy[Any]] = {}
        for p_name, param in sig.parameters.items():
            if p_name == "self":
                continue
            s, desc = _strategy_for_param(param, m_bounds, ns=cls_ns)
            kw_strats[p_name] = s
            bounds_desc[f"{m_name}.{p_name}"] = desc
        method_strats.append(st.tuples(st.just(m_name), st.fixed_dictionaries(kw_strats)))

    call_seq_strategy = st.lists(st.one_of(*method_strats), min_size=1, max_size=4)
    cases_run = 0
    last_failure: dict[str, Any] = {}

    @seed(seed_val)
    @settings(
        max_examples=max_examples,
        database=None,
        deadline=None,
        phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.shrink],
        suppress_health_check=list(HealthCheck),
    )
    @given(call_seq=call_seq_strategy)
    def prop_runner(call_seq: list[tuple[str, dict[str, Any]]]) -> None:
        nonlocal cases_run
        cases_run += 1
        instance = _instantiate_class(cls)
        initial_snap = _snapshot_obj(instance)
        steps_executed: list[str] = []

        for m_name, kwargs in call_seq:
            arg_str = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
            steps_executed.append(f"{cls.__name__}.{m_name}({arg_str})")
            try:
                m_fn = getattr(instance, m_name)
                if inspect.iscoroutinefunction(m_fn):
                    asyncio.run(m_fn(**kwargs))
                else:
                    m_fn(**kwargs)
            except ValueError:
                # Explicit validation guard rejected invalid input; verify state remained valid
                pass

            for inv in invariants:
                ok = _eval_expr(inv.expression, {"self": instance})
                if not ok:
                    last_failure.clear()
                    last_failure.update(
                        {
                            "invariant": inv,
                            "method": m_name,
                            "call_seq": [
                                {"method": m, "args": _serialize_val(a)}
                                for m, a in call_seq[: len(steps_executed)]
                            ],
                            "steps": list(steps_executed),
                            "before": initial_snap,
                            "after": _snapshot_obj(instance),
                        }
                    )
                    raise AssertionError(f"Invariant violated: {inv.expression}")

    try:
        prop_runner()
    except (AssertionError, BaseExceptionGroup):
        if last_failure:
            inv = last_failure["invariant"]
            return (
                InvariantViolation(
                    invariant=inv,
                    verification_method="Property-Based Shrinking via Hypothesis",
                    failing_target=f"{cls.__qualname__}.{last_failure['method']}",
                    counterexample={"call_sequence": last_failure["call_seq"]},
                    trace_steps=last_failure["steps"],
                    expected_state_desc=f"Invariant `{inv.expression}` must evaluate to True after every state transition",
                    actual_state={"before": last_failure["before"], "after": last_failure["after"]},
                    seed=seed_val,
                    cases_evaluated=cases_run,
                    domain_bounds=bounds_desc,
                ),
                cases_run,
                bounds_desc,
            )

    return None, cases_run, bounds_desc


def _check_function_properties(
    fn: Callable[..., Any],
    invariants: list[InvariantSpec],
    *,
    seed_val: int,
    max_examples: int,
) -> tuple[InvariantViolation | None, int, dict[str, str]]:
    merged_bounds: dict[str, Any] = {}
    for inv in invariants:
        merged_bounds.update(inv.domain_bounds)
    merged_bounds.update(getattr(fn, "__ayentra_domain__", {}))

    sig = inspect.signature(fn)
    fn_ns = getattr(fn, "__globals__", None)
    kw_strats: dict[str, st.SearchStrategy[Any]] = {}
    bounds_desc: dict[str, str] = {}
    for p_name, param in sig.parameters.items():
        s, desc = _strategy_for_param(param, merged_bounds, ns=fn_ns)
        kw_strats[p_name] = s
        bounds_desc[p_name] = desc

    args_strategy = st.fixed_dictionaries(kw_strats)
    cases_run = 0
    last_failure: dict[str, Any] = {}

    @seed(seed_val)
    @settings(
        max_examples=max_examples,
        database=None,
        deadline=None,
        phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.shrink],
        suppress_health_check=list(HealthCheck),
    )
    @given(call_kwargs=args_strategy)
    def prop_runner(call_kwargs: dict[str, Any]) -> None:
        nonlocal cases_run
        cases_run += 1
        arg_str = ", ".join(f"{k}={v!r}" for k, v in call_kwargs.items())
        try:
            res = asyncio.run(fn(**call_kwargs)) if inspect.iscoroutinefunction(fn) else fn(**call_kwargs)
        except ValueError:
            return
        except Exception as exc:
            inv = invariants[0]
            last_failure.clear()
            last_failure.update(
                {
                    "invariant": inv,
                    "kwargs": dict(call_kwargs),
                    "steps": [f"{fn.__qualname__}({arg_str}) raised {type(exc).__name__}: {exc}"],
                    "result": f"Unhandled {type(exc).__name__}: {exc}",
                }
            )
            raise AssertionError(f"Unhandled exception: {exc}") from exc

        for inv in invariants:
            ok = _eval_expr(inv.expression, {"result": res, **call_kwargs})
            if not ok:
                last_failure.clear()
                last_failure.update(
                    {
                        "invariant": inv,
                        "kwargs": dict(call_kwargs),
                        "steps": [f"{fn.__qualname__}({arg_str}) -> {res!r}"],
                        "result": res,
                    }
                )
                raise AssertionError(f"Invariant violated: {inv.expression}")

    try:
        prop_runner()
    except (AssertionError, BaseExceptionGroup):
        if last_failure:
            inv = last_failure["invariant"]
            ser_kwargs = _serialize_val(last_failure["kwargs"])
            ser_result = _serialize_val(last_failure["result"])
            return (
                InvariantViolation(
                    invariant=inv,
                    verification_method="Property-Based Shrinking via Hypothesis",
                    failing_target=fn.__qualname__,
                    counterexample={"arguments": ser_kwargs},
                    trace_steps=last_failure["steps"],
                    expected_state_desc=f"Postcondition invariant `{inv.expression}` must hold on return value `result`",
                    actual_state={"arguments": ser_kwargs, "result": ser_result},
                    seed=seed_val,
                    cases_evaluated=cases_run,
                    domain_bounds=bounds_desc,
                ),
                cases_run,
                bounds_desc,
            )

    return None, cases_run, bounds_desc


def _rehydrate_args(kwargs: dict[str, Any], fn: Callable[..., Any]) -> dict[str, Any]:
    sig = inspect.signature(fn)
    fn_ns = getattr(fn, "__globals__", {})
    eval_ns = {
        "int": int,
        "float": float,
        "str": str,
        "bool": bool,
        "list": list,
        "dict": dict,
        "tuple": tuple,
        "set": set,
        "frozenset": frozenset,
        "Decimal": Decimal,
        "decimal": decimal,
        "date": date,
        "datetime": datetime,
        "UUID": uuid.UUID,
        "uuid": uuid,
        "bytes": bytes,
        "bytearray": bytearray,
        "Literal": Literal,
        "Optional": Optional,
        "Union": Union,
        "None": None,
        **fn_ns,
    }
    rehydrated: dict[str, Any] = {}
    for k, v in kwargs.items():
        param = sig.parameters.get(k)
        ann = param.annotation if param is not None else Any
        if isinstance(ann, str):
            s_ann = ann.strip()
            if s_ann in fn_ns:
                ann = fn_ns[s_ann]
            else:
                try:
                    ann = eval(s_ann, {"__builtins__": {}}, eval_ns)
                except Exception:
                    pass
        origin = get_origin(ann)
        if isinstance(v, list):
            if ann in (tuple, "tuple") or origin is tuple:
                rehydrated[k] = tuple(v)
                continue
            if ann in (set, "set") or origin is set:
                rehydrated[k] = set(v)
                continue
            if ann in (frozenset, "frozenset") or origin is frozenset:
                rehydrated[k] = frozenset(v)
                continue
        if isinstance(v, dict) and inspect.isclass(ann) and dataclasses.is_dataclass(ann):
            rehydrated[k] = ann(**v)
            continue
        if ann in (Decimal, "Decimal", "decimal.Decimal") and not isinstance(v, Decimal):
            rehydrated[k] = Decimal(str(v))
            continue
        if ann in (datetime, "datetime", "datetime.datetime") and isinstance(v, str):
            rehydrated[k] = datetime.fromisoformat(v)
            continue
        if ann in (date, "date", "datetime.date") and isinstance(v, str):
            rehydrated[k] = date.fromisoformat(v)
            continue
        if ann in (uuid.UUID, "UUID", "uuid.UUID"):
            if isinstance(v, str):
                try:
                    rehydrated[k] = uuid.UUID(v)
                except (ValueError, AttributeError, TypeError):
                    rehydrated[k] = v
            else:
                rehydrated[k] = v
            continue
        if ann in (bytes, "bytes"):
            if isinstance(v, str):
                try:
                    rehydrated[k] = bytes.fromhex(v)
                except ValueError:
                    rehydrated[k] = v.encode("utf-8")
            elif isinstance(v, (bytes, bytearray)):
                rehydrated[k] = bytes(v)
            else:
                try:
                    rehydrated[k] = bytes(v)
                except Exception:
                    rehydrated[k] = v
            continue
        if ann in (bytearray, "bytearray"):
            if isinstance(v, str):
                try:
                    rehydrated[k] = bytearray.fromhex(v)
                except ValueError:
                    rehydrated[k] = bytearray(v.encode("utf-8"))
            elif isinstance(v, (bytes, bytearray)):
                rehydrated[k] = bytearray(v)
            else:
                try:
                    rehydrated[k] = bytearray(v)
                except Exception:
                    rehydrated[k] = v
            continue
        if isinstance(ann, type) and issubclass(ann, enum.Enum) and not isinstance(v, ann):
            for member in ann:
                if member.value == v or member.name == v:
                    rehydrated[k] = member
                    break
            else:
                rehydrated[k] = v
            continue
        rehydrated[k] = v
    return rehydrated


def replay_counterexample(filepath: str | Path, violation: InvariantViolation) -> bool:
    """
    Replay the exact minimal counterexample against the target file.
    Returns True if the violation is FIXED (invariant holds), False if it still fails.
    """
    module = load_module_from_path(filepath)
    inv = violation.invariant

    if violation.verification_method == "Deterministic Thread Interleaving Check":
        cls = getattr(module, inv.target_name, None)
        if cls is None:
            return False
        c_viol, _ = explore_interleavings(cls, [inv], seed_val=violation.seed, max_schedules=10)
        return c_viol is None

    if inv.kind == "class":
        cls = getattr(module, inv.target_name, None)
        if cls is None:
            return False
        instance = _instantiate_class(cls)
        for step in violation.counterexample.get("call_sequence", []):
            m_fn = getattr(instance, step["method"])
            call_args = _rehydrate_args(step["args"], m_fn)
            try:
                if inspect.iscoroutinefunction(m_fn):
                    asyncio.run(m_fn(**call_args))
                else:
                    m_fn(**call_args)
            except ValueError:
                pass
            if not _eval_expr(inv.expression, {"self": instance}):
                return False
        return True

    fn = getattr(module, inv.target_name, None)
    if fn is None:
        return False
    kwargs = _rehydrate_args(violation.counterexample.get("arguments", {}), fn)
    try:
        res = asyncio.run(fn(**kwargs)) if inspect.iscoroutinefunction(fn) else fn(**kwargs)
    except ValueError:
        return True
    except Exception:
        return False
    return _eval_expr(inv.expression, {"result": res, **kwargs})

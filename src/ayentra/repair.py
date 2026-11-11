from __future__ import annotations

import ast
import difflib
import importlib
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ayentra.engine import InvariantViolation, replay_counterexample, run_verification_engine
from ayentra.regression import RegressionRunResult, run_pytest_suite


@dataclass
class PatchVerificationResult:
    original_filepath: str
    patched_source: str
    unified_diff: str
    counterexample_passed: bool
    invariant_sweep_passed: bool
    invariant_cases_tested: int
    regression_result: RegressionRunResult
    verification_duration_ms: float
    repair_strategy: str

    @property
    def is_verified(self) -> bool:
        return (
            self.counterexample_passed
            and self.invariant_sweep_passed
            and self.regression_result.passed
            and bool(self.unified_diff.strip())
        )

    @property
    def status_label(self) -> str:
        return "VERIFIED CANDIDATE FIX" if self.is_verified else "UNVERIFIED CANDIDATE"


def generate_and_verify_patch(
    filepath: str | Path,
    violation: InvariantViolation,
    *,
    repair_hook: Callable[[str, InvariantViolation], str] | str | None = None,
    max_examples: int = 120,
) -> PatchVerificationResult:
    path = Path(filepath).resolve()
    original_source = path.read_text(encoding="utf-8")

    if repair_hook is not None:
        hook_fn = _resolve_hook(repair_hook)
        candidate_source = hook_fn(original_source, violation)
        strategy_name = "Pluggable Repair Hook + Sandbox Gate"
    else:
        candidate_source, strategy_name = _synthesize_deterministic_patch(original_source, violation)

    return verify_candidate_source(
        filepath=path,
        original_source=original_source,
        candidate_source=candidate_source,
        violation=violation,
        strategy_name=strategy_name,
        max_examples=max_examples,
    )


def verify_candidate_source(
    filepath: str | Path,
    original_source: str,
    candidate_source: str,
    violation: InvariantViolation,
    strategy_name: str = "Deterministic AST Guard Synthesis",
    max_examples: int = 120,
) -> PatchVerificationResult:
    t0 = time.perf_counter()
    path = Path(filepath).resolve()

    diff_lines = list(
        difflib.unified_diff(
            original_source.splitlines(keepends=True),
            candidate_source.splitlines(keepends=True),
            fromfile=f"a/{path.name}",
            tofile=f"b/{path.name}",
        )
    )
    unified_diff = "".join(diff_lines)

    with tempfile.TemporaryDirectory(prefix="ayentra_sandbox_", ignore_cleanup_errors=True) as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        project_root = _detect_project_root(path)
        rel_target = path.relative_to(project_root)

        shutil.copytree(
            project_root,
            tmp_dir,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(
                ".venv",
                "__pycache__",
                ".git",
                ".pytest_cache",
                ".hypothesis",
                "node_modules",
                "build",
                "dist",
                ".tox",
                "*.egg-info",
                ".mypy_cache",
                ".ruff_cache",
            ),
        )
        sandbox_target = tmp_dir / rel_target
        sandbox_target.write_text(candidate_source, encoding="utf-8")

        ce_passed = replay_counterexample(sandbox_target, violation)
        sweep_res = run_verification_engine(
            sandbox_target,
            seed_val=violation.seed,
            max_examples=max_examples,
        )
        sweep_passed = len(sweep_res.violations) == 0
        reg_res = run_pytest_suite(tmp_dir)

    duration_ms = (time.perf_counter() - t0) * 1000.0
    return PatchVerificationResult(
        original_filepath=str(path),
        patched_source=candidate_source,
        unified_diff=unified_diff,
        counterexample_passed=ce_passed,
        invariant_sweep_passed=sweep_passed,
        invariant_cases_tested=sweep_res.total_cases_evaluated,
        regression_result=reg_res,
        verification_duration_ms=duration_ms,
        repair_strategy=strategy_name,
    )


def _detect_project_root(target_path: Path) -> Path:
    curr = target_path.parent
    for candidate in [curr, *curr.parents]:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return target_path.parent


def _resolve_hook(hook: Callable[[str, InvariantViolation], str] | str) -> Callable[[str, InvariantViolation], str]:
    if callable(hook):
        return hook
    if ":" not in hook:
        raise ValueError("Repair hook spec must be formatted as 'module_name:function_name'")
    mod_name, fn_name = hook.split(":", 1)
    mod = importlib.import_module(mod_name)
    return getattr(mod, fn_name)


def synthesize_zero_division_guard_node(
    denominator: str,
    *,
    early_return: str | None = None,
) -> ast.If:
    """Synthesize an AST guard statement for zero denominators."""
    # ponytail: minimal guard checking denominator == 0 with explicit ValueError or early return
    if early_return is not None:
        body = ast.parse(f"return {early_return}").body
    else:
        body = ast.parse(f"raise ValueError('{denominator} must be non-zero')").body
    return ast.If(
        test=ast.Compare(
            left=ast.parse(denominator).body[0].value,  # type: ignore[attr-defined]
            ops=[ast.Eq()],
            comparators=[ast.Constant(value=0)],
        ),
        body=body,
        orelse=[],
    )


def synthesize_none_guard_node(
    param_name: str,
    *,
    early_return: str | None = None,
) -> ast.If:
    """Synthesize an AST guard statement for None-type boundary dereferencing."""
    # ponytail: minimal guard checking param is None with explicit ValueError or early return
    if early_return is not None:
        body = ast.parse(f"return {early_return}").body
    else:
        body = ast.parse(f"raise ValueError('{param_name} must not be None')").body
    return ast.If(
        test=ast.Compare(
            left=ast.Name(id=param_name, ctx=ast.Load()),
            ops=[ast.Is()],
            comparators=[ast.Constant(value=None)],
        ),
        body=body,
        orelse=[],
    )


def _find_target_functions(
    tree: ast.Module,
    target_name: str,
    failing_target: str = "",
) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Find function or method nodes matching target_name or failing_target."""
    matches: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    names_to_match = {target_name}
    if failing_target:
        names_to_match.add(failing_target)
        if "." in failing_target:
            names_to_match.add(failing_target.split(".")[-1])
    if "." in target_name:
        names_to_match.add(target_name.split(".")[-1])

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in names_to_match:
                matches.append(node)
        elif isinstance(node, ast.ClassDef):
            is_target_class = node.name in names_to_match
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name in names_to_match or (is_target_class and not item.name.startswith("_")):
                        matches.append(item)
    return matches


def _is_zero_division_violation(violation: InvariantViolation, tree: ast.Module) -> bool:
    """Determine if an invariant violation stems from a zero denominator."""
    actual_res = str(violation.actual_state.get("result", ""))
    if "ZeroDivisionError" in actual_res or "division by zero" in actual_res:
        return True
    if any("ZeroDivisionError" in step or "division by zero" in step for step in violation.trace_steps):
        return True
    target_fns = _find_target_functions(tree, violation.invariant.target_name, violation.failing_target)
    ce_args = violation.counterexample.get("arguments", {})
    for fn in target_fns:
        for child in ast.walk(fn):
            if isinstance(child, ast.BinOp) and isinstance(child.op, (ast.Div, ast.FloorDiv, ast.Mod)):
                if isinstance(child.right, ast.Name) and ce_args.get(child.right.id) in (0, 0.0):
                    return True
    return False


def _is_none_dereference_violation(violation: InvariantViolation, tree: ast.Module) -> bool:
    """Determine if an invariant violation stems from None-type dereferencing."""
    actual_res = str(violation.actual_state.get("result", ""))
    if "AttributeError" in actual_res or ("TypeError" in actual_res and "NoneType" in actual_res):
        return True
    if any("NoneType" in step or "AttributeError" in step for step in violation.trace_steps):
        return True
    target_fns = _find_target_functions(tree, violation.invariant.target_name, violation.failing_target)
    ce_args = violation.counterexample.get("arguments", {})
    for fn in target_fns:
        for a in fn.args.args:
            if a.arg != "self" and ce_args.get(a.arg) is None and a.arg in ce_args:
                ann = ast.unparse(a.annotation).lower() if a.annotation else ""
                if "none" in ann or "optional" in ann:
                    return True
                for child in ast.walk(fn):
                    if isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name) and child.value.id == a.arg:
                        return True
                    if isinstance(child, ast.Subscript) and isinstance(child.value, ast.Name) and child.value.id == a.arg:
                        return True
    return False


def _apply_zero_division_guard_transform(
    source: str,
    tree: ast.Module,
    target_name: str,
    violation: InvariantViolation | None = None,
    *,
    early_return: str | None = None,
) -> str:
    """Synthesize deterministic non-zero denominator guards at the function boundary."""
    # ponytail: synthesize minimal non-zero guard at top of function without rewriting body
    failing_target = violation.failing_target if violation else ""
    target_fns = _find_target_functions(tree, target_name, failing_target)
    ce_args = violation.counterexample.get("arguments", {}) if violation else {}
    inv_expr = violation.invariant.expression if violation else ""

    for fn_node in target_fns:
        param_names = [a.arg for a in fn_node.args.args if a.arg != "self"]
        param_set = set(param_names)

        seen_guards = {ast.unparse(stmt).strip() for stmt in fn_node.body}
        new_guards: list[ast.stmt] = []

        divisors: list[str] = []
        for child in ast.walk(fn_node):
            if isinstance(child, ast.BinOp) and isinstance(child.op, (ast.Div, ast.FloorDiv, ast.Mod)):
                right = child.right
                if isinstance(right, ast.Name):
                    if right.id in param_set and right.id not in divisors:
                        divisors.append(right.id)
                elif isinstance(right, ast.Call) and isinstance(right.func, ast.Name) and right.func.id == "len":
                    if right.args and isinstance(right.args[0], ast.Name) and right.args[0].id in param_set:
                        seq_name = right.args[0].id
                        empty_guard = ast.parse(f"if not {seq_name}:\n    raise ValueError('{seq_name} must not be empty')").body[0]
                        if ast.unparse(empty_guard).strip() not in seen_guards:
                            seen_guards.add(ast.unparse(empty_guard).strip())
                            new_guards.append(empty_guard)
                        if f"len({seq_name})" not in divisors:
                            divisors.append(f"len({seq_name})")
                elif not (isinstance(right, ast.Constant) and right.value not in (0, 0.0)):
                    d_src = ast.unparse(right).strip()
                    if d_src and d_src not in divisors:
                        divisors.append(d_src)

        for d in divisors:
            g_node = synthesize_zero_division_guard_node(d, early_return=early_return)
            g_str = ast.unparse(g_node).strip()
            if g_str not in seen_guards:
                seen_guards.add(g_str)
                new_guards.append(g_node)

        # Handle postconditions if invariant restricts result (e.g. result >= 0)
        has_post = bool(inv_expr and "result" in inv_expr and inv_expr.strip() != "math.isfinite(result)")
        new_body: list[ast.stmt] = list(new_guards)
        for stmt in fn_node.body:
            if has_post and isinstance(stmt, ast.Return) and stmt.value is not None:
                ret_expr = ast.unparse(stmt.value)
                post_block = ast.parse(
                    f"_raw_result = {ret_expr}\n"
                    f"if not ({inv_expr.replace('result', '_raw_result')}):\n"
                    f"    raise ValueError('Postcondition violated')\n"
                    f"return _raw_result\n"
                ).body
                new_body.extend(post_block)
            else:
                new_body.append(stmt)
        fn_node.body = new_body

    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def _apply_none_guard_transform(
    source: str,
    tree: ast.Module,
    target_name: str,
    violation: InvariantViolation | None = None,
    *,
    early_return: str | None = None,
) -> str:
    """Synthesize deterministic None-type boundary guards at the function boundary."""
    # ponytail: synthesize minimal if obj is None guard at top of function
    failing_target = violation.failing_target if violation else ""
    target_fns = _find_target_functions(tree, target_name, failing_target)
    ce_args = violation.counterexample.get("arguments", {}) if violation else {}
    inv_expr = violation.invariant.expression if violation else ""

    for fn_node in target_fns:
        param_names = [a.arg for a in fn_node.args.args if a.arg != "self"]
        param_anns = {a.arg: (ast.unparse(a.annotation).lower() if a.annotation else "") for a in fn_node.args.args if a.arg != "self"}

        seen_guards = {ast.unparse(stmt).strip() for stmt in fn_node.body}
        new_guards: list[ast.stmt] = []

        none_params: list[str] = []

        for p in param_names:
            ann = param_anns.get(p, "")
            is_optional = "none" in ann or "optional" in ann
            was_none = ce_args.get(p) is None and p in ce_args
            is_dereferenced = False
            for child in ast.walk(fn_node):
                if isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name) and child.value.id == p:
                    is_dereferenced = True
                    break
                if isinstance(child, ast.Subscript) and isinstance(child.value, ast.Name) and child.value.id == p:
                    is_dereferenced = True
                    break
            if (was_none and is_dereferenced) or (is_optional and is_dereferenced) or (not ann and is_dereferenced and was_none):
                if p not in none_params:
                    none_params.append(p)

        for p in none_params:
            g_node = synthesize_none_guard_node(p, early_return=early_return)
            g_str = ast.unparse(g_node).strip()
            if g_str not in seen_guards:
                seen_guards.add(g_str)
                new_guards.append(g_node)

        # Handle postconditions if invariant restricts result (e.g. result >= 0)
        has_post = bool(inv_expr and "result" in inv_expr)
        new_body: list[ast.stmt] = list(new_guards)
        for stmt in fn_node.body:
            if has_post and isinstance(stmt, ast.Return) and stmt.value is not None:
                ret_expr = ast.unparse(stmt.value)
                post_block = ast.parse(
                    f"_raw_result = {ret_expr}\n"
                    f"if not ({inv_expr.replace('result', '_raw_result')}):\n"
                    f"    raise ValueError('Postcondition violated')\n"
                    f"return _raw_result\n"
                ).body
                new_body.extend(post_block)
            else:
                new_body.append(stmt)
        fn_node.body = new_body

    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def _synthesize_deterministic_patch(
    source: str,
    violation: InvariantViolation,
) -> tuple[str, str]:
    tree = ast.parse(source)

    if violation.verification_method == "Deterministic Thread Interleaving Check" or violation.invariant.check_concurrency:
        patched = _apply_concurrency_lock_transform(source, tree, violation.invariant.target_name)
        return patched, "AST Concurrency Lock & Boundary Guard Synthesis"

    # Deterministic zero-division template
    if _is_zero_division_violation(violation, tree):
        patched = _apply_zero_division_guard_transform(
            source, tree, violation.invariant.target_name, violation=violation
        )
        return patched, "AST Zero-Division Guard Synthesis"

    # Deterministic None-type boundary template
    if _is_none_dereference_violation(violation, tree):
        patched = _apply_none_guard_transform(
            source, tree, violation.invariant.target_name, violation=violation
        )
        return patched, "AST None-Type Boundary Guard Synthesis"

    if violation.invariant.kind == "class":
        patched = _apply_class_conservation_transform(source, tree, violation.invariant.target_name)
        return patched, "AST State Precondition & Conservation Guard Synthesis"

    patched = _apply_function_guard_transform(
        source,
        tree,
        violation.invariant.target_name,
        violation=violation,
    )
    return patched, "AST Input Sanitization & Finite-Value Guard Synthesis"


def _select_numeric_params(item: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    numeric: list[str] = []
    for a in item.args.args:
        if a.arg == "self":
            continue
        ann = ast.unparse(a.annotation).strip().lower() if a.annotation is not None else ""
        if not ann or ann in {"int", "float", "decimal", "decimal.decimal", "int | float", "float | int", "number"}:
            numeric.append(a.arg)
    return numeric


def _apply_concurrency_lock_transform(source: str, tree: ast.Module, class_name: str) -> str:
    has_threading = any(
        isinstance(n, ast.Import) and any(alias.name == "threading" for alias in n.names)
        for n in tree.body
    )
    if not has_threading:
        import_node = ast.Import(names=[ast.alias(name="threading", asname=None)])
        insert_idx = 0
        for i, stmt in enumerate(tree.body):
            if isinstance(stmt, ast.ImportFrom) and stmt.module == "__future__":
                insert_idx = i + 1
        tree.body.insert(insert_idx, import_node)

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    has_lock_init = any(
                        isinstance(stmt, ast.Assign)
                        and any(
                            isinstance(t, ast.Attribute)
                            and isinstance(t.value, ast.Name)
                            and t.value.id == "self"
                            and t.attr == "_lock"
                            for t in stmt.targets
                        )
                        for stmt in item.body
                    )
                    if not has_lock_init:
                        lock_assign = ast.parse("self._lock = threading.Lock()").body[0]
                        item.body.append(lock_assign)
                elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and not item.name.startswith("_"):
                    already_locked = (
                        len(item.body) == 1
                        and isinstance(item.body[0], ast.With)
                        and any(ast.unparse(wi.context_expr).strip() == "self._lock" for wi in item.body[0].items)
                    )
                    inner_body = item.body[0].body if already_locked else item.body  # type: ignore[attr-defined]
                    numeric_params = _select_numeric_params(item)
                    returns_bool = (
                        isinstance(item.returns, ast.Name) and item.returns.id == "bool"
                    ) or (
                        isinstance(item.returns, ast.Constant) and item.returns.value == "bool"
                    )
                    existing_src = {ast.unparse(s).strip() for s in inner_body}
                    guards: list[ast.stmt] = []
                    for p in numeric_params:
                        if returns_bool:
                            g_stmt = ast.parse(f"if {p} <= 0:\n    return False").body[0]
                        else:
                            g_stmt = ast.parse(f"if {p} <= 0:\n    raise ValueError('{p} must be positive')").body[0]
                        if ast.unparse(g_stmt).strip() not in existing_src:
                            guards.append(g_stmt)
                    if already_locked:
                        item.body[0].body = guards + inner_body  # type: ignore[attr-defined]
                    else:
                        with_stmt = ast.With(
                            items=[ast.withitem(context_expr=ast.parse("self._lock").body[0].value)],  # type: ignore[attr-defined]
                            body=guards + inner_body,
                        )
                        item.body = [with_stmt]

    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def _is_inadequate_conservation_guard(test_node: ast.expr, param_names: set[str], attrs: set[str]) -> bool:
    # ponytail: match only simple capacity guards like units <= self.available or self.available >= units
    if isinstance(test_node, ast.Compare) and len(test_node.ops) == 1 and len(test_node.comparators) == 1:
        op = test_node.ops[0]
        left = test_node.left
        right = test_node.comparators[0]
        if isinstance(op, (ast.LtE, ast.Lt)):
            if isinstance(left, ast.Name) and left.id in param_names:
                if isinstance(right, ast.Attribute) and isinstance(right.value, ast.Name) and right.value.id == "self" and right.attr in attrs:
                    return True
        if isinstance(op, (ast.GtE, ast.Gt)):
            if isinstance(right, ast.Name) and right.id in param_names:
                if isinstance(left, ast.Attribute) and isinstance(left.value, ast.Name) and left.value.id == "self" and left.attr in attrs:
                    return True
    return False


def _apply_class_conservation_transform(source: str, tree: ast.Module, class_name: str) -> str:
    # ponytail: apply state preconditions and conservation guards for subtracted attributes and parameters
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) or item.name.startswith("_"):
                    continue
                numeric_params = _select_numeric_params(item)

                subtracted_param_pairs: list[tuple[str, str]] = []
                constant_subtracted_attrs: list[str] = []
                subtracted_attrs: list[str] = []
                for child in ast.walk(item):
                    if (
                        isinstance(child, ast.AugAssign)
                        and isinstance(child.op, ast.Sub)
                        and isinstance(child.target, ast.Attribute)
                        and isinstance(child.target.value, ast.Name)
                        and child.target.value.id == "self"
                    ):
                        attr = child.target.attr
                        subtracted_attrs.append(attr)
                        if isinstance(child.value, ast.Name) and child.value.id in numeric_params:
                            subtracted_param_pairs.append((child.value.id, attr))
                        else:
                            constant_subtracted_attrs.append(attr)

                if not subtracted_param_pairs and not constant_subtracted_attrs:
                    continue

                new_body: list[ast.stmt] = []
                seen_guards: set[str] = set()
                for p, attr in subtracted_param_pairs:
                    g_pos = ast.parse(f"if {p} <= 0:\n    raise ValueError('{p} must be positive')").body[0]
                    g_pos_str = ast.unparse(g_pos).strip()
                    if g_pos_str not in seen_guards:
                        seen_guards.add(g_pos_str)
                        new_body.append(g_pos)

                    g_stmt = ast.parse(
                        f"if {p} > self.{attr}:\n    raise ValueError('Insufficient {attr} for operation')"
                    ).body[0]
                    g_str = ast.unparse(g_stmt).strip()
                    if g_str not in seen_guards:
                        seen_guards.add(g_str)
                        new_body.append(g_stmt)

                for attr in constant_subtracted_attrs:
                    g_stmt = ast.parse(
                        f"if self.{attr} <= 0:\n    raise ValueError('Insufficient {attr} for operation')"
                    ).body[0]
                    g_str = ast.unparse(g_stmt).strip()
                    if g_str not in seen_guards:
                        seen_guards.add(g_str)
                        new_body.append(g_stmt)

                filtered_original: list[ast.stmt] = []
                for stmt in item.body:
                    stmt_str = ast.unparse(stmt).strip()
                    if stmt_str in seen_guards:
                        continue
                    if isinstance(stmt, ast.If) and _is_inadequate_conservation_guard(
                        stmt.test, set(numeric_params), set(subtracted_attrs)
                    ):
                        filtered_original.extend(stmt.body)
                    else:
                        filtered_original.append(stmt)

                item.body = new_body + filtered_original

    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def _negate_compare(left: ast.expr, op: ast.cmpop, right: ast.expr) -> str | None:
    l_src, r_src = ast.unparse(left), ast.unparse(right)
    inv_map: dict[type[ast.cmpop], str] = {
        ast.Gt: "<=",
        ast.GtE: "<",
        ast.Lt: ">=",
        ast.LtE: ">",
        ast.NotEq: "==",
        ast.Eq: "!=",
        ast.In: "not in",
        ast.NotIn: "in",
    }
    inv_op = inv_map.get(type(op))
    return f"{l_src} {inv_op} {r_src}" if inv_op else None


def _synthesize_function_preconditions(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    violation: InvariantViolation | None,
) -> list[ast.stmt]:
    # ponytail: single-pass AST walk for division/subscript/attribute/domain preconditions; use symbolic solver if nonlinear cross-variable constraints arise
    param_names = [a.arg for a in node.args.args if a.arg != "self"]
    param_set = set(param_names)
    param_anns: dict[str, str] = {}
    conds: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add_guard(cond_expr: str, msg: str) -> None:
        if cond_expr not in seen:
            seen.add(cond_expr)
            conds.append((cond_expr, msg))

    for param in node.args.args:
        if param.arg == "self":
            continue
        ann_str = ast.unparse(param.annotation).lower() if param.annotation is not None else ""
        param_anns[param.arg] = ann_str
        if ann_str == "float":
            add_guard(f"not math.isfinite({param.arg})", f"{param.arg} must be finite")
        elif "decimal" in ann_str:
            add_guard(f"not {param.arg}.is_finite()", f"{param.arg} must be finite")

    has_value_error_handler = False
    checks_isdigit = False
    int_cast_str_params: list[str] = []
    uuid_cast_params: list[str] = []
    fromhex_cast_params: list[str] = []

    for child in ast.walk(node):
        if isinstance(child, ast.ExceptHandler):
            if child.type is None:
                has_value_error_handler = True
            elif isinstance(child.type, ast.Name) and child.type.id in {"ValueError", "Exception", "BaseException"}:
                has_value_error_handler = True
            elif isinstance(child.type, ast.Tuple) and any(
                isinstance(e, ast.Name) and e.id in {"ValueError", "Exception", "BaseException"}
                for e in child.type.elts
            ):
                has_value_error_handler = True
        elif isinstance(child, ast.Call):
            if isinstance(child.func, ast.Attribute):
                if child.func.attr == "isdigit":
                    checks_isdigit = True
                elif (
                    child.func.attr == "UUID"
                    and isinstance(child.func.value, ast.Name)
                    and child.func.value.id == "uuid"
                    and (child.args or child.keywords)
                ):
                    target_arg = child.args[0] if child.args else (child.keywords[0].value if child.keywords else None)
                    if isinstance(target_arg, ast.Name) and target_arg.id in param_set:
                        uuid_cast_params.append(target_arg.id)
                elif (
                    child.func.attr == "fromhex"
                    and isinstance(child.func.value, ast.Name)
                    and child.func.value.id in {"bytes", "bytearray"}
                    and (child.args or child.keywords)
                ):
                    target_arg = child.args[0] if child.args else (child.keywords[0].value if child.keywords else None)
                    if isinstance(target_arg, ast.Name) and target_arg.id in param_set:
                        fromhex_cast_params.append(target_arg.id)
            elif isinstance(child.func, ast.Name):
                if child.func.id == "int" and child.args:
                    arg0 = child.args[0]
                    if isinstance(arg0, ast.Name) and arg0.id in param_set:
                        if "str" in param_anns.get(arg0.id, ""):
                            int_cast_str_params.append(arg0.id)
                elif child.func.id == "UUID" and (child.args or child.keywords):
                    target_arg = child.args[0] if child.args else (child.keywords[0].value if child.keywords else None)
                    if isinstance(target_arg, ast.Name) and target_arg.id in param_set:
                        uuid_cast_params.append(target_arg.id)
                elif child.func.id in {"min", "max"} and len(child.args) == 1:
                    arg0 = child.args[0]
                    if isinstance(arg0, ast.Name) and arg0.id in param_set:
                        add_guard(f"not {arg0.id}", f"{arg0.id} must not be empty")
                elif child.func.id == "next" and child.args:
                    arg0 = child.args[0]
                    if (
                        isinstance(arg0, ast.Call)
                        and isinstance(arg0.func, ast.Name)
                        and arg0.func.id == "iter"
                        and arg0.args
                        and isinstance(arg0.args[0], ast.Name)
                        and arg0.args[0].id in param_set
                    ):
                        col_name = arg0.args[0].id
                        add_guard(f"not {col_name}", f"{col_name} must not be empty")
        elif (
            isinstance(child, ast.Attribute)
            and isinstance(child.ctx, ast.Load)
            and isinstance(child.value, ast.Name)
            and child.value.id in param_set
        ):
            p_id = child.value.id
            ann_str = param_anns.get(p_id, "")
            is_builtin = (
                ann_str in {"str", "int", "float", "bool", "bytes", "bytearray", "uuid", "uuid.uuid", "decimal", "date", "datetime"}
                or ann_str.startswith(("list", "dict", "tuple", "set", "frozenset", "sequence", "decimal.", "datetime."))
            )
            if "none" in ann_str or "optional" in ann_str or not is_builtin:
                add_guard(f"{p_id} is None", f"{p_id} must not be None")
        elif isinstance(child, ast.BinOp) and isinstance(child.op, ast.Sub):
            if (
                isinstance(child.left, ast.Name)
                and isinstance(child.right, ast.Name)
                and child.left.id in param_set
                and child.right.id in param_set
            ):
                l_id, r_id = child.left.id, child.right.id
                l_ann, r_ann = param_anns.get(l_id, ""), param_anns.get(r_id, "")
                if any(t in l_ann or t in r_ann for t in ("date", "datetime")) or (
                    "end" in l_id.lower() and "start" in r_id.lower()
                ):
                    add_guard(f"{l_id} < {r_id}", f"{l_id} must not precede {r_id}")
        elif isinstance(child, ast.BinOp) and isinstance(child.op, (ast.Div, ast.FloorDiv, ast.Mod)):
            if not (isinstance(child.right, ast.Constant) and child.right.value not in (0, 0.0)):
                div_src = ast.unparse(child.right)
                if (
                    isinstance(child.right, ast.Call)
                    and isinstance(child.right.func, ast.Name)
                    and child.right.func.id == "len"
                    and len(child.right.args) == 1
                    and isinstance(child.right.args[0], ast.Name)
                    and child.right.args[0].id in param_set
                ):
                    col_name = child.right.args[0].id
                    add_guard(f"not {col_name}", f"{col_name} must not be empty")
                add_guard(f"{div_src} == 0", f"{div_src} must be non-zero")
        elif isinstance(child, ast.Subscript) and isinstance(child.ctx, ast.Load):
            val_src = ast.unparse(child.value)
            slc = child.slice
            slc_src = ast.unparse(slc)
            is_int_idx = (
                (isinstance(slc, ast.Constant) and isinstance(slc.value, int))
                or (isinstance(slc, ast.UnaryOp) and isinstance(slc.op, ast.USub))
                or (
                    isinstance(slc, ast.BinOp)
                    and isinstance(slc.op, (ast.Add, ast.Sub, ast.Mult, ast.FloorDiv, ast.Mod))
                )
            )
            if isinstance(child.value, ast.Name) and child.value.id in param_set:
                ann_str = param_anns.get(child.value.id, "")
                is_dict_param = "dict" in ann_str or "mapping" in ann_str
                if isinstance(slc, ast.Constant) and isinstance(slc.value, str):
                    add_guard(f"not {val_src}", f"{val_src} must not be empty")
                    add_guard(f"{slc_src} not in {val_src}", "Missing required key")
                elif is_dict_param:
                    add_guard(f"not {val_src}", f"{val_src} must not be empty")
                    add_guard(f"{slc_src} not in {val_src}", "Missing required key")
                elif is_int_idx:
                    add_guard(
                        f"not (-len({val_src}) <= {slc_src} < len({val_src}))",
                        f"index {slc_src} out of bounds for {val_src}",
                    )
                elif isinstance(slc, ast.Name) and slc.id in param_set:
                    slc_ann = param_anns.get(slc.id, "")
                    if slc_ann == "str":
                        add_guard(f"not {val_src}", f"{val_src} must not be empty")
                        add_guard(f"{slc_src} not in {val_src}", "Missing required key")
                    else:
                        add_guard(
                            f"(isinstance({val_src}, dict) and {slc_src} not in {val_src}) or "
                            f"(isinstance({val_src}, (list, tuple, str)) and not (-len({val_src}) <= {slc_src} < len({val_src})))",
                            "Missing required key",
                        )

    if not has_value_error_handler and not checks_isdigit:
        for p_id in int_cast_str_params:
            add_guard(f"not {p_id}.strip().lstrip('-+').isdigit()", "Invalid integer string")

    if not has_value_error_handler:
        for p_id in uuid_cast_params:
            add_guard(f"len({p_id}.strip()) not in (32, 36)", f"{p_id} must be a valid UUID string")
        for p_id in fromhex_cast_params:
            add_guard(f"len({p_id}.strip()) % 2 != 0", f"{p_id} must have an even hex length")

    if violation is not None:
        try:
            inv_tree = ast.parse(violation.invariant.expression, mode="eval")
            for sub in ast.walk(inv_tree):
                if isinstance(sub, ast.Compare):
                    names_in_cmp = {n.id for n in ast.walk(sub) if isinstance(n, ast.Name)}
                    if "result" in names_in_cmp or not (names_in_cmp & param_set):
                        continue
                    cur_left = sub.left
                    for op, comp in zip(sub.ops, sub.comparators):
                        neg = _negate_compare(cur_left, op, comp)
                        if neg:
                            add_guard(neg, f"precondition violated: {ast.unparse(sub)}")
                        cur_left = comp
        except SyntaxError:
            pass

        date_params = [
            p for p in param_names if any(t in param_anns.get(p, "") for t in ("date", "datetime"))
        ]
        if len(date_params) >= 2:
            p_start, p_end = date_params[0], date_params[1]
            if "end" in p_start.lower() and "start" in p_end.lower():
                p_start, p_end = p_end, p_start
            add_guard(f"{p_end} < {p_start}", f"{p_end} must not precede {p_start}")

        actual_res = str(violation.actual_state.get("result", ""))
        ce_args = dict(violation.counterexample.get("arguments", {}))
        if not ce_args and "call_sequence" in violation.counterexample:
            for step in violation.counterexample.get("call_sequence", []):
                if isinstance(step, dict) and step.get("method") == node.name:
                    ce_args.update(step.get("args", {}))

        for p in param_names:
            if ce_args.get(p) is None or "AttributeError" in actual_res:
                ann_str = param_anns.get(p, "")
                if ce_args.get(p) is None or "none" in ann_str or "optional" in ann_str:
                    add_guard(f"{p} is None", f"{p} must not be None")

        for p in param_names:
            val = ce_args.get(p)
            ann_str = param_anns.get(p, "")
            is_bytes_ann = any(t in ann_str for t in ("bytes", "bytearray"))
            is_empty_bytes = (
                val == ""
                or val == b""
                or (isinstance(val, (bytes, bytearray)) and len(val) == 0)
            )
            if is_bytes_ann and is_empty_bytes:
                add_guard(f"not {p}", f"{p} must not be empty")

        for p in param_names:
            val = ce_args.get(p)
            ann_str = param_anns.get(p, "")
            is_uuid_ann = any(t in ann_str for t in ("uuid", "uuid.uuid"))
            if is_uuid_ann:
                is_nil_uuid = (
                    val in ("00000000-0000-0000-0000-000000000000", 0)
                    or getattr(val, "int", None) == 0
                    or (isinstance(val, uuid.UUID) and val.int == 0)
                )
                if is_nil_uuid:
                    add_guard(f"{p} == uuid.UUID(int=0)", f"{p} must not be nil UUID")
                elif isinstance(val, str) and len(val) not in (32, 36):
                    add_guard(f"not isinstance({p}, uuid.UUID)", f"{p} must be a valid UUID")

        if any(err in actual_res for err in ("IndexError", "KeyError", "ZeroDivisionError", "ValueError", "StopIteration", "InvalidOperation")):
            for p in param_names:
                val = ce_args.get(p)
                ann_str = param_anns.get(p, "")
                is_col_ann = any(t in ann_str for t in ("list", "tuple", "dict", "set", "frozenset", "sequence", "bytes", "bytearray"))
                if (isinstance(val, (list, tuple, dict, set, frozenset, bytes, bytearray)) and len(val) == 0) or (
                    val is not None and is_col_ann and hasattr(val, "__len__") and len(val) == 0
                ):
                    add_guard(f"not {p}", f"{p} must not be empty")

    stmts: list[ast.stmt] = []
    for cond_expr, msg in conds:
        stmts.extend(ast.parse(f"if {cond_expr}:\n    raise ValueError({msg!r})").body)
    return stmts


def _apply_function_guard_transform(
    source: str,
    tree: ast.Module,
    func_name: str,
    violation: InvariantViolation | None = None,
) -> str:
    has_math = any(
        isinstance(n, ast.Import) and any(alias.name == "math" for alias in n.names)
        for n in tree.body
    )
    if not has_math:
        insert_idx = 0
        for i, stmt in enumerate(tree.body):
            if isinstance(stmt, ast.ImportFrom) and stmt.module == "__future__":
                insert_idx = i + 1
        tree.body.insert(insert_idx, ast.Import(names=[ast.alias(name="math", asname=None)]))

    has_uuid = any(
        (isinstance(n, ast.Import) and any(alias.name == "uuid" for alias in n.names))
        or (isinstance(n, ast.ImportFrom) and n.module == "uuid")
        for n in tree.body
    )
    if not has_uuid:
        insert_idx = 0
        for i, stmt in enumerate(tree.body):
            if isinstance(stmt, ast.ImportFrom) and stmt.module == "__future__":
                insert_idx = i + 1
        tree.body.insert(insert_idx, ast.Import(names=[ast.alias(name="uuid", asname=None)]))

    inv_expr = violation.invariant.expression if violation is not None else ""

    target_nodes = _find_target_functions(tree, func_name, violation.failing_target if violation else "")
    if not target_nodes:
        target_nodes = [
            n for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == func_name
        ]

    for node in target_nodes:
            pre_guards = _synthesize_function_preconditions(node, violation)
            new_body: list[ast.stmt] = list(pre_guards)
            for stmt in node.body:
                if isinstance(stmt, ast.Return) and stmt.value is not None:
                    ret_expr = ast.unparse(stmt.value)
                    post_check = ""
                    if inv_expr:
                        post_check = (
                            f"result = _raw_result\n"
                            f"if not ({inv_expr}):\n"
                            f"    raise ValueError('Postcondition violated')\n"
                        )
                    sanitize_block = ast.parse(
                        f"_raw_result = {ret_expr}\n"
                        "if isinstance(_raw_result, dict):\n"
                        "    _raw_result = {\n"
                        "        k.strip(): v\n"
                        "        for k, v in _raw_result.items()\n"
                        "        if isinstance(k, str) and k.strip() and isinstance(v, (int, float)) and math.isfinite(v)\n"
                        "    }\n"
                        "elif isinstance(_raw_result, (int, float)) and not isinstance(_raw_result, bool) and not math.isfinite(_raw_result):\n"
                        "    raise ValueError('Non-finite return value')\n"
                        f"{post_check}"
                        "return _raw_result\n"
                    ).body
                    new_body.extend(sanitize_block)
                else:
                    new_body.append(stmt)
            node.body = new_body

    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"

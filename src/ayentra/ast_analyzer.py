from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class CandidateSuggestion:
    target_name: str
    kind: str
    suggested_expression: str
    rationale: str
    lineno: int
    label: str = "Candidate Suggestion (Requires Developer Approval)"


@dataclass
class ASTAnalysisResult:
    filepath: str
    explicit_decorator_lines: dict[tuple[str, str], int] = field(default_factory=dict)
    mutated_attributes: dict[str, set[str]] = field(default_factory=dict)
    has_lock_synchronization: dict[str, bool] = field(default_factory=dict)
    suggestions: list[CandidateSuggestion] = field(default_factory=list)


def analyze_source(filepath: str | Path) -> ASTAnalysisResult:
    path = Path(filepath)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    result = ASTAnalysisResult(filepath=str(path))

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            _analyze_class(node, result)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _analyze_function(node, result, parent_class=None)

    return result


def _extract_invariant_decorators(
    node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
    target_name: str,
    result: ASTAnalysisResult,
) -> set[str]:
    found: set[str] = set()
    for dec in node.decorator_list:
        if isinstance(dec, ast.Call):
            func_name = ""
            if isinstance(dec.func, ast.Name):
                func_name = dec.func.id
            elif isinstance(dec.func, ast.Attribute):
                func_name = dec.func.attr
            if func_name == "invariant" and dec.args:
                first_arg = dec.args[0]
                if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                    expr = first_arg.value.strip()
                    result.explicit_decorator_lines[(target_name, expr)] = dec.lineno
                    found.add(expr)
    return found


def _analyze_class(node: ast.ClassDef, result: ASTAnalysisResult) -> None:
    explicit = _extract_invariant_decorators(node, node.name, result)
    attrs_read: set[str] = set()
    attrs_mutated: set[str] = set()
    all_attrs: set[str] = set()
    has_lock = False

    for child in ast.walk(node):
        if isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name) and child.value.id == "self":
            all_attrs.add(child.attr)
            if isinstance(child.ctx, ast.Store):
                attrs_mutated.add(child.attr)
            elif isinstance(child.ctx, ast.Load):
                attrs_read.add(child.attr)
            if "lock" in child.attr.lower():
                has_lock = True
        elif isinstance(child, ast.With):
            for item in child.items:
                if "lock" in ast.unparse(item.context_expr).lower():
                    has_lock = True

    result.mutated_attributes[node.name] = attrs_mutated
    result.has_lock_synchronization[node.name] = has_lock

    for method in node.body:
        if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _analyze_function(method, result, parent_class=node.name)

    for attr in sorted(attrs_mutated):
        if attr in {"allocated", "available", "reserved", "stock", "balance", "count"}:
            expr = f"self.{attr} >= 0"
            if not any(expr in e for e in explicit):
                result.suggestions.append(
                    CandidateSuggestion(
                        target_name=node.name,
                        kind="class",
                        suggested_expression=expr,
                        rationale=f"Attribute 'self.{attr}' is mutated across methods; non-negativity guard may apply.",
                        lineno=node.lineno,
                    )
                )

    if "allocated" in all_attrs and "capacity" in all_attrs:
        expr = "self.allocated <= self.capacity"
        if not any(expr in e for e in explicit):
            result.suggestions.append(
                CandidateSuggestion(
                    target_name=node.name,
                    kind="class",
                    suggested_expression=expr,
                    rationale="Detected paired 'allocated' and 'capacity' state attributes.",
                    lineno=node.lineno,
                )
            )

    if {"available", "reserved", "initial_total"}.issubset(all_attrs):
        expr = "self.available + self.reserved == self.initial_total"
        if not any(expr in e for e in explicit):
            result.suggestions.append(
                CandidateSuggestion(
                    target_name=node.name,
                    kind="class",
                    suggested_expression=expr,
                    rationale="Detected conservation triplet ('available', 'reserved', 'initial_total').",
                    lineno=node.lineno,
                )
            )

    rmw_attrs = attrs_read.intersection(attrs_mutated) - {"_lock", "lock"}
    if rmw_attrs and not has_lock:
        result.suggestions.append(
            CandidateSuggestion(
                target_name=node.name,
                kind="class",
                suggested_expression=f"@invariant(..., check_concurrency=True) on {node.name}",
                rationale=f"Read-modify-write mutations on {sorted(rmw_attrs)} without lock synchronization.",
                lineno=node.lineno,
            )
        )


def _analyze_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    result: ASTAnalysisResult,
    parent_class: str | None,
) -> None:
    qualname = f"{parent_class}.{node.name}" if parent_class else node.name
    explicit = _extract_invariant_decorators(node, qualname, result)
    param_names = {a.arg for a in node.args.args if a.arg != "self"}
    optional_params: set[str] = set()
    str_params: set[str] = set()
    decimal_params: set[str] = set()
    for param in node.args.args:
        if param.arg == "self" or param.annotation is None:
            continue
        ann_src = ast.unparse(param.annotation)
        if "None" in ann_src or "Optional" in ann_src:
            optional_params.add(param.arg)
        if ann_src.strip() == "str" or "str" in ann_src:
            str_params.add(param.arg)
        if "Decimal" in ann_src:
            decimal_params.add(param.arg)

    uses_float_cast = False
    checks_isfinite = False
    has_value_error_handler = False
    checks_isdigit = False
    uses_decimal_or_round = bool(decimal_params)
    decimal_line = node.lineno
    int_cast_params: list[tuple[str, int]] = []
    uuid_cast_params: list[tuple[str, int]] = []
    fromhex_cast_params: list[tuple[str, int]] = []
    validated_uuid_params: set[str] = set()
    validated_fromhex_params: set[str] = set()
    divisors: list[tuple[str, int]] = []
    subscripts: list[tuple[str, str, int]] = []
    checked_pairs: set[tuple[str, str]] = set()
    get_vars: set[str] = set()
    none_checked_params: set[str] = set()
    attr_accesses: list[tuple[str, str, int]] = []

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
            if isinstance(child.func, ast.Name):
                if child.func.id == "float":
                    uses_float_cast = True
                elif child.func.id == "Decimal":
                    uses_decimal_or_round = True
                    decimal_line = child.lineno
                elif child.func.id == "round" and len(child.args) >= 2:
                    uses_decimal_or_round = True
                    decimal_line = child.lineno
                elif child.func.id == "int" and child.args:
                    first_arg = child.args[0]
                    if isinstance(first_arg, ast.Name) and first_arg.id in str_params:
                        int_cast_params.append((first_arg.id, child.lineno))
                elif child.func.id == "UUID" and (child.args or child.keywords):
                    target_arg = child.args[0] if child.args else (child.keywords[0].value if child.keywords else None)
                    if isinstance(target_arg, ast.Name) and target_arg.id in param_names:
                        uuid_cast_params.append((target_arg.id, child.lineno))
            elif isinstance(child.func, ast.Attribute):
                if child.func.attr in {"isfinite", "isnan", "isinf"}:
                    checks_isfinite = True
                elif child.func.attr == "isdigit":
                    checks_isdigit = True
                elif child.func.attr == "quantize":
                    uses_decimal_or_round = True
                    decimal_line = child.lineno
                elif child.func.attr == "get" and isinstance(child.func.value, ast.Name):
                    get_vars.add(child.func.value.id)
                elif (
                    child.func.attr == "UUID"
                    and isinstance(child.func.value, ast.Name)
                    and child.func.value.id == "uuid"
                    and (child.args or child.keywords)
                ):
                    target_arg = child.args[0] if child.args else (child.keywords[0].value if child.keywords else None)
                    if isinstance(target_arg, ast.Name) and target_arg.id in param_names:
                        uuid_cast_params.append((target_arg.id, child.lineno))
                elif (
                    child.func.attr == "fromhex"
                    and isinstance(child.func.value, ast.Name)
                    and child.func.value.id in {"bytes", "bytearray"}
                    and (child.args or child.keywords)
                ):
                    target_arg = child.args[0] if child.args else (child.keywords[0].value if child.keywords else None)
                    if isinstance(target_arg, ast.Name) and target_arg.id in param_names:
                        fromhex_cast_params.append((target_arg.id, child.lineno))
        elif isinstance(child, ast.BinOp) and isinstance(child.op, (ast.Div, ast.FloorDiv, ast.Mod)):
            if not isinstance(child.right, ast.Constant):
                divisors.append((ast.unparse(child.right), child.lineno))
        elif isinstance(child, ast.Compare):
            for name_node in ast.walk(child):
                if isinstance(name_node, ast.Name) and name_node.id in param_names:
                    p_id = name_node.id
                    cmp_src = ast.unparse(child)
                    if "len(" in cmp_src and any(k in cmp_src for k in ("32", "36", "37")):
                        validated_uuid_params.add(p_id)
                    if "% 2" in cmp_src:
                        validated_fromhex_params.add(p_id)
            cur = child.left
            for op, comp in zip(child.ops, child.comparators):
                if isinstance(op, (ast.In, ast.NotIn)) and isinstance(comp, ast.Name):
                    checked_pairs.add((comp.id, ast.unparse(cur)))
                elif isinstance(op, (ast.Is, ast.IsNot, ast.Eq, ast.NotEq)):
                    if isinstance(cur, ast.Name) and isinstance(comp, ast.Constant) and comp.value is None:
                        none_checked_params.add(cur.id)
                    elif isinstance(comp, ast.Name) and isinstance(cur, ast.Constant) and cur.value is None:
                        none_checked_params.add(comp.id)
                cur = comp
        elif (
            isinstance(child, ast.Subscript)
            and isinstance(child.ctx, ast.Load)
            and isinstance(child.value, ast.Name)
            and child.value.id in param_names
        ):
            subscripts.append((child.value.id, ast.unparse(child.slice), child.lineno))
        elif (
            isinstance(child, ast.Attribute)
            and isinstance(child.ctx, ast.Load)
            and isinstance(child.value, ast.Name)
            and child.value.id in param_names
        ):
            attr_accesses.append((child.value.id, child.attr, child.lineno))

    if uses_float_cast and not checks_isfinite:
        expr = "all(math.isfinite(v) for v in result.values())"
        if not any("isfinite" in e for e in explicit):
            result.suggestions.append(
                CandidateSuggestion(
                    target_name=qualname,
                    kind="function",
                    suggested_expression=expr,
                    rationale="Function parses floats with float() without checking math.isfinite() against NaN/Inf.",
                    lineno=node.lineno,
                )
            )

    if uses_decimal_or_round:
        expr = "result >= 0"
        if not any("result >= 0" in e for e in explicit):
            result.suggestions.append(
                CandidateSuggestion(
                    target_name=qualname,
                    kind="function",
                    suggested_expression=expr,
                    rationale="Financial Decimal or round(..., 2) calculation detected; non-negative quantized postcondition may apply.",
                    lineno=decimal_line,
                )
            )

    seen_int_params: set[str] = set()
    if not has_value_error_handler and not checks_isdigit:
        for p_name, int_line in int_cast_params:
            if p_name not in seen_int_params:
                seen_int_params.add(p_name)
                expr = f"len({p_name}.strip()) > 0"
                if not any(expr in e for e in explicit):
                    result.suggestions.append(
                        CandidateSuggestion(
                            target_name=qualname,
                            kind="function",
                            suggested_expression=expr,
                            rationale=f"Function calls int() on string parameter '{p_name}' without validating numeric format or handling ValueError.",
                            lineno=int_line,
                        )
                    )

    seen_uuid_params: set[str] = set()
    if not has_value_error_handler:
        for p_name, uuid_line in uuid_cast_params:
            if p_name not in seen_uuid_params and p_name not in validated_uuid_params:
                seen_uuid_params.add(p_name)
                expr = f"len({p_name}.strip()) in (32, 36)"
                if not any(expr in e for e in explicit):
                    result.suggestions.append(
                        CandidateSuggestion(
                            target_name=qualname,
                            kind="function",
                            suggested_expression=expr,
                            rationale=f"Function calls uuid.UUID() on parameter '{p_name}' without validating UUID format or handling ValueError.",
                            lineno=uuid_line,
                        )
                    )

    seen_fromhex_params: set[str] = set()
    if not has_value_error_handler:
        for p_name, fromhex_line in fromhex_cast_params:
            if p_name not in seen_fromhex_params and p_name not in validated_fromhex_params:
                seen_fromhex_params.add(p_name)
                expr = f"len({p_name}.strip()) % 2 == 0"
                if not any(expr in e for e in explicit):
                    result.suggestions.append(
                        CandidateSuggestion(
                            target_name=qualname,
                            kind="function",
                            suggested_expression=expr,
                            rationale=f"Function calls bytes.fromhex() on parameter '{p_name}' without validating hex format or handling ValueError.",
                            lineno=fromhex_line,
                        )
                    )

    for div_expr, div_line in divisors:
        result.suggestions.append(
            CandidateSuggestion(
                target_name=qualname,
                kind="function",
                suggested_expression=f"{div_expr} != 0",
                rationale=f"Division by '{div_expr}' at line {div_line} without explicit non-zero precondition.",
                lineno=div_line,
            )
        )

    for d_name, k_expr, sub_line in subscripts:
        if (d_name, k_expr) not in checked_pairs and d_name not in get_vars:
            expr = f"{k_expr} in {d_name}"
            if not any(expr in e for e in explicit):
                result.suggestions.append(
                    CandidateSuggestion(
                        target_name=qualname,
                        kind="function",
                        suggested_expression=expr,
                        rationale=f"Unvalidated subscript '{d_name}[{k_expr}]' at line {sub_line} without membership check or .get().",
                        lineno=sub_line,
                    )
                )

    seen_none_params: set[str] = set()
    for p_name, attr_name, attr_line in attr_accesses:
        if p_name in optional_params and p_name not in none_checked_params and p_name not in seen_none_params:
            seen_none_params.add(p_name)
            expr = f"{p_name} is not None"
            if not any(expr in e for e in explicit):
                result.suggestions.append(
                    CandidateSuggestion(
                        target_name=qualname,
                        kind="function",
                        suggested_expression=expr,
                        rationale=f"Unvalidated attribute access '{p_name}.{attr_name}' on optional parameter at line {attr_line} without None check.",
                        lineno=attr_line,
                    )
                )

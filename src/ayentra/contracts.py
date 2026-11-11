from __future__ import annotations

import inspect
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class InvariantSpec:
    expression: str
    target_name: str
    kind: str  # "class" or "function"
    lineno: int
    filepath: str
    description: str = ""
    check_concurrency: bool = False
    domain_bounds: dict[str, Any] = field(default_factory=dict)


def invariant(
    expression: str,
    *,
    description: str = "",
    check_concurrency: bool = False,
) -> Callable[[Any], Any]:
    """Attach an explicit behavioral invariant to a class or function."""
    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("Invariant expression must be a non-empty string.")

    def decorator(obj: Any) -> Any:
        try:
            filepath = inspect.getsourcefile(obj) or "<unknown>"
            _, lineno = inspect.getsourcelines(obj)
        except (OSError, TypeError):
            filepath = "<unknown>"
            lineno = 1

        kind = "class" if inspect.isclass(obj) else "function"
        existing: list[InvariantSpec] = list(getattr(obj, "__ayentra_invariants__", []))
        bounds: dict[str, Any] = dict(getattr(obj, "__ayentra_domain__", {}))
        spec = InvariantSpec(
            expression=expression.strip(),
            target_name=obj.__qualname__,
            kind=kind,
            lineno=lineno,
            filepath=filepath,
            description=description,
            check_concurrency=check_concurrency,
            domain_bounds=bounds,
        )
        existing.append(spec)
        setattr(obj, "__ayentra_invariants__", existing)
        return obj

    return decorator


def domain(**bounds: Any) -> Callable[[Any], Any]:
    """Declare explicit parameter domain bounds for property-based testing."""

    def decorator(obj: Any) -> Any:
        current = dict(getattr(obj, "__ayentra_domain__", {}))
        current.update(bounds)
        setattr(obj, "__ayentra_domain__", current)
        if hasattr(obj, "__ayentra_invariants__"):
            updated = [
                InvariantSpec(
                    expression=inv.expression,
                    target_name=inv.target_name,
                    kind=inv.kind,
                    lineno=inv.lineno,
                    filepath=inv.filepath,
                    description=inv.description,
                    check_concurrency=inv.check_concurrency,
                    domain_bounds=current,
                )
                for inv in getattr(obj, "__ayentra_invariants__")
            ]
            setattr(obj, "__ayentra_invariants__", updated)
        return obj

    return decorator


def load_toml_invariants(toml_path: Path, target_filepath: str) -> list[InvariantSpec]:
    """Load explicit invariants defined in an ayentra.toml specification file."""
    if not toml_path.is_file():
        t_path = Path(target_filepath).resolve()
        for parent in [t_path.parent, *t_path.parents]:
            if (parent / "ayentra.toml").is_file():
                toml_path = parent / "ayentra.toml"
                break
            if (parent / "pyproject.toml").is_file():
                toml_path = parent / "ayentra.toml"
                break
        if not toml_path.is_file():
            return []
    data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    specs: list[InvariantSpec] = []
    for entry in data.get("invariants", []):
        if not isinstance(entry, dict):
            continue
        expr = entry.get("expression")
        target = entry.get("target")
        if not expr or not target or not isinstance(expr, str) or not isinstance(target, str):
            continue
        file_match = str(entry.get("file", "")).strip()
        if file_match and Path(file_match).name != Path(target_filepath).name:
            continue
        specs.append(
            InvariantSpec(
                expression=expr.strip(),
                target_name=target.strip(),
                kind=str(entry.get("kind", "function")),
                lineno=int(entry.get("lineno", 1)),
                filepath=target_filepath,
                description=str(entry.get("description", "")),
                check_concurrency=bool(entry.get("check_concurrency", False)),
                domain_bounds=dict(entry.get("domain", {})),
            )
        )
    return specs

from __future__ import annotations

from ayentra.contracts import domain, invariant


@invariant(
    "all(len(k.strip()) > 0 for k in result.keys()) and all(math.isfinite(v) for v in result.values())",
    description="Parsed telemetry dictionary must contain only non-empty metric keys and finite float values",
)
@domain(payload="telemetry_kv")
def parse_telemetry_payload(payload: str) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for item in payload.split(","):
        if "=" not in item:
            continue
        key, raw_val = item.split("=", 1)
        try:
            metrics[key] = float(raw_val)
        except ValueError:
            continue
    return metrics

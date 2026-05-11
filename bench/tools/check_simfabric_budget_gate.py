#!/usr/bin/env python3
"""Gate the manifest-shape full-graph dispatch on the predicted budget.

Mitigates the predicted-wallclock followup item from
docs/cerebras-model-ledgers.md (Manifest-shape simfabric proof plan):

  > The full-graph dispatch will not launch unless the budget is under a
  > configured ceiling in `config/manifest-simfabric-budget.json` — that
  > ceiling + gate are followup once the calibration constant lands.

Inputs:
  - predicted-wallclock budget receipt (default
    `bench/out/r3-1-31b-manifest-simfabric-predicted-wallclock/budget.json`)
  - ceiling config (default `config/manifest-simfabric-budget.json`,
    schema at `config/manifest-simfabric-budget.schema.json`)

Decision rules:
  1. Ceiling config must be schema-valid.
  2. `calibrationStatus` must NOT be the bootstrap sentinel (i.e. a
     per-kernel manifest-shape calibration receipt must back the ceiling).
  3. The predicted-wallclock budget receipt must have `calibrated == true`;
     an uncalibrated budget produces `predictedCycles: null` so the
     comparison is undefined.
  4. `grandPredictedCycles` must be ≤ `ceilings.grandPredictedCycles`.
  5. When both sides cite per-phase entries, each phase's
     `predictedCycles` must be ≤ the corresponding ceiling.

Output: a `doe_simfabric_wallclock_gate_decision` receipt JSON. Exit
code 0 when allowed, 1 when denied, 2 on input errors. The receipt
chains hashes for both the budget file and the ceiling file so any
downstream full-graph launch receipt can cite this decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUDGET = (
    REPO_ROOT
    / "bench/out/r3-1-31b-manifest-simfabric-predicted-wallclock/budget.json"
)
DEFAULT_CEILING = REPO_ROOT / "config/manifest-simfabric-budget.json"
DEFAULT_OUT = (
    REPO_ROOT
    / "bench/out/r3-1-31b-manifest-simfabric-budget-gate/decision.json"
)
SCHEMA_PATH = (
    REPO_ROOT / "config/manifest-simfabric-budget.schema.json"
)
BOOTSTRAP_TOKEN = "<bootstrap-pending-rung-3>"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--budget", type=Path, default=DEFAULT_BUDGET)
    p.add_argument("--ceiling", type=Path, default=DEFAULT_CEILING)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return p.parse_args()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _try_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _validate_ceiling_schema(ceiling: dict[str, Any]) -> list[str]:
    """Validate the ceiling config against its schema. jsonschema is
    optional so the gate stays usable in minimal environments; when the
    library is present we use it, otherwise fall back to structural
    checks that mirror the schema's required keys + const fields."""
    try:
        import jsonschema  # type: ignore[import-untyped]
    except ImportError:
        return _validate_ceiling_structural(ceiling)
    if not SCHEMA_PATH.is_file():
        return [f"ceiling schema absent at {SCHEMA_PATH}"]
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = list(
        jsonschema.Draft202012Validator(schema).iter_errors(ceiling)
    )
    return [
        f"{'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in errors
    ]


def _validate_ceiling_structural(ceiling: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if ceiling.get("schemaVersion") != 1:
        errors.append("schemaVersion must equal 1")
    if ceiling.get("artifactKind") != "doe_simfabric_wallclock_ceiling":
        errors.append(
            "artifactKind must equal 'doe_simfabric_wallclock_ceiling'"
        )
    cs = ceiling.get("calibrationStatus")
    if not isinstance(cs, str):
        errors.append("calibrationStatus must be a string")
    elif cs != BOOTSTRAP_TOKEN and not _is_sha256(cs):
        errors.append(
            "calibrationStatus must be the bootstrap token or a sha256 hex"
        )
    ceilings = ceiling.get("ceilings")
    if not isinstance(ceilings, dict):
        errors.append("ceilings must be an object")
    else:
        if not isinstance(ceilings.get("grandPredictedCycles"), int):
            errors.append("ceilings.grandPredictedCycles must be an integer")
        per_phase = ceilings.get("perPhase")
        if per_phase is not None and not isinstance(per_phase, dict):
            errors.append("ceilings.perPhase must be an object when present")
    return errors


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        c in "0123456789abcdef" for c in value
    )


def _check_calibration(ceiling: dict[str, Any]) -> list[str]:
    cs = ceiling.get("calibrationStatus")
    if cs == BOOTSTRAP_TOKEN:
        return [
            "ceiling.calibrationStatus is <bootstrap-pending-rung-3>; the "
            "per-kernel manifest-shape calibration receipt has not landed, "
            "so any numeric ceiling is unfounded — refusing full-graph launch"
        ]
    if not isinstance(cs, str) or not _is_sha256(cs):
        return [
            f"ceiling.calibrationStatus={cs!r} is neither the bootstrap "
            "token nor a sha256 hex — refusing full-graph launch"
        ]
    return []


def _check_budget_calibrated(budget: dict[str, Any]) -> list[str]:
    if not budget.get("calibrated"):
        return [
            "budget.calibrated is false — predictedCycles is null and the "
            "comparison against the ceiling is undefined; per-kernel "
            "manifest-shape calibration must land a constant first"
        ]
    return []


def _check_ceiling_breach(
    budget: dict[str, Any],
    ceilings: dict[str, Any],
) -> list[str]:
    violations: list[str] = []
    grand = budget.get("grandPredictedCycles")
    grand_ceiling = ceilings.get("grandPredictedCycles")
    if isinstance(grand, int) and isinstance(grand_ceiling, int):
        if grand > grand_ceiling:
            violations.append(
                f"grandPredictedCycles={grand} exceeds ceiling="
                f"{grand_ceiling}"
            )
    per_phase_ceiling = ceilings.get("perPhase") or {}
    phase_totals = budget.get("phaseTotals") or {}
    for phase_name, ceiling_value in per_phase_ceiling.items():
        record = phase_totals.get(phase_name)
        if not isinstance(record, dict):
            continue
        predicted = record.get("predictedCycles")
        if not isinstance(predicted, int):
            continue
        if not isinstance(ceiling_value, int):
            continue
        if predicted > ceiling_value:
            violations.append(
                f"phase {phase_name!r} predictedCycles={predicted} "
                f"exceeds ceiling={ceiling_value}"
            )
    return violations


def evaluate(
    budget: dict[str, Any],
    ceiling: dict[str, Any],
) -> tuple[bool, list[str], list[str]]:
    """Return (allow, schemaErrors, decisionReasons).

    `allow` is True iff schemaErrors and decisionReasons are empty AND
    every check passed. `decisionReasons` lists every reason for denial
    so callers can surface all of them rather than first-violation only.
    """
    schema_errors = _validate_ceiling_schema(ceiling)
    if schema_errors:
        return False, schema_errors, ["ceiling failed schema validation"]
    reasons: list[str] = []
    reasons.extend(_check_calibration(ceiling))
    reasons.extend(_check_budget_calibrated(budget))
    if not reasons:
        # Numeric breach check is only meaningful when calibration is
        # established and the budget itself is calibrated.
        reasons.extend(
            _check_ceiling_breach(budget, ceiling.get("ceilings") or {})
        )
    allow = not reasons
    return allow, [], reasons


def build_decision_receipt(
    *,
    budget_path: Path,
    budget_hash: str,
    ceiling_path: Path,
    ceiling_hash: str,
    budget: dict[str, Any],
    ceiling: dict[str, Any],
    allow: bool,
    schema_errors: list[str],
    reasons: list[str],
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_simfabric_wallclock_gate_decision",
        "decision": "allow" if allow else "deny",
        "schemaErrors": schema_errors,
        "reasons": reasons,
        "budgetPath": _try_relative(budget_path),
        "budgetHash": budget_hash,
        "ceilingPath": _try_relative(ceiling_path),
        "ceilingHash": ceiling_hash,
        "calibrationStatus": ceiling.get("calibrationStatus"),
        "calibrationSourcePath": ceiling.get("calibrationSourcePath"),
        "observed": {
            "calibrated": bool(budget.get("calibrated")),
            "grandPredictedCycles": budget.get("grandPredictedCycles"),
            "phasePredictedCycles": {
                name: record.get("predictedCycles")
                for name, record in (budget.get("phaseTotals") or {}).items()
                if isinstance(record, dict)
            },
        },
        "ceilings": ceiling.get("ceilings"),
        "claim": {
            "scope": (
                "Full-graph launch precondition: gates the manifest-shape "
                "full-graph dispatch on the predicted-wallclock budget "
                "being calibrated and under the configured ceiling. The "
                "decision is structured so a downstream full-graph launch "
                "receipt can cite both the budget hash and the ceiling hash."
            ),
            "notWhat": (
                "Not a measured wallclock and not a guarantee of "
                "successful dispatch. Allow only certifies that the "
                "predicted budget chains back to a per-kernel "
                "manifest-shape calibration and is under the configured "
                "ceiling — runtime behavior may still differ."
            ),
        },
    }


def main() -> int:
    args = parse_args()
    if not args.budget.is_file():
        sys.stderr.write(
            f"check_simfabric_budget_gate: budget receipt absent at "
            f"{args.budget}\n"
        )
        return 2
    if not args.ceiling.is_file():
        sys.stderr.write(
            f"check_simfabric_budget_gate: ceiling config absent at "
            f"{args.ceiling}\n"
        )
        return 2
    budget = json.loads(args.budget.read_text(encoding="utf-8"))
    ceiling = json.loads(args.ceiling.read_text(encoding="utf-8"))

    budget_hash = _sha256_file(args.budget)
    ceiling_hash = _sha256_file(args.ceiling)

    allow, schema_errors, reasons = evaluate(budget, ceiling)
    receipt = build_decision_receipt(
        budget_path=args.budget,
        budget_hash=budget_hash,
        ceiling_path=args.ceiling,
        ceiling_hash=ceiling_hash,
        budget=budget,
        ceiling=ceiling,
        allow=allow,
        schema_errors=schema_errors,
        reasons=reasons,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {args.out} (decision={receipt['decision']}, "
        f"reasons={len(reasons)}, schemaErrors={len(schema_errors)})"
    )
    return 0 if allow else 1


if __name__ == "__main__":
    sys.exit(main())

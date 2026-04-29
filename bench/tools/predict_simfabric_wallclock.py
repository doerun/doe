#!/usr/bin/env python3
"""Predict simfabric wall-clock budget for the manifest-shape graph (rung 2).

Mitigates "Predicted simfabric wall-clock (rung 2)" from
docs/cerebras-north-star.md (Manifest-shape simfabric proof plan). The
manifest-shape full-graph dispatch (rung 8) cannot launch blindly; if
its predicted wall-clock exceeds the simfabric throughput envelope the
launch will time out before producing a receipt. This tool reads the
steps-mode host plan + per-target `pe_program.metadata.json` sidecars
and emits a per-kernel + per-phase wall-clock budget JSON that callers
gate on before launching.

The budget cannot be computed from compile metadata alone; the
throughput constant (bytes / cycle) must be calibrated from a single
rung-3 dispatch. Until calibration data lands, the predictor takes
the throughput constant as input via `--throughput-config`. Without a
calibration constant, the receipt records `"calibrated": false` and
the predicted-wallclock-ms field is `null`. With a calibration
constant the predictor produces a numeric estimate.

Inputs:
  - host plan JSON (`compileTargets[]`, `hostPlan.{kernels,phases}`)
  - compile dir containing `<target>/pe_program.metadata.json`
  - throughput-config JSON: `{"bytesPerCycle": float | null,
    "perPatternCyclesPerCall": {"<pattern>": float, ...}}`

Outputs:
  - budget JSON with per-kernel `outputBytesPerCall`,
    `cyclesPerCall`, `callCountByPhase`, plus phase totals and grand
    total. `calibrated` flag indicates whether `bytesPerCycle` was
    provided.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HOSTPLAN = (
    REPO_ROOT
    / "bench/out/r3-1-31b-manifest-fullgraph-compile-steps/host-plan.json"
)
DEFAULT_COMPILE_ROOT = (
    REPO_ROOT
    / "bench/out/r3-1-31b-manifest-fullgraph-compile-steps/compile"
)
DEFAULT_OUT = (
    REPO_ROOT
    / "bench/out/r3-1-31b-manifest-simfabric-predicted-wallclock/budget.json"
)

ELEM_BYTES = {
    "f32": 4, "u32": 4, "i32": 4,
    "f16": 2, "u16": 2, "i16": 2,
    "u8": 1, "i8": 1,
}

OUTPUT_SYMBOL_PATTERNS = (
    "c",
    "output",
    "key_cache",
    "val_cache",
    "value_cache",
    "key_output",
    "value_output",
    "next_token",
    "sampled_token",
    "tokens",
)

_AS_CAST_INLINE = re.compile(r"@as\([a-z0-9_]+,\s*([^)]+)\)")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NUMBER_RE = re.compile(r"[+-]?\d+")


class SizeExprError(ValueError):
    pass


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host-plan", type=Path, default=DEFAULT_HOSTPLAN)
    p.add_argument("--compile-root", type=Path, default=DEFAULT_COMPILE_ROOT)
    p.add_argument(
        "--throughput-config",
        type=Path,
        default=None,
        help=(
            "JSON file with throughput calibration. Schema: "
            '{"bytesPerCycle": float | null, '
            '"perPatternCyclesPerCall": {"<pattern>": float, ...}}.'
        ),
    )
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return p.parse_args()


def evaluate_size_expr(
    expr: str,
    bindings: dict[str, int],
) -> int:
    """Evaluate a sizeExpr using the bindings dict.

    Supports literals, identifiers (resolved from bindings), `@as(_, x)`
    casts (passed through to x), `+`, `-`, `*`, `/`, parens. Refuses
    anything else so the predictor never silently runs Python eval on
    untrusted strings.
    """
    raw = _AS_CAST_INLINE.sub(r"\1", expr).strip()
    if not raw:
        raise SizeExprError("empty sizeExpr")
    # Tokenize: numbers, idents, ops, parens.
    tokens: list[tuple[str, str | int]] = []
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch.isspace():
            i += 1
            continue
        if ch in "+-*/()":
            tokens.append(("op", ch))
            i += 1
            continue
        m = _NUMBER_RE.match(raw, i)
        if m and (i == 0 or raw[i - 1] in "+-*/(," or raw[i - 1].isspace()):
            tokens.append(("num", int(m.group(0))))
            i = m.end()
            continue
        m = _IDENT_RE.match(raw, i)
        if m:
            ident = m.group(0)
            if ident not in bindings:
                raise SizeExprError(
                    f"unknown identifier {ident!r} in sizeExpr {expr!r}"
                )
            tokens.append(("num", int(bindings[ident])))
            i = m.end()
            continue
        raise SizeExprError(
            f"unrecognized character {ch!r} at offset {i} in sizeExpr {expr!r}"
        )

    # Shunting-yard for + - * /.
    precedence = {"+": 1, "-": 1, "*": 2, "/": 2}
    output: list[tuple[str, str | int]] = []
    op_stack: list[str] = []
    for kind, value in tokens:
        if kind == "num":
            output.append((kind, value))
            continue
        assert isinstance(value, str)
        if value == "(":
            op_stack.append(value)
        elif value == ")":
            while op_stack and op_stack[-1] != "(":
                output.append(("op", op_stack.pop()))
            if not op_stack:
                raise SizeExprError(f"unbalanced parens in {expr!r}")
            op_stack.pop()
        else:
            while (
                op_stack
                and op_stack[-1] != "("
                and precedence.get(op_stack[-1], 0) >= precedence[value]
            ):
                output.append(("op", op_stack.pop()))
            op_stack.append(value)
    while op_stack:
        top = op_stack.pop()
        if top == "(":
            raise SizeExprError(f"unbalanced parens in {expr!r}")
        output.append(("op", top))

    stack: list[int] = []
    for kind, value in output:
        if kind == "num":
            assert isinstance(value, int)
            stack.append(value)
            continue
        if not stack:
            raise SizeExprError(f"missing operand in sizeExpr {expr!r}")
        b = stack.pop()
        if not stack:
            raise SizeExprError(f"missing operand in sizeExpr {expr!r}")
        a = stack.pop()
        if value == "+":
            stack.append(a + b)
        elif value == "-":
            stack.append(a - b)
        elif value == "*":
            stack.append(a * b)
        elif value == "/":
            if b == 0:
                raise SizeExprError(
                    f"division by zero in sizeExpr {expr!r}"
                )
            stack.append(a // b)
        else:
            raise SizeExprError(f"unknown operator {value!r}")
    if len(stack) != 1:
        raise SizeExprError(f"malformed sizeExpr {expr!r}")
    return stack[0]


def output_bytes_for_target(
    metadata: dict[str, Any],
    bindings: dict[str, int],
) -> int:
    """Sum the byte sizes of the target's output exports.

    Outputs are detected by symbol name (exact match against
    OUTPUT_SYMBOL_PATTERNS). Sized via sizeExpr × elem byte width.
    Unknown symbols are skipped (counted as input/state). Unresolved
    sizeExpr surfaces as 0 with the failure recorded in the receipt.
    """
    total = 0
    for export in metadata.get("exports") or []:
        symbol = export.get("symbol")
        if symbol not in OUTPUT_SYMBOL_PATTERNS:
            continue
        elem = export.get("elemType", "f32")
        elem_bytes = ELEM_BYTES.get(elem, 4)
        size_expr = export.get("sizeExpr", "")
        try:
            n_elems = evaluate_size_expr(size_expr, bindings)
        except SizeExprError:
            continue
        total += n_elems * elem_bytes
    return total


def predict_wallclock(
    host_plan: dict[str, Any],
    compile_root: Path,
    throughput: dict[str, Any] | None,
    *,
    host_plan_path: str | None = None,
    host_plan_hash: str | None = None,
) -> dict[str, Any]:
    """Build the wallclock budget receipt body.

    `host_plan_path` and `host_plan_hash` (when provided) are recorded
    on the receipt so the rung-1 hash spine guard can validate the
    chain back to the live host plan file.
    """
    targets = {
        t["name"]: t for t in (host_plan.get("compileTargets") or [])
    }
    kernels = {
        k["name"]: k for k in host_plan["hostPlan"].get("kernels") or []
    }
    phases = host_plan["hostPlan"].get("phases") or {}

    bytes_per_cycle = (throughput or {}).get("bytesPerCycle")
    pattern_cycles = (throughput or {}).get("perPatternCyclesPerCall") or {}
    calibrated = bytes_per_cycle is not None

    per_kernel: list[dict[str, Any]] = []
    issues: list[str] = []
    for kernel_name, kernel_meta in kernels.items():
        target = targets.get(kernel_name)
        if target is None:
            issues.append(
                f"kernel {kernel_name!r} not present in compileTargets"
            )
            continue
        bindings = dict(target.get("compileParams") or {})
        meta_path = (
            compile_root / kernel_name / "pe_program.metadata.json"
        )
        if not meta_path.is_file():
            issues.append(
                f"kernel {kernel_name!r}: pe_program.metadata.json absent at "
                f"{meta_path}"
            )
            continue
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        out_bytes = output_bytes_for_target(metadata, bindings)
        cycles_per_call = pattern_cycles.get(kernel_meta.get("pattern"))
        per_kernel.append(
            {
                "name": kernel_name,
                "pattern": kernel_meta.get("pattern"),
                "outputBytesPerCall": out_bytes,
                "cyclesPerCall": cycles_per_call,
                "perPePeerCount": int(target.get("compileParams", {}).get(
                    "width", 0
                )) * int(target.get("compileParams", {}).get(
                    "height", 0
                )),
            }
        )

    # Phase totals.
    phase_totals: dict[str, dict[str, Any]] = {}
    for phase_name, phase_calls in phases.items():
        total_bytes = 0
        total_cycles = 0
        per_kernel_calls: dict[str, int] = {}
        for call in phase_calls:
            kn = call.get("kernelName")
            repeat = int(call.get("repeat", 1))
            n_calls = repeat
            per_kernel_calls[kn] = per_kernel_calls.get(kn, 0) + n_calls
        for record in per_kernel:
            n = per_kernel_calls.get(record["name"], 0)
            if n == 0:
                continue
            total_bytes += record["outputBytesPerCall"] * n
            cycles_per_call = record.get("cyclesPerCall")
            if cycles_per_call is not None:
                total_cycles += int(round(cycles_per_call * n))
        if calibrated and bytes_per_cycle:
            cycles_from_bytes = total_bytes / bytes_per_cycle
            predicted_cycles = max(total_cycles, int(cycles_from_bytes))
        else:
            predicted_cycles = None
        phase_totals[phase_name] = {
            "perKernelCalls": per_kernel_calls,
            "totalOutputBytes": total_bytes,
            "totalCycles": total_cycles,
            "predictedCycles": predicted_cycles,
        }

    grand_total_bytes = sum(p["totalOutputBytes"] for p in phase_totals.values())
    grand_total_cycles = sum(p["totalCycles"] for p in phase_totals.values())
    grand_predicted = (
        sum((p["predictedCycles"] or 0) for p in phase_totals.values())
        if calibrated
        else None
    )

    receipt: dict[str, Any] = {
        "schemaVersion": 1,
        "artifactKind": "doe_simfabric_wallclock_budget",
        "calibrated": calibrated,
        "bytesPerCycle": bytes_per_cycle,
        "perPatternCyclesPerCall": dict(pattern_cycles),
        "perKernel": per_kernel,
        "phaseTotals": phase_totals,
        "grandTotalOutputBytes": grand_total_bytes,
        "grandTotalCycles": grand_total_cycles,
        "grandPredictedCycles": grand_predicted,
        "issues": issues,
        "claim": {
            "scope": (
                "Per-kernel output-bytes-per-call + per-phase totals "
                "computed from the steps-mode host plan and per-target "
                "pe_program.metadata.json. When a throughput calibration "
                "constant is provided, predictedCycles is filled in."
            ),
            "notWhat": (
                "Not a measured wallclock; cycle estimates depend on the "
                "calibration constant from rung 3. Output-byte estimates "
                "use the OUTPUT_SYMBOL_PATTERNS heuristic (c, output, "
                "key_cache, val_cache, value_cache, tokens, ...) "
                "and may overcount for "
                "kernels that mark KV state as read-write rather than "
                "write-only."
            ),
        },
    }
    if host_plan_path:
        receipt["hostPlanPath"] = host_plan_path
    if host_plan_hash:
        receipt["hostPlanHash"] = host_plan_hash
    return receipt


def main() -> int:
    args = parse_args()
    if not args.host_plan.is_file():
        sys.stderr.write(
            f"predict_simfabric_wallclock: host-plan absent at "
            f"{args.host_plan}\n"
        )
        return 2
    host_plan = json.loads(args.host_plan.read_text(encoding="utf-8"))
    throughput: dict[str, Any] | None = None
    if args.throughput_config is not None:
        if not args.throughput_config.is_file():
            sys.stderr.write(
                f"predict_simfabric_wallclock: throughput config absent at "
                f"{args.throughput_config}\n"
            )
            return 2
        throughput = json.loads(
            args.throughput_config.read_text(encoding="utf-8")
        )

    host_plan_hash = hashlib.sha256(
        args.host_plan.read_bytes()
    ).hexdigest()
    try:
        host_plan_rel = str(args.host_plan.resolve().relative_to(REPO_ROOT))
    except ValueError:
        host_plan_rel = str(args.host_plan)

    receipt = predict_wallclock(
        host_plan,
        args.compile_root,
        throughput,
        host_plan_path=host_plan_rel,
        host_plan_hash=host_plan_hash,
    )

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from bench.tools._receipt_hash_guard import (
        ReceiptHashSpineError,
        enforce_receipt_hash_spine,
    )
    try:
        enforce_receipt_hash_spine(receipt, repo_root=REPO_ROOT)
    except ReceiptHashSpineError as err:
        sys.stderr.write(
            "predict_simfabric_wallclock: receipt hash spine rejected emit:\n"
            f"  {err}\n"
        )
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {args.out} (calibrated={receipt['calibrated']}, "
        f"kernels={len(receipt['perKernel'])}, "
        f"issues={len(receipt['issues'])})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

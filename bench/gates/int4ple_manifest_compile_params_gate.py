#!/usr/bin/env python3
"""Validate INT4 PLE manifest compile params in CSL operation graphs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools.int4ple_manifest_compile_params import (  # noqa: E402
    manifest_compile_param_projection,
    reference_prompt_token_count,
)

DEFAULT_REQUIRED_TARGETS = (
    "embed",
    "tiled",
    "lm_head_gemv_stable",
    "attn_head256",
    "attn_head512",
    "sample",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--operation-graph",
        required=True,
        help=(
            "Path to a csl_operation_graph artifact, or to a simulator driver "
            "result containing an operationGraph object."
        ),
    )
    parser.add_argument("--runtime-config", required=True)
    parser.add_argument("--reference-export", required=True)
    parser.add_argument(
        "--schema",
        default="config/csl-operation-graph.schema.json",
    )
    parser.add_argument(
        "--required-target",
        action="append",
        dest="required_targets",
        help=(
            "Target name to require. May be repeated. Defaults to the "
            "promotion-critical INT4 PLE targets."
        ),
    )
    return parser.parse_args()


def resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_operation_graph(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("operation graph input must be a JSON object")
    if payload.get("artifactKind") == "csl_operation_graph":
        return payload
    graph = payload.get("operationGraph")
    if isinstance(graph, dict):
        return graph
    raise ValueError("input is neither csl_operation_graph nor driver result with operationGraph")


def _target_params_by_name(graph: dict[str, Any]) -> dict[str, dict[str, int]]:
    compile_section = graph.get("compile") or {}
    targets = compile_section.get("compileTargets") or []
    out: dict[str, dict[str, int]] = {}
    if not isinstance(targets, list):
        return out
    for target in targets:
        if not isinstance(target, dict):
            continue
        name = str(target.get("name") or "")
        params = target.get("compileParams")
        if isinstance(params, dict):
            out[name] = {str(key): int(value) for key, value in params.items()}
        elif name:
            out[name] = {}
    return out


def _compile_width(graph: dict[str, Any]) -> int:
    return _compile_grid(graph)["width"]


def _compile_grid(graph: dict[str, Any]) -> dict[str, int]:
    pe_grid = (graph.get("compile") or {}).get("peGrid") or {}
    if not isinstance(pe_grid, dict):
        return {"width": 0, "height": 0}
    return {
        "width": int(pe_grid.get("width") or 0),
        "height": int(pe_grid.get("height") or 0),
    }


def _require_minimum(
    *,
    failures: list[str],
    checks: list[dict[str, Any]],
    check_id: str,
    actual: int,
    minimum: int,
) -> None:
    passed = actual >= minimum
    checks.append(
        {
            "id": check_id,
            "actual": actual,
            "minimum": minimum,
            "passed": passed,
        }
    )
    if not passed:
        failures.append(f"{check_id}:{actual}<{minimum}")


def _check_coverage(
    *,
    graph: dict[str, Any],
    runtime_config: dict[str, Any],
    reference: dict[str, Any],
    target_params: dict[str, dict[str, int]],
    failures: list[str],
    checks: list[dict[str, Any]],
) -> None:
    model = runtime_config.get("modelConfig") or {}
    if not isinstance(model, dict):
        failures.append("runtime_config.modelConfig missing")
        return
    width = _compile_width(graph)
    vocab_size = int(model.get("vocabSize") or model.get("pleVocabSize") or 0)
    hidden_dim = int(model.get("hiddenDim") or 0)
    prompt_tokens = reference_prompt_token_count(reference)
    if vocab_size <= 0:
        failures.append("runtime_config.modelConfig.vocabSize missing")
    if hidden_dim <= 0:
        failures.append("runtime_config.modelConfig.hiddenDim missing")
    if prompt_tokens <= 0:
        failures.append("reference prompt token count missing")

    embed = target_params.get("embed") or {}
    if embed:
        embed_rows = (
            width
            * int(embed.get("height") or 0)
            * int(embed.get("rows_per_pe") or 0)
        )
        _require_minimum(
            failures=failures,
            checks=checks,
            check_id="embed_vocab_row_coverage",
            actual=embed_rows,
            minimum=vocab_size,
        )
        _require_minimum(
            failures=failures,
            checks=checks,
            check_id="embed_prompt_token_capacity",
            actual=int(embed.get("num_tokens") or 0),
            minimum=prompt_tokens,
        )

    tiled = target_params.get("tiled") or {}
    if tiled:
        _require_minimum(
            failures=failures,
            checks=checks,
            check_id="tiled_m_dimension_coverage",
            actual=int(tiled.get("P") or 0) * int(tiled.get("Mt") or 0),
            minimum=hidden_dim,
        )
        _require_minimum(
            failures=failures,
            checks=checks,
            check_id="tiled_n_dimension_coverage",
            actual=int(tiled.get("P") or 0) * int(tiled.get("Nt") or 0),
            minimum=hidden_dim,
        )

    for target_name in ("attn_head256", "attn_head512"):
        attention = target_params.get(target_name) or {}
        if not attention:
            continue
        _require_minimum(
            failures=failures,
            checks=checks,
            check_id=f"{target_name}_prefill_q_len_coverage",
            actual=int(attention.get("q_len") or 0),
            minimum=prompt_tokens,
        )
        _require_minimum(
            failures=failures,
            checks=checks,
            check_id=f"{target_name}_prefill_kv_len_coverage",
            actual=int(attention.get("kv_len") or 0),
            minimum=prompt_tokens,
        )

    lm_head = target_params.get("lm_head_gemv_stable") or {}
    if lm_head:
        _require_minimum(
            failures=failures,
            checks=checks,
            check_id="lm_head_vocab_logit_coverage",
            actual=width * int(lm_head.get("out_dim") or 0),
            minimum=vocab_size,
        )

    sample = target_params.get("sample") or {}
    if sample:
        _require_minimum(
            failures=failures,
            checks=checks,
            check_id="sample_vocab_logit_coverage",
            actual=width * int(sample.get("chunk_size") or 0),
            minimum=vocab_size,
        )


def check_manifest_compile_params(
    *,
    graph: dict[str, Any],
    runtime_config: dict[str, Any],
    reference: dict[str, Any],
    required_targets: tuple[str, ...] = DEFAULT_REQUIRED_TARGETS,
) -> tuple[list[str], dict[str, Any]]:
    failures: list[str] = []
    checks: list[dict[str, Any]] = []
    projection = manifest_compile_param_projection(
        runtime_config=runtime_config,
        reference=reference,
    )
    if projection.get("status") != "projected":
        failures.append(
            "manifest compile param projection unavailable: "
            f"{projection.get('reason', projection.get('status'))}"
        )
        return failures, {"projection": projection, "checks": checks}

    expected_params = projection.get("params") or {}
    target_params = _target_params_by_name(graph)
    expected_grid = projection.get("grid") or {}
    actual_grid = _compile_grid(graph)
    if actual_grid != expected_grid:
        failures.append(
            f"compile.peGrid={actual_grid!r}, expected {expected_grid!r}"
        )
    for target_name in required_targets:
        target_expected = expected_params.get(target_name)
        if not isinstance(target_expected, dict):
            failures.append(f"projection missing target {target_name!r}")
            continue
        actual = target_params.get(target_name)
        if actual is None:
            failures.append(f"compile.compileTargets missing target {target_name!r}")
            continue
        if not actual:
            failures.append(
                f"compile.compileTargets[{target_name}].compileParams missing"
            )
            continue
        for key, expected_value in target_expected.items():
            actual_value = actual.get(key)
            if actual_value != int(expected_value):
                failures.append(
                    f"compile.compileTargets[{target_name}].compileParams."
                    f"{key}={actual_value!r}, expected {int(expected_value)!r}"
                )

    _check_coverage(
        graph=graph,
        runtime_config=runtime_config,
        reference=reference,
        target_params=target_params,
        failures=failures,
        checks=checks,
    )
    return failures, {
        "projection": projection,
        "checks": checks,
        "requiredTargets": list(required_targets),
    }


def main() -> int:
    args = parse_args()
    try:
        graph_input = load_json(resolve(args.operation_graph))
        graph = extract_operation_graph(graph_input)
        runtime_config = load_json(resolve(args.runtime_config))
        reference = load_json(resolve(args.reference_export))
        schema = load_json(resolve(args.schema))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: INT4 PLE manifest compile params gate: {exc}")
        return 1

    failures = [
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: "
        f"{error.message}"
        for error in sorted(
            jsonschema.Draft202012Validator(schema).iter_errors(graph),
            key=lambda item: tuple(str(part) for part in item.absolute_path),
        )
    ]
    required_targets = tuple(args.required_targets or DEFAULT_REQUIRED_TARGETS)
    manifest_failures, report = check_manifest_compile_params(
        graph=graph,
        runtime_config=runtime_config,
        reference=reference,
        required_targets=required_targets,
    )
    failures.extend(manifest_failures)

    if failures:
        print("FAIL: INT4 PLE manifest compile params gate")
        for failure in failures:
            print(f"  {failure}")
        return 1

    check_count = sum(1 for check in report["checks"] if check["passed"])
    print(
        "PASS: INT4 PLE manifest compile params gate "
        f"(targets={len(required_targets)}, coverageChecks={check_count})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

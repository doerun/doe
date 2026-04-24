#!/usr/bin/env python3
"""Generate TSIR bootstrap manifest lowering fixture entries."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools.tsir_manifest_lowering import (
    ManifestLoweringInputs,
    build_manifest_lowering_entry,
    manifest_lowering_entry_digest,
)


DEFAULT_OUTPUT_DIR = REPO_ROOT / "bench" / "fixtures" / "tsir-manifest-entries"
ZIG_INPUT_TOOL = (
    REPO_ROOT / "runtime" / "zig" / "src" / "tsir_bootstrap_manifest_inputs.zig"
)


def _run_zig_input_tool(zig: str) -> list[dict[str, Any]]:
    result = subprocess.run(
        [
            zig,
            "run",
            str(ZIG_INPUT_TOOL),
            "--cache-dir",
            "/tmp/doe-tsir-bootstrap-manifest-cache",
            "--global-cache-dir",
            "/tmp/doe-tsir-bootstrap-manifest-global",
        ],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    docs = json.loads(result.stdout)
    if not isinstance(docs, list):
        raise ValueError("bootstrap manifest input tool must emit a JSON array")
    return docs


def _lowering_inputs(doc: dict[str, Any]) -> ManifestLoweringInputs:
    return ManifestLoweringInputs(
        kernel_ref=doc["kernelRef"],
        backend=doc["backend"],
        target_descriptor_correctness_hash=doc[
            "targetDescriptorCorrectnessHash"
        ],
        frontend_version=doc["frontendVersion"],
        tsir_semantic_digest=doc["tsirSemanticDigest"],
        tsir_realization_digest=doc["tsirRealizationDigest"],
        emitter_digest=doc["emitterDigest"],
        compiler_version=doc["compilerVersion"],
        exactness_class=doc["exactnessClass"],
        algorithm_exact_invariants=tuple(doc["algorithmExactInvariants"]),
        tolerance_metric=doc["toleranceMetric"],
        tolerance_epsilon=doc["toleranceEpsilon"],
        rejection_reasons=tuple(doc["rejectionReasons"]),
    )


def _fixture_name(entry: dict[str, Any]) -> str:
    kernel = entry["kernelRef"].removeprefix("doe.tsir.bootstrap.")
    return f"{kernel}.{entry['backend']}.json"


def generate_entries(zig: str) -> dict[str, dict[str, Any]]:
    fixtures: dict[str, dict[str, Any]] = {}
    for doc in _run_zig_input_tool(zig):
        if not isinstance(doc, dict):
            raise ValueError("bootstrap manifest input rows must be JSON objects")
        entry = build_manifest_lowering_entry(_lowering_inputs(doc))
        name = _fixture_name(entry)
        if name in fixtures:
            raise ValueError(f"duplicate TSIR manifest fixture name: {name}")
        fixtures[name] = entry
    if len(fixtures) != 6:
        raise ValueError(f"expected 6 bootstrap manifest fixtures, got {len(fixtures)}")
    return fixtures


def _entry_text(entry: dict[str, Any]) -> str:
    return json.dumps(entry, indent=2, sort_keys=True) + "\n"


def write_entries(
    output_dir: Path,
    fixtures: dict[str, dict[str, Any]],
    check: bool,
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    for name, entry in sorted(fixtures.items()):
        path = output_dir / name
        expected = _entry_text(entry)
        if check:
            if not path.exists():
                failures.append(f"missing fixture: {path}")
                continue
            actual = path.read_text(encoding="utf-8")
            if actual != expected:
                failures.append(f"stale fixture: {path}")
            continue
        path.write_text(expected, encoding="utf-8")
        digest = manifest_lowering_entry_digest(entry)
        print(f"{path.relative_to(REPO_ROOT)} manifestLoweringEntryDigest={digest}")
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where fixture JSON files are written.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if committed fixtures differ from regenerated entries.",
    )
    parser.add_argument(
        "--zig",
        default=os.environ.get("ZIG", "zig"),
        help="Zig executable used to run the bootstrap input tool.",
    )
    return parser.parse_args()


def main() -> int:
    try:
        args = parse_args()
        fixtures = generate_entries(args.zig)
        return write_entries(args.output_dir, fixtures, args.check)
    except (
        KeyError,
        ValueError,
        json.JSONDecodeError,
        subprocess.CalledProcessError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

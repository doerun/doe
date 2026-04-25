#!/usr/bin/env python3
"""Structured HostPlan binding metadata tests."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_DIR = REPO_ROOT / "bench" / "runners" / "csl-runners"
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))

from int4ple_binding_metadata import (  # noqa: E402
    binding_metadata_by_symbol,
    compile_params_from_target,
    pe_arrays_from_metadata,
    target_phase,
)
from int4ple_hostplan_execution_plan import (  # noqa: E402
    build_hostplan_execution_plan,
)


def _shape(elements: str) -> dict[str, str]:
    return {"kind": "csl_array", "elements": elements}


def _transform(
    kind: str,
    *,
    matrix_role: str,
    rows_from_input: str | None = None,
) -> dict[str, str]:
    result = {"kind": kind, "matrixRole": matrix_role}
    if rows_from_input is not None:
        result["rowsFromInput"] = rows_from_input
    return result


def _binding(
    symbol: str,
    access: str,
    elements: str,
    *,
    staging: dict[str, Any] | None = None,
    detile: dict[str, Any] | None = None,
    weight_source: str | None = None,
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "access": access,
        "elemType": "f32",
        "bindingShape": _shape(elements),
        "perPeShape": _shape(elements),
        "stagingTransform": staging,
        "detileTransform": detile,
        "weightSource": weight_source,
    }


def _tiled_bindings() -> list[dict[str, Any]]:
    return [
        _binding(
            "a",
            "read",
            "Mt * Kt",
            staging=_transform(
                "logical_matrix_to_summa_tiles",
                matrix_role="a",
            ),
        ),
        _binding(
            "b",
            "read",
            "Kt * Nt",
            staging=_transform(
                "weight_matrix_to_summa_tiles",
                matrix_role="b",
            ),
            weight_source="runtime_weight_mapping",
        ),
        _binding(
            "c",
            "read_write",
            "Mt * Nt",
            detile=_transform(
                "summa_tiles_to_logical_matrix",
                matrix_role="c",
                rows_from_input="a",
            ),
        ),
    ]


class StructuredBindingMetadataTests(unittest.TestCase):
    def test_metadata_helpers_project_compile_params_and_pe_arrays(self) -> None:
        target = {
            "name": "tiled",
            "compileParams": {"P": "2", "Mt": 2, "Kt": 2, "Nt": 3},
            "metadata": {
                "targetPhase": "decode",
                "bindings": _tiled_bindings(),
            },
        }

        metadata = binding_metadata_by_symbol(target)
        arrays = pe_arrays_from_metadata(metadata)

        self.assertEqual(target_phase(target), "decode")
        self.assertEqual(
            compile_params_from_target(target),
            {"P": 2, "Mt": 2, "Kt": 2, "Nt": 3},
        )
        self.assertEqual(sorted(metadata), ["a", "b", "c"])
        self.assertEqual(arrays["b"]["sizeExpr"], "Kt * Nt")
        self.assertEqual(arrays["b"]["metadataSource"], "zig_compile_target_metadata")

    def test_simulator_plan_schema_accepts_compile_target_metadata(self) -> None:
        schema = json.loads(
            (REPO_ROOT / "config" / "doe-wgsl-simulator-plan.schema.json").read_text(
                encoding="utf-8"
            )
        )
        payload = {
            "schemaVersion": 2,
            "artifactKind": "csl_simulator_plan",
            "target": "wse3",
            "contract": "explicit_simulator_launch",
            "driver": {
                "protocol": "doe.csl.simulator/v1",
                "executableEnvVar": "DOE_CSL_SIM_EXECUTABLE",
                "failClosedIfMissing": True,
            },
            "inputs": {
                "hostPlanArtifactPath": "artifacts/host-plan.json",
                "runtimeConfigPath": "artifacts/runtime.json",
                "compileRootPath": "artifacts/compile",
                "compileTargets": [
                    {
                        "name": "tiled",
                        "layout": "tiled/layout.csl",
                        "peProgram": "tiled/pe_program.csl",
                        "metadata": {
                            "targetPhase": "base",
                            "bindings": _tiled_bindings(),
                        },
                    }
                ],
            },
            "runtime": {
                "peGrid": {"width": 2, "height": 2},
                "prefillLaunchCount": 1,
                "decodeLaunchCount": 0,
                "weightMappingCount": 1,
                "stateBufferCount": 0,
                "maxDecodeTokens": 0,
                "timeoutMs": 0,
                "batchSize": 1,
                "eosTokenId": None,
            },
            "outputs": {
                "stdoutPath": "artifacts/stdout.log",
                "stderrPath": "artifacts/stderr.log",
                "tracePath": "artifacts/trace.json",
            },
        }

        jsonschema.Draft202012Validator(schema).validate(payload)

    def test_tiled_plan_uses_metadata_without_reading_csl_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            compile_root = Path(tmpdir) / "compile"
            execution_plan = build_hostplan_execution_plan(
                plan={
                    "inputs": {
                        "compileTargets": [
                            {
                                "name": "tiled",
                                "layout": "missing/layout.csl",
                                "peProgram": "missing/pe_program.csl",
                                "compileParams": {
                                    "P": 2,
                                    "Mt": 2,
                                    "Kt": 2,
                                    "Nt": 3,
                                },
                                "metadata": {
                                    "targetPhase": "base",
                                    "bindings": _tiled_bindings(),
                                },
                            }
                        ]
                    }
                },
                compile_root=compile_root,
                runtime_config={
                    "modelConfig": {
                        "hiddenDim": 4,
                        "vocabSize": 8,
                        "maxSeqLen": 4,
                    },
                    "memoryPlan": {"grid": {"width": 2, "height": 2}},
                    "weightMappings": [
                        {
                            "weightKey": "layer.0.q",
                            "tensor": "layer.0.q",
                            "path": "/weights/q.bin",
                            "sha256": "0" * 64,
                            "dtype": "u8_q4k",
                            "shape": [5, 4],
                            "byteSize": 80,
                        }
                    ],
                },
                scheduler={
                    "hostPlan": {
                        "runtimeScheduler": {
                            "status": "bound",
                            "launches": [
                                {
                                    "launchIndex": 2,
                                    "phase": "prefill",
                                    "kernelName": "tiled",
                                    "inputs": [
                                        {
                                            "symbol": "a",
                                            "buffer": "activation:prev",
                                            "role": "activation",
                                            "access": "read",
                                            "matrixCols": 4,
                                        },
                                        {
                                            "symbol": "b",
                                            "buffer": "weight:layer.0.q",
                                            "role": "weight",
                                            "access": "read",
                                        },
                                    ],
                                    "outputs": [
                                        {
                                            "symbol": "c",
                                            "buffer": "activation:next",
                                            "role": "activation",
                                            "access": "write",
                                            "matrixCols": 5,
                                        }
                                    ],
                                }
                            ],
                        }
                    }
                },
                executor_validator={
                    "status": "passed",
                    "producedBufferCount": 1,
                },
            )

        self.assertEqual(
            execution_plan["status"],
            "planned",
            execution_plan["blockers"],
        )
        launch = execution_plan["launches"][0]
        inputs = {item["symbol"]: item for item in launch["inputBindings"]}
        outputs = {item["symbol"]: item for item in launch["outputBindings"]}

        a_mat = inputs["a"]["materialization"]
        self.assertEqual(a_mat["targetPhase"], "base")
        self.assertEqual(a_mat["elementsPerPe"], 4)
        self.assertEqual(a_mat["plannedElementCount"], 16)
        self.assertEqual(a_mat["bindingShape"]["elements"], "Mt * Kt")
        self.assertEqual(
            a_mat["sourceTransform"]["kind"],
            "logical_matrix_to_summa_tiles",
        )
        self.assertEqual(a_mat["sourceTransform"]["sourceCols"], 4)

        b_mat = inputs["b"]["materialization"]
        self.assertEqual(b_mat["elementsPerPe"], 6)
        self.assertEqual(b_mat["plannedElementCount"], 24)
        self.assertEqual(b_mat["plannedByteLength"], 80)
        self.assertEqual(b_mat["weightSource"], "runtime_weight_mapping")
        self.assertEqual(
            b_mat["sourceTransform"]["kind"],
            "weight_matrix_to_summa_tiles",
        )
        self.assertEqual(
            b_mat["sourceTransform"]["sourceTransform"]["kind"],
            "q4km_rowwise_to_f32",
        )

        c_mat = outputs["c"]["materialization"]
        self.assertEqual(c_mat["elementsPerPe"], 6)
        self.assertEqual(c_mat["plannedElementCount"], 24)
        self.assertEqual(
            c_mat["outputTransform"]["kind"],
            "summa_tiles_to_logical_matrix",
        )
        self.assertEqual(c_mat["detileTransform"]["rowsFromInput"], "a")


if __name__ == "__main__":
    unittest.main()

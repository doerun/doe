from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.gates.int4ple_manifest_compile_params_gate import (  # noqa: E402
    DEFAULT_REQUIRED_TARGETS,
    check_manifest_compile_params,
    extract_operation_graph,
)
from bench.tools.int4ple_manifest_compile_params import (  # noqa: E402
    manifest_compile_param_projection,
)


def _runtime_config() -> dict:
    return {
        "memoryPlan": {"grid": {"width": 130, "height": 127}},
        "modelConfig": {
            "hiddenDim": 1536,
            "headDim": 256,
            "globalHeadDim": 512,
            "maxSeqLen": 23,
            "pleVocabSize": 262144,
            "vocabSize": 262144,
        },
    }


def _reference() -> dict:
    return {"inputSetComponents": {"tokenCount": 15}}


def _graph_with_params(params_by_name: dict[str, dict[str, int]]) -> dict:
    return {
        "artifactKind": "csl_operation_graph",
        "compile": {
            "peGrid": {"width": 130, "height": 127},
            "compileTargets": [
                {
                    "name": name,
                    "layout": f"{name}/layout.csl",
                    "peProgram": f"{name}/pe_program.csl",
                    "compileParams": params,
                }
                for name, params in params_by_name.items()
            ],
        },
    }


class Int4PleManifestCompileParamsGateTests(unittest.TestCase):
    def test_manifest_scale_operation_graph_passes(self) -> None:
        projection = manifest_compile_param_projection(
            runtime_config=_runtime_config(),
            reference=_reference(),
        )
        graph = _graph_with_params(
            {
                name: dict(projection["params"][name])
                for name in DEFAULT_REQUIRED_TARGETS
            }
        )

        failures, report = check_manifest_compile_params(
            graph=graph,
            runtime_config=_runtime_config(),
            reference=_reference(),
        )

        self.assertEqual(failures, [])
        self.assertEqual(report["requiredTargets"], list(DEFAULT_REQUIRED_TARGETS))
        self.assertTrue(all(check["passed"] for check in report["checks"]))

    def test_diagnostic_shape_operation_graph_fails_closed(self) -> None:
        graph = _graph_with_params(
            {
                "embed": {
                    "height": 1,
                    "hidden_size": 1536,
                    "num_tokens": 23,
                    "rows_per_pe": 1,
                },
                "tiled": {"P": 2, "Mt": 8, "Kt": 8, "Nt": 8},
                "lm_head_gemv_stable": {
                    "out_dim": 64,
                    "in_dim_per_pe": 512,
                    "num_blocks_per_row": 2,
                },
                "attn_head256": {
                    "block_size": 1,
                    "head_dim": 256,
                    "kv_len": 1,
                    "q_len": 1,
                },
                "attn_head512": {
                    "block_size": 1,
                    "head_dim": 512,
                    "kv_len": 1,
                    "q_len": 1,
                },
                "sample": {"chunk_size": 2017},
            }
        )

        failures, report = check_manifest_compile_params(
            graph=graph,
            runtime_config=_runtime_config(),
            reference=_reference(),
        )

        failure_text = "\n".join(failures)
        # The diagnostic fixture's compileParams are intentionally
        # pre-solver shapes; the gate must flag every mismatch against the
        # current projection. Post-embed-solver and post-attn-streaming-solver
        # expected values shift to match what the solvers now derive from
        # the manifest-scale reference. Anchor on the shape of the failure
        # set (which kernels and coverage checks fire), not the old numeric
        # expected values — those drift whenever a solver's budget or
        # strategy changes.
        self.assertIn(
            "compile.compileTargets[embed].compileParams.height=",
            failure_text,
        )
        self.assertIn(
            "compile.compileTargets[attn_head256].compileParams.q_len_per_pe=",
            failure_text,
        )
        self.assertIn(
            "compile.compileTargets[attn_head512].compileParams.q_len_per_pe=",
            failure_text,
        )
        self.assertIn("embed_vocab_row_coverage:", failure_text)
        self.assertIn("tiled_m_dimension_coverage:", failure_text)
        self.assertIn("tiled_n_dimension_coverage:", failure_text)
        self.assertIn("attn_head256_prefill_q_len_coverage:", failure_text)
        self.assertIn("attn_head512_prefill_kv_len_coverage:", failure_text)
        self.assertIn("lm_head_vocab_logit_coverage:", failure_text)
        self.assertFalse(all(check["passed"] for check in report["checks"]))
        self.assertEqual(
            report["projection"]["targetBlockers"]["embed"],
            "csl_compile_params_infeasible_embed_grid_budget",
        )

    def test_missing_compile_params_is_blocking(self) -> None:
        projection = manifest_compile_param_projection(
            runtime_config=_runtime_config(),
            reference=_reference(),
        )
        params_by_name = {
            name: dict(projection["params"][name])
            for name in DEFAULT_REQUIRED_TARGETS
        }
        graph = _graph_with_params(params_by_name)
        graph["compile"]["compileTargets"][0].pop("compileParams")

        failures, _report = check_manifest_compile_params(
            graph=graph,
            runtime_config=_runtime_config(),
            reference=_reference(),
        )

        self.assertIn(
            "compile.compileTargets[embed].compileParams missing",
            failures,
        )

    def test_operation_graph_grid_must_match_projection_grid(self) -> None:
        projection = manifest_compile_param_projection(
            runtime_config=_runtime_config(),
            reference=_reference(),
        )
        graph = _graph_with_params(
            {
                name: dict(projection["params"][name])
                for name in DEFAULT_REQUIRED_TARGETS
            }
        )
        graph["compile"]["peGrid"]["width"] = 64

        failures, _report = check_manifest_compile_params(
            graph=graph,
            runtime_config=_runtime_config(),
            reference=_reference(),
        )

        self.assertIn(
            "compile.peGrid={'width': 64, 'height': 127}, "
            "expected {'width': 130, 'height': 127}",
            failures,
        )

    def test_extract_operation_graph_accepts_driver_result_wrapper(self) -> None:
        graph = _graph_with_params({"sample": {"chunk_size": 2017}})

        self.assertIs(extract_operation_graph(graph), graph)
        self.assertIs(
            extract_operation_graph({"operationGraph": graph, "status": "succeeded"}),
            graph,
        )
        with self.assertRaisesRegex(ValueError, "neither csl_operation_graph"):
            extract_operation_graph({"status": "succeeded"})


if __name__ == "__main__":
    unittest.main()

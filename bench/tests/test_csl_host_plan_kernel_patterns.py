#!/usr/bin/env python3
"""Verify the HostPlan kernel-pattern taxonomy surfaces into the operation
graph receipt.

Doe's north-star target is a heterogeneous HostPlan (embed + rmsnorm + tiled
matmul + attention + gemv + rope + gelu + sample). The op-graph today only
describes the single rpc_launch for the chosen compile target; gates that
need to see "which pattern is this kernel?" had to re-derive it from the
HostPlan artifact. These tests lock in the contract that the driver reads
the HostPlan and surfaces one `kernelPatterns` entry per compile target
that has a matching kernel name — so a single op-graph receipt carries
both the rpc_launch contract AND the Doppler pattern binding per kernel.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "runtime" / "zig" / "tools"))

from csl_sdk_driver import (  # type: ignore[import-not-found]
    load_host_plan_kernels,
    synthesize_operation_graph,
)

MINIMAL_LAYOUT_CSL = """\
layout {
  @set_rectangle(4, 1);
  @export_name("weights", [*]f32, true);
  @export_name("output", [*]f32, true);
  @export_name("run", fn()void);
}
"""

MINIMAL_PE_PROGRAM = """\
param chunk_size: i16 = 64;
var weights: [chunk_size]f32;
var output: [chunk_size]f32;

fn run() void {
  for (@range(i16, chunk_size)) |i| {
    output[i] = weights[i];
  }
}
"""


def _write_compile_target(root: Path, name: str) -> tuple[Path, Path]:
    target_dir = root / name
    target_dir.mkdir(parents=True, exist_ok=True)
    layout = target_dir / "layout.csl"
    pe = target_dir / "pe_program.csl"
    layout.write_text(MINIMAL_LAYOUT_CSL, encoding="utf-8")
    pe.write_text(MINIMAL_PE_PROGRAM, encoding="utf-8")
    return layout, pe


def _make_plan(
    *,
    compile_root: Path,
    target_name: str,
    host_plan_path: str | None = None,
    inline_host_plan: dict | None = None,
) -> dict:
    plan: dict = {
        "target": "wse3",
        "inputs": {
            "compileTargets": [
                {
                    "name": target_name,
                    "layout": f"{target_name}/layout.csl",
                    "peProgram": f"{target_name}/pe_program.csl",
                }
            ],
            "compileRootPath": str(compile_root),
        },
        "runtime": {"peGrid": {"width": 4, "height": 1}, "channels": 1, "memcpy": True},
    }
    if host_plan_path is not None:
        plan["inputs"]["hostPlanArtifactPath"] = host_plan_path
    if inline_host_plan is not None:
        plan["hostPlan"] = inline_host_plan
    return plan


class LoadHostPlanKernelsTests(unittest.TestCase):
    def test_inline_host_plan(self) -> None:
        """Inline `plan.hostPlan` is used when provided — lets tests
        synthesize the plan in-memory without staging a sidecar file."""
        plan = {
            "hostPlan": {
                "kernels": [
                    {"name": "gemv", "pattern": "fused_gemv_dequant", "count": 8},
                    {"name": "rope", "pattern": "rope", "count": 4},
                ],
            }
        }
        self.assertEqual(
            load_host_plan_kernels(plan=plan, plan_dir=Path("/tmp")),
            {
                "gemv": {"pattern": "fused_gemv_dequant", "count": 8},
                "rope": {"pattern": "rope", "count": 4},
            },
        )

    def test_sidecar_host_plan(self) -> None:
        """`plan.inputs.hostPlanArtifactPath` points at a csl_host_plan
        artifact on disk. The loader resolves it relative to `plan_dir`
        when the path is not absolute."""
        with tempfile.TemporaryDirectory() as td:
            plan_dir = Path(td)
            hp_path = plan_dir / "host_plan.json"
            hp_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 2,
                        "artifactKind": "csl_host_plan",
                        "hostPlan": {
                            "kernels": [
                                {"name": "embed", "pattern": "gather", "count": 1},
                                {"name": "rmsnorm", "pattern": "reduction", "count": 6},
                            ]
                        },
                    }
                )
            )
            plan = {"inputs": {"hostPlanArtifactPath": "host_plan.json"}}
            self.assertEqual(
                load_host_plan_kernels(plan=plan, plan_dir=plan_dir),
                {
                    "embed": {"pattern": "gather", "count": 1},
                    "rmsnorm": {"pattern": "reduction", "count": 6},
                },
            )

    def test_missing_hostplan_path_returns_empty(self) -> None:
        """When neither inline `hostPlan` nor a sidecar path is supplied,
        the loader returns {} — downstream op-graph synthesis then omits
        the `kernelPatterns` section entirely."""
        self.assertEqual(
            load_host_plan_kernels(plan={"inputs": {}}, plan_dir=Path("/tmp")),
            {},
        )

    def test_broken_hostplan_file_degrades(self) -> None:
        """A missing or malformed HostPlan file must NOT raise; it must
        return {} so op-graph synthesis continues. HostPlan pattern binding
        is a receipt enrichment, not a prerequisite."""
        with tempfile.TemporaryDirectory() as td:
            plan = {"inputs": {"hostPlanArtifactPath": "nonexistent.json"}}
            self.assertEqual(
                load_host_plan_kernels(plan=plan, plan_dir=Path(td)),
                {},
            )

            # Malformed JSON also degrades silently.
            bad = Path(td) / "bad.json"
            bad.write_text("{not json")
            self.assertEqual(
                load_host_plan_kernels(
                    plan={"inputs": {"hostPlanArtifactPath": "bad.json"}},
                    plan_dir=Path(td),
                ),
                {},
            )

    def test_unknown_pattern_filtered(self) -> None:
        """Patterns not in the shared enum are dropped — this way
        the op-graph schema validator never sees a value it would reject."""
        plan = {
            "hostPlan": {
                "kernels": [
                    {"name": "gemv", "pattern": "fused_gemv_dequant", "count": 8},
                    {"name": "experimental", "pattern": "lightning_new_thing", "count": 1},
                ]
            }
        }
        # Only the known-taxonomy entry survives.
        self.assertEqual(
            load_host_plan_kernels(plan=plan, plan_dir=Path("/tmp")),
            {"gemv": {"pattern": "fused_gemv_dequant", "count": 8}},
        )


class SynthesizeOperationGraphKernelPatternsTests(unittest.TestCase):
    """End-to-end: HostPlan pattern bindings appear in the synthesized graph
    receipt, one entry per compile target whose name matches a kernel name."""

    def test_single_target_matches_hostplan(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            compile_root = Path(td) / "compile"
            compile_root.mkdir(parents=True)
            _write_compile_target(compile_root, "gemv")

            plan = _make_plan(
                compile_root=compile_root,
                target_name="gemv",
                inline_host_plan={
                    "kernels": [
                        {"name": "gemv", "pattern": "fused_gemv_dequant", "count": 8}
                    ]
                },
            )
            payload = [
                {
                    "name": "gemv",
                    "layoutPath": str(compile_root / "gemv" / "layout.csl"),
                    "peProgramPath": str(compile_root / "gemv" / "pe_program.csl"),
                    "outputDir": str(compile_root / "gemv" / "out"),
                    "status": "succeeded",
                }
            ]
            host_plan_kernels = load_host_plan_kernels(plan=plan, plan_dir=Path(td))
            graph = synthesize_operation_graph(
                plan=plan,
                compile_targets_payload=payload,
                compile_root=compile_root,
                host_plan_kernels=host_plan_kernels,
            )
            self.assertIsNotNone(graph)
            assert graph is not None
            self.assertEqual(
                graph.get("kernelPatterns"),
                [{"targetName": "gemv", "pattern": "fused_gemv_dequant", "count": 8}],
            )

    def test_target_without_matching_kernel_is_skipped(self) -> None:
        """A compile target whose name doesn't appear in the HostPlan is
        not synthesized as a placeholder — the list just omits it so a
        reader can distinguish 'HostPlan said pattern X' from silence."""
        with tempfile.TemporaryDirectory() as td:
            compile_root = Path(td) / "compile"
            compile_root.mkdir(parents=True)
            _write_compile_target(compile_root, "oneoff")

            plan = _make_plan(
                compile_root=compile_root,
                target_name="oneoff",
                inline_host_plan={
                    "kernels": [
                        {"name": "gemv", "pattern": "fused_gemv_dequant", "count": 8}
                    ]
                },
            )
            payload = [
                {
                    "name": "oneoff",
                    "layoutPath": str(compile_root / "oneoff" / "layout.csl"),
                    "peProgramPath": str(compile_root / "oneoff" / "pe_program.csl"),
                    "outputDir": str(compile_root / "oneoff" / "out"),
                    "status": "succeeded",
                }
            ]
            host_plan_kernels = load_host_plan_kernels(plan=plan, plan_dir=Path(td))
            graph = synthesize_operation_graph(
                plan=plan,
                compile_targets_payload=payload,
                compile_root=compile_root,
                host_plan_kernels=host_plan_kernels,
            )
            self.assertIsNotNone(graph)
            assert graph is not None
            # kernelPatterns empty → field is omitted entirely, not present as [].
            self.assertNotIn("kernelPatterns", graph)

    def test_compile_targets_preserve_per_target_compile_params(self) -> None:
        """The operation graph must keep compile params on each compile
        target, not only on the selected rpc-launch compile section. E2B has
        heterogeneous targets, so this is the receipt surface downstream gates
        need for manifest-shape checks."""
        with tempfile.TemporaryDirectory() as td:
            compile_root = Path(td) / "compile"
            compile_root.mkdir(parents=True)
            _write_compile_target(compile_root, "embed")
            _write_compile_target(compile_root, "tiled")

            plan = {
                "target": "wse3",
                "inputs": {
                    "compileTargets": [
                        {
                            "name": "embed",
                            "layout": "embed/layout.csl",
                            "peProgram": "embed/pe_program.csl",
                            "compileParams": {
                                "height": 127,
                                "hidden_size": 1536,
                                "num_tokens": 23,
                                "rows_per_pe": 16,
                            },
                        },
                        {
                            "name": "tiled",
                            "layout": "tiled/layout.csl",
                            "peProgram": "tiled/pe_program.csl",
                            "compileParams": {"P": 96, "Mt": 16, "Kt": 16, "Nt": 16},
                        },
                    ],
                    "compileRootPath": str(compile_root),
                },
                "runtime": {
                    "peGrid": {"width": 130, "height": 127},
                    "channels": 1,
                    "memcpy": True,
                },
            }
            payload = [
                {
                    "name": "embed",
                    "layoutPath": str(compile_root / "embed" / "layout.csl"),
                    "peProgramPath": str(compile_root / "embed" / "pe_program.csl"),
                    "outputDir": str(compile_root / "embed" / "out"),
                    "status": "succeeded",
                }
            ]

            graph = synthesize_operation_graph(
                plan=plan,
                compile_targets_payload=payload,
                compile_root=compile_root,
            )

        self.assertIsNotNone(graph)
        assert graph is not None
        targets = {
            target["name"]: target
            for target in graph["compile"]["compileTargets"]
        }
        self.assertEqual(
            targets["embed"]["compileParams"],
            {
                "height": 127,
                "hidden_size": 1536,
                "num_tokens": 23,
                "rows_per_pe": 16,
            },
        )
        self.assertEqual(
            targets["tiled"]["compileParams"],
            {"P": 96, "Mt": 16, "Kt": 16, "Nt": 16},
        )

    def test_270m_fixture_produces_full_pattern_table(self) -> None:
        """Real 270M HostPlan at bench/out/host-plan.actual.json: every
        compileTarget name matches a kernel name, so every target gets
        a pattern binding in the op-graph receipt."""
        host_plan_artifact = REPO_ROOT / "bench" / "out" / "host-plan.actual.json"
        if not host_plan_artifact.exists():
            self.skipTest(f"270M host plan fixture not found at {host_plan_artifact}")
        hp_payload = json.loads(host_plan_artifact.read_text(encoding="utf-8"))

        with tempfile.TemporaryDirectory() as td:
            compile_root = Path(td) / "compile"
            compile_root.mkdir(parents=True)
            payload = []
            compile_targets_plan = []
            for ct in hp_payload["compileTargets"]:
                name = ct["name"]
                _write_compile_target(compile_root, name)
                payload.append(
                    {
                        "name": name,
                        "layoutPath": str(compile_root / name / "layout.csl"),
                        "peProgramPath": str(compile_root / name / "pe_program.csl"),
                        "outputDir": str(compile_root / name / "out"),
                        "status": "succeeded",
                    }
                )
                compile_targets_plan.append(
                    {
                        "name": name,
                        "layout": f"{name}/layout.csl",
                        "peProgram": f"{name}/pe_program.csl",
                    }
                )

            plan = {
                "target": "wse3",
                "inputs": {
                    "compileTargets": compile_targets_plan,
                    "compileRootPath": str(compile_root),
                },
                "runtime": {
                    "peGrid": hp_payload["hostPlan"]["peGrid"],
                    "channels": 1,
                    "memcpy": True,
                },
                "hostPlan": hp_payload["hostPlan"],
            }
            host_plan_kernels = load_host_plan_kernels(plan=plan, plan_dir=Path(td))
            # Pattern 'attention_decode' and 'sample' live in the schema enum
            # to support E2B; the 270M shape uses those two literal pattern
            # names too. Expect every kernel in the plan to survive the filter.
            expected = {
                k["name"]: {"pattern": k["pattern"], "count": k["count"]}
                for k in hp_payload["hostPlan"]["kernels"]
                if k["pattern"]
                in {
                    "gather",
                    "reduction",
                    "tiled_matmul",
                    "attention_linear",
                    "attention_tiled",
                    "attention_decode",
                    "element_wise",
                    "gelu",
                    "gelu_gated",
                    "fused_gemv_dequant",
                    "residual",
                    "residual_add",
                    "rms_norm",
                    "rope",
                    "sample",
                }
            }
            self.assertEqual(host_plan_kernels, expected)

            graph = synthesize_operation_graph(
                plan=plan,
                compile_targets_payload=payload,
                compile_root=compile_root,
                host_plan_kernels=host_plan_kernels,
            )
            self.assertIsNotNone(graph)
            assert graph is not None
            self.assertIn("kernelPatterns", graph)
            kernel_patterns = graph["kernelPatterns"]
            # Every compile target name that matches a kernel should appear.
            seen = {kp["targetName"]: kp for kp in kernel_patterns}
            for kernel_name, binding in expected.items():
                # HostPlan kernel names are already lowercase-safe in the
                # 270M fixture, so the targetName comes through unchanged.
                self.assertIn(kernel_name, seen, f"{kernel_name} missing from kernelPatterns")
                self.assertEqual(seen[kernel_name]["pattern"], binding["pattern"])
                self.assertEqual(seen[kernel_name]["count"], binding["count"])

    def test_graph_without_host_plan_omits_kernel_patterns(self) -> None:
        """When no HostPlan is available (host_plan_kernels={} or None),
        the graph receipt omits `kernelPatterns` entirely. Gates that key
        on field presence can then distinguish 'no HostPlan surfaced' from
        'HostPlan surfaced an empty list'."""
        with tempfile.TemporaryDirectory() as td:
            compile_root = Path(td) / "compile"
            compile_root.mkdir(parents=True)
            _write_compile_target(compile_root, "gemv")

            plan = _make_plan(compile_root=compile_root, target_name="gemv")
            payload = [
                {
                    "name": "gemv",
                    "layoutPath": str(compile_root / "gemv" / "layout.csl"),
                    "peProgramPath": str(compile_root / "gemv" / "pe_program.csl"),
                    "outputDir": str(compile_root / "gemv" / "out"),
                    "status": "succeeded",
                }
            ]
            # Explicit None and {} both must omit the field.
            for host_plan_kernels in (None, {}):
                graph = synthesize_operation_graph(
                    plan=plan,
                    compile_targets_payload=payload,
                    compile_root=compile_root,
                    host_plan_kernels=host_plan_kernels,
                )
                self.assertIsNotNone(graph)
                assert graph is not None
                self.assertNotIn("kernelPatterns", graph)


if __name__ == "__main__":
    unittest.main()

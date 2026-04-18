#!/usr/bin/env python3
"""Test the sourceWgslPath path of run_csl_governed_lane.materialize_plan.

Verifies that when a compileTarget declares a sourceWgslPath, the lane
regenerates layout.csl + pe_program.csl from that WGSL via
doe-csl-bundle-emitter instead of copying the static `compile/` fixture tree.
This is the path that lets emitter fixes propagate to the governed lane
without per-fixture edits.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "bench"))

from runners.run_csl_governed_lane import materialize_plan  # type: ignore[import-not-found]

BUNDLE_EMITTER = REPO_ROOT / "runtime" / "zig" / "zig-out" / "bin" / "doe-csl-bundle-emitter"


MINIMAL_WGSL = (
    "@group(0) @binding(0) var<storage, read> input: array<f32>;\n"
    "@group(0) @binding(1) var<storage, read_write> output: array<f32>;\n"
    "\n"
    "@compute @workgroup_size(256)\n"
    "fn main(@builtin(global_invocation_id) gid: vec3u) {\n"
    "    let idx = gid.x;\n"
    "    output[idx] = input[idx] * 2.0;\n"
    "}\n"
)


def _stage_template(template_dir: Path, wgsl_path: Path) -> Path:
    template = {
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
            "hostPlanArtifactPath": "../host-plan.json",
            "runtimeConfigPath": "runtime-config.json",
            "compileRootPath": "compile",
            "compileTargets": [
                {
                    "name": "elementwise-double",
                    "layout": "elementwise-double/layout.csl",
                    "peProgram": "elementwise-double/pe_program.csl",
                    "sourceWgslPath": str(wgsl_path.resolve()),
                }
            ],
        },
        "runtime": {
            "peGrid": {"width": 4, "height": 1},
            "prefillLaunchCount": 0,
            "decodeLaunchCount": 0,
            "weightMappingCount": 0,
            "stateBufferCount": 0,
            "maxDecodeTokens": 32,
            "timeoutMs": 30000,
            "batchSize": 1,
            "eosTokenId": 1,
        },
        "outputs": {
            "stdoutPath": "stdout.log",
            "stderrPath": "stderr.log",
            "tracePath": "trace.json",
        },
    }
    runtime_cfg = template_dir / "runtime-config.json"
    runtime_cfg.write_text(
        json.dumps(
            {
                "mode": "compile-only",
                "notes": "source-wgsl-path smoke test",
                "runtimeExecutableEnvVar": "DOE_CSL_RUNTIME_EXECUTABLE",
                "exampleCommandWhenAvailable": [],
            }
        ),
        encoding="utf-8",
    )
    template_path = template_dir / "simulator-plan.template.json"
    template_path.write_text(json.dumps(template), encoding="utf-8")
    return template_path


class SourceWgslRegenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        if not BUNDLE_EMITTER.exists():
            self.skipTest(f"bundle emitter not built at {BUNDLE_EMITTER}")

    def test_regenerates_from_source_wgsl(self) -> None:
        """A compileTarget with sourceWgslPath gets layout.csl + pe_program.csl
        regenerated from WGSL; the resulting content matches a direct
        doe-csl-bundle-emitter call against the same source."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            wgsl = tmp / "elementwise_double.wgsl"
            wgsl.write_text(MINIMAL_WGSL, encoding="utf-8")

            template_dir = tmp / "template"
            template_dir.mkdir()
            template_path = _stage_template(template_dir, wgsl)

            run_dir = tmp / "run"
            run_dir.mkdir()
            host_plan = run_dir / "host-plan.json"
            host_plan.write_text('{"_": "stub"}', encoding="utf-8")

            materialize_plan(
                template_path=template_path,
                host_plan_path=host_plan,
                run_dir=run_dir,
            )

            layout = run_dir / "compile" / "elementwise-double" / "layout.csl"
            pe_program = run_dir / "compile" / "elementwise-double" / "pe_program.csl"
            self.assertTrue(layout.exists(), "layout.csl was not emitted")
            self.assertTrue(pe_program.exists(), "pe_program.csl was not emitted")

            # Cross-check: content must match a fresh direct bundle-emitter call.
            reference = tmp / "direct"
            reference.mkdir()
            subprocess.run(
                [str(BUNDLE_EMITTER), "--wgsl", str(wgsl), "--out-dir", str(reference)],
                check=True,
            )
            self.assertEqual(
                (reference / "layout.csl").read_text(),
                layout.read_text(),
                "regenerated layout.csl diverges from direct bundle-emitter output",
            )
            self.assertEqual(
                (reference / "pe_program.csl").read_text(),
                pe_program.read_text(),
                "regenerated pe_program.csl diverges from direct bundle-emitter output",
            )

    def test_regeneration_does_not_require_static_compile_dir(self) -> None:
        """When every compileTarget declares sourceWgslPath, the template
        directory does NOT need a `compile/` subtree — the lane regenerates
        instead of copying. This is the property that lets WGSL-backed
        fixtures live without hand-authored CSL files."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            wgsl = tmp / "elementwise_double.wgsl"
            wgsl.write_text(MINIMAL_WGSL, encoding="utf-8")

            template_dir = tmp / "template"
            template_dir.mkdir()
            template_path = _stage_template(template_dir, wgsl)

            # Deliberately do NOT create template_dir/compile/ — prove the
            # regeneration path doesn't fall back to a static copy when
            # sourceWgslPath is set.
            self.assertFalse((template_dir / "compile").exists())

            run_dir = tmp / "run"
            run_dir.mkdir()
            host_plan = run_dir / "host-plan.json"
            host_plan.write_text('{"_": "stub"}', encoding="utf-8")

            materialize_plan(
                template_path=template_path,
                host_plan_path=host_plan,
                run_dir=run_dir,
            )

            self.assertTrue(
                (run_dir / "compile" / "elementwise-double" / "layout.csl").exists()
            )
            self.assertTrue(
                (run_dir / "compile" / "elementwise-double" / "pe_program.csl").exists()
            )


if __name__ == "__main__":
    unittest.main()

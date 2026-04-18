#!/usr/bin/env python3
"""End-to-end integration: WGSL storage-binding access modes propagate
through `doe-csl-bundle-emitter` → `synthesize_operation_graph` → the
operation-graph `memcpy_h2d` / `memcpy_d2h` split.

The unit tests in `test_csl_wgsl_binding_parser.py` cover the parser in
isolation; this test exercises the full pipeline against a real bundle
emitter invocation. A regression in either the parser, the access-mode
enum, or the synthesizer's role-resolver functions will land here first
because the test asserts on the final operation-graph shape.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "runtime" / "zig" / "tools"))

from csl_sdk_driver import synthesize_operation_graph  # type: ignore[import-not-found]

BUNDLE_EMITTER = REPO_ROOT / "runtime" / "zig" / "zig-out" / "bin" / "doe-csl-bundle-emitter"


MIXED_ROLES_WGSL = (
    "@group(0) @binding(0) var<storage, read> input_a: array<f32>;\n"
    "@group(0) @binding(1) var<storage, read_write> shared_buf: array<f32>;\n"
    "@group(0) @binding(2) var<storage, write> output: array<f32>;\n"
    "\n"
    "@compute @workgroup_size(256)\n"
    "fn main(@builtin(global_invocation_id) gid: vec3u) {\n"
    "    let idx = gid.x;\n"
    "    output[idx] = input_a[idx] + shared_buf[idx];\n"
    "    shared_buf[idx] = output[idx];\n"
    "}\n"
)


class WgslRoleIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        if not BUNDLE_EMITTER.exists():
            self.skipTest(f"bundle emitter not built at {BUNDLE_EMITTER}")

    def test_roles_drive_h2d_d2h_split(self) -> None:
        """A WGSL source with mixed read/read_write/write storage bindings
        must produce an operationGraph where each symbol's memcpy direction
        matches its WGSL access mode — not the conservative
        'every-mutable-gets-both' fallback.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            wgsl = tmp / "mixed_roles.wgsl"
            wgsl.write_text(MIXED_ROLES_WGSL, encoding="utf-8")

            compile_root = tmp / "compile"
            target_dir = compile_root / "mixed"
            target_dir.mkdir(parents=True)

            # Real bundle-emitter call: the Doe CSL emitter must produce a
            # layout.csl whose @export_name declarations match the WGSL
            # binding names; otherwise the driver's access-map lookup would
            # miss and fall back to the mutable-bit heuristic.
            subprocess.run(
                [str(BUNDLE_EMITTER), "--wgsl", str(wgsl), "--out-dir", str(target_dir)],
                check=True,
            )

            plan = {
                "target": "wse3",
                "inputs": {
                    "compileTargets": [
                        {
                            "name": "mixed",
                            "layout": "mixed/layout.csl",
                            "peProgram": "mixed/pe_program.csl",
                            "sourceWgslPath": str(wgsl),
                        }
                    ],
                    "compileRootPath": str(compile_root),
                },
                "runtime": {
                    "peGrid": {"width": 4, "height": 1},
                    "channels": 1,
                    "memcpy": True,
                },
            }
            targets_payload = [
                {
                    "name": "mixed",
                    "layoutPath": str(target_dir / "layout.csl"),
                    "peProgramPath": str(target_dir / "pe_program.csl"),
                    "outputDir": str(target_dir / "out"),
                    "status": "succeeded",
                }
            ]

            graph = synthesize_operation_graph(
                plan=plan,
                compile_targets_payload=targets_payload,
                compile_root=compile_root,
            )
            self.assertIsNotNone(graph, "operationGraph should synthesize for parseable exports")
            assert graph is not None  # for type narrowing

            h2d_symbols = {
                op["deviceSymbol"]
                for op in graph["operations"]
                if op["kind"] == "memcpy_h2d"
            }
            d2h_symbols = {
                op["deviceSymbol"]
                for op in graph["operations"]
                if op["kind"] == "memcpy_d2h"
            }

            # Contract: access-mode drives memcpy direction.
            #   read       → host writes input → h2d only
            #   read_write → both directions
            #   write      → device writes output → d2h only
            self.assertIn("input_a", h2d_symbols, "read binding should emit h2d")
            self.assertIn("shared_buf", h2d_symbols, "read_write binding should emit h2d")
            self.assertNotIn(
                "output",
                h2d_symbols,
                "write-only binding should NOT emit h2d (host never writes it)",
            )
            self.assertIn("shared_buf", d2h_symbols, "read_write binding should emit d2h")
            self.assertIn("output", d2h_symbols, "write binding should emit d2h")
            self.assertNotIn(
                "input_a",
                d2h_symbols,
                "read-only binding should NOT emit d2h (device never writes it)",
            )


if __name__ == "__main__":
    unittest.main()

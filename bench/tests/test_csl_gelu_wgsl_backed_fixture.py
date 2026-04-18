#!/usr/bin/env python3
"""Exercise the committed WGSL-backed governed-lane fixture end to end.

The fixture lives at:
  runtime/zig/examples/simulator/gelu-wgsl-backed/simulator-plan.template.json

It declares `sourceWgslPath` on its one compile target, pointing at the
already-committed csl-gelu-smoke WGSL. Running materialize_plan against
this committed template is the durable proof that the WGSL→CSL
regeneration path is backed by a real fixture, not just in-memory unit
tests.

If the test skips because the bundle emitter is not built, the
committed schema-validated template still serves as reviewable evidence
that the pattern is wired through the config plumbing.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "bench"))

from runners.run_csl_governed_lane import materialize_plan  # type: ignore[import-not-found]

FIXTURE_DIR = REPO_ROOT / "runtime" / "zig" / "examples" / "simulator" / "gelu-wgsl-backed"
FIXTURE_TEMPLATE = FIXTURE_DIR / "simulator-plan.template.json"
FIXTURE_HOST_PLAN = FIXTURE_DIR / "host-plan.json"
FIXTURE_RUNTIME_CONFIG = FIXTURE_DIR / "runtime-config.json"
FIXTURE_WGSL = REPO_ROOT / "runtime" / "zig" / "examples" / "wgsl" / "csl-gelu-smoke.wgsl"

BUNDLE_EMITTER = REPO_ROOT / "runtime" / "zig" / "zig-out" / "bin" / "doe-csl-bundle-emitter"

SIM_PLAN_SCHEMA = REPO_ROOT / "config" / "doe-wgsl-simulator-plan.schema.json"
HOST_PLAN_SCHEMA = REPO_ROOT / "config" / "doe-wgsl-host-plan.schema.json"


class GeluWgslBackedFixtureTests(unittest.TestCase):
    def test_fixture_files_exist(self) -> None:
        """Every file the fixture references must be committed to the repo."""
        self.assertTrue(FIXTURE_TEMPLATE.exists(), f"missing: {FIXTURE_TEMPLATE}")
        self.assertTrue(FIXTURE_HOST_PLAN.exists(), f"missing: {FIXTURE_HOST_PLAN}")
        self.assertTrue(FIXTURE_RUNTIME_CONFIG.exists(), f"missing: {FIXTURE_RUNTIME_CONFIG}")
        self.assertTrue(FIXTURE_WGSL.exists(), f"missing: {FIXTURE_WGSL}")

    def test_template_matches_simulator_plan_schema(self) -> None:
        """The committed template must validate against the simulator-plan
        schema — this is what makes the fixture a first-class artifact
        rather than a scratchpad."""
        template = json.loads(FIXTURE_TEMPLATE.read_text(encoding="utf-8"))
        schema = json.loads(SIM_PLAN_SCHEMA.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(template)

    def test_host_plan_matches_host_plan_schema(self) -> None:
        host_plan = json.loads(FIXTURE_HOST_PLAN.read_text(encoding="utf-8"))
        schema = json.loads(HOST_PLAN_SCHEMA.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(host_plan)

    def test_template_declares_source_wgsl_path(self) -> None:
        """The fixture's purpose is to exercise the sourceWgslPath code
        path; regressing away from that turns this into a plain static
        template. Lock in the property."""
        template = json.loads(FIXTURE_TEMPLATE.read_text(encoding="utf-8"))
        compile_targets = template["inputs"]["compileTargets"]
        self.assertGreaterEqual(len(compile_targets), 1)
        for target in compile_targets:
            self.assertIn("sourceWgslPath", target, f"target {target['name']} missing sourceWgslPath")
            wgsl_path = target["sourceWgslPath"]
            # Paths are stored relative to repo root.
            resolved = (REPO_ROOT / wgsl_path).resolve() if not Path(wgsl_path).is_absolute() else Path(wgsl_path)
            self.assertTrue(resolved.exists(), f"referenced WGSL source does not exist: {wgsl_path}")

    def test_template_compile_target_names_match_host_plan(self) -> None:
        """The compile-target names in the template must match kernels
        declared in the HostPlan — otherwise the synthesized op-graph's
        kernelPatterns section would be empty and the receipt would lose
        the per-kernel pattern binding."""
        template = json.loads(FIXTURE_TEMPLATE.read_text(encoding="utf-8"))
        host_plan = json.loads(FIXTURE_HOST_PLAN.read_text(encoding="utf-8"))
        target_names = {t["name"] for t in template["inputs"]["compileTargets"]}
        kernel_names = {k["name"] for k in host_plan["hostPlan"]["kernels"]}
        self.assertTrue(
            target_names.issubset(kernel_names),
            f"compile targets {target_names - kernel_names} have no matching HostPlan kernel",
        )

    def test_materialize_plan_regenerates_compile_bundle(self) -> None:
        """End-to-end: materialize_plan reads the committed template,
        invokes doe-csl-bundle-emitter on the referenced WGSL, and writes
        layout.csl + pe_program.csl under run_dir/compile/gelu/. Skips
        when the emitter binary is not built; the schema validation tests
        above still demonstrate the fixture is structurally sound."""
        if not BUNDLE_EMITTER.exists():
            self.skipTest(f"bundle emitter not built at {BUNDLE_EMITTER}")
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            materialize_plan(
                template_path=FIXTURE_TEMPLATE,
                host_plan_path=FIXTURE_HOST_PLAN,
                run_dir=run_dir,
            )
            compile_root = run_dir / "compile"
            self.assertTrue((compile_root / "gelu" / "layout.csl").exists())
            self.assertTrue((compile_root / "gelu" / "pe_program.csl").exists())
            # The materialized plan still validates against the simulator
            # plan schema (with resolved absolute paths).
            materialized = run_dir / "simulator-plan.json"
            self.assertTrue(materialized.exists())
            payload = json.loads(materialized.read_text(encoding="utf-8"))
            schema = json.loads(SIM_PLAN_SCHEMA.read_text(encoding="utf-8"))
            jsonschema.Draft202012Validator(schema).validate(payload)


if __name__ == "__main__":
    unittest.main()

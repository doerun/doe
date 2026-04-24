"""Schema-validate every TSIR JSON in the bootstrap kernel catalog.

Step 1.5 of `docs/tsir-lowering-plan.md` pins a small catalog of WGSL
snapshots with hand-sketched TSIR. This test fails closed if any
catalog entry stops validating against the current schema — either
because the schema drifted or because a new entry isn't
schema-compliant. Category-error discoveries (kernels the schema
CANNOT express) are documented in per-family `*.notes.md` files, not
smuggled into the test via skips.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_DIR = REPO_ROOT / "runtime" / "zig" / "tests" / "tsir" / "bootstrap"
SEMANTIC_SCHEMA_PATH = REPO_ROOT / "config" / "doe-tsir-semantic.schema.json"
REALIZATION_SCHEMA_PATH = REPO_ROOT / "config" / "doe-tsir-realization.schema.json"


class TestTsirBootstrapCatalog(unittest.TestCase):
    def test_catalog_dir_exists(self) -> None:
        self.assertTrue(
            BOOTSTRAP_DIR.is_dir(),
            f"bootstrap directory missing: {BOOTSTRAP_DIR}",
        )
        self.assertTrue(
            (BOOTSTRAP_DIR / "README.md").is_file(),
            "bootstrap README.md is the index; it must exist",
        )

    def test_every_semantic_json_validates(self) -> None:
        schema = json.loads(SEMANTIC_SCHEMA_PATH.read_text(encoding="utf-8"))
        semantic_files = sorted(BOOTSTRAP_DIR.glob("*.tsir-semantic.json"))
        self.assertGreaterEqual(
            len(semantic_files),
            1,
            "bootstrap catalog must hold at least one semantic sketch",
        )
        for path in semantic_files:
            with self.subTest(file=path.name):
                doc = json.loads(path.read_text(encoding="utf-8"))
                jsonschema.validate(doc, schema)

    def test_every_realization_json_validates(self) -> None:
        schema = json.loads(REALIZATION_SCHEMA_PATH.read_text(encoding="utf-8"))
        realization_files = sorted(BOOTSTRAP_DIR.glob("*.tsir-realization.*.json"))
        for path in realization_files:
            with self.subTest(file=path.name):
                doc = json.loads(path.read_text(encoding="utf-8"))
                jsonschema.validate(doc, schema)

    def test_every_wgsl_has_semantic_sketch(self) -> None:
        wgsl_files = sorted(BOOTSTRAP_DIR.glob("*.wgsl"))
        self.assertGreaterEqual(
            len(wgsl_files),
            1,
            "bootstrap catalog must pin at least one WGSL snapshot",
        )
        for path in wgsl_files:
            stem = path.stem
            with self.subTest(family=stem):
                expected_semantic = BOOTSTRAP_DIR / f"{stem}.tsir-semantic.json"
                self.assertTrue(
                    expected_semantic.is_file(),
                    f"WGSL {path.name} must be paired with "
                    f"{expected_semantic.name}",
                )
                expected_notes = BOOTSTRAP_DIR / f"{stem}.notes.md"
                self.assertTrue(
                    expected_notes.is_file(),
                    f"WGSL {path.name} must be paired with {expected_notes.name} "
                    "documenting schema-fit",
                )

    def test_every_wgsl_has_realization_per_target(self) -> None:
        """Every bootstrap kernel must have a realization for each Phase A
        target descriptor (`webgpu-generic` and `wse3`).

        test_every_wgsl_has_semantic_sketch verifies the semantic + notes
        pairing. test_every_realization_json_validates verifies whatever
        realization files exist. Neither enforces that all
        (kernel, target) pairs are present, so a new bootstrap WGSL
        could land with only one target's realization and the existing
        tests would pass. Downstream consumers — the manifest-lowering
        fixture set in `bench/fixtures/tsir-manifest-entries/` and the
        nightly parity canary — assume the set is complete.
        """
        wgsl_files = sorted(BOOTSTRAP_DIR.glob("*.wgsl"))
        required_targets = ("webgpu-generic", "wse3")
        for path in wgsl_files:
            stem = path.stem
            for target in required_targets:
                with self.subTest(family=stem, target=target):
                    expected = BOOTSTRAP_DIR / f"{stem}.tsir-realization.{target}.json"
                    self.assertTrue(
                        expected.is_file(),
                        f"WGSL {path.name} must have a realization for "
                        f"target {target!r}: expected {expected.name}",
                    )


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Regression coverage for the promoted fragility catalog."""

from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

from bench.lib.config_validation import load_validated_config  # noqa: E402


class PromotedFragilityCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog_path = REPO_ROOT / "config" / "promoted-fragility-catalog.json"
        cls.signature_schema_path = REPO_ROOT / "config" / "fragility-signature.schema.json"
        cls.catalog = load_validated_config(
            cls.catalog_path,
            REPO_ROOT / "config" / "promoted-fragility-catalog.schema.json",
        )
        cls.registry = load_validated_config(REPO_ROOT / "config" / "numeric-stability-policy.json")
        cls.policy = load_validated_config(REPO_ROOT / "config" / "fragility-promotion-policy.json")

    def test_catalog_route_taxonomy_matches_registry_and_policy(self) -> None:
        self.assertEqual(
            self.catalog["routeTaxonomyVersion"],
            self.registry["routeTaxonomyVersion"],
        )
        self.assertEqual(
            self.catalog["routeTaxonomyVersion"],
            self.policy["routeTaxonomyVersion"],
        )

    def test_catalog_summary_matches_entries(self) -> None:
        entries = self.catalog["entries"]
        self.assertEqual(self.catalog["summary"]["entryCount"], len(entries))
        counts_by_stage: dict[str, int] = {}
        counts_by_kind: dict[str, int] = {}
        counts_by_class: dict[str, int] = {}
        for entry in entries:
            counts_by_stage[entry["contractStage"]] = counts_by_stage.get(entry["contractStage"], 0) + 1
            counts_by_kind[entry["artifactKind"]] = counts_by_kind.get(entry["artifactKind"], 0) + 1
            counts_by_class[entry["corpusClass"]] = counts_by_class.get(entry["corpusClass"], 0) + 1
        self.assertEqual(self.catalog["summary"]["countsByContractStage"], counts_by_stage)
        self.assertEqual(self.catalog["summary"]["countsByArtifactKind"], counts_by_kind)
        self.assertEqual(self.catalog["summary"]["countsByCorpusClass"], counts_by_class)

    def test_every_signature_file_is_present_once_and_valid(self) -> None:
        signature_paths = []
        for entry in self.catalog["entries"]:
            signature_path = REPO_ROOT / entry["signaturePath"]
            self.assertTrue(signature_path.exists(), entry["signaturePath"])
            signature = load_validated_config(signature_path, self.signature_schema_path)
            self.assertEqual(signature["signatureId"], entry["signatureId"])
            self.assertEqual(signature["contractStage"], entry["contractStage"])
            self.assertEqual(signature["artifactKind"], entry["artifactKind"])
            self.assertEqual(signature["corpusClass"], entry["corpusClass"])
            self.assertEqual(signature["scenarioStem"], entry["scenarioStem"])
            self.assertEqual(signature["routeTaxonomyVersion"], self.catalog["routeTaxonomyVersion"])
            self.assertEqual(signature["routeExpectation"]["decision"], entry["routeExpectationDecision"])
            signature_paths.append(signature_path.resolve())

        self.assertEqual(len(signature_paths), len(set(signature_paths)))
        disk_paths = {
            path.resolve()
            for path in (REPO_ROOT / "config" / "fragility-signatures" / "promoted").glob("*.json")
        }
        self.assertEqual(set(signature_paths), disk_paths)

    def test_promoted_signatures_keep_runtime_outcome_unset(self) -> None:
        for entry in self.catalog["entries"]:
            if entry["contractStage"] != "promoted":
                continue
            signature = load_validated_config(REPO_ROOT / entry["signaturePath"], self.signature_schema_path)
            self.assertEqual(signature["contractStage"], "promoted")
            self.assertNotIn("routeOutcome", signature)
            self.assertEqual(signature["routeExpectation"]["status"], "realized-in-promotion")
            self.assertTrue(signature["routeExpectation"]["hasPromotionEvidence"])

    def test_runtime_exercised_signatures_require_route_outcome(self) -> None:
        runtime_exercised_count = 0
        for entry in self.catalog["entries"]:
            if entry["contractStage"] != "runtime-exercised":
                continue
            runtime_exercised_count += 1
            signature = load_validated_config(REPO_ROOT / entry["signaturePath"], self.signature_schema_path)
            self.assertEqual(signature["contractStage"], "runtime-exercised")
            self.assertIn("routeOutcome", signature)
            self.assertEqual(signature["routeOutcome"]["decision"], entry["routeOutcomeDecision"])
        self.assertGreater(runtime_exercised_count, 0)

    def test_catalog_contains_strict_broad_and_operator_control_lanes(self) -> None:
        classes = {entry["corpusClass"] for entry in self.catalog["entries"]}
        self.assertIn("strict", classes)
        self.assertIn("broad", classes)
        self.assertIn("operator-control", classes)


if __name__ == "__main__":
    unittest.main()

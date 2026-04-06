#!/usr/bin/env python3
"""Tests for the canonical compare taxonomy."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
for _path_entry in (str(REPO_ROOT), str(BENCH_ROOT)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

from bench.tools.generate_compare_taxonomy import (  # noqa: E402
    boundary_by_surface,
    load_json,
    parse_structural_families,
)


class CompareTaxonomyTests(unittest.TestCase):
    def test_taxonomy_loads_and_parses_families(self) -> None:
        taxonomy = load_json(REPO_ROOT / "config" / "compare-taxonomy.json")
        families = parse_structural_families(taxonomy)
        self.assertGreater(len(families), 0)
        family_ids = {f.id for f in families}
        self.assertIn("doe_backend", family_ids)
        self.assertIn("dawn_backend", family_ids)

    def test_taxonomy_v2_has_products_axis(self) -> None:
        taxonomy = load_json(REPO_ROOT / "config" / "compare-taxonomy.json")
        self.assertEqual(taxonomy["schemaVersion"], 3)
        self.assertIn("products", taxonomy["axes"])
        self.assertIn("surfaces", taxonomy["axes"])
        self.assertNotIn("comparisonViews", taxonomy["axes"])
        self.assertNotIn("providerPairs", taxonomy["axes"])

    def test_boundaries_are_derived_from_surfaces(self) -> None:
        taxonomy = load_json(REPO_ROOT / "config" / "compare-taxonomy.json")
        boundaries = boundary_by_surface(taxonomy)
        self.assertEqual(boundaries["backend"], "backend_native")
        self.assertEqual(boundaries["plan"], "direct_plan")

    def test_promoted_run_coverage_references_valid_families(self) -> None:
        taxonomy = load_json(REPO_ROOT / "config" / "compare-taxonomy.json")
        families = parse_structural_families(taxonomy)
        family_ids = {f.id for f in families}
        coverage = taxonomy.get("promotedRunCoverage") or taxonomy.get("promotedCompareCoverage") or []
        for entry in coverage:
            self.assertIn(
                entry["familyId"],
                family_ids,
                f"promoted coverage references unknown family: {entry['familyId']}",
            )

    def test_product_families_have_product_field(self) -> None:
        taxonomy = load_json(REPO_ROOT / "config" / "compare-taxonomy.json")
        for fam in taxonomy.get("productFamilies", []):
            self.assertIn("product", fam, f"family {fam['id']} missing product field")
            self.assertIn("surface", fam, f"family {fam['id']} missing surface field")


if __name__ == "__main__":
    unittest.main()

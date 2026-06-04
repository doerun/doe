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
    build_entries,
    load_json,
    parse_structural_families,
    validate_promoted_subset_alignment,
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

    def test_node_bun_package_developer_profiles_are_reachable(self) -> None:
        taxonomy = load_json(REPO_ROOT / "config" / "compare-taxonomy.json")
        promoted_catalog = load_json(REPO_ROOT / "config" / "promoted-compare-catalog.json")
        families = parse_structural_families(taxonomy)
        family_by_id = {family.id: family for family in families}
        promoted_profile_map = validate_promoted_subset_alignment(
            taxonomy,
            promoted_catalog,
            family_by_id=family_by_id,
        )
        entries = {
            row["entryId"]: row
            for row in build_entries(taxonomy, promoted_profile_map=promoted_profile_map)
        }

        node_direct_warm = entries[
            "apple-metal__package_surface__node__doe_native_direct_vs_dawn_node_webgpu_package__warm__workload"
        ]
        self.assertEqual(node_direct_warm["providerSet"], "package_node_native_direct_providers")
        self.assertEqual(node_direct_warm["providers"], ["doe-direct", "node-webgpu"])
        self.assertEqual(
            node_direct_warm["promotedCompareProfileIds"],
            [
                "apple-metal-gemma270m-node-native-direct-decode-resident-warm",
                "apple-metal-gemma270m-node-native-direct-decode-warm",
                "apple-metal-package-developer-node-native-direct-prepared",
            ],
        )

        node_public_warm = entries[
            "apple-metal__package_surface__node__doe_vs_dawn_node_webgpu_package__warm__workload"
        ]
        self.assertEqual(node_public_warm["providerSet"], "package_node_providers")
        self.assertEqual(node_public_warm["providers"], ["doe", "node-webgpu"])
        self.assertIn("apple-metal-gemma64-package-warm", node_public_warm["promotedCompareProfileIds"])
        self.assertIn("apple-metal-gemma1b-package-warm", node_public_warm["promotedCompareProfileIds"])
        self.assertIn(
            "apple-metal-package-developer-node-prepared",
            node_public_warm["promotedCompareProfileIds"],
        )

        bun_warm = entries[
            "apple-metal__package_surface__bun__doe_vs_dawn_bun_webgpu_package__warm__workload"
        ]
        self.assertEqual(bun_warm["providers"], ["bun-webgpu", "doe"])
        self.assertIn("apple-metal-gemma270m-bun-package-decode-resident-warm", bun_warm["promotedCompareProfileIds"])
        self.assertIn("apple-metal-gemma270m-bun-package-decode-warm", bun_warm["promotedCompareProfileIds"])
        self.assertIn("apple-metal-package-developer-bun-prepared", bun_warm["promotedCompareProfileIds"])

        node_package_default = entries[
            "apple-metal__package_surface__node__doe_vs_dawn_node_webgpu_package__default__workload"
        ]
        self.assertEqual(node_package_default["providers"], ["doe", "node-webgpu"])


if __name__ == "__main__":
    unittest.main()

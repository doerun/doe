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
    DEFAULT_OUTPUT_PATH,
    actual_promoted_profile_map,
    build_rows,
    load_json,
    parse_structural_families,
    render_jsonl,
    summarize_rows,
    surface_alias_by_boundary,
    validate_expected_counts,
    validate_promoted_subset_alignment,
)


class CompareTaxonomyTests(unittest.TestCase):
    def test_expected_counts_match_generated_rows(self) -> None:
        taxonomy = load_json(REPO_ROOT / "config" / "compare-taxonomy.json")
        promoted_catalog = load_json(REPO_ROOT / "config" / "promoted-compare-catalog.json")
        families = parse_structural_families(taxonomy)
        family_by_id = {family.id: family for family in families}
        promoted_profile_map = validate_promoted_subset_alignment(
            taxonomy,
            promoted_catalog,
            family_by_id=family_by_id,
        )
        rows = build_rows(taxonomy, promoted_profile_map=promoted_profile_map)
        validate_expected_counts(taxonomy, rows)
        self.assertEqual(summarize_rows(rows), taxonomy["expectedCounts"])

    def test_generated_artifact_is_current(self) -> None:
        taxonomy = load_json(REPO_ROOT / "config" / "compare-taxonomy.json")
        promoted_catalog = load_json(REPO_ROOT / "config" / "promoted-compare-catalog.json")
        families = parse_structural_families(taxonomy)
        family_by_id = {family.id: family for family in families}
        promoted_profile_map = validate_promoted_subset_alignment(
            taxonomy,
            promoted_catalog,
            family_by_id=family_by_id,
        )
        rows = build_rows(taxonomy, promoted_profile_map=promoted_profile_map)
        expected = render_jsonl(rows)
        actual = DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8")
        self.assertEqual(actual, expected)

    def test_promoted_profiles_attach_to_rows(self) -> None:
        taxonomy = load_json(REPO_ROOT / "config" / "compare-taxonomy.json")
        promoted_catalog = load_json(REPO_ROOT / "config" / "promoted-compare-catalog.json")
        promoted_profile_map = actual_promoted_profile_map(
            promoted_catalog,
            surface_alias_to_boundary={
                value: key for key, value in surface_alias_by_boundary(taxonomy).items()
            },
        )
        rows = build_rows(taxonomy, promoted_profile_map=promoted_profile_map)
        warm_bun_row = next(
            row
            for row in rows
            if row["rowId"]
            == "apple-metal__package_surface__bun__doe_vs_bun_webgpu__warm__workload"
        )
        self.assertEqual(
            warm_bun_row["promotedCompareProfileIds"],
            ["apple-metal-gemma1b-bun-package-warm", "apple-metal-gemma64-bun-package-warm"],
        )
        invalid_row = next(
            row
            for row in rows
            if row["rowId"]
            == "apple-metal__package_surface__none__doe_vs_bun_webgpu__warm__workload"
        )
        self.assertFalse(invalid_row["isTypeCorrectStructural"])
        self.assertEqual(invalid_row["promotedCompareProfileIds"], [])


if __name__ == "__main__":
    unittest.main()

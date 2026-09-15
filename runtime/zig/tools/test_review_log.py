"""Exercise hierarchical review coverage, invalidation, and immutable history."""

from __future__ import annotations

import copy
from pathlib import Path
import subprocess
import tempfile
import unittest

from jsonschema.exceptions import ValidationError

from review_log import (
    GUIDANCE, LOG, REPO, SCHEMA, Scope, canonical_json, check_history,
    current_statuses, digest, input_hash, make_scopes, source_files, validate_log,
)


class ReviewLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        for path in GUIDANCE:
            destination = self.repo / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text("fixture guidance\n", encoding="utf-8")
        (self.repo / SCHEMA).write_bytes((REPO / SCHEMA).read_bytes())
        self.evidence = self.repo / "evidence.txt"
        self.evidence.write_text("passed\n", encoding="utf-8")
        self.files = {"src/a/a.zig": "a" * 64, "src/b/b.zig": "b" * 64}
        self.edges = [("src/a/a.zig", "src/b/b.zig")]
        self.scopes = make_scopes(self.files, self.edges, [])
        self.fingerprints = self.hashes(self.files)

    def hashes(self, files: dict[str, str]) -> dict[Scope, str]:
        return {
            scope: input_hash(self.repo, scope, files, {"fixturePolicy": 1})
            for scope in make_scopes(files, self.edges, [])
        }

    def record(
        self, scope: Scope, review_id: str, prerequisites: list[str] | None = None,
    ) -> dict:
        return {
            "reviewId": review_id, "level": scope.level,
            "targets": list(scope.targets), "status": "verified",
            "reviewer": "test", "reviewedAt": "2026-09-14T12:00:00Z",
            "sourceCommit": "a" * 40, "inputHash": self.fingerprints[scope],
            "supersedes": None, "prerequisites": prerequisites or [],
            "context": [], "summary": "Inspected fixture responsibility.",
            "findings": [], "resolvedFindings": [],
            "evidence": [{"path": "evidence.txt", "sha256": digest(b"passed\n")}],
            "nextAction": "Revisit when an input changes.",
        }

    def complete_reviews(self) -> list[dict]:
        records = []
        identifiers = {}

        def complete(scope: Scope) -> None:
            if scope in identifiers:
                return
            for prerequisite in self.scopes[scope]:
                complete(prerequisite)
            identifier = f"review_{len(records)}"
            records.append(self.record(
                scope, identifier, [identifiers[item] for item in self.scopes[scope]],
            ))
            identifiers[scope] = identifier

        complete(Scope("system", (".",)))
        validate_log(self.repo, {"schemaVersion": 1, "reviews": records})
        return records

    def test_inventory_does_not_grant_review_credit(self) -> None:
        statuses, _ = current_statuses(self.repo, self.scopes, self.fingerprints, [])
        self.assertEqual(set(statuses.values()), {"pending"})

    def test_file_reviews_do_not_complete_directory_or_system(self) -> None:
        records = [self.record(Scope("file", (path,)), f"file_{index}")
                   for index, path in enumerate(self.files)]
        system = Scope("system", (".",))
        records.append(self.record(system, "premature_system"))
        statuses, _ = current_statuses(self.repo, self.scopes, self.fingerprints, records)
        self.assertEqual(statuses[system], "blocked")
        self.assertEqual(statuses[Scope("directory", ("src/a",))], "pending")

    def test_complete_bottom_up_reviews_allow_system_coverage(self) -> None:
        records = self.complete_reviews()
        statuses, _ = current_statuses(self.repo, self.scopes, self.fingerprints, records)
        self.assertEqual(set(statuses.values()), {"verified"})

    def test_source_change_reopens_ancestors_and_boundary(self) -> None:
        records = self.complete_reviews()
        changed = dict(self.files, **{"src/a/a.zig": "c" * 64})
        statuses, _ = current_statuses(self.repo, self.scopes, self.hashes(changed), records)
        for scope in (
            Scope("file", ("src/a/a.zig",)), Scope("directory", ("src/a",)),
            Scope("within_directory", ("src/a",)),
            Scope("cross_directory", ("src/a", "src/b")), Scope("system", (".",)),
        ):
            self.assertEqual(statuses[scope], "stale", scope)
        self.assertEqual(statuses[Scope("file", ("src/b/b.zig",))], "verified")

    def test_new_file_cannot_inherit_completed_directory_review(self) -> None:
        records = self.complete_reviews()
        changed = dict(self.files, **{"src/a/new.zig": "c" * 64})
        scopes = make_scopes(changed, self.edges, records)
        statuses, _ = current_statuses(self.repo, scopes, self.hashes(changed), records)
        self.assertEqual(statuses[Scope("file", ("src/a/new.zig",))], "pending")
        self.assertEqual(statuses[Scope("directory", ("src/a",))], "stale")
        self.assertEqual(statuses[Scope("system", (".",))], "stale")

    def test_deleted_file_retains_retired_history(self) -> None:
        records = self.complete_reviews()
        remaining = {"src/b/b.zig": self.files["src/b/b.zig"]}
        scopes = make_scopes(remaining, [], records)
        hashes = {scope: input_hash(self.repo, scope, remaining, {"fixturePolicy": 1})
                  for scope in scopes}
        statuses, latest = current_statuses(self.repo, scopes, hashes, records)
        removed = Scope("file", ("src/a/a.zig",))
        self.assertEqual(statuses[removed], "retired")
        self.assertIn(removed, latest)

    def test_superseding_lower_review_reopens_parent_without_source_change(self) -> None:
        records = self.complete_reviews()
        scope = Scope("file", ("src/a/a.zig",))
        old = next(record for record in records if record["targets"] == list(scope.targets))
        new = self.record(scope, "reopened_file")
        new.update(status="in_progress", supersedes=old["reviewId"])
        records.append(new)
        validate_log(self.repo, {"schemaVersion": 1, "reviews": records})
        statuses, _ = current_statuses(self.repo, self.scopes, self.fingerprints, records)
        self.assertEqual(statuses[Scope("directory", ("src/a",))], "blocked")
        self.assertEqual(statuses[Scope("system", (".",))], "blocked")

    def test_lost_or_modified_evidence_invalidates_review(self) -> None:
        scope = Scope("file", ("src/a/a.zig",))
        records = [self.record(scope, "file_review")]
        for content in (b"failed\n", None):
            if content is None:
                self.evidence.unlink()
            else:
                self.evidence.write_bytes(content)
            statuses, _ = current_statuses(self.repo, self.scopes, self.fingerprints, records)
            self.assertEqual(statuses[scope], "stale")

    def test_guidance_and_additional_context_are_bound(self) -> None:
        scope = Scope("file", ("src/a/a.zig",))
        record = self.record(scope, "file_review")
        record["context"] = [{"path": "AGENTS.md", "sha256": digest(b"fixture guidance\n")}]
        (self.repo / "AGENTS.md").write_text("new guidance\n", encoding="utf-8")
        self.assertNotEqual(self.hashes(self.files)[scope], self.fingerprints[scope])
        statuses, _ = current_statuses(self.repo, self.scopes, self.fingerprints, [record])
        self.assertEqual(statuses[scope], "stale")

    def test_schema_rejects_completion_with_findings_or_without_evidence(self) -> None:
        record = self.record(Scope("file", ("src/a/a.zig",)), "file_review")
        for update in ({"findings": ["Unresolved borrowed lifetime."]}, {"evidence": []}):
            with self.assertRaises(ValidationError):
                validate_log(self.repo, {"schemaVersion": 1, "reviews": [record | update]})

    def test_log_rejects_duplicate_ids_bad_history_and_escaping_paths(self) -> None:
        record = self.record(Scope("file", ("src/a/a.zig",)), "file_review")
        for records in (
            [record, record], [record | {"supersedes": "unknown"}],
            [record | {"targets": ["../outside.zig"]}],
            [record | {"prerequisites": ["future_review"]}],
        ):
            with self.assertRaises(ValueError):
                validate_log(self.repo, {"schemaVersion": 1, "reviews": records})

    def test_history_checker_rejects_mutation_and_allows_append(self) -> None:
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        record = self.record(Scope("file", ("src/a/a.zig",)), "file_review")
        payload = {"schemaVersion": 1, "reviews": [record]}
        (self.repo / LOG).write_text(canonical_json(payload), encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Review test", "-c", "user.email=review@example.invalid",
             "-c", "commit.gpgsign=false", "commit", "-qm", "fixture"],
            cwd=self.repo, check=True,
        )
        changed = copy.deepcopy(payload)
        changed["reviews"][0]["summary"] = "Rewritten history."
        with self.assertRaisesRegex(ValueError, "append a superseding"):
            check_history(self.repo, changed)
        appended = copy.deepcopy(payload)
        appended["reviews"].append(record | {"reviewId": "next", "supersedes": "file_review"})
        check_history(self.repo, appended)
        base = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=self.repo, text=True,
        ).strip()
        (self.repo / LOG).write_text(canonical_json(changed), encoding="utf-8")
        subprocess.run(["git", "add", LOG], cwd=self.repo, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Review test", "-c", "user.email=review@example.invalid",
             "-c", "commit.gpgsign=false", "commit", "-qm", "rewrite fixture"],
            cwd=self.repo, check=True,
        )
        with self.assertRaisesRegex(ValueError, "append a superseding"):
            check_history(self.repo, changed, base_ref=base)

    def test_source_inventory_includes_new_files_and_excludes_outputs(self) -> None:
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        for name in ("src/new.zig", "tests/new.zig", "vendor/new.zig", "zig-out/new.zig"):
            path = self.repo / "runtime/zig" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("const value = 1;\n", encoding="utf-8")
        self.assertEqual(set(source_files(self.repo)), {"src/new.zig", "tests/new.zig"})


if __name__ == "__main__":
    unittest.main()

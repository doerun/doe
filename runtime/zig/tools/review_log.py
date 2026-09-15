"""Maintain source-bound review coverage from files through system boundaries."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from source_architecture import analyze, canonical_json, load_json_strict


REPO = Path(__file__).resolve().parents[3]
RUNTIME = "runtime/zig"
LOG = RUNTIME + "/reviews/log.json"
SCHEMA = "config/zig-review-log.schema.json"
QUEUE = RUNTIME + "/reviews/queue.tsv"
GUIDANCE = (
    "AGENTS.md", "GOALS.md", "docs/architecture.md", "docs/process.md",
    RUNTIME + "/STYLE.md", RUNTIME + "/reviews/README.md", SCHEMA,
    RUNTIME + "/tools/review_log.py",
)
LEVELS = ("file", "directory", "within_directory", "cross_directory", "system")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def checked_path(repo: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    if (
        not relative or path.is_absolute() or ".." in path.parts
        or path.as_posix() != relative
        or any(char in relative for char in "\\\t\r\n")
    ):
        raise ValueError(f"expected canonical repository-relative path: {relative!r}")
    result = repo / relative
    if not result.resolve().is_relative_to(repo.resolve()):
        raise ValueError(f"path leaves repository: {relative}")
    return result


@dataclass(frozen=True, order=True)
class Scope:
    level: str
    targets: tuple[str, ...]

    @property
    def key(self) -> str:
        return self.level + ":" + "|".join(self.targets)

    def members(self, files: dict[str, str]) -> dict[str, str]:
        if self.level == "file":
            return {path: files[path] for path in self.targets if path in files}
        return {
            path: sha for path, sha in files.items()
            if any(target == "." or path.startswith(target + "/")
                   for target in self.targets)
        }


def review_scope(review: dict[str, Any]) -> Scope:
    return Scope(review["level"], tuple(review["targets"]))


def make_scopes(
    files: dict[str, str], edges: list[tuple[str, str]],
    reviews: list[dict[str, Any]],
) -> dict[Scope, tuple[Scope, ...]]:
    """Derive bottom-up prerequisites; extra relationship scopes stay explicit."""
    directories = {
        parent.as_posix()
        for path in files for parent in PurePosixPath(path).parents
    }
    scopes: dict[Scope, tuple[Scope, ...]] = {
        Scope("file", (path,)): () for path in sorted(files)
    }
    for directory in sorted(directories):
        direct_files = tuple(
            Scope("file", (path,)) for path in sorted(files)
            if PurePosixPath(path).parent.as_posix() == directory
        )
        own = Scope("directory", (directory,))
        scopes[own] = direct_files
        children = tuple(
            Scope("within_directory", (child,))
            for child in sorted(directories)
            if child != directory
            and PurePosixPath(child).parent.as_posix() == directory
        )
        scopes[Scope("within_directory", (directory,))] = (own, *children)
    pairs = {
        tuple(sorted({PurePosixPath(a).parent.as_posix(),
                      PurePosixPath(b).parent.as_posix()}))
        for a, b in edges
    }
    pairs.update(
        tuple(review["targets"]) for review in reviews
        if review["level"] == "cross_directory"
    )
    for targets in sorted(pairs):
        if len(targets) > 1 and all(path in directories for path in targets):
            scopes[Scope("cross_directory", targets)] = tuple(
                Scope("within_directory", (path,)) for path in targets
            )
    scopes[Scope("system", (".",))] = (
        Scope("within_directory", (".",)),
        *sorted(scope for scope in scopes if scope.level == "cross_directory"),
    )
    return scopes


def source_files(repo: Path) -> dict[str, str]:
    result = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard",
         "--", RUNTIME + "/"], cwd=repo,
    )
    files = {}
    for name in sorted(set(filter(None, result.decode().split("\0")))):
        path = PurePosixPath(name).relative_to(RUNTIME)
        if path.suffix != ".zig" or any(
            part in ("vendor", ".zig-cache", "zig-out") for part in path.parts
        ):
            continue
        source = checked_path(repo, name)
        if source.exists():
            files[path.as_posix()] = digest(source.read_bytes())
    return files


def input_hash(
    repo: Path, scope: Scope, files: dict[str, str], policy: dict[str, Any],
) -> str:
    members = scope.members(files)
    guidance = set(GUIDANCE)
    for name in members:
        for parent in PurePosixPath(RUNTIME + "/" + name).parents:
            for filename in ("AGENTS.md", "CATSCAN.md"):
                candidate = (parent / filename).as_posix()
                if checked_path(repo, candidate).is_file():
                    guidance.add(candidate)
    inputs = {
        "level": scope.level,
        "targets": scope.targets,
        "sources": members,
        "policy": policy,
        "guidance": {
            path: digest(checked_path(repo, path).read_bytes())
            for path in sorted(guidance)
        },
    }
    return digest(canonical_json(inputs).encode())


def validate_log(repo: Path, payload: dict[str, Any]) -> None:
    schema = load_json_strict(repo / SCHEMA)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    validator.validate(payload)
    seen: dict[str, dict[str, Any]] = {}
    latest: dict[Scope, str] = {}
    for review in payload["reviews"]:
        scope = review_scope(review)
        review_id = review["reviewId"]
        if review_id in seen:
            raise ValueError(f"duplicate reviewId: {review_id}")
        if scope.targets != tuple(sorted(scope.targets)):
            raise ValueError(f"review targets must be sorted: {review_id}")
        for target in scope.targets:
            checked_path(repo / RUNTIME, target)
        if scope.level == "file" and PurePosixPath(scope.targets[0]).suffix != ".zig":
            raise ValueError(f"file review requires a Zig file: {review_id}")
        if scope.level == "system" and scope.targets != (".",):
            raise ValueError(f"system review requires target '.': {review_id}")
        if review["supersedes"] != latest.get(scope):
            raise ValueError(f"supersedes must name the previous scope review: {review_id}")
        for prerequisite in review["prerequisites"]:
            if prerequisite not in seen:
                raise ValueError(f"prerequisite must precede review: {prerequisite}")
        for kind in ("context", "evidence"):
            paths = [item["path"] for item in review[kind]]
            if len(set(paths)) != len(paths):
                raise ValueError(f"duplicate {kind} path: {review_id}")
            for path in paths:
                checked_path(repo, path)
        seen[review_id] = review
        latest[scope] = review_id


def check_history(repo: Path, payload: dict[str, Any], base_ref: str = "HEAD") -> None:
    base_commit = subprocess.check_output(
        ["git", "rev-parse", "--verify", "--end-of-options", base_ref + "^{commit}"],
        cwd=repo, text=True,
    ).strip()
    tracked = subprocess.check_output(
        ["git", "ls-tree", base_commit, "--", LOG], cwd=repo,
    )
    if not tracked:
        return
    previous = json.loads(subprocess.check_output(
        ["git", "show", base_commit + ":" + LOG], cwd=repo,
    ))
    old = previous["reviews"]
    if payload["reviews"][:len(old)] != old:
        raise ValueError("review history changed; append a superseding entry")


def current_statuses(
    repo: Path, scopes: dict[Scope, tuple[Scope, ...]],
    fingerprints: dict[Scope, str], reviews: list[dict[str, Any]],
) -> tuple[dict[Scope, str], dict[Scope, dict[str, Any]]]:
    latest = {review_scope(review): review for review in reviews}
    statuses: dict[Scope, str] = {}

    def evaluate(scope: Scope) -> str:
        if scope in statuses:
            return statuses[scope]
        review = latest.get(scope)
        if scope not in scopes:
            status = "retired"
        elif review is None:
            status = "pending"
        elif review["inputHash"] != fingerprints[scope]:
            status = "stale"
        else:
            bound = review["context"] + review["evidence"]
            intact = all(
                checked_path(repo, item["path"]).is_file()
                and digest(checked_path(repo, item["path"]).read_bytes()) == item["sha256"]
                for item in bound
            )
            status = review["status"] if intact else "stale"
            if status == "verified":
                prerequisites = scopes[scope]
                complete = all(evaluate(item) == "verified" for item in prerequisites)
                expected = {
                    latest[item]["reviewId"] for item in prerequisites if item in latest
                }
                if not complete or set(review["prerequisites"]) != expected:
                    status = "blocked"
        statuses[scope] = status
        return status

    for scope in sorted(set(scopes) | set(latest)):
        evaluate(scope)
    return statuses, latest


def render_queue(
    scopes: dict[Scope, tuple[Scope, ...]], statuses: dict[Scope, str],
    latest: dict[Scope, dict[str, Any]],
) -> str:
    output = io.StringIO()
    writer = csv.writer(output, delimiter="\t", lineterminator="\n")
    writer.writerow(("level", "targets", "status", "latestReview", "prerequisites", "nextAction"))
    for scope in sorted(statuses, key=lambda item: (LEVELS.index(item.level), item.targets)):
        review = latest.get(scope, {})
        writer.writerow((
            scope.level, "|".join(scope.targets), statuses[scope],
            review.get("reviewId", ""),
            ";".join(item.key for item in scopes.get(scope, ())),
            review.get("nextAction", "Read and review the complete scope."),
        ))
    return output.getvalue()


def bound_files(repo: Path, paths: list[str]) -> list[dict[str, str]]:
    return [
        {"path": path, "sha256": digest(checked_path(repo, path).read_bytes())}
        for path in sorted(set(paths))
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write", action="store_true", help="regenerate queue only")
    action.add_argument("--check", action="store_true", help="validate history and queue")
    action.add_argument("--draft", choices=LEVELS, help="print an unfinished review record")
    parser.add_argument("--target", action="append", default=[], help="runtime-relative review target")
    parser.add_argument("--context", action="append", default=[], help="additional repository-relative input")
    parser.add_argument("--evidence", action="append", default=[], help="repository-relative verification artifact")
    parser.add_argument("--reviewer", help="identity of the reviewer")
    parser.add_argument("--review-id", help="unique review identifier")
    parser.add_argument("--base-ref", default="HEAD", help="commit against which history must be append-only")
    args = parser.parse_args()
    payload = load_json_strict(REPO / LOG)
    validate_log(REPO, payload)
    check_history(REPO, payload, args.base_ref)
    policy = load_json_strict(REPO / RUNTIME / "source-layout.json")
    files = source_files(REPO)
    analysis = analyze(REPO / RUNTIME, policy)
    policy["architecture"].pop("moduleDecisionReviews", None)
    reviews = payload["reviews"]
    scope_reviews = list(reviews)
    if args.draft:
        if not args.target or not args.reviewer or not args.review_id:
            parser.error("--draft requires --target, --reviewer, and --review-id")
        scope_reviews.append({"level": args.draft, "targets": sorted(set(args.target))})
    scopes = make_scopes(files, [(edge.source, edge.target) for edge in analysis.edges], scope_reviews)
    reviewed_scopes = {review_scope(review) for review in scope_reviews}
    fingerprints = {
        scope: input_hash(REPO, scope, files, policy)
        for scope in scopes if scope in reviewed_scopes
    }
    if source_files(REPO) != files:
        raise ValueError("Zig source changed during review inventory; retry")
    statuses, latest = current_statuses(REPO, scopes, fingerprints, reviews)
    if args.draft:
        scope = Scope(args.draft, tuple(sorted(set(args.target))))
        if scope not in scopes:
            raise ValueError(f"review scope does not exist: {scope.key}")
        record = {
            "reviewId": args.review_id, "level": scope.level,
            "targets": list(scope.targets), "status": "in_progress",
            "reviewer": args.reviewer,
            "reviewedAt": datetime.now(timezone.utc).isoformat(),
            "sourceCommit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=REPO, text=True,
            ).strip(),
            "inputHash": fingerprints[scope],
            "supersedes": latest.get(scope, {}).get("reviewId"),
            "prerequisites": [
                latest[item]["reviewId"] for item in scopes[scope]
                if statuses[item] == "verified"
            ],
            "context": bound_files(REPO, args.context),
            "summary": "Review started; complete examination is pending.",
            "findings": [], "resolvedFindings": [],
            "evidence": bound_files(REPO, args.evidence),
            "nextAction": "Read the complete scope and record specific findings.",
        }
        validate_log(REPO, {"schemaVersion": 1, "reviews": reviews + [record]})
        print(canonical_json(record), end="")
        return 0
    queue = render_queue(scopes, statuses, latest)
    if args.write:
        (REPO / QUEUE).write_text(queue, encoding="utf-8")
    elif (REPO / QUEUE).read_text(encoding="utf-8") != queue:
        raise ValueError("review queue is stale; run review_log.py --write")
    print("Review log and queue valid; unfinished coverage remains explicit.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as error:
        print(f"review log schema {error.json_path}: {error.message}", file=sys.stderr)
        raise SystemExit(1)
    except (OSError, ValueError) as error:
        print(f"review log: {error}", file=sys.stderr)
        raise SystemExit(1)

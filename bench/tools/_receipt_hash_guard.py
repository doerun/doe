"""Schema-enforced hash spine for Doe receipts (north-star rung 1).

Imported by Doe receipt writers; rejects emit when the receipt's cited
identity hashes do not chain back to the live bundle / host-plan / fixture
artifacts. The existing audit-time gate
(`bench/tools/prepack_hash_drift_guard.py`) catches drift at pack time
against a pinned baseline; this guard is the upstream catch at receipt-emit
time, before stale receipts ship downstream.

Three checks:

  (a) cited manifest hash matches the live manifest at the bundle path,
  (b) `hostPlanHash` chains back to the manifest (when the receipt cites
      a hostPlanPath, the file's sha256 must equal the cited
      `hostPlanHash`),
  (c) `referenceFixtureHash` is present for any receipt with
      `receiptClass.startswith("manifest_shape")` and
      `comparisonMode == "parity"`.

The guard intentionally validates only the receipt fields it knows about;
unknown fields pass through untouched. Failure is structured: the guard
returns a list of violations and a verdict, and exposes `enforce()` for
callers that want a hard exit.

Receipt writers wire it like:

    from _receipt_hash_guard import enforce_receipt_hash_spine
    enforce_receipt_hash_spine(receipt, repo_root)

Failure raises `ReceiptHashSpineError` with the violation list; callers
either catch (to record a typed-blocked receipt) or let it propagate.

This module is dependency-free aside from the standard library. It is
intentionally simple so it can be imported by any Python receipt writer
without bringing in pyproject scaffolding.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PENDING_TOKENS = frozenset(["", "pending", "<pending>", "unknown", "absent"])


class ReceiptHashSpineError(RuntimeError):
    """Raised when a receipt's identity hash chain does not validate."""


@dataclass
class HashSpineReport:
    """Structured result of evaluating a receipt against the hash spine."""

    bound: bool
    violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "artifactKind": "doe_receipt_hash_spine_report",
            "bound": self.bound,
            "violations": list(self.violations),
        }


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve(repo_root: Path, raw: str | None) -> Path | None:
    if not raw or raw in PENDING_TOKENS:
        return None
    p = Path(raw)
    return p if p.is_absolute() else (repo_root / p).resolve()


def _check_manifest_hash(
    receipt: dict[str, Any],
    repo_root: Path,
) -> list[str]:
    cited = receipt.get("manifestSha256")
    manifest_path = receipt.get("manifestPath")
    if not cited or cited in PENDING_TOKENS:
        return []
    if not manifest_path:
        return [
            "manifestSha256 cited without manifestPath — cannot verify "
            "the hash chains back to a live artifact"
        ]
    resolved = _resolve(repo_root, manifest_path)
    if resolved is None or not resolved.is_file():
        return [
            f"manifestPath={manifest_path!r} does not resolve to a file "
            f"under repo_root={repo_root}"
        ]
    observed = _sha256_file(resolved)
    if observed != cited:
        return [
            f"manifestSha256 drift: cited={cited!r} but live "
            f"{manifest_path!r} hashes to {observed!r}"
        ]
    return []


def _check_host_plan_hash(
    receipt: dict[str, Any],
    repo_root: Path,
) -> list[str]:
    cited = receipt.get("hostPlanHash")
    host_plan_path = receipt.get("hostPlanPath")
    if not cited or cited in PENDING_TOKENS:
        return []
    if not host_plan_path:
        return [
            "hostPlanHash cited without hostPlanPath — cannot verify "
            "the hash chains back to a live host plan"
        ]
    resolved = _resolve(repo_root, host_plan_path)
    if resolved is None or not resolved.is_file():
        return [
            f"hostPlanPath={host_plan_path!r} does not resolve to a file "
            f"under repo_root={repo_root}"
        ]
    observed = _sha256_file(resolved)
    if observed != cited:
        return [
            f"hostPlanHash drift: cited={cited!r} but live "
            f"{host_plan_path!r} hashes to {observed!r}"
        ]
    return []


def _check_reference_fixture_hash(
    receipt: dict[str, Any],
) -> list[str]:
    receipt_class = receipt.get("receiptClass", "")
    comparison_mode = receipt.get("comparisonMode", "")
    if not isinstance(receipt_class, str) or not receipt_class.startswith(
        "manifest_shape"
    ):
        return []
    if comparison_mode != "parity":
        return []
    fixture_hash = receipt.get("referenceFixtureHash")
    if fixture_hash and fixture_hash not in PENDING_TOKENS:
        return []
    return [
        "manifest_shape * parity receipt missing referenceFixtureHash — "
        "the frozen Doppler reference fixture's digest must be cited so "
        "downstream readers can re-derive identity (rung 1 contract)"
    ]


def evaluate_receipt_hash_spine(
    receipt: dict[str, Any],
    repo_root: Path | None = None,
) -> HashSpineReport:
    """Evaluate `receipt` against the schema-enforced hash spine.

    Returns a structured report. Use `enforce_receipt_hash_spine` if you
    want a raise-on-fail entry point.
    """
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[2]
    violations: list[str] = []
    violations.extend(_check_manifest_hash(receipt, repo_root))
    violations.extend(_check_host_plan_hash(receipt, repo_root))
    violations.extend(_check_reference_fixture_hash(receipt))
    return HashSpineReport(bound=not violations, violations=violations)


def enforce_receipt_hash_spine(
    receipt: dict[str, Any],
    repo_root: Path | None = None,
) -> None:
    """Validate the receipt or raise `ReceiptHashSpineError`."""
    report = evaluate_receipt_hash_spine(receipt, repo_root=repo_root)
    if not report.bound:
        raise ReceiptHashSpineError(
            "receipt hash spine violations: " + "; ".join(report.violations)
        )


def evaluate_receipt_path(
    receipt_path: Path,
    repo_root: Path | None = None,
) -> HashSpineReport:
    """Convenience: load a receipt JSON file and evaluate it."""
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    return evaluate_receipt_hash_spine(receipt, repo_root=repo_root)

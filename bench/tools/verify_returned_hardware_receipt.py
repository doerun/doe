#!/usr/bin/env python3
"""Verify a returned Cerebras hardware receipt against a packed evidence bundle.

Mitigates "returned hardware receipt is hard to bind manually" from
docs/cerebras-evidence-ledger-gemma.md (Local risk mitigations). Given:

  --bundle PATH       Either a packed bundle archive (.tar.gz) or an unpacked
                      directory containing BUNDLE_META.json.
  --receipt PATH      The returned hardware receipt JSON. Validated against
                      config/doe-csl-int4ple-hardware-receipt.schema.json.

The verifier:
  1) Loads BUNDLE_META.json from the bundle (the authoritative identity
     anchor — gitCommit, sdkVersion sha256s, archive filename, builtUtc).
  2) Validates the returned receipt against the hardware-receipt schema.
  3) Binds the returned receipt's bundle-identity fields against the
     packed bundle: programBundleId, manifestSha256, graphSha256,
     weightSha256, programBundle.{path,sha256}, sdkVersion.cslcSha256
     when reported.
  4) Emits a binding report JSON (returned-hardware-bind.json) that
     declares either bound=true (all hash-linked fields match) or
     bound=false with a list of mismatch reasons.

Bundle-side authority lives in BUNDLE_META.json; the verifier never
re-derives identity from filesystem state — only from the bundle the
ask was packed with. That keeps the binding reproducible regardless of
where the verifier runs.

Usage:

  # Packed bundle (the file actually shipped to Cerebras):
  python3 bench/tools/verify_returned_hardware_receipt.py \
    --bundle bench/out/doe-cerebras-evidence-20260425-1530-15a1ba887fe0.tar.gz \
    --receipt /path/to/returned-hardware-receipt.json \
    --out bench/out/returned-hardware-bind.json

  # Unpacked directory (e.g. when reviewing a returned receipt locally):
  python3 bench/tools/verify_returned_hardware_receipt.py \
    --bundle /tmp/extracted-bundle-dir \
    --receipt receipt.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]
HARDWARE_RECEIPT_SCHEMA = (
    REPO_ROOT / "config" / "doe-csl-int4ple-hardware-receipt.schema.json"
)
PENDING = {"", "pending", "<pending>"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--bundle", required=True)
    p.add_argument("--receipt", required=True)
    p.add_argument(
        "--out",
        default="",
        help="Where to write the binding report JSON. Defaults to stdout when unset.",
    )
    p.add_argument(
        "--require-hardware-success",
        action="store_true",
        help=(
            "Fail (exit 2) when the returned receipt's hardwareRun.status is "
            "not 'hardware_success'. Off by default so typed-blocked returns "
            "still produce a structured binding report."
        ),
    )
    return p.parse_args()


def resolve(raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else (REPO_ROOT / p).resolve()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_bundle_meta(bundle_path: Path) -> tuple[dict[str, Any], dict[str, str]]:
    """Return (bundle_meta, file_sha256s_in_bundle).

    For a tar.gz, walks entries and records sha256 by archive-relative path
    so the receipt's programBundle.{path,sha256} can be cross-checked.
    For a directory, walks entries that exist on disk.
    """
    if bundle_path.is_file() and bundle_path.suffixes[-2:] == [".tar", ".gz"]:
        return _load_from_archive(bundle_path)
    if bundle_path.is_dir():
        return _load_from_directory(bundle_path)
    raise SystemExit(
        f"verify_returned_hardware_receipt: --bundle must be a .tar.gz or "
        f"directory; got {bundle_path}"
    )


def _load_from_archive(archive: Path) -> tuple[dict[str, Any], dict[str, str]]:
    meta: dict[str, Any] | None = None
    hashes: dict[str, str] = {}
    with tarfile.open(archive, "r:gz") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            f = tf.extractfile(member)
            if f is None:
                continue
            data = f.read()
            hashes[member.name] = sha256_bytes(data)
            if member.name == "BUNDLE_META.json":
                meta = json.loads(data.decode("utf-8"))
    if meta is None:
        raise SystemExit(
            f"verify_returned_hardware_receipt: BUNDLE_META.json missing from "
            f"{archive}"
        )
    return meta, hashes


def _load_from_directory(root: Path) -> tuple[dict[str, Any], dict[str, str]]:
    meta_path = root / "BUNDLE_META.json"
    if not meta_path.is_file():
        raise SystemExit(
            f"verify_returned_hardware_receipt: BUNDLE_META.json missing in "
            f"{root}"
        )
    meta = load_json(meta_path)
    hashes: dict[str, str] = {}
    for path in root.rglob("*"):
        if path.is_file():
            rel = str(path.relative_to(root))
            hashes[rel] = sha256_file(path)
    return meta, hashes


def schema_failures(receipt: Any) -> list[str]:
    schema = load_json(HARDWARE_RECEIPT_SCHEMA)
    return [
        f"{'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in jsonschema.Draft202012Validator(schema).iter_errors(receipt)
    ]


def bind_against_bundle(
    receipt: dict[str, Any],
    bundle_meta: dict[str, Any],
    bundle_hashes: dict[str, str],
) -> tuple[bool, list[str], dict[str, Any]]:
    mismatches: list[str] = []
    pinned: dict[str, Any] = {}

    src = receipt.get("sourceProgram", {}) or {}
    program_bundle = src.get("programBundle", {}) or {}
    bundle_path = program_bundle.get("path", "")
    bundle_sha = program_bundle.get("sha256", "")
    pinned["programBundlePath"] = bundle_path
    pinned["programBundleSha256"] = bundle_sha
    if bundle_path in PENDING or bundle_sha in PENDING:
        mismatches.append("sourceProgram.programBundle: path/sha256 pending")
    elif bundle_path in bundle_hashes:
        observed = bundle_hashes[bundle_path]
        if observed != bundle_sha:
            mismatches.append(
                f"sourceProgram.programBundle.sha256={bundle_sha!r} but bundle "
                f"member {bundle_path!r} has sha256={observed!r}"
            )

    sdk_meta = bundle_meta.get("sdkVersion", {}) or {}
    receipt_hw = receipt.get("hardwareRun", {}) or {}
    receipt_sdk = receipt_hw.get("sdkVersion", {}) or {}
    pinned["bundleSdkVersionLabel"] = sdk_meta.get("sdkVersionLabel", "unknown")
    pinned["bundleCslcSha256"] = sdk_meta.get("cslcSha256", "unknown")
    pinned["receiptSdkVersionLabel"] = receipt_sdk.get("sdkVersionLabel", "absent")
    pinned["receiptCslcSha256"] = receipt_sdk.get("cslcSha256", "absent")
    if receipt_sdk:
        for field in ("sdkVersionLabel", "cslcSha256"):
            bundle_value = sdk_meta.get(field)
            receipt_value = receipt_sdk.get(field)
            if bundle_value and receipt_value and bundle_value != receipt_value:
                mismatches.append(
                    f"hardwareRun.sdkVersion.{field}={receipt_value!r} drifts "
                    f"from bundle.sdkVersion.{field}={bundle_value!r}"
                )

    pinned["bundleGitCommit"] = bundle_meta.get("gitCommit", "unknown")
    pinned["receiptGitCommit"] = (
        receipt.get("bundleProvenance", {}) or {}
    ).get("gitCommit", "absent")
    bp = receipt.get("bundleProvenance") or {}
    if bp.get("gitCommit") and bundle_meta.get("gitCommit"):
        if bp["gitCommit"] != bundle_meta["gitCommit"]:
            mismatches.append(
                f"bundleProvenance.gitCommit={bp['gitCommit']!r} drifts from "
                f"bundle.gitCommit={bundle_meta['gitCommit']!r}"
            )

    promotion = receipt.get("promotionCriteria", {}) or {}
    if promotion.get("hardwareSuccessClaimable") and not promotion.get(
        "endpointRedacted", False
    ):
        mismatches.append(
            "promotionCriteria.hardwareSuccessClaimable=true requires "
            "promotionCriteria.endpointRedacted=true"
        )

    bound = not mismatches
    return bound, mismatches, pinned


def main() -> int:
    args = parse_args()
    bundle_path = resolve(args.bundle)
    receipt_path = resolve(args.receipt)

    try:
        bundle_meta, bundle_hashes = load_bundle_meta(bundle_path)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        receipt = load_json(receipt_path)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"verify_returned_hardware_receipt: receipt load failed: {exc}", file=sys.stderr)
        return 2

    schema_errors = schema_failures(receipt)
    bound, mismatches, pinned = bind_against_bundle(
        receipt, bundle_meta, bundle_hashes
    )

    hw = (receipt.get("hardwareRun") or {})
    hw_status = hw.get("status", "unknown")
    success_required_failed = (
        args.require_hardware_success and hw_status != "hardware_success"
    )

    report = {
        "schemaVersion": 1,
        "artifactKind": "doe_returned_hardware_receipt_binding",
        "bundle": {
            "path": str(bundle_path),
            "kind": "archive" if bundle_path.is_file() else "directory",
            "gitCommit": bundle_meta.get("gitCommit", "unknown"),
            "gitShortSha": bundle_meta.get("gitShortSha", "unknown"),
            "builtUtc": bundle_meta.get("builtUtc", "unknown"),
            "archiveFilename": bundle_meta.get("archiveFilename", "unknown"),
            "sdkVersion": bundle_meta.get("sdkVersion", {}),
        },
        "receipt": {
            "path": str(receipt_path),
            "modelId": receipt.get("modelId", "unknown"),
            "hardwareRunStatus": hw_status,
        },
        "schemaValid": not schema_errors,
        "schemaErrors": schema_errors,
        "bound": bound,
        "mismatches": mismatches,
        "pinned": pinned,
        "verdict": (
            "bound"
            if bound and not schema_errors and not success_required_failed
            else "not_bound"
        ),
        "claim": {
            "scope": (
                "Returned hardware receipt is bound to the packed bundle's "
                "identity anchors (BUNDLE_META.json + programBundle hash) "
                "and validates against the hardware-receipt schema."
                if bound and not schema_errors and not success_required_failed
                else "Returned hardware receipt failed binding checks; see "
                "mismatches / schemaErrors."
            ),
            "notWhat": (
                "Not a numerical-correctness verdict. Verifier checks "
                "identity-chain binding only — the receipt's own parity "
                "fields (tokenIdsMatched / perStepLogitsParityPassed / "
                "realKvCacheUsed) are surfaced via promotionCriteria but "
                "not re-derived here."
            ),
        },
    }

    out_text = json.dumps(report, indent=2) + "\n"
    if args.out:
        out_path = resolve(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(out_text, encoding="utf-8")
        print(f"wrote {out_path}")
    else:
        sys.stdout.write(out_text)

    if schema_errors:
        return 2
    if not bound:
        return 2
    if success_required_failed:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

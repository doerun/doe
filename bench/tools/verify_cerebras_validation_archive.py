#!/usr/bin/env python3
"""Verify a packed Cerebras evidence archive from the outside.

Extracts the tarball to a temp directory, re-reads MANIFEST.txt and
BUNDLE_META.json, and confirms:

  1. Required top-level files are present: BUNDLE_META.json,
     MANIFEST.txt, CLAIM_SCOPE.md, README.md, CEREBRAS_ASK.md,
     LOCAL_INSPECTION.md.
  2. Every file listed in the manifest is present in the archive at
     the declared path.
  3. Every file's sha256 matches the manifest entry's recorded hash.
  4. BUNDLE_META.json parses, declares an expected artifactKind, and
     carries required fields (gitCommit, gitDirtyTree, builtUtc,
     archiveFilename, claimScopeSource).
  5. The archive filename matches the BUNDLE_META.archiveFilename
     field (no rename between pack and verify).
  6. Claim-role taxonomy in MANIFEST.txt uses only known roles.
  7. No file in the archive has a forbidden extension (SDK binaries,
     tensor bytes, logs) — defense-in-depth over the packer's
     allow-list, catches hand-edited tarballs.
  8. No file in the archive has a forbidden path substring
     (`/scratch/`, `/compile/`, `/compile-L`, `simulator.log`) —
     mirrors the packer's non-extension deny-list.
  9. Claim-discipline scan over every text file: hardware-gated and
     MoE-gated rules must not match anywhere outside the skip-listed
     rule-enumerating docs.

Intended to be run on the bundler's own output before external send:
pack → verify against the packed file → send if verify=0.

Usage:
  python3 bench/tools/verify_cerebras_validation_archive.py \\
    --archive bench/out/doe-cerebras-evidence-20260420-1200-abc123.tar.gz

Exit 0 on pass, 1 on any integrity failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "bench" / "gates"))

# Import the live claim-discipline rules so archive scans match
# exactly what the repo gate enforces. When new rules land in the
# repo gate, this verifier picks them up on next invocation.
from claim_discipline_gate import (  # noqa: E402
    HARDWARE_GATED_RULES,
    MOE_GATED_RULES,
)

TEXT_SUFFIXES = {".md", ".txt", ".json"}

# Archive paths whose job IS to enumerate rejected claims. These
# files mention forbidden phrases as part of their content (a rule
# document must be able to name the rule). They are skipped by the
# claim-discipline scan on the archive for the same reason the repo
# gate skips docs/claim-discipline.md itself.
# Extensions that must never appear inside the archive, independent of
# what the packer's allow-list said. Catches the case where a hand-edited
# tarball gets SDK binary bytes or tensor bytes smuggled in.
FORBIDDEN_EXTENSIONS = {
    ".elf", ".lst", ".map", ".symbols", ".viz",
    ".f32", ".stderr", ".stdout",
}

# Path substrings that must never appear inside the archive even if
# the file extension looks benign. Mirrors the packer's non-extension
# EXCLUDE_SUBSTRINGS entries so a hand-edited tarball with e.g.
# bench/out/scratch/foo.json (benign .json extension, but from a
# scratch dir the packer would have blocked) still gets caught.
FORBIDDEN_PATH_SUBSTRINGS = {
    "/scratch/", "/compile/", "/compile-L", "simulator.log",
}

CLAIM_SCAN_SKIP_ARCHIVE_PATHS = {
    "CLAIM_SCOPE.md",                         # archive-root governance
    "MODEL_ACCESS.md",                        # recites artifact/cache claim scope
    "README.md",                              # recites taxonomy + what-not-to-claim
    "CEREBRAS_ASK.md",                        # enumerates what we will NOT publish
    "LOCAL_INSPECTION.md",                    # references deny-listed artifact types
    "docs/claim-discipline.md",
    "docs/cerebras-evidence-bundle-claim-scope.md",
    "docs/cerebras-evidence-bundle-readme.md",
    "docs/cerebras-evidence-bundle-model-access.md",
    "docs/cerebras-evidence-bundle-ask.md",
    "docs/cerebras-evidence-bundle-local-inspection.md",
    "docs/cerebras-evidence-bundle-pointer.md",
    "docs/hardware-validation-appendix.md",   # enumerates what we will NOT publish
    "docs/numeric-stability-claim-ladder.md",
    "bench/out/26b-moe-lane/lane-status.json",
}


def scan_bytes(data: bytes, rules) -> list[tuple[str, int, str]]:
    hits: list[tuple[str, int, str]] = []
    for rule in rules:
        for match in rule.pattern.finditer(data):
            line_no = data.count(b"\n", 0, match.start()) + 1
            snippet = match.group(0).decode("utf-8", "replace")
            hits.append((rule.label, line_no, snippet))
    return hits

def _load_known_claim_roles() -> set[str]:
    """Import the live CLAIM_ROLE dict from the packager and use its
    values as the authoritative role taxonomy. Keeps the packer and
    verifier in sync automatically: a new role landed in the packager
    is accepted by the verifier on next invocation, without touching
    this file. Falls back to a static set only if the import fails."""
    packer_py = (
        Path(__file__).resolve().parent / "pack_cerebras_validation_archive.py"
    )
    try:
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location("_doe_packer", str(packer_py))
        mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return set(mod.CLAIM_ROLE.values())
    except (OSError, ImportError, AttributeError):
        return {
            "governance",
            "real-weight-fixture",
            "doppler-rdrr-fixture",
            "model-runtime-receipt",
            "cross-runtime-parity-verdict",
            "emulator-accuracy-verdict",
            "emulator-speed-verdict",
            "manifest-shape-probe",
            "manifest-shape-execution-oracle",
            "manifest-shape-attention-core",
            "manifest-shape-runtime-path",
            "doppler-webgpu-capture-graph",
            "doppler-webgpu-capture-lowering",
            "real-weight-parity-verdict",
            "doppler-rdrr-probe",
            "doppler-rdrr-q4k-extraction",
            "doppler-rdrr-q4k-audit",
            "doppler-rdrr-q4k-parity",
            "moe-lane-scope",
            "rollup",
            "depth-coverage-rollup",
        }


KNOWN_CLAIM_ROLES = _load_known_claim_roles()

BUNDLE_META_REQUIRED = [
    "schemaVersion",
    "artifactKind",
    "builtUtc",
    "archiveFilename",
    "gitCommit",
    "gitDirtyTree",
    "claimScopeSource",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--archive", required=True)
    return p.parse_args()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_manifest(text: str) -> tuple[list[tuple[str, str, str]], list[str]]:
    # Returns ([(sha, role, path), ...], errors).
    entries: list[tuple[str, str, str]] = []
    errors: list[str] = []
    for i, line in enumerate(text.splitlines()):
        # Data rows look like `<64-hex-sha>  <role>  <path>`. Header
        # and note lines are left alone.
        if not line or line.startswith(" ") or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        sha, role = parts[0], parts[1]
        if len(sha) != 64 or not all(c in "0123456789abcdef" for c in sha):
            continue
        path = " ".join(parts[2:])
        entries.append((sha, role, path))
    return entries, errors


def main() -> int:
    args = parse_args()
    archive_path = Path(args.archive).resolve()
    if not archive_path.is_file():
        print(f"FAIL: archive not found: {archive_path}")
        return 1

    failures: list[str] = []
    warnings: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        try:
            with tarfile.open(archive_path, "r:gz") as tf:
                tf.extractall(tmp_path)
        except (tarfile.TarError, OSError) as exc:
            print(f"FAIL: cannot extract archive: {exc}")
            return 1

        # 1. Required top-level files.
        meta_path = tmp_path / "BUNDLE_META.json"
        manifest_path = tmp_path / "MANIFEST.txt"
        claim_scope_path = tmp_path / "CLAIM_SCOPE.md"
        readme_path = tmp_path / "README.md"
        ask_path = tmp_path / "CEREBRAS_ASK.md"
        local_inspection_path = tmp_path / "LOCAL_INSPECTION.md"
        for required, label in [
            (meta_path, "BUNDLE_META.json"),
            (manifest_path, "MANIFEST.txt"),
            (claim_scope_path, "CLAIM_SCOPE.md"),
            (readme_path, "README.md"),
            (ask_path, "CEREBRAS_ASK.md"),
            (local_inspection_path, "LOCAL_INSPECTION.md"),
        ]:
            if not required.is_file():
                failures.append(f"missing top-level {label}")

        if failures:
            for f in failures:
                print(f"FAIL: {f}")
            return 1

        # 2. BUNDLE_META integrity.
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"FAIL: BUNDLE_META.json unreadable: {exc}")
            return 1
        for field in BUNDLE_META_REQUIRED:
            if field not in meta:
                failures.append(f"BUNDLE_META missing field: {field}")
        if meta.get("artifactKind") != "doe_cerebras_evidence_bundle_meta":
            failures.append(
                f"BUNDLE_META.artifactKind="
                f"{meta.get('artifactKind')!r}, expected "
                f"'doe_cerebras_evidence_bundle_meta'"
            )
        declared_name = meta.get("archiveFilename")
        if declared_name and declared_name != archive_path.name:
            failures.append(
                f"archive filename {archive_path.name!r} does not match "
                f"BUNDLE_META.archiveFilename {declared_name!r}"
            )
        if meta.get("gitDirtyTree") is True:
            warnings.append(
                "bundle built from a dirty git tree — receipts may not "
                "correspond to a reproducible commit"
            )

        # 3. Manifest: every entry resolves, re-hashes match.
        manifest_text = manifest_path.read_text(encoding="utf-8")
        entries, _ = parse_manifest(manifest_text)
        if not entries:
            failures.append("manifest contained zero data rows")
        files_checked = 0
        for sha, role, relpath in entries:
            if role not in KNOWN_CLAIM_ROLES:
                failures.append(
                    f"unknown claim-role {role!r} for {relpath}"
                )
            file_path = tmp_path / relpath
            if not file_path.is_file():
                failures.append(
                    f"manifest references {relpath} but it is not in "
                    f"the archive"
                )
                continue
            actual = sha256_bytes(file_path.read_bytes())
            if actual != sha:
                failures.append(
                    f"sha mismatch for {relpath}: manifest={sha} "
                    f"actual={actual}"
                )
            files_checked += 1

        # 3b. Defense-in-depth: scan the whole extracted tree for
        # forbidden extensions (SDK binaries, tensor bytes, logs).
        # The packer's deny-list blocks them at pack time; this
        # check catches a hand-edited tarball that bypasses the
        # packer. Applies to every file in the archive, not just
        # those listed in MANIFEST, so a smuggled file without a
        # manifest entry still gets caught.
        for p in tmp_path.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() in FORBIDDEN_EXTENSIONS:
                failures.append(
                    f"forbidden extension {p.suffix} in archive at "
                    f"{p.relative_to(tmp_path)} — SDK binaries, "
                    f"tensor bytes, and logs must never ship in the "
                    f"bundle"
                )
            rel_posix = p.relative_to(tmp_path).as_posix()
            # Normalize with a leading slash so substrings like
            # "/scratch/" match when the scratch dir is at the archive
            # root (rel_posix would otherwise have no leading slash).
            rel_match_target = "/" + rel_posix
            for substr in FORBIDDEN_PATH_SUBSTRINGS:
                if substr in rel_match_target:
                    failures.append(
                        f"forbidden path substring '{substr}' in "
                        f"archive at {rel_posix} — scratch dirs, "
                        f"compile artifacts, and simulator logs "
                        f"must never ship in the bundle"
                    )
                    break

    # 4. Negative claim scan: re-apply the live claim-discipline
    # rules to every text file inside the archive. Catches smuggled
    # claims a repo-only gate would miss on a hand-edited tarball.
    # Scope: hardware-gated rules run unconditionally (no in-archive
    # hardware_success receipt is expected); MoE-gated rules same.
    # Runs for every bundle by design: even after the repo gates go
    # inactive, the bundle scope stays narrow until it's explicitly
    # widened. No escape hatch flag; add one only when legitimate
    # post-hardware prose starts tripping the scan.
    all_rules = list(HARDWARE_GATED_RULES) + list(MOE_GATED_RULES)
    claim_violations: list[tuple[str, str, int, str]] = []
    # Re-enter the TemporaryDirectory context manager is gone by here,
    # so we re-extract into a fresh temp dir for the scan. Cheap.
    with tempfile.TemporaryDirectory() as scan_tmp:
        scan_root = Path(scan_tmp)
        try:
            with tarfile.open(archive_path, "r:gz") as tf:
                tf.extractall(scan_root)
        except (tarfile.TarError, OSError):
            scan_root = None  # type: ignore[assignment]
        if scan_root is not None:
            for p in scan_root.rglob("*"):
                if not p.is_file():
                    continue
                if p.suffix.lower() not in TEXT_SUFFIXES:
                    continue
                rel_path = str(p.relative_to(scan_root))
                if rel_path in CLAIM_SCAN_SKIP_ARCHIVE_PATHS:
                    continue
                try:
                    data = p.read_bytes()
                except OSError:
                    continue
                for label, line_no, snippet in scan_bytes(data, all_rules):
                    claim_violations.append(
                        (rel_path, label, line_no, snippet)
                    )

    if claim_violations:
        failures.append(
            f"claim-discipline scan on archive docs found "
            f"{len(claim_violations)} violation(s) — somebody hand-"
            f"edited the tarball to smuggle in a forbidden claim, "
            f"or rebuild the archive from a clean tree"
        )
        for path, label, line_no, snippet in claim_violations[:10]:
            failures.append(f"  {path}:{line_no}: {label}: {snippet!r}")
        if len(claim_violations) > 10:
            failures.append(
                f"  ... and {len(claim_violations) - 10} more"
            )

    if failures:
        print(
            f"FAIL: archive verification found "
            f"{len(failures)} integrity violation(s):"
        )
        for f in failures:
            print(f"  {f}")
        for w in warnings:
            print(f"  warning: {w}")
        return 1

    print(
        f"PASS: {archive_path.name} verified "
        f"({files_checked} files, manifest sha integrity OK, "
        f"claim-role taxonomy clean, BUNDLE_META complete, "
        f"claim-discipline scan clean)."
    )
    for w in warnings:
        print(f"  warning: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

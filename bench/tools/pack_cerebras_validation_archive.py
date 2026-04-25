#!/usr/bin/env python3
"""Pack a Cerebras hardware-validation archive.

Takes the governing evidence (hardware-validation appendix +
claim-discipline doc + evidence-bundle summary + model runtime
receipts + cross-runtime parity verdicts + real-weight parity
verdicts + Doppler RDRR probe/Q4_K_M parity + fixture contracts +
MoE lane-scope + archive-root governance docs) and bundles it into a dated tarball
suitable for attaching to a hardware-access ask.

What IS included: see the INCLUDE_FILES tuple below. Every bundled
file's sha256 is recorded in MANIFEST.txt with a claim-role tag.
C22 in bench/tools/e2b_layer_block_self_check.py asserts that tuple
and the CLAIM_ROLE dict stay in sync.

What is explicitly NOT included (sensitive size / provider bytes /
anything that would require operator approval to publish): see the
EXCLUDE_SUBSTRINGS tuple. Defense-in-depth: the verifier's
FORBIDDEN_EXTENSIONS and FORBIDDEN_PATH_SUBSTRINGS re-enforce the
same deny-list on the packed archive, and C23 / C32 lock the two
sides in sync.

Usage:
  # default: stamped filename with git sha, dirty flag if applicable
  python3 bench/tools/pack_cerebras_validation_archive.py
  # -> bench/out/doe-cerebras-evidence-YYYYMMDD-HHMM-<shortSha>[-dirty].tar.gz

  # or explicit path:
  python3 bench/tools/pack_cerebras_validation_archive.py \\
    --out bench/out/my-custom-bundle.tar.gz
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import subprocess
import sys
import tarfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DIAGNOSTIC_DEPTHS = (2, 4, 8, 35)

# Explicit allow-list. Nothing is bundled that isn't named here — the
# archive cannot accidentally pull SDK binaries or weight bytes
# because the loop walks THIS list, not a directory tree.
#
# Entries are strings OR (source_relpath, archive_relpath) tuples.
# Use the tuple form when the bundled file should sit at a different
# path inside the tarball than in the repo (e.g. surfacing a claim-
# scope doc at the archive root rather than under docs/).
# Tuple sources may use `path.md#ARCHIVE_NAME.md`; the packer extracts
# the matching `<!-- archive:ARCHIVE_NAME.md:start -->` section from
# that source doc.
INCLUDE_FILES: tuple = (
    ("docs/cerebras-evidence-bundle.md#README.md", "README.md"),
    ("docs/cerebras-evidence-bundle.md#CLAIM_SCOPE.md", "CLAIM_SCOPE.md"),
    ("docs/cerebras-evidence-bundle.md#MODEL_ACCESS.md", "MODEL_ACCESS.md"),
    ("docs/cerebras-evidence-bundle.md#CEREBRAS_ASK.md", "CEREBRAS_ASK.md"),
    ("docs/cerebras-evidence-bundle.md#LOCAL_INSPECTION.md", "LOCAL_INSPECTION.md"),
    # NOTE: docs/cerebras-evidence-bundle-pointer.md is intentionally
    # NOT bundled. The prep script writes it AFTER pack, so bundling
    # it would always ship stale values. BUNDLE_META.json inside the
    # archive is authoritative; the pointer doc is a repo-side mirror
    # for git visibility only.
    "docs/hardware-validation-appendix.md",
    "docs/claim-discipline.md",
    # Fixture contracts: one per primary model lane.
    "config/gemma-4-e2b-real-weight-fixture.json",
    "config/gemma-4-31b-real-weight-fixture.json",
    "config/gemma-4-e2b-doppler-rdrr-int4ple-fixture.json",
    # Model runtime receipts (json + md for each model).
    "bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json",
    "bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.md",
    "bench/out/31b-full-graph/gemma-4-31b-runtime-receipt.json",
    "bench/out/31b-full-graph/gemma-4-31b-runtime-receipt.md",
    # Cross-runtime parity verdicts (per model).
    "bench/out/streaming-executor/e2b-layer-block-cross-runtime-parity-check.json",
    "bench/out/streaming-executor/gemma-4-31b-layer-block-cross-runtime-parity-check.json",
    # CSL emulator evidence (claimable local-debug speed only for L1 today).
    "bench/out/doppler-reference/csl-emulator-speed-verdict-L1.json",
    # Manifest-shape blocker: upstream tensor metadata vs Doe manifest fields.
    "bench/out/manifest-shape/gemma-4-e2b-manifest-shape-probe.json",
    "bench/out/manifest-shape/gemma-4-e2b-manifest-shape-execution.json",
    "bench/out/manifest-shape/gemma-4-e2b-manifest-shape-attention-core.json",
    "bench/out/manifest-shape/gemma-4-e2b-manifest-shape-runtime-path.json",
    "bench/out/doppler-capture/gemma-4-e2b-doe-webgpu-capture-graph.json",
    "bench/out/doppler-capture/gemma-4-e2b-capture-to-csl-attention-core-lowering.json",
    # Real-weight parity verdicts and depth diagnostics.
    "bench/out/gemma-4-e2b-real-weight-parity-L1.json",
    *(
        f"bench/out/gemma-4-e2b-real-weight-parity-L{depth}.json"
        for depth in DIAGNOSTIC_DEPTHS
    ),
    "bench/out/gemma-4-31b-real-weight-parity-L1.json",
    # Doppler production-artifact structural probe and Q4_K_M smoke parity.
    "bench/out/doppler-rdrr/gemma-4-e2b-int4ple-rdrr-probe.json",
    "bench/out/doppler-rdrr/gemma-4-e2b-int4ple-q4k-extraction.json",
    "bench/out/weights-audit/gemma-4-e2b-rdrr-int4ple-weights-audit.json",
    "bench/out/doppler-rdrr/gemma-4-e2b-int4ple-rdrr-l1-parity.json",
    "bench/out/doppler-rdrr/gemma-4-e2b-int4ple-q4k-parity.json",
    *(
        "bench/out/doppler-rdrr/"
        f"gemma-4-e2b-int4ple-rdrr-l{depth}-parity.json"
        for depth in DIAGNOSTIC_DEPTHS
    ),
    *(
        "bench/out/doppler-rdrr/"
        f"gemma-4-e2b-int4ple-q4k-parity-L{depth}.json"
        for depth in DIAGNOSTIC_DEPTHS
    ),
    # 26B/A4B MoE lane scope (explicitly blocked, 6 TODO receipts).
    "bench/out/26b-moe-lane/lane-status.json",
    "bench/out/26b-moe-lane/router-todo.json",
    "bench/out/26b-moe-lane/topk-selection-todo.json",
    "bench/out/26b-moe-lane/token-dispatch-todo.json",
    "bench/out/26b-moe-lane/shared-expert-todo.json",
    "bench/out/26b-moe-lane/output-combine-todo.json",
    "bench/out/26b-moe-lane/per-expert-batching-todo.json",
    # Rollups that summarize the lane matrix and gate runs.
    "bench/out/doe-run/all-lanes-summary-L1.json",
    "bench/out/doe-run/depth-coverage-matrix.json",
    "bench/out/doe-run/webgpu-wgsl/L1-receipt.json",
    "bench/out/doe-run/csl-webgpu-emulator/L1-receipt.json",
    "bench/out/doe-run/csl-sdklayout/L1-receipt.json",
    "bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/execution_graph.json",
    "bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/prompt.txt",
    "bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/tokenized_prompt.u32",
    "bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/generated_tokens.u32",
    "bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/decode_transcript.json",
    "bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/doppler_int4ple_reference_export.json",
    # 31B-led evidence (Step 1 of the Cerebras bundle drive plan).
    # Sources are promoted from dated overnight-matrix cells to stable
    # paths so the packer's static allow-list stays deterministic; the
    # PROVENANCE.json files name the original source paths and hashes.
    "bench/out/r3-1-31b-doppler-reference/gemma-4-31b-program-bundle.json",
    "bench/out/r3-1-31b-doppler-reference/reference.json",
    "bench/out/r3-1-31b-doppler-reference/PROVENANCE.json",
    "bench/out/r3-1-31b-a3-partial/trace.json.progress.jsonl",
    "bench/out/r3-1-31b-a3-partial/PROVENANCE.json",
    "bench/out/r3-1-31b-l1-dry/trace.json",
    "bench/out/r3-1-31b-l61-smoke/trace.json",
    "bench/out/cerebras-evidence-bundle/summary.json",
)

# Deny-list substrings. Belt-and-suspenders over the allow-list: if
# someone adds a new allow-list entry by mistake, these tokens in the
# relative path block it from the archive.
EXCLUDE_SUBSTRINGS: tuple[str, ...] = (
    ".elf",
    ".lst",
    ".map",
    ".symbols",
    ".viz",
    ".f32",
    "/scratch/",
    "/compile/",
    "/compile-L",
    "simulator.log",
    ".stderr",
    ".stdout",
)

# Claim-role taxonomy per bundled file. Values enforced in MANIFEST
# so reviewers can see at a glance what each artifact is evidence
# FOR, not just where it came from.
CLAIM_ROLE: dict[str, str] = {
    "README.md": "governance",
    "CLAIM_SCOPE.md": "governance",
    "MODEL_ACCESS.md": "governance",
    "CEREBRAS_ASK.md": "governance",
    "LOCAL_INSPECTION.md": "governance",
    "docs/hardware-validation-appendix.md": "governance",
    "docs/claim-discipline.md": "governance",
    "config/gemma-4-e2b-real-weight-fixture.json": "real-weight-fixture",
    "config/gemma-4-31b-real-weight-fixture.json": "real-weight-fixture",
    "config/gemma-4-e2b-doppler-rdrr-int4ple-fixture.json": "doppler-rdrr-fixture",
    "bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json": "model-runtime-receipt",
    "bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.md": "model-runtime-receipt",
    "bench/out/31b-full-graph/gemma-4-31b-runtime-receipt.json": "model-runtime-receipt",
    "bench/out/31b-full-graph/gemma-4-31b-runtime-receipt.md": "model-runtime-receipt",
    "bench/out/streaming-executor/e2b-layer-block-cross-runtime-parity-check.json": "cross-runtime-parity-verdict",
    "bench/out/streaming-executor/gemma-4-31b-layer-block-cross-runtime-parity-check.json": "cross-runtime-parity-verdict",
    "bench/out/doppler-reference/csl-emulator-speed-verdict-L1.json": "emulator-speed-verdict",
    "bench/out/manifest-shape/gemma-4-e2b-manifest-shape-probe.json": "manifest-shape-probe",
    "bench/out/manifest-shape/gemma-4-e2b-manifest-shape-execution.json": "manifest-shape-execution-oracle",
    "bench/out/manifest-shape/gemma-4-e2b-manifest-shape-attention-core.json": "manifest-shape-attention-core",
    "bench/out/manifest-shape/gemma-4-e2b-manifest-shape-runtime-path.json": "manifest-shape-runtime-path",
    "bench/out/doppler-capture/gemma-4-e2b-doe-webgpu-capture-graph.json": "doppler-webgpu-capture-graph",
    "bench/out/doppler-capture/gemma-4-e2b-capture-to-csl-attention-core-lowering.json": "doppler-webgpu-capture-lowering",
    "bench/out/gemma-4-e2b-real-weight-parity-L1.json": "real-weight-parity-verdict",
    **{
        (
            f"bench/out/gemma-4-e2b-real-weight-parity-L{depth}.json"
        ): "real-weight-parity-verdict"
        for depth in DIAGNOSTIC_DEPTHS
    },
    "bench/out/gemma-4-31b-real-weight-parity-L1.json": "real-weight-parity-verdict",
    "bench/out/doppler-rdrr/gemma-4-e2b-int4ple-rdrr-probe.json": "doppler-rdrr-probe",
    "bench/out/doppler-rdrr/gemma-4-e2b-int4ple-q4k-extraction.json": "doppler-rdrr-q4k-extraction",
    "bench/out/weights-audit/gemma-4-e2b-rdrr-int4ple-weights-audit.json": "doppler-rdrr-q4k-audit",
    "bench/out/doppler-rdrr/gemma-4-e2b-int4ple-rdrr-l1-parity.json": "doppler-rdrr-q4k-parity",
    "bench/out/doppler-rdrr/gemma-4-e2b-int4ple-q4k-parity.json": "doppler-rdrr-q4k-parity",
    **{
        (
            "bench/out/doppler-rdrr/"
            f"gemma-4-e2b-int4ple-rdrr-l{depth}-parity.json"
        ): "doppler-rdrr-q4k-parity"
        for depth in DIAGNOSTIC_DEPTHS
    },
    **{
        (
            "bench/out/doppler-rdrr/"
            f"gemma-4-e2b-int4ple-q4k-parity-L{depth}.json"
        ): "doppler-rdrr-q4k-parity"
        for depth in DIAGNOSTIC_DEPTHS
    },
    "bench/out/26b-moe-lane/lane-status.json": "moe-lane-scope",
    "bench/out/26b-moe-lane/router-todo.json": "moe-lane-scope",
    "bench/out/26b-moe-lane/topk-selection-todo.json": "moe-lane-scope",
    "bench/out/26b-moe-lane/token-dispatch-todo.json": "moe-lane-scope",
    "bench/out/26b-moe-lane/shared-expert-todo.json": "moe-lane-scope",
    "bench/out/26b-moe-lane/output-combine-todo.json": "moe-lane-scope",
    "bench/out/26b-moe-lane/per-expert-batching-todo.json": "moe-lane-scope",
    "bench/out/doe-run/all-lanes-summary-L1.json": "rollup",
    "bench/out/doe-run/depth-coverage-matrix.json": "depth-coverage-rollup",
    "bench/out/doe-run/webgpu-wgsl/L1-receipt.json": "target-run-receipt",
    "bench/out/doe-run/csl-webgpu-emulator/L1-receipt.json": "target-run-receipt",
    "bench/out/doe-run/csl-sdklayout/L1-receipt.json": "target-run-receipt",
    "bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/execution_graph.json": "doppler-int4ple-execution-graph",
    "bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/prompt.txt": "doppler-int4ple-reference-input",
    "bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/tokenized_prompt.u32": "doppler-int4ple-reference-input",
    "bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/generated_tokens.u32": "doppler-int4ple-reference-output-tokens",
    "bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/decode_transcript.json": "doppler-int4ple-reference-transcript",
    "bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/doppler_int4ple_reference_export.json": "doppler-int4ple-reference-export",
    "bench/out/r3-1-31b-doppler-reference/gemma-4-31b-program-bundle.json": "doppler-31b-program-bundle",
    "bench/out/r3-1-31b-doppler-reference/reference.json": "doppler-31b-webgpu-prefill-decode-reference",
    "bench/out/r3-1-31b-doppler-reference/PROVENANCE.json": "promoted-artifact-provenance",
    "bench/out/r3-1-31b-a3-partial/trace.json.progress.jsonl": "doe-csl-31b-a3-partial-typed-blocked",
    "bench/out/r3-1-31b-a3-partial/PROVENANCE.json": "promoted-artifact-provenance",
    "bench/out/r3-1-31b-l1-dry/trace.json": "simfabric-31b-l1-smoke-receipt",
    "bench/out/r3-1-31b-l61-smoke/trace.json": "simfabric-31b-l61-smoke-receipt",
    "bench/out/cerebras-evidence-bundle/summary.json": "rollup",
}


def git_output(args: list[str]) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO_ROOT)] + args,
            capture_output=True, text=True, check=False, timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def git_commit() -> str:
    return git_output(["rev-parse", "HEAD"]) or "unknown"


def git_dirty_tree() -> bool:
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
            capture_output=True, text=True, check=False, timeout=60,
        )
        if r.returncode != 0:
            return True
        return bool(r.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        # A timed-out or unreadable status must not produce a clean-
        # looking archive. Dirty is the conservative external signal.
        return True


def git_short_sha(commit: str) -> str:
    return commit[:12] if commit and commit != "unknown" else "nogit"


def detect_cs_python_availability() -> dict:
    # Availability is useful signal (bundling host CAN run live CSL);
    # the literal path leaks the bundler's home dir so redact it always.
    sdk_root = os.environ.get("DOE_CSL_SDK_ROOT", "/home/x/cerebras-sdk")
    cs_python = os.environ.get("DOE_CSL_CS_PYTHON", f"{sdk_root}/cs_python")
    available = Path(cs_python).is_file()
    return {
        "csPythonAvailableOnBundler": available,
        "csPythonPath": "redacted",
        "sdkRootPath": "redacted",
    }


def detect_host_os() -> dict:
    # Release/version can leak host identity on multi-tenant boxes.
    # Keep high-level only.
    return {
        "system": platform.system(),
        "python": platform.python_version(),
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--out",
        default="",
        help=(
            "Archive output path. When unset, uses "
            "bench/out/doe-cerebras-evidence-YYYYMMDD-HHMM-<shortSha>[-dirty].tar.gz"
        ),
    )
    return p.parse_args()


def default_out_path(commit: str, dirty: bool) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M", time.localtime())
    short = git_short_sha(commit)
    dirty_tag = "-dirty" if dirty else ""
    return REPO_ROOT / "bench/out" / f"doe-cerebras-evidence-{stamp}-{short}{dirty_tag}.tar.gz"


def resolve(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def should_exclude(relpath: str) -> str | None:
    for token in EXCLUDE_SUBSTRINGS:
        if token in relpath:
            return token
    return None


def split_section_source(raw: str) -> tuple[str, str | None]:
    if "#" not in raw:
        return raw, None
    path, section = raw.split("#", 1)
    return path, section


def read_include_bytes(source_rel: str) -> bytes:
    source_path, section = split_section_source(source_rel)
    src = REPO_ROOT / source_path
    if section is None:
        return src.read_bytes()

    text = src.read_text(encoding="utf-8")
    start = f"<!-- archive:{section}:start -->"
    end = f"<!-- archive:{section}:end -->"
    start_idx = text.find(start)
    end_idx = text.find(end)
    if start_idx < 0 or end_idx < 0 or end_idx <= start_idx:
        raise ValueError(
            f"missing or invalid section markers for {section} in "
            f"{source_path}"
        )
    body = text[start_idx + len(start):end_idx].strip() + "\n"
    return body.encode("utf-8")


def main() -> int:
    args = parse_args()

    commit = git_commit()
    dirty = git_dirty_tree()

    if args.out:
        out_path = resolve(args.out)
    else:
        out_path = default_out_path(commit, dirty)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    utc_built = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    host_os = detect_host_os()
    cs_py = detect_cs_python_availability()
    bundle_meta = {
        "schemaVersion": 1,
        "artifactKind": "doe_cerebras_evidence_bundle_meta",
        "builtUtc": utc_built,
        "archiveFilename": out_path.name,
        "gitCommit": commit,
        "gitShortSha": git_short_sha(commit),
        "gitDirtyTree": dirty,
        "hostOs": host_os,
        "csPython": cs_py,
        "claimScopeSource": "docs/claim-discipline.md",
        "hardwareValidationAppendix": "docs/hardware-validation-appendix.md",
        "scope": (
            "Evidence + hashes + commands. NO SDK binaries, weight bytes, "
            "simulator logs, or raw trace data. See docs/claim-discipline.md "
            "for the allowed/rejected claim boundary this bundle evidences."
        ),
    }

    manifest_lines = [
        "Cerebras hardware-validation archive",
        f"Built: {utc_built}  commit: {git_short_sha(commit)}"
        + ("  (dirty tree)" if dirty else ""),
        "",
        "Scope: evidence + hashes + commands only. No SDK binaries, no weight",
        "bytes, no simulator logs. See docs/claim-discipline.md for the",
        "allowed/rejected claim boundary this archive evidences.",
        "",
        "Every file carries a claim-role indicating what it is evidence FOR.",
        "",
        f"{'SHA256':<64}  {'CLAIM-ROLE':<28}  PATH",
    ]

    included: list[tuple[str, bytes]] = []
    missing: list[str] = []
    excluded: list[tuple[str, str]] = []

    for entry in INCLUDE_FILES:
        if isinstance(entry, tuple):
            source_rel, archive_rel = entry
        else:
            source_rel = archive_rel = entry
        source_path, _section = split_section_source(source_rel)
        reason = should_exclude(source_path) or should_exclude(archive_rel)
        if reason:
            excluded.append((archive_rel, f"deny-list token: {reason}"))
            continue
        src = REPO_ROOT / source_path
        if not src.is_file():
            missing.append(source_rel)
            continue
        try:
            data = read_include_bytes(source_rel)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            missing.append(f"{source_rel} ({exc})")
            continue
        included.append((archive_rel, data))
        sha = sha256_bytes(data)
        role = CLAIM_ROLE.get(archive_rel, "UNLABELED")
        manifest_lines.append(f"{sha}  {role:<28}  {archive_rel}")

    if missing:
        manifest_lines.append("")
        manifest_lines.append("Missing at archive time (not fatal, recorded for transparency):")
        for m in missing:
            manifest_lines.append(f"  {m}")
    if excluded:
        manifest_lines.append("")
        manifest_lines.append("Explicitly excluded:")
        for path, reason in excluded:
            manifest_lines.append(f"  {path} ({reason})")

    manifest_text = "\n".join(manifest_lines) + "\n"
    bundle_meta_bytes = (
        json.dumps(bundle_meta, indent=2) + "\n"
    ).encode("utf-8")

    # Write the tarball. Every entry is normalized to mode 0o644, uid/gid 0,
    # mtime = now, owner "cerebras-ask" so the archive is reproducibly
    # structured and doesn't leak local uid info.
    now = int(time.time())
    owner = "cerebras-ask"

    def add_bytes(tf: tarfile.TarFile, name: str, data: bytes) -> None:
        ti = tarfile.TarInfo(name)
        ti.size = len(data)
        ti.mode = 0o644
        ti.mtime = now
        ti.uname = owner
        ti.gname = owner
        tf.addfile(ti, io.BytesIO(data))

    with tarfile.open(out_path, "w:gz") as tf:
        # Bundle metadata first — reviewers open this to know what the
        # bundle IS before deciding whether to read the manifest.
        add_bytes(tf, "BUNDLE_META.json", bundle_meta_bytes)
        # Manifest second — hash + claim-role + path for every file.
        add_bytes(tf, "MANIFEST.txt", manifest_text.encode("utf-8"))
        for relpath, data in included:
            add_bytes(tf, relpath, data)

    out_size = out_path.stat().st_size
    print(f"wrote {rel(out_path)}  ({out_size} bytes, {len(included)} files)")
    if missing:
        print(f"  missing: {len(missing)} file(s)")
        for m in missing:
            print(f"    {m}")
    if excluded:
        print(f"  excluded by deny-list: {len(excluded)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

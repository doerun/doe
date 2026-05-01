"""Durable HostPlan checkpoint persistence and resume validation.

Backs row R2-5a in `docs/cerebras-north-star.md`. The HostPlan launch loop
in `int4ple_compile_target_sim_runner.execute_hostplan_runtime` already
persists per-launch D2H output buffers to disk and threads them through
`buffer_files[symbol] -> Path`. Resume reduces to reconstructing that
dict from a content-addressed manifest with strict identity validation,
not re-executing the prefix.

Identity validation is intentionally strict and raises typed errors so
the runner can fail fast rather than silently drift.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any


CHECKPOINT_SCHEMA_VERSION = 1
MANIFEST_FILENAME = "manifest.json"
LAUNCHES_DIRNAME = "launches"
BUFFERS_DIRNAME = "buffers"


class CheckpointError(Exception):
    """Base class for resume-time validation failures."""

    code: str = "checkpoint_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class CheckpointSchemaDriftError(CheckpointError):
    code = "checkpoint_schema_drift"


class CheckpointIdentityDriftError(CheckpointError):
    """Raised when manifest identity does not match the current run's identity."""


class CheckpointBufferCorruptionError(CheckpointError):
    """Raised when a persisted buffer's bytes do not match the recorded sha256."""


class CheckpointMissingError(CheckpointError):
    code = "checkpoint_missing"


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _atomic_write_text(path: Path, text: str) -> None:
    """Write `text` to `path` atomically via temp-file + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


def _copy_checkpoint_buffer(src: Path, dst: Path) -> None:
    """Copy runtime output bytes into checkpoint-owned storage."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    shutil.copyfile(src, dst)


def compute_identity(
    *,
    plan: dict[str, Any],
    plan_path: Path,
    runtime_config: dict[str, Any],
    runtime_config_path: Path,
    export: dict[str, Any],
    reference_export_path: Path,
    runner_version: str,
) -> dict[str, Any]:
    """Build the identity record persisted into and validated against the manifest.

    Strict equality on the returned dict is the resume gate. Field choices:

    - bundleSha256 / manifestSha256 / executionGraphSha256: pinned by `export`
      and uniquely identify the upstream Doppler reference.
    - hostplanSha256 / runtimeConfigSha256: digest the local plan and runtime
      config artifacts so swapping in a different plan is rejected.
    - compileTargetHashes: per-target compile fingerprint pulled from the plan
      so a recompile with new params invalidates the checkpoint.
    - modelId: cheap human-readable cross-check.
    - runnerVersion: detects logic drift in the runner itself.
    """
    plan_bytes = plan_path.read_bytes()
    runtime_bytes = runtime_config_path.read_bytes()
    compile_targets = (plan.get("inputs") or {}).get("compileTargets") or []
    compile_target_hashes: dict[str, str] = {}
    for target in compile_targets:
        if not isinstance(target, dict):
            continue
        name = target.get("name")
        if not isinstance(name, str):
            continue
        compile_target_hashes[name] = _sha256_of_bytes(_canonical_json(target))
    return {
        "bundleSha256": str(export.get("bundleSha256") or export.get("programBundleId") or "missing"),
        "manifestSha256": str(export.get("manifestSha256") or "missing"),
        "executionGraphSha256": str(export.get("executionGraphSha256") or "missing"),
        "hostplanSha256": _sha256_of_bytes(plan_bytes),
        "runtimeConfigSha256": _sha256_of_bytes(runtime_bytes),
        "compileTargetHashes": compile_target_hashes,
        "modelId": str(export.get("modelId") or "unknown"),
        "runnerVersion": runner_version,
    }


def compute_launch_identity(
    launch_spec: dict[str, Any],
    input_buffer_hashes: dict[str, str],
) -> str:
    """sha256 over (canonical launch_spec, sorted input-buffer hashes)."""
    payload = {
        "launchSpec": launch_spec,
        "inputBufferHashes": dict(sorted(input_buffer_hashes.items())),
    }
    return _sha256_of_bytes(_canonical_json(payload))


def _launch_dir(checkpoint_dir: Path, launch_index: int, target: str) -> Path:
    safe_target = "".join(c if c.isalnum() or c in "-_" else "_" for c in (target or "unknown"))
    return checkpoint_dir / LAUNCHES_DIRNAME / f"{launch_index:04d}_{safe_target}"


def _read_manifest(checkpoint_dir: Path) -> dict[str, Any]:
    manifest_path = checkpoint_dir / MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise CheckpointMissingError(
            f"checkpoint manifest not found at {manifest_path}",
        )
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CheckpointError(
            f"checkpoint manifest at {manifest_path} is not valid JSON: {exc}",
            code="checkpoint_manifest_invalid",
        ) from exc


def _write_manifest(checkpoint_dir: Path, manifest: dict[str, Any]) -> None:
    manifest_path = checkpoint_dir / MANIFEST_FILENAME
    text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    _atomic_write_text(manifest_path, text)


def init_checkpoint(
    checkpoint_dir: Path,
    identity: dict[str, Any],
    *,
    allow_runner_version_drift: bool = False,
) -> dict[str, Any]:
    """Initialize an empty checkpoint dir with identity but no completed launches.

    Idempotent. If the dir already has a manifest with matching identity it is
    reused; if identity differs, the existing manifest is left intact and the
    caller must explicitly clear it (we never silently overwrite).
    """
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = checkpoint_dir / MANIFEST_FILENAME
    if manifest_path.is_file():
        existing = _read_manifest(checkpoint_dir)
        existing_identity = existing.get("identity") or {}
        drift_field = _identity_drift_field(existing_identity, identity)
        if drift_field is None or (
            allow_runner_version_drift and drift_field == "runnerVersion"
        ):
            return existing
        raise CheckpointIdentityDriftError(
            f"checkpoint dir {checkpoint_dir} already exists with different identity; "
            "remove it or use --ignore-checkpoint",
            code="checkpoint_identity_preexisting",
        )
    manifest = {
        "schemaVersion": CHECKPOINT_SCHEMA_VERSION,
        "identity": identity,
        "completedLaunches": [],
        "createdAtUnix": time.time(),
    }
    _write_manifest(checkpoint_dir, manifest)
    return manifest


def persist_launch_checkpoint(
    *,
    checkpoint_dir: Path,
    launch_index: int,
    launch: dict[str, Any],
    launch_receipt: dict[str, Any],
    staged_outputs: list[dict[str, Any]],
    launch_identity: str,
    started_at_unix: float,
) -> None:
    """Copy each output buffer into the checkpoint dir and append a manifest entry.

    Atomicity: buffer copies happen first; manifest rewrite happens last via
    write-temp + os.replace. A crash between buffer copy and manifest rewrite
    leaves orphaned bytes that the next persist call will overwrite.
    """
    target = str(launch.get("targetName") or "unknown")
    launch_dir = _launch_dir(checkpoint_dir, launch_index, target)
    buffers_dir = launch_dir / BUFFERS_DIRNAME
    buffers_dir.mkdir(parents=True, exist_ok=True)

    persisted_outputs: list[dict[str, Any]] = []
    for output in staged_outputs:
        symbol = str(output["buffer"])
        src = Path(str(output["path"]))
        if not src.is_file():
            raise CheckpointError(
                f"launch[{launch_index}] output buffer source missing: {src}",
                code="output_source_missing",
            )
        dst = buffers_dir / f"{symbol}.bin"
        _copy_checkpoint_buffer(src, dst)
        digest = _sha256_of_file(dst)
        byte_count = dst.stat().st_size
        persisted_outputs.append({
            "buffer": symbol,
            "dtype": output.get("dtype", "unknown"),
            "shape": output.get("shape", []),
            "byteCount": byte_count,
            "sha256": digest,
            "path": str(dst.relative_to(checkpoint_dir)),
        })

    manifest = _read_manifest(checkpoint_dir)
    completed = list(manifest.get("completedLaunches") or [])
    # Replace any existing entry at this launch_index (idempotent re-persist)
    completed = [entry for entry in completed if entry.get("launchIndex") != launch_index]
    completed.append({
        "launchIndex": launch_index,
        "target": target,
        "launchIdentity": launch_identity,
        "outputs": persisted_outputs,
        "startedAtUnix": started_at_unix,
        "completedAtUnix": time.time(),
        "elapsedMs": int((time.time() - started_at_unix) * 1000),
        "launchReceiptStatus": launch_receipt.get("status", "unknown"),
    })
    completed.sort(key=lambda e: int(e.get("launchIndex", 0)))
    manifest["completedLaunches"] = completed
    manifest["updatedAtUnix"] = time.time()
    _write_manifest(checkpoint_dir, manifest)


class ResumeState:
    """Validated resume state: start_index plus pre-populated buffer_files."""

    def __init__(
        self,
        *,
        start_index: int,
        buffer_files: dict[str, Path],
        manifest: dict[str, Any],
    ) -> None:
        self.start_index = start_index
        self.buffer_files = buffer_files
        self.manifest = manifest


def load_checkpoint(
    *,
    checkpoint_dir: Path,
    identity: dict[str, Any],
    verify_buffers: bool = True,
    allow_runner_version_drift: bool = False,
) -> ResumeState:
    """Load a manifest, validate identity strictly, verify buffers, return state.

    Raises:
      CheckpointMissingError: manifest absent.
      CheckpointSchemaDriftError: schema version mismatch.
      CheckpointIdentityDriftError: any identity field mismatched.
      CheckpointBufferCorruptionError: a persisted buffer's bytes drift from sha256.
    """
    manifest = _read_manifest(checkpoint_dir)

    schema_version = manifest.get("schemaVersion")
    if schema_version != CHECKPOINT_SCHEMA_VERSION:
        raise CheckpointSchemaDriftError(
            f"checkpoint schema version {schema_version} does not match runner "
            f"version {CHECKPOINT_SCHEMA_VERSION}",
        )

    manifest_identity = manifest.get("identity") or {}
    drift_field = _identity_drift_field(manifest_identity, identity)
    if (
        drift_field is not None
        and not (allow_runner_version_drift and drift_field == "runnerVersion")
    ):
        raise CheckpointIdentityDriftError(
            f"checkpoint identity drift on field {drift_field!r}: "
            f"manifest={manifest_identity.get(drift_field)!r} "
            f"current={identity.get(drift_field)!r}",
            code=_drift_code(drift_field),
        )

    completed = list(manifest.get("completedLaunches") or [])
    completed.sort(key=lambda e: int(e.get("launchIndex", 0)))
    buffer_files: dict[str, Path] = {}
    last_index = -1
    for entry in completed:
        idx = int(entry.get("launchIndex", -1))
        if idx != last_index + 1:
            # Gap detected; refuse to resume past a gap to avoid silent
            # data dependency holes.
            raise CheckpointError(
                f"checkpoint manifest has gap at launch index {last_index + 1} "
                f"(next recorded index is {idx})",
                code="checkpoint_gap",
            )
        for output in entry.get("outputs") or []:
            symbol = str(output["buffer"])
            rel_path = str(output["path"])
            full_path = checkpoint_dir / rel_path
            if not full_path.is_file():
                raise CheckpointBufferCorruptionError(
                    f"launch[{idx}] buffer {symbol!r} missing at {full_path}",
                    code=f"buffer_missing_launch{idx}_{symbol}",
                )
            byte_count = int(output.get("byteCount", -1))
            if full_path.stat().st_size != byte_count:
                raise CheckpointBufferCorruptionError(
                    f"launch[{idx}] buffer {symbol!r} byte count drift: "
                    f"manifest={byte_count} disk={full_path.stat().st_size}",
                    code=f"buffer_size_drift_launch{idx}_{symbol}",
                )
            if verify_buffers:
                actual = _sha256_of_file(full_path)
                if actual != output.get("sha256"):
                    raise CheckpointBufferCorruptionError(
                        f"launch[{idx}] buffer {symbol!r} sha256 drift: "
                        f"manifest={output.get('sha256')} disk={actual}",
                        code=f"buffer_sha_drift_launch{idx}_{symbol}",
                    )
            buffer_files[symbol] = full_path
        last_index = idx

    return ResumeState(
        start_index=last_index + 1,
        buffer_files=buffer_files,
        manifest=manifest,
    )


def _identity_drift_field(manifest_identity: dict[str, Any], current: dict[str, Any]) -> str | None:
    """Return the first field that differs, or None if identities match."""
    keys = sorted(set(manifest_identity.keys()) | set(current.keys()))
    for key in keys:
        if manifest_identity.get(key) != current.get(key):
            return key
    return None


def _drift_code(field: str) -> str:
    mapping = {
        "bundleSha256": "bundle_drift",
        "manifestSha256": "manifest_drift",
        "executionGraphSha256": "graph_drift",
        "hostplanSha256": "hostplan_drift",
        "runtimeConfigSha256": "runtime_config_drift",
        "modelId": "model_id_drift",
        "runnerVersion": "runner_drift",
    }
    if field == "compileTargetHashes":
        return "compile_target_drift"
    return mapping.get(field, f"identity_drift_{field}")

"""Tests for `int4ple_checkpoint` durable HostPlan resume support.

Backs row R2-5a of `docs/cerebras-north-star.md`. The five scenarios cover the
contract documented in the design sketch: persist/load happy path, identity
drift rejection (with the typed code), buffer corruption rejection (with the
typed code), and idempotent stop+resume cycles.

These exercise `int4ple_checkpoint` directly. End-to-end coverage of the
runner's `--checkpoint-dir`/`--resume-from-checkpoint` flags lives in the
runner's own integration suite once a real plan fixture is plumbed.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_DIR = REPO_ROOT / "bench" / "runners" / "csl-runners"
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))

from int4ple_checkpoint import (  # noqa: E402
    CheckpointBufferCorruptionError,
    CheckpointIdentityDriftError,
    CheckpointMissingError,
    CheckpointSchemaDriftError,
    compute_launch_identity,
    init_checkpoint,
    load_checkpoint,
    persist_launch_checkpoint,
)


def _identity(bundle: str = "bundle-A", model_id: str = "gemma-3-1b-it-q4k-ehf16-af32") -> dict:
    return {
        "bundleSha256": bundle,
        "manifestSha256": "manifest-A",
        "executionGraphSha256": "graph-A",
        "hostplanSha256": "hostplan-A",
        "runtimeConfigSha256": "runtime-A",
        "compileTargetHashes": {"embed": "target-embed-A", "rmsnorm": "target-rmsnorm-A"},
        "modelId": model_id,
        "runnerVersion": "abcdef0123456789",
    }


def _seed_buffer(tmp: Path, name: str, payload: bytes) -> dict:
    """Materialize a 'staged_outputs' entry the runner would emit."""
    src = tmp / "runtime" / f"{name}.bin"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(payload)
    return {
        "buffer": name,
        "path": str(src),
        "dtype": "f32",
        "shape": [len(payload) // 4],
    }


class PersistResumeHappyPath(unittest.TestCase):
    """Persist + immediate resume: start_index advances and buffers rehydrate."""

    def test_persist_one_launch_then_resume_advances_start_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ckpt = tmp / "ckpt"
            init_checkpoint(ckpt, _identity())

            staged = [_seed_buffer(tmp, "activations", b"\x01\x02\x03\x04")]
            launch = {"launchIndex": 0, "targetName": "embed"}
            persist_launch_checkpoint(
                checkpoint_dir=ckpt,
                launch_index=0,
                launch=launch,
                launch_receipt={"status": "succeeded"},
                staged_outputs=staged,
                launch_identity=compute_launch_identity(launch, {}),
                started_at_unix=1.0,
            )

            state = load_checkpoint(checkpoint_dir=ckpt, identity=_identity())
            self.assertEqual(state.start_index, 1)
            self.assertIn("activations", state.buffer_files)
            self.assertEqual(state.buffer_files["activations"].read_bytes(), b"\x01\x02\x03\x04")

    def test_persist_multiple_launches_resume_loads_all_buffers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ckpt = tmp / "ckpt"
            init_checkpoint(ckpt, _identity())

            for idx, (name, payload) in enumerate([
                ("embed_out", b"\xaa" * 16),
                ("rmsnorm_out", b"\xbb" * 16),
            ]):
                staged = [_seed_buffer(tmp, name, payload)]
                launch = {"launchIndex": idx, "targetName": name.split("_")[0]}
                persist_launch_checkpoint(
                    checkpoint_dir=ckpt,
                    launch_index=idx,
                    launch=launch,
                    launch_receipt={"status": "succeeded"},
                    staged_outputs=staged,
                    launch_identity=compute_launch_identity(launch, {}),
                    started_at_unix=1.0,
                )

            state = load_checkpoint(checkpoint_dir=ckpt, identity=_identity())
            self.assertEqual(state.start_index, 2)
            self.assertEqual(state.buffer_files["embed_out"].read_bytes(), b"\xaa" * 16)
            self.assertEqual(state.buffer_files["rmsnorm_out"].read_bytes(), b"\xbb" * 16)


class IdentityDriftRejection(unittest.TestCase):
    """Resume must reject with a typed code when any identity field drifts."""

    def test_bundle_drift_raises_with_typed_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ckpt = tmp / "ckpt"
            init_checkpoint(ckpt, _identity(bundle="bundle-A"))
            staged = [_seed_buffer(tmp, "activations", b"\x01" * 8)]
            persist_launch_checkpoint(
                checkpoint_dir=ckpt,
                launch_index=0,
                launch={"launchIndex": 0, "targetName": "embed"},
                launch_receipt={"status": "succeeded"},
                staged_outputs=staged,
                launch_identity="li",
                started_at_unix=1.0,
            )

            with self.assertRaises(CheckpointIdentityDriftError) as ctx:
                load_checkpoint(checkpoint_dir=ckpt, identity=_identity(bundle="bundle-B"))
            self.assertEqual(ctx.exception.code, "bundle_drift")

    def test_runner_drift_raises_with_typed_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ckpt = tmp / "ckpt"
            init_checkpoint(ckpt, _identity())
            staged = [_seed_buffer(tmp, "activations", b"\x02" * 8)]
            persist_launch_checkpoint(
                checkpoint_dir=ckpt,
                launch_index=0,
                launch={"launchIndex": 0, "targetName": "embed"},
                launch_receipt={"status": "succeeded"},
                staged_outputs=staged,
                launch_identity="li",
                started_at_unix=1.0,
            )

            current = _identity()
            current["runnerVersion"] = "deadbeefcafef00d"
            with self.assertRaises(CheckpointIdentityDriftError) as ctx:
                load_checkpoint(checkpoint_dir=ckpt, identity=current)
            self.assertEqual(ctx.exception.code, "runner_drift")

    def test_schema_drift_raises_typed_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ckpt = tmp / "ckpt"
            init_checkpoint(ckpt, _identity())
            # Hand-edit the manifest schemaVersion to simulate a future-incompatible runner.
            manifest_path = ckpt / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["schemaVersion"] = 999
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaises(CheckpointSchemaDriftError) as ctx:
                load_checkpoint(checkpoint_dir=ckpt, identity=_identity())
            self.assertEqual(ctx.exception.code, "checkpoint_schema_drift")


class BufferCorruptionRejection(unittest.TestCase):
    """A persisted buffer that no longer matches its recorded sha256 must reject."""

    def test_corrupted_buffer_bytes_raise_typed_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ckpt = tmp / "ckpt"
            init_checkpoint(ckpt, _identity())

            staged = [_seed_buffer(tmp, "activations", b"\xcc" * 32)]
            persist_launch_checkpoint(
                checkpoint_dir=ckpt,
                launch_index=0,
                launch={"launchIndex": 0, "targetName": "embed"},
                launch_receipt={"status": "succeeded"},
                staged_outputs=staged,
                launch_identity="li",
                started_at_unix=1.0,
            )
            # Corrupt the persisted buffer bytes.
            persisted = ckpt / "launches" / "0000_embed" / "buffers" / "activations.bin"
            self.assertTrue(persisted.is_file())
            persisted.write_bytes(b"\x00" * 32)

            with self.assertRaises(CheckpointBufferCorruptionError) as ctx:
                load_checkpoint(checkpoint_dir=ckpt, identity=_identity())
            self.assertIn("sha_drift", ctx.exception.code)


class StopResumeIdempotence(unittest.TestCase):
    """Resume after a stop must yield byte-identical outputs to a single uninterrupted run."""

    def test_persist_partial_resume_complete_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ckpt = tmp / "ckpt"
            init_checkpoint(ckpt, _identity())

            # First "run": persist launch 0 then stop.
            staged0 = [_seed_buffer(tmp, "embed_out", b"\xde\xad\xbe\xef" * 4)]
            persist_launch_checkpoint(
                checkpoint_dir=ckpt,
                launch_index=0,
                launch={"launchIndex": 0, "targetName": "embed"},
                launch_receipt={"status": "succeeded"},
                staged_outputs=staged0,
                launch_identity="li-0",
                started_at_unix=1.0,
            )
            state_after_stop = load_checkpoint(checkpoint_dir=ckpt, identity=_identity())
            self.assertEqual(state_after_stop.start_index, 1)
            stopped_bytes = state_after_stop.buffer_files["embed_out"].read_bytes()

            # Second "run" simulating resume: persist launch 1 on the same checkpoint dir.
            staged1 = [_seed_buffer(tmp, "rmsnorm_out", b"\xfe\xed\xfa\xce" * 4)]
            persist_launch_checkpoint(
                checkpoint_dir=ckpt,
                launch_index=1,
                launch={"launchIndex": 1, "targetName": "rmsnorm"},
                launch_receipt={"status": "succeeded"},
                staged_outputs=staged1,
                launch_identity="li-1",
                started_at_unix=2.0,
            )
            state_after_resume = load_checkpoint(checkpoint_dir=ckpt, identity=_identity())
            self.assertEqual(state_after_resume.start_index, 2)

            # Stopped buffer is unchanged after the second run; new buffer is present.
            self.assertEqual(
                state_after_resume.buffer_files["embed_out"].read_bytes(),
                stopped_bytes,
            )
            self.assertEqual(
                state_after_resume.buffer_files["rmsnorm_out"].read_bytes(),
                b"\xfe\xed\xfa\xce" * 4,
            )

    def test_missing_checkpoint_raises_typed_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ckpt = Path(tmpdir) / "ckpt-does-not-exist"
            with self.assertRaises(CheckpointMissingError):
                load_checkpoint(checkpoint_dir=ckpt, identity=_identity())


if __name__ == "__main__":
    unittest.main()

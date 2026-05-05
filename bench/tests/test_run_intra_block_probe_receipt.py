from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools.run_intra_block_probe_receipt import (  # noqa: E402
    PROBE_POINTS,
    build_receipt,
    load_probe_map,
    resolve_probe_npy,
)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _sample_probe_map() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_intra_block_probe_map",
        "probePoints": {
            "post_rmsnorm": {
                "kernel": "ple_rmsnorm",
                "outputSymbol": "output",
            },
            "post_qkv": {
                "kernel": "ple_proj",
                "outputSymbol": "output",
            },
            "post_attn": {
                "kernel": "attn_decode",
                "outputSymbol": "output",
            },
            "post_ffn": {
                "kernel": "gelu",
                "outputSymbol": "output",
            },
        },
    }


def _seed_dispatch_npy(
    *, dispatch_out_dir: Path, kernel: str, symbol: str, payload: bytes
) -> Path:
    path = (
        dispatch_out_dir / "scratch" / kernel / "out" / f"{symbol}.npy"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _build_fixture(
    *,
    root: Path,
    layer_index: int,
    activations_sha: dict[str, str],
    fixture_digest: str = "f" * 64,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schemaVersion": 1,
        "artifactKind": "doe_frozen_doppler_reference_manifest",
        "modelId": "synthetic",
        "fixtureDigest": fixture_digest,
        "transcript": {"path": "transcript.json", "sha256": "0" * 64},
        "activations": {
            str(layer_index): {
                probe: {"path": f"act/{probe}.npy", "sha256": sha}
                for probe, sha in activations_sha.items()
            }
        },
    }
    manifest_path = root / "frozen-reference.manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


class LoadProbeMapTest(unittest.TestCase):
    def test_loads_repo_default(self) -> None:
        repo_default = (
            REPO_ROOT / "config/manifest-shape-intra-block-probe-map.json"
        )
        loaded = load_probe_map(repo_default)
        self.assertEqual(loaded["schemaVersion"], 1)
        self.assertEqual(set(loaded["probePoints"]), set(PROBE_POINTS))


class BuildReceiptTest(unittest.TestCase):
    def test_no_oracle_when_no_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            probe_map_path = tmp_path / "probe-map.json"
            probe_map_path.write_text(
                json.dumps(_sample_probe_map(), sort_keys=True),
                encoding="utf-8",
            )
            dispatch_dir = tmp_path / "dispatch"
            for probe, body in _sample_probe_map()["probePoints"].items():  # type: ignore[union-attr]
                _seed_dispatch_npy(
                    dispatch_out_dir=dispatch_dir,
                    kernel=body["kernel"],
                    symbol=body["outputSymbol"],
                    payload=probe.encode("ascii"),
                )
            receipt = build_receipt(
                probe_map=_sample_probe_map(),
                probe_map_path=probe_map_path,
                probe_map_hash=_sha256_file(probe_map_path),
                dispatch_out_dir=dispatch_dir,
                layer_index=0,
                frozen_fixture_root=None,
            )
        self.assertEqual(receipt["comparisonMode"], "no_oracle")
        self.assertEqual(receipt["verdict"], "blocked")
        self.assertEqual(receipt["blocker"], "fixture_absent")
        self.assertEqual(len(receipt["probes"]), 4)
        self.assertEqual(
            sorted(p["probePoint"] for p in receipt["probes"]),
            sorted(PROBE_POINTS),
        )
        for probe in receipt["probes"]:
            self.assertEqual(len(probe["tensorSha256"]), 64)
            self.assertGreater(probe["tensorBytes"], 0)
            self.assertIsNone(probe["fixtureSha256"])

    def test_blocked_on_missing_npy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            probe_map_path = tmp_path / "probe-map.json"
            probe_map_path.write_text(
                json.dumps(_sample_probe_map(), sort_keys=True),
                encoding="utf-8",
            )
            dispatch_dir = tmp_path / "dispatch"
            dispatch_dir.mkdir()
            receipt = build_receipt(
                probe_map=_sample_probe_map(),
                probe_map_path=probe_map_path,
                probe_map_hash=_sha256_file(probe_map_path),
                dispatch_out_dir=dispatch_dir,
                layer_index=0,
                frozen_fixture_root=None,
            )
        self.assertEqual(receipt["verdict"], "blocked")
        for probe in receipt["probes"]:
            self.assertEqual(probe["tensorBytes"], 0)
            self.assertEqual(probe["tensorSha256"], "")
            self.assertEqual(probe["blocker"], "probe_npy_absent")

    def test_parity_mode_bound_when_all_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            probe_map_path = tmp_path / "probe-map.json"
            probe_map_path.write_text(
                json.dumps(_sample_probe_map(), sort_keys=True),
                encoding="utf-8",
            )
            dispatch_dir = tmp_path / "dispatch"
            payloads: dict[str, bytes] = {}
            for probe, body in _sample_probe_map()["probePoints"].items():  # type: ignore[union-attr]
                payload = probe.encode("ascii")
                _seed_dispatch_npy(
                    dispatch_out_dir=dispatch_dir,
                    kernel=body["kernel"],
                    symbol=body["outputSymbol"],
                    payload=payload,
                )
                payloads[probe] = payload
            shas = {
                probe: hashlib.sha256(payload).hexdigest()
                for probe, payload in payloads.items()
            }
            fixture_root = tmp_path / "fixture"
            _build_fixture(
                root=fixture_root,
                layer_index=0,
                activations_sha=shas,
            )
            receipt = build_receipt(
                probe_map=_sample_probe_map(),
                probe_map_path=probe_map_path,
                probe_map_hash=_sha256_file(probe_map_path),
                dispatch_out_dir=dispatch_dir,
                layer_index=0,
                frozen_fixture_root=fixture_root,
            )
        self.assertEqual(receipt["comparisonMode"], "parity")
        self.assertEqual(receipt["verdict"], "bound")
        self.assertIsNone(receipt["blocker"])
        for probe in receipt["probes"]:
            self.assertTrue(probe["match"])
            self.assertEqual(
                probe["tensorSha256"], probe["fixtureSha256"]
            )
        # receipt-hash spine guard: parity mode requires referenceFixtureHash.
        self.assertEqual(len(receipt["referenceFixtureHash"] or ""), 64)

    def test_parity_mode_blocked_on_one_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            probe_map_path = tmp_path / "probe-map.json"
            probe_map_path.write_text(
                json.dumps(_sample_probe_map(), sort_keys=True),
                encoding="utf-8",
            )
            dispatch_dir = tmp_path / "dispatch"
            payloads: dict[str, bytes] = {}
            for probe, body in _sample_probe_map()["probePoints"].items():  # type: ignore[union-attr]
                payload = probe.encode("ascii")
                _seed_dispatch_npy(
                    dispatch_out_dir=dispatch_dir,
                    kernel=body["kernel"],
                    symbol=body["outputSymbol"],
                    payload=payload,
                )
                payloads[probe] = payload
            shas = {
                probe: hashlib.sha256(payload).hexdigest()
                for probe, payload in payloads.items()
            }
            shas["post_attn"] = "0" * 64  # induced drift
            fixture_root = tmp_path / "fixture"
            _build_fixture(
                root=fixture_root,
                layer_index=0,
                activations_sha=shas,
            )
            receipt = build_receipt(
                probe_map=_sample_probe_map(),
                probe_map_path=probe_map_path,
                probe_map_hash=_sha256_file(probe_map_path),
                dispatch_out_dir=dispatch_dir,
                layer_index=0,
                frozen_fixture_root=fixture_root,
            )
        self.assertEqual(receipt["comparisonMode"], "parity")
        self.assertEqual(receipt["verdict"], "blocked")
        self.assertTrue(
            any(
                probe["probePoint"] == "post_attn" and not probe["match"]
                for probe in receipt["probes"]
            )
        )

    def test_fixture_root_with_unreadable_manifest_falls_back(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            probe_map_path = tmp_path / "probe-map.json"
            probe_map_path.write_text(
                json.dumps(_sample_probe_map(), sort_keys=True),
                encoding="utf-8",
            )
            dispatch_dir = tmp_path / "dispatch"
            for probe, body in _sample_probe_map()["probePoints"].items():  # type: ignore[union-attr]
                _seed_dispatch_npy(
                    dispatch_out_dir=dispatch_dir,
                    kernel=body["kernel"],
                    symbol=body["outputSymbol"],
                    payload=probe.encode("ascii"),
                )
            empty_fixture = tmp_path / "missing-fixture"
            empty_fixture.mkdir()
            receipt = build_receipt(
                probe_map=_sample_probe_map(),
                probe_map_path=probe_map_path,
                probe_map_hash=_sha256_file(probe_map_path),
                dispatch_out_dir=dispatch_dir,
                layer_index=0,
                frozen_fixture_root=empty_fixture,
            )
        self.assertEqual(receipt["comparisonMode"], "no_oracle")
        self.assertIn(
            "fixture_manifest_unreadable", receipt["blockers"]
        )


class ResolveProbeNpyTest(unittest.TestCase):
    def test_path_format(self) -> None:
        path = resolve_probe_npy(
            dispatch_out_dir=Path("/tmp/dispatch"),
            kernel="embed",
            output_symbol="output",
        )
        self.assertEqual(
            str(path), "/tmp/dispatch/scratch/embed/out/output.npy"
        )


if __name__ == "__main__":
    unittest.main()

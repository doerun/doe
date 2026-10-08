"""CPU evidence rejects incorrect ELF mapping, fallback and false promotion."""

from __future__ import annotations

from collections.abc import Callable
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
OWNER = REPO / "bench/external-projects/onnx-vulkan-cpu"
REPORT = REPO / "reports/benchmarks/amd-vulkan/20261008-onnx-vulkan-cpu-attribution"


def load_module(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "onnx_cpu_" + name, OWNER / (name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROBE = load_module("probe")
with patch.dict("sys.modules", {"probe": PROBE}):
    ANALYZE = load_module("analyze")
    DECISION = load_module("decision")
with patch.dict("sys.modules", {"decision": DECISION}):
    VERIFY = load_module("verify")


class TestCpuAttribution(unittest.TestCase):
    def test_completed_no_patch_decision_replays(self) -> None:
        self.assertEqual(VERIFY.verify(REPORT, REPO)["candidate"], "none")

    def test_elf_virtual_address_differs_from_file_offset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / "fixture.so"
            header = bytearray(64)
            header[:6] = b"\x7fELF\x02\x01"
            struct.pack_into("<Q", header, 32, 64)
            struct.pack_into("<HH", header, 54, 56, 1)
            segment = struct.pack(
                "<IIQQQQQQ", 1, 5, 0xDEE8, 0xEEE8, 0, 0x2000, 0x2000, 4096
            )
            binary.write_bytes(header + segment)
            self.assertEqual(
                ANALYZE.resolve_mapping(0x100000, 0xD000, binary, 4096), 0xF2000
            )
            self.assertNotEqual(
                ANALYZE.resolve_mapping(0x100000, 0xD000, binary, 4096),
                0x100000 - 0xD000,
            )

    def mutate(self, root: Path, relative: str, change: Callable[[dict], None]) -> Path:
        target = root / "report"
        shutil.copytree(REPORT, target)
        manifest_path = target / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        name = relative if relative in manifest["files"] else relative + ".gz"
        record = manifest["files"][name]
        raw = (target / name).read_bytes()
        content = gzip.decompress(raw) if record["compression"] == "gzip" else raw
        value = json.loads(content)
        change(value)
        content = (json.dumps(value, indent=2) + "\n").encode()
        raw = (
            gzip.compress(content, mtime=0)
            if record["compression"] == "gzip"
            else content
        )
        (target / name).write_bytes(raw)
        record.update(
            sha256=hashlib.sha256(raw).hexdigest(),
            contentSha256=hashlib.sha256(content).hexdigest(),
            contentBytes=len(content),
        )
        manifest_path.write_text(json.dumps(manifest))
        return target

    def test_false_performance_promotion_rejected_after_hash_rebinding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = self.mutate(
                Path(temporary),
                "decision.json",
                lambda value: value.update(performanceClaim=True),
            )
            with self.assertRaisesRegex(ValueError, "Decision replay drift"):
                VERIFY.verify(target, REPO)

    def test_cpu_fallback_rejected_after_hash_rebinding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:

            def fallback(value: dict) -> None:
                value["operatorProviders"][0] = "CPUExecutionProvider"

            target = self.mutate(
                Path(temporary), "raw/qualification/doe-matched.json", fallback
            )
            with self.assertRaisesRegex(ValueError, "CPU fallback"):
                VERIFY.verify(target, REPO)

    def test_diagnostic_cannot_weaken_oracle_after_hash_rebinding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "report"
            shutil.copytree(REPORT, target)
            manifest_path = target / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            name = "raw/diagnostic-v5/application-provider.h.gz"
            content = gzip.decompress((target / name).read_bytes())
            content = content.replace(
                b'std::stof(campaign_env("CAMPAIGN_ATOL"))', b"1.0f"
            )
            raw = gzip.compress(content, mtime=0)
            (target / name).write_bytes(raw)
            manifest["files"][name].update(
                sha256=hashlib.sha256(raw).hexdigest(),
                contentSha256=hashlib.sha256(content).hexdigest(),
                contentBytes=len(content),
            )
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "changed application semantics"):
                VERIFY.verify(target, REPO)

    def test_altered_pc_is_not_rescued_by_unchanged_sample_totals(self) -> None:
        relative = "raw/caller-collection/0-sample-1000-doe/"
        profile = json.loads(
            gzip.decompress(
                (REPORT / (relative + "profile-final.json.gz")).read_bytes()
            )
        )
        records = list(
            struct.iter_unpack(
                "<" + "Q" * 16,
                gzip.decompress((REPORT / (relative + "samples.bin.gz")).read_bytes()),
            )
        )
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "maps").write_bytes(
                gzip.decompress((REPORT / (relative + "maps.gz")).read_bytes())
            )
            VERIFY.replay_locations(directory, profile, records)
            record = list(records[0])
            record[0] += 1
            records[0] = tuple(record)
            with self.assertRaisesRegex(ValueError, "Instruction location drift"):
                VERIFY.replay_locations(directory, profile, records)


if __name__ == "__main__":
    unittest.main()

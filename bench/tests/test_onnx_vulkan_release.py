"""Installation integrity and acceptance reject tampering and missing GPU work."""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "bench/external-projects/onnx-vulkan-release"


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SOURCE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DISTRIBUTION = load("distribution")
with patch.dict(sys.modules, {"distribution": DISTRIBUTION}):
    QUALIFICATION = load("qualification")
    with patch.dict(sys.modules, {"qualification": QUALIFICATION}):
        EVIDENCE = load("verify_evidence")


def seal_test_package(root: Path) -> dict:
    metadata = {
        "version": "0.1.0-eval.1",
        "target": "linux-x64-amd-vulkan",
        "qualification": {"applicationProcesses": 2},
        "compatibility": {},
    }
    inputs = DISTRIBUTION.inventory(root)
    DISTRIBUTION.write_json(
        root / "release-inputs.json",
        {
            **metadata,
            "inputs": inputs,
            "ownedFiles": {},
        },
    )
    (root / "release-inputs.json").chmod(0o644)
    manifest = {
        **metadata,
        "schemaVersion": 1,
        "kind": "doe-onnx-vulkan-evaluation",
        "files": DISTRIBUTION.inventory(root),
    }
    DISTRIBUTION.write_json(root / "manifest.json", manifest)
    (root / "manifest.json").chmod(0o644)
    return manifest


class ReleaseIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / "package"
        self.package.mkdir()
        (self.package / "native.so").write_bytes(b"qualified-native")
        (self.package / "native.so").chmod(0o644)
        seal_test_package(self.package)

    def test_manifest_cannot_remove_frozen_acceptance(self) -> None:
        path = self.package / "manifest.json"
        manifest = json.loads(path.read_text("utf-8"))
        manifest["qualification"]["applicationProcesses"] = 0
        DISTRIBUTION.write_json(path, manifest)
        with self.assertRaisesRegex(ValueError, "frozen input plan"):
            DISTRIBUTION.verify(self.package)

    def test_reproducible_archive_and_relocated_install(self) -> None:
        first, second = self.root / "first.tgz", self.root / "second.tgz"
        DISTRIBUTION.archive(self.package, first)
        moved = self.root / "relocated"
        shutil.copytree(self.package, moved)
        (moved / "native.so").touch()
        DISTRIBUTION.archive(moved, second)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        installed = self.root / "consumer/version"
        DISTRIBUTION.install(first, DISTRIBUTION.digest(first), installed)
        self.assertEqual(
            DISTRIBUTION.verify(installed), DISTRIBUTION.verify(self.package)
        )
        with self.assertRaises(FileExistsError):
            DISTRIBUTION.install(first, DISTRIBUTION.digest(first), installed)

    def test_changed_or_additional_files_rejected(self) -> None:
        (self.package / "native.so").write_bytes(b"different-native")
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            DISTRIBUTION.verify(self.package)
        (self.package / "native.so").write_bytes(b"qualified-native")
        (self.package / "unexpected.so").write_bytes(b"unqualified")
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            DISTRIBUTION.verify(self.package)

    def test_redirected_member_rejected(self) -> None:
        native = self.package / "native.so"
        native.unlink()
        source = self.root / "outside.so"
        source.write_bytes(b"qualified-native")
        native.symlink_to(source)
        with self.assertRaisesRegex(ValueError, "Symlink"):
            DISTRIBUTION.verify(self.package)

    def test_bad_digest_never_publishes_installation(self) -> None:
        archive = self.root / "release.tgz"
        DISTRIBUTION.archive(self.package, archive)
        destination = self.root / "installed"
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            DISTRIBUTION.install(archive, "0" * 64, destination)
        self.assertFalse(destination.exists())

    def test_escaping_duplicate_and_link_members_never_install(self) -> None:
        for index, mode in enumerate(("escape", "duplicate", "symlink")):
            archive = self.root / f"{index}.tgz"
            with tarfile.open(archive, "w:gz") as tar:
                info = tarfile.TarInfo("../escape" if mode == "escape" else "data")
                info.mode = 0o644
                if mode == "symlink":
                    info.type, info.linkname = tarfile.SYMTYPE, "/tmp"
                else:
                    info.size = 1
                tar.addfile(info, io.BytesIO(b"x") if mode != "symlink" else None)
                if mode == "duplicate":
                    tar.addfile(info, io.BytesIO(b"x"))
            destination = self.root / f"installed-{index}"
            with self.assertRaises(ValueError):
                DISTRIBUTION.install(archive, DISTRIBUTION.digest(archive), destination)
            self.assertFalse(destination.exists())
            self.assertFalse((self.root / "escape").exists())


class ReleaseEvidenceTests(unittest.TestCase):
    def test_missing_submission_or_changed_spirv_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "observations").touch()
            (root / "shader.spv").write_bytes(b"exact-spirv")
            DISTRIBUTION.write_json(
                root / "profile.json",
                [
                    {
                        "cat": "Node",
                        "args": {
                            "provider": "WebGpuExecutionProvider",
                            "op_name": "Conv",
                        },
                    }
                ],
            )
            names = [
                "deviceCreateShaderModule",
                "computePassEncoderDispatchWorkgroups",
                "queueSubmit",
                "bufferMapAsync",
                "deviceDestroy",
                "deviceRelease",
            ]
            DISTRIBUTION.write_json(root / "bridge-build.json", {"procNames": names})
            libraries = [
                "doe.so",
                "bridge.so",
                "context.so",
                "provider.so",
                "libonnxruntime.so.1",
                "libonnxruntime_providers_shared.so",
            ]
            manifest = {
                "qualification": {"vendorId": 4098},
                "files": {name: {"sha256": "a" * 64} for name in libraries},
            }
            observed = [
                {"path": "/application/" + name, "sha256": "a" * 64}
                for name in libraries
            ]
            observed.append(
                {"path": "/usr/lib/libvulkan_radeon.so", "sha256": "b" * 64}
            )
            content = (
                "CampaignProfile /results/profile.json\nCampaignContext 6 4098 1 1\n"
            )
            content += "".join(f"CampaignCallCount {i} 1\n" for i in range(len(names)))
            rows = [
                {
                    "processId": 1,
                    "sequence": 1,
                    "event": "dispatch_encoded",
                    "backend": "doe_vulkan",
                    "wgslSha256": "c" * 64,
                    "backendArtifactFile": "shader.spv",
                    "backendArtifactSha256": DISTRIBUTION.digest(root / "shader.spv"),
                },
                {"processId": 1, "sequence": 2, "event": "submission_succeeded"},
            ]
            trace = root / "native.jsonl"
            trace.write_text(
                "\n".join(json.dumps(row) for row in rows), encoding="utf-8"
            )
            with patch.object(QUALIFICATION, "loaded_libraries", return_value=observed):
                self.assertEqual(
                    QUALIFICATION.application_evidence(root, root, content, manifest)[
                        "dispatchCount"
                    ],
                    1,
                )
                trace.write_text(json.dumps(rows[0]), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "submission evidence"):
                    QUALIFICATION.application_evidence(root, root, content, manifest)
                trace.write_text(
                    "\n".join(json.dumps(row) for row in rows), encoding="utf-8"
                )
                (root / "shader.spv").write_bytes(b"changed-spirv")
                with self.assertRaisesRegex(ValueError, "changed executed SPIR-V"):
                    QUALIFICATION.application_evidence(root, root, content, manifest)

    def test_cpu_fallback_rejected_before_native_credit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            DISTRIBUTION.write_json(
                out / "profile.json",
                [
                    {
                        "cat": "Node",
                        "args": {"provider": "CPUExecutionProvider", "op_name": "Conv"},
                    }
                ],
            )
            with self.assertRaisesRegex(ValueError, "all execute on WebGPU"):
                QUALIFICATION.application_evidence(
                    out, out, "CampaignProfile /results/profile.json\n", {}
                )

    def test_requested_but_unloaded_library_is_not_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "doe.so").write_bytes(b"native")
            self.assertEqual(
                QUALIFICATION.loaded_libraries(
                    "trying file=/application/doe.so\n", root
                ),
                [],
            )
            observed = QUALIFICATION.loaded_libraries(
                "42: calling init: /application/doe.so\n", root
            )
            self.assertEqual(
                observed[0]["sha256"], DISTRIBUTION.digest(root / "doe.so")
            )

    def test_omitted_controls_rejected_even_with_passed_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            package = out / "package"
            package.mkdir()
            manifest = seal_test_package(package)
            receipt = {
                "manifestSha256": DISTRIBUTION.digest(package / "manifest.json"),
                "version": manifest["version"],
                "mode": "qualify",
                "passed": True,
                "jobs": [],
            }
            DISTRIBUTION.write_json(out / "qualification.json", receipt)
            with self.assertRaisesRegex(ValueError, "acceptance jobs"):
                EVIDENCE.verify_results(package, out)


if __name__ == "__main__":
    unittest.main()

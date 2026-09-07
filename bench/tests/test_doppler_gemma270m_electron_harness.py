from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import jsonschema

from bench.external_project_reproduction import reproduction_plan, resolve_selection


REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_PATH = (
    REPO_ROOT
    / "bench/external-projects/doppler/gemma270m-electron.harness.json"
)
SCHEMA_PATH = REPO_ROOT / "config/external-project-harness.schema.json"


class DopplerGemma270mElectronHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.harness = json.loads(HARNESS_PATH.read_text(encoding="utf-8"))
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.validator = jsonschema.Draft202012Validator(cls.schema)

    def test_harness_validates_against_canonical_external_project_schema(self) -> None:
        self.assertEqual(list(self.validator.iter_errors(self.harness)), [])

    def test_runner_is_valid_ecmascript_module_syntax(self) -> None:
        runner = REPO_ROOT / self.harness["workload"]["command"][1]
        completed = subprocess.run(
            ["node", "--check", str(runner)],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_model_contract_rejects_missing_model_shader_and_provider_identity(self) -> None:
        removals = (
            ("modelId",),
            ("artifactSource",),
            ("shaderIdentity",),
            ("providerContract",),
            ("application", "package"),
            ("providers", "W0"),
            ("providers", "D0"),
        )
        for removal in removals:
            with self.subTest(removal=removal):
                payload = copy.deepcopy(self.harness)
                target = payload["workload"]["modelContract"]
                for key in removal[:-1]:
                    target = target[key]
                del target[removal[-1]]
                errors = list(self.validator.iter_errors(payload))
                self.assertTrue(errors)

    def test_dry_run_resolves_frozen_source_application_providers_tuple_and_outputs(self) -> None:
        selection = resolve_selection(
            REPO_ROOT,
            "doppler",
            "gemma270m-electron",
            run_id="amd-gemma270m-qm0",
        )

        plan = reproduction_plan(selection)
        resolved = plan["resolvedContract"]
        model = resolved["modelContract"]

        self.assertEqual(
            resolved["upstream"]["commit"],
            "c27d1354b24f2ddfaaccd2742d1550a848db1931",
        )
        self.assertEqual(
            model["manifest"]["path"],
            "models/local/gemma-3-270m-it-q4k-ehf16-af32/manifest.json",
        )
        self.assertEqual(model["artifactSource"]["project"], "doppler")
        self.assertEqual(
            model["artifactSource"]["path"],
            "models/local/gemma-3-270m-it-q4k-ehf16-af32",
        )
        self.assertEqual(model["application"]["runtime"], "electron")
        self.assertEqual(model["application"]["version"], "43.4.0")
        self.assertEqual(
            model["application"]["package"]["path"],
            "bench/external-projects/doppler/electron-app/package.json",
        )
        self.assertFalse(model["execution"]["useChatTemplate"])
        self.assertEqual(model["providers"]["W0"]["id"], "dawn-node-webgpu")
        self.assertEqual(model["providers"]["D0"]["id"], "doe-gpu")
        self.assertEqual(model["providers"]["P0"]["sourceBuild"]["kind"], "electron-owned-mappings-p0")
        self.assertEqual(
            resolved["supportTargets"],
            [
                {
                    "id": "linux-x64-radeon-8060s-radv-26-0-3-electron-43-4-0",
                    "os": "linux",
                    "arch": "x86_64",
                    "runtime": "electron-43.4.0",
                    "adapter": "Radeon 8060S Graphics",
                    "driver": "Mesa 26.0.3",
                    "status": "validated",
                }
            ],
        )

        self.assertEqual(
            plan["outputs"]["preparationReceipt"],
            "bench/out/external-projects/doppler/amd-gemma270m-qm0/preparation.json",
        )
        self.assertEqual(
            plan["outputs"]["reproductionReceipt"],
            "bench/out/external-projects/doppler/amd-gemma270m-qm0/reproduction.json",
        )
        self.assertEqual(
            [entry["path"] for entry in plan["outputs"]["evidence"]],
            [
                "bench/out/external-projects/doppler/amd-gemma270m-qm0/result.json",
                "bench/out/external-projects/doppler/amd-gemma270m-qm0/oracle.json",
                (
                    "bench/out/external-projects/doppler/amd-gemma270m-qm0/"
                    "lanes/W0/doppler_int4ple_reference_export.json"
                ),
                (
                    "bench/out/external-projects/doppler/amd-gemma270m-qm0/"
                    "lanes/D0/doppler_int4ple_reference_export.json"
                ),
            ],
        )

    def test_source_built_control_requires_patch_and_native_identity(self) -> None:
        for missing in ("patch", "library", "provenance", "sourceRevision"):
            with self.subTest(missing=missing):
                payload = copy.deepcopy(self.harness)
                del payload["workload"]["modelContract"]["providers"]["P0"]["sourceBuild"][missing]
                self.assertTrue(list(self.validator.iter_errors(payload)))

    def test_unknown_incumbent_rejects_before_preparation_or_execution(self) -> None:
        runner = REPO_ROOT / self.harness["workload"]["command"][1]
        result = subprocess.run(
            ["node", str(runner), "--run-id", "invalid-control", "--upstream-root", "/missing",
             "--preparation-receipt", "/missing", "--out", "/missing", "--incumbent", "automatic"],
            capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--incumbent must be W0 or P0", result.stderr)

    def test_p0_requires_versioned_opt_in(self) -> None:
        payload = copy.deepcopy(self.harness)
        payload["schemaVersion"] = 4
        self.assertTrue(list(self.validator.iter_errors(payload)))
        del payload["workload"]["modelContract"]["providers"]["P0"]
        self.assertEqual(list(self.validator.iter_errors(payload)), [])

    def test_interrupted_output_is_not_reused(self) -> None:
        runner = REPO_ROOT / self.harness["workload"]["command"][1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "lanes").mkdir()
            result = subprocess.run(
                ["node", str(runner), "--run-id", "interrupted", "--upstream-root", "/missing",
                 "--preparation-receipt", "/missing", "--out", str(root / "result.json")],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Qualification output already exists", result.stderr)

    def test_passing_result_requires_loaded_library_receipts_and_p0_provenance(self) -> None:
        schema = json.loads((REPO_ROOT / "config/gemma270m-electron-qualification.schema.json").read_text())
        validator = jsonschema.Draft202012Validator(schema)
        # Use the retained physical result when available, without requiring GPU work in this test.
        path = REPO_ROOT / "bench/out/external-projects/doppler/20260907-multi-dot-p0-qualified/result.json"
        if not path.exists():
            self.skipTest("retained physical model result unavailable")
        result = json.loads(path.read_text())
        self.assertEqual(list(validator.iter_errors(result)), [])
        for removal in (("runs", "D0", "nativeIdentity"), ("providers", "W0", "sourceBuild")):
            payload = copy.deepcopy(result)
            del payload[removal[0]][removal[1]][removal[2]]
            self.assertTrue(list(validator.iter_errors(payload)))
        result["runs"]["D0"]["exitCode"] = 1
        self.assertTrue(list(validator.iter_errors(result)))

    def test_source_identity_rejects_changed_patch_and_unloaded_library(self) -> None:
        runner = (REPO_ROOT / self.harness["workload"]["command"][1]).as_uri()
        script = (
            "const {validateProviderIdentity} = await import(process.argv[1]);"
            "const provider = JSON.parse(process.argv[2]);"
            "await validateProviderIdentity(provider, process.argv[3], process.argv[3]);"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def artifact(name: str, content: bytes) -> dict:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                return {"path": name, "sha256": hashlib.sha256(content).hexdigest()}

            provider = {
                "id": "dawn-node-webgpu", "targetRoot": "repo",
                "target": artifact("index.js", b"provider"),
                "sourceBuild": {
                    "library": artifact("dist/linux-x64.dawn.node", b"native"),
                    "patch": artifact("source.patch", b"patch"),
                    "provenance": artifact("provenance.txt", b"source"),
                },
            }
            def check() -> subprocess.CompletedProcess:
                return subprocess.run(
                    ["node", "--input-type=module", "-e", script, runner,
                     json.dumps(provider), str(root)],
                    capture_output=True, text=True, check=False,
                )

            self.assertEqual(check().returncode, 0)
            (root / "source.patch").write_bytes(b"changed")
            self.assertIn("source-built patch hash mismatch", check().stderr)
            (root / "source.patch").write_bytes(b"patch")
            provider["sourceBuild"]["library"] = artifact("unloaded.dawn.node", b"native")
            self.assertIn("must be the native module loaded", check().stderr)


if __name__ == "__main__":
    unittest.main()

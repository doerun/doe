"""Exercise peer identity resolution, reference integrity and drift rejection."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import jsonschema

from bench.lib import implementation_peers as peers
from bench.lib.compare_axes import PROVIDER_SETS


class ImplementationPeersTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload = json.loads(
            (peers.REPO_ROOT / peers.REGISTRY_PATH).read_text(encoding="utf-8")
        )
        paths = {peers.REGISTRY_PATH, peers.SCHEMA_PATH, peers.DOC_PATH}
        for peer in self.payload["peers"]:
            paths.update(Path(p) for p in peer["trackingPaths"])
            paths.update(Path(p) for p in peer["evidencePaths"])
        for path in paths:
            (self.root / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(peers.REPO_ROOT / path, self.root / path)

    def save_registry(self) -> None:
        (self.root / peers.REGISTRY_PATH).write_text(
            json.dumps(self.payload), encoding="utf-8",
        )

    def test_registry_change_reaches_consumers_and_invalidates_doc(self) -> None:
        self.assertEqual(peers.validate_peer_document(self.root), [])
        self.payload["peers"][-1]["nativeProviderId"] = "changed-binding"
        self.save_registry()
        entry = {
            "id": "backend_native_providers",
            "sourceRegistryPath": peers.REGISTRY_PATH.as_posix(),
        }
        resolved = peers.resolve_provider_sets([entry], self.root)
        self.assertEqual(resolved[entry["id"]][-1], "changed-binding")
        self.assertIn("stale", peers.validate_peer_document(self.root)[0])
        (self.root / peers.DOC_PATH).write_text(
            peers.render_peers(peers.load_peers(self.root)), encoding="utf-8",
        )
        self.assertEqual(peers.validate_peer_document(self.root), [])

    def test_duplicate_family_and_provider_are_rejected(self) -> None:
        for key in ("id", "nativeProviderId"):
            with self.subTest(key=key):
                original = self.payload["peers"][1][key]
                self.payload["peers"][1][key] = self.payload["peers"][0][key]
                self.save_registry()
                with self.assertRaisesRegex(ValueError, "duplicate or reserved"):
                    peers.load_peers(self.root)
                self.payload["peers"][1][key] = original

    def test_missing_and_escaping_references_are_rejected(self) -> None:
        for path in ("missing.json", "../outside.json"):
            with self.subTest(path=path):
                self.payload["peers"][0]["trackingPaths"] = [path]
                self.save_registry()
                with self.assertRaisesRegex(ValueError, "invalid local reference"):
                    peers.load_peers(self.root)

    def test_malformed_registry_is_a_gate_failure(self) -> None:
        self.payload["peers"][0]["unregisteredField"] = True
        self.save_registry()
        self.assertIn("Additional properties", peers.validate_peer_document(self.root)[0])

    def test_cube_and_compare_axes_share_membership(self) -> None:
        cube = json.loads(
            (peers.REPO_ROOT / "config/benchmark-cube-policy.json").read_text(
                encoding="utf-8",
            )
        )
        resolved = peers.resolve_provider_sets(cube["providerSets"])
        self.assertEqual(resolved["backend_native_providers"],
                         PROVIDER_SETS["backend_native_providers"])
        self.assertEqual(resolved["backend_native_providers"],
                         PROVIDER_SETS["direct_plan_providers"])

    def test_cube_schema_rejects_reintroduced_native_list(self) -> None:
        schema = json.loads(
            (peers.REPO_ROOT / "config/benchmark-cube-policy.schema.json")
            .read_text(encoding="utf-8")
        )["properties"]["providerSets"]["items"]
        entry = {"id": "backend_native_providers", "providers": ["doe"]}
        validator = jsonschema.Draft202012Validator(schema)
        self.assertTrue(list(validator.iter_errors(entry)))
        entry.pop("providers")
        entry["sourceRegistryPath"] = peers.REGISTRY_PATH.as_posix()
        self.assertEqual(list(validator.iter_errors(entry)), [])
        entry["providers"] = ["doe"]
        self.assertTrue(list(validator.iter_errors(entry)))


if __name__ == "__main__":
    unittest.main()

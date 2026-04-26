from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools.compile_cache_manager import (  # noqa: E402
    CACHE_ENTRY_METADATA,
    cache_path,
    is_hit,
    load_entry_metadata,
    restore,
    store,
    target_cache_key,
)


def _make_target_dir(root: Path, *, layout: str, pe_program: str) -> Path:
    target = root / "target"
    target.mkdir(parents=True, exist_ok=False)
    (target / "layout.csl").write_text(layout, encoding="utf-8")
    (target / "pe_program.csl").write_text(pe_program, encoding="utf-8")
    return target


def _make_compiled_dir(root: Path, *, elf_payload: bytes) -> Path:
    compiled = root / "compiled"
    bin_dir = compiled / "bin"
    bin_dir.mkdir(parents=True, exist_ok=False)
    (bin_dir / "out_1_0.elf").write_bytes(elf_payload)
    (compiled / "driver-log.txt").write_text("ok\n", encoding="utf-8")
    return compiled


class TargetCacheKeyTest(unittest.TestCase):
    def test_key_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            target = _make_target_dir(
                root, layout="layout {}\n", pe_program="fn compute() void {}\n"
            )
            k1 = target_cache_key(target)
            k2 = target_cache_key(target)
            self.assertEqual(k1, k2)
            self.assertEqual(len(k1), 64)

    def test_key_changes_with_layout_change(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            t1 = _make_target_dir(
                root / "a", layout="layout {}\n", pe_program="x"
            )
            t2 = _make_target_dir(
                root / "b", layout="layout { pe }\n", pe_program="x"
            )
            self.assertNotEqual(target_cache_key(t1), target_cache_key(t2))

    def test_key_changes_with_pe_program_change(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            t1 = _make_target_dir(
                root / "a", layout="L", pe_program="fn a() void {}"
            )
            t2 = _make_target_dir(
                root / "b", layout="L", pe_program="fn b() void {}"
            )
            self.assertNotEqual(target_cache_key(t1), target_cache_key(t2))

    def test_key_changes_with_compile_params(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            target = _make_target_dir(root, layout="L", pe_program="P")
            k_default = target_cache_key(target)
            k_with_params = target_cache_key(
                target, compile_params={"channels": 1}
            )
            self.assertNotEqual(k_default, k_with_params)

    def test_compile_params_ordering_is_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            target = _make_target_dir(root, layout="L", pe_program="P")
            k_a = target_cache_key(
                target,
                compile_params={"channels": 1, "fabricSize": "8x3"},
            )
            k_b = target_cache_key(
                target,
                compile_params={"fabricSize": "8x3", "channels": 1},
            )
            self.assertEqual(k_a, k_b)

    def test_missing_layout_raises(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            target = Path(scratch) / "no-layout"
            target.mkdir()
            (target / "pe_program.csl").write_text("p", encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                target_cache_key(target)

    def test_missing_pe_program_raises(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            target = Path(scratch) / "no-pe"
            target.mkdir()
            (target / "layout.csl").write_text("l", encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                target_cache_key(target)


class CacheStoreRestoreTest(unittest.TestCase):
    def test_miss_then_store_then_hit(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            target = _make_target_dir(root, layout="L", pe_program="P")
            compiled = _make_compiled_dir(root, elf_payload=b"\x7fELF...")
            cache_root = root / "cache"
            key = target_cache_key(target)
            self.assertFalse(is_hit(cache_root, key))
            entry = store(
                cache_root,
                key,
                target_compile_dir=compiled,
                source_target_dir=target,
                compile_params={"channels": 1},
            )
            self.assertTrue(is_hit(cache_root, key))
            self.assertTrue((entry / "bin/out_1_0.elf").is_file())
            self.assertTrue((entry / CACHE_ENTRY_METADATA).is_file())
            metadata = load_entry_metadata(cache_root, key)
            self.assertIsNotNone(metadata)
            assert metadata is not None
            self.assertEqual(metadata["key"], key)
            self.assertEqual(metadata["compileParams"], {"channels": 1})

    def test_restore_to_clean_dir(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            target = _make_target_dir(root, layout="L", pe_program="P")
            compiled = _make_compiled_dir(root, elf_payload=b"\x7fELF...")
            cache_root = root / "cache"
            key = target_cache_key(target)
            store(
                cache_root,
                key,
                target_compile_dir=compiled,
                source_target_dir=target,
            )

            restored_dir = root / "restored"
            restore(cache_root, key, restored_dir)
            self.assertTrue((restored_dir / "bin/out_1_0.elf").is_file())
            self.assertEqual(
                (restored_dir / "bin/out_1_0.elf").read_bytes(),
                b"\x7fELF...",
            )
            # Cache-entry metadata stays in the cache, not in the restored dir.
            self.assertFalse((restored_dir / CACHE_ENTRY_METADATA).is_file())

    def test_restore_overwrites_existing_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            target = _make_target_dir(root, layout="L", pe_program="P")
            compiled = _make_compiled_dir(root, elf_payload=b"\x7fELF...new")
            cache_root = root / "cache"
            key = target_cache_key(target)
            store(
                cache_root,
                key,
                target_compile_dir=compiled,
                source_target_dir=target,
            )
            restored_dir = root / "restored"
            restored_dir.mkdir()
            (restored_dir / "bin").mkdir()
            (restored_dir / "bin/out_1_0.elf").write_bytes(b"\x7fELF...stale")
            restore(cache_root, key, restored_dir)
            self.assertEqual(
                (restored_dir / "bin/out_1_0.elf").read_bytes(),
                b"\x7fELF...new",
            )

    def test_restore_miss_raises(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            cache_root = root / "cache"
            with self.assertRaises(FileNotFoundError):
                restore(cache_root, "0" * 64, root / "restored")

    def test_store_replaces_prior_entry_for_same_key(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            target = _make_target_dir(root, layout="L", pe_program="P")
            compiled_a = _make_compiled_dir(root / "a", elf_payload=b"A")
            compiled_b = _make_compiled_dir(root / "b", elf_payload=b"B")
            cache_root = root / "cache"
            key = target_cache_key(target)
            store(
                cache_root,
                key,
                target_compile_dir=compiled_a,
                source_target_dir=target,
            )
            store(
                cache_root,
                key,
                target_compile_dir=compiled_b,
                source_target_dir=target,
            )
            entry = cache_path(cache_root, key)
            self.assertEqual((entry / "bin/out_1_0.elf").read_bytes(), b"B")

    def test_store_refuses_compile_dir_without_bin(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            target = _make_target_dir(root, layout="L", pe_program="P")
            empty = root / "empty"
            empty.mkdir()
            cache_root = root / "cache"
            key = target_cache_key(target)
            with self.assertRaises(FileNotFoundError):
                store(
                    cache_root,
                    key,
                    target_compile_dir=empty,
                    source_target_dir=target,
                )

    def test_metadata_round_trips_as_json(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            target = _make_target_dir(root, layout="L", pe_program="P")
            compiled = _make_compiled_dir(root, elf_payload=b"\x7fELF")
            cache_root = root / "cache"
            key = target_cache_key(target)
            store(
                cache_root,
                key,
                target_compile_dir=compiled,
                source_target_dir=target,
            )
            entry = cache_path(cache_root, key)
            text = (entry / CACHE_ENTRY_METADATA).read_text(encoding="utf-8")
            payload = json.loads(text)
            self.assertEqual(payload["schemaVersion"], 1)
            self.assertEqual(payload["artifactKind"], "doe_compile_cache_entry")
            self.assertIn("layout.csl", payload["inputHashes"])
            self.assertIn("pe_program.csl", payload["inputHashes"])


if __name__ == "__main__":
    unittest.main()

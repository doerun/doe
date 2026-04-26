from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools import compile_cache_manager  # noqa: E402


def _load_driver_module():
    """Import the script-style driver under a stable module name.

    The driver lives at `runtime/zig/tools/csl_sdk_driver.py` and is
    designed to run as a script. We import via importlib so the test
    can exercise `compile_targets` directly.
    """
    if "csl_sdk_driver" in sys.modules:
        return sys.modules["csl_sdk_driver"]
    spec = importlib.util.spec_from_file_location(
        "csl_sdk_driver",
        REPO_ROOT / "runtime/zig/tools/csl_sdk_driver.py",
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["csl_sdk_driver"] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_plan_dir(tmp: Path, *, kernel: str = "kernelA") -> tuple[Path, Path]:
    """Materialize a minimal plan directory with one kernel target.

    Returns (plan_path, target_dir). The plan satisfies just enough of
    the driver's reads — the driver's compile_targets() only consults
    plan["inputs"]["compileRootPath"], plan["inputs"]["compileTargets"],
    plan["runtime"]["peGrid"], and plan["target"].
    """
    compile_root = tmp / "compile"
    target_dir = compile_root / kernel
    target_dir.mkdir(parents=True)
    (target_dir / "layout.csl").write_text(
        "layout {}\n", encoding="utf-8"
    )
    (target_dir / "pe_program.csl").write_text(
        "fn compute() void { sys_mod.unblock_cmd_stream(); }\n",
        encoding="utf-8",
    )
    plan: dict[str, object] = {
        "target": "wse3",
        "inputs": {
            "compileRootPath": "compile",
            "compileTargets": [
                {
                    "name": kernel,
                    "layout": f"{kernel}/layout.csl",
                    "peProgram": f"{kernel}/pe_program.csl",
                    "compileParams": {"width": 1, "height": 1},
                }
            ],
            "runtimeConfigPath": "runtime-config.json",
        },
        "runtime": {
            "peGrid": {"width": 1, "height": 1},
            "channels": 1,
            "memcpy": True,
        },
        "outputs": {
            "tracePath": "trace.json",
            "stdoutPath": "stdout.log",
            "stderrPath": "stderr.log",
        },
    }
    plan_path = tmp / "plan.json"
    plan_path.write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return plan_path, target_dir


def _seed_cache(
    cache_root: Path,
    *,
    target_dir: Path,
    cache_compile_params: dict[str, object],
    elf_payload: bytes,
) -> str:
    """Pre-populate the cache for a target so the driver should hit on
    the next run."""
    key = compile_cache_manager.target_cache_key(
        target_dir, compile_params=cache_compile_params
    )
    with tempfile.TemporaryDirectory() as scratch:
        compiled = Path(scratch) / "compiled"
        bin_dir = compiled / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "out_1_0.elf").write_bytes(elf_payload)
        compile_cache_manager.store(
            cache_root,
            key,
            target_compile_dir=compiled,
            source_target_dir=target_dir,
            compile_params=cache_compile_params,
        )
    return key


def _expected_cache_compile_params(
    *,
    arch: str = "wse3",
    width: int = 1,
    height: int = 1,
) -> dict[str, object]:
    """Mirror the cache_compile_params dict that the driver constructs.

    Stays in sync with `compile_targets` in csl_sdk_driver.py: any
    cslc-flag change there must update this helper too — that is the
    contract this test enforces.
    """
    fabric_dims = [0 + 4 + width + 0 + 3, 1 + height + 1]
    fabric_offsets = [0 + 4, 1]
    return {
        "arch": arch,
        "channels": 1,
        "fabricDims": fabric_dims,
        "fabricOffsets": fabric_offsets,
        "memcpy": True,
        "widthWestBuf": 0,
        "widthEastBuf": 0,
        "params": {"width": width, "height": height},
    }


class CompileCacheWiringTest(unittest.TestCase):
    def test_cache_hit_skips_cslc_invocation(self) -> None:
        driver = _load_driver_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            plan_path, target_dir = _make_plan_dir(tmp_path)
            cache_root = tmp_path / "cache"
            elf_payload = b"\x7fELF...cached"
            _seed_cache(
                cache_root,
                target_dir=target_dir,
                cache_compile_params=_expected_cache_compile_params(),
                elf_payload=elf_payload,
            )

            # Stub run_command. If invoked, the test fails (cache hit
            # must short-circuit cslc).
            calls: list[list[str]] = []

            def fake_run_command(command, *args, **kwargs):
                calls.append(list(command))
                return 1, "", "", False

            original = driver.run_command
            driver.run_command = fake_run_command
            try:
                plan = json.loads(plan_path.read_text(encoding="utf-8"))
                summary, targets, _ = driver.compile_targets(
                    plan_path=plan_path,
                    plan=plan,
                    cslc_executable="cslc-must-not-run",
                    compile_cache_root=cache_root,
                )
            finally:
                driver.run_command = original

            self.assertEqual(calls, [], "cache hit should bypass cslc")
            self.assertEqual(summary["status"], "succeeded")
            self.assertEqual(len(targets), 1)
            entry = targets[0]
            self.assertEqual(entry["status"], "succeeded")
            self.assertTrue(entry["cacheHit"])
            self.assertFalse(entry["cacheStored"])
            self.assertEqual(len(entry["cacheKey"]), 64)

            # Cached binary made it into output_dir.
            output_dir = Path(entry["outputDir"])
            cached_elf = output_dir / "bin/out_1_0.elf"
            self.assertTrue(cached_elf.is_file())
            self.assertEqual(cached_elf.read_bytes(), elf_payload)

    def test_cache_miss_then_store_then_hit(self) -> None:
        driver = _load_driver_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            plan_path, _ = _make_plan_dir(tmp_path)
            cache_root = tmp_path / "cache"

            # First run: stub cslc to write a fake bin/out_1_0.elf into
            # output_dir, mimicking a real cslc compile.
            stubbed_payload = b"\x7fELF...freshly-compiled"
            invocation_count = {"n": 0}

            def fake_run_command(
                command, stdout_path, stderr_path, *args, **kwargs
            ):
                invocation_count["n"] += 1
                # The driver passes -o <output_dir> as the last two
                # tokens; pull it out and seed the bin dir.
                output_dir_idx = command.index("-o") + 1
                output_dir = Path(command[output_dir_idx])
                (output_dir / "bin").mkdir(parents=True, exist_ok=True)
                (output_dir / "bin/out_1_0.elf").write_bytes(stubbed_payload)
                Path(stdout_path).write_text("ok\n", encoding="utf-8")
                Path(stderr_path).write_text("", encoding="utf-8")
                return 0, str(stdout_path), str(stderr_path), False

            original = driver.run_command
            driver.run_command = fake_run_command
            try:
                plan = json.loads(plan_path.read_text(encoding="utf-8"))
                summary_a, targets_a, _ = driver.compile_targets(
                    plan_path=plan_path,
                    plan=plan,
                    cslc_executable="cslc-fake",
                    compile_cache_root=cache_root,
                )
                self.assertEqual(summary_a["status"], "succeeded")
                self.assertEqual(invocation_count["n"], 1)
                self.assertFalse(targets_a[0]["cacheHit"])
                self.assertTrue(targets_a[0]["cacheStored"])

                # Second run: same plan, cache should now hit.
                summary_b, targets_b, _ = driver.compile_targets(
                    plan_path=plan_path,
                    plan=plan,
                    cslc_executable="cslc-fake",
                    compile_cache_root=cache_root,
                )
                self.assertEqual(summary_b["status"], "succeeded")
                self.assertEqual(
                    invocation_count["n"],
                    1,
                    "second run must hit cache; cslc must not be called",
                )
                self.assertTrue(targets_b[0]["cacheHit"])
                self.assertFalse(targets_b[0]["cacheStored"])
                self.assertEqual(
                    targets_a[0]["cacheKey"], targets_b[0]["cacheKey"]
                )
            finally:
                driver.run_command = original

    def test_no_compile_cache_disables_lookup_and_store(self) -> None:
        driver = _load_driver_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            plan_path, _ = _make_plan_dir(tmp_path)

            calls = {"n": 0}

            def fake_run_command(
                command, stdout_path, stderr_path, *args, **kwargs
            ):
                calls["n"] += 1
                output_dir_idx = command.index("-o") + 1
                output_dir = Path(command[output_dir_idx])
                (output_dir / "bin").mkdir(parents=True, exist_ok=True)
                (output_dir / "bin/out_1_0.elf").write_bytes(b"\x7fELF")
                Path(stdout_path).write_text("ok\n", encoding="utf-8")
                Path(stderr_path).write_text("", encoding="utf-8")
                return 0, str(stdout_path), str(stderr_path), False

            original = driver.run_command
            driver.run_command = fake_run_command
            try:
                plan = json.loads(plan_path.read_text(encoding="utf-8"))
                summary_a, targets_a, _ = driver.compile_targets(
                    plan_path=plan_path,
                    plan=plan,
                    cslc_executable="cslc-fake",
                    compile_cache_root=None,
                )
                summary_b, targets_b, _ = driver.compile_targets(
                    plan_path=plan_path,
                    plan=plan,
                    cslc_executable="cslc-fake",
                    compile_cache_root=None,
                )
            finally:
                driver.run_command = original

            self.assertEqual(summary_a["status"], "succeeded")
            self.assertEqual(summary_b["status"], "succeeded")
            self.assertEqual(
                calls["n"], 2, "without cache, cslc must run every time"
            )
            self.assertNotIn("cacheKey", targets_a[0])
            self.assertNotIn("cacheKey", targets_b[0])

    def test_cache_invalidates_on_layout_change(self) -> None:
        driver = _load_driver_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            plan_path, target_dir = _make_plan_dir(tmp_path)
            cache_root = tmp_path / "cache"

            calls = {"n": 0}

            def fake_run_command(
                command, stdout_path, stderr_path, *args, **kwargs
            ):
                calls["n"] += 1
                output_dir_idx = command.index("-o") + 1
                output_dir = Path(command[output_dir_idx])
                (output_dir / "bin").mkdir(parents=True, exist_ok=True)
                (output_dir / "bin/out_1_0.elf").write_bytes(b"\x7fELF")
                Path(stdout_path).write_text("ok\n", encoding="utf-8")
                Path(stderr_path).write_text("", encoding="utf-8")
                return 0, str(stdout_path), str(stderr_path), False

            original = driver.run_command
            driver.run_command = fake_run_command
            try:
                plan = json.loads(plan_path.read_text(encoding="utf-8"))
                driver.compile_targets(
                    plan_path=plan_path,
                    plan=plan,
                    cslc_executable="cslc-fake",
                    compile_cache_root=cache_root,
                )
                self.assertEqual(calls["n"], 1)

                # Mutate the layout — cache key must change.
                (target_dir / "layout.csl").write_text(
                    "layout { changed }\n", encoding="utf-8"
                )
                _, targets, _ = driver.compile_targets(
                    plan_path=plan_path,
                    plan=plan,
                    cslc_executable="cslc-fake",
                    compile_cache_root=cache_root,
                )
            finally:
                driver.run_command = original

            self.assertEqual(
                calls["n"], 2, "layout change must invalidate cache"
            )
            self.assertFalse(targets[0]["cacheHit"])
            self.assertTrue(targets[0]["cacheStored"])


if __name__ == "__main__":
    unittest.main()

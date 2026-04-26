from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_runner_module():
    if "manifest_kernel_probe_runner" in sys.modules:
        return sys.modules["manifest_kernel_probe_runner"]
    spec = importlib.util.spec_from_file_location(
        "manifest_kernel_probe_runner",
        REPO_ROOT
        / "bench/runners/csl-runners/manifest_kernel_probe_runner.py",
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["manifest_kernel_probe_runner"] = mod
    spec.loader.exec_module(mod)
    return mod


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _make_kernel_dir(
    compile_root: Path,
    *,
    name: str,
    exports: list[dict[str, object]],
) -> None:
    kdir = compile_root / name
    kdir.mkdir(parents=True, exist_ok=True)
    (kdir / "pe_program.metadata.json").write_text(
        json.dumps({"exports": exports}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (kdir / "bin").mkdir(parents=True, exist_ok=True)
    (kdir / "bin" / "out_1_0.elf").write_bytes(b"\x7fELF")


def _write_probe(
    *,
    probe_dir: Path,
    kernel: str,
    input_fixture_rel: str,
    fixture_path: Path,
    inputs: dict[str, list[float]],
) -> Path:
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(
        json.dumps(
            {
                "kernel": kernel,
                "inputs": {
                    sym: {
                        "elem": "f32",
                        "shape": [len(vals)],
                        "values": vals,
                    }
                    for sym, vals in inputs.items()
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    transcript = probe_dir / f"{kernel}.doppler-transcript.json"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text(
        json.dumps(
            {
                "schema": "doppler.reference-transcript/v1",
                "kernelRef": f"doe.tsir.real.{kernel}",
                "source": {
                    "hash": "sha256:abc",
                    "fixturePath": input_fixture_rel,
                },
                "kernelProbe": {"hash": "abc", "outputElementCount": 4},
                "exactness": {
                    "class": "bit_exact_solo",
                    "toleranceMetric": "",
                    "toleranceEpsilon": 0.0,
                },
                "referenceOutputs": {},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return transcript


class FindProbeTest(unittest.TestCase):
    def test_direct_match(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "embed.doppler-transcript.json").write_text(
                "{}", encoding="utf-8"
            )
            found = runner.find_probe_transcript(
                kernel="embed", probe_dir=tmp_path
            )
            self.assertIsNotNone(found)
            assert found is not None
            self.assertEqual(found.name, "embed.doppler-transcript.json")

    def test_underscore_alias(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "rmsnorm.doppler-transcript.json").write_text(
                "{}", encoding="utf-8"
            )
            found = runner.find_probe_transcript(
                kernel="rms_norm", probe_dir=tmp_path
            )
            self.assertIsNotNone(found)

    def test_absent(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self.assertIsNone(
                runner.find_probe_transcript(
                    kernel="ghost", probe_dir=tmp_path
                )
            )


class MaterializeProbeInputTest(unittest.TestCase):
    def test_zero_when_no_probe_values(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.npy"
            byte_len, strategy = runner.materialize_probe_input(
                target_path=path,
                pe_count=2,
                per_pe_chunk=4,
                elem_type="f32",
                probe_values=None,
            )
            self.assertEqual(strategy, "zero")
            import numpy as np
            arr = np.load(path)
            self.assertEqual(arr.shape, (8,))
            self.assertTrue((arr == 0).all())
            self.assertGreater(byte_len, 0)

    def test_tile_when_probe_smaller_than_buffer(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.npy"
            byte_len, strategy = runner.materialize_probe_input(
                target_path=path,
                pe_count=2,
                per_pe_chunk=4,
                elem_type="f32",
                probe_values=[1.0, 2.0],
            )
            self.assertEqual(strategy, "tile")
            import numpy as np
            arr = np.load(path)
            self.assertEqual(arr.shape, (8,))
            self.assertTrue((arr[::2] == 1.0).all())
            self.assertTrue((arr[1::2] == 2.0).all())

    def test_truncate_when_probe_larger_than_buffer(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.npy"
            byte_len, strategy = runner.materialize_probe_input(
                target_path=path,
                pe_count=1,
                per_pe_chunk=2,
                elem_type="f32",
                probe_values=[1.0, 2.0, 3.0, 4.0, 5.0],
            )
            self.assertEqual(strategy, "truncate")
            import numpy as np
            arr = np.load(path)
            self.assertEqual(arr.shape, (2,))
            self.assertTrue((arr == [1.0, 2.0]).all())


class LoadProbeInputsTest(unittest.TestCase):
    def test_resolves_via_source_fixture_path(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            probe_dir = tmp_path / "probes"
            input_fixture = tmp_path / "inputs/embed.json"
            input_rel = str(input_fixture.relative_to(tmp_path))
            transcript = _write_probe(
                probe_dir=probe_dir,
                kernel="embed",
                input_fixture_rel=input_rel,
                fixture_path=input_fixture,
                inputs={"u": [1.0, 2.0], "indices": [0.0]},
            )
            # Patch REPO_ROOT during the call so the runner resolves
            # input_fixture_rel correctly under tmp.
            original_repo_root = runner.REPO_ROOT
            runner.REPO_ROOT = tmp_path
            try:
                values_by_symbol, metadata = runner.load_probe_inputs(
                    transcript
                )
            finally:
                runner.REPO_ROOT = original_repo_root
            self.assertIn("u", values_by_symbol)
            self.assertEqual(values_by_symbol["u"], [1.0, 2.0])
            self.assertEqual(
                metadata["broadcastStrategy"], "tile_to_manifest_shape"
            )
            self.assertEqual(metadata["kernelRef"], "doe.tsir.real.embed")


class RunOneKernelTest(unittest.TestCase):
    def _setup(
        self, tmp: Path
    ) -> tuple[dict, Path, Path, Path, Path, Path]:
        runner = _load_runner_module()
        compile_root = tmp / "compile"
        compile_root.mkdir(parents=True)
        _make_kernel_dir(
            compile_root,
            name="embed",
            exports=[
                {
                    "symbol": "indices",
                    "elemType": "u32",
                    "sizeExpr": "tokens_per_chunk",
                },
                {
                    "symbol": "table",
                    "elemType": "f32",
                    "sizeExpr": "rows_per_pe * hidden_per_pe",
                },
                {
                    "symbol": "output",
                    "elemType": "f32",
                    "sizeExpr": "tokens_per_chunk * hidden_per_pe",
                },
            ],
        )
        host_plan_path = tmp / "host-plan.json"
        host_plan_path.write_text(
            json.dumps(
                {
                    "compileTargets": [
                        {
                            "name": "embed",
                            "compileParams": {
                                "width": 4,
                                "height": 2,
                                "tokens_per_chunk": 8,
                                "rows_per_pe": 2,
                                "hidden_per_pe": 4,
                            },
                        }
                    ]
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        target = json.loads(host_plan_path.read_text(encoding="utf-8"))[
            "compileTargets"
        ][0]
        probe_dir = tmp / "probes"
        input_fixture = tmp / "inputs/embed.json"
        _write_probe(
            probe_dir=probe_dir,
            kernel="embed",
            input_fixture_rel=str(input_fixture.relative_to(tmp)),
            fixture_path=input_fixture,
            inputs={
                "indices": [3.0],
                "table": [0.5, 1.5],
            },
        )
        out_dir = tmp / "out"
        cs_python = tmp / "cs_python.sh"
        cs_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        cs_python.chmod(0o755)
        adapter = tmp / "adapter.py"
        adapter.write_text("# stub\n", encoding="utf-8")
        return (
            target,
            compile_root,
            probe_dir,
            host_plan_path,
            cs_python,
            adapter,
        )

    def test_dry_run_records_probe_and_strategy(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target, compile_root, probe_dir, host_plan_path, cs_python, adapter = (
                self._setup(tmp_path)
            )
            original_repo_root = runner.REPO_ROOT
            runner.REPO_ROOT = tmp_path
            try:
                receipt = runner.run_one_kernel(
                    kernel="embed",
                    target=target,
                    compile_root=compile_root,
                    probe_dir=probe_dir,
                    host_plan_path=host_plan_path,
                    host_plan_hash=_sha256_file(host_plan_path),
                    out_dir=tmp_path / "out",
                    cmaddr="",
                    timeout_seconds=30,
                    cs_python=cs_python,
                    adapter=adapter,
                    dry_run=True,
                )
            finally:
                runner.REPO_ROOT = original_repo_root
        self.assertEqual(receipt["verdict"], "blocked")
        self.assertEqual(receipt["blocker"], "dry_run")
        self.assertIn("probe", receipt)
        self.assertEqual(
            receipt["probe"]["kernelRef"], "doe.tsir.real.embed"
        )
        self.assertEqual(
            receipt["probe"]["broadcastStrategy"],
            "tile_to_manifest_shape",
        )
        per_symbol = receipt["probe"]["perSymbolStrategy"]
        self.assertEqual(per_symbol["indices"], "tile")
        self.assertEqual(per_symbol["table"], "tile")
        self.assertEqual(
            receipt["receiptClass"], "manifest_shape_per_kernel_dispatch"
        )

    def test_absent_probe_blocks(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target, compile_root, _, host_plan_path, cs_python, adapter = (
                self._setup(tmp_path)
            )
            empty_probe_dir = tmp_path / "empty-probes"
            empty_probe_dir.mkdir()
            receipt = runner.run_one_kernel(
                kernel="embed",
                target=target,
                compile_root=compile_root,
                probe_dir=empty_probe_dir,
                host_plan_path=host_plan_path,
                host_plan_hash=_sha256_file(host_plan_path),
                out_dir=tmp_path / "out",
                cmaddr="",
                timeout_seconds=30,
                cs_python=cs_python,
                adapter=adapter,
                dry_run=False,
            )
        self.assertEqual(receipt["verdict"], "blocked")
        self.assertEqual(receipt["blocker"], "probe_fixture_absent")

    def test_stubbed_dispatch_records_wallclock(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target, compile_root, probe_dir, host_plan_path, cs_python, adapter = (
                self._setup(tmp_path)
            )

            def fake_dispatch(command, *, timeout_seconds, env=None):
                import numpy as np

                for i, token in enumerate(command):
                    if token == "--output":
                        spec = command[i + 1]
                        out_path = Path(spec.split(":")[1])
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        np.save(
                            out_path, np.zeros(8 * 32, dtype=np.float32)
                        )
                return 0, "ok\n", "", False

            original_repo_root = runner.REPO_ROOT
            runner.REPO_ROOT = tmp_path
            try:
                receipt = runner.run_one_kernel(
                    kernel="embed",
                    target=target,
                    compile_root=compile_root,
                    probe_dir=probe_dir,
                    host_plan_path=host_plan_path,
                    host_plan_hash=_sha256_file(host_plan_path),
                    out_dir=tmp_path / "out",
                    cmaddr="",
                    timeout_seconds=30,
                    cs_python=cs_python,
                    adapter=adapter,
                    dry_run=False,
                    dispatcher=fake_dispatch,
                )
            finally:
                runner.REPO_ROOT = original_repo_root
        self.assertEqual(receipt["verdict"], "bound")
        self.assertEqual(receipt["dispatchExitCode"], 0)
        self.assertGreater(receipt["dispatchWallclockNs"], 0)
        self.assertGreater(receipt["totalOutputBytes"], 0)


if __name__ == "__main__":
    unittest.main()

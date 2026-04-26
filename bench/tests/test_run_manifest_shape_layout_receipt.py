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

from bench.tools.run_manifest_shape_layout_receipt import (  # noqa: E402
    LayoutReceiptError,
    build_dispatch_command,
    build_kernel_receipt,
    classify_exports,
    run_one_kernel,
    synthesize_zero_input,
    write_kernel_receipt,
    write_summary,
)


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


class ClassifyExportsTest(unittest.TestCase):
    def test_partitions_inputs_from_outputs(self) -> None:
        exports = [
            {"symbol": "indices"},
            {"symbol": "table"},
            {"symbol": "output"},
        ]
        inputs, outputs = classify_exports(exports)
        self.assertEqual([e["symbol"] for e in inputs], ["indices", "table"])
        self.assertEqual([e["symbol"] for e in outputs], ["output"])

    def test_kv_cache_treated_as_output(self) -> None:
        exports = [
            {"symbol": "k_proj"},
            {"symbol": "key_cache"},
            {"symbol": "value_cache"},
        ]
        inputs, outputs = classify_exports(exports)
        self.assertEqual([e["symbol"] for e in inputs], ["k_proj"])
        self.assertEqual(
            [e["symbol"] for e in outputs], ["key_cache", "value_cache"]
        )


class SynthesizeZeroInputTest(unittest.TestCase):
    def test_writes_npy_with_expected_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.npy"
            byte_len = synthesize_zero_input(
                target_path=path,
                pe_count=4,
                per_pe_chunk=8,
                elem_type="f32",
            )
            self.assertTrue(path.is_file())
            import numpy as np

            arr = np.load(path)
            self.assertEqual(arr.shape, (4 * 8,))
            self.assertEqual(arr.dtype, np.float32)
            self.assertTrue((arr == 0).all())
            self.assertGreater(byte_len, 0)


class BuildKernelReceiptTest(unittest.TestCase):
    def test_bound_when_dispatch_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            host_plan = tmp_path / "host-plan.json"
            host_plan.write_text("{}", encoding="utf-8")
            receipt = build_kernel_receipt(
                kernel="embed",
                compile_dir=tmp_path / "compile/embed",
                compile_params={"width": 246, "height": 236},
                inputs=[
                    {
                        "symbol": "indices",
                        "elemType": "u32",
                        "elemBytes": 4,
                        "perPeChunk": 16,
                        "totalElements": 64,
                        "totalBytes": 256,
                        "sha256": "a" * 64,
                    }
                ],
                outputs=[
                    {
                        "symbol": "output",
                        "elemType": "f32",
                        "elemBytes": 4,
                        "perPeChunk": 22,
                        "totalElements": 100,
                        "totalBytes": 400,
                        "sha256": "b" * 64,
                    }
                ],
                dispatch_command=["cs_python", "adapter.py"],
                dispatch_exit_code=0,
                dispatch_stdout="ok",
                dispatch_stderr="",
                dispatch_timed_out=False,
                host_plan_path=host_plan,
                host_plan_hash=_sha256_file(host_plan),
                cmaddr="",
                blocker=None,
            )
        self.assertEqual(receipt["verdict"], "bound")
        self.assertEqual(receipt["dispatchExitCode"], 0)
        self.assertEqual(receipt["totalInputBytes"], 256)
        self.assertEqual(receipt["totalOutputBytes"], 400)
        self.assertEqual(receipt["bufferAlignment"], 4)
        self.assertEqual(receipt["receiptClass"], "manifest_shape_layout")
        self.assertEqual(receipt["comparisonMode"], "no_oracle")
        self.assertEqual(len(receipt["outputDigest"]), 64)

    def test_blocked_on_nonzero_exit(self) -> None:
        receipt = build_kernel_receipt(
            kernel="x",
            compile_dir=Path("/tmp/x"),
            compile_params={},
            inputs=[],
            outputs=[],
            dispatch_command=["fake"],
            dispatch_exit_code=2,
            dispatch_stdout="",
            dispatch_stderr="boom",
            dispatch_timed_out=False,
            host_plan_path=Path("/tmp/host-plan.json"),
            host_plan_hash="0" * 64,
            cmaddr="",
            blocker=None,
        )
        self.assertEqual(receipt["verdict"], "blocked")
        self.assertEqual(receipt["blocker"], "dispatch_exit_code_2")

    def test_blocked_on_timeout(self) -> None:
        receipt = build_kernel_receipt(
            kernel="x",
            compile_dir=Path("/tmp/x"),
            compile_params={},
            inputs=[],
            outputs=[],
            dispatch_command=["fake"],
            dispatch_exit_code=-1,
            dispatch_stdout="",
            dispatch_stderr="",
            dispatch_timed_out=True,
            host_plan_path=Path("/tmp/host-plan.json"),
            host_plan_hash="0" * 64,
            cmaddr="",
            blocker=None,
        )
        self.assertEqual(receipt["blocker"], "dispatch_timed_out")


class BuildDispatchCommandTest(unittest.TestCase):
    def test_passes_cmaddr_when_provided(self) -> None:
        cmd = build_dispatch_command(
            cs_python=Path("/cs_python"),
            adapter=Path("/adapter"),
            compile_dir=Path("/compile"),
            width=4,
            height=2,
            chunk_size=8,
            input_specs=["a:/in/a.npy:f32:8"],
            output_specs=["b:/out/b.npy:f32:8"],
            cmaddr="1.2.3.4:9000",
        )
        self.assertIn("--cmaddr", cmd)
        self.assertIn("1.2.3.4:9000", cmd)

    def test_omits_cmaddr_when_empty(self) -> None:
        cmd = build_dispatch_command(
            cs_python=Path("/cs_python"),
            adapter=Path("/adapter"),
            compile_dir=Path("/compile"),
            width=4,
            height=1,
            chunk_size=8,
            input_specs=[],
            output_specs=[],
            cmaddr="",
        )
        self.assertNotIn("--cmaddr", cmd)


class RunOneKernelTest(unittest.TestCase):
    def _setup(self, tmp: Path) -> tuple[dict, Path, Path, Path]:
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
        host_plan = {
            "compileTargets": [
                {
                    "name": "embed",
                    "layout": "embed/layout.csl",
                    "peProgram": "embed/pe_program.csl",
                    "compileParams": {
                        "width": 4,
                        "height": 2,
                        "tokens_per_chunk": 8,
                        "rows_per_pe": 2,
                        "hidden_per_pe": 4,
                    },
                }
            ],
        }
        host_plan_path.write_text(
            json.dumps(host_plan, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        out_dir = tmp / "out"
        # cs_python and adapter must exist for non-blocked runs.
        cs_python = tmp / "cs_python.sh"
        cs_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        cs_python.chmod(0o755)
        adapter = tmp / "adapter.py"
        adapter.write_text("# stub\n", encoding="utf-8")
        return host_plan["compileTargets"][0], compile_root, out_dir, cs_python  # type: ignore[index]

    def test_stubbed_dispatch_produces_bound_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target, compile_root, out_dir, cs_python = self._setup(tmp_path)
            host_plan_path = tmp_path / "host-plan.json"
            adapter = tmp_path / "adapter.py"

            def fake_dispatch(command, *, timeout_seconds, env=None):
                # Simulate what chain_step_adapter would do: write a
                # zero-filled output .npy at the path embedded in the
                # output spec.
                import numpy as np

                for i, token in enumerate(command):
                    if token == "--output":
                        spec = command[i + 1]
                        # spec format: symbol:path:dtype:chunk
                        parts = spec.split(":")
                        out_path = Path(parts[1])
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        # 4 (width) * 2 (height) PEs, 8*4 = 32 elems chunk
                        np.save(out_path, np.zeros(8 * 32, dtype=np.float32))
                return 0, "ok\n", "", False

            receipt = run_one_kernel(
                kernel="embed",
                target=target,
                compile_root=compile_root,
                host_plan_path=host_plan_path,
                host_plan_hash=_sha256_file(host_plan_path),
                out_dir=out_dir,
                cmaddr="",
                timeout_seconds=30,
                cs_python=cs_python,
                adapter=adapter,
                dry_run=False,
                dispatcher=fake_dispatch,
            )
        self.assertEqual(receipt["verdict"], "bound")
        self.assertEqual(receipt["dispatchExitCode"], 0)
        self.assertEqual(len(receipt["inputs"]), 2)
        self.assertEqual(len(receipt["outputs"]), 1)
        self.assertEqual(
            receipt["inputs"][0]["symbol"], "indices"
        )
        self.assertEqual(receipt["outputs"][0]["symbol"], "output")
        self.assertGreater(receipt["totalInputBytes"], 0)
        self.assertGreater(receipt["totalOutputBytes"], 0)
        self.assertEqual(receipt["bufferAlignment"], 4)

    def test_dry_run_produces_blocked_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target, compile_root, out_dir, cs_python = self._setup(tmp_path)
            host_plan_path = tmp_path / "host-plan.json"
            adapter = tmp_path / "adapter.py"
            receipt = run_one_kernel(
                kernel="embed",
                target=target,
                compile_root=compile_root,
                host_plan_path=host_plan_path,
                host_plan_hash=_sha256_file(host_plan_path),
                out_dir=out_dir,
                cmaddr="",
                timeout_seconds=30,
                cs_python=cs_python,
                adapter=adapter,
                dry_run=True,
            )
        self.assertEqual(receipt["verdict"], "blocked")
        self.assertEqual(receipt["blocker"], "dry_run")
        self.assertGreater(len(receipt["subprocess"]["command"]), 0)
        # No subprocess actually ran, so output bytes are 0.
        self.assertEqual(receipt["totalOutputBytes"], 0)

    def test_missing_cs_python_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target, compile_root, out_dir, cs_python = self._setup(tmp_path)
            host_plan_path = tmp_path / "host-plan.json"
            adapter = tmp_path / "adapter.py"
            receipt = run_one_kernel(
                kernel="embed",
                target=target,
                compile_root=compile_root,
                host_plan_path=host_plan_path,
                host_plan_hash=_sha256_file(host_plan_path),
                out_dir=out_dir,
                cmaddr="",
                timeout_seconds=30,
                cs_python=tmp_path / "no-such-cs_python",
                adapter=adapter,
                dry_run=False,
            )
        self.assertEqual(receipt["verdict"], "blocked")
        self.assertIn("cs_python_unavailable", receipt["blocker"])


class WriteReceiptHashSpineTest(unittest.TestCase):
    def test_writes_kernel_receipt_when_host_plan_hash_matches(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            host_plan_path = tmp_path / "host-plan.json"
            host_plan_path.write_text("{}", encoding="utf-8")
            host_plan_hash = _sha256_file(host_plan_path)
            receipt = build_kernel_receipt(
                kernel="x",
                compile_dir=tmp_path / "compile/x",
                compile_params={},
                inputs=[],
                outputs=[],
                dispatch_command=[],
                dispatch_exit_code=0,
                dispatch_stdout="",
                dispatch_stderr="",
                dispatch_timed_out=False,
                host_plan_path=host_plan_path,
                host_plan_hash=host_plan_hash,
                cmaddr="",
                blocker="dry_run",
            )
            # write_kernel_receipt enforces hash spine; this shouldn't
            # raise because hostPlanHash matches the file.
            out = write_kernel_receipt(
                receipt=receipt, out_dir=tmp_path / "out"
            )
            self.assertTrue(out.is_file())
            persisted = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(persisted["kernel"], "x")

    def test_summary_writes_with_matching_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            host_plan_path = tmp_path / "host-plan.json"
            host_plan_path.write_text("{}", encoding="utf-8")
            host_plan_hash = _sha256_file(host_plan_path)
            r = build_kernel_receipt(
                kernel="x",
                compile_dir=tmp_path,
                compile_params={},
                inputs=[],
                outputs=[],
                dispatch_command=[],
                dispatch_exit_code=0,
                dispatch_stdout="",
                dispatch_stderr="",
                dispatch_timed_out=False,
                host_plan_path=host_plan_path,
                host_plan_hash=host_plan_hash,
                cmaddr="",
                blocker="dry_run",
            )
            path = write_summary(
                out_dir=tmp_path / "out",
                receipts=[r],
                host_plan_path=host_plan_path,
                host_plan_hash=host_plan_hash,
            )
            self.assertTrue(path.is_file())
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                payload["artifactKind"],
                "doe_manifest_shape_layout_summary",
            )
            self.assertEqual(payload["totals"]["kernelCount"], 1)
            self.assertEqual(payload["totals"]["blockedCount"], 1)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from unittest import mock
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


def _load_chain_step_adapter_module():
    name = "chain_step_adapter_for_tests"
    if name in sys.modules:
        return sys.modules[name]
    fake = types.ModuleType("sdkruntimepybind")

    class _MemcpyDataType:
        MEMCPY_32BIT = "MEMCPY_32BIT"
        MEMCPY_16BIT = "MEMCPY_16BIT"

    class _MemcpyOrder:
        ROW_MAJOR = "ROW_MAJOR"

    class _SdkRuntime:
        pass

    fake.MemcpyDataType = _MemcpyDataType
    fake.MemcpyOrder = _MemcpyOrder
    fake.SdkRuntime = _SdkRuntime
    sys.modules.setdefault("cerebras", types.ModuleType("cerebras"))
    sys.modules.setdefault("cerebras.sdk", types.ModuleType("cerebras.sdk"))
    sys.modules.setdefault(
        "cerebras.sdk.runtime",
        types.ModuleType("cerebras.sdk.runtime"),
    )
    sys.modules["cerebras.sdk.runtime.sdkruntimepybind"] = fake
    spec = importlib.util.spec_from_file_location(
        name,
        REPO_ROOT / "bench/runners/csl-runners/chain_step_adapter.py",
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
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

    def test_declared_family_alias(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "residual.doppler-transcript.json").write_text(
                "{}", encoding="utf-8"
            )
            found = runner.find_probe_transcript(
                kernel="residual_prefill", probe_dir=tmp_path
            )
            self.assertIsNotNone(found)
            assert found is not None
            self.assertEqual(found.name, "residual.doppler-transcript.json")

    def test_absent(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self.assertIsNone(
                runner.find_probe_transcript(
                    kernel="ghost", probe_dir=tmp_path
                )
            )


class ManifestShapeProbeCoverageTest(unittest.TestCase):
    def test_claimed_manifest_shape_kernels_have_probe_inputs(self) -> None:
        runner = _load_runner_module()
        kernels = (
            "attn_decode",
            "attn_decode_sliding",
            "attn_prefill_kv_axis_sharded",
            "attn_small",
            "embed",
            "gelu",
            "gelu_decode",
            "gelu_prefill",
            "gemv",
            "kv_write",
            "kv_write_shared",
            "o_gate",
            "ple_embed",
            "ple_proj",
            "ple_residual",
            "ple_rmsnorm",
            "residual",
            "residual_decode",
            "residual_prefill",
            "rmsnorm",
            "rmsnorm_decode",
            "rmsnorm_prefill",
            "rope",
            "rope_partial",
            "sample",
            "silu_gated",
            "ssm_conv1d_depthwise",
            "ssm_l2_normalize",
            "ssm_linear_attention",
            "tiled",
        )
        for kernel in kernels:
            with self.subTest(kernel=kernel):
                transcript = runner.find_probe_transcript(
                    kernel=kernel,
                    probe_dir=runner.DEFAULT_PROBE_DIR,
                )
                self.assertIsNotNone(transcript)
                assert transcript is not None
                _, metadata = runner.load_probe_inputs(transcript)
                self.assertEqual(
                    metadata["broadcastStrategy"],
                    "tile_to_manifest_shape",
                )
                self.assertIsNotNone(metadata["inputFixtureHash"])


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

    def test_f16_materializes_native_half(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.npy"
            byte_len, strategy = runner.materialize_probe_input(
                target_path=path,
                pe_count=2,
                per_pe_chunk=4,
                elem_type="f16",
                probe_values=[1.0, 2.0],
            )
            self.assertEqual(strategy, "tile")
            import numpy as np
            arr = np.load(path)
            self.assertEqual(arr.dtype, np.float16)
            self.assertEqual(arr.shape, (8,))
            self.assertTrue((arr[::2] == np.float16(1.0)).all())
            self.assertTrue((arr[1::2] == np.float16(2.0)).all())
            # 2 bytes per element × 8 elements
            self.assertEqual(byte_len, path.stat().st_size)

    def test_u8_materializes_native_byte_array(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.npy"
            byte_len, strategy = runner.materialize_probe_input(
                target_path=path,
                pe_count=1,
                per_pe_chunk=8,
                elem_type="u8",
                probe_values=[16, 32, 48, 64],
            )
            self.assertEqual(strategy, "tile")
            import numpy as np
            arr = np.load(path)
            self.assertEqual(arr.dtype, np.uint8)
            self.assertEqual(arr.tolist(), [16, 32, 48, 64, 16, 32, 48, 64])
            self.assertEqual(byte_len, path.stat().st_size)

    def test_lm_head_probe_uses_explicit_zero_default_h2d_inputs(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            scratch = Path(tmp) / "scratch"
            inputs, outputs, input_specs, output_specs, _, strategies = (
                runner._materialize_inputs(
                    kernel="lm_head_prefill_stable",
                    target={"compileParams": {"width": 2, "height": 2}},
                    metadata={
                        "exports": [
                            {
                                "symbol": "activation",
                                "elemType": "f16",
                                "sizeExpr": "8",
                            },
                            {
                                "symbol": "weight",
                                "elemType": "u8",
                                "sizeExpr": "16",
                            },
                            {
                                "symbol": "c",
                                "elemType": "f16",
                                "sizeExpr": "8",
                            },
                        ]
                    },
                    probe_inputs={},
                    scratch_dir=scratch,
                )
            )
        self.assertEqual(len(input_specs), 2)
        self.assertEqual(len(output_specs), 1)
        self.assertEqual(strategies["activation"], "zero_default_h2d")
        self.assertEqual(strategies["weight"], "zero_default_h2d")
        records_by_symbol = {record["symbol"]: record for record in inputs}
        self.assertIsNotNone(records_by_symbol["activation"]["path"])
        self.assertIsNotNone(records_by_symbol["weight"]["path"])
        self.assertEqual(records_by_symbol["activation"]["totalBytes"], 64)
        self.assertEqual(records_by_symbol["weight"]["totalBytes"], 64)
        self.assertEqual(outputs[0]["symbol"], "c")


class AdapterDtypeTokenTest(unittest.TestCase):
    def test_f32_passthrough(self) -> None:
        runner = _load_runner_module()
        self.assertEqual(runner._adapter_dtype_token("f32"), "f32")

    def test_u32_passthrough(self) -> None:
        runner = _load_runner_module()
        self.assertEqual(runner._adapter_dtype_token("u32"), "u32")

    def test_i32_remaps_to_u32(self) -> None:
        runner = _load_runner_module()
        self.assertEqual(runner._adapter_dtype_token("i32"), "u32")

    def test_f16_passthrough(self) -> None:
        runner = _load_runner_module()
        self.assertEqual(runner._adapter_dtype_token("f16"), "f16")

    def test_u8_passthrough(self) -> None:
        runner = _load_runner_module()
        self.assertEqual(runner._adapter_dtype_token("u8"), "u8")

    def test_unsupported_dtype_raises_with_wired_set(self) -> None:
        runner = _load_runner_module()
        with self.assertRaises(runner.LayoutReceiptError) as ctx:
            runner._adapter_dtype_token("i8")
        msg = str(ctx.exception)
        self.assertIn("i8", msg)
        self.assertIn("f32", msg)
        self.assertIn("u32", msg)
        self.assertIn("f16", msg)
        self.assertIn("u8", msg)


class ChainStepAdapterMemcpyPackingTest(unittest.TestCase):
    def test_parse_args_allows_device_default_inputs(self) -> None:
        adapter = _load_chain_step_adapter_module()
        with mock.patch.object(
            sys,
            "argv",
            [
                "chain_step_adapter.py",
                "--compile-dir",
                "compiled/lm_head",
                "--width",
                "2",
                "--chunk-size",
                "4",
                "--output",
                "output:/tmp/output.npy:f32:4",
            ],
        ):
            args = adapter.parse_args()
        self.assertEqual(args.input, [])
        self.assertEqual(args.output, ["output:/tmp/output.npy:f32:4"])

    def test_f16_h2d_uses_32bit_packed_payload(self) -> None:
        adapter = _load_chain_step_adapter_module()
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.npy"
            source = np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float16)
            np.save(path, source)
            payload, memcpy_dtype, memcpy_chunk = adapter._memcpy_payload_for_h2d(
                path=str(path),
                dtype="f16",
                chunk_size=2,
                pe_count=2,
            )
        self.assertEqual(payload.dtype, np.uint32)
        self.assertEqual(
            memcpy_dtype,
            adapter.MemcpyDataType.MEMCPY_32BIT,
        )
        self.assertEqual(memcpy_chunk, 1)
        self.assertEqual(payload.view(np.float16).tolist(), source.tolist())

    def test_f16_d2h_uses_32bit_buffer_with_f16_output_dtype(self) -> None:
        adapter = _load_chain_step_adapter_module()
        import numpy as np

        buffer, memcpy_dtype, memcpy_chunk, output_dtype = (
            adapter._memcpy_buffer_for_d2h(
                dtype="f16",
                chunk_size=2,
                pe_count=2,
            )
        )
        self.assertEqual(buffer.dtype, np.uint32)
        self.assertEqual(
            memcpy_dtype,
            adapter.MemcpyDataType.MEMCPY_32BIT,
        )
        self.assertEqual(memcpy_chunk, 1)
        self.assertEqual(output_dtype, np.dtype(np.float16))

    def test_f16_rejects_odd_per_pe_chunk(self) -> None:
        adapter = _load_chain_step_adapter_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.npy"
            import numpy as np

            np.save(path, np.array([1.0, 2.0, 3.0], dtype=np.float16))
            with self.assertRaises(ValueError):
                adapter._memcpy_payload_for_h2d(
                    path=str(path),
                    dtype="f16",
                    chunk_size=3,
                    pe_count=1,
                )

    def test_save_outputs_persists_before_shutdown_boundary(self) -> None:
        adapter = _load_chain_step_adapter_module()
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out" / "x.npy"
            adapter._save_outputs(
                [("x", str(path), np.array([1.0, 2.0], dtype=np.float32))]
            )
            saved = np.load(path)
        self.assertEqual(saved.dtype, np.float32)
        self.assertEqual(saved.tolist(), [1.0, 2.0])


class CompileBindingsTest(unittest.TestCase):
    def test_merges_layout_defaults_metadata_constants_and_grid(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            compile_dir = tmp_path / "compiled" / "rope"
            bin_dir = compile_dir / "bin"
            bin_dir.mkdir(parents=True)
            for x in range(3):
                (bin_dir / f"out_{x}_0.elf").write_bytes(b"\x7fELF")
            layout = tmp_path / "source" / "rope" / "layout.csl"
            layout.parent.mkdir(parents=True)
            layout.write_text(
                "param width: i16;\n"
                "param head_dim: i16 = 128;\n"
                "param num_pairs: i16 = 64;\n",
                encoding="utf-8",
            )
            metadata = {
                "compileTimeConstants": [
                    {
                        "kind": "const",
                        "name": "local",
                        "type": "u32",
                        "expr": "@as(u32, head_dim) * 2",
                    }
                ]
            }
            bindings = runner._compile_bindings(
                target={"compileParams": {}},
                metadata=metadata,
                compile_dir=compile_dir,
                layout_path=layout,
            )
            self.assertEqual(bindings["width"], 3)
            self.assertEqual(bindings["height"], 1)
            self.assertEqual(bindings["head_dim"], 128)
            self.assertEqual(bindings["num_pairs"], 64)
            self.assertEqual(bindings["local"], 256)


class SchedulingAndResumeTest(unittest.TestCase):
    def test_heavy_first_orders_by_estimated_io(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            compile_root = tmp_path / "compiled"
            source_root = tmp_path / "source"
            _make_kernel_dir(
                source_root,
                name="small",
                exports=[
                    {
                        "symbol": "input",
                        "elemType": "f32",
                        "sizeExpr": "1",
                    },
                    {
                        "symbol": "output",
                        "elemType": "f32",
                        "sizeExpr": "1",
                    },
                ],
            )
            _make_kernel_dir(
                source_root,
                name="large",
                exports=[
                    {
                        "symbol": "input",
                        "elemType": "f32",
                        "sizeExpr": "1024",
                    },
                    {
                        "symbol": "output",
                        "elemType": "f32",
                        "sizeExpr": "1024",
                    },
                ],
            )
            (compile_root / "small").mkdir(parents=True)
            (compile_root / "large").mkdir(parents=True)
            targets = [
                {"name": "small", "compileParams": {"width": 1, "height": 1}},
                {"name": "large", "compileParams": {"width": 1, "height": 1}},
            ]
            ordered = runner.order_targets(
                targets=targets,
                schedule="heavy-first",
                compile_root=compile_root,
                source_root=source_root,
            )
            self.assertEqual([t["name"] for t in ordered], ["large", "small"])

    def test_resume_reuses_bound_and_timeouts_not_dispatch_exit(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            base = {
                "kernel": "embed",
                "hostPlanHash": "abc",
                "verdict": "blocked",
                "blocker": "dry_run",
                "dispatchExitCode": None,
                "dispatchTimedOut": False,
                "dispatchWallclockNs": None,
            }
            (out_dir / "embed.json").write_text(
                json.dumps(base, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            self.assertIsNone(
                runner.load_reusable_receipt(
                    kernel="embed",
                    out_dir=out_dir,
                    host_plan_hash="abc",
                    dry_run=False,
                )
            )
            real = dict(base)
            real["blocker"] = "dispatch_exit_code_1"
            real["dispatchExitCode"] = 1
            (out_dir / "embed.json").write_text(
                json.dumps(real, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            self.assertIsNone(
                runner.load_reusable_receipt(
                    kernel="embed",
                    out_dir=out_dir,
                    host_plan_hash="abc",
                    dry_run=False,
                )
            )
            timed_out = dict(base)
            timed_out["blocker"] = "dispatch_timed_out"
            timed_out["dispatchExitCode"] = -1
            timed_out["dispatchTimedOut"] = True
            (out_dir / "embed.json").write_text(
                json.dumps(timed_out, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            reused = runner.load_reusable_receipt(
                kernel="embed",
                out_dir=out_dir,
                host_plan_hash="abc",
                dry_run=False,
            )
            self.assertIsNotNone(reused)
            assert reused is not None
            self.assertTrue(reused["dispatchTimedOut"])

    def test_resume_can_preserve_blocked_dispatch_exit_when_requested(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            receipt = {
                "kernel": "embed",
                "hostPlanHash": "abc",
                "verdict": "blocked",
                "blocker": "dispatch_exit_code_1",
                "dispatchExitCode": 1,
                "dispatchTimedOut": False,
                "dispatchWallclockNs": 100,
            }
            (out_dir / "embed.json").write_text(
                json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            reused = runner.load_reusable_receipt(
                kernel="embed",
                out_dir=out_dir,
                host_plan_hash="abc",
                dry_run=False,
                reuse_blocked=True,
            )
            self.assertIsNotNone(reused)
            assert reused is not None
            self.assertEqual(reused["blocker"], "dispatch_exit_code_1")


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

    def test_rope_in_place_input_is_read_back_as_output(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            compile_root = tmp_path / "compile"
            compile_root.mkdir(parents=True)
            _make_kernel_dir(
                compile_root,
                name="rope",
                exports=[
                    {
                        "symbol": "input",
                        "elemType": "f16",
                        "sizeExpr": "head_dim",
                    },
                    {
                        "symbol": "cos_table",
                        "elemType": "f16",
                        "sizeExpr": "num_pairs",
                    },
                    {
                        "symbol": "sin_table",
                        "elemType": "f16",
                        "sizeExpr": "num_pairs",
                    },
                ],
            )
            host_plan_path = tmp_path / "host-plan.json"
            host_plan_path.write_text(
                json.dumps(
                    {
                        "compileTargets": [
                            {
                                "name": "rope",
                                "compileParams": {
                                    "width": 1,
                                    "height": 1,
                                    "head_dim": 4,
                                    "num_pairs": 2,
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
            probe_dir = tmp_path / "probes"
            input_fixture = tmp_path / "inputs/rope.json"
            _write_probe(
                probe_dir=probe_dir,
                kernel="rope",
                input_fixture_rel=str(input_fixture.relative_to(tmp_path)),
                fixture_path=input_fixture,
                inputs={
                    "input": [1.0, 2.0, 3.0, 4.0],
                    "cos_table": [1.0, 1.0],
                    "sin_table": [0.0, 0.0],
                },
            )
            cs_python = tmp_path / "cs_python.sh"
            cs_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            cs_python.chmod(0o755)
            adapter = tmp_path / "adapter.py"
            adapter.write_text("# stub\n", encoding="utf-8")
            target = json.loads(host_plan_path.read_text(encoding="utf-8"))[
                "compileTargets"
            ][0]
            original_repo_root = runner.REPO_ROOT
            runner.REPO_ROOT = tmp_path
            try:
                receipt = runner.run_one_kernel(
                    kernel="rope",
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
        self.assertEqual(receipt["blocker"], "dry_run")
        self.assertEqual([item["symbol"] for item in receipt["outputs"]], ["input"])
        command = receipt["subprocess"]["command"]
        self.assertIn("--input", command)
        self.assertIn("--output", command)
        input_specs = [
            command[i + 1]
            for i, token in enumerate(command)
            if token == "--input"
        ]
        self.assertTrue(any(spec.startswith("input:") for spec in input_specs))
        output_specs = [
            command[i + 1]
            for i, token in enumerate(command)
            if token == "--output"
        ]
        self.assertEqual(len(output_specs), 1)
        self.assertTrue(output_specs[0].startswith("input:"))


if __name__ == "__main__":
    unittest.main()

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


def _tile_compile_param_digest(
    *,
    source_digest: str,
    width: int,
    tile_height: int,
    out_dim_per_pe: int,
    in_dim_per_pe: int,
) -> str:
    import manifest_dense_gemv_tiles as tiles

    return tiles._compile_param_digest(
        source_digest=source_digest,
        width=width,
        tile_height=tile_height,
        out_dim_per_pe=out_dim_per_pe,
        in_dim_per_pe=in_dim_per_pe,
    )


def _write_tile_compile_receipt(
    *,
    tile_dir: Path,
    source_digest: str,
    width: int,
    tile_height: int,
    out_dim_per_pe: int,
    in_dim_per_pe: int,
    layout_path: Path | None = None,
) -> None:
    import manifest_dense_gemv_tiles as tiles

    command_digest = None
    cslc = tiles.discover_cslc(None)
    if cslc is not None and layout_path is not None:
        command_digest = tiles._stable_digest(
            tiles._compile_command(
                cslc=cslc,
                layout_path=layout_path,
                output_dir=tile_dir,
                width=width,
                height=tile_height,
                out_dim_per_pe=out_dim_per_pe,
                in_dim_per_pe=in_dim_per_pe,
            )
        )
    receipt = {
        "compileParamDigest": _tile_compile_param_digest(
            source_digest=source_digest,
            width=width,
            tile_height=tile_height,
            out_dim_per_pe=out_dim_per_pe,
            in_dim_per_pe=in_dim_per_pe,
        ),
        "inDimPerPe": in_dim_per_pe,
        "outDimPerPe": out_dim_per_pe,
        "sourceDigest": source_digest,
        "tileHeight": tile_height,
        "verdict": "bound",
        "width": width,
    }
    if command_digest is not None:
        receipt["commandDigest"] = command_digest
    (tile_dir / "dense-gemv-tile-compile.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


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

    def test_lm_head_prefill_output_uses_dense_gemv_sink_column_region(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            scratch = Path(tmp) / "scratch"
            _, outputs, _, output_specs, _, _ = runner._materialize_inputs(
                kernel="lm_head_prefill_stable",
                target={
                    "compileParams": {
                        "width": 4,
                        "height": 3,
                        "out_dim": 24,
                        "out_dim_per_pe": 8,
                        "in_dim_per_pe": 2,
                    }
                },
                metadata={
                    "exports": [
                        {
                            "symbol": "activation",
                            "elemType": "f16",
                            "sizeExpr": "in_dim_per_pe",
                        },
                        {
                            "symbol": "weight",
                            "elemType": "f16",
                            "sizeExpr": "out_dim_per_pe * in_dim_per_pe",
                        },
                        {
                            "symbol": "output",
                            "elemType": "f32",
                            "sizeExpr": "out_dim_per_pe",
                        },
                    ]
                },
                probe_inputs={},
                scratch_dir=scratch,
            )
        self.assertEqual(outputs[0]["deviceRegion"], {
            "x": 3,
            "y": 0,
            "width": 1,
            "height": 3,
        })
        self.assertEqual(outputs[0]["outputScope"], "dense_gemv_sink_column")
        self.assertEqual(outputs[0]["deviceTotalElements"], 96)
        self.assertEqual(outputs[0]["totalElements"], 24)
        self.assertTrue(output_specs[0].endswith(":3,0,1,3"))
        self.assertEqual(
            runner._d2h_mode_for_outputs(
                kernel="lm_head_prefill_stable",
                output_records=outputs,
            ),
            "row_split_copyback",
        )


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

    def test_parse_io_spec_accepts_output_region(self) -> None:
        adapter = _load_chain_step_adapter_module()
        parsed = adapter.parse_io_spec("output:/tmp/output.npy:f32:4:3,0,1,2")
        self.assertEqual(parsed[0], "output")
        self.assertEqual(parsed[1], "/tmp/output.npy")
        self.assertEqual(parsed[2], "f32")
        self.assertEqual(parsed[3], 4)
        self.assertEqual(parsed[4], (3, 0, 1, 2))

    def test_region_validation_rejects_outside_grid(self) -> None:
        adapter = _load_chain_step_adapter_module()
        with self.assertRaises(ValueError):
            adapter._validate_region(region=(3, 0, 2, 1), width=4, height=1)

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

    def test_f16_h2d_uses_mmap_backed_payload_when_layout_matches(self) -> None:
        adapter = _load_chain_step_adapter_module()
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.npy"
            source = np.lib.format.open_memmap(
                path,
                mode="w+",
                dtype=np.float16,
                shape=(4,),
            )
            source[:] = [1.0, 2.0, 3.0, 4.0]
            source.flush()
            del source
            payload, _, _ = adapter._memcpy_payload_for_h2d(
                path=str(path),
                dtype="f16",
                chunk_size=2,
                pe_count=2,
            )
        self.assertIsInstance(payload, np.memmap)
        self.assertEqual(payload.dtype, np.uint32)
        self.assertTrue(payload.flags.writeable)
        self.assertEqual(payload.view(np.float16).tolist(), [1.0, 2.0, 3.0, 4.0])

    def test_f16_h2d_copies_read_only_payload(self) -> None:
        adapter = _load_chain_step_adapter_module()
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.npy"
            np.save(path, np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float16))
            with mock.patch.object(
                adapter,
                "_load_writeable_mmap_or_copy",
                return_value=np.load(path, mmap_mode="r").ravel(),
            ):
                payload, _, _ = adapter._memcpy_payload_for_h2d(
                    path=str(path),
                    dtype="f16",
                    chunk_size=2,
                    pe_count=2,
                )
        self.assertEqual(payload.dtype, np.uint32)
        self.assertTrue(payload.flags.writeable)
        self.assertEqual(payload.view(np.float16).tolist(), [1.0, 2.0, 3.0, 4.0])

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

    def test_split_d2h_rows_concatenates_row_major_output(self) -> None:
        adapter = _load_chain_step_adapter_module()
        import numpy as np

        class FakeRunner:
            def get_id(self, symbol):
                return symbol

            def memcpy_d2h(
                self,
                arr,
                sym_id,
                x,
                y,
                width,
                height,
                chunk,
                **kwargs,
            ):
                arr[:] = np.arange(arr.size, dtype=arr.dtype) + y * 10

        with mock.patch.object(adapter, "_phase"):
            symbol, path, arr = adapter._copy_d2h_output(
                runner=FakeRunner(),
                symbol="output",
                path="/tmp/out.npy",
                dtype="f32",
                chunk_size=2,
                region=(3, 5, 1, 3),
                split_rows=True,
            )
        self.assertEqual(symbol, "output")
        self.assertEqual(path, "/tmp/out.npy")
        self.assertEqual(arr.tolist(), [50.0, 51.0, 60.0, 61.0, 70.0, 71.0])


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
    def test_lm_head_tiling_is_not_default_refresh_path(self) -> None:
        runner = _load_runner_module()
        with mock.patch.object(sys, "argv", ["manifest_kernel_probe_runner.py"]):
            args = runner.parse_args()
        self.assertEqual(args.dense_gemv_tile_height, 0)
        self.assertIsNone(args.dense_gemv_hidden_tile_width)
        self.assertFalse(args.dense_gemv_allow_unsafe_tile_shapes)
        self.assertFalse(args.dense_gemv_reuse_verified_tile_partials)
        self.assertEqual(args.dense_gemv_tile_dispatch_budget, 0)
        self.assertEqual(args.dense_gemv_tile_dispatch_jobs, 1)
        self.assertFalse(args.dense_gemv_batch_runtime)
        self.assertEqual(args.dense_gemv_max_row_tile_height, 1)

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

    def test_resume_reuses_bound_not_blocked_or_timeout_by_default(self) -> None:
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
            self.assertIsNone(
                runner.load_reusable_receipt(
                    kernel="embed",
                    out_dir=out_dir,
                    host_plan_hash="abc",
                    dry_run=False,
                )
            )

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

    def test_lm_head_timeout_records_d2h_wedge_when_phase_reaches_copyback(self) -> None:
        runner = _load_runner_module()
        receipt = runner.build_kernel_receipt(
            kernel="lm_head_prefill_stable",
            compile_dir=Path("/tmp/compile/lm_head_prefill_stable"),
            compile_params={"width": 4, "height": 3},
            inputs=[
                {
                    "symbol": "activation",
                    "totalBytes": 48,
                },
                {
                    "symbol": "weight",
                    "totalBytes": 384,
                },
            ],
            outputs=[
                {
                    "symbol": "output",
                    "totalBytes": 0,
                    "sha256": "",
                },
            ],
            probe={},
            dispatch_command=[],
            dispatch_exit_code=-1,
            dispatch_stdout=(
                "phase:load_complete\n"
                "phase:run_complete\n"
                "phase:launch_complete function=compute\n"
                "phase:memcpy_d2h_start chunk=4 symbol=output words=12\n"
            ),
            dispatch_stderr="",
            dispatch_timed_out=True,
            dispatch_wallclock_ns=123,
            host_plan_path=Path("/tmp/host-plan.json"),
            host_plan_hash="abc",
            cmaddr="",
            blocker=None,
        )

        self.assertEqual(receipt["verdict"], "blocked")
        self.assertEqual(
            receipt["blocker"],
            "sdk_d2h_output_transfer_wedged",
        )
        self.assertEqual(receipt["lastPhaseReached"], "memcpy_d2h_start")
        self.assertEqual(receipt["failurePhase"], "memcpy_d2h_start")
        self.assertTrue(
            receipt["dispatchTimeoutEvidence"]["launchCompleted"],
        )

    def test_lm_head_timeout_records_residency_before_launch_complete(self) -> None:
        runner = _load_runner_module()
        receipt = runner.build_kernel_receipt(
            kernel="lm_head_prefill_stable",
            compile_dir=Path("/tmp/compile/lm_head_prefill_stable"),
            compile_params={"width": 4, "height": 3},
            inputs=[
                {
                    "symbol": "weight",
                    "totalBytes": 384,
                },
            ],
            outputs=[
                {
                    "symbol": "output",
                    "totalBytes": 0,
                    "sha256": "",
                },
            ],
            probe={},
            dispatch_command=[],
            dispatch_exit_code=-1,
            dispatch_stdout="phase:run_complete\nphase:launch_start function=compute\n",
            dispatch_stderr="",
            dispatch_timed_out=True,
            dispatch_wallclock_ns=123,
            host_plan_path=Path("/tmp/host-plan.json"),
            host_plan_hash="abc",
            cmaddr="",
            blocker=None,
        )

        self.assertEqual(receipt["verdict"], "blocked")
        self.assertEqual(
            receipt["blocker"],
            "launch_payload_weight_residency_missing",
        )


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

    def test_lm_head_dispatch_uses_row_tiled_aggregate(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            compile_root = tmp_path / "compile"
            kernel_dir = compile_root / "lm_head_prefill_stable"
            kernel_dir.mkdir(parents=True)
            metadata = {
                "exports": [
                    {
                        "symbol": "activation",
                        "elemType": "f16",
                        "sizeExpr": "in_dim_per_pe",
                    },
                    {
                        "symbol": "weight",
                        "elemType": "f16",
                        "sizeExpr": "out_dim_per_pe * in_dim_per_pe",
                    },
                    {
                        "symbol": "output",
                        "elemType": "f32",
                        "sizeExpr": "out_dim_per_pe",
                    },
                ]
            }
            (kernel_dir / "pe_program.metadata.json").write_text(
                json.dumps(metadata, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            layout = kernel_dir / "layout.csl"
            pe = kernel_dir / "pe_program.csl"
            layout.write_text("// layout\n", encoding="utf-8")
            pe.write_text("// pe\n", encoding="utf-8")
            (kernel_dir / "bin").mkdir()
            (kernel_dir / "bin" / "out_2_1.elf").write_bytes(b"\x7fELF")
            tile_dir = compile_root / "lm_head_prefill_stable_row_tile_h1"
            (tile_dir / "bin").mkdir(parents=True)
            source_digest = hashlib.sha256()
            source_digest.update(_sha256_file(layout).encode("ascii"))
            source_digest.update(_sha256_file(pe).encode("ascii"))
            _write_tile_compile_receipt(
                tile_dir=tile_dir,
                source_digest=source_digest.hexdigest(),
                width=3,
                tile_height=1,
                out_dim_per_pe=4,
                in_dim_per_pe=2,
                layout_path=layout,
            )
            host_plan_path = tmp_path / "host-plan.json"
            host_plan_path.write_text(
                json.dumps(
                    {
                        "compileTargets": [
                            {
                                "name": "lm_head_prefill_stable",
                                "compileParams": {
                                    "width": 3,
                                    "height": 2,
                                    "out_dim": 8,
                                    "out_dim_per_pe": 4,
                                    "in_dim_per_pe": 2,
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
            input_fixture = tmp_path / "inputs/lm_head.json"
            _write_probe(
                probe_dir=probe_dir,
                kernel="lm_head_prefill_stable",
                input_fixture_rel=str(input_fixture.relative_to(tmp_path)),
                fixture_path=input_fixture,
                inputs={
                    "activation": [1.0, 2.0],
                    "weight": [0.5, 1.5],
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

            def fake_dispatch(command, *, timeout_seconds):
                import numpy as np

                for i, token in enumerate(command):
                    if token != "--output":
                        continue
                    spec = command[i + 1]
                    parts = spec.split(":")
                    out_path = Path(parts[1])
                    chunk = int(parts[3])
                    region_height = int(parts[4].split(",")[3])
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    np.save(
                        out_path,
                        np.arange(chunk * region_height, dtype=np.float32),
                    )
                return 0, "ok\n", "", False

            original_repo_root = runner.REPO_ROOT
            runner.REPO_ROOT = tmp_path
            try:
                receipt = runner.run_one_kernel(
                    kernel="lm_head_prefill_stable",
                    target=target,
                    compile_root=compile_root,
                    source_root=compile_root,
                    probe_dir=probe_dir,
                    host_plan_path=host_plan_path,
                    host_plan_hash=_sha256_file(host_plan_path),
                    out_dir=tmp_path / "out",
                    cmaddr="",
                    timeout_seconds=30,
                    cs_python=cs_python,
                    adapter=adapter,
                    dry_run=False,
                    cslc=None,
                    dense_gemv_tile_height=1,
                    dispatcher=fake_dispatch,
                )
            finally:
                runner.REPO_ROOT = original_repo_root
        self.assertEqual(receipt["verdict"], "bound")
        self.assertEqual(receipt["dispatchMode"], "dense_gemv_row_tiled")
        self.assertEqual(len(receipt["tileDispatches"]), 2)
        self.assertTrue(receipt["tileCoverage"]["covered"])
        self.assertEqual(receipt["outputs"][0]["aggregatedElements"], 8)
        self.assertGreater(receipt["totalOutputBytes"], 0)

    def test_lm_head_hidden_width_tiling_aggregates_partials(self) -> None:
        runner = _load_runner_module()
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            kernel = "lm_head_prefill_stable"
            source_root = tmp_path / "compile"
            kernel_dir = source_root / kernel
            kernel_dir.mkdir(parents=True)
            layout = kernel_dir / "layout.csl"
            pe = kernel_dir / "pe_program.csl"
            layout.write_text("// layout\n", encoding="utf-8")
            pe.write_text("// pe\n", encoding="utf-8")
            source_digest = hashlib.sha256()
            source_digest.update(_sha256_file(layout).encode("ascii"))
            source_digest.update(_sha256_file(pe).encode("ascii"))
            for width in (3, 2):
                tile_dir = source_root / f"{kernel}_row_tile_w{width}_h2"
                (tile_dir / "bin").mkdir(parents=True)
                _write_tile_compile_receipt(
                    tile_dir=tile_dir,
                    source_digest=source_digest.hexdigest(),
                    width=width,
                    tile_height=2,
                    out_dim_per_pe=4,
                    in_dim_per_pe=2,
                    layout_path=layout,
                )
            full_dir = tmp_path / "scratch" / "in"
            full_dir.mkdir(parents=True)
            activation = full_dir / "activation.npy"
            weight = full_dir / "weight.npy"
            np.save(activation, np.zeros(2 * 5 * 2, dtype=np.float16))
            np.save(weight, np.zeros(2 * 5 * 8, dtype=np.float16))
            output = tmp_path / "scratch" / "out" / "output.npy"

            def fake_dispatch(command, *, timeout_seconds):
                for i, token in enumerate(command):
                    if token != "--output":
                        continue
                    parts = command[i + 1].split(":")
                    out_path = Path(parts[1])
                    chunk = int(parts[3])
                    region_height = int(parts[4].split(",")[3])
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    np.save(
                        out_path,
                        np.ones(chunk * region_height, dtype=np.float32),
                    )
                return 0, "ok\n", "", False

            result = runner.run_dense_gemv_row_tiled(
                kernel=kernel,
                compile_root=source_root,
                source_root=source_root,
                compile_params={
                    "width": 5,
                    "height": 2,
                    "out_dim": 8,
                    "out_dim_per_pe": 4,
                    "in_dim_per_pe": 2,
                },
                input_records=[
                    {
                        "symbol": "activation",
                        "path": str(activation),
                        "absolutePath": str(activation),
                        "elemType": "f16",
                        "perPeChunk": 2,
                        "sha256": _sha256_file(activation),
                        "totalBytes": activation.stat().st_size,
                    },
                    {
                        "symbol": "weight",
                        "path": str(weight),
                        "absolutePath": str(weight),
                        "elemType": "f16",
                        "perPeChunk": 8,
                        "sha256": _sha256_file(weight),
                        "totalBytes": weight.stat().st_size,
                    },
                ],
                output_records=[
                    {
                        "symbol": "output",
                        "path": str(output),
                        "absolutePath": str(output),
                        "elemType": "f32",
                        "perPeChunk": 4,
                        "totalElements": 8,
                        "totalBytes": 0,
                        "sha256": "",
                    }
                ],
                scratch_dir=tmp_path / "scratch",
                cs_python=tmp_path / "cs_python",
                adapter=tmp_path / "adapter.py",
                cmaddr="",
                timeout_seconds=30,
                repo_root=tmp_path,
                cslc=None,
                hidden_tile_width=3,
                max_row_tile_height=2,
                dispatcher=fake_dispatch,
            )
            output_values = np.load(output).tolist()
        assert result is not None
        self.assertEqual(result.blocker, None)
        self.assertEqual(result.dispatch_mode, "dense_gemv_width_tiled")
        self.assertEqual(len(result.tile_dispatches), 2)
        assert result.tile_coverage is not None
        self.assertTrue(result.tile_coverage["covered"])
        self.assertEqual(
            result.output_records[0]["hostReduction"]["kind"],
            "sum_hidden_width_tiles",
        )
        self.assertEqual(result.weight_input_scope, "hidden_width_slice")
        self.assertEqual(result.weight_residency_mode, "per_tile_h2d_sliced")
        self.assertEqual(output_values, [2.0] * 8)

    def test_width_tiling_can_dispatch_independent_subprocesses(self) -> None:
        runner = _load_runner_module()
        import manifest_dense_gemv_tiles as tiles
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            kernel = "lm_head_prefill_stable"
            source_root = tmp_path / "source"
            kernel_dir = source_root / kernel
            kernel_dir.mkdir(parents=True)
            layout = kernel_dir / "layout.csl"
            pe = kernel_dir / "pe_program.csl"
            layout.write_text("// layout\n", encoding="utf-8")
            pe.write_text("// pe\n", encoding="utf-8")
            source_digest = hashlib.sha256()
            source_digest.update(_sha256_file(layout).encode("ascii"))
            source_digest.update(_sha256_file(pe).encode("ascii"))
            for width in (3, 2):
                tile_dir = source_root / f"{kernel}_row_tile_w{width}_h2"
                (tile_dir / "bin").mkdir(parents=True)
                _write_tile_compile_receipt(
                    tile_dir=tile_dir,
                    source_digest=source_digest.hexdigest(),
                    width=width,
                    tile_height=2,
                    out_dim_per_pe=4,
                    in_dim_per_pe=2,
                    layout_path=layout,
                )
            full_dir = tmp_path / "scratch" / "in"
            full_dir.mkdir(parents=True)
            activation = full_dir / "activation.npy"
            weight = full_dir / "weight.npy"
            np.save(activation, np.zeros(2 * 5 * 2, dtype=np.float16))
            np.save(weight, np.zeros(2 * 5 * 8, dtype=np.float16))
            output = tmp_path / "scratch" / "out" / "output.npy"
            commands_seen: list[list[str]] = []

            def fake_run(command, *, timeout_seconds, cwd=None):
                commands_seen.append(command)
                for i, token in enumerate(command):
                    if token != "--output":
                        continue
                    parts = command[i + 1].split(":")
                    out_path = Path(parts[1])
                    chunk = int(parts[3])
                    region_height = int(parts[4].split(",")[3])
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    np.save(
                        out_path,
                        np.ones(chunk * region_height, dtype=np.float32),
                    )
                return 0, "phase:launch_complete\n", "", False

            with mock.patch.object(tiles, "_run_command", side_effect=fake_run):
                result = runner.run_dense_gemv_row_tiled(
                    kernel=kernel,
                    compile_root=source_root,
                    source_root=source_root,
                    compile_params={
                        "width": 5,
                        "height": 2,
                        "out_dim": 8,
                        "out_dim_per_pe": 4,
                        "in_dim_per_pe": 2,
                    },
                    input_records=[
                        {
                            "symbol": "activation",
                            "path": str(activation),
                            "absolutePath": str(activation),
                            "elemType": "f16",
                            "perPeChunk": 2,
                            "sha256": _sha256_file(activation),
                            "totalBytes": activation.stat().st_size,
                        },
                        {
                            "symbol": "weight",
                            "path": str(weight),
                            "absolutePath": str(weight),
                            "elemType": "f16",
                            "perPeChunk": 8,
                            "sha256": _sha256_file(weight),
                            "totalBytes": weight.stat().st_size,
                        },
                    ],
                    output_records=[
                        {
                            "symbol": "output",
                            "path": str(output),
                            "absolutePath": str(output),
                            "elemType": "f32",
                            "perPeChunk": 4,
                            "totalElements": 8,
                            "totalBytes": 0,
                            "sha256": "",
                        }
                    ],
                    scratch_dir=tmp_path / "scratch",
                    cs_python=tmp_path / "cs_python",
                    adapter=tmp_path / "adapter.py",
                    cmaddr="",
                    timeout_seconds=30,
                    repo_root=tmp_path,
                    cslc=None,
                    hidden_tile_width=3,
                    tile_dispatch_jobs=2,
                    max_row_tile_height=2,
                )
            output_values = np.load(output).tolist()

        assert result is not None
        assert result.tile_coverage is not None
        self.assertIsNone(result.blocker)
        self.assertEqual(len(commands_seen), 2)
        self.assertEqual(result.tile_coverage["tileDispatchJobs"], 2)
        self.assertEqual(result.tile_compile["tileDispatchJobs"], 2)
        self.assertTrue(
            all(
                t["executionMode"] == "independent_subprocess"
                for t in result.tile_dispatches
            )
        )
        self.assertEqual(output_values, [2.0] * 8)

    def test_hidden_width_tiling_reuses_verified_partials_only(self) -> None:
        runner = _load_runner_module()
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            kernel = "lm_head_prefill_stable"
            source_root = tmp_path / "source"
            kernel_dir = source_root / kernel
            kernel_dir.mkdir(parents=True)
            layout = kernel_dir / "layout.csl"
            pe = kernel_dir / "pe_program.csl"
            layout.write_text("// layout\n", encoding="utf-8")
            pe.write_text("// pe\n", encoding="utf-8")
            source_digest = hashlib.sha256()
            source_digest.update(_sha256_file(layout).encode("ascii"))
            source_digest.update(_sha256_file(pe).encode("ascii"))
            tile_dir = source_root / f"{kernel}_row_tile_w1_h1"
            (tile_dir / "bin").mkdir(parents=True)
            _write_tile_compile_receipt(
                tile_dir=tile_dir,
                source_digest=source_digest.hexdigest(),
                width=1,
                tile_height=1,
                out_dim_per_pe=4,
                in_dim_per_pe=2,
                layout_path=layout,
            )
            full_dir = tmp_path / "scratch" / "in"
            full_dir.mkdir(parents=True)
            activation = full_dir / "activation.npy"
            weight = full_dir / "weight.npy"
            np.save(activation, np.zeros(4, dtype=np.float16))
            np.save(weight, np.zeros(16, dtype=np.float16))
            output = tmp_path / "scratch" / "out" / "output.npy"
            inputs = [
                {
                    "symbol": "activation",
                    "path": str(activation),
                    "absolutePath": str(activation),
                    "elemType": "f16",
                    "perPeChunk": 2,
                    "sha256": _sha256_file(activation),
                    "totalBytes": activation.stat().st_size,
                },
                {
                    "symbol": "weight",
                    "path": str(weight),
                    "absolutePath": str(weight),
                    "elemType": "f16",
                    "perPeChunk": 8,
                    "sha256": _sha256_file(weight),
                    "totalBytes": weight.stat().st_size,
                },
            ]
            output_record = {
                "symbol": "output",
                "path": str(output),
                "absolutePath": str(output),
                "elemType": "f32",
                "perPeChunk": 4,
                "totalElements": 4,
                "totalBytes": 0,
                "sha256": "",
            }

            def write_partial(command, *, timeout_seconds):
                for i, token in enumerate(command):
                    if token != "--output":
                        continue
                    parts = command[i + 1].split(":")
                    out_path = Path(parts[1])
                    chunk = int(parts[3])
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    np.save(out_path, np.ones(chunk, dtype=np.float32))
                return 0, "phase:launch_complete\n", "", False

            first = runner.run_dense_gemv_row_tiled(
                kernel=kernel,
                compile_root=source_root,
                source_root=source_root,
                compile_params={
                    "width": 2,
                    "height": 1,
                    "out_dim": 4,
                    "out_dim_per_pe": 4,
                    "in_dim_per_pe": 2,
                },
                input_records=inputs,
                output_records=[dict(output_record)],
                scratch_dir=tmp_path / "scratch",
                cs_python=tmp_path / "cs_python",
                adapter=tmp_path / "adapter.py",
                cmaddr="",
                timeout_seconds=30,
                repo_root=tmp_path,
                cslc=None,
                hidden_tile_width=1,
                dispatcher=write_partial,
            )
            assert first is not None
            self.assertIsNone(first.blocker)

            def fail_if_called(command, *, timeout_seconds):
                raise AssertionError("verified partial should have been reused")

            second = runner.run_dense_gemv_row_tiled(
                kernel=kernel,
                compile_root=source_root,
                source_root=source_root,
                compile_params={
                    "width": 2,
                    "height": 1,
                    "out_dim": 4,
                    "out_dim_per_pe": 4,
                    "in_dim_per_pe": 2,
                },
                input_records=inputs,
                output_records=[dict(output_record)],
                scratch_dir=tmp_path / "scratch",
                cs_python=tmp_path / "cs_python",
                adapter=tmp_path / "adapter.py",
                cmaddr="",
                timeout_seconds=30,
                repo_root=tmp_path,
                cslc=None,
                hidden_tile_width=1,
                reuse_verified_tile_partials=True,
                dispatcher=fail_if_called,
            )
            output_values = np.load(output).tolist()

        assert second is not None
        assert second.tile_coverage is not None
        self.assertIsNone(second.blocker)
        self.assertEqual(second.tile_coverage["reusedTileCount"], 2)
        self.assertTrue(
            all(t["reusedVerifiedPartial"] for t in second.tile_dispatches)
        )
        self.assertEqual(output_values, [2.0] * 4)

    def test_hidden_width_tiling_clamps_to_safe_d2h_shape(self) -> None:
        runner = _load_runner_module()
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            kernel = "lm_head_prefill_stable"
            source_root = tmp_path / "compile"
            kernel_dir = source_root / kernel
            kernel_dir.mkdir(parents=True)
            layout = kernel_dir / "layout.csl"
            pe = kernel_dir / "pe_program.csl"
            layout.write_text("// layout\n", encoding="utf-8")
            pe.write_text("// pe\n", encoding="utf-8")
            source_digest = hashlib.sha256()
            source_digest.update(_sha256_file(layout).encode("ascii"))
            source_digest.update(_sha256_file(pe).encode("ascii"))
            for width in (127, 3):
                tile_dir = source_root / f"{kernel}_row_tile_w{width}_h1"
                (tile_dir / "bin").mkdir(parents=True)
                _write_tile_compile_receipt(
                    tile_dir=tile_dir,
                    source_digest=source_digest.hexdigest(),
                    width=width,
                    tile_height=1,
                    out_dim_per_pe=512,
                    in_dim_per_pe=1,
                    layout_path=layout,
                )
            full_dir = tmp_path / "scratch" / "in"
            full_dir.mkdir(parents=True)
            activation = full_dir / "activation.npy"
            weight = full_dir / "weight.npy"
            np.save(activation, np.zeros(130, dtype=np.float16))
            np.save(weight, np.zeros(130 * 512, dtype=np.float16))
            output = tmp_path / "scratch" / "out" / "output.npy"

            def fake_dispatch(command, *, timeout_seconds):
                for i, token in enumerate(command):
                    if token != "--output":
                        continue
                    parts = command[i + 1].split(":")
                    out_path = Path(parts[1])
                    chunk = int(parts[3])
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    np.save(out_path, np.ones(chunk, dtype=np.float32))
                return 0, "phase:launch_complete\n", "", False

            result = runner.run_dense_gemv_row_tiled(
                kernel=kernel,
                compile_root=source_root,
                source_root=source_root,
                compile_params={
                    "width": 130,
                    "height": 1,
                    "out_dim": 512,
                    "out_dim_per_pe": 512,
                    "in_dim_per_pe": 1,
                },
                input_records=[
                    {
                        "symbol": "activation",
                        "path": str(activation),
                        "absolutePath": str(activation),
                        "elemType": "f16",
                        "perPeChunk": 1,
                        "sha256": _sha256_file(activation),
                        "totalBytes": activation.stat().st_size,
                    },
                    {
                        "symbol": "weight",
                        "path": str(weight),
                        "absolutePath": str(weight),
                        "elemType": "f16",
                        "perPeChunk": 512,
                        "sha256": _sha256_file(weight),
                        "totalBytes": weight.stat().st_size,
                    },
                ],
                output_records=[
                    {
                        "symbol": "output",
                        "path": str(output),
                        "absolutePath": str(output),
                        "elemType": "f32",
                        "perPeChunk": 512,
                        "totalElements": 512,
                        "totalBytes": 0,
                        "sha256": "",
                    }
                ],
                scratch_dir=tmp_path / "scratch",
                cs_python=tmp_path / "cs_python",
                adapter=tmp_path / "adapter.py",
                cmaddr="",
                timeout_seconds=30,
                repo_root=tmp_path,
                cslc=None,
                hidden_tile_width=200,
                dispatcher=fake_dispatch,
            )
        assert result is not None
        assert result.tile_coverage is not None
        self.assertIsNone(result.blocker)
        self.assertEqual(
            result.tile_coverage["requestedHiddenTileWidth"], 200
        )
        self.assertEqual(
            result.tile_coverage["effectiveHiddenTileWidth"], 127
        )
        self.assertTrue(result.tile_coverage["tileShapeSafety"]["safe"])
        self.assertEqual(
            result.tile_coverage["hiddenWidthChunks"],
            [
                {"widthStart": 0, "width": 127, "maxRowTileHeight": 1},
                {"widthStart": 127, "width": 3, "maxRowTileHeight": 1},
            ],
        )
        self.assertTrue(
            all(
                t["tileShapeSafety"]["safe"]
                for t in result.tile_dispatches
            )
        )

    def test_row_tiling_refuses_unsafe_d2h_shape_by_default(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            called = False

            def fake_dispatch(command, *, timeout_seconds):
                nonlocal called
                called = True
                return 0, "", "", False

            result = runner.run_dense_gemv_row_tiled(
                kernel="lm_head_prefill_stable",
                compile_root=tmp_path / "compile",
                source_root=tmp_path / "compile",
                compile_params={
                    "width": 128,
                    "height": 1,
                    "out_dim": 512,
                    "out_dim_per_pe": 512,
                    "in_dim_per_pe": 1,
                },
                input_records=[
                    {"symbol": "activation"},
                    {"symbol": "weight"},
                ],
                output_records=[{"symbol": "output", "path": "out.npy"}],
                scratch_dir=tmp_path / "scratch",
                cs_python=tmp_path / "cs_python",
                adapter=tmp_path / "adapter.py",
                cmaddr="",
                timeout_seconds=30,
                repo_root=tmp_path,
                cslc=None,
                tile_height=1,
                dispatcher=fake_dispatch,
            )
        assert result is not None
        assert result.tile_coverage is not None
        self.assertFalse(called)
        self.assertEqual(
            result.blocker,
            "dense_gemv_tile_shape_exceeds_sdk_d2h_limit",
        )
        self.assertFalse(result.tile_coverage["tileShapeSafety"]["safe"])
        self.assertEqual(
            result.tile_coverage["tileShapeSafety"]["outputElements"],
            65536,
        )

    def test_unsafe_tile_shape_requires_explicit_diagnostic_sweep(self) -> None:
        runner = _load_runner_module()
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            kernel = "lm_head_prefill_stable"
            source_root = tmp_path / "compile"
            kernel_dir = source_root / kernel
            kernel_dir.mkdir(parents=True)
            layout = kernel_dir / "layout.csl"
            pe = kernel_dir / "pe_program.csl"
            layout.write_text("// layout\n", encoding="utf-8")
            pe.write_text("// pe\n", encoding="utf-8")
            source_digest = hashlib.sha256()
            source_digest.update(_sha256_file(layout).encode("ascii"))
            source_digest.update(_sha256_file(pe).encode("ascii"))
            tile_dir = source_root / f"{kernel}_row_tile_h1"
            (tile_dir / "bin").mkdir(parents=True)
            _write_tile_compile_receipt(
                tile_dir=tile_dir,
                source_digest=source_digest.hexdigest(),
                width=128,
                tile_height=1,
                out_dim_per_pe=512,
                in_dim_per_pe=1,
                layout_path=layout,
            )
            full_dir = tmp_path / "scratch" / "in"
            full_dir.mkdir(parents=True)
            activation = full_dir / "activation.npy"
            weight = full_dir / "weight.npy"
            np.save(activation, np.zeros(128, dtype=np.float16))
            np.save(weight, np.zeros(128 * 512, dtype=np.float16))
            output = tmp_path / "scratch" / "out" / "output.npy"

            def fake_dispatch(command, *, timeout_seconds):
                for i, token in enumerate(command):
                    if token != "--output":
                        continue
                    parts = command[i + 1].split(":")
                    out_path = Path(parts[1])
                    chunk = int(parts[3])
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    np.save(out_path, np.ones(chunk, dtype=np.float32))
                return 0, "phase:launch_complete\n", "", False

            result = runner.run_dense_gemv_row_tiled(
                kernel=kernel,
                compile_root=source_root,
                source_root=source_root,
                compile_params={
                    "width": 128,
                    "height": 1,
                    "out_dim": 512,
                    "out_dim_per_pe": 512,
                    "in_dim_per_pe": 1,
                },
                input_records=[
                    {
                        "symbol": "activation",
                        "path": str(activation),
                        "absolutePath": str(activation),
                        "elemType": "f16",
                        "perPeChunk": 1,
                        "sha256": _sha256_file(activation),
                        "totalBytes": activation.stat().st_size,
                    },
                    {
                        "symbol": "weight",
                        "path": str(weight),
                        "absolutePath": str(weight),
                        "elemType": "f16",
                        "perPeChunk": 512,
                        "sha256": _sha256_file(weight),
                        "totalBytes": weight.stat().st_size,
                    },
                ],
                output_records=[
                    {
                        "symbol": "output",
                        "path": str(output),
                        "absolutePath": str(output),
                        "elemType": "f32",
                        "perPeChunk": 512,
                        "totalElements": 512,
                        "totalBytes": 0,
                        "sha256": "",
                    }
                ],
                scratch_dir=tmp_path / "scratch",
                cs_python=tmp_path / "cs_python",
                adapter=tmp_path / "adapter.py",
                cmaddr="",
                timeout_seconds=30,
                repo_root=tmp_path,
                cslc=None,
                tile_height=1,
                allow_unsafe_tile_shapes=True,
                dispatcher=fake_dispatch,
            )
        assert result is not None
        assert result.tile_coverage is not None
        self.assertIsNone(result.blocker)
        self.assertFalse(result.tile_coverage["tileShapeSafety"]["safe"])
        self.assertTrue(result.tile_coverage["unsafeTileShapeAllowed"])
        self.assertEqual(result.tile_coverage["evidenceIntent"], "diagnostic_sweep")

    def test_dense_gemv_tile_compile_reuse_requires_param_digest(self) -> None:
        import manifest_dense_gemv_tiles as tiles

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_dir = tmp_path / "source" / "lm_head_prefill_stable"
            source_dir.mkdir(parents=True)
            layout = source_dir / "layout.csl"
            pe = source_dir / "pe_program.csl"
            layout.write_text("// layout\n", encoding="utf-8")
            pe.write_text("// pe\n", encoding="utf-8")
            source_digest = hashlib.sha256()
            source_digest.update(_sha256_file(layout).encode("ascii"))
            source_digest.update(_sha256_file(pe).encode("ascii"))

            tile_dir = tmp_path / "compile" / "tile"
            (tile_dir / "bin").mkdir(parents=True)
            (tile_dir / "dense-gemv-tile-compile.json").write_text(
                json.dumps(
                    {
                        "sourceDigest": source_digest.hexdigest(),
                        "tileHeight": 1,
                        "verdict": "bound",
                        "width": 8,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            receipt, blocker = tiles._ensure_tile_compile(
                cslc=None,
                source_dir=source_dir,
                tile_compile_dir=tile_dir,
                width=8,
                tile_height=1,
                out_dim_per_pe=4,
                in_dim_per_pe=2,
                timeout_seconds=1,
                repo_root=tmp_path,
            )
            self.assertEqual(
                blocker,
                "cslc_unavailable_for_dense_gemv_tile_compile",
            )
            self.assertEqual(receipt["verdict"], "blocked")

            _write_tile_compile_receipt(
                tile_dir=tile_dir,
                source_digest=source_digest.hexdigest(),
                width=8,
                tile_height=1,
                out_dim_per_pe=4,
                in_dim_per_pe=2,
                layout_path=layout,
            )
            receipt, blocker = tiles._ensure_tile_compile(
                cslc=None,
                source_dir=source_dir,
                tile_compile_dir=tile_dir,
                width=8,
                tile_height=1,
                out_dim_per_pe=4,
                in_dim_per_pe=2,
                timeout_seconds=1,
                repo_root=tmp_path,
            )
            self.assertIsNone(blocker)
            self.assertTrue(receipt["reused"])

    def test_width_tiling_does_not_count_stale_partial_after_failed_dispatch(self) -> None:
        runner = _load_runner_module()
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            kernel = "lm_head_prefill_stable"
            source_root = tmp_path / "compile"
            kernel_dir = source_root / kernel
            kernel_dir.mkdir(parents=True)
            layout = kernel_dir / "layout.csl"
            pe = kernel_dir / "pe_program.csl"
            layout.write_text("// layout\n", encoding="utf-8")
            pe.write_text("// pe\n", encoding="utf-8")
            source_digest = hashlib.sha256()
            source_digest.update(_sha256_file(layout).encode("ascii"))
            source_digest.update(_sha256_file(pe).encode("ascii"))
            tile_dir = source_root / f"{kernel}_row_tile_w3_h1"
            (tile_dir / "bin").mkdir(parents=True)
            _write_tile_compile_receipt(
                tile_dir=tile_dir,
                source_digest=source_digest.hexdigest(),
                width=3,
                tile_height=1,
                out_dim_per_pe=4,
                in_dim_per_pe=2,
                layout_path=layout,
            )
            full_dir = tmp_path / "scratch" / "in"
            full_dir.mkdir(parents=True)
            activation = full_dir / "activation.npy"
            weight = full_dir / "weight.npy"
            np.save(activation, np.zeros(4 * 2, dtype=np.float16))
            np.save(weight, np.zeros(4 * 8, dtype=np.float16))
            stale = (
                tmp_path
                / "scratch"
                / "width-row-tiles"
                / "x0000_w0003"
                / "y0000"
                / "out"
                / "partial.npy"
            )
            stale.parent.mkdir(parents=True)
            np.save(stale, np.ones(4, dtype=np.float32))

            def failing_dispatch(command, *, timeout_seconds):
                return 255, "", "container failed\n", False

            result = runner.run_dense_gemv_row_tiled(
                kernel=kernel,
                compile_root=source_root,
                source_root=source_root,
                compile_params={
                    "width": 4,
                    "height": 1,
                    "out_dim": 4,
                    "out_dim_per_pe": 4,
                    "in_dim_per_pe": 2,
                },
                input_records=[
                    {
                        "symbol": "activation",
                        "path": str(activation),
                        "absolutePath": str(activation),
                        "elemType": "f16",
                        "perPeChunk": 2,
                        "sha256": _sha256_file(activation),
                        "totalBytes": activation.stat().st_size,
                    },
                    {
                        "symbol": "weight",
                        "path": str(weight),
                        "absolutePath": str(weight),
                        "elemType": "f16",
                        "perPeChunk": 8,
                        "sha256": _sha256_file(weight),
                        "totalBytes": weight.stat().st_size,
                    },
                ],
                output_records=[
                    {
                        "symbol": "output",
                        "path": str(tmp_path / "scratch" / "out" / "output.npy"),
                        "absolutePath": str(
                            tmp_path / "scratch" / "out" / "output.npy"
                        ),
                        "elemType": "f32",
                        "perPeChunk": 4,
                        "totalElements": 4,
                        "totalBytes": 0,
                        "sha256": "",
                    }
                ],
                scratch_dir=tmp_path / "scratch",
                cs_python=tmp_path / "cs_python",
                adapter=tmp_path / "adapter.py",
                cmaddr="",
                timeout_seconds=30,
                repo_root=tmp_path,
                cslc=None,
                hidden_tile_width=3,
                dispatcher=failing_dispatch,
            )

        assert result is not None
        self.assertEqual(
            result.blocker,
            "dense_gemv_width_tile_dispatch_exit_code_255",
        )
        self.assertEqual(result.tile_dispatches[0]["output"]["totalBytes"], 0)
        assert result.tile_coverage is not None
        self.assertEqual(result.tile_coverage["completedTileCount"], 0)

    def test_summary_preserves_dispatch_mode_and_tile_contract(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            host_plan_path = tmp_path / "host-plan.json"
            host_plan_path.write_text("{}", encoding="utf-8")
            receipt = runner.build_kernel_receipt(
                kernel="lm_head_prefill_stable",
                compile_dir=tmp_path / "compile",
                compile_params={"width": 5, "height": 2},
                inputs=[],
                outputs=[
                    {
                        "symbol": "output",
                        "totalBytes": 64,
                        "sha256": "a" * 64,
                        "hostReduction": {
                            "kind": "sum_hidden_width_tiles",
                        },
                    }
                ],
                probe={},
                dispatch_command=[],
                dispatch_exit_code=0,
                dispatch_stdout="phase:launch_complete\n",
                dispatch_stderr="",
                dispatch_timed_out=False,
                dispatch_wallclock_ns=1,
                dispatch_mode="dense_gemv_width_tiled",
                host_plan_path=host_plan_path,
                host_plan_hash=_sha256_file(host_plan_path),
                cmaddr="",
                blocker=None,
            )
            receipt["tileCoverage"] = {
                "kind": "width_row_tiles",
                "covered": True,
            }
            receipt["tileCompile"] = {
                "mode": "dense_gemv_width_tiled",
                "receipts": [
                    {
                        "verdict": "bound",
                        "commandDigest": "b" * 64,
                    }
                ],
            }
            receipt["tileDispatches"] = [
                {
                    "executionMode": "batched_runtime",
                    "exitCode": 0,
                    "timedOut": False,
                    "output": {
                        "totalBytes": 64,
                        "sha256": "c" * 64,
                    },
                }
            ]
            summary_path = runner.write_summary(
                out_dir=tmp_path / "out",
                receipts=[receipt],
                host_plan_path=host_plan_path,
                host_plan_hash=_sha256_file(host_plan_path),
            )
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        entry = summary["kernels"][0]
        self.assertEqual(entry["dispatchMode"], "dense_gemv_width_tiled")
        self.assertEqual(
            entry["lmHeadEvidenceScope"],
            "full_vocab_host_reduced_width_row_tiles",
        )
        self.assertEqual(entry["tileDispatches"]["blockedCount"], 0)
        self.assertEqual(
            entry["tileDispatches"]["executionModes"],
            ["batched_runtime"],
        )
        self.assertTrue(entry["tileCoverage"]["covered"])
        self.assertEqual(
            entry["hostReduction"]["kind"],
            "sum_hidden_width_tiles",
        )

    def test_existing_receipts_can_feed_restricted_summary_refresh(self) -> None:
        runner = _load_runner_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            host_plan_path = tmp_path / "host-plan.json"
            host_plan_path.write_text("{}", encoding="utf-8")
            host_plan_hash = _sha256_file(host_plan_path)
            out_dir = tmp_path / "out"
            sample = runner.build_kernel_receipt(
                kernel="sample",
                compile_dir=tmp_path / "compile",
                compile_params={"width": 1, "height": 1},
                inputs=[],
                outputs=[],
                probe={},
                dispatch_command=[],
                dispatch_exit_code=0,
                dispatch_stdout="",
                dispatch_stderr="",
                dispatch_timed_out=False,
                dispatch_wallclock_ns=1,
                host_plan_path=host_plan_path,
                host_plan_hash=host_plan_hash,
                cmaddr="",
                blocker=None,
            )
            runner.write_kernel_receipt(receipt=sample, out_dir=out_dir)
            existing = runner.load_existing_receipts_for_summary(
                out_dir=out_dir,
                host_plan_hash=host_plan_hash,
            )

        self.assertIn("sample", existing)
        self.assertEqual(existing["sample"]["verdict"], "bound")

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

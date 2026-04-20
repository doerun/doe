from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from bench.tools.doppler_rdrr_q4k import (
    Q4_K_M_BLOCK_BYTES,
    dequantize_q4km_block,
    dequantize_q4km_rowwise_bytes,
    read_q4km_rowwise_prefix,
    unpack_q4k_scale_min_bits,
)


def _f16_word(value: float) -> int:
    return struct.unpack("<H", struct.pack("<e", value))[0]


def _make_q4k_block(
    scale_bits: list[int] | None = None,
    min_bits: list[int] | None = None,
    quant_values: list[int] | None = None,
    d: float = 1.0,
    dmin: float = 0.0,
) -> bytes:
    scales = scale_bits or [1] * 8
    mins = min_bits or [0] * 8
    quant = quant_values or [1] * 256
    block = bytearray(Q4_K_M_BLOCK_BYTES)
    d_word = _f16_word(d)
    dmin_word = _f16_word(dmin)
    block[0] = d_word & 0xFF
    block[1] = (d_word >> 8) & 0xFF
    block[2] = dmin_word & 0xFF
    block[3] = (dmin_word >> 8) & 0xFF
    for index in range(4):
        block[4 + index] = (
            (scales[index] & 0x3F)
            | (((scales[index + 4] >> 4) & 0x03) << 6)
        )
        block[8 + index] = (
            (mins[index] & 0x3F)
            | (((mins[index + 4] >> 4) & 0x03) << 6)
        )
        block[12 + index] = (
            (scales[index + 4] & 0x0F)
            | ((mins[index + 4] & 0x0F) << 4)
        )
    for chunk in range(4):
        chunk_base = chunk * 64
        byte_base = 16 + chunk * 32
        for index in range(32):
            low = quant[chunk_base + index] & 0x0F
            high = quant[chunk_base + 32 + index] & 0x0F
            block[byte_base + index] = low | (high << 4)
    return bytes(block)


class DopplerRdrrQ4KTests(unittest.TestCase):
    def test_q4k_scale_min_bit_unpack_and_dequant(self) -> None:
        scale_bits = [1, 2, 3, 4, 17, 18, 19, 20]
        min_bits = [0, 1, 2, 3, 21, 22, 23, 24]
        quant = [index % 16 for index in range(256)]
        block = _make_q4k_block(
            scale_bits=scale_bits,
            min_bits=min_bits,
            quant_values=quant,
            d=0.5,
            dmin=0.25,
        )

        got_scales, got_mins, d, dmin = unpack_q4k_scale_min_bits(block)
        self.assertEqual(got_scales, scale_bits)
        self.assertEqual(got_mins, min_bits)
        self.assertEqual(d, 0.5)
        self.assertEqual(dmin, 0.25)

        values = dequantize_q4km_block(block)
        self.assertEqual(len(values), 256)
        self.assertAlmostEqual(values[0], 0.0)
        self.assertAlmostEqual(values[32], 1.0 * (quant[32]) - 0.25)
        self.assertAlmostEqual(values[161], 9.0 * quant[161] - 5.5)

    def test_rowwise_dequant_strips_tail_padding(self) -> None:
        row0_a = _make_q4k_block(quant_values=[1] * 256)
        row0_b = _make_q4k_block(quant_values=[2] * 256)
        row1_a = _make_q4k_block(quant_values=[3] * 256)
        row1_b = _make_q4k_block(quant_values=[4] * 256)
        values = dequantize_q4km_rowwise_bytes(
            row0_a + row0_b + row1_a + row1_b,
            [2, 300],
        )

        self.assertEqual(len(values), 600)
        self.assertEqual(values[:256], [1.0] * 256)
        self.assertEqual(values[256:300], [2.0] * 44)
        self.assertEqual(values[300:556], [3.0] * 256)
        self.assertEqual(values[556:600], [4.0] * 44)

    def test_manifest_prefix_reader_crosses_row_boundary(self) -> None:
        row0_a = _make_q4k_block(quant_values=[1] * 256)
        row0_b = _make_q4k_block(quant_values=[2] * 256)
        row1_a = _make_q4k_block(quant_values=[3] * 256)
        row1_b = _make_q4k_block(quant_values=[4] * 256)
        shard_bytes = row0_a + row0_b + row1_a + row1_b

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "shard_00000.bin").write_bytes(shard_bytes)
            manifest = {
                "shards": [
                    {
                        "index": 0,
                        "filename": "shard_00000.bin",
                        "size": len(shard_bytes),
                    }
                ],
                "tensors": {
                    "tensor.weight": {
                        "shard": 0,
                        "offset": 0,
                        "size": len(shard_bytes),
                        "shape": [2, 300],
                        "dtype": "Q4_K_M",
                        "layout": "row",
                    }
                },
            }
            (root / "manifest.json").write_text(json.dumps(manifest))
            values = read_q4km_rowwise_prefix(
                root,
                manifest,
                "tensor.weight",
                320,
            )

        self.assertEqual(len(values), 320)
        self.assertEqual(values[:256], [1.0] * 256)
        self.assertEqual(values[256:300], [2.0] * 44)
        self.assertEqual(values[300:320], [3.0] * 20)


if __name__ == "__main__":
    unittest.main()

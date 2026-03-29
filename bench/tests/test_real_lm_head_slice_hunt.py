#!/usr/bin/env python3
"""Regression tests for the real LM-head slice hunt runner."""

from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from bench.runners.run_real_lm_head_slice_hunt import TensorRowReader
from bench.runners.run_real_lm_head_slice_hunt import build_commands
from bench.runners.run_real_lm_head_slice_hunt import forward_dot_f16accum
from bench.runners.run_real_lm_head_slice_hunt import forward_dot_f32
from bench.runners.run_real_lm_head_slice_hunt import reverse_dot_f32
from bench.runners.run_real_lm_head_slice_hunt import tree64_dot_f32


def f16_bytes(values: list[float]) -> bytes:
    return struct.pack("<" + "e" * len(values), *values)


class RealLmHeadSliceHuntTests(unittest.TestCase):
    def test_tree64_matches_forward_for_uniform_inputs(self) -> None:
        hidden = [1.0] * 128
        weights = [1.0] * 128
        self.assertEqual(forward_dot_f32(hidden, weights), 128.0)
        self.assertEqual(reverse_dot_f32(hidden, weights), 128.0)
        self.assertEqual(tree64_dot_f32(hidden, weights), 128.0)

    def test_f16accum_matches_simple_exact_sum(self) -> None:
        hidden = [1.0, 2.0, 3.0, 4.0]
        weights = [0.5, 0.25, 0.5, 0.25]
        self.assertAlmostEqual(forward_dot_f16accum(hidden, weights), 3.5)

    def test_tensor_row_reader_reads_rows_across_spans(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            row0 = [1.0, 2.0, 3.0]
            row1 = [4.0, 5.0, 6.0]
            row2 = [7.0, 8.0, 9.0]
            row3 = [10.0, 11.0, 12.0]
            tensor_bytes = b"".join(f16_bytes(row) for row in (row0, row1, row2, row3))
            (root / "shard_00000.bin").write_bytes(tensor_bytes[:10])
            (root / "shard_00001.bin").write_bytes(tensor_bytes[10:])
            manifest = {
                "shards": [
                    {"filename": "shard_00000.bin"},
                    {"filename": "shard_00001.bin"},
                ],
                "tensors": {
                    "model.embed_tokens.weight": {
                        "dtype": "F16",
                        "shape": [4, 3],
                        "size": len(tensor_bytes),
                        "spans": [
                            {"shardIndex": 0, "offset": 0, "size": 10},
                            {"shardIndex": 1, "offset": 0, "size": len(tensor_bytes) - 10},
                        ],
                    }
                },
            }
            reader = TensorRowReader(root, manifest, "model.embed_tokens.weight")
            try:
                rows = reader.read_rows([1, 2])
            finally:
                reader.close()
            self.assertEqual(rows[1], row1)
            self.assertEqual(rows[2], row2)

    def test_build_commands_emits_expected_dispatches(self) -> None:
        commands = build_commands([1.0, 2.0], [[3.0, 4.0], [5.0, 6.0]], kernel="matmul_logits_tree64_f32.wgsl")
        self.assertEqual(len(commands), 6)
        self.assertEqual(commands[0]["data"][:2], [2, 2])
        self.assertEqual(commands[4]["kernel"], "matmul_logits_tree64_f32.wgsl")
        self.assertEqual(commands[5]["kernel"], "sample.wgsl")


if __name__ == "__main__":
    unittest.main()

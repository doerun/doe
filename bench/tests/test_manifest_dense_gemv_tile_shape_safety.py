"""Regression tests for the simfabric D2H tile-shape safety invariant.

Anchored on the empirical cliff observed under SDK 2.10 / simfabric: tile
dispatches whose total output element count reaches 2^16 wedge at
memcpy_d2h_start with totalOutputBytes=0. The predicates below encode that
boundary as machine-checkable constraints so tile-shape selection cannot
silently pick an unsafe shape.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_module():
    name = "manifest_dense_gemv_tiles"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name,
        REPO_ROOT / "bench/runners/csl-runners/manifest_dense_gemv_tiles.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


M = _load_module()


class TileShapeSafetyTest(unittest.TestCase):
    def test_limit_constant_matches_2_to_16(self) -> None:
        # The cliff sits exactly at 2**16 in the empirical receipts. If the
        # canonical receipts later separate width-cliff from multi-row-D2H
        # wedge into distinct constants, this test should split with them.
        self.assertEqual(M.SDK_D2H_ELEMENT_COUNT_LIMIT, 65536)

    def test_observed_landing_shape_is_safe(self) -> None:
        # width=120, height=1, out_dim_per_pe=512 lands a real partial.npy
        # under SDK 2.10 / simfabric (61,440 elements).
        self.assertTrue(
            M.is_safe_tile_shape(width=120, height=1, out_dim_per_pe=512)
        )

    def test_observed_stall_shape_is_unsafe(self) -> None:
        # width=128, height=1, out_dim_per_pe=512 stalls at memcpy_d2h_start
        # with totalOutputBytes=0 (65,536 elements -- exactly at the cliff).
        self.assertFalse(
            M.is_safe_tile_shape(width=128, height=1, out_dim_per_pe=512)
        )

    def test_observed_full_fabric_shape_is_unsafe(self) -> None:
        # The monolithic Gemma 4 31B af16 lm_head_prefill shape:
        # width=160, height=512, out_dim_per_pe=512 -- well past the cliff.
        self.assertFalse(
            M.is_safe_tile_shape(width=160, height=512, out_dim_per_pe=512)
        )

    def test_multi_row_height_amplifies_cliff(self) -> None:
        # height>1 amplifies the element count: width=64, height=2,
        # out_dim_per_pe=512 already hits 65,536 and wedges.
        self.assertFalse(
            M.is_safe_tile_shape(width=64, height=2, out_dim_per_pe=512)
        )
        # width=32, height=2 (32,768) is safe -- under the cliff.
        self.assertTrue(
            M.is_safe_tile_shape(width=32, height=2, out_dim_per_pe=512)
        )

    def test_invalid_shapes_are_unsafe(self) -> None:
        for shape in (
            {"width": 0, "height": 1, "out_dim_per_pe": 512},
            {"width": 1, "height": 0, "out_dim_per_pe": 512},
            {"width": 1, "height": 1, "out_dim_per_pe": 0},
            {"width": -1, "height": 1, "out_dim_per_pe": 512},
        ):
            self.assertFalse(M.is_safe_tile_shape(**shape), msg=shape)

    def test_max_safe_tile_width_at_cliff_boundary(self) -> None:
        # For height=1, out_dim_per_pe=512, the maximum safe width is
        # floor((65536 - 1) / 512) = 127.
        self.assertEqual(
            M.max_safe_tile_width(height=1, out_dim_per_pe=512),
            127,
        )
        # That width must itself be safe.
        self.assertTrue(
            M.is_safe_tile_shape(width=127, height=1, out_dim_per_pe=512)
        )
        # And one above must not be.
        self.assertFalse(
            M.is_safe_tile_shape(width=128, height=1, out_dim_per_pe=512)
        )

    def test_max_safe_tile_width_for_multi_row(self) -> None:
        # height=2 at out_dim_per_pe=512 -> floor((65536-1)/1024) = 63.
        self.assertEqual(
            M.max_safe_tile_width(height=2, out_dim_per_pe=512),
            63,
        )
        self.assertTrue(
            M.is_safe_tile_shape(width=63, height=2, out_dim_per_pe=512)
        )

    def test_max_safe_tile_width_zero_when_per_unit_exceeds_limit(self) -> None:
        # If height * out_dim_per_pe alone meets or exceeds the limit, no
        # width is safe and the helper returns 0 rather than negative.
        self.assertEqual(
            M.max_safe_tile_width(height=128, out_dim_per_pe=512),
            0,
        )
        self.assertEqual(
            M.max_safe_tile_width(height=0, out_dim_per_pe=512),
            0,
        )

    def test_custom_limit_override(self) -> None:
        # If the canonical sweep later refines the boundary, callers can pass
        # a tighter or looser limit explicitly.
        self.assertTrue(
            M.is_safe_tile_shape(
                width=8, height=1, out_dim_per_pe=64, limit=1024
            )
        )
        self.assertFalse(
            M.is_safe_tile_shape(
                width=16, height=1, out_dim_per_pe=64, limit=1024
            )
        )

    def test_split_d2h_rows_allows_tall_claim_tiles(self) -> None:
        tiles = M._planned_width_row_tiles(
            width=160,
            full_height=512,
            hidden_tile_width=120,
            out_dim_per_pe=512,
            allow_unsafe_tile_shapes=False,
            split_d2h_rows=True,
        )
        self.assertEqual(
            tiles,
            [
                {
                    "widthStart": 0,
                    "width": 120,
                    "rowStart": 0,
                    "rowCount": 512,
                    "rowTileHeight": 512,
                },
                {
                    "widthStart": 120,
                    "width": 40,
                    "rowStart": 0,
                    "rowCount": 512,
                    "rowTileHeight": 512,
                },
            ],
        )
        summary = M._width_row_tile_shape_summary(
            planned_tiles=tiles,
            out_dim_per_pe=512,
            split_d2h_rows=True,
        )
        self.assertTrue(summary["safe"])
        self.assertEqual(summary["d2hCopyHeight"], 1)
        self.assertEqual(summary["d2hElementsPerCopy"], 61440)
        self.assertEqual(summary["outputElements"], 120 * 512 * 512)

    def test_batch_dispatch_command_records_split_and_phase_trace(self) -> None:
        command = M._batch_dispatch_command(
            cs_python=Path("cs_python"),
            adapter=Path("adapter.py"),
            compile_dir=Path("compiled/lm_head"),
            width=120,
            height=1,
            in_dim_per_pe=32,
            batch_path=Path("batch.json"),
            dummy_output_spec="output:partial.npy:f32:512:119,0,1,1",
            cmaddr="",
            split_d2h_rows=True,
            phase_trace_path=Path("phase-trace.log"),
        )
        self.assertIn("--split-d2h-rows", command)
        self.assertIn("--phase-trace", command)
        self.assertEqual(
            command[command.index("--phase-trace") + 1],
            "phase-trace.log",
        )

    def test_batch_phase_events_are_step_scoped(self) -> None:
        events = M._parse_phase_events(
            "\n".join(
                [
                    "phase:step_start step=0",
                    "phase:memcpy_d2h_complete step=0 symbol=output",
                    "phase:step_complete step=0",
                    "phase:step_start step=1",
                    "phase:memcpy_d2h_complete step=1 symbol=output",
                    "phase:step_complete step=1",
                    "phase:stop_complete",
                ]
            )
        )
        scoped = M._phase_events_for_batch_step(events, 1)
        self.assertEqual(
            [event["phase"] for event in scoped],
            [
                "step_start",
                "memcpy_d2h_complete",
                "step_complete",
            ],
        )
        self.assertTrue(all(event.get("step") == "1" for event in scoped))

    def test_batch_group_dir_name_includes_tile_range(self) -> None:
        self.assertEqual(
            M._batch_group_dir_name(
                3,
                [
                    {
                        "widthStart": 0,
                        "width": 120,
                        "rowStart": 105,
                        "rowCount": 1,
                    },
                    {
                        "widthStart": 0,
                        "width": 120,
                        "rowStart": 120,
                        "rowCount": 1,
                    },
                ],
            ),
            "g0003_x0000_w0120_y0105_y0120",
        )

    def test_filter_tiles_by_y_range_keeps_all_width_chunks(self) -> None:
        planned = [
            {"widthStart": 0, "width": 120, "rowStart": 0, "rowCount": 1},
            {"widthStart": 120, "width": 40, "rowStart": 0, "rowCount": 1},
            {"widthStart": 0, "width": 120, "rowStart": 1, "rowCount": 1},
            {"widthStart": 120, "width": 40, "rowStart": 1, "rowCount": 1},
            {"widthStart": 0, "width": 120, "rowStart": 2, "rowCount": 1},
            {"widthStart": 120, "width": 40, "rowStart": 2, "rowCount": 1},
        ]
        filtered = M._filter_tiles_by_y_range(planned, (1, 2))
        self.assertEqual(len(filtered), 2)
        self.assertEqual({tile["widthStart"] for tile in filtered}, {0, 120})
        self.assertEqual({tile["rowStart"] for tile in filtered}, {1})


if __name__ == "__main__":
    unittest.main()

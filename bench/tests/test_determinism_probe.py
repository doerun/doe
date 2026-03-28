#!/usr/bin/env python3
"""Regression tests for the Apple determinism probe runner."""

from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from bench.runners.run_determinism_probe import annotate_commands
from bench.runners.run_determinism_probe import audit_greedy_tie_break
from bench.runners.run_determinism_probe import build_tie_break_audit
from bench.runners.run_determinism_probe import compare_lanes
from bench.runners.run_determinism_probe import decode_capture_f32le
from bench.runners.run_determinism_probe import decode_capture_value
from bench.runners.run_determinism_probe import infer_captures_for_mode
from bench.runners.run_determinism_probe import resolve_captures
from bench.runners.run_determinism_probe import summarize_lane_runs


class DeterminismProbeTests(unittest.TestCase):
    def test_annotate_commands_only_touches_requested_rows(self) -> None:
        commands = [
            {"kind": "buffer_write", "handle": 1, "bufferSize": 4, "data": [1]},
            {"kind": "kernel_dispatch", "kernel": "sample.wgsl", "bindings": []},
        ]
        captures = [
            {
                "commandIndex": 1,
                "semanticOpId": "decode.sample_token",
                "semanticStage": "gemma3_decode",
                "semanticPhase": "sample_token",
                "semanticTokenIndex": 0,
                "captureBufferHandle": 2228,
                "captureOffset": 0,
                "captureSize": 4,
            }
        ]
        annotated = annotate_commands(commands, captures, execution_plan_hash="abc123")
        self.assertNotIn("semanticOpId", annotated[0])
        self.assertEqual(annotated[1]["semanticOpId"], "decode.sample_token")
        self.assertEqual(annotated[1]["semanticExecutionPlanHash"], "abc123")
        self.assertEqual(annotated[1]["captureBufferHandle"], 2228)
        self.assertEqual(commands[1].get("semanticOpId"), None)

    def test_decode_capture_value_reads_u32le(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-determinism-probe-") as tmpdir:
            path = Path(tmpdir) / "token.bin"
            path.write_bytes((1234).to_bytes(4, "little"))
            self.assertEqual(decode_capture_value(path, "u32le"), 1234)
            self.assertIsNone(decode_capture_value(path, None))

    def test_decode_capture_f32le_and_audit_greedy_tie_break(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-determinism-probe-") as tmpdir:
            path = Path(tmpdir) / "logits.bin"
            path.write_bytes(struct.pack("<ffff", 1.0, 2.0, 2.0, -3.0))
            self.assertEqual(decode_capture_f32le(path), [1.0, 2.0, 2.0, -3.0])
            audit = audit_greedy_tie_break(path, sampled_token=1)
            self.assertEqual(audit["exactMaxTieCount"], 2)
            self.assertEqual(audit["expectedGreedyToken"], 1)
            self.assertTrue(audit["matchesExpectedGreedyToken"])

    def test_infer_stable_token_capture_from_sample_kernel(self) -> None:
        commands = [
            {"kind": "buffer_write", "handle": 2227, "bufferSize": 16, "data": [0, 0, 0, 0]},
            {
                "kind": "kernel_dispatch",
                "kernel": "sample.wgsl",
                "bindings": [
                    {"binding": 0, "resource_handle": 1001, "buffer_size": 16, "buffer_type": "uniform"},
                    {"binding": 1, "resource_handle": 2227, "buffer_size": 16, "buffer_type": "readonly"},
                    {"binding": 2, "resource_handle": 2228, "buffer_size": 4, "buffer_type": "storage"},
                ],
            },
        ]
        captures = infer_captures_for_mode(commands, determinism_mode="stable-token", semantic_stage="greedy_sample")
        self.assertEqual(
            captures,
            [
                {
                    "commandIndex": 1,
                    "semanticOpId": "sample.output_token",
                    "semanticStage": "greedy_sample",
                    "semanticPhase": "output_token",
                    "semanticTokenIndex": 0,
                    "captureBufferHandle": 2228,
                    "captureOffset": 0,
                    "captureSize": 4,
                    "decode": "u32le",
                }
            ],
        )

    def test_infer_stable_decode_step_captures_logits_producer_and_token(self) -> None:
        commands = [
            {
                "kind": "kernel_dispatch",
                "kernel": "matmul-gemv.wgsl",
                "bindings": [
                    {"binding": 2, "resource_handle": 2201, "buffer_size": 6144, "buffer_type": "readonly"},
                    {"binding": 3, "resource_handle": 2227, "buffer_size": 16384, "buffer_type": "storage"},
                ],
            },
            {
                "kind": "kernel_dispatch",
                "kernel": "sample.wgsl",
                "bindings": [
                    {"binding": 0, "resource_handle": 1010, "buffer_size": 16, "buffer_type": "uniform"},
                    {"binding": 1, "resource_handle": 2227, "buffer_size": 16384, "buffer_type": "readonly"},
                    {"binding": 2, "resource_handle": 2228, "buffer_size": 4, "buffer_type": "storage"},
                ],
            },
        ]
        captures = infer_captures_for_mode(commands, determinism_mode="stable-decode-step", semantic_stage="gemma3_decode")
        self.assertEqual(captures[0]["commandIndex"], 0)
        self.assertEqual(captures[0]["semanticOpId"], "decode.final_logits")
        self.assertEqual(captures[0]["captureBufferHandle"], 2227)
        self.assertEqual(captures[1]["commandIndex"], 1)
        self.assertEqual(captures[1]["semanticOpId"], "decode.sample_token")
        self.assertEqual(captures[1]["captureBufferHandle"], 2228)
        self.assertEqual(captures[1]["decode"], "u32le")

    def test_resolve_captures_prefers_inferred_mode_when_present(self) -> None:
        fixture = {
            "determinismMode": "stable-token",
            "semanticStage": "greedy_sample",
            "captures": [
                {
                    "commandIndex": 999,
                    "semanticOpId": "wrong.capture",
                    "semanticStage": "wrong",
                    "semanticPhase": "wrong",
                    "captureBufferHandle": 999,
                    "captureSize": 4,
                }
            ],
        }
        commands = [
            {"kind": "buffer_write", "handle": 1, "bufferSize": 4, "data": [0]},
            {
                "kind": "kernel_dispatch",
                "kernel": "sample.wgsl",
                "bindings": [
                    {"binding": 1, "resource_handle": 2, "buffer_size": 16, "buffer_type": "readonly"},
                    {"binding": 2, "resource_handle": 3, "buffer_size": 4, "buffer_type": "storage"},
                ],
            },
        ]
        captures, plan = resolve_captures(fixture, commands, mode_override=None)
        self.assertEqual(plan["kind"], "inferred")
        self.assertEqual(plan["determinismMode"], "stable-token")
        self.assertEqual(captures[0]["semanticOpId"], "sample.output_token")

    def test_summaries_detect_stable_runs_and_cross_lane_match(self) -> None:
        captures = [
            {
                "semanticOpId": "decode.final_logits",
                "captureSize": 16,
            },
            {
                "semanticOpId": "decode.sample_token",
                "captureSize": 4,
                "decode": "u32le",
            },
        ]
        with tempfile.TemporaryDirectory(prefix="doe-determinism-probe-") as tmpdir:
            root = Path(tmpdir)
            token_a = root / "token-a.bin"
            token_b = root / "token-b.bin"
            logits = root / "logits.bin"
            token_a.write_bytes((7).to_bytes(4, "little"))
            token_b.write_bytes((7).to_bytes(4, "little"))
            logits.write_bytes(b"\x00" * 16)
            doe_runs = [
                {
                    "runIndex": 0,
                    "operatorRows": {
                        "decode.final_logits": {"capture": {"status": "ok", "sha256": "aaa", "path": str(logits)}},
                        "decode.sample_token": {"capture": {"status": "ok", "sha256": "bbb", "path": str(token_a)}},
                    },
                },
                {
                    "runIndex": 1,
                    "operatorRows": {
                        "decode.final_logits": {"capture": {"status": "ok", "sha256": "aaa", "path": str(logits)}},
                        "decode.sample_token": {"capture": {"status": "ok", "sha256": "bbb", "path": str(token_b)}},
                    },
                },
            ]
            dawn_runs = [
                {
                    "runIndex": 0,
                    "operatorRows": {
                        "decode.final_logits": {"capture": {"status": "ok", "sha256": "aaa", "path": str(logits)}},
                        "decode.sample_token": {"capture": {"status": "ok", "sha256": "bbb", "path": str(token_a)}},
                    },
                },
                {
                    "runIndex": 1,
                    "operatorRows": {
                        "decode.final_logits": {"capture": {"status": "ok", "sha256": "aaa", "path": str(logits)}},
                        "decode.sample_token": {"capture": {"status": "ok", "sha256": "bbb", "path": str(token_b)}},
                    },
                },
            ]
            doe_summary = summarize_lane_runs(doe_runs, captures)
            dawn_summary = summarize_lane_runs(dawn_runs, captures)
            self.assertTrue(doe_summary["stableAcrossRuns"])
            self.assertTrue(doe_summary["operators"]["decode.sample_token"]["decodedValueStableAcrossRuns"])
            cross_lane = compare_lanes({"doe": doe_summary, "dawn": dawn_summary}, captures)
            self.assertTrue(cross_lane["operators"]["decode.final_logits"]["sameAcrossLanes"])
            self.assertTrue(cross_lane["operators"]["decode.sample_token"]["sameDecodedValueAcrossLanes"])

    def test_build_tie_break_audit_pairs_logits_and_sample_token(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doe-determinism-probe-") as tmpdir:
            root = Path(tmpdir)
            logits = root / "logits.bin"
            token = root / "token.bin"
            logits.write_bytes(struct.pack("<fff", 0.0, 5.0, 5.0))
            token.write_bytes((1).to_bytes(4, "little"))
            lane_summaries = {
                "doe": {
                    "operators": {
                        "decode.final_logits": {
                            "artifacts": [{"capturePath": str(logits)}],
                        },
                        "decode.sample_token": {
                            "dominantDecodedValue": 1,
                        },
                    }
                },
                "dawn": {
                    "operators": {
                        "decode.final_logits": {
                            "artifacts": [{"capturePath": str(logits)}],
                        },
                        "decode.sample_token": {
                            "dominantDecodedValue": 1,
                        },
                    }
                },
            }
            audit = build_tie_break_audit(lane_summaries)
            self.assertTrue(audit["lanes"]["doe"]["decode.final_logits"]["matchesExpectedGreedyToken"])
            self.assertEqual(audit["lanes"]["doe"]["decode.final_logits"]["exactMaxTieCount"], 2)
            self.assertTrue(audit["crossLane"]["decode.final_logits"]["allLanesMatchExpectedGreedyToken"])


if __name__ == "__main__":
    unittest.main()

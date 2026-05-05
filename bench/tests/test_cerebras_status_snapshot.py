#!/usr/bin/env python3
"""Tests for the Cerebras lane status snapshot reflector."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]


class CerebrasStatusSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "cerebras_status_snapshot",
            REPO_ROOT / "bench" / "tools" / "cerebras_status_snapshot.py",
        )
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, rel: str, payload: dict) -> Path:
        p = self.tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload))
        return p

    def test_cross_model_parity_bound(self) -> None:
        self._write(
            self.module.CROSS_MODEL_PARITY,
            {"verdict": "bound", "issues": [], "requiredLanes": ["a", "b"]},
        )
        with mock.patch.object(self.module, "REPO_ROOT", self.tmp):
            row = self.module.cross_model_parity_row()
        self.assertEqual(row["verdict"], "bound")
        self.assertIsNone(row["blocker"])

    def test_cross_model_parity_with_issues(self) -> None:
        self._write(
            self.module.CROSS_MODEL_PARITY,
            {
                "verdict": "unbound",
                "issues": [{"class": "lane_missing", "detail": "qwen lane absent"}],
            },
        )
        with mock.patch.object(self.module, "REPO_ROOT", self.tmp):
            row = self.module.cross_model_parity_row()
        self.assertEqual(row["verdict"], "unbound")
        self.assertEqual(row["blocker"], "lane_missing")

    def test_per_kernel_summary_blocked_when_any_kernel_unbound(self) -> None:
        dir_rel = self.module.GEMMA_PER_KERNEL_DIR
        self._write(
            f"{dir_rel}/summary.json",
            {
                "kernels": [
                    {"name": "sample", "verdict": "bound"},
                    {"name": "lm_head_prefill", "verdict": "blocked"},
                ],
            },
        )
        self._write(
            f"{dir_rel}/sample.json",
            {"verdict": "bound", "blocker": None},
        )
        self._write(
            f"{dir_rel}/lm_head_prefill.json",
            {"verdict": "blocked", "blocker": "shape_exceeds_d2h_limit"},
        )
        with mock.patch.object(self.module, "REPO_ROOT", self.tmp):
            rows = self.module.per_kernel_rows("gemma", dir_rel)
        summary_row = next(r for r in rows if r["lane"].endswith("summary"))
        self.assertEqual(summary_row["verdict"], "blocked")
        self.assertIn("lm_head_prefill", summary_row["blocker"])
        sample_row = next(r for r in rows if r["lane"].endswith("sample"))
        self.assertEqual(sample_row["verdict"], "bound")
        lm_row = next(r for r in rows if r["lane"].endswith("lm_head_prefill"))
        self.assertEqual(lm_row["verdict"], "blocked")
        self.assertEqual(lm_row["blocker"], "shape_exceeds_d2h_limit")

    def test_per_kernel_dispatch_timed_out_annotation(self) -> None:
        dir_rel = self.module.GEMMA_PER_KERNEL_DIR
        self._write(f"{dir_rel}/summary.json", {"kernels": []})
        self._write(
            f"{dir_rel}/gemv.json",
            {"verdict": "blocked", "blocker": "dispatch_timed_out", "dispatchTimedOut": True},
        )
        with mock.patch.object(self.module, "REPO_ROOT", self.tmp):
            rows = self.module.per_kernel_rows("gemma", dir_rel)
        gemv_row = next(r for r in rows if r["lane"].endswith("gemv"))
        self.assertIn("dispatchTimedOut", gemv_row["blocker"])

    def test_phase7_in_progress_when_last_complete_advances(self) -> None:
        progress_rel = f"{self.module.GEMMA_PHASE7_SESSION_DIR}/progress.jsonl"
        events = [
            {"phase": "hostplan_launch_complete", "launchIndex": 25, "target": "rmsnorm_prefill", "status": "succeeded"},
            {"phase": "hostplan_launch_complete", "launchIndex": 26, "target": "tiled_31b", "status": "succeeded"},
            {"phase": "hostplan_launch_start", "launchIndex": 27, "target": "rope"},
        ]
        p = self.tmp / progress_rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(json.dumps(e) for e in events) + "\n")
        with mock.patch.object(self.module, "REPO_ROOT", self.tmp):
            row = self.module.phase7_row()
        self.assertEqual(row["verdict"], "in_progress")
        self.assertIn("lastCompleteLaunch=26", row["blocker"])

    def test_phase7_blocked_when_block_after_last_complete(self) -> None:
        progress_rel = f"{self.module.GEMMA_PHASE7_SESSION_DIR}/progress.jsonl"
        events = [
            {"phase": "hostplan_launch_complete", "launchIndex": 25, "target": "rmsnorm_prefill", "status": "succeeded"},
            {"phase": "hostplan_launch_blocked", "launchIndex": 26, "target": "tiled_31b", "error": "tiled_q4k_gemv_runtime_failed"},
        ]
        p = self.tmp / progress_rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(json.dumps(e) for e in events) + "\n")
        with mock.patch.object(self.module, "REPO_ROOT", self.tmp):
            row = self.module.phase7_row()
        self.assertEqual(row["verdict"], "blocked")
        self.assertIn("launch[26]", row["blocker"])
        self.assertIn("tiled_q4k_gemv_runtime_failed", row["blocker"])

    def test_qwen_multi_token_decode_blocked_when_partial(self) -> None:
        self._write(
            self.module.QWEN_MULTI_TOKEN_DECODE,
            {"boundKernelCount": 0, "kernelCompileDirs": ["a", "b", "c"]},
        )
        with mock.patch.object(self.module, "REPO_ROOT", self.tmp):
            row = self.module.qwen_multi_token_decode_row()
        self.assertEqual(row["verdict"], "blocked")
        self.assertEqual(row["blocker"], "boundKernelCount=0/3")

    def test_bounded_smoke_blocker_count(self) -> None:
        self._write(
            self.module.GEMMA_BOUNDED_SMOKE,
            {
                "status": "blocked",
                "blockers": [
                    {"class": "inference_evidence_gate.dispatch_evidence_lm_head_unbound"},
                    {"class": "manifest_kernel_dispatch_not_bound"},
                    {"class": "real_session_runtime_blocked"},
                ],
            },
        )
        with mock.patch.object(self.module, "REPO_ROOT", self.tmp):
            row = self.module.bounded_smoke_row()
        self.assertEqual(row["verdict"], "blocked")
        self.assertIn("inference_evidence_gate.dispatch_evidence_lm_head_unbound", row["blocker"])
        self.assertIn("(+2 more)", row["blocker"])

    def test_render_markdown_contains_marker(self) -> None:
        rows = [
            {"lane": "x", "artifact": "a/b.json", "verdict": "bound", "blocker": None, "artifactMtime": "t"},
            {"lane": "y", "artifact": "a/c.json", "verdict": "blocked", "blocker": "z", "artifactMtime": "t"},
        ]
        md = self.module.render_markdown(rows, "now")
        self.assertIn("✅ bound", md)
        self.assertIn("❌ blocked", md)
        self.assertIn("`a/b.json`", md)


if __name__ == "__main__":
    unittest.main()

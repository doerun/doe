"""Scheduler-level sample-feedback assertions for the af16 session runtime.

The runtime-scheduler artifact records bound sample feedback edges and the
transcript capture schedule before SDK execution. This test verifies that
when the artifact is present, the scheduler claims a coherent sample
feedback contract: every feedback edge's tokenBuffer matches a
generated_token emitter, the lm-head -> sample edge is materialized as a
logitsBuffer/logitsLaunchIndex pair on each token emitter, and supporting
activation/KV schedules are bound.

Real per-step transcript-feedback assertions wait on SDK execution evidence
and are not in this file.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


SCHEDULER_PATH = (
    REPO_ROOT
    / "bench/out/r3-1-31b-af16-hostplan-session/runtime-scheduler.json"
)


class RuntimeSchedulerSampleFeedbackTest(unittest.TestCase):
    def setUp(self) -> None:
        if not SCHEDULER_PATH.is_file():
            self.skipTest(
                f"runtime-scheduler artifact not present: {SCHEDULER_PATH}"
            )
        self.scheduler = json.loads(
            SCHEDULER_PATH.read_text(encoding="utf-8")
        )

    def test_top_level_status_bound(self) -> None:
        self.assertEqual(self.scheduler.get("status"), "bound")

    def test_sample_feedback_status_bound(self) -> None:
        feedback = self.scheduler.get("sampleFeedback") or {}
        self.assertEqual(feedback.get("status"), "bound")

    def test_sample_feedback_has_at_least_one_edge(self) -> None:
        edges = (
            self.scheduler.get("sampleFeedback", {}).get("edges") or []
        )
        self.assertGreater(len(edges), 0)
        for edge in edges:
            self.assertIsInstance(edge.get("fromLaunchIndex"), int)
            self.assertIsInstance(edge.get("toDecodeStepIndex"), int)
            token_buffer = edge.get("tokenBuffer")
            self.assertIsInstance(token_buffer, str)
            self.assertTrue(token_buffer)

    def test_transcript_capture_schedule_bound(self) -> None:
        sched = self.scheduler.get("transcriptCaptureSchedule") or {}
        self.assertEqual(sched.get("status"), "bound")
        self.assertGreater(int(sched.get("logitsEmitterCount") or 0), 0)
        self.assertGreater(int(sched.get("tokenEmitterCount") or 0), 0)

    def test_generated_token_emitters_reference_logits(self) -> None:
        emitters = (
            self.scheduler.get("transcriptCaptureSchedule", {})
            .get("emitters")
            or []
        )
        token_emitters = [
            entry for entry in emitters
            if entry.get("kind") == "generated_token"
        ]
        self.assertGreater(len(token_emitters), 0)
        for emitter in token_emitters:
            logits_buffer = emitter.get("logitsBuffer")
            self.assertIsInstance(logits_buffer, str)
            self.assertTrue(logits_buffer)
            self.assertIsInstance(emitter.get("logitsLaunchIndex"), int)

    def test_feedback_edges_match_token_emitter_buffers(self) -> None:
        edges = (
            self.scheduler.get("sampleFeedback", {}).get("edges") or []
        )
        emitters = (
            self.scheduler.get("transcriptCaptureSchedule", {})
            .get("emitters")
            or []
        )
        token_emitter_keys = {
            (str(entry.get("buffer")), int(entry.get("launchIndex") or -1))
            for entry in emitters
            if entry.get("kind") == "generated_token"
        }
        for edge in edges:
            key = (
                str(edge.get("tokenBuffer")),
                int(edge.get("fromLaunchIndex") or -1),
            )
            self.assertIn(key, token_emitter_keys)

    def test_activation_routing_bound(self) -> None:
        routing = self.scheduler.get("activationRouting") or {}
        self.assertEqual(routing.get("status"), "bound")

    def test_kv_cache_schedule_bound(self) -> None:
        kv = self.scheduler.get("kvCacheSchedule") or {}
        self.assertEqual(kv.get("status"), "bound")


if __name__ == "__main__":
    unittest.main()

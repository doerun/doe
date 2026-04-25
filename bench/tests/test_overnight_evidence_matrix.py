"""Tests for the overnight evidence-matrix orchestrator.

Synthetic cells use simple `python -c '...'` invocations to exercise the
orchestrator's contract without depending on any heavy runner. Cases:
mixed success+failure, timeout enforcement, exception isolation,
resume-skips-succeeded, dry-run-noops.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR = REPO_ROOT / "bench" / "runners" / "overnight_evidence_matrix.py"
GENERATE_31B_MATRIX = REPO_ROOT / "bench" / "tools" / "generate_overnight_31b_matrix.py"


def _python_cell(cell_id: str, lane: str, body: str, **extra) -> dict:
    return {
        "id": cell_id,
        "lane": lane,
        "cmd": [sys.executable, "-c", body],
        **extra,
    }


def _write_matrix(path: Path, cells: list[dict]) -> None:
    path.write_text(json.dumps({"cells": cells}, indent=2), encoding="utf-8")


def _run_orchestrator(matrix: Path, out: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ORCHESTRATOR), "--matrix", str(matrix), "--out", str(out), *extra],
        check=False,
        capture_output=True,
        text=True,
    )


class MixedSuccessAndFailure(unittest.TestCase):
    def test_orchestrator_isolates_failures_and_records_per_cell_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            matrix = tmp / "matrix.json"
            out = tmp / "batch"
            cells = [
                _python_cell("ok-1", "light", "print('ok-1'); import sys; sys.exit(0)"),
                _python_cell("fail-1", "light", "import sys; sys.exit(7)"),
                _python_cell("ok-2", "light", "print('ok-2')"),
            ]
            _write_matrix(matrix, cells)

            res = _run_orchestrator(matrix, out)
            # Exit 3 because at least one cell failed.
            self.assertEqual(res.returncode, 3, msg=res.stderr)

            summary = json.loads((out / "batch.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["byStatus"].get("succeeded"), 2)
            self.assertEqual(summary["byStatus"].get("failed"), 1)

            # Per-cell receipts exist with correct shapes.
            ok_done = json.loads((out / "cells" / "ok-1" / "done.json").read_text())
            fail_done = json.loads((out / "cells" / "fail-1" / "done.json").read_text())
            self.assertEqual(ok_done["status"], "succeeded")
            self.assertEqual(ok_done["exitCode"], 0)
            self.assertEqual(fail_done["status"], "failed")
            self.assertEqual(fail_done["exitCode"], 7)
            # Stdout was captured to disk.
            self.assertEqual(
                (out / "cells" / "ok-1" / "stdout.log").read_text().strip(),
                "ok-1",
            )


class TimeoutEnforcement(unittest.TestCase):
    def test_orchestrator_kills_cell_at_timeout_and_records_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            matrix = tmp / "matrix.json"
            out = tmp / "batch"
            cells = [
                _python_cell(
                    "slow",
                    "light",
                    "import time; time.sleep(30)",
                    timeoutSeconds=1,
                ),
            ]
            _write_matrix(matrix, cells)

            res = _run_orchestrator(matrix, out)
            self.assertEqual(res.returncode, 3, msg=res.stderr)

            done = json.loads((out / "cells" / "slow" / "done.json").read_text())
            self.assertEqual(done["status"], "timeout")
            self.assertIsNone(done["exitCode"])
            # Elapsed should be near the timeout, not 30s.
            self.assertLess(done["elapsedSeconds"], 5.0)


class ResumeSkipsSucceeded(unittest.TestCase):
    def test_resume_skips_succeeded_cells_and_reruns_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            matrix = tmp / "matrix.json"
            out = tmp / "batch"
            cells = [
                _python_cell("ok-1", "light", "print('ok-1')"),
                _python_cell("flaky", "light", "import sys; sys.exit(1)"),
            ]
            _write_matrix(matrix, cells)

            # First run: ok-1 succeeds, flaky fails.
            res1 = _run_orchestrator(matrix, out)
            self.assertEqual(res1.returncode, 3)
            done1 = json.loads((out / "cells" / "flaky" / "done.json").read_text())
            self.assertEqual(done1["status"], "failed")
            ok_completed_at = json.loads(
                (out / "cells" / "ok-1" / "done.json").read_text()
            )["completedAtUnix"]

            # Mutate the matrix so flaky now succeeds, ok-1 unchanged.
            cells[1]["cmd"] = [sys.executable, "-c", "print('flaky-now-ok')"]
            _write_matrix(matrix, cells)

            # Resume: ok-1 already succeeded, should be skipped (completedAtUnix unchanged).
            res2 = _run_orchestrator(matrix, out, "--resume", str(out))
            self.assertEqual(res2.returncode, 0, msg=res2.stderr)
            ok_after = json.loads(
                (out / "cells" / "ok-1" / "done.json").read_text()
            )["completedAtUnix"]
            self.assertEqual(ok_after, ok_completed_at, "ok-1 should not have been rerun")
            done2 = json.loads((out / "cells" / "flaky" / "done.json").read_text())
            self.assertEqual(done2["status"], "succeeded")


class ExpectedReceiptGate(unittest.TestCase):
    def test_cell_exit_zero_but_missing_receipt_downgrades_to_missing_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            matrix = tmp / "matrix.json"
            out = tmp / "batch"
            phantom_receipt = tmp / "does-not-exist.json"
            cells = [
                _python_cell(
                    "lies",
                    "light",
                    "print('claims success but writes no receipt')",
                    expectSuccessReceiptPath=str(phantom_receipt),
                ),
            ]
            _write_matrix(matrix, cells)

            res = _run_orchestrator(matrix, out)
            self.assertEqual(res.returncode, 3)
            done = json.loads((out / "cells" / "lies" / "done.json").read_text())
            self.assertEqual(done["status"], "missing_receipt")
            self.assertEqual(done["exitCode"], 0)
            self.assertFalse(done["expectedReceiptExists"])

    def test_receipt_json_mismatch_downgrades_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            matrix = tmp / "matrix.json"
            out = tmp / "batch"
            receipt = tmp / "receipt.json"
            cells = [
                _python_cell(
                    "bad-receipt",
                    "light",
                    (
                        "from pathlib import Path; "
                        f"Path({str(receipt)!r}).write_text("
                        "'{\"status\":\"simulator_failed\"}')"
                    ),
                    expectSuccessReceiptPath=str(receipt),
                    expectJson=[{"path": "status", "equals": "output_ready"}],
                ),
            ]
            _write_matrix(matrix, cells)

            res = _run_orchestrator(matrix, out)
            self.assertEqual(res.returncode, 3)
            done = json.loads((out / "cells" / "bad-receipt" / "done.json").read_text())
            self.assertEqual(done["status"], "receipt_mismatch")
            self.assertEqual(done["exitCode"], 0)
            self.assertIn("status", done["expectedJsonFailures"][0])


class DependencyGate(unittest.TestCase):
    def test_dependent_cell_blocks_when_producer_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            matrix = tmp / "matrix.json"
            out = tmp / "batch"
            cells = [
                _python_cell("producer", "webgpu_heavy", "import sys; sys.exit(9)"),
                _python_cell(
                    "consumer",
                    "webgpu_heavy",
                    "print('should not run')",
                    dependsOn=["producer"],
                ),
            ]
            _write_matrix(matrix, cells)

            res = _run_orchestrator(matrix, out, "--max-webgpu-heavy", "1")
            self.assertEqual(res.returncode, 3)
            producer = json.loads((out / "cells" / "producer" / "done.json").read_text())
            consumer = json.loads((out / "cells" / "consumer" / "done.json").read_text())
            self.assertEqual(producer["status"], "failed")
            self.assertEqual(consumer["status"], "blocked")
            self.assertEqual(consumer["blockedBy"], ["producer:failed"])
            self.assertEqual(
                (out / "cells" / "consumer" / "stdout.log").read_text()
                if (out / "cells" / "consumer" / "stdout.log").is_file()
                else "",
                "",
            )


class CellCwd(unittest.TestCase):
    def test_cell_can_run_from_explicit_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            matrix = tmp / "matrix.json"
            out = tmp / "batch"
            cell_cwd = tmp / "cell-cwd"
            cell_cwd.mkdir()
            sentinel = cell_cwd / "sentinel.txt"
            cells = [
                _python_cell(
                    "cwd-cell",
                    "light",
                    "from pathlib import Path; Path('sentinel.txt').write_text('ok')",
                    cwd=str(cell_cwd),
                    expectSuccessReceiptPath=str(sentinel),
                ),
            ]
            _write_matrix(matrix, cells)

            res = _run_orchestrator(matrix, out)
            self.assertEqual(res.returncode, 0, msg=res.stderr)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "ok")
            done = json.loads((out / "cells" / "cwd-cell" / "done.json").read_text())
            self.assertEqual(done["cwd"], str(cell_cwd))


class DryRunNoExecution(unittest.TestCase):
    def test_dry_run_lists_cells_and_exits_zero_without_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            matrix = tmp / "matrix.json"
            out = tmp / "batch"
            cells = [
                _python_cell(
                    "side-effect",
                    "light",
                    f"open({str(tmp / 'sentinel')!r}, 'w').write('ran')",
                ),
            ]
            _write_matrix(matrix, cells)

            res = _run_orchestrator(matrix, out, "--dry-run")
            self.assertEqual(res.returncode, 0, msg=res.stderr)
            self.assertIn("side-effect", res.stdout)
            # The cell did not execute, so the sentinel was never created.
            self.assertFalse((tmp / "sentinel").exists())
            # No batch.json gets written under dry-run.
            self.assertFalse((out / "batch.json").exists())


class Generate31BMatrix(unittest.TestCase):
    def test_lane_a_uses_31b_reference_runtime_and_isolated_hostplan_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            batch = tmp / "batch"
            matrix = tmp / "matrix.json"

            res = subprocess.run(
                [
                    sys.executable,
                    str(GENERATE_31B_MATRIX),
                    "--batch-dir",
                    str(batch),
                    "--out",
                    str(matrix),
                    "--smoke-depths",
                    "1",
                    "--include-lane-a",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, msg=res.stderr)

            cells = json.loads(matrix.read_text(encoding="utf-8"))["cells"]
            by_id = {cell["id"]: cell for cell in cells}
            self.assertEqual(len(cells), 7)
            self.assertNotIn("light-31b-runtime-receipt-refresh", by_id)

            a1 = by_id["wg-31b-doppler-reference-bundle"]
            self.assertEqual(a1["lane"], "webgpu_heavy")
            self.assertEqual(a1["cwd"], "/home/x/deco/doppler")
            self.assertIn(
                "/home/x/deco/doppler/reports/program-bundles/doe-overnight/",
                a1["expectSuccessReceiptPath"],
            )
            runtime_index = a1["cmd"].index("--runtime-config") + 1
            runtime_config = json.loads(a1["cmd"][runtime_index])
            self.assertEqual(
                runtime_config["inference"]["largeWeights"]["gpuResidentOverrides"],
                [],
            )
            self.assertEqual(
                runtime_config["inference"]["session"]["decodeLoop"]["batchSize"],
                1,
            )

            a2 = by_id["csl-31b-L001-decode-truncated-size1024"]
            self.assertEqual(a2["dependsOn"], ["wg-31b-doppler-reference-bundle"])
            self.assertEqual(a2["expectJson"], [{"path": "status", "equals": "output_ready"}])
            a2_hostplan = a2["cmd"][a2["cmd"].index("--hostplan-bundle-root") + 1]
            self.assertTrue(a2_hostplan.endswith("/csl-31b-L001-decode-truncated-size1024/hostplan"))

            truncated = by_id["csl-3-1b-L001-decode-truncated-size1024"]
            self.assertEqual(
                truncated["expectJson"],
                [{"path": "status", "equals": "output_ready"}],
            )
            truncated_hostplan = truncated["cmd"][
                truncated["cmd"].index("--hostplan-bundle-root") + 1
            ]
            self.assertTrue(
                truncated_hostplan.endswith("/csl-3-1b-L001-decode-truncated-size1024/hostplan")
            )


if __name__ == "__main__":
    unittest.main()

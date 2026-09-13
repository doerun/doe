"""Physical sampling requires distinct, successful, ordered child identities."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from bench.lib.compute_program_process import run_tracked_process
from bench.runners.run_compute_program_calibration import read_pairs


@unittest.skipUnless(sys.platform == 'linux', 'Calibration requires Linux process identity')
class ProcessIdentityTests(unittest.TestCase):
    def test_capture_and_reject_replayed_or_reordered_processes(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            directory = Path(scratch)
            paths = [directory / f'heat_diffusion.{v}.process-00.json'
                     for v in ('baseline', 'candidate')]
            for path in paths:
                command = [sys.executable, '-c',
                           'import pathlib,sys; pathlib.Path(sys.argv[1]).write_text("{}")', str(path)]
                result = run_tracked_process(command, directory, dict(os.environ),
                                             10, Path(f'{path}.process.json'), path)
                self.assertEqual(result.returncode, 0)
            pairs = read_pairs(directory, 'heat_diffusion', 0, 1)
            self.assertNotEqual(*pairs[0].execution_ids)
            second = Path(f'{paths[1]}.process.json')
            data = json.loads(second.read_text())
            data['startedMonotonicNs'] = 0
            second.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'alternating order'):
                read_pairs(directory, 'heat_diffusion', 0, 1)

    def test_timeout_retains_failure_without_a_successful_report(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            directory = Path(scratch)
            output, identity = directory / 'report.json', directory / 'process.json'
            with self.assertRaises(subprocess.TimeoutExpired):
                run_tracked_process([sys.executable, '-c', 'import time; time.sleep(10)'],
                                    directory, dict(os.environ), .05, identity, output)
            row = json.loads(identity.read_text())
            self.assertLess(row['exitCode'], 0)
            self.assertIsNone(row['reportHash'])


if __name__ == '__main__':
    unittest.main()

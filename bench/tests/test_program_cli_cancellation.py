"""The public program command must deliver cancellation to its executor."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE_TIMEOUT_SECONDS = 10
PROBE_INTERVAL_SECONDS = 0.01


@unittest.skipIf(sys.platform == 'win32', 'POSIX process signal contract')
class ProgramCliCancellationTests(unittest.TestCase):
    def test_sigterm_reaches_executor_and_retains_cancelled_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ready = root / 'ready'
            outcome = root / 'outcome'
            child = root / 'executor.py'
            child.write_text('''import os, signal, sys
from pathlib import Path
def cancel(_signal, _frame):
    Path(sys.argv[2]).write_text('cancelled')
    raise SystemExit(0)
signal.signal(signal.SIGTERM, cancel)
Path(sys.argv[1]).write_text(str(os.getpid()))
signal.pause()
''', encoding='utf-8')
            launch = '''import sys
from bench import cli
cli.PROGRAM_COMMANDS['candidate'] = (EXECUTOR_ARGUMENTS_TOKEN, 'cancellation probe')
sys.argv = ['bench/cli.py', 'program', 'candidate']
raise SystemExit(cli.main())
'''.replace('EXECUTOR_ARGUMENTS_TOKEN', repr([sys.executable, str(child), str(ready), str(outcome)]))
            process = subprocess.Popen([sys.executable, '-c', launch], cwd=ROOT,
                                       env={**os.environ, 'PYTHONPATH': os.pathsep.join(
                                           [str(ROOT), str(ROOT / 'bench')])},
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            executor_pid = None
            try:
                deadline = time.monotonic() + PROBE_TIMEOUT_SECONDS
                while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(PROBE_INTERVAL_SECONDS)
                self.assertTrue(ready.exists(), process.stderr.read().decode()
                                if process.poll() is not None else 'Executor did not start')
                executor_pid = int(ready.read_text())
                process.send_signal(signal.SIGTERM)
                process.wait(timeout=PROBE_TIMEOUT_SECONDS)
                self.assertTrue(outcome.exists(), 'CLI cancellation left its executor running')
                self.assertEqual(outcome.read_text(), 'cancelled')
                self.assertEqual(executor_pid, process.pid)
            finally:
                if executor_pid and executor_pid != process.pid:
                    try:
                        os.kill(executor_pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                if process.poll() is None:
                    process.kill()
                    process.wait()
                process.stderr.close()


if __name__ == '__main__':
    unittest.main()

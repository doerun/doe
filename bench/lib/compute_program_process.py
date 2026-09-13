"""Retain actual fresh-process identity outside the application's timing scope."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from bench.lib.hash_utils import file_sha256


def run_tracked_process(
    command: list[str], cwd: Path, environment: dict[str, str],
    timeout: float, identity: Path, output: Path,
) -> subprocess.CompletedProcess[str]:
    boot_id = Path('/proc/sys/kernel/random/boot_id').read_text(encoding='utf-8').strip()
    started = time.monotonic_ns()
    with subprocess.Popen(command, cwd=cwd, env=environment, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            stdout, stderr = process.communicate()
            exc.stdout, exc.stderr = stdout, stderr
            raise
        finally:
            row = {'schemaVersion': 1, 'kind': 'compute-program-process',
                   'bootId': boot_id, 'pid': process.pid, 'startedMonotonicNs': started,
                   'completedMonotonicNs': time.monotonic_ns(), 'exitCode': process.returncode,
                   'reportPath': str(output.resolve()),
                   'reportHash': file_sha256(output) if output.is_file() else None}
            identity.write_text(json.dumps(row, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)

"""Verify the service's kernel limits before entering the candidate namespace."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    policy_path, admission_path, *command = sys.argv[1:]
    policy = json.loads(Path(policy_path).read_text(encoding='utf-8'))
    unified = [line[3:] for line in Path('/proc/self/cgroup').read_text().splitlines()
               if line.startswith('0::/')]
    if len(unified) != 1:
        raise ValueError('Candidate isolation requires a unified cgroup v2 hierarchy')
    group = Path('/sys/fs/cgroup') / unified[0].lstrip('/')
    expected = {'memory.max': str(policy['maximumHostMemoryBytes']),
                'memory.swap.max': '0', 'pids.max': str(policy['maximumTasks'])}
    observed = {key: (group / key).read_text().strip() for key in expected}
    if observed != expected:
        raise ValueError(f'Candidate cgroup limits were not enforced: {observed}')
    Path(admission_path).write_text(json.dumps(observed, indent=2, sort_keys=True) + '\n',
                                    encoding='utf-8')
    os.execv(command[0], command)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())

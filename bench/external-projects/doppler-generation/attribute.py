"""Summarize scoped API intervals without adding overlapping completion waits."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


def union_ms(events: list[dict]) -> float:
    intervals = sorted((event['startedMs'], event['endedMs']) for event in events)
    total = 0.0
    right = float('-inf')
    for start, end in intervals:
        if end < start:
            raise ValueError('An observed API interval ends before it begins')
        total += max(0, end - max(start, right))
        right = max(right, end)
    return total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--profiles', type=Path, nargs='+', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    profiles = []
    for path in args.profiles:
        receipt = json.loads(path.read_text())
        if not receipt['passed'] or receipt['mode'] != 'profile':
            raise ValueError(f'Unqualified diagnostic profile: {path}')
        phases = defaultdict(list)
        for event in receipt['phaseEvents']:
            phases[event['phase']].append(event)
        rows = []
        for phase, events in phases.items():
            methods = defaultdict(list)
            for event in events:
                methods[event['method']].append(event)
            sizes = defaultdict(list)
            for event in methods['createBuffer']:
                sizes[event['bytes']].append(event)
            rows.append({'phase': phase, 'allObservedApiIntervalUnionMs': union_ms(events),
                'methods': [{'method': name, 'calls': len(spans), 'intervalUnionMs': union_ms(spans)}
                            for name, spans in methods.items() if spans],
                'bufferSizes': [{'bytes': size, 'calls': len(spans), 'intervalUnionMs': union_ms(spans)}
                                for size, spans in sorted(sizes.items())]})
        profiles.append({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                         'lane': receipt['lane'], 'loadMs': receipt['loadMs'],
                         'cleanup': receipt['cleanup'], 'phases': rows})
    args.out.write_text(json.dumps({'schemaVersion': 1, 'classification': 'diagnostic',
        'scope': 'API observer intervals include host work and overlapping completion promises. Each union is distinct and is not additive across methods or phases. No pure GPU, native allocation-count, physical GPU residency, or performance-promotion claim.',
        'profiles': profiles}, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

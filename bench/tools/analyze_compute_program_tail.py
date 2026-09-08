"""Join host events to complete invocations; keep percentile and causal evidence distinct."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from bench.runners.run_compute_program_tail_experiment import write_tsv


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding='utf-8') as stream:
        return list(csv.DictReader(stream, delimiter='\t'))


def correlate(path: Path) -> list[dict[str, Any]]:
    report = json.loads(path.read_text(encoding='utf-8'))
    identities = read_tsv(Path(f'{path}.invocations.tsv'))
    events = read_tsv(Path(f'{path}.events.tsv'))
    invocations = {value['invocationId']: value for value in identities}
    if len(invocations) != len(identities):
        raise ValueError('Duplicate diagnostic invocation identity')
    gc_events = [event for event in events if event['event'] == 'gc']
    rows = []
    for sample in report['samples']:
        receipt = sample['receipt']
        identity = f"{receipt['programInstance']}:{receipt['run']}"
        invocation = invocations[identity]
        start, end = float(invocation['startMs']), float(invocation['endMs'])
        calls = [event for event in events if event['invocationOrdinal'] == invocation['ordinal']
                 and event['kind'] == '0' and event['event'] != 'invocation']
        encode_calls = [event for event in calls if event['event'].startswith(('encoder.', 'pass.', 'device.createCommandEncoder'))]
        duration = lambda event: float(event['endMs']) - float(event['startMs'])
        gc_overlap = sum(max(0, min(end, float(event['endMs'])) - max(start, float(event['startMs'])))
                         for event in gc_events)
        slowest = max(calls, key=duration)
        slowest_encode = max(encode_calls, key=duration)
        rows.append({
            'artifactPath': str(path), 'invocationId': identity, 'run': receipt['run'],
            'wallMs': sample['wallMs'], 'cpuMs': sample['cpuMs'], **receipt['timingMs'],
            'gcOverlapMs': gc_overlap,
            'heapUsedBefore': invocation['heapUsedBefore'], 'heapUsedAfter': invocation['heapUsedAfter'],
            'voluntaryContextSwitches': invocation['voluntaryContextSwitches'],
            'involuntaryContextSwitches': invocation['involuntaryContextSwitches'],
            'slowestSyncCall': slowest['event'], 'slowestSyncCallMs': duration(slowest),
            'slowestEncodeCall': slowest_encode['event'], 'slowestEncodeCallMs': duration(slowest_encode),
            'encodeSyncCallsMs': sum(duration(event) for event in encode_calls),
            'claimStatus': 'diagnostic',
        })
    return rows


def join_storage(native_path: Path, report_path: Path, output: Path) -> None:
    """Join serial native encoder loans to observed host creation and invocation order."""
    report = json.loads(report_path.read_text(encoding='utf-8'))
    invocations = read_tsv(Path(f'{report_path}.invocations.tsv'))
    events = read_tsv(Path(f'{report_path}.events.tsv'))
    records = read_tsv(native_path)
    takes = [row for row in records if row['event'] == 'take']
    samples = [report['cold'], *report['warmups'], *report['samples'], *report['lifecycleRuns']]
    if not (len(takes) == len(invocations) == len(samples)):
        raise ValueError('Native encoder/invocation counts differ; cannot infer the identity join')
    for invocation, sample in zip(invocations, samples, strict=True):
        calls = [event for event in events if event['event'] == 'device.createCommandEncoder'
                 and event['invocationOrdinal'] == invocation['ordinal']]
        receipt = sample['receipt']
        if len(calls) != 1 or invocation['invocationId'] != f"{receipt['programInstance']}:{receipt['run']}":
            raise ValueError('Storage correlation requires one encoder per serial invocation')
    index = -1
    joined = []
    for record in records:
        if record['event'] == 'take':
            index += 1
        if index < 0 or record['encoder'] != takes[index]['encoder']:
            raise ValueError('Native allocation escaped the current encoder observation')
        joined.append({'invocationId': invocations[index]['invocationId'], **record})
    write_tsv(output, joined)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, help='Directory containing diagnostic process reports')
    args = parser.parse_args()
    rows = []
    for path in sorted(args.directory.glob('*.process-*.json')):
        if len(path.name.split('.')) == 4:
            rows.extend(correlate(path))
    if not rows:
        raise ValueError('No complete diagnostic invocations')
    write_tsv(args.directory / 'correlated-invocations.tsv', rows)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

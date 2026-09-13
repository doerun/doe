"""Describe ordered process samples without changing performance admission."""
from __future__ import annotations

import collections
import math
import statistics
from typing import Any

from bench.runners.run_compute_program_tail_experiment import PHASES

METRICS = ('wallMs', 'cpuMs', *PHASES, 'gpuMs',
           'outsideReceiptMs', 'unassignedReceiptMs')


def sample_costs(sample: dict[str, Any]) -> dict[str, float | None]:
    """Keep overlapping GPU time separate from host timing decomposition."""
    timing = sample['receipt']['timingMs']
    result = {key: float(sample[key]) for key in ('wallMs', 'cpuMs')}
    result.update({key: float(timing[key]) for key in PHASES})
    if any(not math.isfinite(value) or value < 0 for value in result.values()):
        raise ValueError('Sample costs must be finite and nonnegative')
    gpu = sample['receipt'].get('gpuTiming')
    result['gpuMs'] = gpu['elapsedNs'] / 1_000_000 if gpu else None
    result['outsideReceiptMs'] = result['wallMs'] - result['total']
    result['unassignedReceiptMs'] = result['total'] - sum(
        result[key] for key in PHASES if key != 'total')
    return result


def process_blocks(report: dict[str, Any], blocks: int) -> list[dict[str, Any]]:
    """Partition every timed invocation in order, retaining uneven last blocks."""
    samples = report['samples']
    if not 2 <= blocks <= len(samples):
        raise ValueError('Require at least two nonempty sample blocks')
    if report['status'] != 'passed' or report['phase'] != 'measure':
        raise ValueError('Resolution analysis requires a passed measured process')
    first = report['cold']['receipt']
    sequence = [report['cold'], *report['warmups'], *samples]
    for run, sample in enumerate(sequence, 1):
        receipt = sample['receipt']
        if (receipt['run'] != run or not sample['oracle']['passed']
                or any(receipt[key] != first[key] for key in (
                    'programInstance', 'programHash', 'execution',
                    'dispatchCount', 'submissionCount', 'readbackPath',
                    'completionMode'))):
            raise ValueError('Sample sequence changed identity, work, or ordering')
    rows = []
    for index in range(blocks):
        start, end = index * len(samples) // blocks, (index + 1) * len(samples) // blocks
        costs = [sample_costs(sample) for sample in samples[start:end]]
        for metric in METRICS:
            values = [sample[metric] for sample in costs]
            if any(value is None for value in values):
                if not all(value is None for value in values):
                    raise ValueError('Measurement availability changed inside a block')
                median = None
            else:
                median = statistics.median(values)
            rows.append({'block': index, 'firstRun': samples[start]['receipt']['run'],
                         'lastRun': samples[end - 1]['receipt']['run'],
                         'samples': end - start, 'metric': metric, 'medianMs': median})
    return rows


def summarize_blocks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarize processes equally; no invocation-level confidence is inferred."""
    groups: dict[tuple[str, str, str], dict[str, list[dict[str, Any]]]] = {}
    for row in rows:
        key = row['application'], row['treatment'], row['metric']
        groups.setdefault(key, {}).setdefault(row['process'], []).append(row)
    summary = []
    for (application, treatment, metric), processes in sorted(groups.items()):
        ratios, first, last = [], [], []
        for values in processes.values():
            ordered = sorted(values, key=lambda row: row['block'])
            if [row['block'] for row in ordered] != list(range(len(ordered))):
                raise ValueError('Incomplete or duplicated process blocks')
            before, after = ordered[0]['medianMs'], ordered[-1]['medianMs']
            if before is not None and after is not None:
                first.append(before)
                last.append(after)
                if before > 0:
                    ratios.append(after / before)
        summary.append({'application': application, 'treatment': treatment,
                        'metric': metric, 'processes': len(processes),
                        'firstBlockMedianMs': statistics.median(first) if first else None,
                        'lastBlockMedianMs': statistics.median(last) if last else None,
                        'medianLastOverFirst': statistics.median(ratios) if ratios else None,
                        'decreasedProcesses': sum(ratio < 1 for ratio in ratios),
                        'ratioProcesses': len(ratios)})
    return summary


def cpu_profile_rows(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Attribute V8 self samples; these include the harness and startup."""
    nodes = {node['id']: node['callFrame'] for node in profile['nodes']}
    samples, deltas = profile['samples'], profile['timeDeltas']
    if len(samples) != len(deltas) or not samples:
        raise ValueError('CPU profile requires matching nonempty samples and deltas')
    groups: dict[tuple[str, str, int], list[float]] = collections.defaultdict(list)
    for sample, delta in zip(samples, deltas, strict=True):
        if sample not in nodes or not math.isfinite(delta):
            raise ValueError('Invalid CPU profile node or sampling delta')
        frame = nodes[sample]
        key = frame['functionName'], frame['url'], frame['lineNumber'] + 1
        groups[key].append(delta)
    return [{'function': key[0], 'url': key[1], 'line': key[2],
             'samples': len(values), 'signedDeltaUs': sum(values),
             'negativeDeltas': sum(value < 0 for value in values)}
            for key, values in sorted(groups.items(), key=lambda item: -len(item[1]))]

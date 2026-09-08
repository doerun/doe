"""Assess a frozen startup experiment without changing warm-tail acceptance."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import jsonschema

from bench.gates.compute_program_gate import startup_scope, validate_run
from bench.native_compare_modules.reporting import format_stats
from bench.runners.run_compute_program_tail_experiment import (
    PHASES, assert_control_identity, write_tsv,
)

ROOT = Path(__file__).resolve().parents[2]
VARIANTS = ('baseline', 'candidate')


def assess_application(
    groups: dict[str, list[dict[str, Any]]], application: str,
    startup: dict[str, Any], tail: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Apply startup improvement and independent latency/cost regression limits."""
    for reports in groups.values():
        if len(reports) != tail['expandedProcessPairs']:
            raise ValueError(
                'Startup assessment requires complete expanded pairs')
        for report in reports:
            if startup_scope(report) != startup['deviceStartupTimingScope']:
                raise ValueError(
                    'Startup assessment requires device-ready timing')
            if len(report['samples']) != tail['expandedTimedRuns']:
                raise ValueError(
                    'Startup assessment requires expanded samples')
    reference = groups['baseline'][0]
    for reports in groups.values():
        for report in reports:
            assert_control_identity(reference, report)
    rows = []
    statistics = {}
    process_latency = ('deviceStartupMs', 'preparationMs', 'teardownMs',
                       'coldWallMs')
    process_cost = ('peakProcessRssBytes', 'allocatedBufferBytes', 'coldCpuMs')
    for metric in (*process_latency, *process_cost, 'wallMs', 'cpuMs', *PHASES):
        statistics[metric] = {}
        for variant in VARIANTS:
            if metric == 'coldWallMs':
                values = [r['cold']['wallMs'] for r in groups[variant]]
            elif metric == 'coldCpuMs':
                values = [r['cold']['cpuMs'] for r in groups[variant]]
            elif metric in (*process_latency, *process_cost):
                values = [r[metric] for r in groups[variant]]
            else:
                values = [s['receipt']['timingMs'][metric]
                          if metric in PHASES else s[metric]
                          for r in groups[variant] for s in r['samples']]
            statistics[metric][variant] = format_stats(
                values, percentile_method='nearest-rank')
        quantiles = (startup['warmLatencyQuantiles']
                     if metric in ('wallMs', 'cpuMs', *PHASES)
                     else startup['startupQuantiles'])
        for quantile in quantiles:
            before, after = (statistics[metric][v][quantile] for v in VARIANTS)
            limit = (tail['maximumCostRegression']
                     if metric in (*process_cost, 'cpuMs')
                     else tail['maximumLatencyRegression'])
            rows.append({'application': application, 'metric': metric,
                         'quantile': quantile, 'baselineValue': before,
                         'candidateValue': after,
                         'maximumRegression': limit,
                         'regressionPassed': after <= before * (1 + limit)})
    before, after = (statistics['deviceStartupMs'][v]['p50Ms']
                     for v in VARIANTS)
    reduction = 1 - after / before
    improved = sum(a['deviceStartupMs'] < b['deviceStartupMs'] for b, a in zip(
        *(groups[v] for v in VARIANTS), strict=True)) / len(groups['baseline'])
    development = application == tail['developmentApplication']
    improvement_passed = (not development or (
        reduction >= startup['minimumStartupMedianReduction']
        and improved >= tail['minimumImprovedProcessFraction']))
    regressions_passed = all(row['regressionPassed'] for row in rows)
    return ({'application': application,
             'startupMedianReduction': reduction,
             'improvedStartupProcessFraction': improved,
             'improvementPassed': improvement_passed,
             'regressionsPassed': regressions_passed,
             'acceptancePassed': improvement_passed and regressions_passed,
             'claimStatus': startup['claimStatus']}, rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True,
                        help='Retained completed alternating cohort')
    parser.add_argument('--output', type=Path, required=True,
                        help='New directory; existing assessments are preserved')
    parser.add_argument('--policy', type=Path, required=True,
                        help='Frozen startup policy; tail policy resolved at root')
    args = parser.parse_args()
    startup = json.loads(args.policy.read_text(encoding='utf-8'))
    schema = json.loads((ROOT / 'config/compute-program-startup-experiment.schema.json')
                        .read_text(encoding='utf-8'))
    jsonschema.Draft202012Validator(schema).validate(startup)
    tail = json.loads((ROOT / startup['tailExperimentPolicy'])
                      .read_text(encoding='utf-8'))
    evaluation = json.loads(
        (args.input / 'policy.json').read_text(encoding='utf-8'))
    decisions, metrics = [], []
    for application in (tail['developmentApplication'], *tail['transferApplications']):
        groups = {}
        for variant in VARIANTS:
            groups[variant] = []
            for index in range(tail['expandedProcessPairs']):
                path = args.input / (
                    f'{application}.{variant}.process-{index:02d}.json')
                if Path(f'{path}.events.tsv').exists():
                    raise ValueError(
                        'Instrumented samples cannot establish benefit')
                groups[variant].append(validate_run(path, ROOT, evaluation))
        decision, rows = assess_application(groups, application, startup, tail)
        decisions.append(decision)
        metrics.extend(rows)
    args.output.mkdir(parents=True, exist_ok=False)
    write_tsv(args.output / 'acceptance.tsv', decisions)
    write_tsv(args.output / 'metrics.tsv', metrics)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

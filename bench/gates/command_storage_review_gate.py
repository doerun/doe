"""Require physical evidence replay and fresh executions across all series."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import jsonschema

from bench.gates.command_storage_experiment_gate import validate_experiment
from bench.gates.compute_program_gate import digest
from bench.runners.run_compute_program_calibration import load_policy

ROOT = Path(__file__).resolve().parents[2]
VARIANTS = ('baseline', 'candidate')


def verify_execution_sequence(executions: list[dict[str, Any]]) -> None:
    """Reject reused children and overlapping/reversed execution boundaries."""
    if not executions:
        raise ValueError('Review requires actual application child executions')
    seen = set()
    completed_by_boot: dict[str, int] = {}
    for item in executions:
        key = (item['bootId'], item['pid'], item['startedMonotonicNs'])
        if key in seen:
            raise ValueError('Evaluation and confirmation must use distinct physical processes')
        if (item['exitCode'] != 0 or
                item['completedMonotonicNs'] <= item['startedMonotonicNs'] or
                item['startedMonotonicNs'] < completed_by_boot.get(item['bootId'], 0)):
            raise ValueError('Application executions overlap, fail, or violate the declared order')
        seen.add(key)
        completed_by_boot[item['bootId']] = item['completedMonotonicNs']


def validate_execution_independence(path: Path) -> dict[str, Any]:
    """Check the complete series sequence, including the confirmation boundary.

    This is an additional admission invariant. Numerical/work replay remains
    required separately; child identities alone never establish a performance
    result. Historical measurements and their statistical procedure are intact.
    """
    report = load_policy(path, 'command-storage-experiment.schema.json')
    if report['status'] == 'incomplete' or report['error'] is not None:
        raise ValueError('Incomplete experiment cannot establish execution independence')
    calibration = load_policy(Path(report['calibration']['path']),
                              'compute-program-calibration-report.schema.json')
    policy = load_policy(Path(calibration['policy']['path']), 'compute-program-calibration.schema.json')
    startup = load_policy(ROOT / policy['startupPolicy'], 'compute-program-startup-experiment.schema.json')
    tail = load_policy(ROOT / startup['tailExperimentPolicy'], 'compute-program-tail-experiment.schema.json')
    decision = load_policy(ROOT / policy['decisionPolicy'], 'compute-program-decision.schema.json')
    executions = []
    for series in report['series']:
        for cohort in range(decision['cohorts']):
            directory = path.parent / series['name'] / f'round-{cohort:02d}'
            for index in range(tail['expandedProcessPairs']):
                order = VARIANTS if (cohort + index) % len(VARIANTS) == 0 else reversed(VARIANTS)
                order = tuple(order)
                for application in [tail['developmentApplication'], *tail['transferApplications']]:
                    for variant in order:
                        output = directory / f'{application}.{variant}.process-{index:02d}.json'
                        item = load_policy(Path(f'{output}.process.json'), 'compute-program-process.schema.json')
                        if item['reportPath'] != str(output.resolve()) or item['reportHash'] != digest(output):
                            raise ValueError('Child identity does not bind the reviewed report')
                        executions.append(item)
    verify_execution_sequence(executions)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True, help='Retained experiment report')
    parser.add_argument('--execution-only', action='store_true',
                        help='Run the additional freshness check; evidence replay is separately required')
    parser.add_argument('--require-accepted', action='store_true', help='Require a fully reviewed accepted proposal')
    args = parser.parse_args()
    if args.execution_only and args.require_accepted:
        parser.error('Acceptance requires full evidence replay and execution independence')
    try:
        path = args.report.resolve()
        if not args.execution_only:
            validate_experiment(path)
        report = validate_execution_independence(path)
        if args.require_accepted and report['status'] != 'accepted-proposal':
            raise ValueError(f"Candidate is {report['status']}; no accepted improvement")
    except (OSError, ValueError, jsonschema.ValidationError) as exc:
        print(str(exc))
        return 1
    if args.execution_only:
        print('Execution independence passed; full physical evidence replay is separately required')
    else:
        print(f"Reviewed experiment outcome: {report['status']}; accepted package unchanged")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

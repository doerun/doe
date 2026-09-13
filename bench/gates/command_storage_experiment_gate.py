"""Replay storage candidate decisions without treating completion as acceptance."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import jsonschema

from bench.gates.compute_program_calibration_gate import validate_calibration
from bench.lib.compute_program_package import load_qualification
from bench.lib.compute_program_uncertainty import candidate_verdict
from bench.runners.run_command_storage_experiment import (
    assess_series, validate_candidate, verify_references,
)
from bench.runners.run_compute_program_calibration import load_policy

ROOT = Path(__file__).resolve().parents[2]


def validate_experiment(path: Path) -> dict[str, Any]:
    report = load_policy(path, 'command-storage-experiment.schema.json')
    if report['status'] == 'incomplete' or report['error'] is not None:
        raise ValueError('Incomplete experiment cannot establish a candidate decision')
    verify_references([report['candidate'], report['calibration'], report['frozenInputs'],
                       *report['artifacts']])
    frozen = json.loads(Path(report['frozenInputs']['path']).read_text(encoding='utf-8'))
    verify_references(frozen)
    calibration = validate_calibration(Path(report['calibration']['path']))
    spec = validate_candidate(Path(report['candidate']['path']), calibration)
    policy = load_policy(Path(calibration['policy']['path']), 'compute-program-calibration.schema.json')
    startup = load_policy(ROOT / policy['startupPolicy'], 'compute-program-startup-experiment.schema.json')
    tail = load_policy(ROOT / startup['tailExperimentPolicy'], 'compute-program-tail-experiment.schema.json')
    decision = load_policy(ROOT / policy['decisionPolicy'], 'compute-program-decision.schema.json')
    previous = None
    for index, item in enumerate(report['series']):
        if item['name'] != ('evaluation', 'confirmation')[index]:
            raise ValueError('Experiment series identity changed')
        if index and previous != 'confirm':
            raise ValueError('Confirmation requires a passing independent evaluation')
        directory = path.parent / item['name']
        for cohort in range(decision['cohorts']):
            for variant in ('baseline', 'candidate'):
                qualified = load_qualification(Path(spec[f'{variant}Qualification']['path']), ROOT)
                measured = load_qualification(directory / f'round-{cohort:02d}' / variant /
                                              'package-inputs/summary.json', ROOT)
                if sorted(p['hash'] for p in qualified['packages']) != sorted(
                        p['hash'] for p in measured['packages']):
                    raise ValueError('Experiment measured an undeclared package')
        uncertainty, raw = assess_series(directory, startup, tail, decision, validate=True)
        verify_references([item['uncertainty'], item['rawAcceptance']])
        if uncertainty != load_policy(Path(item['uncertainty']['path']),
                                      'compute-program-uncertainty.schema.json'):
            raise ValueError('Candidate uncertainty differs from raw process pairs')
        actual = candidate_verdict(uncertainty, raw, tail,
                                   calibration_resolved=calibration['promotionResolutionPassed'])
        if actual != item['decision']:
            raise ValueError('Candidate decision differs from physical evidence')
        previous = actual['verdict']
    expected = 'accepted-proposal' if previous == 'confirm' and len(report['series']) == 2 else previous
    if report['status'] != expected:
        raise ValueError('Candidate status lacks the required evaluation and confirmation')
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True, help='Retained experiment report')
    parser.add_argument('--require-accepted', action='store_true', help='Fail unless independently confirmed')
    args = parser.parse_args()
    try:
        report = validate_experiment(args.report.resolve())
        if args.require_accepted and report['status'] != 'accepted-proposal':
            raise ValueError(f"Candidate is {report['status']}; no accepted improvement")
    except (OSError, ValueError, jsonschema.ValidationError) as exc:
        print(str(exc))
        return 1
    print(f"Verified experiment outcome: {report['status']}; accepted package unchanged")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

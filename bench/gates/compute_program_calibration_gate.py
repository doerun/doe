"""Reject candidate decisions that lack current, consistent A/A evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import jsonschema

from bench.gates.compute_program_gate import digest, validate_run
from bench.lib.compute_program_package import load_qualification
from bench.lib.compute_program_uncertainty import assess_uncertainty
from bench.runners.run_compute_program_calibration import assess_round, load_policy, read_pairs
from bench.runners.run_compute_program_tail_experiment import verify_cohort_policy

ROOT = Path(__file__).resolve().parents[2]
VARIANTS = ('baseline', 'candidate')


def validate_calibration(path: Path) -> dict[str, Any]:
    """Recompute eligibility from frozen inputs and complete physical cohorts."""
    report = load_policy(path, 'compute-program-calibration-report.schema.json')
    if report['status'] != 'consistent' or report['error'] is not None:
        raise ValueError('Calibration is incomplete or inconclusive; candidate decisions remain unavailable')
    for item in [report['policy'], report['frozenInputs'], *report['packages'], *report['artifacts']]:
        if digest(Path(item['path'])) != item['hash']:
            raise ValueError(f"Calibration artifact changed: {item['path']}")
    frozen = json.loads(Path(report['frozenInputs']['path']).read_text(encoding='utf-8'))
    for item in frozen:
        if digest(Path(item['path'])) != item['hash']:
            raise ValueError(f"Calibration acceptance input changed: {item['path']}")
    policy = load_policy(Path(report['policy']['path']), 'compute-program-calibration.schema.json')
    startup = load_policy(ROOT / policy['startupPolicy'], 'compute-program-startup-experiment.schema.json')
    tail = load_policy(ROOT / startup['tailExperimentPolicy'], 'compute-program-tail-experiment.schema.json')
    if len(report['rounds']) != policy['rounds']:
        raise ValueError('Calibration requires every declared round')
    violations = 0
    all_pairs = []
    expected_packages = sorted(p['hash'] for p in report['packages'])
    for index, result in enumerate(report['rounds']):
        if result['index'] != index or result['firstVariant'] != VARIANTS[index % len(VARIANTS)]:
            raise ValueError('Calibration order or round identity changed')
        cohort = path.parent / f'round-{index:02d}'
        for variant in VARIANTS:
            qualification = load_qualification(cohort / variant / 'package-inputs/summary.json', ROOT)
            if sorted(p['hash'] for p in qualification['packages']) != expected_packages:
                raise ValueError('Calibration packages differ between rounds or labels')
        evaluation = verify_cohort_policy(cohort, tail)
        rows = []
        for application in [tail['developmentApplication'], *tail['transferApplications']]:
            groups = {}
            for variant in VARIANTS:
                groups[variant] = []
                for process in range(tail['expandedProcessPairs']):
                    sample_path = cohort / f'{application}.{variant}.process-{process:02d}.json'
                    if Path(f'{sample_path}.events.tsv').exists():
                        raise ValueError('Diagnostic instrumentation cannot calibrate ordinary decisions')
                    measured = validate_run(sample_path, ROOT, evaluation)
                    if measured['policyHash'] != digest(cohort / 'policy.json'):
                        raise ValueError('Calibration process does not bind its declared policy')
                    groups[variant].append(measured)
            rows.extend(assess_round(groups, application, startup, tail))
            all_pairs.extend(read_pairs(cohort, application, index, tail['expandedProcessPairs'],
                                        require_identity=policy['schemaVersion'] == 3))
        passed = all(row['regressionPassed'] for row in rows)
        if result['regressionsPassed'] != passed:
            raise ValueError('Calibration decision differs from raw observations')
        violations += not passed
    if policy['schemaVersion'] == 3:
        if report['schemaVersion'] != 3 or not report['uncertainty']:
            raise ValueError('Calibration lacks the declared uncertainty assessment')
        decision = load_policy(ROOT / policy['decisionPolicy'], 'compute-program-decision.schema.json')
        if policy['rounds'] != decision['cohorts']:
            raise ValueError('Calibration and decision cohorts differ')
        actual = assess_uncertainty(all_pairs, tail, decision)
        retained = load_policy(Path(report['uncertainty']['path']), 'compute-program-uncertainty.schema.json')
        if digest(Path(report['uncertainty']['path'])) != report['uncertainty']['hash']:
            raise ValueError('Calibration uncertainty bytes changed')
        if actual != retained or not actual['nullConsistent']:
            raise ValueError('Calibration uncertainty disagrees with raw observations')
        if report['promotionResolutionPassed'] != actual['regressionBandsResolved']:
            raise ValueError('Calibration resolution differs from raw observations')
    elif violations > policy['maximumRegressionViolationRounds']:
        raise ValueError('A/A regression limits are unstable; candidate decisions remain unavailable')
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True, help='Retained calibration report')
    args = parser.parse_args()
    try:
        validate_calibration(args.report.resolve())
    except (OSError, ValueError, jsonschema.ValidationError) as exc:
        print(str(exc))
        return 1
    print('Calibration observations are consistent; no candidate is promoted')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

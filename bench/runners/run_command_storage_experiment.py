"""Evaluate a declared storage policy using qualified ordinary applications."""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from bench.gates.compute_program_calibration_gate import validate_calibration
from bench.gates.compute_program_gate import digest, validate_run
from bench.lib.compute_program_host import host_observation
from bench.lib.compute_program_package import load_qualification
from bench.lib.compute_program_uncertainty import assess_uncertainty, candidate_verdict
from bench.runners.run_compute_program_calibration import (
    assess_round, load_policy, read_pairs, reference, write_json,
)
from bench.runners.run_compute_program_tail_experiment import (
    summarize, verify_cohort_policy, write_tsv,
)

ROOT = Path(__file__).resolve().parents[2]
VARIANTS = ('baseline', 'candidate')


def verify_references(references: list[dict[str, str]]) -> None:
    for item in references:
        if digest(Path(item['path'])) != item['hash']:
            raise ValueError(f"Frozen experiment input changed: {item['path']}")


def validate_candidate(path: Path, calibration: dict[str, Any]) -> dict[str, Any]:
    """Bind the bounded policy and compiled library to the qualified archives."""
    spec = load_policy(path, 'command-storage-candidate.schema.json')
    verify_references([value for value in spec.values() if isinstance(value, dict)])
    baseline = load_qualification(Path(spec['baselineQualification']['path']), ROOT)
    candidate = load_qualification(Path(spec['candidateQualification']['path']), ROOT)
    if sorted(p['hash'] for p in baseline['packages']) != sorted(
            p['hash'] for p in calibration['packages']):
        raise ValueError('Candidate baseline differs from calibrated archives')
    if baseline['packages'][0]['hash'] != candidate['packages'][0]['hash']:
        raise ValueError('Storage policy experiment requires an unchanged wrapper archive')
    if candidate['hosts'][0]['libraryHash'] != spec['library']['hash']:
        raise ValueError('Qualified candidate differs from the declared build')
    retention = load_policy(Path(spec['retentionPolicy']['path']),
                            'native-command-storage-policy.schema.json')
    observation = load_policy(Path(spec['observationPolicy']['path']),
                              'native-command-storage-observation.schema.json')
    if retention['maxRetainedBytes'] != 0 or observation['mode'] != 'ordinary':
        raise ValueError('Declared control requires disabled retention and ordinary observation')
    if b'command_storage_released' in Path(spec['library']['path']).read_bytes():
        raise ValueError('Candidate library contains optional storage diagnostics')
    return spec


def assess_series(
    output: Path, startup: dict[str, Any], tail: dict[str, Any],
    decision: dict[str, Any], *, validate: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Reconstruct confidence and unchanged raw acceptance guards."""
    pairs, raw = [], []
    for cohort in range(decision['cohorts']):
        directory = output / f'round-{cohort:02d}'
        evaluation = json.loads((directory / 'policy.json').read_text(encoding='utf-8'))
        if validate:
            evaluation = verify_cohort_policy(directory, tail)
            for app in [tail['developmentApplication'], *tail['transferApplications']]:
                for variant in VARIANTS:
                    for i in range(tail['expandedProcessPairs']):
                        path = directory / f'{app}.{variant}.process-{i:02d}.json'
                        if Path(f'{path}.events.tsv').exists():
                            raise ValueError('Instrumented output cannot confirm an improvement')
                        measured = validate_run(path, ROOT, evaluation)
                        if measured['policyHash'] != digest(directory / 'policy.json'):
                            raise ValueError('Candidate process does not bind its declared policy')
            with tempfile.TemporaryDirectory(prefix='doe-storage-assess-') as scratch:
                summarize(directory, tail, summary_output=Path(scratch))
                if (Path(scratch) / 'acceptance.tsv').read_bytes() != (directory / 'acceptance.tsv').read_bytes():
                    raise ValueError('Raw acceptance differs from physical observations')
        with (directory / 'acceptance.tsv').open(encoding='utf-8') as stream:
            legacy = {r['application']: r for r in csv.DictReader(stream, delimiter='\t')}
        for app in [tail['developmentApplication'], *tail['transferApplications']]:
            group = read_pairs(directory, app, cohort, tail['expandedProcessPairs'])
            pairs.extend(group)
            checks = assess_round({v: [getattr(p, v) for p in group] for v in VARIANTS},
                                  app, startup, tail)
            raw.append({'cohort': cohort, 'application': app,
                        'acceptancePassed': legacy[app]['acceptancePassed'] == 'True'
                        and all(r['regressionPassed'] for r in checks if r['direction'] == 'forward')})
    return assess_uncertainty(pairs, tail, decision), raw


def run_experiment(spec_path: Path, calibration_path: Path, output: Path) -> dict[str, Any]:
    calibration = validate_calibration(calibration_path)
    if calibration['schemaVersion'] != 3:
        raise ValueError('Storage experiment requires the uncertainty calibration procedure')
    spec = validate_candidate(spec_path, calibration)
    policy = load_policy(Path(calibration['policy']['path']), 'compute-program-calibration.schema.json')
    startup = load_policy(ROOT / policy['startupPolicy'], 'compute-program-startup-experiment.schema.json')
    tail = load_policy(ROOT / startup['tailExperimentPolicy'], 'compute-program-tail-experiment.schema.json')
    decision = load_policy(ROOT / policy['decisionPolicy'], 'compute-program-decision.schema.json')
    if any(os.environ.get(key) for key in ('LD_PRELOAD', 'NODE_OPTIONS', 'NODE_PATH')):
        raise ValueError('Ordinary experiment requires no preload or Node injection')
    output.mkdir(parents=True, exist_ok=False)
    frozen = json.loads(Path(calibration['frozenInputs']['path']).read_text(encoding='utf-8'))
    frozen.extend([reference(spec_path), reference(calibration_path)])
    frozen.extend(value for value in spec.values() if isinstance(value, dict))
    for key in ('baselineQualification', 'candidateQualification'):
        qualified = load_qualification(Path(spec[key]['path']), ROOT)
        frozen.extend([*qualified['packages'], *qualified['artifacts']])
    verify_references(frozen)
    write_json(output / 'frozen-inputs.json', frozen)
    retained = output / 'frozen-bytes'
    retained.mkdir()
    for item in frozen:
        destination = retained / item['hash']
        if not destination.exists():
            shutil.copyfile(item['path'], destination)
    report = {'schemaVersion': 1, 'kind': 'command-storage-experiment',
              'claimStatus': 'diagnostic', 'status': 'incomplete', 'error': None,
              'candidate': reference(spec_path), 'calibration': reference(calibration_path),
              'frozenInputs': reference(output / 'frozen-inputs.json'),
              'series': [], 'artifacts': []}
    try:
        for series_name in ('evaluation', 'confirmation'):
            series = output / series_name
            series.mkdir()
            for index in range(decision['cohorts']):
                verify_references(frozen)
                if shutil.disk_usage(output).free < policy['minimumFreeBytes']:
                    raise ValueError('Insufficient free space for the declared experiment cohort')
                cohort = series / f'round-{index:02d}'
                command = [sys.executable, '-m', 'bench.runners.run_compute_program_tail_experiment',
                           '--policy', str(ROOT / startup['tailExperimentPolicy']),
                           '--output', str(cohort), '--sampling', 'expanded', '--applications',
                           tail['developmentApplication'], *tail['transferApplications'],
                           '--baseline-qualification', spec['baselineQualification']['path'],
                           '--candidate-qualification', spec['candidateQualification']['path'],
                           '--first-variant', VARIANTS[index % len(VARIANTS)],
                           '--record-process-identity']
                command.extend(['--output-retention', policy['outputRetention'],
                                '--minimum-free-bytes', str(policy['minimumFreeBytes'])])
                write_json(series / f'round-{index:02d}.command.json', command)
                write_json(series / f'round-{index:02d}.host-before.json', host_observation())
                with (series / f'round-{index:02d}.log').open('w', encoding='utf-8') as stream:
                    result = subprocess.run(command, cwd=ROOT, stdout=stream,
                                            stderr=subprocess.STDOUT, check=False)
                write_json(series / f'round-{index:02d}.host-after.json', host_observation())
                verify_references(frozen)
                if result.returncode:
                    raise ValueError(f'{series_name} cohort {index} failed; see retained log')
                shutil.copyfile(cohort / 'process-output-retention.json',
                                series / f'round-{index:02d}.retention.json')
                print(f'{series_name} cohort {index}: validated', flush=True)
            uncertainty, raw = assess_series(series, startup, tail, decision)
            write_json(series / 'uncertainty.json', uncertainty)
            write_tsv(series / 'raw-acceptance.tsv', raw)
            verdict = candidate_verdict(uncertainty, raw, tail,
                                        calibration_resolved=calibration['promotionResolutionPassed'])
            report['series'].append({'name': series_name,
                                     'uncertainty': reference(series / 'uncertainty.json'),
                                     'rawAcceptance': reference(series / 'raw-acceptance.tsv'),
                                     'decision': verdict})
            write_json(output / 'report.json', report)
            if verdict['verdict'] != 'confirm':
                report['status'] = verdict['verdict']
                break
            if series_name == 'confirmation':
                report['status'] = 'accepted-proposal'
    except (OSError, ValueError, subprocess.SubprocessError, KeyboardInterrupt) as exc:
        report['error'] = str(exc) or type(exc).__name__
    finally:
        report['artifacts'] = [reference(p) for p in sorted(output.rglob('*'))
                               if p.is_file() and p.name != 'report.json'
                               and 'node_modules' not in p.parts]
        write_json(output / 'report.json', report)
        load_policy(output / 'report.json', 'command-storage-experiment.schema.json')
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True, help='Hash-bound bounded candidate')
    parser.add_argument('--calibration-report', type=Path, required=True, help='Fresh A/A decision evidence')
    parser.add_argument('--output', type=Path, required=True, help='New retained experiment directory')
    args = parser.parse_args()
    result = run_experiment(args.candidate.resolve(), args.calibration_report.resolve(), args.output.resolve())
    print(f"experiment: {result['status']}; {args.output / 'report.json'}", flush=True)
    return int(result['status'] == 'incomplete')


if __name__ == '__main__':
    raise SystemExit(main())

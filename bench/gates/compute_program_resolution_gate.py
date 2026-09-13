"""Replay diagnostic warmup treatments without authorizing runtime promotion."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from bench.gates.compute_program_gate import digest, validate_run
from bench.gates.command_storage_review_gate import verify_execution_sequence
from bench.lib.compute_program_resolution import (
    cpu_profile_rows, process_blocks, summarize_blocks,
)
from bench.lib.compute_program_package import load_qualification
from bench.runners.run_compute_program_calibration import load_policy
from bench.runners.run_compute_program_resolution import TREATMENTS, analyze_history
from bench.runners.run_compute_program_tail_experiment import assert_control_identity

ROOT = Path(__file__).resolve().parents[2]


def check_execution_contract(
    data: dict[str, Any], application: str, policy_hash: str,
    qualification_hash: str, library_hash: str,
) -> None:
    """A qualified package must also be the declared accepted package."""
    if (data['provider'] != 'doe-webgpu' or data['application'] != application
            or data['backend'] != 'vulkan' or data['runtime']['name'] != 'node'
            or data['policyHash'] != policy_hash
            or data['packageQualification']['hash'] != qualification_hash
            or data['providerArtifact']['hash'] != library_hash):
        raise ValueError('Execution differs from the accepted package or declared treatment')


def verify_reference(item: dict[str, str]) -> Path:
    path = Path(item['path'])
    if digest(path) != item['hash']:
        raise ValueError(f'Resolution evidence changed: {path}')
    return path


def check_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    expected = [{key: '' if value is None else str(value) for key, value in row.items()}
                for row in rows]
    with path.open(encoding='utf-8', newline='') as stream:
        actual = list(csv.DictReader(stream, delimiter='\t'))
    if actual != expected:
        raise ValueError(f'Resolution projection differs from raw evidence: {path}')


def validate_resolution(path: Path) -> dict[str, Any]:
    """Verify physical work, original outputs, exact inputs, and projections."""
    report = load_policy(path, 'compute-program-resolution-report.schema.json')
    if report['status'] != 'completed' or report['error'] is not None:
        raise ValueError('Resolution diagnosis is incomplete')
    output = path.parent
    references = {item['path']: item['hash'] for item in report['artifacts']}
    if len(references) != len(report['artifacts']):
        raise ValueError('Duplicate resolution artifact references')
    for item in [report['policy'], *report['inputs'], *report['artifacts']]:
        verify_reference(item)
    for item in report['inputs']:
        if digest(output / 'frozen-bytes' / item['hash']) != item['hash']:
            raise ValueError('Missing or changed frozen diagnostic source')
    policy = load_policy(verify_reference(report['policy']), 'compute-program-resolution.schema.json')
    calibration = load_policy(ROOT / policy['calibrationPolicy'], 'compute-program-calibration.schema.json')
    startup = load_policy(ROOT / calibration['startupPolicy'], 'compute-program-startup-experiment.schema.json')
    tail = load_policy(ROOT / startup['tailExperimentPolicy'], 'compute-program-tail-experiment.schema.json')
    original = load_policy(ROOT / tail['evaluationPolicy'], 'compute-program-evaluation.schema.json')
    accepted_path = ROOT / calibration['baselineQualification']
    accepted = load_qualification(accepted_path, ROOT)
    qualification_hash = digest(accepted_path)
    library_hash = accepted['hosts'][0]['libraryHash']
    apps = [tail['developmentApplication'], *tail['transferApplications']]
    expected = {(app, treatment, index) for app in apps for treatment in TREATMENTS
                for index in range(tail['diagnosticProcessRuns'])}
    identities = [(r['application'], r['treatment'], r['process']) for r in report['runs']]
    if len(set(identities)) != len(identities) or set(identities) != expected:
        raise ValueError('Resolution requires every declared application and treatment process')
    expected_order = []
    for family in [('original', 'extended'), ('host', 'v8')]:
        for index in range(tail['diagnosticProcessRuns']):
            order = family if index % 2 == 0 else tuple(reversed(family))
            expected_order.extend((app, treatment, index) for app in apps for treatment in order)
    if identities != expected_order:
        raise ValueError('Resolution processes differ from the declared alternating schedule')
    rows, executions, audits = [], [], {}
    for app in apps:
        selected = load_policy(output / 'original/policy.json', 'compute-program-evaluation.schema.json')
        audits[app] = validate_run(output / 'original' / f'{app}.audit.json', ROOT, selected)
        check_execution_contract(audits[app], app, digest(output / 'original/policy.json'),
                                 qualification_hash, library_hash)
    for run in report['runs']:
        target = verify_reference(run['report'])
        if references.get(str(target)) != run['report']['hash']:
            raise ValueError('Process is absent from retained diagnostic artifacts')
        selected = load_policy(verify_reference(run['policy']), 'compute-program-evaluation.schema.json')
        expected_policy = dict(original, timedRuns=tail['expandedTimedRuns'],
                               processRuns=tail['diagnosticProcessRuns'])
        if run['treatment'] == 'extended':
            expected_policy['warmupRuns'] = policy['extendedWarmupRuns']
        if selected != expected_policy:
            raise ValueError('Warmup treatment changed other evaluation semantics')
        data = validate_run(target, ROOT, selected)
        check_execution_contract(data, run['application'], run['policy']['hash'],
                                 qualification_hash, library_hash)
        assert_control_identity(audits[run['application']], data)
        identity = load_policy(Path(f'{target}.process.json'), 'compute-program-process.schema.json')
        if identity['reportPath'] != str(target) or identity['reportHash'] != digest(target):
            raise ValueError('Physical child does not identify this measured report')
        executions.append(identity)
        events = Path(f'{target}.events.tsv')
        if events.exists() != (run['treatment'] == 'host'):
            raise ValueError('Host diagnostics differ from the declared treatment')
        if events.exists() and 'droppedEvents=0\n' not in Path(f'{target}.limits.txt').read_text(encoding='utf-8'):
            raise ValueError('Host diagnostic records were dropped')
        if run['treatment'] == 'v8':
            profiles = list(target.with_suffix('.profile').glob('*.cpuprofile'))
            if len(profiles) != 1:
                raise ValueError('Expected one retained CPU profile')
            check_tsv(Path(f'{target}.cpu.tsv'), cpu_profile_rows(
                json.loads(profiles[0].read_text(encoding='utf-8'))))
        rows.extend({'application': run['application'], 'treatment': run['treatment'],
                     'process': str(target), **row}
                    for row in process_blocks(data, policy['sampleBlocks']))
    verify_execution_sequence(executions)
    check_tsv(output / 'blocks.tsv', rows)
    check_tsv(output / 'summary.tsv', summarize_blocks(rows))
    history = analyze_history(ROOT / policy['calibrationReport'], policy['sampleBlocks'])
    check_tsv(output / 'historical-blocks.tsv', history)
    check_tsv(output / 'historical-summary.tsv', summarize_blocks(history))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True, help='Completed diagnostic report')
    args = parser.parse_args()
    validate_resolution(args.report.resolve())
    print('Verified warmup and profile diagnosis; no runtime promotion authorized')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

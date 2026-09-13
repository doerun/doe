"""Calibrate frozen application decisions using identical accepted packages."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import jsonschema

from bench.gates.compute_program_gate import digest
from bench.lib.compute_program_package import load_qualification
from bench.lib.compute_program_retention import deduplicate_outputs
from bench.lib.compute_program_host import host_observation
from bench.lib.compute_program_uncertainty import ProcessPair, assess_uncertainty
from bench.runners.assess_compute_program_startup import assess_application
from bench.runners.run_compute_program_tail_experiment import write_tsv

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / 'config/compute-program-calibration.json'
VARIANTS = ('baseline', 'candidate')


def reference(path: Path) -> dict[str, str]:
    """Bind exact retained bytes, including failures, to their source path."""
    return {'path': str(path.resolve()), 'hash': digest(path)}


def assess_round(
    groups: dict[str, list[dict[str, Any]]], application: str,
    startup: dict[str, Any], tail: dict[str, Any],
) -> list[dict[str, Any]]:
    """Apply unchanged regression limits in both A/A label directions."""
    _, forward = assess_application(groups, application, startup, tail)
    swapped = dict(baseline=groups['candidate'], candidate=groups['baseline'])
    _, reverse = assess_application(swapped, application, startup, tail)
    rows = []
    for direction, metrics in [('forward', forward), ('reverse', reverse)]:
        for row in metrics:
            before, after = row['baselineValue'], row['candidateValue']
            rows.append({**row, 'direction': direction,
                         'relativeDifference': after / before - 1
                         if before else None})
    return rows


def thermal_observations() -> list[dict[str, Any]]:
    """Read available hwmon temperatures; missing observations stay unavailable."""
    rows = []
    for path in sorted(Path('/sys/class/hwmon').glob('hwmon*/temp*_input')):
        try:
            value = int(path.read_text(encoding='utf-8'))
            error = None
        except (OSError, ValueError) as exc:
            value, error = None, str(exc)
        rows.append({'path': str(path.resolve()), 'milliCelsius': value,
                     'error': error})
    return rows


def load_policy(path: Path, schema_name: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding='utf-8'))
    schema = json.loads((ROOT / 'config' / schema_name).read_text(encoding='utf-8'))
    jsonschema.Draft202012Validator(schema).validate(value)
    return value


def write_json(path: Path, value: Any) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                         dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def read_pairs(cohort: Path, application: str, index: int, count: int,
               *, require_identity: bool = True) -> list[ProcessPair]:
    """Read complete child-validated pairs in their actual execution order."""
    pairs = []
    for i in range(count):
        first = VARIANTS[(index + i) % len(VARIANTS)]
        paths = [cohort / f'{application}.{v}.process-{i:02d}.json' for v in VARIANTS]
        identities = None
        if require_identity:
            executions = [load_policy(Path(f'{p}.process.json'), 'compute-program-process.schema.json')
                          for p in paths]
            for path, execution in zip(paths, executions, strict=True):
                if (execution['exitCode'] != 0 or execution['reportPath'] != str(path.resolve())
                        or execution['reportHash'] != digest(path)
                        or execution['completedMonotonicNs'] <= execution['startedMonotonicNs']):
                    raise ValueError('Process execution does not identify this completed report')
            before, after = executions if first == 'baseline' else reversed(executions)
            if (before['bootId'] != after['bootId'] or
                    before['completedMonotonicNs'] > after['startedMonotonicNs']):
                raise ValueError('Actual process execution violates the alternating order')
            identities = tuple(f"{e['bootId']}:{e['pid']}:{e['startedMonotonicNs']}" for e in executions)
        pairs.append(ProcessPair(application, index, i, first,
                                 *(json.loads(p.read_text(encoding='utf-8')) for p in paths),
                                 execution_ids=identities))
    return pairs


def run_calibration(policy_path: Path, output: Path) -> dict[str, Any]:
    """Retain alternating cohorts and distinguish variation from a decision."""
    policy = load_policy(policy_path, 'compute-program-calibration.schema.json')
    if policy['schemaVersion'] != 3:
        raise ValueError('Current calibration execution requires uncertainty policy version 3')
    decision_path = ROOT / policy['decisionPolicy']
    decision = load_policy(decision_path, 'compute-program-decision.schema.json')
    if decision['cohorts'] != policy['rounds']:
        raise ValueError('Calibration and decision cohort counts differ')
    startup_path = ROOT / policy['startupPolicy']
    startup = load_policy(startup_path, 'compute-program-startup-experiment.schema.json')
    tail_path = ROOT / startup['tailExperimentPolicy']
    tail = load_policy(tail_path, 'compute-program-tail-experiment.schema.json')
    # The existing executor owns this policy; accepting a different file here
    # would assess one procedure after executing another.
    if tail_path.resolve() != (ROOT / 'config/compute-program-tail-experiment.json').resolve():
        raise ValueError('Calibration requires the canonical tail executor policy')
    qualification = ROOT / policy['baselineQualification']
    accepted = load_qualification(qualification, ROOT)
    if any(os.environ.get(key) for key in ('LD_PRELOAD', 'NODE_OPTIONS', 'NODE_PATH')):
        raise ValueError('Ordinary calibration requires no preload or Node injection')
    output.mkdir(parents=True, exist_ok=False)
    frozen_paths = [policy_path, decision_path, startup_path, tail_path, qualification,
                    ROOT / tail['evaluationPolicy']]
    evaluation = load_policy(ROOT / tail['evaluationPolicy'],
                             'compute-program-evaluation.schema.json')
    frozen_paths.extend((ROOT / 'config').glob('compute-program*.schema.json'))
    frozen_paths.extend((ROOT / 'config').glob('command-storage-*.schema.json'))
    frozen_paths.append(ROOT / 'config/benchmark-methodology-thresholds.json')
    frozen_paths.extend(ROOT / r['path'] for r in evaluation.get('timestampSources', []))
    for item in evaluation.get('fixtures', {}).values():
        fixture = ROOT / item['path']
        frozen_paths.extend(p for p in fixture.parent.rglob('*') if p.is_file())
    for directory, suffixes in [('bench/runners', {'.py', '.mjs'}),
                                ('bench/lib', {'.py'}),
                                ('bench/gates', {'.py'}),
                                ('bench/oracles', {'.mjs'}),
                                ('bench/shared/lib', {'.js'}),
                                ('bench/native_compare_modules', {'.py'})]:
        frozen_paths.extend(p for p in (ROOT / directory).rglob('*')
                            if p.suffix in suffixes)
    frozen = [reference(p) for p in sorted(set(frozen_paths))]
    write_json(output / 'frozen-inputs.json', frozen)
    retained_inputs = output / 'frozen-bytes'
    retained_inputs.mkdir()
    for item in frozen:
        target = retained_inputs / item['hash']
        target.write_bytes(Path(item['path']).read_bytes())
        if digest(target) != item['hash']:
            raise ValueError(f"Calibration input changed during retention: {item['path']}")
    report: dict[str, Any] = {
        'schemaVersion': 3, 'kind': 'compute-program-calibration',
        'claimStatus': 'diagnostic', 'status': 'incomplete',
        'candidateEvaluationAllowed': False,
        'policy': reference(policy_path), 'frozenInputs': reference(output / 'frozen-inputs.json'),
        'packages': accepted['packages'], 'rounds': [], 'artifacts': [],
        'error': None, 'uncertainty': None, 'promotionResolutionPassed': False,
    }
    all_rows = []
    all_pairs = []
    applications = [tail['developmentApplication'], *tail['transferApplications']]

    def verify_frozen() -> None:
        for item in frozen:
            if digest(Path(item['path'])) != item['hash']:
                raise ValueError(f"Calibration input changed: {item['path']}")

    try:
        for index in range(policy['rounds']):
            verify_frozen()
            if shutil.disk_usage(output).free < policy['minimumFreeBytes']:
                raise ValueError('Insufficient free space for the declared calibration cohort')
            cohort = output / f'round-{index:02d}'
            first = VARIANTS[index % len(VARIANTS)]
            command = [sys.executable, '-m',
                       'bench.runners.run_compute_program_tail_experiment',
                       '--output', str(cohort), '--sampling', 'expanded',
                       '--applications', *applications,
                       '--baseline-qualification', str(qualification),
                       '--candidate-qualification', str(qualification),
                       '--first-variant', first, '--record-process-identity']
            command_path = output / f'round-{index:02d}.command.json'
            write_json(command_path, command)
            thermal_before = thermal_observations()
            write_json(output / f'round-{index:02d}.host-before.json', host_observation())
            log_path = output / f'round-{index:02d}.log'
            with log_path.open('w', encoding='utf-8') as log:
                result = subprocess.run(command, cwd=ROOT, stdout=log,
                                        stderr=subprocess.STDOUT, check=False)
            verify_frozen()
            write_json(output / f'round-{index:02d}.host-after.json', host_observation())
            if result.returncode:
                raise ValueError(f'Calibration round {index} failed; see {log_path}')
            identities = [load_qualification(cohort / v / 'package-inputs/summary.json', ROOT)
                          for v in VARIANTS]
            archive_hashes = [sorted(p['hash'] for p in r['packages']) for r in identities]
            if archive_hashes[0] != archive_hashes[1]:
                raise ValueError('A/A requires identical package archives')
            rows = []
            for application in applications:
                pairs = read_pairs(cohort, application, index, tail['expandedProcessPairs'])
                all_pairs.extend(pairs)
                groups = {variant: [getattr(p, variant) for p in pairs] for variant in VARIANTS}
                rows.extend(assess_round(groups, application, startup, tail))
            all_rows.extend({'round': index, 'firstVariant': first, **r} for r in rows)
            report['rounds'].append({
                'index': index, 'firstVariant': first,
                'regressionsPassed': all(r['regressionPassed'] for r in rows),
                'thermalBefore': thermal_before, 'thermalAfter': thermal_observations(),
                'retention': deduplicate_outputs(cohort),
            })
            write_tsv(output / 'metrics.tsv', all_rows)
            print(f'calibration round {index}: '
                  f"regressionsPassed={report['rounds'][-1]['regressionsPassed']}", flush=True)
            write_json(output / 'report.json', report)
        uncertainty = assess_uncertainty(all_pairs, tail, decision)
        write_json(output / 'uncertainty.json', uncertainty)
        report['uncertainty'] = reference(output / 'uncertainty.json')
        report['status'] = 'consistent' if uncertainty['nullConsistent'] else 'inconclusive'
        report['promotionResolutionPassed'] = uncertainty['regressionBandsResolved']
        report['candidateEvaluationAllowed'] = report['status'] == 'consistent'
    except (OSError, ValueError, subprocess.SubprocessError, KeyboardInterrupt) as exc:
        report['error'] = str(exc) or type(exc).__name__
    finally:
        report['artifacts'] = [reference(p) for p in sorted(output.rglob('*'))
                               if p.is_file() and p.name != 'report.json'
                               and 'node_modules' not in p.parts]
        schema = json.loads((ROOT / 'config/compute-program-calibration-report.schema.json')
                            .read_text(encoding='utf-8'))
        jsonschema.Draft202012Validator(schema).validate(report)
        write_json(output / 'report.json', report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New calibration directory')
    parser.add_argument('--policy', type=Path, default=POLICY, help='Versioned calibration policy')
    args = parser.parse_args()
    report = run_calibration(args.policy.resolve(), args.output.resolve())
    print(f"calibration: {report['status']}; {args.output / 'report.json'}", flush=True)
    return 0 if report['status'] == 'consistent' else 1


if __name__ == '__main__':
    raise SystemExit(main())

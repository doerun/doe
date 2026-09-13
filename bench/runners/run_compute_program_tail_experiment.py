"""Repeat exact packages in alternating processes without changing workload semantics."""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import jsonschema

from bench.gates.compute_program_gate import digest, startup_scope
from bench.lib.compute_program_package import (
    install_qualification, load_qualification, validate_package_root,
)
from bench.lib.compute_program_retention import ProcessOutputRetention
from bench.native_compare_modules.reporting import format_stats
from bench.runners.run_compute_program_evidence import run_child, same_adapter

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / 'config/compute-program-tail-experiment.json'
PHASES = ('upload', 'encode', 'submitWait', 'readback', 'total')
COSTS = ('deviceStartupMs', 'preparationMs', 'teardownMs',
         'peakProcessRssBytes', 'allocatedBufferBytes')


def load_experiment_policy(path: Path) -> dict[str, Any]:
    """Validate an explicitly selected policy against the repository schema."""
    policy = json.loads(path.read_text(encoding='utf-8'))
    schema = json.loads(POLICY.with_suffix('.schema.json').read_text(encoding='utf-8'))
    jsonschema.Draft202012Validator(schema).validate(policy)
    return policy


def evaluation_for_sampling(policy: dict[str, Any], sampling: str) -> dict[str, Any]:
    """Derive sample counts while preserving the selected invocation procedure."""
    if sampling not in ('frozen', 'expanded'):
        raise ValueError(f'Unknown experiment sampling: {sampling}')
    evaluation = json.loads((ROOT / policy['evaluationPolicy']).read_text(encoding='utf-8'))
    evaluation['processRuns'] = policy['reproductionProcessPairs']
    if sampling == 'expanded':
        evaluation['timedRuns'] = policy['expandedTimedRuns']
        evaluation['processRuns'] = policy['expandedProcessPairs']
    schema = json.loads((ROOT / 'config/compute-program-evaluation.schema.json').read_text(encoding='utf-8'))
    jsonschema.Draft202012Validator(schema).validate(evaluation)
    return evaluation


def verify_cohort_policy(directory: Path, policy: dict[str, Any]) -> dict[str, Any]:
    """Reject a coherent cohort that executed a different declared procedure."""
    if load_experiment_policy(directory / 'experiment-policy.json') != policy:
        raise ValueError('Cohort experiment policy differs from calibration')
    evaluation = json.loads((directory / 'policy.json').read_text(encoding='utf-8'))
    if evaluation != evaluation_for_sampling(policy, 'expanded'):
        raise ValueError('Cohort invocation policy differs from calibration')
    return evaluation


def require_calibrated_policy(path: Path, calibration: dict[str, Any]) -> None:
    """A candidate cannot select a different procedure after calibration."""
    selected = json.loads(Path(calibration['policy']['path']).read_text(encoding='utf-8'))
    startup = json.loads((ROOT / selected['startupPolicy']).read_text(encoding='utf-8'))
    if digest(path) != digest(ROOT / startup['tailExperimentPolicy']):
        raise ValueError('Candidate experiment policy differs from calibrated procedure')


def assert_control_identity(control: dict[str, Any], report: dict[str, Any]) -> None:
    """Reject changed work, host, or completion scope before interpreting latency."""
    if startup_scope(control) != startup_scope(report):
        raise ValueError('Package controls differ in startup timing scopes')
    if (report['programHash'] != control['programHash']
            or report['runtime'] != control['runtime']
            or report['backend'] != control['backend']
            or not same_adapter(control['adapter'], report['adapter'])):
        raise ValueError('Package controls differ in program, runtime host, or hardware identity')
    for key in ('inputHashes', 'dispatchCount', 'submissionCount', 'clearedBytes',
                'uploadedBytes', 'readbackBytes', 'readbackPath', 'completionMode', 'execution'):
        if report['cold']['receipt'][key] != control['cold']['receipt'][key]:
            raise ValueError(f'Package controls differ in {key}')
    for sample in report['samples']:
        if any(sample['receipt']['timingMs'][phase] <= 0 for phase in PHASES):
            raise ValueError('Missing execution timing phase')


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)


def summarize(
    output: Path, policy: dict[str, Any], *, summary_output: Path | None = None,
) -> None:
    """Keep invocation identity, full timings, and process costs alongside quantiles."""
    destination = output if summary_output is None else summary_output
    invocations, costs, comparisons, decisions = [], [], [], []
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for path in sorted(output.glob('*.process-*.json')):
        if len(path.name.split('.')) != 4:
            continue
        report = json.loads(path.read_text(encoding='utf-8'))
        if Path(f'{path}.events.tsv').exists():
            raise ValueError('Instrumented samples cannot confirm an application benefit')
        application, variant, process_part, _ = path.name.split('.')
        process_index = int(process_part.removeprefix('process-'))
        groups.setdefault((application, variant), []).append(report)
        costs.append({'application': application, 'variant': variant,
                      'process': process_index, **{k: report[k] for k in COSTS},
                      'deviceStartupTimingScope': startup_scope(report),
                      'providerEvidenceMs': report.get('providerEvidenceMs'),
                      'coldWallMs': report['cold']['wallMs']})
        for sample in report['samples']:
            receipt = sample['receipt']
            invocations.append({
                'application': application, 'variant': variant, 'process': process_index,
                'invocationId': f"{receipt['programInstance']}:{receipt['run']}",
                'artifactPath': str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path),
                'wallMs': sample['wallMs'], 'cpuMs': sample['cpuMs'],
                **receipt['timingMs'], 'gpuNs': receipt['gpuTiming']['elapsedNs'],
                'dispatchCount': receipt['dispatchCount'],
                'submissionCount': receipt['submissionCount'],
                'readbackBytes': receipt['readbackBytes'],
                'allocatedBufferBytes': receipt['allocatedBufferBytes'],
            })
    for application in sorted({key[0] for key in groups}):
        if len({startup_scope(report) for (app, _), reports in groups.items()
                if app == application for report in reports}) != 1:
            raise ValueError(f'{application}: mixed startup timing scopes')
        variants = sorted(variant for app, variant in groups if app == application)
        left, right = ('baseline', 'candidate') if 'candidate' in variants else ('previous', 'baseline')
        metrics: dict[str, dict[str, dict[str, float]]] = {}
        for metric in ('wallMs', 'cpuMs', *PHASES):
            metrics[metric] = {}
            for variant in (left, right):
                values = [row[metric] for row in invocations
                          if row['application'] == application and row['variant'] == variant]
                metrics[metric][variant] = format_stats(values, percentile_method='nearest-rank')
            for quantile in ('p50Ms', 'p95Ms', 'p99Ms'):
                before, after = (metrics[metric][v][quantile] for v in (left, right))
                comparisons.append({'application': application, 'metric': metric,
                                    'quantile': quantile, 'control': left, 'treatment': right,
                                    'controlMs': before, 'treatmentMs': after,
                                    'controlOverTreatment': before / after})
        median_reduction = 1 - metrics['wallMs'][right]['p50Ms'] / metrics['wallMs'][left]['p50Ms']
        tails_pass = all(metrics[m][right][q] <= metrics[m][left][q] * (1 + policy['maximumLatencyRegression'])
                         for m in ('wallMs', *PHASES) for q in ('p95Ms', 'p99Ms'))
        paired_improved = sum(
            after['latencyStatsMs']['median'] < before['latencyStatsMs']['median']
            for before, after in zip(groups[(application, left)], groups[(application, right)], strict=True)
        ) / len(groups[(application, left)])
        costs_pass = all(
            metrics['cpuMs'][right][quantile]
            <= metrics['cpuMs'][left][quantile]
            * (1 + policy['maximumCostRegression'])
            for quantile in ('p50Ms', 'p95Ms')
        )
        for metric in (*COSTS, 'coldWallMs'):
            values = {
                variant: format_stats([row[metric] for row in costs
                                       if row['application'] == application and row['variant'] == variant],
                                      percentile_method='nearest-rank')
                for variant in (left, right)
            }
            costs_pass &= values[right]['p50Ms'] <= values[left]['p50Ms'] * (1 + policy['maximumCostRegression'])
            costs_pass &= values[right]['p95Ms'] <= values[left]['p95Ms'] * (1 + policy['maximumCostRegression'])
        threshold = policy['minimumWallMedianReduction'] if application == policy['developmentApplication'] else 0
        decisions.append({'application': application, 'control': left, 'treatment': right,
                          'wallMedianReduction': median_reduction, 'improvedProcessFraction': paired_improved,
                          'tailsPass': tails_pass, 'costsPass': costs_pass,
                          'acceptancePassed': median_reduction > threshold and tails_pass and costs_pass
                          and paired_improved >= policy['minimumImprovedProcessFraction'],
                          'claimStatus': 'diagnostic'})
    write_tsv(destination / 'invocations.tsv', invocations)
    write_tsv(destination / 'process-costs.tsv', costs)
    write_tsv(destination / 'comparison.tsv', comparisons)
    write_tsv(destination / 'acceptance.tsv', decisions)
    slow = sorted(invocations, key=lambda row: row['wallMs'], reverse=True)[:policy['slowInvocationCount']]
    write_tsv(destination / 'slow-invocations.tsv', slow)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', type=Path, default=POLICY,
                        help='Versioned experiment policy; retained with the cohort')
    parser.add_argument('--output', type=Path, required=True, help='New retained experiment directory')
    parser.add_argument('--sampling', choices=['frozen', 'expanded'], required=True, help='Original or expanded sampling')
    parser.add_argument('--applications', nargs='+', required=True, help='Frozen development or transfer applications')
    parser.add_argument('--candidate-qualification', type=Path, help='Compare this qualified correction with baseline')
    parser.add_argument('--baseline-qualification', type=Path,
                        help='Explicit accepted qualification; workload and limits stay frozen')
    parser.add_argument('--first-variant', choices=['baseline', 'candidate'],
                        default='baseline', help='First side of an alternating candidate comparison')
    parser.add_argument('--calibration-report', type=Path,
                        help='Require current A/A admission for a new candidate decision')
    parser.add_argument('--record-process-identity', action='store_true',
                        help='Retain actual child process identity for uncertainty assessment')
    parser.add_argument('--output-retention', choices=['none', 'hardlink-identical-outputs'],
                        default='none', help='Share exact outputs after each child process')
    parser.add_argument('--minimum-free-bytes', type=int,
                        help='Configured free-space admission before each retained child')
    args = parser.parse_args()
    args.policy = args.policy.resolve()
    policy = load_experiment_policy(args.policy)
    if args.calibration_report:
        from bench.gates.compute_program_calibration_gate import validate_calibration
        calibration = validate_calibration(args.calibration_report.resolve())
        require_calibrated_policy(args.policy, calibration)
        if args.candidate_qualification is None:
            raise ValueError('Calibrated candidate comparison requires a qualified candidate')
        baseline = args.baseline_qualification or ROOT / policy['baselineQualification']
        qualification = load_qualification(baseline, ROOT)
        if (sorted(p['hash'] for p in qualification['packages'])
                != sorted(p['hash'] for p in calibration['packages'])):
            raise ValueError('Candidate baseline differs from calibrated accepted archives')
    if set(args.applications) - {policy['developmentApplication'], *policy['transferApplications']}:
        raise ValueError('Unknown application; use the frozen development and transfer set')
    if len(args.applications) != len(set(args.applications)):
        raise ValueError('Applications must be unique')
    output = args.output.resolve()
    retention = ProcessOutputRetention(output, args.output_retention, args.minimum_free_bytes)
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(args.policy, output / 'experiment-policy.json')
    shutil.copyfile(__file__, output / Path(__file__).name)
    shutil.copyfile(ROOT / policy['originalComparison'], output / 'original-comparison.tsv')
    evaluation = evaluation_for_sampling(policy, args.sampling)
    processes = evaluation['processRuns']
    for reference in evaluation.get('timestampSources', []):
        if digest(ROOT / reference['path']) != reference['hash']:
            raise ValueError(f'Timestamp source changed: {reference["path"]}')
    evaluation_path = output / 'policy.json'
    evaluation_path.write_text(json.dumps(evaluation, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    subprocess.run(['vulkaninfo', f"--json={evaluation['vulkanDeviceIndex']}", '-o', str(output / 'hardware-profile.json')],
                   capture_output=True, check=True, timeout=evaluation['processTimeoutMs'] / 1000)
    qualifications = {'previous': ROOT / policy['previousQualification'], 'baseline': ROOT / policy['baselineQualification']}
    if args.baseline_qualification:
        if args.candidate_qualification is None:
            raise ValueError('Explicit baseline requires a candidate comparison')
        qualifications['baseline'] = args.baseline_qualification.resolve()
    if args.candidate_qualification:
        qualifications = {'baseline': qualifications['baseline'], 'candidate': args.candidate_qualification.resolve()}
    packages = {}
    for variant, qualification in qualifications.items():
        destination = output / variant
        destination.mkdir()
        packages[variant] = install_qualification(qualification, destination, ROOT, evaluation['processTimeoutMs'])
    variants = list(packages)
    if args.first_variant == 'candidate':
        if 'candidate' not in variants:
            raise ValueError('Candidate-first order requires a candidate comparison')
        variants.reverse()
    identities = {}
    for application in args.applications:
        for variant in variants:
            path = output / f'{application}.{variant}.audit.json'
            with retention.process(path):
                report = run_child('doe-webgpu', application, 'audit', path, evaluation_path, evaluation,
                                   'vulkan', 'node', '', None, packages[variant], output / variant / 'package-inputs/summary.json')
            identities[(application, variant)] = report
            print(f'audit passed: {application}/{variant}', flush=True)
        before, after = (identities[(application, variant)] for variant in variants)
        assert_control_identity(before, after)
    for index in range(processes):
        order = variants if index % 2 == 0 else list(reversed(variants))
        for application in args.applications:
            for variant in order:
                path = output / f'{application}.{variant}.process-{index:02d}.json'
                with retention.process(path):
                    report = run_child('doe-webgpu', application, 'measure', path, evaluation_path, evaluation,
                                       'vulkan', 'node', '', None, packages[variant], output / variant / 'package-inputs/summary.json',
                                       process_identity=Path(f'{path}.process.json') if args.record_process_identity else None)
                assert_control_identity(identities[(application, variant)], report)
                print(f'measured: {application}/{variant}/{index}', flush=True)
    for variant, package in packages.items():
        validate_package_root(package, load_qualification(output / variant / 'package-inputs/summary.json', ROOT))
    summarize(output, policy)
    print((output / 'acceptance.tsv').read_text(encoding='utf-8'), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

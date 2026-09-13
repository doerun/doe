"""Diagnose ordinary application warmup and costs with the accepted package."""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

from bench.gates.compute_program_gate import digest
from bench.lib.compute_program_host import host_observation
from bench.lib.compute_program_package import install_qualification
from bench.lib.compute_program_resolution import (
    cpu_profile_rows, process_blocks, summarize_blocks,
)
from bench.lib.compute_program_retention import deduplicate_outputs
from bench.runners.run_compute_program_calibration import (
    load_policy, reference, write_json,
)
from bench.runners.run_compute_program_evidence import run_child
from bench.runners.run_compute_program_tail_experiment import (
    assert_control_identity, write_tsv,
)

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / 'config/compute-program-resolution.json'
TREATMENTS = ('original', 'extended', 'host', 'v8')


def analyze_history(calibration: Path, blocks: int) -> list[dict[str, Any]]:
    """Read exact historical reports; this analysis does not replace replay."""
    report = load_policy(calibration, 'compute-program-calibration-report.schema.json')
    rows = []
    for item in report['artifacts']:
        path = Path(item['path'])
        if '.process-' not in path.name or len(path.name.split('.')) != 4:
            continue
        if digest(path) != item['hash']:
            raise ValueError(f'Historical process bytes changed: {path}')
        data = json.loads(path.read_text(encoding='utf-8'))
        rows.extend({'application': data['application'], 'treatment': 'historical',
                     'process': str(path), **row} for row in process_blocks(data, blocks))
    if not rows:
        raise ValueError('Calibration contains no bound measured process reports')
    return rows


def run_resolution(policy_path: Path, output: Path, node: Path) -> dict[str, Any]:
    """Keep all treatments diagnostic and validate every numerical output."""
    policy = load_policy(policy_path, 'compute-program-resolution.schema.json')
    calibration_path = ROOT / policy['calibrationPolicy']
    calibration = load_policy(calibration_path, 'compute-program-calibration.schema.json')
    startup_path = ROOT / calibration['startupPolicy']
    startup = load_policy(startup_path, 'compute-program-startup-experiment.schema.json')
    tail_path = ROOT / startup['tailExperimentPolicy']
    tail = load_policy(tail_path, 'compute-program-tail-experiment.schema.json')
    evaluation_path = ROOT / tail['evaluationPolicy']
    evaluation = load_policy(evaluation_path, 'compute-program-evaluation.schema.json')
    if any(os.environ.get(key) for key in ('LD_PRELOAD', 'NODE_OPTIONS', 'NODE_PATH')):
        raise ValueError('Resolution diagnosis requires no preload or Node injection')
    if policy['extendedWarmupRuns'] <= evaluation['warmupRuns']:
        raise ValueError('Extended warmup must exceed the original warmup')
    if tail['expandedTimedRuns'] % policy['sampleBlocks']:
        raise ValueError('Diagnostic sample blocks must divide the declared timed runs')
    output.mkdir(parents=True, exist_ok=False)
    report: dict[str, Any] = {
        'schemaVersion': 1, 'kind': 'compute-program-resolution',
        'claimStatus': 'diagnostic', 'status': 'incomplete', 'error': None,
        'policy': reference(policy_path), 'inputs': [], 'runs': [], 'artifacts': [],
    }
    applications = [tail['developmentApplication'], *tail['transferApplications']]
    sources = {policy_path, calibration_path, startup_path, tail_path, evaluation_path,
               ROOT / calibration['baselineQualification'], ROOT / policy['calibrationReport'], node}
    for directory, suffix in [('bench/runners', '.py'), ('bench/runners', '.mjs'),
                              ('bench/lib', '.py'), ('bench/gates', '.py'),
                              ('bench/oracles', '.mjs'), ('bench/shared/lib', '.js'),
                              ('bench/native_compare_modules', '.py')]:
        sources.update((ROOT / directory).rglob(f'*{suffix}'))
    sources.update((ROOT / 'config').glob('compute-program*.schema.json'))
    sources.update(ROOT / item['path'] for item in evaluation.get('timestampSources', []))
    sources.add(ROOT / 'config/benchmark-methodology-thresholds.json')
    for item in evaluation.get('fixtures', {}).values():
        sources.update(path for path in (ROOT / item['path']).parent.rglob('*') if path.is_file())
    report['inputs'] = [reference(path) for path in sorted(sources)]
    frozen = output / 'frozen-bytes'
    frozen.mkdir()
    for item in report['inputs']:
        shutil.copyfile(item['path'], frozen / item['hash'])

    def verify_inputs() -> None:
        for item in report['inputs']:
            if (digest(Path(item['path'])) != item['hash']
                    or digest(frozen / item['hash']) != item['hash']):
                raise ValueError(f"Diagnostic input changed: {item['path']}")

    rows = []
    try:
        historical = analyze_history(ROOT / policy['calibrationReport'], policy['sampleBlocks'])
        write_tsv(output / 'historical-blocks.tsv', historical)
        write_tsv(output / 'historical-summary.tsv', summarize_blocks(historical))
        package = install_qualification(ROOT / calibration['baselineQualification'],
                                        output, ROOT, evaluation['processTimeoutMs'])
        qualification = output / 'package-inputs/summary.json'
        write_json(output / 'host-before.json', host_observation())
        audits = {}
        policies = {}
        for treatment in TREATMENTS:
            directory = output / treatment
            directory.mkdir()
            selected = dict(evaluation, timedRuns=tail['expandedTimedRuns'],
                            processRuns=tail['diagnosticProcessRuns'])
            if treatment == 'extended':
                selected['warmupRuns'] = policy['extendedWarmupRuns']
            path = directory / 'policy.json'
            write_json(path, selected)
            load_policy(path, 'compute-program-evaluation.schema.json')
            policies[treatment] = (path, selected)
            subprocess.run(['vulkaninfo', f"--json={selected['vulkanDeviceIndex']}",
                            '-o', str(directory / 'hardware-profile.json')],
                           capture_output=True, check=True,
                           timeout=selected['processTimeoutMs'] / 1000)
        for app in applications:
            path, selected = policies['original']
            audits[app] = run_child('doe-webgpu', app, 'audit',
                                    output / 'original' / f'{app}.audit.json',
                                    path, selected, 'vulkan', str(node), '', None,
                                    package, qualification)
            print(f'audit passed: {app}', flush=True)
        # Profiled processes run after the ordinary warmup treatment cohort.
        for family in [('original', 'extended'), ('host', 'v8')]:
            for index in range(tail['diagnosticProcessRuns']):
                order = family if index % 2 == 0 else tuple(reversed(family))
                for app in applications:
                    for treatment in order:
                        verify_inputs()
                        if shutil.disk_usage(output).free < calibration['minimumFreeBytes']:
                            raise ValueError('Insufficient space for a diagnostic process')
                        directory = output / treatment
                        path, selected = policies[treatment]
                        target = directory / f'{app}.process-{index:02d}.json'
                        executable, diagnostic = str(node), None
                        if treatment == 'host':
                            diagnostic = tail_path
                        if treatment == 'v8':
                            profile_dir = directory / f'{app}.process-{index:02d}.profile'
                            profile_dir.mkdir()
                            flags = [str(node), '--cpu-prof',
                                     f'--cpu-prof-dir={profile_dir}',
                                     f"--cpu-prof-interval={policy['cpuProfileIntervalUs']}",
                                     '--trace-opt', '--trace-deopt']
                            launcher = profile_dir / 'node-profile.sh'
                            launcher.write_text('#!/bin/sh\nexec ' + shlex.join(flags)
                                                + ' "$@"\n', encoding='utf-8')
                            launcher.chmod(0o700)
                            executable = str(launcher)
                        data = run_child('doe-webgpu', app, 'measure', target,
                                         path, selected, 'vulkan', executable, '', None,
                                         package, qualification, diagnostic,
                                         Path(f'{target}.process.json'))
                        assert_control_identity(audits[app], data)
                        rows.extend({'application': app, 'treatment': treatment,
                                     'process': str(target), **row}
                                    for row in process_blocks(data, policy['sampleBlocks']))
                        if treatment == 'v8':
                            profiles = list(profile_dir.glob('*.cpuprofile'))
                            if len(profiles) != 1:
                                raise ValueError('Expected one retained V8 CPU profile')
                            profile = json.loads(profiles[0].read_text(encoding='utf-8'))
                            write_tsv(Path(f'{target}.cpu.tsv'), cpu_profile_rows(profile))
                        report['runs'].append({'application': app, 'treatment': treatment,
                                               'process': index, 'report': reference(target),
                                               'policy': reference(path)})
                        write_json(directory / 'retention.json', deduplicate_outputs(directory))
                        write_json(output / 'report.json', report)
                        print(f'validated: {app}/{treatment}/{index}', flush=True)
        verify_inputs()
        write_tsv(output / 'blocks.tsv', rows)
        write_tsv(output / 'summary.tsv', summarize_blocks(rows))
        write_json(output / 'host-after.json', host_observation())
        report['status'] = 'completed'
    except (OSError, ValueError, subprocess.SubprocessError, KeyboardInterrupt) as exc:
        report['error'] = str(exc) or type(exc).__name__
    finally:
        report['artifacts'] = [reference(path) for path in sorted(output.rglob('*'))
                               if path.is_file() and path != output / 'report.json'
                               and 'node_modules' not in path.parts]
        write_json(output / 'report.json', report)
        load_policy(output / 'report.json', 'compute-program-resolution-report.schema.json')
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='New evidence directory')
    parser.add_argument('--policy', type=Path, default=POLICY, help='Diagnostic policy')
    parser.add_argument('--node', type=Path, default=Path(shutil.which('node') or '/usr/bin/node'),
                        help='Installed Node executable')
    args = parser.parse_args()
    report = run_resolution(args.policy.resolve(), args.output.resolve(), args.node.resolve())
    print(f"resolution diagnosis: {report['status']}; {report['error']}", flush=True)
    return 0 if report['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())

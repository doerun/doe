"""Validate retained ONNX execution, interception, and artifact identities."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=Path(
        'reports/benchmarks/amd-vulkan/20261005-onnx-webgpu-substitution'))
    parser.add_argument('--with-custody', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    report = args.report.resolve()
    manifest = json.loads((report / 'manifest.json').read_text())
    for item in manifest['files']:
        path = report / item['path']
        require(path.resolve().is_relative_to(report), 'Artifact escapes report')
        require(digest(path) == item['sha256'], f'Changed artifact: {path}')
    for item in manifest['sources']:
        path = root / item['path']
        require(digest(path) == item['sha256'], f'Changed source: {path}')
    if args.with_custody:
        bundle = root / manifest['custody']['path']
        require(digest(bundle) == manifest['custody']['sha256'], 'Changed custody archive')
        require(bundle.stat().st_size == manifest['custody']['bytes'], 'Changed custody size')
    baseline, preload, control = [json.loads((report / name).read_text()) for name in
                                 ['dawn-control.json', 'doe-preload.json', 'probe-control.json']]
    require(digest(Path(__file__).with_name('run.py')) == baseline['runner']['sha256'],
            'Retained results do not match the current runner')
    for result in [baseline, preload, control]:
        require(result['passed'] and not result['doeExecutionEstablished'],
                'Diagnostic passed state or execution attribution changed')
        require(result['runner']['sha256'] == baseline['runner']['sha256'], 'Runner mismatch')
    require(baseline['model']['sha256'] == preload['model']['sha256'], 'Model mismatch')
    require(baseline['executionOptions'] == preload['executionOptions'] == {
        'graphOptimization': 'disabled', 'cpuFallback': 'disabled',
        'backend': 'Vulkan', 'validation': 'full'}, 'Execution options mismatch')
    require(baseline['providerLibrary']['sha256'] == preload['providerLibrary']['sha256'],
            'Provider library mismatch')
    for result in [baseline, preload]:
        require(result['observed'] == result['expected'] == baseline['expected'],
                'Independent output oracle failed')
        require(result['operatorNames'] == ['MatMul', 'Add'], 'Original operators changed')
        require(result['operatorProviders'] == ['WebGpuExecutionProvider'] * 2,
                'CPU fallback or missing operator')
        profile_path = report / Path(result['profile']['path']).name
        require(digest(profile_path) == result['profile']['sha256'], 'Profile mismatch')
        nodes = [event['args'] for event in json.loads(profile_path.read_text())
                 if event.get('cat') == 'Node' and 'provider' in event.get('args', {})]
        require([node['op_name'] for node in nodes] == result['operatorNames'],
                'Profile does not establish original operators')
        require([node['provider'] for node in nodes] == result['operatorProviders'],
                'Profile does not establish provider placement')
    for result in [preload, control]:
        probe = result['preloadProbe']
        require(probe['doeLibraryLoaded'] and probe['probeLibraryLoaded'],
                'Preloaded library not observed')
        require(probe['library']['sha256'] == preload['preloadProbe']['library']['sha256'],
                'Probe binary mismatch')
        require(probe['doeLibrary']['sha256'] == preload['preloadProbe']['doeLibrary']['sha256'],
                'Doe binary mismatch')
    require(preload['preloadProbe']['counters'] == {
        'instances': 0, 'shaders': 0, 'submissions': 0}, 'Unexpected intercepted ONNX work')
    require(control['preloadProbe']['counters'] == {
        'instances': 1, 'shaders': 0, 'submissions': 0}, 'Positive control failed')
    generation = json.loads((root / 'reports/benchmarks/amd-vulkan/'
                             '20261005-installed-generation/providers.json').read_text())
    accepted = next(item['sha256'] for item in generation['files']
                    if item['path'] == generation['doeLibrary'])
    require(preload['preloadProbe']['doeLibrary']['sha256'] == accepted,
            'Preloaded Doe differs from the accepted generation library')
    for name in ['elf-defined.txt', 'elf-undefined.txt']:
        text = (report / name).read_text()
        require('wgpu' not in text and 'dawnProc' not in text, 'External WebGPU seam changed')
    dynamic = (report / 'elf-dynamic.txt').read_text().lower()
    require('webgpu_dawn' not in dynamic, 'External Dawn dependency changed')
    disposition = json.loads((report / 'disposition.json').read_text())
    require(all(disposition['checks'].values()), 'Disposition check failed')
    require(not disposition['doeExecutionEstablished'] and not disposition['performanceClaim'],
            'Diagnostic was promoted to execution/performance evidence')
    option = json.loads((report / 'option-control.json').read_text())
    rejection = option['expectedConfigurationRejection']
    require(option['passed'] and not option['doeExecutionEstablished']
            and option['failure'] is None and rejection is not None,
            'Expected proc-table configuration rejection missing')
    require('dawn_proc_table_str' in rejection['message']
            and 'from_chars' in rejection['message'], 'Different configuration failure')
    require(option['providerLibrary']['sha256'] == baseline['providerLibrary']['sha256']
            and option['runner']['sha256'] == baseline['runner']['sha256'],
            'Option control package/runner mismatch')
    print('PASS: native ONNX control, preload boundary, and retained identities')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Validate the bounded ONNX proc-table integration and its retained identities."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tarfile


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=Path(
        'reports/benchmarks/amd-vulkan/20261005-onnx-proc-adapter'))
    parser.add_argument('--with-custody', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    report = args.report.resolve()
    read = lambda name: json.loads((report / name).read_text(encoding='utf-8'))
    manifest = read('manifest.json')
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
        with tarfile.open(bundle) as archive:
            inventory = json.load(archive.extractfile('onnx-proc-adapter/inventory.json'))
            for item in inventory:
                member = archive.extractfile('onnx-proc-adapter/' + item['path'])
                require(member is not None and hashlib.file_digest(member, 'sha256').hexdigest()
                        == item['sha256'], f'Changed custody member: {item["path"]}')
    build = read('bridge-build.json')
    source = read('source-build.json')
    require(build['dawnCommit'] == source['dawnCommit'], 'Consumer/adapter Dawn ABI mismatch')
    require(build['doeHeader']['sha256'] == source['doeHeader']['sha256'], 'Doe ABI mismatch')
    require(len(build['procNames']) == len(set(build['procNames'])), 'Duplicate proc identity')
    doe, dawn, original, corrected = [read(name) for name in (
        'doe.json', 'dawn-control.json', 'future-original.json', 'future-corrected.json')]
    offline = [read('offline-first.json'), read('offline-reopen.json'), read('archive-execution.json')]
    for result in (doe, dawn, original, corrected, *offline):
        require(result['runner']['sha256'] == digest(Path(__file__).with_name('run_adapter.py')),
                'Retained result uses different runner bytes')
        require(result['bridgeBuild']['sha256'] == digest(report / 'bridge-build.json'),
                'Different qualified adapter')
        require(result['initialDrmClients'] == result['finalDrmClients'],
                'Native DRM clients survived context cleanup')
    require(doe['passed'] and doe['doeExecutionEstablished'], 'Doe inference did not pass')
    require(dawn['passed'] and not dawn['doeExecutionEstablished']
            and not any(dawn['callCounts'].values()), 'Published incumbent control failed')
    require(doe['model']['sha256'] == dawn['model']['sha256'], 'Changed model')
    for result in (doe, dawn, *offline):
        require(result['executionOptions'] == {
            'graphOptimization': 'disabled', 'cpuFallback': 'disabled',
            'backend': 'Vulkan', 'validation': 'full'}, 'Changed execution options')
        require(result['cancellation']['phase'] == 'before-execution'
                and result['cancellation']['reused'], 'Cancellation/reuse missing')
        require(result['operatorNames'] == ['MatMul', 'Add'] * 3
                and result['operatorProviders'] == ['WebGpuExecutionProvider'] * 6,
                'Original operator placement changed')
        require(len(result['runs']) == 3, 'Missing repeated inputs')
        for index, run in enumerate(result['runs']):
            expected = [[sum((row * 4 + k + index) * (col * 4 + k - index)
                             for k in range(4)) + index + 1
                         for col in range(4)] for row in range(4)]
            require(run['expected'] == run['observed'] == expected, 'Independent oracle failed')
        profile = report / Path(result['profile']['path']).name
        require(digest(profile) == result['profile']['sha256'], 'Changed operator profile')
        nodes = [event['args'] for event in json.loads(profile.read_text(encoding='utf-8'))
                 if event.get('cat') == 'Node' and 'provider' in event.get('args', {})]
        require([node['op_name'] for node in nodes] == result['operatorNames']
                and [node['provider'] for node in nodes] == result['operatorProviders'],
                'Profile contradicts operator placement')
    require(doe['contextIdentity']['backend'] == 6
            and doe['contextIdentity']['vendor'] == 0x1002, 'Different physical execution context')
    for name in ('deviceCreateShaderModule', 'computePassEncoderDispatchWorkgroups',
                 'queueSubmit', 'bufferMapAsync'):
        require(doe['callCounts'][name] > 0, f'Missing observed Doe call: {name}')
    require(not original['passed'] and not original['futureControl']['passed'],
            'Original premature-completion control was discarded')
    require(corrected['passed'] and corrected['futureControl']['passed'],
            'Corrected asynchronous completion failed')
    require(corrected['doeLibrary']['sha256'] == doe['doeLibrary']['sha256'],
            'Completion and inference used different native libraries')
    for result in offline:
        require(result['passed'] and result['doeExecutionEstablished']
                and result['doeLibrary']['sha256'] == doe['doeLibrary']['sha256']
                and result['provider']['sha256'] == doe['provider']['sha256'],
                'Offline installed consumer used different libraries')
    generation = read('doppler-final-transfer-audit.json')
    require(generation['passed'] and generation['nativeSha256'] == doe['doeLibrary']['sha256'],
            'Generation transfer did not use final native bytes')
    require(build['builder']['sha256'] == digest(Path(__file__).with_name('build_adapter.py')),
            'ABI builder source changed')
    require(doe['doeLibrary']['sha256'] == source['qualifiedNative']['sha256'],
            'Source build binds different native bytes')
    require(doe['provider']['sha256'] == source['patchedProvider']['sha256'],
            'Different consumer integration library')
    disposition = read('disposition.json')
    require(all(disposition['checks'].values()) and not disposition['performanceClaim']
            and not disposition['browserSwitchEstablished'], 'Disposition changed')
    print('PASS: bounded native ONNX integration, oracle, completion, and identities')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

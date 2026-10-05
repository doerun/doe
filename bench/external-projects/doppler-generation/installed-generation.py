"""Prepare and execute the retained generation workload outside its checkouts."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
from pathlib import Path
from typing import Any

APPLICATION = Path('/application')
LANES = ('doe', 'dawn')


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n',
                    encoding='utf-8')


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_file(path: Path, expected: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f'Required artifact is missing: {path}')
    if digest(path) != expected:
        raise ValueError(f'Artifact SHA-256 mismatch: {path}')


def run_logged(command: list[str], cwd: Path, log: Path) -> int:
    with log.open('w', encoding='utf-8') as stream:
        process = subprocess.run(command, cwd=cwd, stdout=stream,
                                 stderr=subprocess.STDOUT, check=False)
    return process.returncode


def inventory(root: Path) -> list[dict[str, Any]]:
    """Reject every installed symlink that escapes the consumer directory."""
    entries = []
    for path in sorted((root / 'node_modules').rglob('*')):
        if path.is_symlink() and not path.resolve().is_relative_to(root):
            raise ValueError(f'Installed dependency escapes consumer: {path}')
        if path.is_file():
            entries.append({'path': str(path.relative_to(root)),
                            'sha256': digest(path),
                            'bytes': path.stat().st_size})
    return entries


def verify_archive_install(archive: Path, package: Path) -> None:
    """Authenticate shipped files after npm has normalized the archive root."""
    with tarfile.open(archive) as stream:
        for member in stream.getmembers():
            if not member.isfile():
                continue
            relative = Path(*Path(member.name).parts[1:])
            target = package / relative
            if not target.resolve().is_relative_to(package.resolve()):
                raise ValueError(f'Archive member escapes package: {member.name}')
            content = stream.extractfile(member)
            assert content is not None
            verify_file(target, hashlib.file_digest(content, 'sha256').hexdigest())


def prepare(args: argparse.Namespace) -> None:
    root = args.destination.resolve()
    root.mkdir(parents=True, exist_ok=False)
    for name in ('archives', 'inputs', 'harness', 'model', 'results', 'npm-cache'):
        (root / name).mkdir()
    sources = {}
    for label in ('contract', 'providers', 'reference'):
        source = getattr(args, label).resolve()
        shutil.copy2(source, root / 'inputs' / f'{label}.json')
        sources[label] = {'path': str(source), 'sha256': digest(source)}
    contract = read_json(args.contract)
    providers = read_json(args.providers)
    reference = read_json(args.reference)
    if reference['contractSha256'] != sources['contract']['sha256']:
        raise ValueError('CPU reference does not bind the supplied contract')
    for item in providers['files']:
        verify_file(Path(item['path']), item['sha256'])
    dependencies = {}
    packages = []
    for item in providers['archives']:
        source = Path(item['path'])
        verify_file(source, item['sha256'])
        target = root / 'archives' / source.name
        shutil.copy2(source, target)
        with tarfile.open(target) as stream:
            member = next(item for item in stream.getmembers()
                          if item.name.endswith('/package.json')
                          and len(Path(item.name).parts) == 2)
            package = json.load(stream.extractfile(member))
        dependencies[package['name']] = f'file:archives/{source.name}'
        packages.append({'name': package['name'], 'version': package['version'],
                         'archive': f'archives/{source.name}',
                         'sha256': item['sha256']})
    if set(dependencies) != {'doe-gpu', 'doppler-gpu', 'webgpu'}:
        raise ValueError('Expected exact Doe, Doppler and Dawn provider archives')
    write_json(root / 'package.json', {
        'name': 'doe-installed-generation', 'version': '1.0.0',
        'private': True, 'type': 'module', 'dependencies': dependencies,
    })
    command = ['npm', 'install', '--ignore-scripts', '--omit=optional',
               '--no-audit', '--no-fund', '--cache', str(root / 'npm-cache')]
    if run_logged(command, root, root / 'results/install.log'):
        raise RuntimeError(f'npm installation failed: {root}/results/install.log')
    for package in packages:
        verify_archive_install(root / package['archive'],
                               root / 'node_modules' / package['name'])
    for item in contract['model']['files']:
        source = Path(contract['model']['path']) / item['path']
        verify_file(source, item['sha256'])
        target = root / 'model' / item['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['cp', '--reflink=auto', str(source), str(target)],
                       check=True)
    contract['model']['path'] = str(APPLICATION / 'model')
    contract['workloadId'] = 'doppler_installed_generation_native_vulkan_v1'
    contract['classification'] = 'standalone-installation-qualification'
    write_json(root / 'contract.json', contract)
    reference['contractSha256'] = digest(root / 'contract.json')
    write_json(root / 'reference.json', reference)
    locations = {'doppler': 'doppler-gpu', 'doe': 'doe-gpu', 'dawn': 'webgpu'}
    for key in ('dopplerModule', 'doeModule', 'doeLibrary', 'dawnModule'):
        relative = Path(providers[key].split('/installed/', 1)[1])
        providers[key] = str(APPLICATION / 'node_modules'
                             / locations[relative.parts[0]]
                             / Path(*relative.parts[1:]))
    for item in providers['files']:
        relative = Path(item['path'].split('/installed/', 1)[1])
        item['path'] = str(APPLICATION / 'node_modules'
                           / locations[relative.parts[0]]
                           / Path(*relative.parts[1:]))
    for item in providers['archives']:
        item['path'] = str(APPLICATION / 'archives' / Path(item['path']).name)
    providers['dopplerArchive'] = next(item['path']
                                     for item in providers['archives']
                                     if 'doppler-gpu-' in item['path'])
    providers['dopplerDependencyClosure'] = (
        'Independent npm install; required dependencies retained in npm cache; '
        'optional auto-provider packages omitted; explicit archived natives used.')
    providers['dopplerDependencyLockSha256'] = digest(root / 'package-lock.json')
    write_json(root / 'providers.json', providers)
    harness = Path(__file__).parent
    for name in ('run-generation.mjs', 'observe-phases.mjs',
                 'installed-audit.mjs', 'installed-generation.py'):
        shutil.copy2(harness / name, root / 'harness' / name)
    write_json(root / 'inventory.json', inventory(root))
    write_json(root / 'installation.json', {
        'schemaVersion': 1, 'classification': 'standalone-installation',
        'sources': sources, 'packages': packages,
        'workspaceRoots': [str(Path(__file__).resolve().parents[4])],
        'files': [{'path': str(path.relative_to(root)), 'sha256': digest(path)}
                  for path in sorted(root.rglob('*'))
                  if path.is_file() and not path.is_relative_to(root / 'results')
                  and not path.is_relative_to(root / 'node_modules')
                  and not path.is_relative_to(root / 'npm-cache')],
        'scope': 'Retained Linux x64 provider snapshots, not an npm release; '
                 'system drivers, /sys and /dev remain host dependencies.',
    })
    print(json.dumps({'prepared': str(root), 'packages': packages}))


def sandbox(root: Path) -> list[str]:
    command = ['bwrap', '--die-with-parent', '--unshare-net', '--clearenv']
    for path in ('/usr', '/lib', '/lib64', '/etc', '/sys'):
        if Path(path).exists():
            command += ['--ro-bind', path, path]
    command += ['--proc', '/proc', '--dev-bind', '/dev', '/dev',
                '--tmpfs', '/tmp', '--dir', '/home',
                '--bind', str(root), str(APPLICATION),
                '--setenv', 'PATH', '/usr/bin:/bin',
                '--setenv', 'HOME', '/tmp',
                '--setenv', 'XDG_CACHE_HOME', '/tmp/cache',
                '--chdir', str(APPLICATION)]
    return command


def execute(args: argparse.Namespace) -> None:
    root = args.destination.resolve()
    installation = read_json(root / 'installation.json')
    for item in installation['files']:
        verify_file(root / item['path'], item['sha256'])
    if inventory(root) != read_json(root / 'inventory.json'):
        raise ValueError('Installed dependency inventory changed')
    results = root / 'results'
    command = sandbox(root) + [
        '/usr/bin/npm', 'ci', '--offline', '--ignore-scripts', '--omit=optional',
        '--no-audit', '--no-fund', '--cache', '/application/npm-cache',
    ]
    if run_logged(command, root, results / 'offline-install.log'):
        raise RuntimeError('Offline npm ci failed; inspect results/offline-install.log')
    if inventory(root) != read_json(root / 'inventory.json'):
        raise ValueError('Offline npm ci changed installed dependency bytes')
    checks = []
    for label, lane, fault in (
        ('doe-first', 'doe', None), ('doe-reopen', 'doe', None),
        ('dawn-control', 'dawn', None),
        ('missing-library', 'doe', 'library'),
        ('incompatible-package', 'doe', 'package'),
        ('missing-model', 'doe', 'model'),
    ):
        command = sandbox(root)
        if fault == 'library':
            command += ['--tmpfs', '/application/node_modules/doe-gpu/native']
        if fault == 'model':
            command += ['--tmpfs', '/application/model']
        if fault == 'package':
            package = read_json(root / 'node_modules/doppler-gpu/package.json')
            package['version'] = '0.0.0-incompatible'
            write_json(results / 'incompatible-package.json', package)
            command += ['--ro-bind', str(results / 'incompatible-package.json'),
                        '/application/node_modules/doppler-gpu/package.json']
        command += ['/usr/bin/node', 'harness/installed-audit.mjs', lane, label]
        code = run_logged(command, root, results / f'{label}.log')
        audit = read_json(results / f'{label}-audit.json')
        expected_code = {
            'library': 'MISSING_LIBRARY', 'model': 'MISSING_MODEL',
            'package': 'INCOMPATIBLE_PACKAGE',
        }.get(fault)
        passed = (code == 0 and audit['passed'] if fault is None else
                  code != 0 and audit['failure']['code'] == expected_code)
        checks.append({'label': label, 'lane': lane, 'passed': passed,
                       'exitCode': code, 'expectedFailure': expected_code})
        print(json.dumps(checks[-1]), flush=True)
        if not passed:
            break
    write_json(results / 'summary.json', {
        'schemaVersion': 1, 'classification': 'standalone-installation',
        'installationSha256': digest(root / 'installation.json'),
        'offlineReinstallationPassed': True, 'checks': checks,
        'passed': len(checks) == 6 and all(item['passed'] for item in checks),
    })
    if not read_json(results / 'summary.json')['passed']:
        raise RuntimeError(f'Installed generation failed; inspect {results}')


def verify(args: argparse.Namespace) -> None:
    """Recheck the installed artifacts and join each observation to its oracle."""
    root = args.destination.resolve()
    installation = read_json(root / 'installation.json')
    for item in installation['files']:
        verify_file(root / item['path'], item['sha256'])
    if inventory(root) != read_json(root / 'inventory.json'):
        raise ValueError('Installed dependency inventory changed')
    summary = read_json(root / 'results/summary.json')
    if (not summary['passed'] or not summary['offlineReinstallationPassed']
            or summary['installationSha256'] != digest(root / 'installation.json')):
        raise ValueError('Unqualified or incorrectly bound installation summary')
    reference = read_json(root / 'reference.json')
    expected = {item['id']: item for item in reference['cases']}
    providers = read_json(root / 'providers.json')
    native_hashes = {item['path']: item['sha256']
                     for item in providers['files']}
    stops = {'eos': 'stop-token', 'max_tokens': 'max-tokens',
             'stop_sequence': 'stop-sequence'}
    labels = {'doe-first', 'doe-reopen', 'dawn-control', 'missing-library',
              'incompatible-package', 'missing-model'}
    if ({item['label'] for item in summary['checks']} != labels
            or len(summary['checks']) != len(labels)):
        raise ValueError('Installation acceptance cases are missing or duplicated')
    for check in summary['checks']:
        if not check['passed']:
            raise ValueError(f'Failed installation check: {check["label"]}')
        audit = read_json(root / 'results' / f'{check["label"]}-audit.json')
        if check['expectedFailure'] is not None:
            if (audit['passed'] or check['exitCode'] == 0
                    or audit['failure']['code'] != check['expectedFailure']):
                raise ValueError('Failure check did not reject its intended boundary')
            continue
        path = root / 'results' / f'{check["label"]}.json'
        verify_file(path, audit['receiptSha256'])
        receipt = read_json(path)
        if (not audit['passed'] or not audit['nativeLoaded'] or not receipt['passed']
                or audit['nativeSha256'] != native_hashes[audit['nativePath']]
                or receipt['referenceSha256'] != digest(root / 'reference.json')
                or receipt['contractSha256'] != digest(root / 'contract.json')
                or receipt['providerManifestSha256'] != digest(root / 'providers.json')
                or any(item['accessible'] for item in audit['workspaceProbes'])
                or set(audit['networkInterfaces']) != {'lo'}):
            raise ValueError(f'Incorrect installation identity: {check["label"]}')
        if (not receipt['cleanup']['unloaded']
                or receipt['cleanup']['devicesDestroyed'] < 1):
            raise ValueError('Missing unload/device cleanup observation')
        if {item['id'] for item in receipt['rows']} != set(expected) | {'cancellation'}:
            raise ValueError('Incomplete generation oracle coverage')
        for row in receipt['rows']:
            if row['id'] == 'cancellation':
                contract = read_json(root / 'contract.json')
                first = expected[contract['cases'][0]['id']]
                if (row['followingOutputText'] != first['outputText']
                        or row['chunks'] != contract['cancellation']['abortAfterStreamChunks']
                        or not first['outputText'].startswith(row['cancelledText'])):
                    raise ValueError('Cancellation/reuse oracle mismatch')
            else:
                case = expected[row['id']]
                if (row['tokenIds'] != case['tokenIds']
                        or row['outputText'] != case['outputText']
                        or row['stats']['stopReason'] != stops[case['stopReason']]):
                    raise ValueError(f'Generation oracle mismatch: {row["id"]}')
    print(json.dumps({'passed': True, 'checksVerified': len(labels),
                      'installedFilesVerified': len(inventory(root))}))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['prepare', 'run', 'verify'])
    parser.add_argument('--destination', type=Path, required=True,
                        help='New standalone directory, or prepared directory to run')
    for name in ('contract', 'providers', 'reference'):
        parser.add_argument(f'--{name}', type=Path,
                            help=f'Existing frozen {name} JSON for preparation')
    args = parser.parse_args()
    if args.phase == 'prepare':
        for name in ('contract', 'providers', 'reference'):
            if getattr(args, name) is None:
                parser.error(f'prepare requires --{name}')
        prepare(args)
    elif args.phase == 'run':
        execute(args)
    else:
        verify(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

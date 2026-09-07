"""Reproduce a single model lane without promoting a failed pairwise control."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

root = Path(__file__).resolve().parents[4]
checkpoint = Path(__file__).resolve().parent
lane = sys.argv[1]
assert lane in ('W0', 'D0')
host = sys.argv[2] if len(sys.argv) > 2 else 'electron'
assert host in ('node', 'electron')
result = json.loads((checkpoint / 'gemma270m/result.json').read_text())
contract = json.loads((root / 'bench/external-projects/doppler/gemma270m-electron.harness.json').read_text())['workload']['modelContract']
out = checkpoint / (f'gemma270m-{lane}-isolated' if host == 'electron' else f'gemma270m-{lane}-node')
out.mkdir(exist_ok=False)
command = [result['application']['executable'], *result['runs']['W0']['command']]
command[command.index('--out-dir') + 1] = str(out)
if host == 'node':
    command = ['/usr/bin/node', str(root / 'bench/tools/export_doppler_int4ple_reference.mjs'), *command[command.index('--doppler-root'):]]
provider = contract['providers'][lane]
upstream = root / 'bench/out/external-projects/doppler/upstream'
environment = {key: value for key, value in os.environ.items() if not key.startswith('DOE_')}
declared = {
    'DOPPLER_NODE_WEBGPU_MODULE': str(root / provider['wrapper']['path']),
    'DOE_DOPPLER_QUALIFICATION_EXPORT_TOOL': str(root / 'bench/tools/export_doppler_int4ple_reference.mjs'),
    'DOE_DOPPLER_QUALIFICATION_PROVIDER_CONTRACT': str(root / contract['providerContract']['path']),
    'DOE_DOPPLER_QUALIFICATION_PROVIDER_TARGET': str((root if provider['targetRoot'] == 'repo' else upstream) / provider['target']['path']),
    'DOE_WEBGPU_LIB': str(root / 'runtime/zig/zig-out/lib/libwebgpu_doe.so'),
}
environment.update(declared)
(out / 'command.txt').write_text(shlex.join(['env', *(f'{key}={value}' for key, value in declared.items()), *command]) + '\n')
with (out / 'stdout.log').open('w') as stdout, (out / 'stderr.log').open('w') as stderr:
    completed = subprocess.run(command, cwd=upstream, env=environment, stdout=stdout, stderr=stderr, timeout=600)
(out / 'exit-code.txt').write_text(str(completed.returncode) + '\n')
sys.exit(completed.returncode)

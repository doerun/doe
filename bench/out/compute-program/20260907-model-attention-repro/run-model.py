"""Run the unchanged diagnostic model lane with a declared compiler experiment."""
from pathlib import Path
import json
import os
import shlex
import subprocess
import sys

here = Path(__file__).resolve().parent
root = here.parents[3]
source = here.parent / '20260907-linux-completion'
experiment = sys.argv[1] if len(sys.argv) > 1 else 'dont-unroll'
assert experiment in ('dont-unroll', 'multi-dot-loops', 'native-node', 'native-electron', 'dawn-electron', 'p0-electron')
out = here / f'{experiment}-model'
out.mkdir(exist_ok=False)
prior = json.loads((source / 'gemma270m/result.json').read_text())
args = prior['runs']['W0']['command']
command = ([prior['application']['executable'], *args] if experiment.endswith('electron') else
           ['/usr/bin/node', str(root / 'bench/tools/export_doppler_int4ple_reference.mjs'), *args[args.index('--doppler-root'):]])
command[command.index('--out-dir') + 1] = str(out)
environment = {key: value for key, value in os.environ.items() if not key.startswith('DOE_') and key != 'LD_PRELOAD'}
declared = {
    'DOPPLER_NODE_WEBGPU_MODULE': str(root / 'bench/external-projects/doppler/provider-doe.mjs'),
    'DOE_DOPPLER_QUALIFICATION_PROVIDER_CONTRACT': str(root / 'packages/doe-gpu/src/node-webgpu.js'),
    'DOE_DOPPLER_QUALIFICATION_PROVIDER_TARGET': str(here / 'retained/installed-package/node_modules/doe-gpu/src/compute.js'),
    'DOE_WEBGPU_LIB': str(here / 'retained/installed-package/node_modules/doe-gpu-linux-x64/libwebgpu_doe.so'),
    'LD_PRELOAD': str(here / f'{experiment}.so'),
}
if experiment.startswith(('native-', 'dawn-', 'p0-')):
    del declared['LD_PRELOAD']
    declared['DOE_WEBGPU_LIB'] = str(here / 'native-retained/installed-package/node_modules/doe-gpu-linux-x64/libwebgpu_doe.so')
    declared['DOE_DOPPLER_QUALIFICATION_PROVIDER_TARGET'] = str(here / 'native-retained/installed-package/node_modules/doe-gpu/src/compute.js')
if experiment in ('dawn-electron', 'p0-electron'):
    declared['DOPPLER_NODE_WEBGPU_MODULE'] = str(root / 'bench/external-projects/doppler/provider-dawn.mjs')
    declared['DOE_DOPPLER_QUALIFICATION_PROVIDER_TARGET'] = str(root / 'bench/out/external-projects/doppler/upstream/node_modules/webgpu/index.js')
if experiment == 'p0-electron':
    declared['DOE_DOPPLER_QUALIFICATION_PROVIDER_TARGET'] = str(here / 'p0-provider/index.js')
if experiment.endswith('electron'):
    declared['DOE_DOPPLER_QUALIFICATION_EXPORT_TOOL'] = str(root / 'bench/tools/export_doppler_int4ple_reference.mjs')
environment.update(declared)
(out / 'command.txt').write_text(shlex.join(['env', *(f'{k}={v}' for k,v in declared.items()), *command]) + '\n')
with (out / 'stdout.log').open('w') as stdout, (out / 'stderr.log').open('w') as stderr:
    result = subprocess.run(command, cwd=root / 'bench/out/external-projects/doppler/upstream',
                            env=environment, stdout=stdout, stderr=stderr, timeout=600)
(out / 'exit-code.txt').write_text(str(result.returncode) + '\n')
raise SystemExit(result.returncode)

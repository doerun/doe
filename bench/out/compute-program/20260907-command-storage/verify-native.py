"""Verify retained package bytes and prepare public C tests against its library."""
from pathlib import Path
import hashlib
import json
import subprocess
import tarfile
from bench.lib.compute_program_package import load_qualification

repository = Path.cwd()
root = Path(__file__).resolve().parent / 'final-validation'
root.mkdir(exist_ok=True)
qualification = load_qualification(repository/'bench/out/compute-program/20260907-command-storage-qualified/summary.json', repository)
archive = next(p['path'] for p in qualification['packages'] if 'linux-x64' in p['path'])
extracted = root/'extracted-native'
extracted.mkdir(exist_ok=True)
with tarfile.open(archive) as stream:
    for name, staged in [('libwebgpu_doe.so','packages/doe-gpu-linux-x64/bin/libwebgpu_doe.so'),
                         ('doe_napi.node','packages/doe-gpu/build/Release/doe_napi.node')]:
        data = stream.extractfile('package/bin/'+name).read()
        assert data == (repository/staged).read_bytes()
        (extracted/name).write_bytes(data)
library = extracted/'libwebgpu_doe.so'
assert hashlib.sha256(library.read_bytes()).hexdigest() == qualification['hosts'][0]['libraryHash']
previous = repository/'bench/out/compute-program/20260907-binding-storage/final-validation/extracted-native/libwebgpu_doe.so'
def symbols(path):
    output = subprocess.check_output(['nm','-D','--defined-only',str(path)],text=True)
    return sorted(line.split()[-1] for line in output.splitlines())
assert symbols(library) == symbols(previous)
(root/'public-symbols.txt').write_text('\n'.join(symbols(library))+'\n')
commands=[]
for name in ['native_async_pipeline','native_recorded_compute']:
    source = repository/f'runtime/zig/tests/{name}.c'
    (root/source.name).write_bytes(source.read_bytes())
    command = ['cc','-std=c11','-Wall','-Wextra','-Werror','-I','runtime/zig/vendor/webgpu-headers',
               str(source),'-L',str(extracted),'-Wl,-rpath,'+str(extracted),'-lwebgpu_doe','-o',str(root/name)]
    commands.append(command)
    subprocess.run(command,check=True)
(root/'native-c-build.command.json').write_text(json.dumps(commands,indent=2)+'\n')
print('PASS: qualification schema and hashes, extracted native/addon equality, matching host library hashes, unchanged exported symbols; C tests compiled against extracted library')

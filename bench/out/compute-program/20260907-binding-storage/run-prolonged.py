"""Recheck the existing bounded resource cases using exact qualified archive members."""
from pathlib import Path
import json
import subprocess
from bench.lib.compute_program_package import load_qualification, validate_package_root

repository = Path.cwd()
root = Path(__file__).resolve().parent
matrix = repository / 'bench/out/compute-program/20260907-binding-storage-applications'
run = json.loads((matrix / 'image_edges.doe-webgpu.process-0.json').read_text())
package = Path(run['packageRoot'])
qualification = load_qualification(Path(run['packageQualification']['path']), repository)
validate_package_root(package, qualification)
fixtures = root / 'retained-tests'
fixtures.mkdir()
for name in ['native-resource-retention', 'live-simulation']:
    source = repository / f'packages/doe-gpu/test/integration/test-integration-{name}.js'
    text = source.read_text()
    for before, after in [('../../src/native.js', (package/'src/native.js').as_uri()),
                          ('../../src/compute-program.js', (package/'src/compute-program.js').as_uri()),
                          ('../../examples/live-simulation/', (package/'examples/live-simulation').as_uri()+'/')]:
        text = text.replace(before, after)
    fixture = fixtures / f'{name}.mjs'
    fixture.write_text(text)
    command = ['/usr/bin/node', str(fixture), '--prolonged']
    (root/f'{name}.command.json').write_text(json.dumps(command, indent=2)+'\n')
    with (root/f'{name}.log').open('w') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=900, check=False)
    validate_package_root(package, qualification)
    print(name, 'exit', result.returncode, flush=True)
    if result.returncode:
        raise SystemExit(result.returncode)
print('PASS: exact installed archives before and after bounded prolonged checks')

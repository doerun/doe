"""Run from the repository root after retained-package installation."""
import hashlib
import json
from pathlib import Path
import subprocess
import jsonschema
from bench.lib.compute_program_package import load_qualification, validate_package_root

root = Path.cwd()
run = Path(__file__).resolve().parent
result = json.loads((run / 'result.json').read_text())
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def reference(value):
    assert digest(Path(value['path'])) == value['sha256'], value['path']
def schema(name, value):
    jsonschema.Draft202012Validator(json.loads((root / 'config' / name).read_text())).validate(value)
schema('gemma270m-electron-qualification.schema.json', result)
assert result['status'] == 'passed' and result['pass'] and result['comparisonBaseline'] == 'P0'
reference(result['oracle'])
reference(result['packageQualification'])
qualification = load_qualification(Path(result['packageQualification']['path']), root)
package = (root / result['providers']['D0']['target']['path']).parent.parent
validate_package_root(package, qualification)
for lane, entry in result['runs'].items():
    for prefix in ['stdout', 'stderr', 'receipt']:
        reference({'path': entry[prefix+'Path'], 'sha256': entry[prefix+'Sha256']})
    reference(entry['nativeIdentity'])
    identity = json.loads(Path(entry['nativeIdentity']['path']).read_text())
    schema('gemma270m-electron-native-identity.schema.json', identity)
    reference(identity['library'])
    expected = (qualification['hosts'][0]['libraryHash'] if lane == 'D0'
                else result['providers']['W0']['sourceBuild']['library']['sha256'])
    assert identity['library']['sha256'] == expected
control = result['providers']['W0']
for key in ['patch', 'library', 'provenance']:
    link = control['sourceBuild'][key]
    reference({'path': str(root / link['path']), 'sha256': link['sha256']})
script = """
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';
const load = async path => JSON.parse(await readFile(path, 'utf8'));
const root = process.cwd(), run = process.argv[1];
const { evaluateQualification } = await import(pathToFileURL(resolve(root, 'bench/external-projects/doppler/oracle.mjs')));
const harness = await load(resolve(root, 'bench/external-projects/doppler/gemma270m-electron.harness.json'));
const result = await load(resolve(run, 'result.json'));
const contract = { ...harness.workload.modelContract, providers: result.providers };
const laneRoots = Object.fromEntries(['W0', 'D0'].map(lane => [lane, resolve(run, 'lanes', lane)]));
const receipts = {};
for (const lane of ['W0', 'D0']) receipts[lane] = await load(resolve(laneRoots[lane], 'doppler_int4ple_reference_export.json'));
const oracle = await evaluateQualification({ contract, laneRoots, receipts });
assert.deepEqual(oracle, await load(resolve(run, 'oracle.json')));
assert.equal(oracle.pass, true);
"""
subprocess.run(['node', '--input-type=module', '-e', script, str(run)], check=True)
print('PASS: retained package files, loaded binaries, control provenance, transcript hashes, and recomputed frozen oracle')

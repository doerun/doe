"""Validate retained producer output; this does not admit performance claims."""
from pathlib import Path
import hashlib
import json
import subprocess

from native_compare_modules import contracts

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
schema = json.loads((ROOT / 'config/shader-artifact.schema.json').read_text())
for path in sorted((OUT / 'manifests').glob('*.json')):
    errors = contracts.validate_manifest(path, schema)
    assert not errors, errors
    print('PASS schema-only backend probe:', path.name)
meta = json.loads((OUT / 'physical.meta.json').read_text())
assert meta['executionSuccessCount'] == 1
assert meta['executionErrorCount'] == 0
assert meta['executionDispatchCount'] == 1
assert meta['outputOracleMatchedCount'] == 1
assert meta['fallbackUsed'] is False
path = OUT / 'physical-artifacts' / Path(meta['shaderArtifactManifestPath']).name
manifest = json.loads(path.read_text())
assert not contracts.validate_manifest(path, schema)
assert manifest['hash'] == meta['shaderArtifactManifestHash']
prehash = path.read_text().rsplit(',"hash":', 1)[0] + '}'
assert hashlib.sha256(prehash.encode()).hexdigest() == manifest['hash']
assert manifest['wgslHashKind'] == 'source_observation'
assert hashlib.sha256((OUT / 'sentinel.wgsl').read_bytes()).hexdigest() == manifest['wgslSha256']
assert hashlib.sha256((OUT / 'expected.bin').read_bytes()).hexdigest() == meta['outputOracleActualSha256']
observed_content = False
for stage in manifest['stages']:
    if stage['hashKind'] != 'content':
        assert 'artifactPath' not in stage
        continue
    observed_content = True
    binary = path.parent / stage['artifactPath']
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    assert digest == stage['artifactSha256'] == manifest['spirvSha256']
    subprocess.run(['spirv-val', '--target-env', 'vulkan1.1', str(binary)], check=True)
assert observed_content
print('PASS physical output oracle, manifest prehash, source observation, content digest, Vulkan 1.1 validation')

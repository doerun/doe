"""Verify retained generation evidence, including compressed producer receipts."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--schema', type=Path, required=True)
    parser.add_argument('--local-archives', action='store_true')
    args = parser.parse_args()
    schema = json.loads(args.schema.read_text())
    Draft202012Validator.check_schema(schema)
    manifest = json.loads((args.report / 'manifest.json').read_text())
    Draft202012Validator({'$ref': '#/$defs/manifest', '$defs': schema['$defs']}).validate(manifest)
    reference_bytes = (args.report / 'reference.json').read_bytes()
    reference = json.loads(reference_bytes)
    expected = {case['id']: case for case in reference['cases']}
    reference_hash = hashlib.sha256(reference_bytes).hexdigest()
    providers = {cohort: hashlib.sha256((args.report / file).read_bytes()).hexdigest()
                 for cohort, file in [('baseline', 'providers.json'), ('candidate', 'candidate-providers.json')]}
    stop_reasons = {'eos': 'stop-token', 'max_tokens': 'max-tokens', 'stop_sequence': 'stop-sequence'}
    for artifact in manifest['artifacts']:
        path = args.report / artifact['path']
        if not path.resolve().is_relative_to(args.report.resolve()):
            raise ValueError(f'Artifact escapes the report: {path}')
        data = path.read_bytes()
        if len(data) != artifact['bytes'] or hashlib.sha256(data).hexdigest() != artifact['sha256']:
            raise ValueError(f'Retained artifact identity mismatch: {path}')
        definition = artifact['schemaDefinition']
        if definition is not None:
            payload = gzip.decompress(data) if path.suffix == '.gz' else data
            receipt = json.loads(payload)
            Draft202012Validator({'$ref': '#/$defs/' + definition, '$defs': schema['$defs']}).validate(receipt)
            if definition == 'receipt':
                cohort = 'candidate' if 'candidate' in artifact['path'] else 'baseline'
                if not receipt['passed'] or receipt['contractSha256'] != reference['contractSha256']:
                    raise ValueError(f'Unqualified retained receipt: {path}')
                if receipt['referenceSha256'] != reference_hash or receipt['providerManifestSha256'] != providers[cohort]:
                    raise ValueError(f'Incorrect reference/provider join: {path}')
                for row in receipt['rows']:
                    if row['id'] == 'cancellation':
                        if row['followingOutputText'] != expected['full_sentence']['outputText']:
                            raise ValueError(f'Post-cancellation output mismatch: {path}')
                    else:
                        case = expected[row['id']]
                        if (row['tokenIds'] != case['tokenIds'] or row['outputText'] != case['outputText']
                                or row['stats']['stopReason'] != stop_reasons[case['stopReason']]):
                            raise ValueError(f'Complete output/stopping mismatch: {path}')
                if 'qualification' in artifact['path'] and set(expected) != {
                    row['id'] for row in receipt['rows'] if row['id'] != 'cancellation'}:
                    raise ValueError(f'Incomplete qualification cases: {path}')
    patch = gzip.decompress((args.report / 'candidate.patch.gz').read_bytes())
    if hashlib.sha256(patch).hexdigest() != manifest['sourcePatchSha256']:
        raise ValueError('Rejected candidate patch identity mismatch')
    if args.local_archives:
        for archive in manifest['archives']:
            data = Path(archive['path']).read_bytes()
            if len(data) != archive['bytes'] or hashlib.sha256(data).hexdigest() != archive['sha256']:
                raise ValueError(f'Local archive identity mismatch: {archive["path"]}')
    decision = json.loads((args.report / 'disposition.json').read_text())
    if decision['disposition'] != 'rejected' or decision['performancePromoted']:
        raise ValueError('This retained rejected candidate cannot promote performance')
    if manifest['runtimeCandidateRetained'] or decision['timingAdmissionPassed'] != all(
            check['passed'] for check in decision['checks']):
        raise ValueError('Candidate retention/admission contradicts its failed criteria')
    print(json.dumps({'passed': True, 'artifactsVerified': len(manifest['artifacts']),
                      'localArchivesVerified': args.local_archives}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

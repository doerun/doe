"""Diagnostic compiler-option experiment using the existing admitted child runner."""
from pathlib import Path
import json
import shutil
import statistics
import sys

from bench.runners.run_compute_program_evidence import run_child
from bench.lib.compute_program_package import load_qualification, validate_package_root

repository = Path.cwd()
root = Path(__file__).resolve().parent
out = root / 'alternating'
out.mkdir()
base = repository / 'bench/out/compute-program/20260907-concurrent-applications'
optimized = repository / 'bench/out/compute-program/20260907-addon-o2-applications-retry'
policy = json.loads((base / 'policy.json').read_text())
policy['processRuns'] = 6
policy_path = out / 'policy.json'
policy_path.write_text(json.dumps(policy, indent=2) + '\n')
shutil.copy2(base / 'hardware-profile.json', out / 'hardware-profile.json')
variants = {}
for name, matrix in [('unoptimized', base), ('optimized', optimized)]:
    run = json.loads((matrix / 'image_edges.doe-webgpu.process-0.json').read_text())
    package = Path(run['packageRoot'])
    qualification = Path(run['packageQualification']['path'])
    validate_package_root(package, load_qualification(qualification, repository))
    variants[name] = (package, qualification)
reports = {}
for application in policy['applications']:
    reports[application] = {name: [] for name in variants}
    for iteration in range(policy['processRuns']):
        order = list(variants) if iteration % 2 == 0 else list(reversed(variants))
        for name in order:
            package, qualification = variants[name]
            output = out / f'{application}.{name}.{iteration}.json'
            report = run_child('doe-webgpu', application, 'measure', output, policy_path,
                               policy, 'vulkan', '/usr/bin/node', '', None, package, qualification)
            reports[application][name].append(report)
            print(application, iteration, name, 'accepted', flush=True)
with (out / 'comparison.tsv').open('w') as table:
    table.write('application\tmetric\tunoptimized_median_ms\toptimized_median_ms\tunoptimized_over_optimized\n')
    identity_fields = ['programHash', 'inputHashes', 'outputHash', 'dispatchCount', 'clearedBytes',
                       'uploadedBytes', 'submissionCount', 'readbackBytes', 'readbackPath', 'completionMode']
    for application, variants in reports.items():
        samples = {name: [sample for report in group for sample in report['samples']]
                   for name, group in variants.items()}
        expected = samples['unoptimized'][0]['receipt']
        for group in samples.values():
            for sample in group:
                assert sample['oracle']['passed']
                for field in identity_fields:
                    assert sample['receipt'][field] == expected[field], (application, field)
        for metric in ['wallMs', 'cpuMs', 'encode', 'submitWait', 'readback', 'total']:
            values = [statistics.median(sample.get(metric, sample['receipt']['timingMs'].get(metric))
                                        for sample in samples[name])
                      for name in ['unoptimized', 'optimized']]
            table.write(f'{application}\t{metric}\t{values[0]}\t{values[1]}\t{values[0]/values[1]}\n')
print('PASS: alternating variants, accepted outputs and equivalent execution receipts; diagnostic timings only')

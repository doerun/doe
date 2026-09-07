"""Alternate exact qualified Doe packages through the existing frozen-work runner."""
from pathlib import Path
import json
import shutil

from bench.runners.run_compute_program_evidence import run_child
from bench.native_compare_modules.reporting import format_stats
from bench.lib.compute_program_package import load_qualification, validate_package_root

repository = Path.cwd()
root = Path(__file__).resolve().parent
out = root / 'alternating'
out.mkdir()
base = repository / 'bench/out/compute-program/20260907-dispatch-copy-applications'
candidate = repository / 'bench/out/compute-program/20260907-command-storage-applications'
policy = json.loads((base / 'policy.json').read_text())
policy_path = out / 'policy.json'
policy_path.write_text(json.dumps(policy, indent=2) + '\n')
shutil.copy2(base / 'hardware-profile.json', out / 'hardware-profile.json')
variants = {}
for name, matrix in [('previous', base), ('candidate', candidate)]:
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
    table.write('application\tmetric\tquantile\tprevious_ms\tcandidate_ms\tprevious_over_candidate\n')
    identity_fields = ['programHash', 'inputHashes', 'outputHash', 'dispatchCount', 'clearedBytes',
                       'uploadedBytes', 'submissionCount', 'readbackBytes', 'readbackPath', 'completionMode']
    for application, groups in reports.items():
        samples = {name: [sample for report in group for sample in report['samples']]
                   for name, group in groups.items()}
        expected = samples['previous'][0]['receipt']
        for group in samples.values():
            for sample in group:
                assert sample['oracle']['passed']
                for field in identity_fields:
                    assert sample['receipt'][field] == expected[field], (application, field)
        for metric in ['wallMs', 'cpuMs', 'encode', 'submitWait', 'readback', 'total']:
            values = [format_stats([sample.get(metric, sample['receipt']['timingMs'].get(metric))
                                    for sample in samples[name]], percentile_method=policy['percentileMethod'])
                      for name in ['previous', 'candidate']]
            for quantile in ['p50Ms', 'p95Ms', 'p99Ms']:
                left, right = [value[quantile] for value in values]
                table.write(f'{application}\t{metric}\t{quantile}\t{left}\t{right}\t{left/right}\n')
with (out / 'process-costs.tsv').open('w') as table:
    table.write('application\tvariant\tprocess\tdeviceStartupMs\tpreparationMs\tcoldWallMs\tteardownMs\tpeakProcessRssBytes\tallocatedBufferBytes\n')
    for application, groups in reports.items():
        for name, group in groups.items():
            for index, report in enumerate(group):
                values = [report['deviceStartupMs'], report['preparationMs'], report['cold']['wallMs'],
                          report['teardownMs'], report['peakProcessRssBytes'], report['allocatedBufferBytes']]
                table.write('\t'.join(map(str, [application, name, index, *values]))+'\n')
for package, qualification in variants.values():
    validate_package_root(package, load_qualification(qualification, repository))
print('PASS: alternating packages, accepted outputs and equivalent execution receipts; diagnostic timings only')

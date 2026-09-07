"""Inspect ordinary-provider application measurements, including incumbent controls."""
import csv
import json
from pathlib import Path
from bench.native_compare_modules.reporting import format_stats

root = Path(__file__).resolve().parent
matrix = root.parent/'20260907-command-storage-applications'
policy = json.loads((matrix/'policy.json').read_text())
with (root/'ordinary-incumbents.tsv').open('w') as table:
    writer = csv.writer(table,delimiter='\t')
    writer.writerow(['application','backend','comparator','metric','quantile','doe','incumbent','incumbent_over_doe','status','caveat'])
    for application in policy['applications']:
        reports = {provider:[json.loads((matrix/f'{application}.{provider}.process-{i}.json').read_text())
                             for i in range(policy['processRuns'])]
                   for provider in ['doe-webgpu','dawn','wgpu']}
        samples = {provider:[sample for report in group for sample in report['samples']]
                   for provider,group in reports.items()}
        expected = samples['doe-webgpu'][0]['receipt']
        for provider,group in samples.items():
            for sample in group:
                assert sample['oracle']['passed']
                for field in ['programHash','inputHashes','dispatchCount','clearedBytes','uploadedBytes',
                              'submissionCount','readbackBytes','readbackPath','completionMode']:
                    assert sample['receipt'][field] == expected[field], (application,provider,field)
        for comparator in ['dawn','wgpu']:
            for metric in ['wallMs','cpuMs','encode','submitWait','readback']:
                stats = {provider:format_stats([s.get(metric,s['receipt']['timingMs'].get(metric))
                                                for s in samples[provider]],percentile_method=policy['percentileMethod'])
                         for provider in ['doe-webgpu',comparator]}
                for quantile in ['p50Ms','p95Ms','p99Ms']:
                    doe,incumbent=[stats[provider][quantile] for provider in ['doe-webgpu',comparator]]
                    writer.writerow([application,'vulkan',comparator,metric,quantile,doe,incumbent,incumbent/doe,
                                     'diagnostic','Deno host/polling asymmetry; suspicious ratios; no leadership claim' if comparator=='wgpu'
                                     else 'complete invocation; persistent resources; preparation and cold costs remain in raw process reports'])
print('PASS: accepted outputs and matched work receipts; ordinary comparisons remain diagnostic')

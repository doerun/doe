"""Isolate native command preparation; the GPU oracle runs outside timing."""
from pathlib import Path
import csv
import hashlib
import json
import os
import subprocess
import tarfile
from bench.lib.compute_program_package import load_qualification
from bench.native_compare_modules.reporting import format_stats

repository = Path.cwd()
root = Path(__file__).resolve().parent
out = root / 'native-record-cost-validated'
out.mkdir()
variants = {}
for name, folder in [('previous','20260907-dispatch-copy-qualified'), ('candidate','20260907-command-storage-qualified')]:
    qualification = repository / 'bench/out/compute-program' / folder / 'summary.json'
    report = load_qualification(qualification, repository)
    archive = next(p['path'] for p in report['packages'] if 'linux-x64' in p['path'])
    directory = out / name
    directory.mkdir()
    library = directory / 'libwebgpu_doe.so'
    with tarfile.open(archive) as tf:
        library.write_bytes(tf.extractfile('package/bin/libwebgpu_doe.so').read())
    assert hashlib.sha256(library.read_bytes()).hexdigest() == report['hosts'][0]['libraryHash']
    variants[name] = directory
command = ['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I','runtime/zig/vendor/webgpu-headers',
           str(root/'record-cost.c'),'-L',str(variants['previous']),'-Wl,-rpath,'+str(variants['previous']),
           '-lwebgpu_doe','-ldl','-o',str(out/'record-cost')]
(out/'compile.command.json').write_text(json.dumps(command,indent=2)+'\n')
subprocess.run(command,check=True)
rows = {name: [] for name in variants}
for index in range(3):
    for name in (list(variants) if index % 2 == 0 else list(reversed(variants))):
        env = dict(os.environ, LD_LIBRARY_PATH=str(variants[name]))
        result = subprocess.run([str(out/'record-cost')],env=env,capture_output=True,text=True,timeout=120)
        (out/f'{name}.{index}.tsv').write_text(result.stdout)
        (out/f'{name}.{index}.stderr').write_text(result.stderr)
        assert result.returncode == 0, result.stderr
        assert f"native-library: {variants[name] / 'libwebgpu_doe.so'}" in result.stderr
        samples = list(csv.DictReader(result.stdout.splitlines(),delimiter='\t'))
        assert samples and len(samples) == int(samples[-1]['sample']) + 1
        assert 'PASS: untimed GPU check' in result.stderr
        rows[name].extend(samples)
        print(name,index,'accepted',flush=True)
with (out/'comparison.tsv').open('w') as table:
    table.write('metric\tquantile\tprevious_ms\tcandidate_ms\tprevious_over_candidate\n')
    for metric in ['recordWallMs','recordCpuMs','finishAndCleanupMs']:
        values = [format_stats([float(row[metric]) for row in rows[name]],percentile_method='nearest-rank')
                  for name in ['previous','candidate']]
        for quantile in ['p50Ms','p95Ms','p99Ms']:
            left,right=[v[quantile] for v in values]
            table.write(f'{metric}\t{quantile}\t{left}\t{right}\t{left/right}\n')
print('Diagnostic native preparation only; untimed GPU oracle; no useful-operation performance claim')

"""Freeze-qualified, balanced independent-process inference measurements."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import time
import numpy as np


def identity(path):
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['doe', 'dawn', 'doppler', 'out']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists(): parser.error('Measurement directory must be new')
    args.out.mkdir(parents=True)
    repo = Path(__file__).resolve().parents[3]
    policy_path = repo / 'config/onnx-vulkan-campaign.json'
    policy = json.loads(policy_path.read_text())
    qualified = {arm: json.loads(getattr(args, arm).read_text()) for arm in ['doe', 'dawn']}
    for arm, receipt in qualified.items():
        if not receipt['passed'] or receipt['negativeControl'] or receipt['policy'] != identity(policy_path):
            raise ValueError('Qualification or policy failure: ' + arm)
        for item in receipt['inputs'].values():
            if identity(Path(item['path']))['sha256'] != item['sha256']:
                raise ValueError('Qualified artifact changed')
        if not receipt['operatorNames'] or set(receipt['operatorProviders']) != {'WebGpuExecutionProvider'}:
            raise ValueError('Operator placement failed')
    for name in ['application', 'provider', 'bridge', 'context', 'reference']:
        if qualified['doe']['inputs'][name] != qualified['dawn']['inputs'][name]:
            raise ValueError('Source-matched input mismatch: ' + name)
    if qualified['doe']['operatorNames'] != qualified['dawn']['operatorNames']:
        raise ValueError('Consumer operation sequence differs')
    doppler = json.loads(args.doppler.read_text())
    if not doppler['passed']: raise ValueError('Doppler safety is unqualified')
    settings = policy['measurement']
    rows = []
    summary = {'schemaVersion': 1, 'classification': 'source-matched-application-measurement',
        'policy': identity(policy_path), 'qualification': {a: identity(getattr(args, a)) for a in qualified},
        'dopplerSafety': identity(args.doppler), 'passed': False, 'disposition': None,
        'failure': None, 'aaMedianRatio': None, 'primaryRatio': None, 'lowerConfidenceRatio': None,
        'regressionRatios': {}, 'performanceCorrections': 0, 'rows': rows}

    def run(arm, stage, index, cache, warmup, runs):
        receipt = qualified[arm]; inputs = receipt['inputs']
        label = f'{stage}-{index:02d}-{arm}'
        log = args.out / (label + '.log'); observations = args.out / (label + '.observations')
        environment = {k: v for k, v in os.environ.items() if k not in (
            'LD_PRELOAD', 'LD_LIBRARY_PATH', 'DOE_WEBGPU_LIB', 'XDG_CACHE_HOME', 'MESA_SHADER_CACHE_DIR')
            and not k.startswith('CAMPAIGN_')}
        environment.update({'CAMPAIGN_ARM': arm, 'CAMPAIGN_MODE': 'timing',
            'CAMPAIGN_PROFILE': str((args.out / label).resolve()),
            'CAMPAIGN_OBSERVATIONS': str(observations.resolve()), 'CAMPAIGN_WARMUP': str(warmup),
            'CAMPAIGN_RUNS': str(runs), 'CAMPAIGN_ATOL': str(policy['correctness']['absoluteTolerance']),
            'CAMPAIGN_RTOL': str(policy['correctness']['relativeTolerance']),
            'XDG_CACHE_HOME': str(cache.resolve()), 'MESA_SHADER_CACHE_DIR': str(cache.resolve())})
        for key, name in [('PROVIDER','provider'),('NATIVE','native'),('BRIDGE','bridge'),('CONTEXT','context'),('REFERENCE','reference')]:
            environment['CAMPAIGN_' + key] = inputs[name]['path']
        start = time.perf_counter_ns()
        with log.open('w') as stream:
            child = subprocess.run([inputs['application']['path']], cwd=Path(inputs['application']['path']).parent,
                                   env=environment, stdout=stream, stderr=subprocess.STDOUT)
        wall = time.perf_counter_ns() - start
        content = log.read_text()
        row = {'arm': arm, 'stage': stage, 'index': index, 'exitCode': child.returncode,
               'cache': str(cache.resolve()), 'log': identity(log), 'processWallNs': wall,
               'runWallNs': [], 'runCpuNs': [], 'peakRssBytes': None}
        rows.append(row)
        if child.returncode or 'CampaignCleanupFailure ' in content:
            raise ValueError('Measured application failed: ' + label)
        samples = [line.split() for line in observations.read_text().splitlines()]
        if len(samples) != runs: raise ValueError('Missing measured invocation')
        row['runWallNs'] = [int(parts[1]) for parts in samples]
        row['runCpuNs'] = [float(parts[2]) for parts in samples]
        if min(row['runWallNs']) <= 0: raise ValueError('Incomplete operation timing')
        row['peakRssBytes'] = int(next(line.split()[1] for line in content.splitlines() if line.startswith('CampaignPeakRss ')))
        row['observations'] = identity(observations)
        row['loadAverage'] = list(os.getloadavg())
        return row

    try:
        caches = {arm: args.out / (arm + '-warm-cache') for arm in qualified}
        for arm, cache in caches.items():
            cache.mkdir(); run(arm, 'cache-precondition', 0, cache, settings['warmupRuns'], 1)
        aa = []
        for index in range(settings['aaPairs']):
            pair = [run('dawn', 'aa-first', index, caches['dawn'], settings['warmupRuns'], settings['runsPerProcess']),
                    run('dawn', 'aa-second', index, caches['dawn'], settings['warmupRuns'], settings['runsPerProcess'])]
            aa.append(statistics.median(pair[0]['runWallNs']) / statistics.median(pair[1]['runWallNs']))
        aa_ratio = statistics.median(aa)
        summary['aaMedianRatio'] = max(aa_ratio, 1 / aa_ratio)
        if summary['aaMedianRatio'] > settings['maximumAaMedianRatio']:
            summary['disposition'] = 'stopped-aa-control'; return 1
        cold = []
        for index in range(settings['coldProcessesPerArm']):
            for arm in (['dawn','doe'] if index % 2 == 0 else ['doe','dawn']):
                cache = args.out / f'{arm}-cold-cache-{index}'; cache.mkdir()
                cold.append(run(arm, 'cold', index, cache, 0, 1))
        pairs = []
        for index in range(settings['processPairs']):
            pair = {}
            for arm in (['dawn','doe'] if index % 2 == 0 else ['doe','dawn']):
                pair[arm] = run(arm, 'warm', index, caches[arm], settings['warmupRuns'], settings['runsPerProcess'])
            pairs.append(pair)
        ratios = np.array([statistics.median(p['dawn']['runWallNs']) / statistics.median(p['doe']['runWallNs']) for p in pairs])
        summary['primaryRatio'] = float(np.median(ratios))
        random = np.random.default_rng(settings['bootstrapSeed'])
        estimates = np.median(random.choice(ratios, (settings['bootstrapResamples'], len(ratios))), axis=1)
        summary['lowerConfidenceRatio'] = float(np.quantile(estimates, (1 - settings['confidence']) / 2))
        def arm_median(arm, field, population, inner=lambda x:x):
            return statistics.median(inner(r[field]) for r in population if r['arm']==arm)
        warm = [p[arm] for p in pairs for arm in qualified]
        checks = {
            'warmP95': (warm, 'runWallNs', lambda x:float(np.quantile(x, 0.95))),
            'coldProcessWall': (cold, 'processWallNs', lambda x:x),
            'processCpu': (warm, 'runCpuNs', statistics.median),
            'peakRss': (warm, 'peakRssBytes', lambda x:x)}
        for name,(population,field,inner) in checks.items():
            baseline = arm_median('dawn',field,population,inner)
            if baseline <= 0: raise ValueError('Missing regression control: ' + name)
            summary['regressionRatios'][name] = arm_median('doe',field,population,inner)/baseline
        summary['passed'] = summary['primaryRatio'] >= settings['materialGainRatio'] and summary['lowerConfidenceRatio'] >= settings['minimumLowerConfidenceRatio'] and all(
            value <= settings['regressionMaximumRatios'][name] for name,value in summary['regressionRatios'].items())
        summary['disposition'] = 'material-advantage-qualified' if summary['passed'] else 'no-material-advantage'
    except Exception as error:
        summary['disposition'] = 'stopped-measurement-failure'
        summary['failure'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        (args.out/'measurement.json').write_text(json.dumps(summary,indent=2)+'\n')
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

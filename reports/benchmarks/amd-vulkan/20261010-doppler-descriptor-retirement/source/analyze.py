"""Process-paired controls and full application timing from frozen receipts."""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import numpy as np


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--cohort', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text())
    analysis = json.loads((Path(__file__).parent / 'analysis.json').read_text())
    rng = np.random.default_rng(analysis['seed'])
    results = {}
    for lane in ['dawn', 'doe']:
        sessions = [json.loads((args.root / f'{args.cohort}-{lane}-{index}.json').read_text())
                    for index in range(contract['performance']['processes'])]
        if not all(session['passed'] for session in sessions):
            raise ValueError('Failed correctness receipt in cohort')
        controls = {}
        for field in ['firstTokenMs', 'completeMs']:
            logs = []
            for session in sessions:
                pair = {row['label']: row[field] for row in session['rows'] if row.get('label') in ['A', 'B']}
                logs.append(math.log(pair['B'] / pair['A']))
            draws = rng.choice(logs, (analysis['bootstrapSamples'], len(logs)), replace=True)
            ratio = float(np.exp(np.mean(logs)))
            margin = (1 - analysis['confidence']) / 2
            lower, upper = np.quantile(np.exp(np.mean(draws, axis=1)), [margin, 1-margin])
            bound = contract['performance']['maximumControlRatio']
            controls[field] = {'ratio': ratio, 'lower': float(lower), 'upper': float(upper),
                'stable': bool(lower >= 1/bound and upper <= bound), 'pairedLogRatios': logs}
        groups = {}
        for scope in ['initial', 'resident']:
            rows = [row for session in sessions for row in session['rows']
                    if row.get('label') == 'initial' or scope == 'resident' and row.get('label') in ['A','B']]
            if scope == 'resident':
                rows = [row for row in rows if row['label'] in ['A','B']]
            groups[scope] = {field: {'p50': float(np.median([row[field] for row in rows])),
                'p95': float(np.quantile([row[field] for row in rows], .95))}
                for field in ['firstTokenMs','completeMs']}
        results[lane] = {'controls': controls, 'timingsMs': groups,
            'loadMs': [session['loadMs'] for session in sessions],
            'peakProcessRssBytes': [session['peakProcessRssBytes'] for session in sessions]}
    args.out.write_text(json.dumps({'schemaVersion':1,'classification':'diagnostic',
        'cohort':args.cohort,'providers':results,'performancePromoted':False},indent=2)+'\n')
    for lane, result in results.items(): print(lane, json.dumps(result['controls']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Apply the frozen admission limits to independent application cohorts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--candidate-policy', type=Path)
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text())
    candidate = json.loads(args.candidate.read_text())
    contract = json.loads(args.contract.read_text())
    policy = json.loads(args.candidate_policy.read_text()) if args.candidate_policy else None
    if policy and (policy['candidateId'] != 'batched-buffer-descriptor-retirement-v1'
                   or policy['primaryMetric'] != 'resident completeMs p50'):
        raise ValueError('Unsupported candidate policy')
    primary_metric = 'completeMs' if policy else 'firstTokenMs'
    limits = {**contract['performance'], **(policy or {})}
    checks = []
    ratios = []
    for lane in ['doe', 'dawn']:
        before = baseline['providers'][lane]
        after = candidate['providers'][lane]
        for cohort, result in [('baseline', before), ('candidate', after)]:
            for metric in (['firstTokenMs', 'completeMs'] if policy else ['firstTokenMs']):
                checks.append({'id': f'{cohort}_{lane}_{metric}_control' if policy else f'{cohort}_{lane}_first_token_control',
                               'passed': result['controls'][metric]['stable']})
        for scope in ['initial', 'resident']:
            for metric in ['firstTokenMs', 'completeMs']:
                old = before['timingsMs'][scope][metric]
                new = after['timingsMs'][scope][metric]
                ratio = {'lane': lane, 'scope': scope, 'metric': metric,
                         'p50CandidateOverBaseline': new['p50'] / old['p50'],
                         'p95CandidateOverBaseline': new['p95'] / old['p95']}
                ratios.append(ratio)
                if lane == 'doe':
                    checks.append({'id': f'{scope}_{metric}_tail',
                                   'passed': ratio['p95CandidateOverBaseline'] <= limits['maximumTailRegressionRatio']})
                elif (policy or metric == 'firstTokenMs') and scope == 'resident':
                    bound = limits['maximumControlRatio']
                    checks.append({'id': f'unchanged_dawn_resident_{metric}_drift' if policy else 'unchanged_dawn_resident_first_token_drift',
                                   'passed': 1 / bound <= ratio['p50CandidateOverBaseline'] <= bound})
        memory_ratio = float(np.quantile(after['peakProcessRssBytes'], .95)
                             / np.quantile(before['peakProcessRssBytes'], .95))
        checks.append({'id': f'{lane}_host_peak_rss',
                       'passed': memory_ratio <= limits['maximumMemoryRegressionRatio']})
        ratios.append({'lane': lane, 'scope': 'process', 'metric': 'peakProcessRssBytes',
                       'p95CandidateOverBaseline': memory_ratio})
    primary = next(row for row in ratios if row['lane'] == 'doe'
                   and row['scope'] == 'resident' and row['metric'] == primary_metric)
    gain = 1 / primary['p50CandidateOverBaseline']
    checks.append({'id': f'material_resident_{primary_metric}_gain' if policy else 'material_resident_first_token_gain',
                   'passed': gain >= (policy['minimumBaselineGainRatio'] if policy else limits['minimumLatencyGainRatio'])})
    admitted = all(check['passed'] for check in checks)
    output = {
        'schemaVersion': 1, 'classification': 'diagnostic',
        'candidateId': policy['candidateId'] if policy else 'completed-small-buffer-reuse-v1',
        'contractSha256': hashlib.sha256(args.contract.read_bytes()).hexdigest(),
        'baselineSummarySha256': hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
        'candidateSummarySha256': hashlib.sha256(args.candidate.read_bytes()).hexdigest(),
        'primaryGainRatio': gain, 'ratios': ratios, 'checks': checks,
        'timingAdmissionPassed': admitted, 'performancePromoted': False,
        'disposition': 'eligible-for-regression-gates' if admitted else 'rejected',
        'completeLatencyClaimAllowed': all(
            result['controls']['completeMs']['stable']
            for summary in [baseline, candidate]
            for result in summary['providers'].values()),
        'scope': 'Independent sequential cohorts with balanced provider order; no candidate/baseline process pairing. API observer disabled. Failed controls and regressions are retained; no complete-latency gain is attributed.'}
    if policy:
        output['candidatePolicySha256'] = hashlib.sha256(args.candidate_policy.read_bytes()).hexdigest()
        output['scope'] = ('Unchanged-application replacement; incremental complete-generation admission against repaired Doe. '
                           'Dawn remains an unchanged drift control. No incumbent advantage or transfer claim; '
                           'no outcome-selected retry. Cleanup warning and process CPU consumption remain separately unqualified.')
    args.out.write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps({'disposition': output['disposition'], 'primaryGainRatio': gain,
                      'failedChecks': [row['id'] for row in checks if not row['passed']]}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

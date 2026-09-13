"""Order-stratified uncertainty for paired, fresh application processes."""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any

from bench.native_compare_modules.reporting import format_stats
from bench.runners.run_compute_program_tail_experiment import PHASES

PROCESS_LATENCY = ('deviceStartupMs', 'preparationMs', 'teardownMs', 'coldWallMs')
PROCESS_COST = ('peakProcessRssBytes', 'allocatedBufferBytes', 'coldCpuMs')
WARM_METRICS = ('wallMs', 'cpuMs', *PHASES)
QUANTILES = ('p50Ms', 'p95Ms', 'p99Ms')
ORDERS = ('baseline', 'candidate')


@dataclass(frozen=True)
class ProcessPair:
    application: str
    cohort: int
    index: int
    first: str
    baseline: dict[str, Any]
    candidate: dict[str, Any]
    execution_ids: tuple[str, str] | None = None


def median_interval(values: list[float], alpha: float) -> dict[str, Any]:
    """Invert the exact binomial sign test without interpolation or resampling.

    Coverage assumes independent pairs with a common median within an order
    stratum. Closed endpoints make ties conservative. Insufficient process
    samples yield unavailable bounds, even for identical observations.
    """
    if not values or not 0 < alpha < 1:
        raise ValueError('Require nonempty observations and alpha between zero and one')
    if any(not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError('Process ratios must be finite and positive')
    ordered = sorted(values)
    count = len(ordered)
    rank, tail = 0, 0
    for k in range(1, count // 2 + 1):
        tail += math.comb(count, k - 1)
        if 2 * tail / 2 ** count > alpha:
            break
        rank = k
    return {'pairs': count, 'medianRatio': statistics.median(ordered),
            'lowerRatio': ordered[rank - 1] if rank else None,
            'upperRatio': ordered[count - rank] if rank else None,
            'endpointRank': rank or None}


def process_metrics(report: dict[str, Any]) -> dict[tuple[str, str], float]:
    """Summarize a process once; its invocations are never independent pairs."""
    result = {(metric, 'process'): report[metric]
              for metric in (*PROCESS_LATENCY, *PROCESS_COST)
              if not metric.startswith('cold')}
    result.update({('coldWallMs', 'process'): report['cold']['wallMs'],
                   ('coldCpuMs', 'process'): report['cold']['cpuMs']})
    for metric in WARM_METRICS:
        values = [s['receipt']['timingMs'][metric] if metric in PHASES
                  else s[metric] for s in report['samples']]
        summary = format_stats(values, percentile_method='nearest-rank')
        result.update({(metric, quantile): summary[quantile]
                       for quantile in QUANTILES})
    if any(not math.isfinite(v) or v <= 0 for v in result.values()):
        raise ValueError('Required process measurements must be finite and positive')
    return result


def assess_uncertainty(
    pairs: list[ProcessPair], tail: dict[str, Any], decision: dict[str, Any],
) -> dict[str, Any]:
    """Correct the whole family, including applications, metrics, and orders.

    Per-process tail ratios estimate a typical process's tail, not the pooled
    invocation tail or population startup p99. Existing raw guards remain
    separate requirements. Bonferroni does not assume independent endpoints.
    """
    applications = [tail['developmentApplication'], *tail['transferApplications']]
    identities = {(p.application, p.cohort, p.index) for p in pairs}
    if len(identities) != len(pairs):
        raise ValueError('Duplicate process pair identity')
    expected = {(app, cohort, index) for app in applications
                for cohort in range(decision['cohorts'])
                for index in range(tail['expandedProcessPairs'])}
    if identities != expected:
        raise ValueError('Uncertainty requires every declared application process pair')
    if any(p.execution_ids is not None for p in pairs):
        executions = [identity for p in pairs for identity in (p.execution_ids or ())]
        if len(executions) != len(pairs) * 2 or len(set(executions)) != len(executions):
            raise ValueError('Uncertainty requires distinct physical process executions')
    groups: dict[tuple[str, str, str, str], list[float]] = {}
    for pair in pairs:
        if pair.first != ORDERS[(pair.cohort + pair.index) % len(ORDERS)]:
            raise ValueError('Process order differs from the declared alternating schedule')
        before, after = process_metrics(pair.baseline), process_metrics(pair.candidate)
        for (metric, summary), baseline in before.items():
            key = (pair.application, metric, summary, pair.first)
            groups.setdefault(key, []).append(after[(metric, summary)] / baseline)
    family_size = len(groups)
    alpha = decision['familywiseErrorRate'] / family_size
    rows = []
    for (app, metric, summary, first), values in sorted(groups.items()):
        bounds = median_interval(values, alpha)
        low, high = bounds['lowerRatio'], bounds['upperRatio']
        finite = low is not None and high is not None
        limit = tail['maximumCostRegression'] if metric in (*PROCESS_COST, 'cpuMs') \
            else tail['maximumLatencyRegression']
        rows.append({'application': app, 'metric': metric, 'summary': summary,
                     'firstVariant': first, **bounds,
                     'maximumRegression': limit,
                     'nullConsistent': finite and low <= 1 <= high,
                     'regressionBandResolved': finite and
                     low >= 1 / (1 + limit) and high <= 1 + limit})
    return {'schemaVersion': 1, 'kind': 'compute-program-uncertainty',
            'method': decision['method'], 'familywiseErrorRate': decision['familywiseErrorRate'],
            'familySize': family_size, 'intervalErrorRate': alpha,
            'allIntervalsFinite': all(r['endpointRank'] is not None for r in rows),
            'nullConsistent': all(r['nullConsistent'] for r in rows),
            'regressionBandsResolved': all(r['regressionBandResolved'] for r in rows),
            'rows': rows}


def candidate_verdict(
    uncertainty: dict[str, Any], raw_acceptance: list[dict[str, Any]],
    tail: dict[str, Any], *, calibration_resolved: bool,
) -> dict[str, Any]:
    """Separate demonstrated harm, unresolved effects, and eligible confirmation."""
    rows = uncertainty['rows']
    regressions = [r for r in rows if r['lowerRatio'] is not None
                   and r['lowerRatio'] > 1 + r['maximumRegression']]
    primary = [r for r in rows if r['metric'] == 'wallMs' and r['summary'] == 'p50Ms']
    development = [r for r in primary if r['application'] == tail['developmentApplication']]
    required = tail['minimumWallMedianReduction']
    improvement_ruled_out = len(development) == len(ORDERS) and all(
        r['lowerRatio'] is not None and r['lowerRatio'] > 1 - required
        for r in development)
    improvement_confirmed = len(primary) == len(ORDERS) * (
        1 + len(tail['transferApplications'])) and all(
        r['upperRatio'] is not None and r['upperRatio'] < 1 - (
            required if r['application'] == tail['developmentApplication'] else 0)
        for r in primary)
    guards_confirmed = uncertainty['allIntervalsFinite'] and all(
        r['upperRatio'] <= 1 + r['maximumRegression'] for r in rows)
    raw_passed = bool(raw_acceptance) and all(r['acceptancePassed'] for r in raw_acceptance)
    if regressions or improvement_ruled_out:
        verdict = 'reject'
    elif calibration_resolved and improvement_confirmed and guards_confirmed and raw_passed:
        verdict = 'confirm'
    else:
        verdict = 'inconclusive'
    return {'verdict': verdict, 'confirmedRegressionEndpoints': len(regressions),
            'requiredImprovementRuledOut': improvement_ruled_out,
            'improvementConfirmed': improvement_confirmed,
            'regressionsExcluded': guards_confirmed, 'rawAcceptancePassed': raw_passed,
            'calibrationResolutionPassed': calibration_resolved}

#!/usr/bin/env node

import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { basename, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

import {
  applyDebugStepLimit,
} from '../executors/node-webgpu/executor.js';
import {
  normalizePlan,
} from '../executors/node-webgpu/plan.js';

const REPO_ROOT = resolve(fileURLToPath(new URL('../..', import.meta.url)));
const NODE_RUNNER = 'bench/executors/run-node-webgpu-plan.js';
const BUN_RUNNER = 'bench/executors/run-bun-webgpu-plan.js';

function stableArtifactHash(payload) {
  return createHash('sha256').update(JSON.stringify(payload), 'utf8').digest('hex');
}

function repoRelative(path) {
  const normalized = resolve(path);
  return normalized.startsWith(`${REPO_ROOT}/`)
    ? normalized.slice(REPO_ROOT.length + 1)
    : normalized;
}

function usage() {
  return [
    'usage: node bench/tools/package_dispatch_prefix_profile.mjs',
    '  --plan <path> --workload <id> --provider <doe|node-webgpu|bun-webgpu>',
    '  --runtime-host <node|bun> --out <path> --trace-dir <dir>',
    '  [--sample-count <n>] [--command-repeat <n>] [--prepared-session]',
    '  [--resident-buffer-loads] [--executor-dry-run] [--include-full-plan]',
    '  [--full-plan-command-repeat <n>] [--max-dispatches <n>]',
  ].join(' ');
}

function parsePositiveInt(value, fieldName, defaultValue) {
  const text = typeof value === 'string' ? value.trim() : '';
  if (!text) {
    return defaultValue;
  }
  const parsed = Number(text);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error(`expected a positive integer for ${fieldName}, got: ${value}`);
  }
  return parsed;
}

function parseNonNegativeInt(value, fieldName, defaultValue) {
  const text = typeof value === 'string' ? value.trim() : '';
  if (!text) {
    return defaultValue;
  }
  const parsed = Number(text);
  if (!Number.isInteger(parsed) || parsed < 0) {
    throw new Error(`expected a non-negative integer for ${fieldName}, got: ${value}`);
  }
  return parsed;
}

function median(values) {
  if (values.length === 0) {
    return 0;
  }
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) {
    return sorted[middle];
  }
  return Math.round((sorted[middle - 1] + sorted[middle]) / 2);
}

function percentile(values, fraction) {
  if (values.length === 0) {
    return 0;
  }
  const sorted = [...values].sort((left, right) => left - right);
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil(sorted.length * fraction) - 1));
  return sorted[index];
}

function ratioPermille(numerator, denominator) {
  if (!Number.isFinite(numerator) || !Number.isFinite(denominator) || denominator <= 0) {
    return 0;
  }
  return Math.max(0, Math.round((numerator / denominator) * 1000));
}

function summarizeNs(values) {
  if (values.length === 0) {
    return {
      count: 0,
      min: 0,
      median: 0,
      p95: 0,
      max: 0,
      mean: 0,
      range: 0,
      p95ToMedianPermille: 0,
      maxToMedianPermille: 0,
    };
  }
  const total = values.reduce((sum, value) => sum + value, 0);
  const minValue = Math.min(...values);
  const medianValue = median(values);
  const p95Value = percentile(values, 0.95);
  const maxValue = Math.max(...values);
  return {
    count: values.length,
    min: minValue,
    median: medianValue,
    p95: p95Value,
    max: maxValue,
    mean: Math.round(total / values.length),
    range: maxValue - minValue,
    p95ToMedianPermille: ratioPermille(p95Value, medianValue),
    maxToMedianPermille: ratioPermille(maxValue, medianValue),
  };
}

function pickStepMetadata(step, dispatchOrdinal, stepIndex) {
  return {
    dispatchOrdinal,
    stepIndex,
    stepId: typeof step.id === 'string' ? step.id : `step-${stepIndex}`,
    moduleId: typeof step.moduleId === 'string' ? step.moduleId : '',
    entryPoint: typeof step.entryPoint === 'string' ? step.entryPoint : 'main',
    workgroups: Array.isArray(step.workgroups) ? step.workgroups : [1, 1, 1],
    ...(typeof step.semanticOpId === 'string' ? { semanticOpId: step.semanticOpId } : {}),
    ...(typeof step.semanticStage === 'string' ? { semanticStage: step.semanticStage } : {}),
    ...(typeof step.semanticPhase === 'string' ? { semanticPhase: step.semanticPhase } : {}),
    ...(Number.isInteger(step.semanticTokenIndex) ? { semanticTokenIndex: step.semanticTokenIndex } : {}),
    ...(Number.isInteger(step.semanticLayerIndex) ? { semanticLayerIndex: step.semanticLayerIndex } : {}),
  };
}

function collectDispatchPrefixes(normalizedPlan, maxDispatches) {
  const prefixes = [];
  let dispatchOrdinal = 0;
  for (const [stepIndex, step] of normalizedPlan.steps.entries()) {
    if (step.kind !== 'dispatch') {
      continue;
    }
    dispatchOrdinal += 1;
    if (maxDispatches > 0 && dispatchOrdinal > maxDispatches) {
      break;
    }
    prefixes.push({
      ...pickStepMetadata(step, dispatchOrdinal, stepIndex),
      stepLimit: stepIndex + 1,
    });
  }
  return prefixes;
}

function runnerForRuntimeHost(runtimeHost) {
  if (runtimeHost === 'node') {
    return { command: process.execPath, script: NODE_RUNNER };
  }
  if (runtimeHost === 'bun') {
    return { command: 'bun', script: BUN_RUNNER };
  }
  throw new Error(`unsupported runtime host: ${runtimeHost}`);
}

function metricFromMeta(meta, key) {
  const value = Number(meta?.[key] ?? 0);
  return Number.isFinite(value) && value > 0 ? Math.round(value) : 0;
}

const PHASE_BREAKDOWN_KEYS = [
  'writeMaterializeTotalNs',
  'writeQueueWriteTotalNs',
  'dispatchEncodeApiTotalNs',
  'copyEncodeApiTotalNs',
  'submitCommandEncoderFinishTotalNs',
  'submitQueueSubmitTotalNs',
  'submitQueueWaitTotalNs',
  'submitCommandPrepTotalNs',
  'submitAddonCallTotalNs',
  'submitAddonCommandReplayTotalNs',
  'submitAddonCommandReplayPrepareTotalNs',
  'submitAddonCommandReplayRecordTotalNs',
  'submitAddonCommandReplayCopyTotalNs',
  'submitAddonQueueSubmitTotalNs',
  'submitAddonCommandBufferEndTotalNs',
  'submitAddonSyncPrepareTotalNs',
  'submitAddonDriverSubmitTotalNs',
  'submitAddonFlushTotalNs',
  'submitPostSubmitBookkeepingTotalNs',
  'submitQueueFlushTotalNs',
  'submitQueueFlushWaitCompletedTotalNs',
  'submitQueueFlushDeferredCopyTotalNs',
  'submitQueueFlushDeferredResolveTotalNs',
  'submitQueueWaitBookkeepingTotalNs',
  'readbackTotalNs',
  'readbackMapReadCopyUnmapTotalNs',
  'readbackMapReadCopyUnmapQueueWaitCompletedTotalNs',
  'readbackMapReadCopyUnmapDeferredCopyTotalNs',
  'readbackMapReadCopyUnmapDeferredResolveTotalNs',
  'readbackMapReadCopyUnmapMapTotalNs',
  'readbackMapReadCopyUnmapCopyTotalNs',
  'readbackMapReadCopyUnmapUnmapTotalNs',
  'readbackMapAsyncTotalNs',
  'readbackGetMappedRangeTotalNs',
  'readbackHostCopyTotalNs',
  'readbackNativeReadCopyTotalNs',
  'readbackUnmapTotalNs',
  'readbackValidationTotalNs',
  'readbackCaptureTotalNs',
];

const ADJACENT_RANKING_METRICS = [
  'executionTotalNs',
  'executionSubmitWaitTotalNs',
  'submitQueueWaitTotalNs',
  'readbackTotalNs',
  'hostCommandOrchestrationTotalNs',
];

const ADJACENT_RANKING_LIMIT = 8;
const STABILITY_DIAGNOSTIC_METRICS = [
  'executionTotalNs',
  'executionSubmitWaitTotalNs',
  'readbackTotalNs',
  'hostCommandOrchestrationTotalNs',
];
const STABILITY_MIN_SAMPLE_COUNT = 3;
const STABILITY_P95_TO_MEDIAN_PERMILLE_THRESHOLD = 1500;
const STABILITY_MAX_TO_MEDIAN_PERMILLE_THRESHOLD = 1500;

function phaseBreakdownFromMeta(meta) {
  const stepBreakdown = meta?.packageStepBreakdownNs && typeof meta.packageStepBreakdownNs === 'object'
    ? meta.packageStepBreakdownNs
    : {};
  const breakdown = {};
  for (const key of PHASE_BREAKDOWN_KEYS) {
    breakdown[key] = metricFromMeta(stepBreakdown, key);
  }
  return breakdown;
}

function packageFastPathStatsFromMeta(meta) {
  const stats = meta?.packageFastPathStats;
  if (!stats || typeof stats !== 'object') {
    return null;
  }
  return {
    dispatchFlush: Math.max(0, Math.round(Number(stats.dispatchFlush ?? 0) || 0)),
    flushAndMap: Math.max(0, Math.round(Number(stats.flushAndMap ?? 0) || 0)),
    commandBufferBuild: Math.max(0, Math.round(Number(stats.commandBufferBuild ?? 0) || 0)),
  };
}

function packageNativeFastPathsFromMeta(meta) {
  const info = meta?.packageNativeFastPaths;
  if (!info || typeof info !== 'object') {
    return null;
  }
  return {
    appleFastPathCompiled: Boolean(info.appleFastPathCompiled),
    queueFlush: Boolean(info.queueFlush),
    queueFlushBreakdown: Boolean(info.queueFlushBreakdown),
    queueWriteBufferBatch: Boolean(info.queueWriteBufferBatch),
    queueWriteBufferBatchDataPtrs: Boolean(info.queueWriteBufferBatchDataPtrs),
    computeDispatchFlush: Boolean(info.computeDispatchFlush),
    computeDispatchFlushBreakdown: Boolean(info.computeDispatchFlushBreakdown),
    computeDispatchBatchFlush: Boolean(info.computeDispatchBatchFlush),
    computeDispatchBatchCopyFlush: Boolean(info.computeDispatchBatchCopyFlush),
    computeDispatchBatchCopyFlushBreakdown: Boolean(info.computeDispatchBatchCopyFlushBreakdown),
    bufferMapReadCopyUnmap: Boolean(info.bufferMapReadCopyUnmap),
  };
}

function summarizePhaseBreakdowns(samples) {
  const summary = {};
  for (const key of PHASE_BREAKDOWN_KEYS) {
    summary[key] = summarizeNs(samples.map((sample) => sample.phaseBreakdownNs[key]));
  }
  return summary;
}

function sampleFromMeta(meta, traceMetaPath, traceJsonlPath, sampleIndex) {
  const phaseBreakdownNs = phaseBreakdownFromMeta(meta);
  const readbackCaptures = Array.isArray(meta?.readbackCaptures) ? meta.readbackCaptures : [];
  const packageFastPathStats = packageFastPathStatsFromMeta(meta);
  const packageNativeFastPaths = packageNativeFastPathsFromMeta(meta);
  const packageReadbackMode = typeof meta?.packageReadbackMode === 'string'
    ? meta.packageReadbackMode
    : '';
  return {
    sampleIndex,
    traceMetaPath,
    traceJsonlPath,
    executionTotalNs: metricFromMeta(meta, 'executionTotalNs'),
    executionSetupTotalNs: metricFromMeta(meta, 'executionSetupTotalNs'),
    executionEncodeTotalNs: metricFromMeta(meta, 'executionEncodeTotalNs'),
    executionSubmitWaitTotalNs: metricFromMeta(meta, 'executionSubmitWaitTotalNs'),
    hostCommandOrchestrationTotalNs: metricFromMeta(meta, 'hostCommandOrchestrationTotalNs'),
    executionDispatchCount: metricFromMeta(meta, 'executionDispatchCount'),
    submitQueueWaitTotalNs: phaseBreakdownNs.submitQueueWaitTotalNs,
    readbackTotalNs: phaseBreakdownNs.readbackTotalNs,
    readbackQueueWaitNs: phaseBreakdownNs.readbackMapReadCopyUnmapQueueWaitCompletedTotalNs,
    ...(packageReadbackMode ? { packageReadbackMode } : {}),
    ...(packageNativeFastPaths ? { packageNativeFastPaths } : {}),
    phaseBreakdownNs,
    ...(packageFastPathStats ? { packageFastPathStats } : {}),
    readbackCaptureCount: readbackCaptures.length,
    ...(readbackCaptures.length > 0 ? { lastReadbackCapture: readbackCaptures.at(-1) } : {}),
  };
}

function spawnRunner({
  runtimeHost,
  provider,
  planPath,
  workloadId,
  traceMetaPath,
  traceJsonlPath,
  stepLimit,
  commandRepeat,
  preparedSession,
  residentBufferLoads,
  executorDryRun,
}) {
  const runner = runnerForRuntimeHost(runtimeHost);
  const args = [
    runner.script,
    '--provider', provider,
    '--plan', planPath,
    '--trace-meta', traceMetaPath,
    '--trace-jsonl', traceJsonlPath,
    '--workload', workloadId,
    '--command-repeat', String(commandRepeat),
  ];
  if (preparedSession) {
    args.push('--prepared-session');
  }
  if (residentBufferLoads) {
    args.push('--resident-buffer-loads');
  }
  if (executorDryRun) {
    args.push('--dry-run');
  }
  if (Number.isInteger(stepLimit) && stepLimit > 0) {
    args.push('--step-limit', String(stepLimit));
  }
  return new Promise((resolvePromise, reject) => {
    const child = spawn(runner.command, args, {
      cwd: REPO_ROOT,
      env: process.env,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString();
    });
    child.on('error', reject);
    child.on('close', (code, signal) => {
      if (code === 0) {
        if (stderr.trim()) {
          reject(new Error(`${runner.command} ${args.join(' ')} wrote stderr during a successful run\n${stderr}`));
          return;
        }
        resolvePromise({ stdout, stderr });
        return;
      }
      const suffix = signal ? ` signal=${signal}` : '';
      reject(new Error(`${runner.command} ${args.join(' ')} failed with code=${code ?? 'null'}${suffix}\n${stderr || stdout}`));
    });
  });
}

async function runPrefixSample({
  runtimeHost,
  provider,
  planPath,
  workloadId,
  traceDir,
  prefix,
  sampleIndex,
  commandRepeat,
  preparedSession,
  residentBufferLoads,
  executorDryRun,
}) {
  const prefixName = `dispatch-${String(prefix.dispatchOrdinal).padStart(3, '0')}`;
  const sampleName = `sample-${String(sampleIndex).padStart(3, '0')}`;
  const traceMetaPath = resolve(traceDir, `${prefixName}.${sampleName}.meta.json`);
  const traceJsonlPath = resolve(traceDir, `${prefixName}.${sampleName}.jsonl`);
  await spawnRunner({
    runtimeHost,
    provider,
    planPath,
    workloadId,
    traceMetaPath,
    traceJsonlPath,
    stepLimit: prefix.stepLimit,
    commandRepeat,
    preparedSession,
    residentBufferLoads,
    executorDryRun,
  });
  const meta = JSON.parse(await readFile(traceMetaPath, 'utf8'));
  return sampleFromMeta(
    meta,
    repoRelative(traceMetaPath),
    repoRelative(traceJsonlPath),
    sampleIndex,
  );
}

async function runFullPlanSample({
  runtimeHost,
  provider,
  planPath,
  workloadId,
  traceDir,
  sampleIndex,
  commandRepeat,
  preparedSession,
  residentBufferLoads,
  executorDryRun,
}) {
  const sampleName = `sample-${String(sampleIndex).padStart(3, '0')}`;
  const traceMetaPath = resolve(traceDir, `full-plan.${sampleName}.meta.json`);
  const traceJsonlPath = resolve(traceDir, `full-plan.${sampleName}.jsonl`);
  await spawnRunner({
    runtimeHost,
    provider,
    planPath,
    workloadId,
    traceMetaPath,
    traceJsonlPath,
    stepLimit: 0,
    commandRepeat,
    preparedSession,
    residentBufferLoads,
    executorDryRun,
  });
  const meta = JSON.parse(await readFile(traceMetaPath, 'utf8'));
  return sampleFromMeta(
    meta,
    repoRelative(traceMetaPath),
    repoRelative(traceJsonlPath),
    sampleIndex,
  );
}

function summarizePrefix(prefix, samples, previousSummary) {
  const executionTotal = summarizeNs(samples.map((sample) => sample.executionTotalNs));
  const executionSubmitWait = summarizeNs(samples.map((sample) => sample.executionSubmitWaitTotalNs));
  const submitQueueWait = summarizeNs(samples.map((sample) => sample.submitQueueWaitTotalNs));
  const readbackTotal = summarizeNs(samples.map((sample) => sample.readbackTotalNs));
  const hostCommandOrchestration = summarizeNs(samples.map((sample) => sample.hostCommandOrchestrationTotalNs));
  return {
    ...prefix,
    sampleCount: samples.length,
    executionTotalNs: executionTotal,
    executionSubmitWaitTotalNs: executionSubmitWait,
    submitQueueWaitTotalNs: submitQueueWait,
    readbackTotalNs: readbackTotal,
    hostCommandOrchestrationTotalNs: hostCommandOrchestration,
    phaseBreakdownNs: summarizePhaseBreakdowns(samples),
    deltaFromPreviousMedianExecutionTotalNs: previousSummary
      ? executionTotal.median - previousSummary.executionTotalNs.median
      : executionTotal.median,
    deltaFromPreviousMedianSubmitWaitNs: previousSummary
      ? executionSubmitWait.median - previousSummary.executionSubmitWaitTotalNs.median
      : executionSubmitWait.median,
    samples,
  };
}

function summarizeFullPlan(samples) {
  return {
    sampleCount: samples.length,
    executionTotalNs: summarizeNs(samples.map((sample) => sample.executionTotalNs)),
    executionSubmitWaitTotalNs: summarizeNs(samples.map((sample) => sample.executionSubmitWaitTotalNs)),
    submitQueueWaitTotalNs: summarizeNs(samples.map((sample) => sample.submitQueueWaitTotalNs)),
    readbackTotalNs: summarizeNs(samples.map((sample) => sample.readbackTotalNs)),
    hostCommandOrchestrationTotalNs: summarizeNs(samples.map((sample) => sample.hostCommandOrchestrationTotalNs)),
    phaseBreakdownNs: summarizePhaseBreakdowns(samples),
    samples,
  };
}

function pickDispatchIdentity(dispatch) {
  return {
    dispatchOrdinal: dispatch.dispatchOrdinal,
    stepIndex: dispatch.stepIndex,
    stepId: dispatch.stepId,
    moduleId: dispatch.moduleId,
    entryPoint: dispatch.entryPoint,
    ...(typeof dispatch.semanticOpId === 'string' ? { semanticOpId: dispatch.semanticOpId } : {}),
    ...(typeof dispatch.semanticStage === 'string' ? { semanticStage: dispatch.semanticStage } : {}),
    ...(typeof dispatch.semanticPhase === 'string' ? { semanticPhase: dispatch.semanticPhase } : {}),
    ...(Number.isInteger(dispatch.semanticTokenIndex) ? { semanticTokenIndex: dispatch.semanticTokenIndex } : {}),
    ...(Number.isInteger(dispatch.semanticLayerIndex) ? { semanticLayerIndex: dispatch.semanticLayerIndex } : {}),
  };
}

function rankedAdjacentDeltas(dispatches, metricName, limit = ADJACENT_RANKING_LIMIT) {
  const records = dispatches.map((dispatch, index) => {
    const previous = index > 0 ? dispatches[index - 1] : null;
    const currentMedianNs = Number(dispatch?.[metricName]?.median ?? 0);
    const previousMedianNs = previous ? Number(previous?.[metricName]?.median ?? 0) : 0;
    return {
      ...pickDispatchIdentity(dispatch),
      metric: metricName,
      previousDispatchOrdinal: previous?.dispatchOrdinal ?? null,
      previousStepId: previous?.stepId ?? null,
      currentMedianNs,
      previousMedianNs,
      deltaNs: currentMedianNs - previousMedianNs,
      positiveMeansCurrentPrefixAddedCost: true,
    };
  });
  return records
    .sort((left, right) => {
      if (right.deltaNs !== left.deltaNs) {
        return right.deltaNs - left.deltaNs;
      }
      return left.dispatchOrdinal - right.dispatchOrdinal;
    })
    .slice(0, Math.max(0, Math.min(limit, records.length)));
}

function buildAdjacentDeltaRankings(dispatches) {
  const rankings = {};
  for (const metricName of ADJACENT_RANKING_METRICS) {
    rankings[metricName] = rankedAdjacentDeltas(dispatches, metricName);
  }
  return rankings;
}

function buildFullPlanResidual(fullPlan, dispatches) {
  if (!fullPlan || dispatches.length === 0) {
    return null;
  }
  const lastPrefix = dispatches.at(-1);
  const metrics = {};
  for (const metricName of ADJACENT_RANKING_METRICS) {
    const fullPlanMedianNs = Number(fullPlan?.[metricName]?.median ?? 0);
    const lastPrefixMedianNs = Number(lastPrefix?.[metricName]?.median ?? 0);
    metrics[metricName] = {
      fullPlanMedianNs,
      lastPrefixMedianNs,
      residualNs: fullPlanMedianNs - lastPrefixMedianNs,
      positiveMeansFullPlanHasExtraCost: true,
    };
  }
  return {
    basis: 'full-plan-median-minus-last-dispatch-prefix-median',
    lastDispatchOrdinal: lastPrefix.dispatchOrdinal,
    lastStepId: lastPrefix.stepId,
    metrics,
  };
}

function buildFullPlanPhaseResidualRanking(fullPlan, dispatches, limit = ADJACENT_RANKING_LIMIT) {
  if (!fullPlan || dispatches.length === 0) {
    return null;
  }
  const lastPrefix = dispatches.at(-1);
  const records = PHASE_BREAKDOWN_KEYS.map((phase) => {
    const fullPlanMedianNs = Number(fullPlan?.phaseBreakdownNs?.[phase]?.median ?? 0);
    const lastPrefixMedianNs = Number(lastPrefix?.phaseBreakdownNs?.[phase]?.median ?? 0);
    return {
      phase,
      fullPlanMedianNs,
      lastPrefixMedianNs,
      residualNs: fullPlanMedianNs - lastPrefixMedianNs,
      positiveMeansFullPlanHasExtraCost: true,
    };
  });
  return {
    basis: 'full-plan-phase-median-minus-last-dispatch-prefix-phase-median',
    lastDispatchOrdinal: lastPrefix.dispatchOrdinal,
    lastStepId: lastPrefix.stepId,
    phases: records
      .sort((left, right) => {
        if (right.residualNs !== left.residualNs) {
          return right.residualNs - left.residualNs;
        }
        return left.phase.localeCompare(right.phase);
      })
      .slice(0, Math.max(0, Math.min(limit, records.length))),
  };
}

function stabilityStatusForSummary(summary) {
  const sampleCount = Number(summary?.count ?? 0);
  if (sampleCount < STABILITY_MIN_SAMPLE_COUNT) {
    return 'insufficient-samples';
  }
  const p95ToMedianPermille = Number(summary?.p95ToMedianPermille ?? 0);
  const maxToMedianPermille = Number(summary?.maxToMedianPermille ?? 0);
  return (
    p95ToMedianPermille > STABILITY_P95_TO_MEDIAN_PERMILLE_THRESHOLD
    || maxToMedianPermille > STABILITY_MAX_TO_MEDIAN_PERMILLE_THRESHOLD
  )
    ? 'unstable'
    : 'stable';
}

function stabilityRecordForSummary({
  scope,
  metric,
  summary,
  dispatchOrdinal = null,
  stepId = null,
}) {
  return {
    scope,
    metric,
    ...(dispatchOrdinal !== null ? { dispatchOrdinal } : {}),
    ...(stepId !== null ? { stepId } : {}),
    sampleCount: Number(summary?.count ?? 0),
    medianNs: Number(summary?.median ?? 0),
    p95ToMedianPermille: Number(summary?.p95ToMedianPermille ?? 0),
    maxToMedianPermille: Number(summary?.maxToMedianPermille ?? 0),
    status: stabilityStatusForSummary(summary),
  };
}

function buildStabilityDiagnostics({ dispatches, fullPlan }) {
  const records = [];
  if (fullPlan) {
    for (const metric of STABILITY_DIAGNOSTIC_METRICS) {
      records.push(stabilityRecordForSummary({
        scope: 'fullPlan',
        metric,
        summary: fullPlan[metric],
      }));
    }
  }
  for (const dispatch of dispatches) {
    for (const metric of STABILITY_DIAGNOSTIC_METRICS) {
      records.push(stabilityRecordForSummary({
        scope: 'dispatchPrefix',
        metric,
        summary: dispatch[metric],
        dispatchOrdinal: dispatch.dispatchOrdinal,
        stepId: dispatch.stepId,
      }));
    }
  }
  const unstableMetricCount = records.filter((record) => record.status === 'unstable').length;
  const insufficientSampleMetricCount = records.filter((record) => record.status === 'insufficient-samples').length;
  return {
    basis: 'summary-p95-and-max-to-median-permille',
    minSampleCount: STABILITY_MIN_SAMPLE_COUNT,
    p95ToMedianPermilleThreshold: STABILITY_P95_TO_MEDIAN_PERMILLE_THRESHOLD,
    maxToMedianPermilleThreshold: STABILITY_MAX_TO_MEDIAN_PERMILLE_THRESHOLD,
    overallStatus: insufficientSampleMetricCount > 0
      ? 'insufficient-samples'
      : unstableMetricCount > 0
        ? 'unstable'
        : 'stable',
    metricCount: records.length,
    unstableMetricCount,
    insufficientSampleMetricCount,
    records,
  };
}

async function main() {
  const { values: args } = parseArgs({
    options: {
      plan: { type: 'string', default: '' },
      workload: { type: 'string', default: '' },
      provider: { type: 'string', default: 'doe' },
      'runtime-host': { type: 'string', default: 'node' },
      out: { type: 'string', default: '' },
      'trace-dir': { type: 'string', default: '' },
      'sample-count': { type: 'string', default: '3' },
      'command-repeat': { type: 'string', default: '1' },
      'max-dispatches': { type: 'string', default: '0' },
      'full-plan-command-repeat': { type: 'string', default: '' },
      'prepared-session': { type: 'boolean', default: false },
      'resident-buffer-loads': { type: 'boolean', default: false },
      'executor-dry-run': { type: 'boolean', default: false },
      'include-full-plan': { type: 'boolean', default: false },
    },
  });

  if (!args.plan || !args.workload || !args.out || !args['trace-dir']) {
    throw new Error(usage());
  }
  const runtimeHost = args['runtime-host'];
  const sampleCount = parsePositiveInt(args['sample-count'], '--sample-count', 3);
  const commandRepeat = parsePositiveInt(args['command-repeat'], '--command-repeat', 1);
  const fullPlanCommandRepeat = parsePositiveInt(
    args['full-plan-command-repeat'],
    '--full-plan-command-repeat',
    commandRepeat,
  );
  const maxDispatches = parseNonNegativeInt(args['max-dispatches'], '--max-dispatches', 0);
  const planPath = resolve(args.plan);
  const traceDir = resolve(args['trace-dir']);
  const outPath = resolve(args.out);
  const planPayload = JSON.parse(await readFile(planPath, 'utf8'));
  const normalizedPlan = normalizePlan(planPayload);
  const prefixes = collectDispatchPrefixes(normalizedPlan, maxDispatches);
  if (prefixes.length === 0) {
    throw new Error(`plan has no dispatch steps: ${args.plan}`);
  }
  await mkdir(traceDir, { recursive: true });
  await mkdir(dirname(outPath), { recursive: true });

  const dispatches = [];
  let previousSummary = null;
  for (const prefix of prefixes) {
    const samples = [];
    for (let sampleIndex = 0; sampleIndex < sampleCount; sampleIndex += 1) {
      samples.push(await runPrefixSample({
        runtimeHost,
        provider: args.provider,
        planPath,
        workloadId: args.workload,
        traceDir,
        prefix,
        sampleIndex,
        commandRepeat,
        preparedSession: Boolean(args['prepared-session']),
        residentBufferLoads: Boolean(args['resident-buffer-loads']),
        executorDryRun: Boolean(args['executor-dry-run']),
      }));
    }
    const summary = summarizePrefix(prefix, samples, previousSummary);
    dispatches.push(summary);
    previousSummary = summary;
  }

  let fullPlan = null;
  if (Boolean(args['include-full-plan'])) {
    const fullPlanSamples = [];
    for (let sampleIndex = 0; sampleIndex < sampleCount; sampleIndex += 1) {
      fullPlanSamples.push(await runFullPlanSample({
        runtimeHost,
        provider: args.provider,
        planPath,
        workloadId: args.workload,
        traceDir,
        sampleIndex,
        commandRepeat: fullPlanCommandRepeat,
        preparedSession: Boolean(args['prepared-session']),
        residentBufferLoads: Boolean(args['resident-buffer-loads']),
        executorDryRun: Boolean(args['executor-dry-run']),
      }));
    }
    fullPlan = summarizeFullPlan(fullPlanSamples);
  }

  const payload = {
    schemaVersion: 1,
    kind: 'package_dispatch_prefix_profile',
    profileMode: 'dispatch-prefix-terminal-wait',
    deltaMethod: 'adjacent-prefix-subtraction-diagnostic',
    runtimeHost,
    provider: args.provider,
    workloadId: args.workload,
    planPath: repoRelative(planPath),
    planId: normalizedPlan.planId,
    planHash: normalizedPlan.planHash,
    commandRepeat,
    fullPlanCommandRepeat,
    sampleCount,
    preparedSession: Boolean(args['prepared-session']),
    residentBufferLoads: Boolean(args['resident-buffer-loads']),
    executorDryRun: Boolean(args['executor-dry-run']),
    includeFullPlan: Boolean(args['include-full-plan']),
    traceDir: repoRelative(traceDir),
    dispatchCount: dispatches.length,
    adjacentDeltaRankingLimit: ADJACENT_RANKING_LIMIT,
    adjacentDeltaRankings: buildAdjacentDeltaRankings(dispatches),
    stabilityDiagnostics: buildStabilityDiagnostics({ dispatches, fullPlan }),
    dispatches,
    ...(fullPlan ? { fullPlan } : {}),
  };
  const fullPlanResidual = buildFullPlanResidual(fullPlan, dispatches);
  if (fullPlanResidual) {
    payload.fullPlanResidualNs = fullPlanResidual;
  }
  const fullPlanPhaseResidual = buildFullPlanPhaseResidualRanking(fullPlan, dispatches);
  if (fullPlanPhaseResidual) {
    payload.fullPlanPhaseResidualRanking = fullPlanPhaseResidual;
  }
  payload.artifactHash = stableArtifactHash(payload);
  await writeFile(outPath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
  process.stderr.write(
    `wrote ${basename(outPath)} with ${dispatches.length} dispatch prefixes for ${args.provider}/${runtimeHost}\n`,
  );
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exit(1);
});

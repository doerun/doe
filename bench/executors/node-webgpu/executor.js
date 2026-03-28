import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { performance } from 'node:perf_hooks';
import { createHash } from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { join, resolve } from 'node:path';
import os from 'node:os';

import {
  materializeBufferData,
  normalizePlan,
  planSummary,
  validateSampleExpectation,
} from './plan.js';

const REPO_ROOT = resolve(fileURLToPath(new URL('../../..', import.meta.url)));
const FALLBACK_WEBGPU_PATH = join(
  REPO_ROOT,
  'bench/package-compare/node/node_modules/webgpu/index.js',
);
const DOE_PACKAGE_PATH = join(
  REPO_ROOT,
  'packages/doe-gpu/src/index.js',
);
const FALLBACK_BUN_WEBGPU_PATH = join(
  REPO_ROOT,
  'bench/package-compare/bun/node_modules/bun-webgpu/index.js',
);
const DOE_BUN_PACKAGE_PATH = join(
  REPO_ROOT,
  'packages/doe-gpu/src/bun.js',
);
const PACKAGE_EXECUTION_POLICY_PATH = join(
  REPO_ROOT,
  'config/package-execution-policy.json',
);

const PROVIDERS_BY_RUNTIME = Object.freeze({
  node: Object.freeze({
    dawn: {
      provider: 'dawn',
      providerName: 'webgpu',
      executionBackend: 'dawn_node_webgpu',
      loader: 'node-dawn',
    },
    doe: {
      provider: 'doe',
      providerName: 'doe-gpu',
      executionBackend: 'doe_node_webgpu',
      loader: 'node-doe',
    },
  }),
  bun: Object.freeze({
    'bun-webgpu': {
      provider: 'bun-webgpu',
      providerName: 'bun-webgpu',
      executionBackend: 'bun_webgpu_package',
      loader: 'bun-webgpu',
    },
    doe: {
      provider: 'doe',
      providerName: 'doe-gpu',
      executionBackend: 'doe_bun_package',
      loader: 'bun-doe',
    },
  }),
});

const TRACE_META_PROCESS_WALL_SOURCE = 'trace-meta-process-wall';
const DEBUG_PROGRESS_INTERVAL = 64;
const NODE_WEBGPU_UNSUPPORTED_ERROR_CODE = 'NODE_WEBGPU_UNSUPPORTED';
let packageExecutionPolicyPromise = null;

function nsFromMs(ms) {
  return Math.max(0, Math.round(ms * 1_000_000));
}

function digestBytes(view) {
  return createHash('sha256').update(view).digest('hex');
}

function stableArtifactHash(payload) {
  return createHash('sha256').update(JSON.stringify(payload), 'utf8').digest('hex');
}

function nsDelta(startedAtMs) {
  return nsFromMs(performance.now() - startedAtMs);
}

function parseOptionalPositiveInt(value) {
  const normalized = typeof value === 'string' ? value.trim() : '';
  if (!normalized) {
    return 0;
  }
  const parsed = Number(normalized);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error(`expected a positive integer, got: ${value}`);
  }
  return parsed;
}

function createDebugLogger(enabled) {
  return (phase, fields = {}) => {
    if (!enabled) {
      return;
    }
    process.stderr.write(`${JSON.stringify({
      kind: 'node_webgpu_debug',
      phase,
      ...fields,
    })}\n`);
  };
}

function shouldLogProgress(index, total) {
  if (total <= 0) {
    return false;
  }
  return index < 3 || index === total - 1 || (index + 1) % DEBUG_PROGRESS_INTERVAL === 0;
}

function executionShapeForPlan(plan) {
  return {
    bufferCount: plan.buffers.length,
    moduleCount: plan.modules.length,
    stepCount: plan.steps.length,
    writeBufferCount: plan.steps.filter((step) => step.kind === 'writeBuffer').length,
    dispatchCount: plan.steps.filter((step) => step.kind === 'dispatch').length,
    copyBufferToBufferCount: plan.steps.filter((step) => step.kind === 'copyBufferToBuffer').length,
    readBufferCount: plan.steps.filter((step) => step.kind === 'readBuffer').length,
  };
}

export function applyDebugStepLimit(normalizedPlan, stepLimit) {
  if (!stepLimit || stepLimit >= normalizedPlan.steps.length) {
    return normalizedPlan;
  }
  const steps = normalizedPlan.steps.slice(0, stepLimit);
  const referencedBuffers = new Set();
  const referencedModules = new Set();
  for (const step of steps) {
    if (step.kind === 'writeBuffer' || step.kind === 'readBuffer') {
      referencedBuffers.add(step.bufferId);
      continue;
    }
    if (step.kind === 'copyBufferToBuffer') {
      referencedBuffers.add(step.srcBufferId);
      referencedBuffers.add(step.dstBufferId);
      continue;
    }
    if (step.kind === 'dispatch') {
      referencedModules.add(step.moduleId);
      for (const binding of step.bindings ?? []) {
        referencedBuffers.add(binding.bufferId);
      }
    }
  }
  const limitedPlan = {
    ...normalizedPlan,
    buffers: normalizedPlan.buffers.filter((buffer) => referencedBuffers.has(buffer.id)),
    modules: normalizedPlan.modules.filter((module) => referencedModules.has(module.id)),
    steps,
  };
  return {
    ...limitedPlan,
    planHash: stableArtifactHash({
      schemaVersion: limitedPlan.schemaVersion,
      planId: limitedPlan.planId,
      executorId: limitedPlan.executorId,
      workloadId: limitedPlan.workloadId,
      domain: limitedPlan.domain,
      comparable: limitedPlan.comparable,
      timing: limitedPlan.timing,
      adapter: limitedPlan.adapter,
      buffers: limitedPlan.buffers,
      modules: limitedPlan.modules,
      steps: limitedPlan.steps,
    }),
    executionShape: executionShapeForPlan(limitedPlan),
  };
}

async function loadJsonFile(path) {
  const text = await readFile(path, 'utf8');
  const payload = JSON.parse(text);
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error(`${path}: expected a JSON object`);
  }
  return payload;
}

async function loadPackageExecutionPolicy() {
  if (!packageExecutionPolicyPromise) {
    packageExecutionPolicyPromise = loadJsonFile(PACKAGE_EXECUTION_POLICY_PATH)
      .catch((error) => {
        packageExecutionPolicyPromise = null;
        throw error;
      });
  }
  return await packageExecutionPolicyPromise;
}

function zeroHostTotals() {
  return {
    hostInputReadTotalNs: 0,
    hostInputParseTotalNs: 0,
    hostWorkloadPrepareTotalNs: 0,
    hostExecutorInitTotalNs: 0,
    hostUploadPrewarmTotalNs: 0,
    hostKernelPrewarmTotalNs: 0,
    hostCommandOrchestrationTotalNs: 0,
    hostArtifactFinalizeTotalNs: 0,
  };
}

export function boundaryScopedHostTotals({
  preparedSession,
  hostInputReadTotalNs,
  hostInputParseTotalNs,
  hostWorkloadPrepareTotalNs,
  hostExecutorInitTotalNs,
  hostUploadPrewarmTotalNs,
  hostKernelPrewarmTotalNs,
  hostCommandOrchestrationTotalNs,
  hostArtifactFinalizeTotalNs,
}) {
  return {
    hostInputReadTotalNs: preparedSession ? 0 : hostInputReadTotalNs,
    hostInputParseTotalNs: preparedSession ? 0 : hostInputParseTotalNs,
    hostWorkloadPrepareTotalNs: preparedSession ? 0 : hostWorkloadPrepareTotalNs,
    hostExecutorInitTotalNs: preparedSession ? 0 : hostExecutorInitTotalNs,
    hostUploadPrewarmTotalNs,
    hostKernelPrewarmTotalNs,
    hostCommandOrchestrationTotalNs,
    hostArtifactFinalizeTotalNs,
  };
}

function zeroPackageSetupBreakdown() {
  return {
    bufferCreateTotalNs: 0,
    initialDataWriteTotalNs: 0,
    shaderModuleCreateTotalNs: 0,
    bindGroupLayoutCreateTotalNs: 0,
    pipelineLayoutCreateTotalNs: 0,
    pipelineCreateTotalNs: 0,
    bindGroupCreateTotalNs: 0,
  };
}

function zeroPackageStepBreakdown() {
  return {
    writeMaterializeTotalNs: 0,
    writeQueueWriteTotalNs: 0,
    dispatchEncodeApiTotalNs: 0,
    copyEncodeApiTotalNs: 0,
    submitCommandEncoderFinishTotalNs: 0,
    submitQueueSubmitTotalNs: 0,
    submitQueueWaitTotalNs: 0,
    submitCommandPrepTotalNs: 0,
    submitAddonCallTotalNs: 0,
    submitAddonCommandReplayTotalNs: 0,
    submitAddonQueueSubmitTotalNs: 0,
    submitAddonFlushTotalNs: 0,
    submitPostSubmitBookkeepingTotalNs: 0,
    submitQueueFlushTotalNs: 0,
    submitQueueFlushWaitCompletedTotalNs: 0,
    submitQueueFlushDeferredCopyTotalNs: 0,
    submitQueueFlushDeferredResolveTotalNs: 0,
    submitQueueWaitBookkeepingTotalNs: 0,
    readbackTotalNs: 0,
  };
}

function fallbackExecutionShape() {
  return {
    stepCount: 0,
    dispatchCount: 0,
    bufferCount: 0,
    moduleCount: 0,
    writeBufferCount: 0,
    copyBufferToBufferCount: 0,
    readBufferCount: 0,
  };
}

function fallbackPlanSummary({ workloadId, planPath }) {
  const executionShape = fallbackExecutionShape();
  const planId = `unparsed:${workloadId || 'unknown'}`;
  const planHash = stableArtifactHash({
    workloadId: workloadId || '',
    planPath: planPath || '',
    executionShape,
  });
  return {
    workloadId: workloadId || '',
    canonicalWorkloadId: workloadId || '',
    planId,
    planHash,
    executionShape,
    planSummary: {
      schemaVersion: 1,
      planId,
      executorId: 'node-webgpu',
      workloadId: workloadId || '',
      domain: 'unknown',
      comparable: false,
      timing: {
        iterations: 1,
        warmup: 0,
        timingSource: 'doe-execution-total-ns',
        timingClass: 'operation',
      },
      planHash,
      executionShape,
      planPath: planPath || '',
    },
  };
}

function resolvePlanMetadata({ normalizedPlan = null, workloadId = '', planPath = '' }) {
  if (normalizedPlan) {
    return {
      workloadId: normalizedPlan.workloadId,
      canonicalWorkloadId: normalizedPlan.workloadId,
      planId: normalizedPlan.planId,
      planHash: normalizedPlan.planHash,
      executionShape: normalizedPlan.executionShape,
      planSummary: {
        schemaVersion: normalizedPlan.schemaVersion,
        planId: normalizedPlan.planId,
        executorId: normalizedPlan.executorId,
        workloadId: normalizedPlan.workloadId,
        domain: normalizedPlan.domain,
        comparable: normalizedPlan.comparable,
        timing: normalizedPlan.timing,
        planHash: normalizedPlan.planHash,
        executionShape: normalizedPlan.executionShape,
      },
    };
  }
  return fallbackPlanSummary({ workloadId, planPath });
}

function makeUnsupportedNodeWebGpuError({
  unsupportedCode,
  message,
  detail = '',
  hostExecutorInitTotalNs = 0,
}) {
  const error = new Error(message);
  error.code = NODE_WEBGPU_UNSUPPORTED_ERROR_CODE;
  error.unsupportedCode = unsupportedCode;
  error.unsupportedDetail = detail;
  error.hostExecutorInitTotalNs = hostExecutorInitTotalNs;
  return error;
}

function isUnsupportedNodeWebGpuError(error) {
  return Boolean(error && error.code === NODE_WEBGPU_UNSUPPORTED_ERROR_CODE);
}

export function classifyBringupUnsupported(stage, error) {
  const message = String(error?.message ?? error ?? '');
  const code = String(error?.code ?? '');
  const normalized = message.toLowerCase();
  const unavailable = (
    normalized.includes('status=3')
    || normalized.includes('unavailable')
    || normalized.includes('no adapter found')
    || normalized.includes('runtime init failed')
  );
  if (!unavailable && code !== 'DOE_REQUEST_ADAPTER_ERROR' && code !== 'DOE_REQUEST_DEVICE_ERROR') {
    return null;
  }
  return {
    unsupportedCode: stage === 'requestDevice' ? 'device_unavailable' : 'adapter_unavailable',
    detail: message,
  };
}

export function buildUnsupportedExecutionResult({
  normalizedPlan = null,
  spec,
  preparedSession,
  hostInputReadTotalNs,
  hostInputParseTotalNs,
  hostWorkloadPrepareTotalNs,
  hostExecutorInitTotalNs,
  processWallMs,
  unsupportedCode = '',
  unsupportedDetail = '',
  workloadId = '',
  planPath = '',
}) {
  const planMeta = resolvePlanMetadata({ normalizedPlan, workloadId, planPath });
  const scopedHostTotals = boundaryScopedHostTotals({
    preparedSession,
    hostInputReadTotalNs,
    hostInputParseTotalNs,
    hostWorkloadPrepareTotalNs,
    hostExecutorInitTotalNs,
    hostUploadPrewarmTotalNs: 0,
    hostKernelPrewarmTotalNs: 0,
    hostCommandOrchestrationTotalNs: 0,
    hostArtifactFinalizeTotalNs: 0,
  });
  const meta = {
    schemaVersion: 1,
    kind: 'trace_meta',
    provider: spec.provider,
    providerName: spec.providerName,
    executionBackend: spec.executionBackend,
    executionProvider: spec.provider,
    executionProviderName: spec.providerName,
    executionRowCount: 0,
    executionSuccessCount: 0,
    executionErrorCount: 0,
    executionSkippedCount: 0,
    executionUnsupportedCount: 1,
    executionDispatchCount: 0,
    executionTotalNs: 0,
    executionSetupTotalNs: 0,
    executionEncodeTotalNs: 0,
    executionSubmitWaitTotalNs: 0,
    ...scopedHostTotals,
    timingMs: 0,
    elapsedMs: processWallMs,
    processWallMs,
    timingSource: 'doe-execution-total-ns',
    timingClass: 'operation',
    queueSyncMode: 'per-command',
    queueWaitMode: 'queue.onSubmittedWorkDone',
    executionQueueSyncMode: 'per-command',
    executionQueueWaitMode: 'queue.onSubmittedWorkDone',
    ...(unsupportedCode ? { unsupportedCode } : {}),
    ...(unsupportedDetail ? { unsupportedDetail } : {}),
    workload: planMeta.workloadId,
    canonicalWorkloadId: planMeta.canonicalWorkloadId,
    planId: planMeta.planId,
    planHash: planMeta.planHash,
    planSummary: planMeta.planSummary,
    executionShape: planMeta.executionShape,
    packagePreparedSession: preparedSession,
    packageSetupIncludedInSelectedTiming: !preparedSession,
    packageSetupTotalNs: 0,
    packageSetupBreakdownNs: zeroPackageSetupBreakdown(),
    packageStepBreakdownNs: zeroPackageStepBreakdown(),
    ...(preparedSession ? { workloadUnitWallSource: TRACE_META_PROCESS_WALL_SOURCE } : {}),
    samplesMs: [0],
    stats: {
      count: 1,
      min: 0,
      max: 0,
      median: 0,
      p95: 0,
      p99: 0,
      mean: 0,
      stdev: 0,
    },
  };
  meta.artifactHash = stableArtifactHash(meta);
  return { meta, rows: [] };
}

export function buildErrorExecutionResult({
  normalizedPlan = null,
  spec,
  preparedSession,
  hostInputReadTotalNs,
  hostInputParseTotalNs,
  hostWorkloadPrepareTotalNs,
  hostExecutorInitTotalNs,
  processWallMs,
  workloadId = '',
  planPath = '',
}) {
  const planMeta = resolvePlanMetadata({ normalizedPlan, workloadId, planPath });
  const scopedHostTotals = boundaryScopedHostTotals({
    preparedSession,
    hostInputReadTotalNs,
    hostInputParseTotalNs,
    hostWorkloadPrepareTotalNs,
    hostExecutorInitTotalNs,
    hostUploadPrewarmTotalNs: 0,
    hostKernelPrewarmTotalNs: 0,
    hostCommandOrchestrationTotalNs: 0,
    hostArtifactFinalizeTotalNs: 0,
  });
  const meta = {
    schemaVersion: 1,
    kind: 'trace_meta',
    provider: spec.provider,
    providerName: spec.providerName,
    executionBackend: spec.executionBackend,
    executionProvider: spec.provider,
    executionProviderName: spec.providerName,
    executionRowCount: 0,
    executionSuccessCount: 0,
    executionErrorCount: 1,
    executionSkippedCount: 0,
    executionUnsupportedCount: 0,
    executionDispatchCount: 0,
    executionTotalNs: 0,
    executionSetupTotalNs: 0,
    executionEncodeTotalNs: 0,
    executionSubmitWaitTotalNs: 0,
    ...scopedHostTotals,
    timingMs: 0,
    elapsedMs: processWallMs,
    processWallMs,
    timingSource: 'doe-execution-total-ns',
    timingClass: 'operation',
    queueSyncMode: 'per-command',
    queueWaitMode: 'queue.onSubmittedWorkDone',
    executionQueueSyncMode: 'per-command',
    executionQueueWaitMode: 'queue.onSubmittedWorkDone',
    workload: planMeta.workloadId,
    canonicalWorkloadId: planMeta.canonicalWorkloadId,
    planId: planMeta.planId,
    planHash: planMeta.planHash,
    planSummary: planMeta.planSummary,
    executionShape: planMeta.executionShape,
    packagePreparedSession: preparedSession,
    packageSetupIncludedInSelectedTiming: !preparedSession,
    packageSetupTotalNs: 0,
    packageSetupBreakdownNs: zeroPackageSetupBreakdown(),
    packageStepBreakdownNs: zeroPackageStepBreakdown(),
    ...(preparedSession ? { workloadUnitWallSource: TRACE_META_PROCESS_WALL_SOURCE } : {}),
    samplesMs: [0],
    stats: {
      count: 1,
      min: 0,
      max: 0,
      median: 0,
      p95: 0,
      p99: 0,
      mean: 0,
      stdev: 0,
    },
  };
  meta.artifactHash = stableArtifactHash(meta);
  return { meta, rows: [] };
}

async function writeExecutorArtifacts(traceMetaPath, traceJsonlPath, meta, rows) {
  if (traceMetaPath) {
    await mkdir(resolve(traceMetaPath, '..'), { recursive: true });
    await writeFile(traceMetaPath, `${JSON.stringify(meta)}\n`, 'utf8');
  }
  if (traceJsonlPath) {
    await mkdir(resolve(traceJsonlPath, '..'), { recursive: true });
    const payload = rows.length > 0
      ? `${rows.map((row) => JSON.stringify(row)).join('\n')}\n`
      : '';
    await writeFile(traceJsonlPath, payload, 'utf8');
  }
}

function bufferUsageMask(globals, usage) {
  let mask = 0;
  for (const entry of usage) {
    if (entry === 'storage') mask |= globals.GPUBufferUsage.STORAGE;
    if (entry === 'copy_dst') mask |= globals.GPUBufferUsage.COPY_DST;
    if (entry === 'copy_src') mask |= globals.GPUBufferUsage.COPY_SRC;
    if (entry === 'map_read') mask |= globals.GPUBufferUsage.MAP_READ;
    if (entry === 'map_write') mask |= globals.GPUBufferUsage.MAP_WRITE;
    if (entry === 'uniform') mask |= globals.GPUBufferUsage.UNIFORM;
  }
  return mask;
}

export function providerSpec(provider, runtimeHost = 'node') {
  const runtimeProviders = PROVIDERS_BY_RUNTIME[runtimeHost] ?? {};
  const normalized = typeof provider === 'string' ? provider.trim().toLowerCase() : '';
  const spec = runtimeProviders[normalized];
  if (!spec) {
    throw new Error(
      `unsupported provider: ${provider} for runtime ${runtimeHost} `
      + `(expected one of ${Object.keys(runtimeProviders).join(', ')})`,
    );
  }
  return spec;
}

export function buildRequestDeviceDescriptor(adapterDescriptor = null) {
  const requiredFeatures = adapterDescriptor?.requiredFeatures ?? [];
  const requiredLimits = adapterDescriptor?.requiredLimits ?? {};
  const requestDeviceDescriptor = {};
  if (requiredFeatures.length > 0) {
    requestDeviceDescriptor.requiredFeatures = requiredFeatures;
  }
  if (Object.keys(requiredLimits).length > 0) {
    requestDeviceDescriptor.requiredLimits = requiredLimits;
  }
  return requestDeviceDescriptor;
}

function hostPolicyValueMatches(actual, expected) {
  if (expected === undefined || expected === null || expected === '') {
    return true;
  }
  if (Array.isArray(expected)) {
    return expected.includes(actual);
  }
  return actual === expected;
}

export function lookupUnsupportedPackageExecutionEntry(policy, {
  runtimeHost,
  provider,
  workloadId,
  platform,
  arch,
  hostname,
  osRelease,
}) {
  const entries = Array.isArray(policy?.unsupportedExecutions)
    ? policy.unsupportedExecutions
    : [];
  return entries.find((entry) => {
    if (!hostPolicyValueMatches(runtimeHost, entry.runtimeHost)) {
      return false;
    }
    if (!hostPolicyValueMatches(provider, entry.provider)) {
      return false;
    }
    if (!hostPolicyValueMatches(workloadId, entry.workloadId)) {
      return false;
    }
    if (!hostPolicyValueMatches(platform, entry.host?.platform)) {
      return false;
    }
    if (!hostPolicyValueMatches(arch, entry.host?.arch)) {
      return false;
    }
    if (!hostPolicyValueMatches(hostname, entry.host?.hostname)) {
      return false;
    }
    if (!hostPolicyValueMatches(osRelease, entry.host?.osRelease)) {
      return false;
    }
    return true;
  }) ?? null;
}

function globalsFromGlobalThis() {
  const required = [
    'GPUBufferUsage',
    'GPUShaderStage',
    'GPUMapMode',
    'GPUTextureUsage',
  ];
  const globals = {};
  for (const name of required) {
    const value = globalThis[name];
    if (value === undefined) {
      throw new Error(`global ${name} is not available after Bun WebGPU setup`);
    }
    globals[name] = value;
  }
  return globals;
}

async function resolveBunWebGpuModule() {
  let mod;
  try {
    mod = await import(pathToFileURL(FALLBACK_BUN_WEBGPU_PATH).href);
  } catch (_err) {
    mod = await import('bun-webgpu');
  }
  if (typeof mod.setupGlobals !== 'function') {
    throw new Error('bun-webgpu does not export setupGlobals()');
  }
  await mod.setupGlobals();
  if (typeof navigator === 'undefined' || !navigator.gpu) {
    throw new Error('bun-webgpu did not install navigator.gpu');
  }
  return {
    create: () => navigator.gpu,
    globals: globalsFromGlobalThis(),
  };
}

async function resolveProviderModule(spec) {
  switch (spec.loader) {
    case 'node-doe':
      return await import(pathToFileURL(DOE_PACKAGE_PATH).href);
    case 'node-dawn':
      try {
        return await import(pathToFileURL(FALLBACK_WEBGPU_PATH).href);
      } catch (_err) {
        return await import('webgpu');
      }
    case 'bun-doe':
      return await import(pathToFileURL(DOE_BUN_PACKAGE_PATH).href);
    case 'bun-webgpu':
      return await resolveBunWebGpuModule();
    default:
      throw new Error(`unsupported provider loader: ${spec.loader}`);
  }
}

function buildBindingDescriptor(binding, buffers, globals) {
  const buffer = buffers.get(binding.bufferId);
  if (!buffer) {
    throw new Error(`unknown buffer in binding: ${binding.bufferId}`);
  }
  return {
    layout: {
      binding: binding.binding,
      visibility: globals.GPUShaderStage.COMPUTE,
      buffer: { type: binding.bufferType },
    },
    entry: {
      binding: binding.binding,
      resource: {
        buffer,
        offset: binding.offset ?? 0,
        ...(binding.size !== undefined ? { size: binding.size } : {}),
      },
    },
  };
}

export function buildDispatchBindingCacheKey(step) {
  return stableArtifactHash(
    (step.bindings ?? []).map((binding) => ({
      binding: binding.binding,
      bufferId: binding.bufferId,
      bufferType: binding.bufferType,
      offset: binding.offset ?? 0,
      size: binding.size ?? null,
    })),
  );
}

async function createRuntime(normalizedPlan, webgpu, spec, { debugLog }) {
  const { create, globals } = webgpu;
  debugLog('runtime.create.start', {
    provider: spec.provider,
    executionBackend: spec.executionBackend,
    executionShape: normalizedPlan.executionShape,
  });
  const executorInitStartedAt = performance.now();
  const gpu = create([]);
  const preferredPower = normalizedPlan.adapter?.powerPreference ?? 'high-performance';
  const adapterRequests = [];
  if (preferredPower) {
    adapterRequests.push({ powerPreference: preferredPower });
  }
  adapterRequests.push({});
  if (preferredPower !== 'low-power') {
    adapterRequests.push({ powerPreference: 'low-power' });
  }
  let adapter = null;
  const adapterAttemptDetails = [];
  for (const [requestIndex, request] of adapterRequests.entries()) {
    debugLog('runtime.requestAdapter.start', {
      requestIndex,
      request,
    });
    try {
      adapter = await gpu.requestAdapter(request);
    } catch (error) {
      const unsupported = classifyBringupUnsupported('requestAdapter', error);
      if (!unsupported) {
        throw error;
      }
      adapterAttemptDetails.push(unsupported.detail);
      debugLog('runtime.requestAdapter.result', {
        requestIndex,
        found: false,
        unsupportedCode: unsupported.unsupportedCode,
        detail: unsupported.detail,
      });
      continue;
    }
    debugLog('runtime.requestAdapter.result', {
      requestIndex,
      found: Boolean(adapter),
    });
    if (adapter) {
      break;
    }
  }
  if (!adapter) {
    throw makeUnsupportedNodeWebGpuError({
      unsupportedCode: 'adapter_unavailable',
      message: `node-webgpu adapter unavailable for provider ${spec.provider}`,
      detail: adapterAttemptDetails.join('; ') || 'requestAdapter returned null for all requests',
      hostExecutorInitTotalNs: nsDelta(executorInitStartedAt),
    });
  }

  const requiredFeatures = normalizedPlan.adapter?.requiredFeatures ?? [];
  const requiredLimits = normalizedPlan.adapter?.requiredLimits ?? {};
  const requestDeviceDescriptor = buildRequestDeviceDescriptor(normalizedPlan.adapter);
  debugLog('runtime.requestDevice.start', {
    requiredFeatureCount: requiredFeatures.length,
    requiredLimitCount: Object.keys(requiredLimits).length,
  });
  let device;
  try {
    device = await adapter.requestDevice(requestDeviceDescriptor);
  } catch (error) {
    const unsupported = classifyBringupUnsupported('requestDevice', error);
    if (!unsupported) {
      throw error;
    }
    throw makeUnsupportedNodeWebGpuError({
      unsupportedCode: unsupported.unsupportedCode,
      message: `node-webgpu device unavailable for provider ${spec.provider}`,
      detail: unsupported.detail,
      hostExecutorInitTotalNs: nsDelta(executorInitStartedAt),
    });
  }
  debugLog('runtime.requestDevice.done', {});
  const hostExecutorInitTotalNs = nsDelta(executorInitStartedAt);
  const queue = device.queue;
  const buffers = new Map();
  const shaderModules = new Map();
  const dispatchStates = [];
  const bindGroupLayoutCache = new Map();
  const pipelineLayoutCache = new Map();
  const pipelineCache = new Map();
  const bindGroupCache = new Map();
  const setupBreakdownNs = zeroPackageSetupBreakdown();
  debugLog('runtime.setup.start', {
    bufferCount: normalizedPlan.buffers.length,
    moduleCount: normalizedPlan.modules.length,
    dispatchCount: normalizedPlan.executionShape.dispatchCount,
  });

  const setupStartedAt = performance.now();
  for (const [bufferIndex, bufferDef] of normalizedPlan.buffers.entries()) {
    if (shouldLogProgress(bufferIndex, normalizedPlan.buffers.length)) {
      debugLog('runtime.setup.buffer', {
        bufferIndex,
        bufferCount: normalizedPlan.buffers.length,
        bufferId: bufferDef.id,
        size: bufferDef.size,
      });
    }
    const createStartedAt = performance.now();
    const buffer = device.createBuffer({
      size: bufferDef.size,
      usage: bufferUsageMask(globals, bufferDef.usage),
      ...(bufferDef.label ? { label: bufferDef.label } : {}),
    });
    setupBreakdownNs.bufferCreateTotalNs += nsDelta(createStartedAt);
    buffers.set(bufferDef.id, buffer);
    if (bufferDef.data) {
      const writeStartedAt = performance.now();
      const materialized = materializeBufferData(bufferDef.data);
      if (materialized) {
        queue.writeBuffer(buffer, 0, materialized);
      }
      setupBreakdownNs.initialDataWriteTotalNs += nsDelta(writeStartedAt);
    }
  }

  for (const [moduleIndex, moduleDef] of normalizedPlan.modules.entries()) {
    if (shouldLogProgress(moduleIndex, normalizedPlan.modules.length)) {
      debugLog('runtime.setup.module', {
        moduleIndex,
        moduleCount: normalizedPlan.modules.length,
        moduleId: moduleDef.id,
        sourceKind: moduleDef.source.kind,
      });
    }
    const moduleStartedAt = performance.now();
    const code = moduleDef.source.kind === 'inline'
      ? moduleDef.source.code
      : await readFile(resolve(REPO_ROOT, moduleDef.source.path), 'utf8');
    shaderModules.set(moduleDef.id, device.createShaderModule({ code }));
    setupBreakdownNs.shaderModuleCreateTotalNs += nsDelta(moduleStartedAt);
  }

  let dispatchSetupIndex = 0;
  for (const step of normalizedPlan.steps) {
    if (step.kind !== 'dispatch') {
      continue;
    }
    if (shouldLogProgress(dispatchSetupIndex, normalizedPlan.executionShape.dispatchCount)) {
      debugLog('runtime.setup.dispatch', {
        dispatchSetupIndex,
        dispatchCount: normalizedPlan.executionShape.dispatchCount,
        moduleId: step.moduleId,
        bindingCount: step.bindings.length,
      });
    }
    const shaderModule = shaderModules.get(step.moduleId);
    if (!shaderModule) {
      throw new Error(`dispatch references unknown module: ${step.moduleId}`);
    }
    const bindingLayouts = [];
    const bindEntries = [];
    for (const binding of step.bindings) {
      const { layout, entry } = buildBindingDescriptor(binding, buffers, globals);
      bindingLayouts.push(layout);
      bindEntries.push(entry);
    }
    const layoutKey = stableArtifactHash(bindingLayouts);
    let bindGroupLayout = bindGroupLayoutCache.get(layoutKey);
    if (!bindGroupLayout) {
      const bindGroupLayoutStartedAt = performance.now();
      bindGroupLayout = device.createBindGroupLayout({ entries: bindingLayouts });
      setupBreakdownNs.bindGroupLayoutCreateTotalNs += nsDelta(bindGroupLayoutStartedAt);
      bindGroupLayoutCache.set(layoutKey, bindGroupLayout);
    }
    let pipelineLayout = pipelineLayoutCache.get(layoutKey);
    if (!pipelineLayout) {
      const pipelineLayoutStartedAt = performance.now();
      pipelineLayout = device.createPipelineLayout({ bindGroupLayouts: [bindGroupLayout] });
      setupBreakdownNs.pipelineLayoutCreateTotalNs += nsDelta(pipelineLayoutStartedAt);
      pipelineLayoutCache.set(layoutKey, pipelineLayout);
    }
    const pipelineKey = `${step.moduleId}:${step.entryPoint ?? 'main'}:${layoutKey}`;
    let pipeline = pipelineCache.get(pipelineKey);
    if (!pipeline) {
      const pipelineStartedAt = performance.now();
      pipeline = device.createComputePipeline({
        layout: pipelineLayout,
        compute: {
          module: shaderModule,
          entryPoint: step.entryPoint ?? 'main',
        },
      });
      setupBreakdownNs.pipelineCreateTotalNs += nsDelta(pipelineStartedAt);
      pipelineCache.set(pipelineKey, pipeline);
    }
    const bindGroupKey = `${layoutKey}:${buildDispatchBindingCacheKey(step)}`;
    let bindGroup = bindGroupCache.get(bindGroupKey);
    if (!bindGroup) {
      const bindGroupStartedAt = performance.now();
      bindGroup = device.createBindGroup({
        layout: bindGroupLayout,
        entries: bindEntries,
      });
      setupBreakdownNs.bindGroupCreateTotalNs += nsDelta(bindGroupStartedAt);
      bindGroupCache.set(bindGroupKey, bindGroup);
    }
    dispatchStates.push({ step, pipeline, bindGroup });
    dispatchSetupIndex += 1;
  }
  const setupTotalNs = nsFromMs(performance.now() - setupStartedAt);
  debugLog('runtime.setup.done', {
    setupTotalNs,
    setupBreakdownNs,
  });

  return {
    adapter,
    device,
    queue,
    globals,
    providerSpec: spec,
    buffers,
    dispatchStates,
    hostExecutorInitTotalNs,
    setupTotalNs,
    setupBreakdownNs,
  };
}

async function executeSample(normalizedPlan, runtime, { includeSetupInSelectedTiming, debugLog }) {
  const rows = [];
  let executionSetupTotalNs = 0;
  let executionEncodeTotalNs = 0;
  let executionSubmitWaitTotalNs = 0;
  let executionDispatchCount = 0;
  let executionSuccessCount = 0;
  const stepBreakdownNs = zeroPackageStepBreakdown();
  let encoder = null;
  let pass = null;
  let dispatchStateIndex = 0;
  let firstSubmitLogged = false;
  async function flushEncoder() {
    if (!encoder) {
      return;
    }
    if (pass) {
      pass.end();
      pass = null;
    }
    const submitStartedAt = performance.now();
    const finishStartedAt = submitStartedAt;
    const isFirstSubmit = !firstSubmitLogged;
    if (isFirstSubmit) {
      debugLog('execution.firstSubmit.finish.start', {
        dispatchesEncoded: dispatchStateIndex,
      });
    }
    const commandBuffer = encoder.finish();
    const finishNs = nsDelta(finishStartedAt);
    encoder = null;
    if (isFirstSubmit) {
      debugLog('execution.firstSubmit.start', {
        dispatchesEncoded: dispatchStateIndex,
      });
      firstSubmitLogged = true;
    }
    if (isFirstSubmit) {
      debugLog('execution.firstSubmit.finish.done', {
        finishNs,
        dispatchesEncoded: dispatchStateIndex,
      });
    }
    const queueSubmitStartedAt = performance.now();
    if (isFirstSubmit) {
      debugLog('execution.firstSubmit.queueSubmit.start', {
        dispatchesEncoded: dispatchStateIndex,
      });
    }
    runtime.queue.submit([commandBuffer]);
    const queueSubmitNs = nsDelta(queueSubmitStartedAt);
    if (isFirstSubmit) {
      debugLog('execution.firstSubmit.queueSubmit.done', {
        queueSubmitNs,
        dispatchesEncoded: dispatchStateIndex,
      });
    }
    const queueWaitStartedAt = performance.now();
    if (isFirstSubmit) {
      debugLog('execution.firstSubmit.queueWait.start', {
        dispatchesEncoded: dispatchStateIndex,
      });
    }
    await runtime.queue.onSubmittedWorkDone?.();
    const queueWaitNs = nsDelta(queueWaitStartedAt);
    if (isFirstSubmit) {
      debugLog('execution.firstSubmit.queueWait.done', {
        queueWaitNs,
        dispatchesEncoded: dispatchStateIndex,
      });
    }
    const submitNs = nsFromMs(performance.now() - submitStartedAt);
    stepBreakdownNs.submitCommandEncoderFinishTotalNs += finishNs;
    stepBreakdownNs.submitQueueSubmitTotalNs += queueSubmitNs;
    stepBreakdownNs.submitQueueWaitTotalNs += queueWaitNs;
    executionSubmitWaitTotalNs += submitNs;
    if (firstSubmitLogged) {
      debugLog('execution.firstSubmit.done', {
        finishNs,
        queueSubmitNs,
        queueWaitNs,
        submitWaitNs: submitNs,
      });
      firstSubmitLogged = false;
    }
  }

  const commandLoopStartedAt = performance.now();
  for (const [index, step] of normalizedPlan.steps.entries()) {
    if (step.kind === 'writeBuffer') {
      await flushEncoder();
      const buffer = runtime.buffers.get(step.bufferId);
      if (!buffer) {
        throw new Error(`writeBuffer references unknown buffer: ${step.bufferId}`);
      }
      const materializeStartedAt = performance.now();
      const materialized = materializeBufferData(step.data);
      const materializeNs = nsDelta(materializeStartedAt);
      const writeStartedAt = performance.now();
      runtime.queue.writeBuffer(buffer, step.offset ?? 0, materialized);
      const queueWriteNs = nsDelta(writeStartedAt);
      const writeNs = materializeNs + queueWriteNs;
      stepBreakdownNs.writeMaterializeTotalNs += materializeNs;
      stepBreakdownNs.writeQueueWriteTotalNs += queueWriteNs;
      executionSetupTotalNs += writeNs;
      rows.push({
        schemaVersion: 1,
        kind: 'node_webgpu_step',
        stepIndex: index,
        stepId: step.id ?? `step-${index}`,
        stepKind: step.kind,
        executionBackend: runtime.providerSpec.executionBackend,
        executionProvider: runtime.providerSpec.provider,
        executionProviderName: runtime.providerSpec.providerName,
        executionDurationNs: writeNs,
        executionSetupNs: writeNs,
        executionEncodeNs: 0,
        executionSubmitWaitNs: 0,
        executionSuccess: true,
        timingSource: 'doe-execution-total-ns',
        timingClass: 'operation',
        workloadId: normalizedPlan.workloadId,
        planId: normalizedPlan.planId,
        planHash: normalizedPlan.planHash,
      });
      executionSuccessCount += 1;
      continue;
    }

    if (step.kind === 'dispatch') {
      if (!encoder) {
        encoder = runtime.device.createCommandEncoder();
      }
      if (!pass) {
        pass = encoder.beginComputePass();
      }
      const state = runtime.dispatchStates[dispatchStateIndex++];
      if (!state || state.step.moduleId !== step.moduleId) {
        throw new Error(`dispatch plan mismatch at step ${index}`);
      }
      const opStartedAt = performance.now();
      pass.setPipeline(state.pipeline);
      pass.setBindGroup(0, state.bindGroup);
      pass.dispatchWorkgroups(step.workgroups[0], step.workgroups[1], step.workgroups[2]);
      const opNs = nsDelta(opStartedAt);
      stepBreakdownNs.dispatchEncodeApiTotalNs += opNs;
      executionEncodeTotalNs += opNs;
      rows.push({
        schemaVersion: 1,
        kind: 'node_webgpu_step',
        stepIndex: index,
        stepId: step.id ?? `step-${index}`,
        stepKind: step.kind,
        executionBackend: runtime.providerSpec.executionBackend,
        executionProvider: runtime.providerSpec.provider,
        executionProviderName: runtime.providerSpec.providerName,
        executionDurationNs: opNs,
        executionSetupNs: 0,
        executionEncodeNs: opNs,
        executionSubmitWaitNs: 0,
        executionSuccess: true,
        timingSource: 'doe-execution-total-ns',
        timingClass: 'operation',
        workloadId: normalizedPlan.workloadId,
        planId: normalizedPlan.planId,
        planHash: normalizedPlan.planHash,
      });
      executionDispatchCount += 1;
      executionSuccessCount += 1;
      continue;
    }

    if (step.kind === 'copyBufferToBuffer') {
      if (!encoder) {
        encoder = runtime.device.createCommandEncoder();
      }
      if (pass) {
        pass.end();
        pass = null;
      }
      const src = runtime.buffers.get(step.srcBufferId);
      const dst = runtime.buffers.get(step.dstBufferId);
      if (!src || !dst) {
        throw new Error(`copyBufferToBuffer references unknown buffer(s): ${step.srcBufferId} -> ${step.dstBufferId}`);
      }
      const opStartedAt = performance.now();
      encoder.copyBufferToBuffer(src, 0, dst, 0, step.sizeBytes);
      const opNs = nsDelta(opStartedAt);
      stepBreakdownNs.copyEncodeApiTotalNs += opNs;
      executionEncodeTotalNs += opNs;
      rows.push({
        schemaVersion: 1,
        kind: 'node_webgpu_step',
        stepIndex: index,
        stepId: step.id ?? `step-${index}`,
        stepKind: step.kind,
        executionBackend: runtime.providerSpec.executionBackend,
        executionProvider: runtime.providerSpec.provider,
        executionProviderName: runtime.providerSpec.providerName,
        executionDurationNs: opNs,
        executionSetupNs: 0,
        executionEncodeNs: opNs,
        executionSubmitWaitNs: 0,
        executionSuccess: true,
        timingSource: 'doe-execution-total-ns',
        timingClass: 'operation',
        workloadId: normalizedPlan.workloadId,
        planId: normalizedPlan.planId,
        planHash: normalizedPlan.planHash,
      });
      executionSuccessCount += 1;
      continue;
    }

    if (step.kind === 'readBuffer') {
      await flushEncoder();
      const buffer = runtime.buffers.get(step.bufferId);
      if (!buffer) {
        throw new Error(`readBuffer references unknown buffer: ${step.bufferId}`);
      }
      const readStartedAt = performance.now();
      await buffer.mapAsync(runtime.globals.GPUMapMode.READ);
      const mapped = new Uint8Array(buffer.getMappedRange(0, buffer.size)).slice();
      const validation = validateSampleExpectation(mapped, step.validate);
      if (!validation.ok) {
        throw new Error(`validation failed for ${step.bufferId}: ${validation.detail}`);
      }
      buffer.unmap();
      const stepNs = nsDelta(readStartedAt);
      stepBreakdownNs.readbackTotalNs += stepNs;
      executionSubmitWaitTotalNs += stepNs;
      rows.push({
        schemaVersion: 1,
        kind: 'node_webgpu_step',
        stepIndex: index,
        stepId: step.id ?? `step-${index}`,
        stepKind: step.kind,
        executionBackend: runtime.providerSpec.executionBackend,
        executionProvider: runtime.providerSpec.provider,
        executionProviderName: runtime.providerSpec.providerName,
        executionDurationNs: stepNs,
        executionSetupNs: 0,
        executionEncodeNs: 0,
        executionSubmitWaitNs: stepNs,
        executionSuccess: true,
        timingSource: 'doe-execution-total-ns',
        timingClass: 'operation',
        workloadId: normalizedPlan.workloadId,
        planId: normalizedPlan.planId,
        planHash: normalizedPlan.planHash,
      });
      executionSuccessCount += 1;
      continue;
    }

    throw new Error(`unsupported step kind during execution: ${step.kind}`);
  }

  await flushEncoder();
  if (runtime.queue?._submitBreakdownNs) {
    stepBreakdownNs.submitCommandPrepTotalNs = runtime.queue._submitBreakdownNs.submitCommandPrepTotalNs ?? 0;
    stepBreakdownNs.submitAddonCallTotalNs = runtime.queue._submitBreakdownNs.submitAddonCallTotalNs ?? 0;
    stepBreakdownNs.submitAddonCommandReplayTotalNs = runtime.queue._submitBreakdownNs.submitAddonCommandReplayTotalNs ?? 0;
    stepBreakdownNs.submitAddonQueueSubmitTotalNs = runtime.queue._submitBreakdownNs.submitAddonQueueSubmitTotalNs ?? 0;
    stepBreakdownNs.submitAddonFlushTotalNs = runtime.queue._submitBreakdownNs.submitAddonFlushTotalNs ?? 0;
    stepBreakdownNs.submitPostSubmitBookkeepingTotalNs = runtime.queue._submitBreakdownNs.submitPostSubmitBookkeepingTotalNs ?? 0;
    stepBreakdownNs.submitQueueFlushTotalNs = runtime.queue._submitBreakdownNs.submitQueueFlushTotalNs ?? 0;
    stepBreakdownNs.submitQueueFlushWaitCompletedTotalNs = runtime.queue._submitBreakdownNs.submitQueueFlushWaitCompletedTotalNs ?? 0;
    stepBreakdownNs.submitQueueFlushDeferredCopyTotalNs = runtime.queue._submitBreakdownNs.submitQueueFlushDeferredCopyTotalNs ?? 0;
    stepBreakdownNs.submitQueueFlushDeferredResolveTotalNs = runtime.queue._submitBreakdownNs.submitQueueFlushDeferredResolveTotalNs ?? 0;
    stepBreakdownNs.submitQueueWaitBookkeepingTotalNs = runtime.queue._submitBreakdownNs.submitQueueWaitBookkeepingTotalNs ?? 0;
  }
  const commandLoopWallNs = nsDelta(commandLoopStartedAt);
  const selectedLoopTotalNs = executionSetupTotalNs + executionEncodeTotalNs + executionSubmitWaitTotalNs;
  const executionTotalNs = (
    (includeSetupInSelectedTiming ? runtime.setupTotalNs : 0)
    + selectedLoopTotalNs
  );
  const hostCommandOrchestrationTotalNs = Math.max(0, commandLoopWallNs - selectedLoopTotalNs);
  const timingMs = executionTotalNs / 1_000_000;
  debugLog('execution.done', {
    includeSetupInSelectedTiming,
    executionTotalNs,
    executionSetupTotalNs: (includeSetupInSelectedTiming ? runtime.setupTotalNs : 0) + executionSetupTotalNs,
    executionEncodeTotalNs,
    executionSubmitWaitTotalNs,
    hostCommandOrchestrationTotalNs,
  });

  const meta = {
    schemaVersion: 1,
    kind: 'trace_meta',
    provider: runtime.providerSpec.provider,
    providerName: runtime.providerSpec.providerName,
    executionBackend: runtime.providerSpec.executionBackend,
    executionProvider: runtime.providerSpec.provider,
    executionProviderName: runtime.providerSpec.providerName,
    executionRowCount: rows.length,
    executionSuccessCount,
    executionErrorCount: 0,
    executionSkippedCount: 0,
    executionUnsupportedCount: 0,
    executionDispatchCount,
    executionTotalNs,
    executionSetupTotalNs: (includeSetupInSelectedTiming ? runtime.setupTotalNs : 0) + executionSetupTotalNs,
    executionEncodeTotalNs,
    executionSubmitWaitTotalNs,
    hostInputReadTotalNs: 0,
    hostInputParseTotalNs: 0,
    hostWorkloadPrepareTotalNs: 0,
    hostExecutorInitTotalNs: runtime.hostExecutorInitTotalNs,
    hostUploadPrewarmTotalNs: 0,
    hostKernelPrewarmTotalNs: 0,
    hostCommandOrchestrationTotalNs,
    hostArtifactFinalizeTotalNs: 0,
    timingMs,
    timingSource: 'doe-execution-total-ns',
    timingClass: 'operation',
    queueSyncMode: 'per-command',
    queueWaitMode: 'queue.onSubmittedWorkDone',
    executionQueueSyncMode: 'per-command',
    executionQueueWaitMode: 'queue.onSubmittedWorkDone',
    workload: normalizedPlan.workloadId,
    canonicalWorkloadId: normalizedPlan.workloadId,
    planId: normalizedPlan.planId,
    planHash: normalizedPlan.planHash,
    adapterInfo: runtime.adapter.info ?? null,
    adapterLimits: runtime.adapter.limits ?? null,
    planSummary: planSummary(normalizedPlan),
    executionShape: normalizedPlan.executionShape,
    packagePreparedSession: !includeSetupInSelectedTiming,
    packageSetupIncludedInSelectedTiming: includeSetupInSelectedTiming,
    packageSetupTotalNs: runtime.setupTotalNs,
    packageSetupBreakdownNs: runtime.setupBreakdownNs,
    packageStepBreakdownNs: stepBreakdownNs,
    samplesMs: [timingMs],
    stats: {
      count: 1,
      min: timingMs,
      max: timingMs,
      median: timingMs,
      p95: timingMs,
      p99: timingMs,
      mean: timingMs,
      stdev: 0,
    },
  };
  meta.artifactHash = stableArtifactHash(meta);

  return { meta, rows };
}

export async function executePlanFile({
  planPath,
  workloadId,
  provider = 'dawn',
  runtimeHost = 'node',
  traceMetaPath,
  traceJsonlPath,
  dryRun = false,
  preparedSession = false,
  debugBoundaries = false,
  stepLimit = 0,
}) {
  const debugEnabled = (
    debugBoundaries
    || process.env.DOE_NODE_WEBGPU_DEBUG_BOUNDARIES === '1'
    || (runtimeHost === 'bun' && process.env.DOE_BUN_WEBGPU_DEBUG_BOUNDARIES === '1')
  );
  const effectiveStepLimit = stepLimit || parseOptionalPositiveInt(
    process.env.DOE_NODE_WEBGPU_STEP_LIMIT
      ?? (runtimeHost === 'bun' ? process.env.DOE_BUN_WEBGPU_STEP_LIMIT : '')
      ?? '',
  );
  const debugLog = createDebugLogger(debugEnabled);
  debugLog('execute.start', {
    runtimeHost,
    provider,
    planPath,
    workloadId,
    preparedSession,
    dryRun,
    stepLimit: effectiveStepLimit,
  });
  const spec = providerSpec(provider, runtimeHost);
  const hostInputReadStartedAt = performance.now();
  const planText = await readFile(planPath, 'utf8');
  const hostInputReadTotalNs = nsDelta(hostInputReadStartedAt);
  const hostInputParseStartedAt = performance.now();
  const plan = JSON.parse(planText);
  const hostInputParseTotalNs = nsDelta(hostInputParseStartedAt);
  const hostWorkloadPrepareStartedAt = performance.now();
  let normalizedPlan = normalizePlan(plan);
  const hostWorkloadPrepareTotalNs = nsDelta(hostWorkloadPrepareStartedAt);
  debugLog('plan.normalized', {
    planBytes: planText.length,
    executionShape: normalizedPlan.executionShape,
  });
  if (effectiveStepLimit > 0) {
    normalizedPlan = applyDebugStepLimit(normalizedPlan, effectiveStepLimit);
    debugLog('plan.stepLimit.applied', {
      stepLimit: effectiveStepLimit,
      executionShape: normalizedPlan.executionShape,
    });
  }
  if (workloadId && workloadId !== normalizedPlan.workloadId) {
    throw new Error(`workload mismatch: expected ${workloadId}, got ${normalizedPlan.workloadId}`);
  }
  if (dryRun) {
    const meta = {
      schemaVersion: 1,
      kind: 'trace_meta',
      provider: spec.provider,
      providerName: spec.providerName,
      executionBackend: spec.executionBackend,
      executionProvider: spec.provider,
      executionProviderName: spec.providerName,
      executionRowCount: normalizedPlan.executionShape.stepCount,
      executionSuccessCount: normalizedPlan.executionShape.stepCount,
      executionErrorCount: 0,
      executionSkippedCount: 0,
      executionUnsupportedCount: 0,
      executionDispatchCount: normalizedPlan.executionShape.dispatchCount,
      executionTotalNs: 0,
      executionSetupTotalNs: 0,
      executionEncodeTotalNs: 0,
      executionSubmitWaitTotalNs: 0,
      ...zeroHostTotals(),
      timingMs: 0,
      elapsedMs: 0,
      processWallMs: 0,
      timingSource: 'doe-execution-total-ns',
      timingClass: 'operation',
      queueSyncMode: 'per-command',
      queueWaitMode: 'queue.onSubmittedWorkDone',
      executionQueueSyncMode: 'per-command',
      executionQueueWaitMode: 'queue.onSubmittedWorkDone',
      workload: normalizedPlan.workloadId,
      canonicalWorkloadId: normalizedPlan.workloadId,
      planId: normalizedPlan.planId,
      planHash: normalizedPlan.planHash,
      planSummary: planSummary(normalizedPlan),
      executionShape: normalizedPlan.executionShape,
      packagePreparedSession: preparedSession,
      packageSetupIncludedInSelectedTiming: !preparedSession,
      packageSetupTotalNs: 0,
      packageSetupBreakdownNs: zeroPackageSetupBreakdown(),
      packageStepBreakdownNs: zeroPackageStepBreakdown(),
      ...(preparedSession ? { workloadUnitWallSource: TRACE_META_PROCESS_WALL_SOURCE } : {}),
      samplesMs: [0],
      stats: {
        count: 1,
        min: 0,
        max: 0,
        median: 0,
        p95: 0,
        p99: 0,
        mean: 0,
        stdev: 0,
      },
    };
    meta.artifactHash = stableArtifactHash(meta);
    const rows = normalizedPlan.steps.map((step, index) => ({
      schemaVersion: 1,
      kind: 'node_webgpu_step',
      stepIndex: index,
      stepId: step.id ?? `step-${index}`,
      stepKind: step.kind,
      executionBackend: spec.executionBackend,
      executionProvider: spec.provider,
      executionProviderName: spec.providerName,
      executionDurationNs: 0,
      executionSetupNs: 0,
      executionEncodeNs: 0,
      executionSubmitWaitNs: 0,
      executionSuccess: true,
      timingSource: 'doe-execution-total-ns',
      timingClass: 'operation',
      workloadId: normalizedPlan.workloadId,
      planId: normalizedPlan.planId,
      planHash: normalizedPlan.planHash,
    }));
    await writeExecutorArtifacts(traceMetaPath, traceJsonlPath, meta, rows);
    return { meta, rows };
  }

  const executionEnvelopeStartedAt = performance.now();
  const unsupportedEntry = lookupUnsupportedPackageExecutionEntry(
    await loadPackageExecutionPolicy(),
    {
      runtimeHost,
      provider: spec.provider,
      workloadId: normalizedPlan.workloadId,
      platform: process.platform,
      arch: process.arch,
      hostname: os.hostname(),
      osRelease: os.release(),
    },
  );
  if (unsupportedEntry) {
    const unsupportedResult = buildUnsupportedExecutionResult({
      normalizedPlan,
      spec,
      preparedSession,
      hostInputReadTotalNs,
      hostInputParseTotalNs,
      hostWorkloadPrepareTotalNs,
      hostExecutorInitTotalNs: 0,
      processWallMs: performance.now() - executionEnvelopeStartedAt,
      unsupportedCode: unsupportedEntry.unsupportedCode,
      unsupportedDetail: unsupportedEntry.detail ?? '',
    });
    const artifactFinalizeStartedAt = performance.now();
    await writeExecutorArtifacts(traceMetaPath, traceJsonlPath, unsupportedResult.meta, unsupportedResult.rows);
    unsupportedResult.meta.hostArtifactFinalizeTotalNs = nsDelta(artifactFinalizeStartedAt);
    unsupportedResult.meta.artifactHash = stableArtifactHash(unsupportedResult.meta);
    await writeExecutorArtifacts(traceMetaPath, null, unsupportedResult.meta, unsupportedResult.rows);
    return unsupportedResult;
  }
  const webgpuResolveStartedAt = performance.now();
  debugLog('provider.resolve.start', {
    provider: spec.provider,
  });
  const webgpu = await resolveProviderModule(spec);
  const providerModuleResolveTotalNs = nsDelta(webgpuResolveStartedAt);
  debugLog('provider.resolve.done', {
    provider: spec.provider,
    providerModuleResolveTotalNs,
  });
  let runtime = null;
  try {
    runtime = await createRuntime(normalizedPlan, webgpu, spec, { debugLog });
    runtime.hostExecutorInitTotalNs += providerModuleResolveTotalNs;
    const timedEnvelopeStartedAt = performance.now();
    const result = await executeSample(normalizedPlan, runtime, {
      includeSetupInSelectedTiming: !preparedSession,
      debugLog,
    });
    const artifactFinalizeStartedAt = performance.now();
    if (traceJsonlPath) {
      debugLog('artifact.write.traceJsonl.start', {
        traceJsonlPath,
        rowCount: result.rows.length,
      });
      await writeExecutorArtifacts(null, traceJsonlPath, result.meta, result.rows);
      debugLog('artifact.write.traceJsonl.done', {
        traceJsonlPath,
        rowCount: result.rows.length,
      });
    }
    Object.assign(result.meta, boundaryScopedHostTotals({
      preparedSession,
      hostInputReadTotalNs,
      hostInputParseTotalNs,
      hostWorkloadPrepareTotalNs,
      hostExecutorInitTotalNs: runtime.hostExecutorInitTotalNs,
      hostUploadPrewarmTotalNs: result.meta.hostUploadPrewarmTotalNs,
      hostKernelPrewarmTotalNs: result.meta.hostKernelPrewarmTotalNs,
      hostCommandOrchestrationTotalNs: result.meta.hostCommandOrchestrationTotalNs,
      hostArtifactFinalizeTotalNs: nsDelta(artifactFinalizeStartedAt),
    }));
    const processWallMs = (performance.now() - timedEnvelopeStartedAt);
    result.meta.elapsedMs = processWallMs;
    result.meta.processWallMs = processWallMs;
    if (preparedSession) {
      result.meta.workloadUnitWallSource = TRACE_META_PROCESS_WALL_SOURCE;
    }
    result.meta.artifactHash = stableArtifactHash(result.meta);
    debugLog('artifact.write.traceMeta.start', {
      traceMetaPath,
      rowCount: result.rows.length,
    });
    await writeExecutorArtifacts(traceMetaPath, null, result.meta, result.rows);
    debugLog('artifact.write.traceMeta.done', {
      traceMetaPath,
      rowCount: result.rows.length,
    });

    return result;
  } catch (error) {
    if (isUnsupportedNodeWebGpuError(error)) {
      debugLog('runtime.unsupported', {
        unsupportedCode: error.unsupportedCode,
        detail: error.unsupportedDetail ?? '',
      });
      const unsupportedResult = buildUnsupportedExecutionResult({
        normalizedPlan,
        spec,
        preparedSession,
        hostInputReadTotalNs,
        hostInputParseTotalNs,
        hostWorkloadPrepareTotalNs,
        hostExecutorInitTotalNs: providerModuleResolveTotalNs + (error.hostExecutorInitTotalNs ?? 0),
        processWallMs: performance.now() - executionEnvelopeStartedAt,
        unsupportedCode: error.unsupportedCode ?? '',
        unsupportedDetail: error.unsupportedDetail ?? '',
      });
      const artifactFinalizeStartedAt = performance.now();
      await writeExecutorArtifacts(traceMetaPath, traceJsonlPath, unsupportedResult.meta, unsupportedResult.rows);
      unsupportedResult.meta.hostArtifactFinalizeTotalNs = nsDelta(artifactFinalizeStartedAt);
      unsupportedResult.meta.artifactHash = stableArtifactHash(unsupportedResult.meta);
      await writeExecutorArtifacts(traceMetaPath, null, unsupportedResult.meta, unsupportedResult.rows);
      return unsupportedResult;
    }
    const errorResult = buildErrorExecutionResult({
      normalizedPlan,
      spec,
      preparedSession,
      hostInputReadTotalNs,
      hostInputParseTotalNs,
      hostWorkloadPrepareTotalNs,
      hostExecutorInitTotalNs: providerModuleResolveTotalNs + (runtime?.hostExecutorInitTotalNs ?? 0),
      processWallMs: performance.now() - executionEnvelopeStartedAt,
    });
    const artifactFinalizeStartedAt = performance.now();
    await writeExecutorArtifacts(traceMetaPath, traceJsonlPath, errorResult.meta, errorResult.rows);
    errorResult.meta.hostArtifactFinalizeTotalNs = nsDelta(artifactFinalizeStartedAt);
    errorResult.meta.artifactHash = stableArtifactHash(errorResult.meta);
    await writeExecutorArtifacts(traceMetaPath, null, errorResult.meta, errorResult.rows);
    throw error;
  } finally {
    debugLog('runtime.destroy.start', {
      provider: spec.provider,
    });
    debugLog('runtime.destroy.done', {
      provider: spec.provider,
    });
  }
}

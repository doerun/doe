import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { performance } from 'node:perf_hooks';
import { createHash } from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { join, resolve } from 'node:path';

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

const PROVIDERS = Object.freeze({
  dawn: {
    provider: 'dawn',
    providerName: 'webgpu',
    executionBackend: 'dawn_node_webgpu',
  },
  doe: {
    provider: 'doe',
    providerName: 'doe-gpu',
    executionBackend: 'doe_node_webgpu',
  },
});

function nsFromMs(ms) {
  return Math.max(0, Math.round(ms * 1_000_000));
}

function digestBytes(view) {
  return createHash('sha256').update(view).digest('hex');
}

function stableArtifactHash(payload) {
  return createHash('sha256').update(JSON.stringify(payload), 'utf8').digest('hex');
}

async function loadJsonFile(path) {
  const text = await readFile(path, 'utf8');
  const payload = JSON.parse(text);
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error(`${path}: expected a JSON object`);
  }
  return payload;
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

function providerSpec(provider) {
  const normalized = typeof provider === 'string' ? provider.trim().toLowerCase() : '';
  const spec = PROVIDERS[normalized];
  if (!spec) {
    throw new Error(`unsupported provider: ${provider} (expected one of ${Object.keys(PROVIDERS).join(', ')})`);
  }
  return spec;
}

async function resolveProviderModule(spec) {
  if (spec.provider === 'doe') {
    return await import(pathToFileURL(DOE_PACKAGE_PATH).href);
  }
  try {
    return await import(pathToFileURL(FALLBACK_WEBGPU_PATH).href);
  } catch (_err) {
    return await import('webgpu');
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

async function createRuntime(normalizedPlan, webgpu, spec) {
  const { create, globals } = webgpu;
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
  for (const request of adapterRequests) {
    adapter = await gpu.requestAdapter(request);
    if (adapter) {
      break;
    }
  }
  if (!adapter) {
    throw new Error('no adapter found for node-webgpu executor');
  }

  const device = await adapter.requestDevice({
    requiredFeatures: normalizedPlan.adapter?.requiredFeatures ?? [],
    requiredLimits: normalizedPlan.adapter?.requiredLimits ?? {},
  });
  const queue = device.queue;
  const buffers = new Map();
  const shaderModules = new Map();
  const dispatchStates = [];
  const bindGroupLayoutCache = new Map();
  const pipelineLayoutCache = new Map();
  const pipelineCache = new Map();

  const setupStartedAt = performance.now();
  for (const bufferDef of normalizedPlan.buffers) {
    const buffer = device.createBuffer({
      size: bufferDef.size,
      usage: bufferUsageMask(globals, bufferDef.usage),
      ...(bufferDef.label ? { label: bufferDef.label } : {}),
    });
    buffers.set(bufferDef.id, buffer);
    if (bufferDef.data) {
      const materialized = materializeBufferData(bufferDef.data);
      if (materialized) {
        queue.writeBuffer(buffer, 0, materialized);
      }
    }
  }

  for (const moduleDef of normalizedPlan.modules) {
    const code = moduleDef.source.kind === 'inline'
      ? moduleDef.source.code
      : await readFile(resolve(REPO_ROOT, moduleDef.source.path), 'utf8');
    shaderModules.set(moduleDef.id, device.createShaderModule({ code }));
  }

  for (const step of normalizedPlan.steps) {
    if (step.kind !== 'dispatch') {
      continue;
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
      bindGroupLayout = device.createBindGroupLayout({ entries: bindingLayouts });
      bindGroupLayoutCache.set(layoutKey, bindGroupLayout);
    }
    let pipelineLayout = pipelineLayoutCache.get(layoutKey);
    if (!pipelineLayout) {
      pipelineLayout = device.createPipelineLayout({ bindGroupLayouts: [bindGroupLayout] });
      pipelineLayoutCache.set(layoutKey, pipelineLayout);
    }
    const pipelineKey = `${step.moduleId}:${step.entryPoint ?? 'main'}:${layoutKey}`;
    let pipeline = pipelineCache.get(pipelineKey);
    if (!pipeline) {
      pipeline = device.createComputePipeline({
        layout: pipelineLayout,
        compute: {
          module: shaderModule,
          entryPoint: step.entryPoint ?? 'main',
        },
      });
      pipelineCache.set(pipelineKey, pipeline);
    }
    const bindGroup = device.createBindGroup({
      layout: bindGroupLayout,
      entries: bindEntries,
    });
    dispatchStates.push({ step, pipeline, bindGroup });
  }
  const setupTotalNs = nsFromMs(performance.now() - setupStartedAt);

  return {
    adapter,
    device,
    queue,
    globals,
    providerSpec: spec,
    buffers,
    dispatchStates,
    setupTotalNs,
  };
}

async function executeSample(normalizedPlan, runtime) {
  const rows = [];
  let executionSetupTotalNs = 0;
  let executionEncodeTotalNs = 0;
  let executionSubmitWaitTotalNs = 0;
  let executionDispatchCount = 0;
  let executionSuccessCount = 0;
  let encoder = null;
  let pass = null;
  let dispatchStateIndex = 0;
  async function flushEncoder() {
    if (!encoder) {
      return;
    }
    if (pass) {
      pass.end();
      pass = null;
    }
    const submitStartedAt = performance.now();
    const commandBuffer = encoder.finish();
    encoder = null;
    runtime.queue.submit([commandBuffer]);
    await runtime.queue.onSubmittedWorkDone?.();
    executionSubmitWaitTotalNs += nsFromMs(performance.now() - submitStartedAt);
  }

  for (const [index, step] of normalizedPlan.steps.entries()) {
    if (step.kind === 'writeBuffer') {
      await flushEncoder();
      const buffer = runtime.buffers.get(step.bufferId);
      if (!buffer) {
        throw new Error(`writeBuffer references unknown buffer: ${step.bufferId}`);
      }
      const writeStartedAt = performance.now();
      const materialized = materializeBufferData(step.data);
      runtime.queue.writeBuffer(buffer, step.offset ?? 0, materialized);
      const writeNs = nsFromMs(performance.now() - writeStartedAt);
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
      const opNs = nsFromMs(performance.now() - opStartedAt);
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
      const opNs = nsFromMs(performance.now() - opStartedAt);
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
      const stepNs = nsFromMs(performance.now() - readStartedAt);
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
  const executionTotalNs = runtime.setupTotalNs + executionSetupTotalNs + executionEncodeTotalNs + executionSubmitWaitTotalNs;
  const timingMs = executionTotalNs / 1_000_000;

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
    executionDispatchCount,
    executionTotalNs,
    executionSetupTotalNs: runtime.setupTotalNs + executionSetupTotalNs,
    executionEncodeTotalNs,
    executionSubmitWaitTotalNs,
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
  traceMetaPath,
  traceJsonlPath,
  dryRun = false,
}) {
  const spec = providerSpec(provider);
  const plan = await loadJsonFile(planPath);
  const normalizedPlan = normalizePlan(plan);
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
      executionDispatchCount: normalizedPlan.executionShape.dispatchCount,
      executionTotalNs: 0,
      executionSetupTotalNs: 0,
      executionEncodeTotalNs: 0,
      executionSubmitWaitTotalNs: 0,
      timingMs: 0,
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
    if (traceMetaPath) {
      await mkdir(resolve(traceMetaPath, '..'), { recursive: true });
      await writeFile(traceMetaPath, `${JSON.stringify(meta, null, 2)}\n`, 'utf8');
    }
    if (traceJsonlPath) {
      await mkdir(resolve(traceJsonlPath, '..'), { recursive: true });
      await writeFile(
        traceJsonlPath,
        `${rows.map((row) => JSON.stringify(row)).join('\n')}\n`,
        'utf8',
      );
    }
    return { meta, rows };
  }

  const webgpu = await resolveProviderModule(spec);
  const runtime = await createRuntime(normalizedPlan, webgpu, spec);
  try {
    const result = await executeSample(normalizedPlan, runtime);

    if (traceMetaPath) {
      await mkdir(resolve(traceMetaPath, '..'), { recursive: true });
      await writeFile(traceMetaPath, `${JSON.stringify(result.meta, null, 2)}\n`, 'utf8');
    }
    if (traceJsonlPath) {
      await mkdir(resolve(traceJsonlPath, '..'), { recursive: true });
      await writeFile(
        traceJsonlPath,
        `${result.rows.map((row) => JSON.stringify(row)).join('\n')}\n`,
        'utf8',
      );
    }

    return result;
  } finally {
    runtime.device.destroy?.();
  }
}

#!/usr/bin/env node
/**
 * End-to-end inference pipeline benchmark.
 *
 * Runs a full transformer inference pipeline (prefill + decode) through
 * the real WebGPU dispatch path. Weights are randomly generated at
 * runtime (not timed). Correctness is irrelevant — only dispatch
 * throughput matters.
 *
 * Usage:
 *   node bench/inference-pipeline/run-inference-bench.js [options]
 *
 * Options:
 *   --config <path>     Config JSON (default: bench/inference-pipeline/inference-pipeline-config.json)
 *   --model <id>        Model ID from config (default: first model)
 *   --phase <phase>     Run only this phase: prefill, decode, or e2e (default: all)
 *   --iterations <n>    Override iteration count
 *   --warmup <n>        Override warmup count
 *   --out <path>        Output NDJSON path (default: stdout)
 *   --backend <name>    Backend override (doe-native or dawn-delegate)
 */

import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve, dirname, join } from 'node:path';
import { performance } from 'node:perf_hooks';
import { parseArgs } from 'node:util';

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

const { values: flags } = parseArgs({
  options: {
    config: { type: 'string', default: 'bench/inference-pipeline/inference-pipeline-config.json' },
    model: { type: 'string' },
    phase: { type: 'string' },
    iterations: { type: 'string' },
    warmup: { type: 'string' },
    out: { type: 'string' },
    backend: { type: 'string' },
  },
});

const REPO_ROOT = resolve(import.meta.dirname, '..', '..');

function loadJson(relPath) {
  return JSON.parse(readFileSync(resolve(REPO_ROOT, relPath), 'utf8'));
}

// ---------------------------------------------------------------------------
// Weight pool — random, shared across layers, not timed
// ---------------------------------------------------------------------------

function createWeightPool(shapes) {
  const pool = new Map();
  for (const [name, size] of shapes) {
    if (pool.has(name)) continue;
    const data = new Float32Array(size);
    for (let i = 0; i < size; i++) data[i] = (Math.random() - 0.5) * 0.2;
    pool.set(name, data);
  }
  return pool;
}

function modelShapes(cfg) {
  const { hiddenDim: h, intermediateSize: ff, headDim: hd, numHeads: nh, vocabSize: v } = cfg;
  return [
    // embedding table
    ['embed_table', v * h],
    // per-layer weights (reused across all layers)
    ['norm_weight', h],
    ['q_proj', h * (nh * hd)],
    ['k_proj', h * (nh * hd)],
    ['v_proj', h * (nh * hd)],
    ['o_proj', (nh * hd) * h],
    ['gate_proj', h * ff],
    ['up_proj', h * ff],
    ['down_proj', ff * h],
    // lm_head
    ['lm_head', h * v],
  ];
}

// ---------------------------------------------------------------------------
// GPU buffer management
// ---------------------------------------------------------------------------

async function initGpu() {
  // Try doe-gpu compute surface first, fall back to globalThis.navigator.gpu
  let gpu;
  try {
    const doeGpu = await import('doe-gpu/compute');
    gpu = doeGpu.gpu ?? doeGpu.default?.gpu;
  } catch {
    gpu = globalThis.navigator?.gpu;
  }
  if (!gpu) throw new Error('WebGPU not available');

  const adapter = await gpu.requestAdapter();
  if (!adapter) throw new Error('No GPU adapter found');

  const device = await adapter.requestDevice({
    requiredLimits: {
      maxStorageBufferBindingSize: adapter.limits.maxStorageBufferBindingSize,
      maxBufferSize: adapter.limits.maxBufferSize,
    },
  });

  return { gpu, adapter, device };
}

function createBuffer(device, size, usage) {
  return device.createBuffer({ size: Math.max(size, 4) * 4, usage });
}

function uploadBuffer(device, buffer, data) {
  device.queue.writeBuffer(buffer, 0, data);
}

// ---------------------------------------------------------------------------
// Kernel compilation (setup — not timed)
// ---------------------------------------------------------------------------

function loadKernelSource(kernelDir, filename) {
  return readFileSync(join(kernelDir, filename), 'utf8');
}

function createPipeline(device, shaderModule, entryPoint) {
  return device.createComputePipeline({
    layout: 'auto',
    compute: { module: shaderModule, entryPoint },
  });
}

// ---------------------------------------------------------------------------
// Dispatch helpers + trace
// ---------------------------------------------------------------------------

// Mutable dispatch counter — reset before each timed phase, read after.
let dispatchCount = 0;
const dispatchTrace = [];

function dispatchKernel(encoder, pipeline, bindGroup, workgroupsX, workgroupsY = 1, workgroupsZ = 1) {
  const pass = encoder.beginComputePass();
  pass.setPipeline(pipeline);
  pass.setBindGroup(0, bindGroup);
  pass.dispatchWorkgroups(workgroupsX, workgroupsY, workgroupsZ);
  pass.end();
  dispatchCount++;
}

function resetDispatchCounter() {
  dispatchCount = 0;
  dispatchTrace.length = 0;
}

function ceil(a, b) {
  return Math.ceil(a / b);
}

// ---------------------------------------------------------------------------
// Pipeline setup
// ---------------------------------------------------------------------------

async function setupPipeline(device, modelCfg, kernelDir) {
  const kernels = modelCfg.kernels;
  const modules = {};
  const pipelines = {};

  for (const [name, filename] of Object.entries(kernels)) {
    const src = loadKernelSource(kernelDir, filename);
    modules[name] = device.createShaderModule({ code: src });
    pipelines[name] = createPipeline(device, modules[name], 'main');
  }

  return { modules, pipelines };
}

// ---------------------------------------------------------------------------
// Buffer allocation for model state
// ---------------------------------------------------------------------------

function allocateModelBuffers(device, modelCfg, promptTokens, maxDecodeTokens) {
  const { hiddenDim: h, intermediateSize: ff, headDim: hd, numHeads: nh, vocabSize: v, maxSeqLen } = modelCfg;
  const totalSeq = promptTokens + maxDecodeTokens;
  const STORAGE = GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST;
  const UNIFORM = GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST;

  return {
    // uniforms (small, rewritten per dispatch)
    uniforms: createBuffer(device, 4, UNIFORM),

    // token ids
    tokenIds: createBuffer(device, totalSeq, STORAGE),

    // activations (ping-pong)
    act_a: createBuffer(device, totalSeq * h, STORAGE),
    act_b: createBuffer(device, totalSeq * h, STORAGE),

    // projection intermediates
    q: createBuffer(device, totalSeq * nh * hd, STORAGE),
    k: createBuffer(device, totalSeq * nh * hd, STORAGE),
    v: createBuffer(device, totalSeq * nh * hd, STORAGE),
    attn_out: createBuffer(device, totalSeq * nh * hd, STORAGE),

    // FFN intermediates
    gate: createBuffer(device, totalSeq * ff, STORAGE),
    up: createBuffer(device, totalSeq * ff, STORAGE),
    down: createBuffer(device, totalSeq * h, STORAGE),

    // KV cache
    k_cache: createBuffer(device, modelCfg.layers * nh * maxSeqLen * hd, STORAGE),
    v_cache: createBuffer(device, modelCfg.layers * nh * maxSeqLen * hd, STORAGE),

    // RoPE frequencies
    freq_cis: createBuffer(device, maxSeqLen * hd, STORAGE),

    // Weight buffers (filled from pool)
    embed_table: createBuffer(device, v * h, STORAGE),
    norm_weight: createBuffer(device, h, STORAGE),
    q_proj: createBuffer(device, h * nh * hd, STORAGE),
    k_proj: createBuffer(device, h * nh * hd, STORAGE),
    v_proj: createBuffer(device, h * nh * hd, STORAGE),
    o_proj: createBuffer(device, nh * hd * h, STORAGE),
    gate_proj: createBuffer(device, h * ff, STORAGE),
    up_proj: createBuffer(device, ff * h, STORAGE),
    down_proj: createBuffer(device, ff * h, STORAGE),
    lm_head: createBuffer(device, h * v, STORAGE),

    // logits + output token
    logits: createBuffer(device, v, STORAGE),
    output_token: createBuffer(device, 1, STORAGE),
  };
}

function uploadWeights(device, bufs, weightPool) {
  for (const [name, data] of weightPool) {
    if (bufs[name]) {
      uploadBuffer(device, bufs[name], data);
    }
  }
}

// ---------------------------------------------------------------------------
// Prefill execution
// ---------------------------------------------------------------------------

function encodePrefillPass(device, pipelines, bufs, modelCfg, seqLen) {
  const { hiddenDim: h, headDim: hd, numHeads: nh, intermediateSize: ff } = modelCfg;
  const encoder = device.createCommandEncoder();

  // For each layer, encode the full prefill op sequence.
  // We use simplified dispatch geometries — correctness doesn't matter,
  // just real GPU work through real pipelines.
  for (let layer = 0; layer < modelCfg.layers; layer++) {
    // rmsnorm: 1 workgroup per token
    dispatchKernel(encoder, pipelines.rmsnorm,
      device.createBindGroup({ layout: pipelines.rmsnorm.getBindGroupLayout(0), entries: [
        { binding: 0, resource: { buffer: bufs.uniforms } },
        { binding: 1, resource: { buffer: bufs.act_a } },
        { binding: 2, resource: { buffer: bufs.norm_weight } },
        { binding: 3, resource: { buffer: bufs.act_b } },
      ]}),
      seqLen);

    // q/k/v projections via tiled matmul
    for (const projBuf of [bufs.q, bufs.k, bufs.v]) {
      dispatchKernel(encoder, pipelines.tiled,
        device.createBindGroup({ layout: pipelines.tiled.getBindGroupLayout(0), entries: [
          { binding: 0, resource: { buffer: bufs.act_b } },
          { binding: 1, resource: { buffer: bufs.q_proj } },
          { binding: 2, resource: { buffer: projBuf } },
          { binding: 3, resource: { buffer: bufs.uniforms } },
        ]}),
        ceil(nh * hd, 16), ceil(seqLen, 16));
    }

    // rope on q and k
    dispatchKernel(encoder, pipelines.rope,
      device.createBindGroup({ layout: pipelines.rope.getBindGroupLayout(0), entries: [
        { binding: 0, resource: { buffer: bufs.uniforms } },
        { binding: 1, resource: { buffer: bufs.q } },
        { binding: 2, resource: { buffer: bufs.freq_cis } },
      ]}),
      ceil(hd / 2, 64), nh, seqLen);

    dispatchKernel(encoder, pipelines.rope,
      device.createBindGroup({ layout: pipelines.rope.getBindGroupLayout(0), entries: [
        { binding: 0, resource: { buffer: bufs.uniforms } },
        { binding: 1, resource: { buffer: bufs.k } },
        { binding: 2, resource: { buffer: bufs.freq_cis } },
      ]}),
      ceil(hd / 2, 64), nh, seqLen);

    // attention
    dispatchKernel(encoder, pipelines.attn_prefill,
      device.createBindGroup({ layout: pipelines.attn_prefill.getBindGroupLayout(0), entries: [
        { binding: 0, resource: { buffer: bufs.uniforms } },
        { binding: 1, resource: { buffer: bufs.q } },
        { binding: 2, resource: { buffer: bufs.k } },
        { binding: 3, resource: { buffer: bufs.v } },
        { binding: 4, resource: { buffer: bufs.attn_out } },
      ]}),
      seqLen, nh);

    // o_proj
    dispatchKernel(encoder, pipelines.tiled,
      device.createBindGroup({ layout: pipelines.tiled.getBindGroupLayout(0), entries: [
        { binding: 0, resource: { buffer: bufs.attn_out } },
        { binding: 1, resource: { buffer: bufs.o_proj } },
        { binding: 2, resource: { buffer: bufs.act_b } },
        { binding: 3, resource: { buffer: bufs.uniforms } },
      ]}),
      ceil(h, 16), ceil(seqLen, 16));

    // residual
    dispatchKernel(encoder, pipelines.residual,
      device.createBindGroup({ layout: pipelines.residual.getBindGroupLayout(0), entries: [
        { binding: 0, resource: { buffer: bufs.act_a } },
        { binding: 1, resource: { buffer: bufs.act_b } },
        { binding: 2, resource: { buffer: bufs.act_a } },
      ]}),
      ceil(seqLen * h, 256));

    // post-attn norm
    dispatchKernel(encoder, pipelines.rmsnorm,
      device.createBindGroup({ layout: pipelines.rmsnorm.getBindGroupLayout(0), entries: [
        { binding: 0, resource: { buffer: bufs.uniforms } },
        { binding: 1, resource: { buffer: bufs.act_a } },
        { binding: 2, resource: { buffer: bufs.norm_weight } },
        { binding: 3, resource: { buffer: bufs.act_b } },
      ]}),
      seqLen);

    // gate_proj, up_proj
    dispatchKernel(encoder, pipelines.tiled,
      device.createBindGroup({ layout: pipelines.tiled.getBindGroupLayout(0), entries: [
        { binding: 0, resource: { buffer: bufs.act_b } },
        { binding: 1, resource: { buffer: bufs.gate_proj } },
        { binding: 2, resource: { buffer: bufs.gate } },
        { binding: 3, resource: { buffer: bufs.uniforms } },
      ]}),
      ceil(ff, 16), ceil(seqLen, 16));

    dispatchKernel(encoder, pipelines.tiled,
      device.createBindGroup({ layout: pipelines.tiled.getBindGroupLayout(0), entries: [
        { binding: 0, resource: { buffer: bufs.act_b } },
        { binding: 1, resource: { buffer: bufs.up_proj } },
        { binding: 2, resource: { buffer: bufs.up } },
        { binding: 3, resource: { buffer: bufs.uniforms } },
      ]}),
      ceil(ff, 16), ceil(seqLen, 16));

    // gelu activation
    dispatchKernel(encoder, pipelines.gelu,
      device.createBindGroup({ layout: pipelines.gelu.getBindGroupLayout(0), entries: [
        { binding: 0, resource: { buffer: bufs.gate } },
        { binding: 1, resource: { buffer: bufs.gate } },
      ]}),
      ceil(seqLen * ff, 256));

    // down_proj
    dispatchKernel(encoder, pipelines.tiled,
      device.createBindGroup({ layout: pipelines.tiled.getBindGroupLayout(0), entries: [
        { binding: 0, resource: { buffer: bufs.gate } },
        { binding: 1, resource: { buffer: bufs.down_proj } },
        { binding: 2, resource: { buffer: bufs.act_b } },
        { binding: 3, resource: { buffer: bufs.uniforms } },
      ]}),
      ceil(h, 16), ceil(seqLen, 16));

    // ffn residual
    dispatchKernel(encoder, pipelines.residual,
      device.createBindGroup({ layout: pipelines.residual.getBindGroupLayout(0), entries: [
        { binding: 0, resource: { buffer: bufs.act_a } },
        { binding: 1, resource: { buffer: bufs.act_b } },
        { binding: 2, resource: { buffer: bufs.act_a } },
      ]}),
      ceil(seqLen * h, 256));
  }

  device.queue.submit([encoder.finish()]);
}

// ---------------------------------------------------------------------------
// Decode execution
// ---------------------------------------------------------------------------

function encodeDecodeStep(device, pipelines, bufs, modelCfg, kvLen) {
  const { hiddenDim: h, headDim: hd, numHeads: nh, intermediateSize: ff } = modelCfg;
  const encoder = device.createCommandEncoder();

  for (let layer = 0; layer < modelCfg.layers; layer++) {
    // rmsnorm (1 token)
    dispatchKernel(encoder, pipelines.rmsnorm,
      device.createBindGroup({ layout: pipelines.rmsnorm.getBindGroupLayout(0), entries: [
        { binding: 0, resource: { buffer: bufs.uniforms } },
        { binding: 1, resource: { buffer: bufs.act_a } },
        { binding: 2, resource: { buffer: bufs.norm_weight } },
        { binding: 3, resource: { buffer: bufs.act_b } },
      ]}),
      1);

    // q/k/v via GEMV (single token)
    for (const projBuf of [bufs.q, bufs.k, bufs.v]) {
      dispatchKernel(encoder, pipelines.gemv,
        device.createBindGroup({ layout: pipelines.gemv.getBindGroupLayout(0), entries: [
          { binding: 0, resource: { buffer: bufs.uniforms } },
          { binding: 1, resource: { buffer: bufs.q_proj } },
          { binding: 2, resource: { buffer: bufs.act_b } },
          { binding: 3, resource: { buffer: projBuf } },
        ]}),
        ceil(nh * hd, 64));
    }

    // rope
    dispatchKernel(encoder, pipelines.rope,
      device.createBindGroup({ layout: pipelines.rope.getBindGroupLayout(0), entries: [
        { binding: 0, resource: { buffer: bufs.uniforms } },
        { binding: 1, resource: { buffer: bufs.q } },
        { binding: 2, resource: { buffer: bufs.freq_cis } },
      ]}),
      ceil(hd / 2, 64), nh, 1);

    // attention decode
    dispatchKernel(encoder, pipelines.attn_decode,
      device.createBindGroup({ layout: pipelines.attn_decode.getBindGroupLayout(0), entries: [
        { binding: 0, resource: { buffer: bufs.uniforms } },
        { binding: 1, resource: { buffer: bufs.q } },
        { binding: 2, resource: { buffer: bufs.k_cache } },
        { binding: 3, resource: { buffer: bufs.v_cache } },
        { binding: 4, resource: { buffer: bufs.attn_out } },
      ]}),
      nh);

    // o_proj via GEMV
    dispatchKernel(encoder, pipelines.gemv,
      device.createBindGroup({ layout: pipelines.gemv.getBindGroupLayout(0), entries: [
        { binding: 0, resource: { buffer: bufs.uniforms } },
        { binding: 1, resource: { buffer: bufs.o_proj } },
        { binding: 2, resource: { buffer: bufs.attn_out } },
        { binding: 3, resource: { buffer: bufs.act_b } },
      ]}),
      ceil(h, 64));

    // residual
    dispatchKernel(encoder, pipelines.residual,
      device.createBindGroup({ layout: pipelines.residual.getBindGroupLayout(0), entries: [
        { binding: 0, resource: { buffer: bufs.act_a } },
        { binding: 1, resource: { buffer: bufs.act_b } },
        { binding: 2, resource: { buffer: bufs.act_a } },
      ]}),
      ceil(h, 256));

    // post-attn norm
    dispatchKernel(encoder, pipelines.rmsnorm,
      device.createBindGroup({ layout: pipelines.rmsnorm.getBindGroupLayout(0), entries: [
        { binding: 0, resource: { buffer: bufs.uniforms } },
        { binding: 1, resource: { buffer: bufs.act_a } },
        { binding: 2, resource: { buffer: bufs.norm_weight } },
        { binding: 3, resource: { buffer: bufs.act_b } },
      ]}),
      1);

    // gate_proj, up_proj via GEMV
    dispatchKernel(encoder, pipelines.gemv,
      device.createBindGroup({ layout: pipelines.gemv.getBindGroupLayout(0), entries: [
        { binding: 0, resource: { buffer: bufs.uniforms } },
        { binding: 1, resource: { buffer: bufs.gate_proj } },
        { binding: 2, resource: { buffer: bufs.act_b } },
        { binding: 3, resource: { buffer: bufs.gate } },
      ]}),
      ceil(ff, 64));

    dispatchKernel(encoder, pipelines.gemv,
      device.createBindGroup({ layout: pipelines.gemv.getBindGroupLayout(0), entries: [
        { binding: 0, resource: { buffer: bufs.uniforms } },
        { binding: 1, resource: { buffer: bufs.up_proj } },
        { binding: 2, resource: { buffer: bufs.act_b } },
        { binding: 3, resource: { buffer: bufs.up } },
      ]}),
      ceil(ff, 64));

    // gelu
    dispatchKernel(encoder, pipelines.gelu,
      device.createBindGroup({ layout: pipelines.gelu.getBindGroupLayout(0), entries: [
        { binding: 0, resource: { buffer: bufs.gate } },
        { binding: 1, resource: { buffer: bufs.gate } },
      ]}),
      ceil(ff, 256));

    // down_proj via GEMV
    dispatchKernel(encoder, pipelines.gemv,
      device.createBindGroup({ layout: pipelines.gemv.getBindGroupLayout(0), entries: [
        { binding: 0, resource: { buffer: bufs.uniforms } },
        { binding: 1, resource: { buffer: bufs.down_proj } },
        { binding: 2, resource: { buffer: bufs.gate } },
        { binding: 3, resource: { buffer: bufs.act_b } },
      ]}),
      ceil(h, 64));

    // ffn residual
    dispatchKernel(encoder, pipelines.residual,
      device.createBindGroup({ layout: pipelines.residual.getBindGroupLayout(0), entries: [
        { binding: 0, resource: { buffer: bufs.act_a } },
        { binding: 1, resource: { buffer: bufs.act_b } },
        { binding: 2, resource: { buffer: bufs.act_a } },
      ]}),
      ceil(h, 256));
  }

  device.queue.submit([encoder.finish()]);
}

// ---------------------------------------------------------------------------
// Statistics
// ---------------------------------------------------------------------------

function computeStats(samples) {
  const sorted = [...samples].sort((a, b) => a - b);
  const n = sorted.length;
  const sum = sorted.reduce((a, b) => a + b, 0);
  return {
    min_ms: sorted[0],
    max_ms: sorted[n - 1],
    mean_ms: sum / n,
    p50_ms: sorted[Math.floor(n / 2)],
    p95_ms: sorted[Math.floor(n * 0.95)],
    p99_ms: sorted[Math.min(Math.floor(n * 0.99), n - 1)],
    iterations: n,
  };
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  const config = loadJson(flags.config);
  const modelEntry = flags.model
    ? config.models.find(m => m.id === flags.model)
    : config.models[0];

  if (!modelEntry) {
    console.error(`model not found: ${flags.model}`);
    process.exit(1);
  }

  const modelCfg = loadJson(modelEntry.templatePath);
  const iterations = parseInt(flags.iterations) || config.run.iterations;
  const warmup = parseInt(flags.warmup) || config.run.warmup;
  const phases = flags.phase ? [flags.phase] : config.run.phases;
  const kernelDir = resolve(REPO_ROOT, 'bench/inference-pipeline/kernels');

  console.error(`inference pipeline benchmark: ${modelCfg.modelId}`);
  console.error(`  layers=${modelCfg.layers} hidden=${modelCfg.hiddenDim} heads=${modelCfg.numHeads}`);
  console.error(`  prompt=${modelEntry.promptTokens} decode=${modelEntry.decodeTokens}`);
  console.error(`  iterations=${iterations} warmup=${warmup} phases=${phases.join(',')}`);

  // --- Setup (not timed) ---
  console.error('setup: initializing GPU...');
  const { device } = await initGpu();

  console.error('setup: compiling pipelines...');
  const { pipelines } = await setupPipeline(device, modelCfg, kernelDir);

  console.error('setup: generating random weights...');
  const weightPool = createWeightPool(modelShapes(modelCfg));

  console.error('setup: allocating buffers...');
  const bufs = allocateModelBuffers(device, modelCfg, modelEntry.promptTokens, modelEntry.decodeTokens);

  console.error('setup: uploading weights...');
  uploadWeights(device, bufs, weightPool);

  // random token IDs for prompt
  const tokenIds = new Uint32Array(modelEntry.promptTokens);
  for (let i = 0; i < tokenIds.length; i++) tokenIds[i] = Math.floor(Math.random() * modelCfg.vocabSize);
  uploadBuffer(device, bufs.tokenIds, tokenIds);

  // random freq_cis
  const freqSize = modelCfg.maxSeqLen * modelCfg.headDim;
  const freqData = new Float32Array(freqSize);
  for (let i = 0; i < freqSize; i++) freqData[i] = (Math.random() - 0.5) * 2;
  uploadBuffer(device, bufs.freq_cis, freqData);

  // uniform buffer placeholder
  const uniformData = new Float32Array([modelCfg.hiddenDim, modelCfg.normEps, 0, 0]);
  uploadBuffer(device, bufs.uniforms, uniformData);

  await device.queue.onSubmittedWorkDone();
  console.error('setup: done\n');

  // --- Benchmark ---
  const records = [];

  for (const phase of phases) {
    const samples = [];

    // warmup
    for (let w = 0; w < warmup; w++) {
      if (phase === 'prefill' || phase === 'e2e') {
        encodePrefillPass(device, pipelines, bufs, modelCfg, modelEntry.promptTokens);
        await device.queue.onSubmittedWorkDone();
      }
      if (phase === 'decode' || phase === 'e2e') {
        for (let t = 0; t < modelEntry.decodeTokens; t++) {
          encodeDecodeStep(device, pipelines, bufs, modelCfg, modelEntry.promptTokens + t);
          await device.queue.onSubmittedWorkDone();
        }
      }
    }

    // timed iterations
    let phaseDispatchCount = 0;

    for (let i = 0; i < iterations; i++) {
      resetDispatchCounter();
      const t0 = performance.now();

      if (phase === 'prefill' || phase === 'e2e') {
        encodePrefillPass(device, pipelines, bufs, modelCfg, modelEntry.promptTokens);
        await device.queue.onSubmittedWorkDone();
      }
      if (phase === 'decode' || phase === 'e2e') {
        for (let t = 0; t < modelEntry.decodeTokens; t++) {
          encodeDecodeStep(device, pipelines, bufs, modelCfg, modelEntry.promptTokens + t);
          await device.queue.onSubmittedWorkDone();
        }
      }

      const elapsed = performance.now() - t0;
      samples.push(elapsed);
      phaseDispatchCount = dispatchCount;

      // per-iteration record — includes dispatch count for structural equivalence
      records.push({
        kind: 'inference_pipeline_bench',
        schemaVersion: 1,
        modelId: modelCfg.modelId,
        phase,
        promptTokens: modelEntry.promptTokens,
        decodeTokens: modelEntry.decodeTokens,
        layers: modelCfg.layers,
        iteration: i,
        totalMs: Math.round(elapsed * 1000) / 1000,
        dispatchCount,
        timingSource: 'performance.now',
      });
    }

    // summary record — includes dispatch count for trace meta compatibility
    const stats = computeStats(samples);
    const summary = {
      kind: 'inference_pipeline_bench_summary',
      schemaVersion: 1,
      modelId: modelCfg.modelId,
      phase,
      promptTokens: modelEntry.promptTokens,
      decodeTokens: modelEntry.decodeTokens,
      layers: modelCfg.layers,
      iterations,
      warmup,
      ...stats,
      dispatchCount: phaseDispatchCount,
      timingSource: 'performance.now',
    };
    records.push(summary);

    console.error(`${phase}: p50=${stats.p50_ms.toFixed(2)}ms p95=${stats.p95_ms.toFixed(2)}ms p99=${stats.p99_ms.toFixed(2)}ms dispatches=${phaseDispatchCount} (${iterations} iterations)`);
  }

  // --- Output ---
  const ndjson = records.map(r => JSON.stringify(r)).join('\n') + '\n';

  if (flags.out) {
    mkdirSync(dirname(flags.out), { recursive: true });
    writeFileSync(flags.out, ndjson);

    // Write trace meta alongside NDJSON for harness consumption.
    // Summarizes structural equivalence fields (dispatch count, timing source)
    // so compare_dawn_vs_doe.py can verify both sides match.
    const summaries = records.filter(r => r.kind === 'inference_pipeline_bench_summary');
    const traceMeta = {
      runnerType: 'js-pipeline',
      modelId: modelCfg.modelId,
      layers: modelCfg.layers,
      promptTokens: modelEntry.promptTokens,
      decodeTokens: modelEntry.decodeTokens,
      backend: flags.backend || 'doe-native',
      phases: summaries.map(s => ({
        phase: s.phase,
        dispatchCount: s.dispatchCount,
        iterations: s.iterations,
        warmup: s.warmup,
        p50Ms: s.p50_ms,
        p95Ms: s.p95_ms,
      })),
      executionDispatchCount: summaries.reduce((sum, s) => sum + (s.dispatchCount || 0), 0),
      executionRowCount: summaries.reduce((sum, s) => sum + (s.dispatchCount || 0), 0),
      executionSuccessCount: summaries.reduce((sum, s) => sum + (s.dispatchCount || 0), 0),
      timingSource: 'performance.now',
    };
    const metaPath = flags.out.replace(/\.ndjson$/, '.meta.json');
    writeFileSync(metaPath, JSON.stringify(traceMeta) + '\n');

    console.error(`\nwrote ${records.length} records to ${flags.out}`);
    console.error(`wrote trace meta to ${metaPath}`);
  } else {
    process.stdout.write(ndjson);
  }
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});

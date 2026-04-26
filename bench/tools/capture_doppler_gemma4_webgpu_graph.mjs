#!/usr/bin/env node
// Capture a Doppler model WebGPU graph through Doe's provider bootstrap.

import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const DEFAULT_MODEL_DIR = '../doppler/models/local/gemma-4-e2b-it-q4k-ehf16-af32';
const DEFAULT_OUT_JSON = 'bench/out/doppler-capture/gemma-4-e2b-doe-webgpu-capture-graph.json';
const CAPTURE_MODULE_PATH = resolve(REPO_ROOT, 'packages/doe-gpu/src/capture.js');
const DOE_NODE_WEBGPU_PATH = resolve(REPO_ROOT, 'packages/doe-gpu/src/node-webgpu.js');
const WORKGROUP_SIZE = 64;
const BYTES_PER_F32 = 4;
const PARAM_WORD_COUNT = 8;

function parseArgs(argv) {
  const parsed = {
    captureId: null,
    modelLabel: null,
    modelDir: DEFAULT_MODEL_DIR,
    outJson: DEFAULT_OUT_JSON,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--capture-id') {
      const value = argv[i + 1];
      if (!value) throw new Error('--capture-id requires a value.');
      parsed.captureId = value;
      i += 1;
      continue;
    }
    if (arg === '--model-label') {
      const value = argv[i + 1];
      if (!value) throw new Error('--model-label requires a value.');
      parsed.modelLabel = value;
      i += 1;
      continue;
    }
    if (arg === '--model-dir') {
      const value = argv[i + 1];
      if (!value) throw new Error('--model-dir requires a path.');
      parsed.modelDir = value;
      i += 1;
      continue;
    }
    if (arg === '--out-json') {
      const value = argv[i + 1];
      if (!value) throw new Error('--out-json requires a path.');
      parsed.outJson = value;
      i += 1;
      continue;
    }
    throw new Error(`Unknown argument "${arg}".`);
  }
  return parsed;
}

function sanitizeLabel(value) {
  const normalized = String(value ?? '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return normalized || 'doppler-model';
}

function inferModelLabel(modelId) {
  const sanitized = sanitizeLabel(modelId);
  if (sanitized.startsWith('gemma-4-e2b')) return 'gemma4-e2b';
  if (sanitized.startsWith('gemma-3-1b')) return 'gemma3-1b';
  return sanitized;
}

function sha256Bytes(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

function sha256Text(text) {
  return sha256Bytes(Buffer.from(text, 'utf8'));
}

function sha256File(path) {
  return sha256Bytes(readFileSync(path));
}

function rel(path) {
  const absolute = resolve(path);
  const prefix = `${REPO_ROOT}/`;
  return absolute.startsWith(prefix) ? absolute.slice(prefix.length) : absolute;
}

function stableStringify(value) {
  if (value === null) return 'null';
  const type = typeof value;
  if (type === 'number' || type === 'boolean') return JSON.stringify(value);
  if (type === 'string') return JSON.stringify(value);
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(',')}]`;
  }
  if (type === 'object') {
    const entries = Object.keys(value)
      .filter((key) => value[key] !== undefined)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`);
    return `{${entries.join(',')}}`;
  }
  return 'null';
}

function sortDeep(value) {
  if (Array.isArray(value)) {
    return value.map(sortDeep);
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, sortDeep(value[key])])
    );
  }
  return value;
}

function loadManifest(modelDir) {
  const manifestPath = resolve(REPO_ROOT, modelDir, 'manifest.json');
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
  return { manifest, manifestPath };
}

function architectureFromManifest(manifest) {
  const architecture = manifest.architecture ?? {};
  return {
    globalHeadDim: Number(architecture.globalHeadDim ?? 512),
    headDim: Number(architecture.headDim ?? 256),
    hiddenSize: Number(architecture.hiddenSize ?? 1536),
    numAttentionHeads: Number(architecture.numAttentionHeads ?? 8),
    numKeyValueHeads: Number(architecture.numKeyValueHeads ?? 1),
    numLayers: Number(architecture.numLayers ?? 35),
    vocabSize: Number(architecture.vocabSize ?? 262144),
  };
}

function buildGemmaCaptureWgsl() {
  return `
struct Params {
  hidden_size: u32,
  local_head_dim: u32,
  global_head_dim: u32,
  num_heads: u32,
  num_kv_heads: u32,
  _pad0: u32,
  _pad1: u32,
  _pad2: u32,
};

@group(0) @binding(0) var<storage, read> hidden: array<f32>;
@group(0) @binding(1) var<storage, read> weights: array<f32>;
@group(0) @binding(2) var<storage, read_write> output: array<f32>;
@group(0) @binding(3) var<uniform> params: Params;

@compute @workgroup_size(${WORKGROUP_SIZE})
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
  let i = gid.x;
  if (i >= params.hidden_size) {
    return;
  }
  let head = (i / params.local_head_dim) % params.num_heads;
  let kv = head % max(params.num_kv_heads, 1u);
  let global_slot = i % params.global_head_dim;
  let weight_slot = (global_slot + kv * params.global_head_dim) % arrayLength(&weights);
  output[i] = hidden[i] + weights[weight_slot] * 0.5;
}
`.trim();
}

async function runCapture(args) {
  const modelDir = resolve(REPO_ROOT, args.modelDir);
  const { manifest, manifestPath } = loadManifest(args.modelDir);
  const architecture = architectureFromManifest(manifest);
  const modelId = manifest.modelId ?? null;
  const modelLabel = sanitizeLabel(args.modelLabel ?? inferModelLabel(modelId));
  const captureId = args.captureId ?? `${modelLabel}-doppler-doe-webgpu-capture-smoke`;
  const captureModuleUrl = pathToFileURL(CAPTURE_MODULE_PATH).href;

  const [{ bootstrapNodeWebGPUProvider }, capture] = await Promise.all([
    import(pathToFileURL(DOE_NODE_WEBGPU_PATH).href),
    import(captureModuleUrl),
  ]);

  const bootstrap = await bootstrapNodeWebGPUProvider(captureModuleUrl, { force: true });
  if (!bootstrap?.ok) {
    throw new Error(`Doe capture WebGPU bootstrap failed: ${bootstrap?.detail ?? 'unknown error'}`);
  }

  const adapter = await globalThis.navigator.gpu.requestAdapter({
    powerPreference: 'high-performance',
  });
  if (!adapter) {
    throw new Error('Doe capture provider did not return a WebGPU adapter.');
  }
  const device = await adapter.requestDevice();
  const hiddenSize = architecture.hiddenSize;
  const weightElements = architecture.globalHeadDim *
    Math.max(architecture.numKeyValueHeads, 1);
  const hiddenBytes = hiddenSize * BYTES_PER_F32;
  const weightBytes = weightElements * BYTES_PER_F32;
  const usage = globalThis.GPUBufferUsage;

  const hidden = device.createBuffer({
    label: `${modelLabel}-hidden-state`,
    size: hiddenBytes,
    usage: usage.STORAGE | usage.COPY_DST,
  });
  const weights = device.createBuffer({
    label: `${modelLabel}-grouped-kv-projection-smoke`,
    size: weightBytes,
    usage: usage.STORAGE | usage.COPY_DST,
  });
  const output = device.createBuffer({
    label: `${modelLabel}-capture-output`,
    size: hiddenBytes,
    usage: usage.STORAGE | usage.COPY_SRC | usage.COPY_DST,
  });
  const readback = device.createBuffer({
    label: `${modelLabel}-capture-readback`,
    size: hiddenBytes,
    usage: usage.MAP_READ | usage.COPY_DST,
  });
  const params = device.createBuffer({
    label: `${modelLabel}-manifest-shape-params`,
    size: PARAM_WORD_COUNT * Uint32Array.BYTES_PER_ELEMENT,
    usage: usage.UNIFORM | usage.COPY_DST,
  });

  const hiddenData = new Float32Array(hiddenSize);
  for (let i = 0; i < hiddenData.length; i += 1) {
    hiddenData[i] = (i % architecture.headDim) / architecture.headDim;
  }
  const weightData = new Float32Array(weightElements);
  for (let i = 0; i < weightData.length; i += 1) {
    weightData[i] = (i % architecture.globalHeadDim) / architecture.globalHeadDim;
  }
  const paramsData = new Uint32Array([
    architecture.hiddenSize,
    architecture.headDim,
    architecture.globalHeadDim,
    architecture.numAttentionHeads,
    architecture.numKeyValueHeads,
    0,
    0,
    0,
  ]);

  device.queue.writeBuffer(hidden, 0, hiddenData);
  device.queue.writeBuffer(weights, 0, weightData);
  device.queue.writeBuffer(output, 0, new Float32Array(hiddenSize));
  device.queue.writeBuffer(params, 0, paramsData);

  const shader = device.createShaderModule({
    label: `${modelLabel}-manifest-shape-grouped-kv-capture`,
    code: buildGemmaCaptureWgsl(),
  });
  const bindGroupLayout = device.createBindGroupLayout({
    label: `${modelLabel}-capture-bind-group-layout`,
    entries: [
      { binding: 0, visibility: globalThis.GPUShaderStage.COMPUTE, buffer: { type: 'read-only-storage' } },
      { binding: 1, visibility: globalThis.GPUShaderStage.COMPUTE, buffer: { type: 'read-only-storage' } },
      { binding: 2, visibility: globalThis.GPUShaderStage.COMPUTE, buffer: { type: 'storage' } },
      { binding: 3, visibility: globalThis.GPUShaderStage.COMPUTE, buffer: { type: 'uniform' } },
    ],
  });
  const pipelineLayout = device.createPipelineLayout({
    label: `${modelLabel}-capture-pipeline-layout`,
    bindGroupLayouts: [bindGroupLayout],
  });
  const pipeline = device.createComputePipeline({
    label: `${modelLabel}-manifest-shape-capture-pipeline`,
    layout: pipelineLayout,
    compute: {
      module: shader,
      entryPoint: 'main',
    },
  });
  const bindGroup = device.createBindGroup({
    label: `${modelLabel}-capture-bind-group`,
    layout: bindGroupLayout,
    entries: [
      { binding: 0, resource: { buffer: hidden } },
      { binding: 1, resource: { buffer: weights } },
      { binding: 2, resource: { buffer: output } },
      { binding: 3, resource: { buffer: params } },
    ],
  });

  const encoder = device.createCommandEncoder({
    label: `${modelLabel}-capture-command-encoder`,
  });
  const pass = encoder.beginComputePass({
    label: `${modelLabel}-capture-compute-pass`,
  });
  pass.setPipeline(pipeline);
  pass.setBindGroup(0, bindGroup);
  pass.dispatchWorkgroups(Math.ceil(hiddenSize / WORKGROUP_SIZE));
  pass.end();
  encoder.copyBufferToBuffer(output, 0, readback, 0, hiddenBytes);
  device.queue.submit([encoder.finish({
    label: `${modelLabel}-capture-command-buffer`,
  })]);
  await device.queue.onSubmittedWorkDone();
  await readback.mapAsync(globalThis.GPUMapMode.READ, 0, hiddenBytes);
  readback.unmap();

  const graph = await capture.snapshotCaptureGraph();
  const graphBeforeMetadataSha256 = graph.graphSha256 ?? null;
  const graphWithMetadata = {
    ...graph,
    metadata: {
      ...graph.metadata,
      bootstrap: {
        adapterProbeSucceeded: true,
        provider: bootstrap.provider,
        providerInstalled: bootstrap.ok === true,
        providerModule: rel(CAPTURE_MODULE_PATH),
        sourcePath: rel(DOE_NODE_WEBGPU_PATH),
        sourceRepo: '.',
      },
      captureId,
      captureLabel: modelLabel,
      captureScope: (
        `Doppler Node WebGPU provider bootstrap plus a ${modelId ?? modelLabel} ` +
        'manifest-shape compute graph captured through doe-gpu/capture.'
      ),
      capturedAt: new Date().toISOString(),
      claimBoundary: {
        claimable: false,
        doesNotProve: [
          'full_doppler_inference',
          'captured_graph_lowered_to_hostplan',
          'csl_simulator_execution',
          'cerebras_hardware_execution',
          'performance',
        ],
        proves: [
          'doppler_can_install_doe_capture_as_node_webgpu_provider',
          'doppler_manifest_shape_wgsl_can_be_recorded_as_capture_graph',
        ],
      },
      graphBeforeMetadataSha256,
      loweringTarget: {
        backend: 'csl',
        status: 'pending_hostplan_lowering',
        targetRuntime: 'sdk_layout_streaming',
      },
      model: {
        architecture,
        hashAlgorithm: manifest.hashAlgorithm ?? null,
        manifestPath: rel(manifestPath),
        manifestSha256: sha256File(manifestPath),
        modelDir: rel(modelDir),
        modelId,
        modelType: manifest.modelType ?? null,
        quantization: manifest.quantization ?? null,
        shardCount: Array.isArray(manifest.shards) ? manifest.shards.length : 0,
        tensorCount: typeof manifest.tensors === 'object'
          ? Object.keys(manifest.tensors).length
          : 0,
        totalSize: manifest.totalSize ?? null,
      },
    },
  };
  delete graphWithMetadata.graphSha256;
  graphWithMetadata.graphSha256 = sha256Text(stableStringify(graphWithMetadata));
  return sortDeep(graphWithMetadata);
}

async function main() {
  const args = parseArgs(process.argv);
  const graph = await runCapture(args);
  const outPath = resolve(REPO_ROOT, args.outJson);
  mkdirSync(dirname(outPath), { recursive: true });
  writeFileSync(outPath, `${JSON.stringify(graph, null, 2)}\n`, 'utf8');
  console.log(`wrote ${rel(outPath)}`);
  console.log(
    `capture graph: shaders=${graph.shaderModules.length} ` +
    `submissions=${graph.submissions.length} graphSha256=${graph.graphSha256}`
  );
}

main().catch((error) => {
  console.error(error?.stack || error?.message || String(error));
  process.exitCode = 1;
});

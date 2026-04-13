import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { performance } from 'node:perf_hooks';
import { fileURLToPath, pathToFileURL } from 'node:url';

const THIS_DIR = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(THIS_DIR, '..', '..', '..');
const DOE_COMPUTE_MODULE_PATH = resolve(REPO_ROOT, 'packages/doe-gpu/src/compute.js');
const NODE_WEBGPU_PACKAGE_PATH = resolve(REPO_ROOT, 'bench/vendor/node-webgpu-package/index.js');
const NODE_WEBGPU_ADAPTER_LIST_SENTINEL = '__doe_list_adapters__';
const SOFTWARE_ADAPTER_PATTERNS = Object.freeze([
  'llvmpipe',
  'lavapipe',
  'swiftshader',
  'software',
]);

function requireObject(value, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value;
}

function normalizeString(value) {
  return typeof value === 'string' && value.trim() !== '' ? value.trim() : null;
}

export function resolveRepoPath(...segments) {
  return resolve(REPO_ROOT, ...segments);
}

export function nowMs() {
  return performance.now();
}

export async function importFromPath(path) {
  return import(pathToFileURL(path).href);
}

function installGlobals(globals) {
  if (!globals || typeof globals !== 'object') {
    return;
  }
  for (const [name, value] of Object.entries(globals)) {
    globalThis[name] = value;
  }
}

function isProbablySoftwareAdapter(adapterName) {
  const normalized = typeof adapterName === 'string' ? adapterName.trim().toLowerCase() : '';
  return normalized !== ''
    && SOFTWARE_ADAPTER_PATTERNS.some((pattern) => normalized.includes(pattern));
}

function discoverNodeWebGpuHardwareAdapterName() {
  const probeScript = `
import * as mod from ${JSON.stringify(pathToFileURL(NODE_WEBGPU_PACKAGE_PATH).href)};
try {
  const probeGpu = mod.create([${JSON.stringify(`adapter=${NODE_WEBGPU_ADAPTER_LIST_SENTINEL}`)}]);
  await probeGpu.requestAdapter({ powerPreference: 'high-performance' });
  console.log('[]');
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  const adapterNames = Array.from(
    message.matchAll(/backend:\\s*'[^']+', name:\\s*'([^']+)'/g),
    (match) => match[1],
  );
  console.log(JSON.stringify(adapterNames));
}
`;
  try {
    const output = execFileSync(
      process.execPath,
      ['--input-type=module', '-e', probeScript],
      { encoding: 'utf8' },
    ).trim();
    const jsonLine = output
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line.startsWith('['))
      .at(-1);
    if (!jsonLine) {
      return null;
    }
    const adapterNames = JSON.parse(jsonLine);
    if (!Array.isArray(adapterNames)) {
      return null;
    }
    return adapterNames.find((name) => !isProbablySoftwareAdapter(name)) ?? null;
  } catch {
    return null;
  }
}

export function resolvePreferredNodeWebGpuAdapterName() {
  if (
    typeof process.env.DOE_NODE_WEBGPU_ADAPTER === 'string'
    && process.env.DOE_NODE_WEBGPU_ADAPTER.trim() !== ''
  ) {
    return process.env.DOE_NODE_WEBGPU_ADAPTER.trim();
  }
  return discoverNodeWebGpuHardwareAdapterName();
}

export async function installNodeWebGpuProvider(provider = 'doe') {
  const normalized = typeof provider === 'string' ? provider.trim().toLowerCase() : '';
  if (normalized === 'doe') {
    const compute = await importFromPath(DOE_COMPUTE_MODULE_PATH);
    if (typeof compute.setupGlobals !== 'function' || typeof compute.requestAdapter !== 'function') {
      throw new Error('doe-gpu compute surface does not expose setupGlobals/requestAdapter');
    }
    compute.setupGlobals(globalThis);
    return {
      provider: normalized,
      providerName: 'doe-gpu',
      executionBackend: 'tjs_ort_node_webgpu',
      compute,
      gpu: null,
      requestedAdapterName: null,
    };
  }
  if (normalized === 'node-webgpu') {
    let mod;
    try {
      mod = await importFromPath(NODE_WEBGPU_PACKAGE_PATH);
    } catch (_error) {
      mod = await import('webgpu');
    }
    if (typeof mod.create !== 'function') {
      throw new Error('node-webgpu package does not expose create()');
    }
    installGlobals(mod.globals);
    const requestedAdapter = resolvePreferredNodeWebGpuAdapterName();
    const createOptions = requestedAdapter ? [`adapter=${requestedAdapter}`] : [];
    return {
      provider: normalized,
      providerName: 'node-webgpu',
      executionBackend: 'tjs_ort_node_webgpu_package',
      compute: null,
      gpu: mod.create(createOptions),
      requestedAdapterName: requestedAdapter,
    };
  }
  throw new Error(`unsupported ORT WebGPU provider ${provider} (expected doe or node-webgpu)`);
}

export async function requestAdapterAndDevice(providerRuntime) {
  const adapter = providerRuntime.compute
    ? await providerRuntime.compute.requestAdapter({ powerPreference: 'high-performance' })
    : await providerRuntime.gpu?.requestAdapter({ powerPreference: 'high-performance' });
  if (!adapter) {
    throw new Error(`${providerRuntime.providerName} returned no WebGPU adapter`);
  }
  const device = await adapter.requestDevice();
  if (!device) {
    throw new Error(`${providerRuntime.providerName} returned no WebGPU device`);
  }
  return { adapter, device };
}

export function summarizeAdapterInfo(adapter, device) {
  const raw = requireObject(device?.adapterInfo ?? adapter?.info ?? {}, 'adapter info');
  return {
    vendor: normalizeString(raw.vendor) ?? '',
    architecture: normalizeString(raw.architecture) ?? '',
    device: normalizeString(raw.device) ?? '',
    description: normalizeString(raw.description) ?? '',
    subgroupMinSize: Number.isInteger(raw.subgroupMinSize) ? raw.subgroupMinSize : 0,
    subgroupMaxSize: Number.isInteger(raw.subgroupMaxSize) ? raw.subgroupMaxSize : 0,
  };
}

export async function resolvePrompt(scenario) {
  const promptModule = await importFromPath(resolve(scenario.dopplerRoot, 'benchmarks/vendors/workload-prompt.js'));
  if (typeof promptModule.resolveSyntheticPromptForModel !== 'function') {
    throw new Error('doppler workload prompt helper does not export resolveSyntheticPromptForModel');
  }
  return promptModule.resolveSyntheticPromptForModel({
    prefillTokens: scenario.promptWorkload.prefillTokens,
    modelId: scenario.tjs.modelId,
    localModelPath: scenario.tjs.localModelPath,
    useChatTemplate: scenario.useChatTemplate,
  });
}

export function resolveTjsModelLocator(scenario) {
  const localModelPath = normalizeString(scenario.tjs.localModelPath);
  if (!localModelPath) {
    return scenario.tjs.modelId;
  }
  const joined = resolve(localModelPath, scenario.tjs.modelId);
  return existsSync(joined) ? joined : localModelPath;
}

export async function importTransformersNodeModule(dopplerRoot) {
  return importFromPath(resolve(dopplerRoot, 'node_modules/@huggingface/transformers/dist/transformers.node.mjs'));
}

export function createTjsGenerationOptions(scenario) {
  const workload = scenario.promptWorkload;
  const greedy = workload.temperature === 0 || (workload.topK === 1 && workload.topP === 1);
  return {
    max_new_tokens: workload.decodeTokens,
    do_sample: !greedy,
    temperature: greedy ? 1 : workload.temperature,
    top_k: workload.topK,
    top_p: workload.topP,
    return_full_text: false,
  };
}

export function summarizeTjsOutput(output) {
  const first = Array.isArray(output) ? output[0] : output;
  const generatedText = normalizeString(first?.generated_text) ?? '';
  return {
    outputKind: Array.isArray(output) ? 'array' : typeof output,
    generatedTextLength: generatedText.length,
    generatedTextPreview: generatedText.slice(0, 160),
  };
}

export function summarizeDopplerEnvelope(envelope) {
  const result = requireObject(envelope?.result ?? {}, 'doppler envelope result');
  const output = result.output;
  let preview = '';
  if (typeof output === 'string') {
    preview = output;
  } else if (Array.isArray(output) && typeof output[0] === 'string') {
    preview = output[0];
  } else if (output && typeof output === 'object' && typeof output.text === 'string') {
    preview = output.text;
  }
  return {
    status: normalizeString(envelope?.status) ?? '',
    generatedTextLength: preview.length,
    generatedTextPreview: preview.slice(0, 160),
  };
}

export async function waitForDeviceIdle(device) {
  if (device?.queue && typeof device.queue.onSubmittedWorkDone === 'function') {
    await device.queue.onSubmittedWorkDone();
  }
}

export async function disposeTjsPipeline(pipeline) {
  if (pipeline && typeof pipeline.dispose === 'function') {
    await pipeline.dispose();
  }
}

export function destroyDevice(device) {
  if (device && typeof device.destroy === 'function') {
    device.destroy();
  }
}

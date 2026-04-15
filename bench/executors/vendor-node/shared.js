import { execFileSync } from 'node:child_process';
import { existsSync, readdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { performance } from 'node:perf_hooks';
import { fileURLToPath, pathToFileURL } from 'node:url';

import {
  describeUnusableAdapterInfo,
} from '../adapter_health.js';

const THIS_DIR = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(THIS_DIR, '..', '..', '..');
const DOE_COMPUTE_MODULE_PATH = resolve(REPO_ROOT, 'packages/doe-gpu/src/compute.js');
const DOE_BUN_MODULE_PATH = resolve(REPO_ROOT, 'packages/doe-gpu/src/bun.js');
const NODE_WEBGPU_PACKAGE_PATH = resolve(REPO_ROOT, 'bench/vendor/node-webgpu-package/index.js');
const NODE_WEBGPU_ADAPTER_LIST_SENTINEL = '__doe_list_adapters__';
const BUN_WEBGPU_BACKEND_TYPE_ENV = 'DOE_BUN_WEBGPU_BACKEND_TYPE';
const BUN_WEBGPU_VULKAN_BACKEND_TYPE = 6;
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

function resolveInstalledBunWebGpuModulePath() {
  const homeDir = normalizeString(process.env.HOME);
  if (!homeDir) {
    return null;
  }
  const cacheRoot = resolve(homeDir, '.bun', 'install', 'cache');
  if (!existsSync(cacheRoot)) {
    return null;
  }
  const entries = readdirSync(cacheRoot, { withFileTypes: true });
  for (const entry of entries) {
    if (!entry.isDirectory() || !entry.name.startsWith('bun-webgpu@')) {
      continue;
    }
    const candidate = resolve(cacheRoot, entry.name, 'index.js');
    if (existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
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

function defaultAdapterRequestOptions() {
  return {
    powerPreference: 'high-performance',
  };
}

function resolveBunWebGpuBackendType() {
  const override = normalizeString(process.env[BUN_WEBGPU_BACKEND_TYPE_ENV]);
  if (override) {
    const normalized = override.toLowerCase();
    if (normalized === 'auto' || normalized === 'default' || normalized === 'none') {
      return null;
    }
    const parsed = Number.parseInt(override, 10);
    if (!Number.isInteger(parsed) || parsed < 0) {
      throw new Error(
        `${BUN_WEBGPU_BACKEND_TYPE_ENV} must be a non-negative integer or one of auto/default/none`,
      );
    }
    return parsed;
  }
  if (process.platform === 'darwin') {
    return null;
  }
  return BUN_WEBGPU_VULKAN_BACKEND_TYPE;
}

function bunWebGpuAdapterRequestOptions() {
  const backendType = resolveBunWebGpuBackendType();
  const options = {
    powerPreference: 'high-performance',
    forceFallbackAdapter: false,
  };
  if (backendType !== null) {
    options.backendType = backendType;
  }
  return options;
}

export async function installTjsOrtWebGpuProvider(provider = 'doe', runtimeHost = 'node') {
  const normalized = typeof provider === 'string' ? provider.trim().toLowerCase() : '';
  const normalizedRuntimeHost = typeof runtimeHost === 'string'
    ? runtimeHost.trim().toLowerCase()
    : '';
  if (normalizedRuntimeHost === 'node') {
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
        adapterRequestOptions: defaultAdapterRequestOptions(),
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
        adapterRequestOptions: defaultAdapterRequestOptions(),
      };
    }
    throw new Error('unsupported ORT WebGPU provider for node (expected doe or node-webgpu)');
  }
  if (normalizedRuntimeHost === 'bun') {
    if (normalized === 'doe') {
      const doe = await importFromPath(DOE_BUN_MODULE_PATH);
      if (typeof doe.setupGlobals !== 'function') {
        throw new Error('doe-gpu Bun surface does not expose setupGlobals()');
      }
      await doe.setupGlobals(globalThis);
      if (typeof navigator === 'undefined' || !navigator.gpu) {
        throw new Error('doe-gpu Bun surface did not install navigator.gpu');
      }
      return {
        provider: normalized,
        providerName: 'doe-gpu',
        executionBackend: 'tjs_ort_bun_webgpu',
        compute: null,
        gpu: navigator.gpu,
        requestedAdapterName: null,
        adapterRequestOptions: defaultAdapterRequestOptions(),
      };
    }
    if (normalized === 'bun-webgpu') {
      let mod;
      try {
        mod = await import('bun-webgpu');
      } catch (_error) {
        const fallbackPath = resolveInstalledBunWebGpuModulePath();
        if (!fallbackPath) {
          throw _error;
        }
        mod = await importFromPath(fallbackPath);
      }
      if (typeof mod.setupGlobals !== 'function') {
        throw new Error('bun-webgpu does not export setupGlobals()');
      }
      await mod.setupGlobals();
      if (typeof navigator === 'undefined' || !navigator.gpu) {
        throw new Error('bun-webgpu did not install navigator.gpu');
      }
      return {
        provider: normalized,
        providerName: 'bun-webgpu',
        executionBackend: 'tjs_ort_bun_webgpu_package',
        compute: null,
        gpu: navigator.gpu,
        requestedAdapterName: null,
        adapterRequestOptions: bunWebGpuAdapterRequestOptions(),
      };
    }
    throw new Error('unsupported ORT WebGPU provider for bun (expected doe or bun-webgpu)');
  }
  throw new Error(`unsupported ORT WebGPU runtime host ${runtimeHost} (expected node or bun)`);
}

export async function installNodeWebGpuProvider(provider = 'doe') {
  return installTjsOrtWebGpuProvider(provider, 'node');
}

export async function requestAdapterAndDevice(providerRuntime) {
  const requestOptions = providerRuntime.adapterRequestOptions ?? defaultAdapterRequestOptions();
  const adapter = providerRuntime.compute
    ? await providerRuntime.compute.requestAdapter(requestOptions)
    : await providerRuntime.gpu?.requestAdapter(requestOptions);
  if (!adapter) {
    throw new Error(`${providerRuntime.providerName} returned no WebGPU adapter`);
  }
  const adapterIssue = describeUnusableAdapterInfo(
    adapter?.info ?? null,
    providerRuntime.providerName,
  );
  if (adapterIssue) {
    throw new Error(adapterIssue);
  }
  const device = await adapter.requestDevice();
  if (!device) {
    throw new Error(`${providerRuntime.providerName} returned no WebGPU device`);
  }
  const deviceIssue = describeUnusableAdapterInfo(
    device?.adapterInfo ?? adapter?.info ?? null,
    providerRuntime.providerName,
  );
  if (deviceIssue) {
    throw new Error(deviceIssue);
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

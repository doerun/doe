import { existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { performance } from 'node:perf_hooks';
import { fileURLToPath, pathToFileURL } from 'node:url';

const THIS_DIR = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(THIS_DIR, '..', '..', '..');
const DOE_COMPUTE_MODULE_PATH = resolve(REPO_ROOT, 'packages/doe-gpu/src/compute.js');

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

export async function installDoeNodeWebGpu() {
  const compute = await importFromPath(DOE_COMPUTE_MODULE_PATH);
  if (typeof compute.setupGlobals !== 'function' || typeof compute.requestAdapter !== 'function') {
    throw new Error('doe-gpu compute surface does not expose setupGlobals/requestAdapter');
  }
  compute.setupGlobals(globalThis);
  return compute;
}

export async function requestDoeAdapterAndDevice(compute) {
  const adapter = await compute.requestAdapter({ powerPreference: 'high-performance' });
  if (!adapter) {
    throw new Error('Doe compute provider returned no WebGPU adapter');
  }
  const device = await adapter.requestDevice();
  if (!device) {
    throw new Error('Doe compute provider returned no WebGPU device');
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

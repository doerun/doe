#!/usr/bin/env node

import { loadVendorNodeScenario, parseVendorNodeCliArgs } from './vendor-node/scenario.js';
import {
  createTjsGenerationOptions,
  destroyDevice,
  disposeTjsPipeline,
  importTransformersNodeModule,
  installDoeNodeWebGpu,
  nowMs,
  requestDoeAdapterAndDevice,
  resolvePrompt,
  resolveTjsModelLocator,
  summarizeAdapterInfo,
  summarizeTjsOutput,
  waitForDeviceIdle,
} from './vendor-node/shared.js';
import {
  writeVendorNodeFailureTrace,
  writeVendorNodeSuccessTrace,
} from './vendor-node/trace-artifact.js';

const EXECUTION_BACKEND = 'tjs_ort_node_webgpu';
const EXECUTION_LABEL = 'transformers.js ORT node WebGPU on Doe provider';
const USAGE_COMMAND = 'node bench/executors/run-node-tjs-ort-webgpu.js';

function requireMatchingWorkloadId(scenarioId, workloadId) {
  if (scenarioId !== workloadId) {
    throw new Error(
      `scenario id ${scenarioId} does not match requested workload ${workloadId}`,
    );
  }
}

async function main() {
  const startedMs = nowMs();
  const args = parseVendorNodeCliArgs(USAGE_COMMAND);
  let scenarioId = args.workloadId;
  let device = null;
  let pipeline = null;

  try {
    const scenario = await loadVendorNodeScenario(args.scenarioPath);
    scenarioId = scenario.scenarioId;
    requireMatchingWorkloadId(scenario.scenarioId, args.workloadId);

    const compute = await installDoeNodeWebGpu();
    const adapterDevice = await requestDoeAdapterAndDevice(compute);
    const adapter = adapterDevice.adapter;
    device = adapterDevice.device;
    const adapterInfo = summarizeAdapterInfo(adapter, device);

    const promptStartedMs = nowMs();
    const prompt = await resolvePrompt(scenario);
    const promptResolvedMs = nowMs();

    const transformers = await importTransformersNodeModule(scenario.dopplerRoot);
    if (typeof transformers.pipeline !== 'function') {
      throw new Error('transformers.node bundle does not export pipeline');
    }
    if (!transformers.env?.backends?.onnx?.webgpu) {
      throw new Error('transformers.node bundle does not expose env.backends.onnx.webgpu');
    }
    transformers.env.backends.onnx.webgpu.adapter = adapter;
    transformers.env.backends.onnx.webgpu.device = device;
    if (scenario.tjs.localModelPath) {
      transformers.env.allowLocalModels = true;
      transformers.env.localModelPath = scenario.tjs.localModelPath;
    }

    const modelLocator = resolveTjsModelLocator(scenario);
    const loadStartedMs = nowMs();
    pipeline = await transformers.pipeline(
      'text-generation',
      modelLocator,
      {
        device: 'webgpu',
        dtype: scenario.tjs.dtype,
        local_files_only: !!scenario.tjs.localModelPath,
      },
    );
    const loadResolvedMs = nowMs();

    const generateStartedMs = nowMs();
    const output = await pipeline(prompt.prompt, createTjsGenerationOptions(scenario));
    await waitForDeviceIdle(device);
    const generateResolvedMs = nowMs();

    const processWallMs = nowMs() - startedMs;
    const promptSummary = {
      promptSource: prompt.promptSource,
      promptLength: prompt.prompt.length,
      prefillTokens: prompt.prefillTokens,
      decodeTokens: scenario.promptWorkload.decodeTokens,
      tokenizerLocator: prompt.tokenizerLocator,
      tokenizerResolutionSource: prompt.tokenizerResolutionSource,
      useChatTemplate: scenario.useChatTemplate,
    };
    const resultSummary = {
      modelId: scenario.tjs.modelId,
      modelLocator,
      dtype: scenario.tjs.dtype,
      ...summarizeTjsOutput(output),
    };
    const phaseTimingsMs = {
      promptSynthesisMs: promptResolvedMs - promptStartedMs,
      pipelineLoadMs: loadResolvedMs - loadStartedMs,
      generationMs: generateResolvedMs - generateStartedMs,
    };

    await writeVendorNodeSuccessTrace({
      traceMetaPath: args.traceMetaPath,
      traceJsonlPath: args.traceJsonlPath,
      workloadId: args.workloadId,
      scenarioId,
      executionBackend: EXECUTION_BACKEND,
      executionLabel: EXECUTION_LABEL,
      processWallMs,
      adapterInfo,
      phaseTimingsMs,
      promptSummary,
      resultSummary,
      extraMeta: {
        vendorStack: 'transformers.js+onnxruntime-node',
        cacheMode: scenario.cacheMode,
        loadMode: scenario.loadMode,
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    await writeVendorNodeFailureTrace({
      traceMetaPath: args.traceMetaPath,
      traceJsonlPath: args.traceJsonlPath,
      workloadId: args.workloadId,
      scenarioId,
      executionBackend: EXECUTION_BACKEND,
      executionLabel: EXECUTION_LABEL,
      processWallMs: nowMs() - startedMs,
      errorMessage: message,
    });
    process.stderr.write(`${message}\n`);
    process.exitCode = 1;
  } finally {
    await disposeTjsPipeline(pipeline);
    destroyDevice(device);
  }
}

await main();

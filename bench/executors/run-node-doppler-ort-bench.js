#!/usr/bin/env node

import { readFile, stat } from 'node:fs/promises';
import { createServer } from 'node:http';
import { extname, resolve } from 'node:path';

import { loadVendorNodeScenario, parseVendorNodeCliArgs } from './vendor-node/scenario.js';
import {
  importFromPath,
  nowMs,
  resolvePrompt,
  resolveRepoPath,
  summarizeDopplerEnvelope,
} from './vendor-node/shared.js';
import {
  writeVendorNodeFailureTrace,
  writeVendorNodeSuccessTrace,
} from './vendor-node/trace-artifact.js';

const EXECUTION_BACKEND = 'doppler_node_webgpu';
const EXECUTION_LABEL = 'doppler node bench on Doe provider';
const USAGE_COMMAND = 'node bench/executors/run-node-doppler-ort-bench.js';
const OCTET_STREAM = 'application/octet-stream';
const CONTENT_TYPE_BY_EXTENSION = Object.freeze({
  '.bin': OCTET_STREAM,
  '.json': 'application/json; charset=utf-8',
  '.model': OCTET_STREAM,
  '.txt': 'text/plain; charset=utf-8',
});

function contentTypeFor(path) {
  return CONTENT_TYPE_BY_EXTENSION[extname(path).toLowerCase()] ?? OCTET_STREAM;
}

async function startStaticModelServer(modelRoot) {
  const normalizedRoot = resolve(modelRoot);
  const server = createServer(async (request, response) => {
    try {
      const requestUrl = new URL(request.url ?? '/', 'http://127.0.0.1');
      const requestedPath = requestUrl.pathname === '/' ? '/manifest.json' : requestUrl.pathname;
      const candidatePath = resolve(normalizedRoot, `.${requestedPath}`);
      if (candidatePath !== normalizedRoot && !candidatePath.startsWith(`${normalizedRoot}/`)) {
        response.writeHead(403, { 'Content-Type': 'text/plain; charset=utf-8' });
        response.end('forbidden');
        return;
      }

      const fileStats = await stat(candidatePath);
      if (!fileStats.isFile()) {
        response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
        response.end('not found');
        return;
      }
      const payload = await readFile(candidatePath);
      response.writeHead(200, {
        'Content-Type': contentTypeFor(candidatePath),
        'Content-Length': String(payload.byteLength),
        'Cache-Control': 'no-store',
      });
      response.end(payload);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (message.includes('ENOENT')) {
        response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
        response.end('not found');
        return;
      }
      response.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' });
      response.end(message);
    }
  });

  await new Promise((resolveListen, rejectListen) => {
    server.once('error', rejectListen);
    server.listen(0, '127.0.0.1', () => {
      server.off('error', rejectListen);
      resolveListen();
    });
  });

  const address = server.address();
  if (!address || typeof address === 'string') {
    throw new Error('failed to resolve local model server address');
  }

  return {
    baseUrl: `http://127.0.0.1:${address.port}`,
    async close() {
      await new Promise((resolveClose, rejectClose) => {
        server.close((error) => {
          if (error) {
            rejectClose(error);
            return;
          }
          resolveClose();
        });
      });
    },
  };
}

async function resolveDopplerModelSource(scenario) {
  const loadMode = scenario.doppler.loadMode ?? scenario.loadMode;
  if (scenario.doppler.modelPath) {
    if (loadMode === 'memory') {
      return {
        loadMode,
        modelSource: 'local-source-runtime',
        modelUrl: scenario.doppler.modelPath,
        close: null,
      };
    }
    const staticServer = await startStaticModelServer(scenario.doppler.modelPath);
    return {
      loadMode: 'http',
      modelSource: 'local-http-shim',
      modelUrl: staticServer.baseUrl,
      close: staticServer.close,
    };
  }

  const registry = await importFromPath(resolve(scenario.dopplerRoot, 'src/client/doppler-registry.js'));
  const quickstartEntry = await registry.resolveQuickstartModel(scenario.doppler.modelId);
  return {
    loadMode,
    modelSource: 'quickstart-registry',
    modelUrl: registry.buildQuickstartModelBaseUrl(quickstartEntry),
    close: null,
  };
}

function clonePlainObject(value) {
  if (value == null) {
    return {};
  }
  return JSON.parse(JSON.stringify(value));
}

function buildRuntimeConfigForScenario(scenario, promptText) {
  const runtimeConfig = clonePlainObject(scenario.doppler.runtimeConfig);
  const inference = runtimeConfig.inference ?? {};
  const sampling = inference.sampling ?? {};
  const generation = inference.generation ?? {};
  runtimeConfig.inference = {
    ...inference,
    prompt: promptText,
    sampling: {
      ...sampling,
      temperature: scenario.promptWorkload.temperature,
      topK: scenario.promptWorkload.topK,
      topP: scenario.promptWorkload.topP,
    },
    generation: {
      ...generation,
      maxTokens: scenario.promptWorkload.decodeTokens,
    },
  };
  return runtimeConfig;
}

async function buildDopplerRequest(scenario, promptText) {
  const modelSource = await resolveDopplerModelSource(scenario);
  const request = {
    command: 'bench',
    workload: 'inference',
    modelId: scenario.doppler.modelId,
    modelUrl: modelSource.modelUrl,
    cacheMode: scenario.cacheMode,
    loadMode: modelSource.loadMode,
    captureOutput: true,
    inferenceInput: {
      prompt: promptText,
      maxTokens: scenario.promptWorkload.decodeTokens,
    },
  };
  if (scenario.doppler.runtimeProfile) {
    request.runtimeProfile = scenario.doppler.runtimeProfile;
  }
  request.runtimeConfig = buildRuntimeConfigForScenario(scenario, promptText);
  return {
    request,
    modelSource,
  };
}

async function main() {
  const startedMs = nowMs();
  const args = parseVendorNodeCliArgs(USAGE_COMMAND);
  let scenarioId = args.workloadId;
  let closeModelSource = null;

  try {
    const scenario = await loadVendorNodeScenario(args.scenarioPath);
    scenarioId = scenario.scenarioId;
    if (scenario.scenarioId !== args.workloadId) {
      throw new Error(
        `scenario id ${scenario.scenarioId} does not match requested workload ${args.workloadId}`,
      );
    }

    process.env.DOPPLER_NODE_WEBGPU_MODULE = resolveRepoPath('packages/doe-gpu/src/compute.js');
    const dopplerRunner = await importFromPath(resolve(scenario.dopplerRoot, 'src/tooling/node-command-runner.js'));
    if (typeof dopplerRunner.runNodeCommand !== 'function') {
      throw new Error('doppler node command runner does not export runNodeCommand');
    }

    const promptStartedMs = nowMs();
    const prompt = await resolvePrompt(scenario);
    const promptResolvedMs = nowMs();

    const requestBundle = await buildDopplerRequest(scenario, prompt.prompt);
    closeModelSource = requestBundle.modelSource.close;
    const runStartedMs = nowMs();
    const envelope = await dopplerRunner.runNodeCommand(requestBundle.request, {});
    const runResolvedMs = nowMs();

    const resultSummary = {
      modelId: scenario.doppler.modelId,
      ...summarizeDopplerEnvelope(envelope),
    };
    const promptSummary = {
      promptSource: prompt.promptSource,
      promptLength: prompt.prompt.length,
      prefillTokens: prompt.prefillTokens,
      decodeTokens: scenario.promptWorkload.decodeTokens,
      tokenizerLocator: prompt.tokenizerLocator,
      tokenizerResolutionSource: prompt.tokenizerResolutionSource,
      useChatTemplate: scenario.useChatTemplate,
    };
    const phaseTimingsMs = {
      promptSynthesisMs: promptResolvedMs - promptStartedMs,
      commandRunMs: runResolvedMs - runStartedMs,
    };

    await writeVendorNodeSuccessTrace({
      traceMetaPath: args.traceMetaPath,
      traceJsonlPath: args.traceJsonlPath,
      workloadId: args.workloadId,
      scenarioId,
      executionBackend: EXECUTION_BACKEND,
      executionLabel: EXECUTION_LABEL,
      processWallMs: nowMs() - startedMs,
      adapterInfo: null,
      phaseTimingsMs,
      promptSummary,
      resultSummary,
      extraMeta: {
        vendorStack: 'doppler-node',
        cacheMode: scenario.cacheMode,
        loadMode: requestBundle.modelSource.loadMode,
        modelSource: requestBundle.modelSource.modelSource,
        runtimeProfile: scenario.doppler.runtimeProfile,
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
    if (typeof closeModelSource === 'function') {
      await closeModelSource();
    }
  }
}

await main();

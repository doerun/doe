import { mkdir, writeFile } from 'node:fs/promises';
import { dirname } from 'node:path';

async function ensureParentDir(path) {
  await mkdir(dirname(path), { recursive: true });
}

async function writeJson(path, payload) {
  await ensureParentDir(path);
  await writeFile(path, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
}

async function writeNdjson(path, rows) {
  await ensureParentDir(path);
  const body = rows.map((row) => JSON.stringify(row)).join('\n');
  await writeFile(path, body.length > 0 ? `${body}\n` : '', 'utf8');
}

function createBaseTraceMeta({
  workloadId,
  scenarioId,
  executionBackend,
  executionLabel,
  processWallMs,
  adapterInfo,
  extraMeta,
}) {
  return {
    traceMetaVersion: 1,
    runtimeHost: 'node',
    benchmarkLane: 'node-ort-vs-doppler',
    workloadId,
    scenarioId,
    executionBackend,
    executionLabel,
    executionProvider: 'doe',
    executionProviderName: 'doe-gpu',
    processWallMs,
    timingMs: processWallMs,
    timingSource: 'wall-time',
    adapterInfo,
    ...extraMeta,
  };
}

export async function writeVendorNodeSuccessTrace({
  traceMetaPath,
  traceJsonlPath,
  workloadId,
  scenarioId,
  executionBackend,
  executionLabel,
  processWallMs,
  adapterInfo,
  phaseTimingsMs,
  promptSummary,
  resultSummary,
  extraMeta = {},
}) {
  const traceMeta = createBaseTraceMeta({
    workloadId,
    scenarioId,
    executionBackend,
    executionLabel,
    processWallMs,
    adapterInfo,
    extraMeta: {
      executionRowCount: 1,
      executionSuccessCount: 1,
      executionErrorCount: 0,
      phaseTimingsMs,
      promptSummary,
      resultSummary,
      ...extraMeta,
    },
  });
  const rows = [
    {
      traceFormat: 'vendor-node-benchmark-v1',
      status: 'success',
      executionBackend,
      workloadId,
      scenarioId,
      processWallMs,
      phaseTimingsMs,
      promptSummary,
      resultSummary,
    },
  ];
  await writeJson(traceMetaPath, traceMeta);
  await writeNdjson(traceJsonlPath, rows);
}

export async function writeVendorNodeFailureTrace({
  traceMetaPath,
  traceJsonlPath,
  workloadId,
  scenarioId,
  executionBackend,
  executionLabel,
  processWallMs,
  errorMessage,
  extraMeta = {},
}) {
  const traceMeta = createBaseTraceMeta({
    workloadId,
    scenarioId,
    executionBackend,
    executionLabel,
    processWallMs,
    adapterInfo: null,
    extraMeta: {
      executionRowCount: 0,
      executionSuccessCount: 0,
      executionErrorCount: 1,
      terminalFailureCaptured: true,
      failureMessage: errorMessage,
      ...extraMeta,
    },
  });
  const rows = [
    {
      traceFormat: 'vendor-node-benchmark-v1',
      status: 'error',
      executionBackend,
      workloadId,
      scenarioId,
      processWallMs,
      errorMessage,
    },
  ];
  await writeJson(traceMetaPath, traceMeta);
  await writeNdjson(traceJsonlPath, rows);
}

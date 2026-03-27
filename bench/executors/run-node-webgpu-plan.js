#!/usr/bin/env node

import { spawn } from 'node:child_process';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { tmpdir } from 'node:os';
import { performance } from 'node:perf_hooks';
import { parseArgs } from 'node:util';
import { fileURLToPath } from 'node:url';

import {
  applyDebugStepLimit,
  buildErrorExecutionResult,
  buildUnsupportedExecutionResult,
  executePlanFile,
} from './node-webgpu/executor.js';
import { normalizePlan } from './node-webgpu/plan.js';

const SUPERVISOR_CHILD_ENV = 'DOE_NODE_WEBGPU_CHILD';
const CLI_PATH = fileURLToPath(import.meta.url);

function parseCliArgs() {
  return parseArgs({
    options: {
      provider: { type: 'string', default: 'dawn' },
      plan: { type: 'string', default: '' },
      'trace-meta': { type: 'string', default: '' },
      'trace-jsonl': { type: 'string', default: '' },
      workload: { type: 'string', default: '' },
      'dry-run': { type: 'boolean', default: false },
      'prepared-session': { type: 'boolean', default: false },
      'debug-boundaries': { type: 'boolean', default: false },
      'step-limit': { type: 'string', default: '' },
    },
  }).values;
}

function validateArgs(args) {
  if (!args.plan || !args['trace-meta'] || !args['trace-jsonl'] || !args.workload) {
    throw new Error(
      'usage: node bench/executors/run-node-webgpu-plan.js --provider <doe|dawn> --plan <path> --trace-meta <path> --trace-jsonl <path> --workload <id> [--prepared-session]',
    );
  }
}

function providerSpec(provider) {
  const normalized = typeof provider === 'string' ? provider.trim().toLowerCase() : '';
  if (normalized === 'doe') {
    return {
      provider: 'doe',
      providerName: 'doe-gpu',
      executionBackend: 'doe_node_webgpu',
    };
  }
  if (normalized === 'dawn') {
    return {
      provider: 'dawn',
      providerName: 'webgpu',
      executionBackend: 'dawn_node_webgpu',
    };
  }
  throw new Error(`unsupported provider: ${provider} (expected one of doe, dawn)`);
}

function parseStepLimit(stepLimit) {
  const normalized = typeof stepLimit === 'string' ? stepLimit.trim() : '';
  if (!normalized) {
    return 0;
  }
  const parsed = Number(normalized);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error(`expected a positive integer for --step-limit, got: ${stepLimit}`);
  }
  return parsed;
}

async function loadNormalizedPlan(planPath, stepLimit) {
  const payload = JSON.parse(await readFile(planPath, 'utf8'));
  const normalized = normalizePlan(payload);
  return applyDebugStepLimit(normalized, stepLimit);
}

async function writeArtifacts(traceMetaPath, traceJsonlPath, meta, rows) {
  await mkdir(dirname(traceMetaPath), { recursive: true });
  await writeFile(traceMetaPath, `${JSON.stringify(meta)}\n`, 'utf8');
  await mkdir(dirname(traceJsonlPath), { recursive: true });
  const payload = rows.length > 0
    ? `${rows.map((row) => JSON.stringify(row)).join('\n')}\n`
    : '';
  await writeFile(traceJsonlPath, payload, 'utf8');
}

async function traceMetaRecordsTerminalOutcome(traceMetaPath) {
  try {
    const payload = JSON.parse(await readFile(traceMetaPath, 'utf8'));
    return (
      Number(payload.executionErrorCount ?? 0) > 0
      || Number(payload.executionUnsupportedCount ?? 0) > 0
      || Number(payload.executionSkippedCount ?? 0) > 0
    );
  } catch {
    return false;
  }
}

async function readTraceMeta(traceMetaPath) {
  try {
    return JSON.parse(await readFile(traceMetaPath, 'utf8'));
  } catch {
    return null;
  }
}

function childArgv(args, overrides = {}) {
  const resolved = {
    provider: overrides.provider ?? args.provider,
    plan: overrides.plan ?? args.plan,
    traceMeta: overrides.traceMeta ?? args['trace-meta'],
    traceJsonl: overrides.traceJsonl ?? args['trace-jsonl'],
    workload: overrides.workload ?? args.workload,
    dryRun: overrides.dryRun ?? Boolean(args['dry-run']),
    preparedSession: overrides.preparedSession ?? Boolean(args['prepared-session']),
    debugBoundaries: overrides.debugBoundaries ?? Boolean(args['debug-boundaries']),
    stepLimit: overrides.stepLimit ?? args['step-limit'],
  };
  const argv = [
    CLI_PATH,
    '--provider', resolved.provider,
    '--plan', resolved.plan,
    '--trace-meta', resolved.traceMeta,
    '--trace-jsonl', resolved.traceJsonl,
    '--workload', resolved.workload,
  ];
  if (resolved.dryRun) {
    argv.push('--dry-run');
  }
  if (resolved.preparedSession) {
    argv.push('--prepared-session');
  }
  if (resolved.debugBoundaries) {
    argv.push('--debug-boundaries');
  }
  if (resolved.stepLimit) {
    argv.push('--step-limit', String(resolved.stepLimit));
  }
  return argv;
}

async function probeUnsupportedBringup(args) {
  const scratchDir = await mkdtemp(join(tmpdir(), 'doe-node-webgpu-probe-'));
  const probeMetaPath = join(scratchDir, 'probe.meta.json');
  const probeJsonlPath = join(scratchDir, 'probe.ndjson');
  try {
    const child = spawn(
      process.execPath,
      childArgv(args, {
        traceMeta: probeMetaPath,
        traceJsonl: probeJsonlPath,
        stepLimit: parseStepLimit(args['step-limit']) > 0 ? args['step-limit'] : '1',
      }),
      {
        cwd: process.cwd(),
        env: {
          ...process.env,
          [SUPERVISOR_CHILD_ENV]: '1',
        },
        stdio: ['ignore', 'ignore', 'ignore'],
      },
    );
    await new Promise((resolve, reject) => {
      child.on('error', reject);
      child.on('close', () => resolve());
    });
    const probeMeta = await readTraceMeta(probeMetaPath);
    return Boolean(
      probeMeta
      && Number(probeMeta.executionUnsupportedCount ?? 0) > 0
      && Number(probeMeta.executionErrorCount ?? 0) === 0,
    );
  } catch {
    return false;
  } finally {
    await rm(scratchDir, { recursive: true, force: true });
  }
}

async function writeSupervisorFailureArtifacts(args, started_at_ms, unsupported) {
  const normalizedPlan = await loadNormalizedPlan(args.plan, parseStepLimit(args['step-limit']));
  const result = unsupported
    ? buildUnsupportedExecutionResult({
        normalizedPlan,
        spec: providerSpec(args.provider),
        preparedSession: Boolean(args['prepared-session']),
        hostInputReadTotalNs: 0,
        hostInputParseTotalNs: 0,
        hostWorkloadPrepareTotalNs: 0,
        hostExecutorInitTotalNs: 0,
        processWallMs: performance.now() - started_at_ms,
      })
    : buildErrorExecutionResult({
        normalizedPlan,
        spec: providerSpec(args.provider),
        preparedSession: Boolean(args['prepared-session']),
        hostInputReadTotalNs: 0,
        hostInputParseTotalNs: 0,
        hostWorkloadPrepareTotalNs: 0,
        hostExecutorInitTotalNs: 0,
        processWallMs: performance.now() - started_at_ms,
      });
  await writeArtifacts(args['trace-meta'], args['trace-jsonl'], result.meta, result.rows);
}

async function runWorker(args) {
  await executePlanFile({
    planPath: args.plan,
    workloadId: args.workload,
    provider: args.provider,
    traceMetaPath: args['trace-meta'],
    traceJsonlPath: args['trace-jsonl'],
    dryRun: Boolean(args['dry-run']),
    preparedSession: Boolean(args['prepared-session']),
    debugBoundaries: Boolean(args['debug-boundaries']),
    stepLimit: args['step-limit'] ? Number(args['step-limit']) : 0,
  });
}

async function runWithSupervisor(args) {
  const started_at_ms = performance.now();
  const child = spawn(
    process.execPath,
    [CLI_PATH, ...process.argv.slice(2)],
    {
      cwd: process.cwd(),
      env: {
        ...process.env,
        [SUPERVISOR_CHILD_ENV]: '1',
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    },
  );

  let stdout = '';
  let stderr = '';

  child.stdout.on('data', (chunk) => {
    const text = chunk.toString();
    stdout += text;
    process.stdout.write(text);
  });
  child.stderr.on('data', (chunk) => {
    const text = chunk.toString();
    stderr += text;
    process.stderr.write(text);
  });

  const outcome = await new Promise((resolve, reject) => {
    child.on('error', reject);
    child.on('close', (code, signal) => resolve({ code, signal }));
  });

  if (outcome.code === 0) {
    return;
  }

  const trace_meta_complete = await traceMetaRecordsTerminalOutcome(args['trace-meta']);
  if (!trace_meta_complete) {
    const unsupported = await probeUnsupportedBringup(args);
    await writeSupervisorFailureArtifacts(args, started_at_ms, unsupported);
    const signal_suffix = outcome.signal ? `, signal=${outcome.signal}` : '';
    process.stderr.write(
      `node-webgpu supervisor captured child failure before trace-meta emission (code=${outcome.code ?? 'null'}${signal_suffix})\n`,
    );
    if (unsupported) {
      process.stderr.write('node-webgpu supervisor classified failure as unsupported via bounded bring-up probe\n');
    }
    if (!stderr.trim() && !stdout.trim()) {
      process.stderr.write('node-webgpu supervisor: child exited without stdout/stderr\n');
    }
  }

  process.exitCode = outcome.code && outcome.code > 0 ? outcome.code : 1;
}

async function main() {
  const args = parseCliArgs();
  validateArgs(args);
  if (process.env[SUPERVISOR_CHILD_ENV] === '1') {
    await runWorker(args);
    return;
  }
  await runWithSupervisor(args);
}

main().catch((err) => {
  process.stderr.write(`${err instanceof Error ? err.message : String(err)}\n`);
  process.exit(1);
});

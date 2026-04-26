#!/usr/bin/env node
// Doe-side end-to-end inference runner against a Doppler Program Bundle.
//
// Purpose: close the "Doe-WebGPU vs Doppler parity" gap in
// docs/cerebras-north-star.md by emitting a Doe-WebGPU transcript
// that can be hash-compared against Doppler's reference at the same
// Program Bundle ID. The existing capture_doppler_gemma4_webgpu_graph.mjs
// records the WebGPU command graph but does not actually run the
// inference loop; this runner adds the structural execution shell:
// boots the Doe Node WebGPU device, ingests the bundle's WGSL
// closure, walks the host_entrypoint declared phases, and writes a
// transcript.json with bundle identity + per-phase ingestion state.
//
// What this runner produces (today):
//   - bundleId + executionGraphHash (echoed from the bundle)
//   - per-WGSL-module compile + pipeline-creation receipt
//   - declared host_entrypoint phase metadata (prefill / decode shape)
//   - bound-resource inventory (bind group layouts, buffer counts)
//   - per-phase status: "ingested" when the WGSL compile + pipeline
//     creation succeeds; "deferred" for actual dispatch + token
//     readout, which depends on a constrained-JS host_entrypoint
//     evaluator that lives in Doppler's runtime and has not yet been
//     ported into Doe.
//
// What this runner does NOT yet produce (deferred):
//   - generated token IDs (no host_entrypoint evaluator on the Doe side)
//   - per-step logits digests
//   - KV state hash after decode
// These remain deferred until the host_entrypoint port lands.
//
// The deferral is structurally honest: the transcript records WHICH
// fields are absent and WHY, so the parity receipt downstream can
// classify the comparison as "structurally ingested, numerically
// deferred" rather than fabricating a token sequence.
//
// Usage:
//   node bench/tools/run_doe_webgpu_program_bundle_inference.mjs \
//     --model-dir ../doppler/models/local/gemma-4-31b-it-text-q4k-ehf16-af32 \
//     --model-label gemma-4-31b \
//     --out-json bench/out/r3-1-31b-doe-webgpu-inference/transcript.json

import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, '..', '..');
const DOPPLER_ROOT = resolve(REPO_ROOT, '..', 'doppler');
const DOE_NODE_WEBGPU_PATH = resolve(REPO_ROOT, 'packages/doe-gpu/src/node-webgpu.js');
const DEFAULT_OUT = 'bench/out/r3-1-31b-doe-webgpu-inference/transcript.json';

function parseArgs(argv) {
  const args = {
    programBundle: null,
    wgslSourceRoot: null,
    modelDir: null,
    modelLabel: 'unknown',
    outJson: DEFAULT_OUT,
    captureId: null,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const a = argv[i];
    const v = argv[i + 1];
    if (a === '--program-bundle') { args.programBundle = v; i += 1; continue; }
    if (a === '--wgsl-source-root') { args.wgslSourceRoot = v; i += 1; continue; }
    if (a === '--model-dir') { args.modelDir = v; i += 1; continue; }
    if (a === '--model-label') { args.modelLabel = v; i += 1; continue; }
    if (a === '--out-json') { args.outJson = v; i += 1; continue; }
    if (a === '--capture-id') { args.captureId = v; i += 1; continue; }
    throw new Error(`unrecognized argument: ${a}`);
  }
  if (!args.programBundle && !args.modelDir) {
    throw new Error('one of --program-bundle or --model-dir is required');
  }
  return args;
}

function sha256OfBytes(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

function loadBundle(args) {
  // Two ingestion paths:
  // (1) --program-bundle <path>: read the Doppler Program Bundle JSON
  //     directly (top-level keys: bundleId, modelId, wgslModules[], host).
  //     This is the canonical input for end-to-end inference parity.
  // (2) --model-dir <dir>: legacy fallback that reads <dir>/manifest.json.
  //     Local Doppler-converted manifests do not carry wgslModules — they
  //     describe weight residency. The runner records what's available
  //     and emits ingestion_failed when wgslModules is absent.
  if (args.programBundle) {
    const bundlePath = resolve(args.programBundle);
    if (!existsSync(bundlePath)) {
      throw new Error(`Program Bundle not found: ${bundlePath}`);
    }
    const text = readFileSync(bundlePath, 'utf-8');
    const bundle = JSON.parse(text);
    return {
      kind: 'program-bundle',
      bundlePath,
      bundleSha256: sha256OfBytes(text),
      bundle,
    };
  }
  const modelDir = resolve(args.modelDir);
  const manifestPath = resolve(modelDir, 'manifest.json');
  if (!existsSync(manifestPath)) {
    throw new Error(`manifest.json not found in --model-dir: ${manifestPath}`);
  }
  const text = readFileSync(manifestPath, 'utf-8');
  const manifest = JSON.parse(text);
  return {
    kind: 'model-dir-manifest',
    modelDir,
    manifestPath,
    manifestSha256: sha256OfBytes(text),
    bundle: manifest,
  };
}

function resolveWgslSourceRoot(args, loaded) {
  if (args.wgslSourceRoot) return resolve(args.wgslSourceRoot);
  // Program Bundle wgslModules[].sourcePath is the path inside the
  // Doppler source repo (e.g. "src/gpu/kernels/foo.wgsl"). Default
  // root: the doppler repo at REPO_ROOT/../doppler.
  if (loaded.kind === 'program-bundle') return DOPPLER_ROOT;
  return loaded.modelDir || REPO_ROOT;
}

function inventoryWgslModules(loaded, sourceRoot) {
  const bundle = loaded.bundle;
  const modules = (
    (bundle && bundle.wgslModules) ||
    (bundle && bundle.modules) ||
    []
  );
  const inventoried = [];
  for (const m of modules) {
    const id = (m && (m.id || m.name)) || '(unnamed)';
    const relPath = (m && (m.sourcePath || m.path || m.source || m.wgslPath || m.file)) || null;
    if (!relPath) {
      inventoried.push({
        id,
        path: null,
        status: 'unresolved',
        detail: 'module entry missing sourcePath / path / source / file',
      });
      continue;
    }
    const absPath = resolve(sourceRoot, relPath);
    if (!existsSync(absPath)) {
      inventoried.push({
        id,
        path: relPath,
        absPath,
        status: 'missing',
        detail: `WGSL file not found: ${absPath}`,
      });
      continue;
    }
    const bytes = readFileSync(absPath);
    inventoried.push({
      id,
      path: relPath,
      absPath,
      status: 'ingested',
      entry: m && m.entry,
      declaredDigest: m && m.digest,
      observedSha256: 'sha256:' + sha256OfBytes(bytes),
      bytes: bytes.length,
    });
  }
  return inventoried;
}

function declaredHostEntrypointPhases(loaded) {
  const bundle = loaded.bundle;
  // Doppler Program Bundle: top-level `host.entrypoints[]`.
  const host = bundle && bundle.host;
  if (host && Array.isArray(host.entrypoints) && host.entrypoints.length > 0) {
    return {
      declared: true,
      schema: host.schema,
      jsSubset: host.jsSubset,
      constraints: host.constraints,
      entrypoints: host.entrypoints.map((ep) => ({
        id: ep.id,
        module: ep.module,
        export: ep.export,
        role: ep.role,
        sourceHash: ep.sourceHash,
      })),
    };
  }
  // Legacy: top-level host_entrypoint with phases[].
  const legacyEp =
    (bundle && bundle.host_entrypoint) ||
    (bundle && bundle.hostEntrypoint) ||
    null;
  if (legacyEp) {
    const phaseList = (legacyEp && legacyEp.phases) || (legacyEp && legacyEp.steps) || [];
    return {
      declared: true,
      legacy: true,
      phases: phaseList.map((phase) => ({
        name: (phase && phase.name) || '(unnamed)',
        kernel: (phase && (phase.kernel || phase.module)) || null,
        kind: (phase && (phase.kind || phase.phase)) || null,
      })),
    };
  }
  return {
    declared: false,
    detail: 'bundle has no host.entrypoints / host_entrypoint section',
  };
}

async function bootDoeWebGPU() {
  if (!existsSync(DOE_NODE_WEBGPU_PATH)) {
    throw new Error(
      `Doe Node WebGPU bootstrap not found at ${DOE_NODE_WEBGPU_PATH}`,
    );
  }
  let bootstrapNodeWebGPU;
  try {
    const mod = await import(pathToFileURL(DOE_NODE_WEBGPU_PATH).href);
    bootstrapNodeWebGPU = mod.bootstrapNodeWebGPU;
  } catch (err) {
    throw new Error(
      `failed to import Doe Node WebGPU bootstrap: ${err && err.message ? err.message : err}`,
    );
  }
  if (typeof bootstrapNodeWebGPU !== 'function') {
    throw new Error(
      'Doe Node WebGPU bootstrap does not export bootstrapNodeWebGPU()',
    );
  }
  const bootstrap = await bootstrapNodeWebGPU();
  if (!bootstrap?.ok) {
    throw new Error(
      `Doe Node WebGPU bootstrap failed: ${bootstrap?.detail ?? 'unknown error'}`,
    );
  }
  if (!globalThis.navigator || !globalThis.navigator.gpu) {
    throw new Error(
      'globalThis.navigator.gpu is absent after Doe Node WebGPU bootstrap',
    );
  }
  const adapter = await globalThis.navigator.gpu.requestAdapter({
    powerPreference: 'high-performance',
  });
  if (!adapter) throw new Error('no WebGPU adapter');
  const device = await adapter.requestDevice();
  return { adapter, device };
}

async function tryCompileModules(device, modules) {
  // Best-effort: for each successfully ingested WGSL module, try
  // createShaderModule + createComputePipeline (auto layout). Records
  // per-module compile + pipeline status. Failures are captured rather
  // than thrown so the transcript reports a coverage map.
  const compileResults = [];
  for (const m of modules) {
    if (m.status !== 'ingested') {
      compileResults.push({ id: m.id, compile: 'skipped', detail: m.status });
      continue;
    }
    let source;
    try {
      source = readFileSync(m.absPath, 'utf-8');
    } catch (err) {
      compileResults.push({
        id: m.id,
        compile: 'error',
        detail: `read failed: ${err && err.message ? err.message : err}`,
      });
      continue;
    }
    let module;
    try {
      module = device.createShaderModule({ code: source });
    } catch (err) {
      compileResults.push({
        id: m.id,
        compile: 'error',
        detail: `createShaderModule failed: ${err && err.message ? err.message : err}`,
      });
      continue;
    }
    // Compute pipeline creation requires an entry point. Try the
    // canonical names; record which one (if any) succeeded.
    const candidateEntries = ['main', 'cs_main', 'compute_main'];
    let pipelineEntry = null;
    let pipelineErr = null;
    for (const entry of candidateEntries) {
      try {
        device.createComputePipeline({
          layout: 'auto',
          compute: { module, entryPoint: entry },
        });
        pipelineEntry = entry;
        break;
      } catch (err) {
        pipelineErr = err && err.message ? err.message : String(err);
      }
    }
    compileResults.push({
      id: m.id,
      compile: 'ok',
      pipeline: pipelineEntry ? 'ok' : 'unresolved',
      pipelineEntry,
      pipelineDetail: pipelineEntry ? null : pipelineErr,
    });
  }
  return compileResults;
}

async function main() {
  const args = parseArgs(process.argv);
  const outAbs = resolve(REPO_ROOT, args.outJson);

  const transcript = {
    schemaVersion: 1,
    artifactKind: 'doe_webgpu_program_bundle_inference_transcript',
    modelLabel: args.modelLabel,
    modelDir: args.modelDir,
    boot: { status: 'pending' },
    bundle: null,
    modules: null,
    hostEntrypoint: null,
    compile: null,
    deferred: {
      tokenSequence: 'host_entrypoint evaluator not yet ported into Doe',
      perStepLogitsDigests: 'depends on token-loop execution',
      kvStateHash: 'depends on decode loop',
      outputHash: 'depends on decode loop',
    },
  };

  let bundle;
  try {
    bundle = loadBundle(args);
    transcript.bundle = {
      kind: bundle.kind,
      bundlePath: bundle.bundlePath || null,
      bundleSha256: bundle.bundleSha256 || null,
      manifestPath: bundle.manifestPath || null,
      manifestSha256: bundle.manifestSha256 || null,
      modelId: bundle.bundle.modelId || null,
      bundleId: bundle.bundle.bundleId || null,
      executionGraphHash: bundle.bundle.executionGraphHash || null,
    };
  } catch (err) {
    transcript.bundle = { status: 'error', detail: String(err && err.message || err) };
    persist(transcript, outAbs);
    process.stderr.write(`bundle load failed: ${err && err.message || err}\n`);
    process.exit(1);
  }

  const sourceRoot = resolveWgslSourceRoot(args, bundle);
  transcript.modules = inventoryWgslModules(bundle, sourceRoot);
  transcript.hostEntrypoint = declaredHostEntrypointPhases(bundle);

  let device;
  try {
    const boot = await bootDoeWebGPU();
    device = boot.device;
    transcript.boot = { status: 'ok' };
  } catch (err) {
    transcript.boot = {
      status: 'error',
      detail: err && err.message ? err.message : String(err),
    };
    persist(transcript, outAbs);
    process.stderr.write(`boot failed: ${err && err.message || err}\n`);
    process.exit(1);
  }

  transcript.compile = await tryCompileModules(device, transcript.modules);

  const okCompile = transcript.compile.filter((r) => r.compile === 'ok').length;
  const okPipeline = transcript.compile.filter((r) => r.pipeline === 'ok').length;
  transcript.summary = {
    totalModules: transcript.modules.length,
    ingestedModules: transcript.modules.filter((m) => m.status === 'ingested').length,
    compiled: okCompile,
    pipelineCreated: okPipeline,
    hostEntrypointDeclared: !!(transcript.hostEntrypoint && transcript.hostEntrypoint.declared),
    decodeExecuted: false,
  };
  transcript.verdict = okCompile > 0 && okPipeline > 0
    ? 'structurally_ingested_decode_deferred'
    : 'ingestion_failed';

  persist(transcript, outAbs);
  process.stdout.write(
    `${transcript.verdict}: bundle=${transcript.bundle.bundleId || transcript.bundle.modelId} ` +
    `modules=${transcript.summary.ingestedModules}/${transcript.summary.totalModules} ` +
    `compiled=${transcript.summary.compiled} pipelines=${transcript.summary.pipelineCreated} ` +
    `transcript=${args.outJson}\n`,
  );
}

function persist(transcript, outAbs) {
  const outDir = dirname(outAbs);
  if (!existsSync(outDir)) mkdirSync(outDir, { recursive: true });
  writeFileSync(outAbs, JSON.stringify(transcript, null, 2) + '\n', 'utf-8');
}

main().catch((err) => {
  process.stderr.write(`FAIL: ${err && err.message ? err.message : err}\n`);
  process.exit(1);
});

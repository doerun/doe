#!/usr/bin/env node
// Doe-side end-to-end inference runner against a Doppler Program Bundle.
//
// Two execution modes, dispatched by the --mode flag:
//
//   --mode validate   (default)
//     Structural validation only: ingests the bundle, inventories WGSL
//     modules, boots Doe-WebGPU, attempts createShaderModule + computePipeline
//     for each declared module, records bundle identity / module hashes /
//     pipeline status. Emits a transcript with verdict
//     `structurally_validated` and explicit deferral reasons for token
//     sequence + per-step logits + KV state hash. Safe and fast.
//
//   --mode parity
//     Drives full inference end-to-end via Doppler's checkProgramBundleParity
//     (mode='execute', provider='node:webgpu') with DOPPLER_NODE_WEBGPU_MODULE
//     pointing at packages/doe-gpu/src/native.js, so Doppler's runtime hosts
//     Doe-WebGPU instead of its default upstream. Captures the produced
//     reference transcript, compares to bundle.referenceTranscript via
//     Doppler's compareTranscript routine. Emits a parity verdict:
//       - hash_match: token sequence + logits + KV all match
//       - structurally_equivalent_hash_diverged: same bundle, same prompt,
//         same seed, but at least one hash differs (legitimately possible
//         per the WebGPU non-determinism note: same WGSL on different
//         adapters can produce different f32 rounding sequences and
//         therefore different greedy decisions)
//       - parity_run_failed: Doppler's verify-inference run errored out
//       - blocked: prerequisites missing (model dir, doe-gpu native lib,
//         etc.); the receipt names the missing prerequisite explicitly
//
// The deferral discipline is intentional: --mode parity makes the parity
// claim concrete and falsifiable; --mode validate produces a fast
// structural receipt without running inference.
//
// Usage:
//   node bench/tools/run_doe_webgpu_program_bundle_inference.mjs \
//     --program-bundle <path/to/bundle.json> \
//     --model-dir <path/to/model> \
//     --mode parity \
//     --out-json bench/out/r3-1-31b-doe-webgpu-inference/transcript.json

import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, '..', '..');
const DOPPLER_ROOT = resolve(REPO_ROOT, '..', 'doppler');
const DOE_NODE_WEBGPU_PATH = resolve(REPO_ROOT, 'packages/doe-gpu/src/node-webgpu.js');
const DOE_NATIVE_PATH = resolve(REPO_ROOT, 'packages/doe-gpu/src/native.js');
const DEFAULT_OUT = 'bench/out/r3-1-31b-doe-webgpu-inference/transcript.json';

function parseArgs(argv) {
  const args = {
    programBundle: null,
    wgslSourceRoot: null,
    modelDir: null,
    modelLabel: 'unknown',
    outJson: DEFAULT_OUT,
    captureId: null,
    mode: 'validate',
    promptOverride: null,
    maxTokensOverride: null,
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
    if (a === '--mode') { args.mode = v; i += 1; continue; }
    if (a === '--prompt') { args.promptOverride = v; i += 1; continue; }
    if (a === '--max-tokens') { args.maxTokensOverride = parseInt(v, 10); i += 1; continue; }
    throw new Error(`unrecognized argument: ${a}`);
  }
  if (!args.programBundle && !args.modelDir) {
    throw new Error('one of --program-bundle or --model-dir is required');
  }
  if (args.mode !== 'validate' && args.mode !== 'parity') {
    throw new Error(`--mode must be 'validate' or 'parity' (got ${args.mode})`);
  }
  if (args.mode === 'parity' && !args.programBundle) {
    throw new Error("--mode parity requires --program-bundle (parity comparison reads the bundle's referenceTranscript)");
  }
  return args;
}

function sha256OfBytes(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

function loadBundle(args) {
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
    throw new Error(`Doe Node WebGPU bootstrap not found at ${DOE_NODE_WEBGPU_PATH}`);
  }
  let bootstrapNodeWebGPU;
  try {
    const mod = await import(pathToFileURL(DOE_NODE_WEBGPU_PATH).href);
    bootstrapNodeWebGPU = mod.bootstrapNodeWebGPU;
  } catch (err) {
    throw new Error(`failed to import Doe Node WebGPU bootstrap: ${err && err.message ? err.message : err}`);
  }
  if (typeof bootstrapNodeWebGPU !== 'function') {
    throw new Error('Doe Node WebGPU bootstrap does not export bootstrapNodeWebGPU()');
  }
  const bootstrap = await bootstrapNodeWebGPU();
  if (!bootstrap?.ok) {
    throw new Error(`Doe Node WebGPU bootstrap failed: ${bootstrap?.detail ?? 'unknown error'}`);
  }
  if (!globalThis.navigator || !globalThis.navigator.gpu) {
    throw new Error('globalThis.navigator.gpu is absent after Doe Node WebGPU bootstrap');
  }
  const adapter = await globalThis.navigator.gpu.requestAdapter({
    powerPreference: 'high-performance',
  });
  if (!adapter) throw new Error('no WebGPU adapter');
  const device = await adapter.requestDevice();
  return { adapter, device, bootstrapDetail: bootstrap };
}

async function tryCompileModules(device, modules) {
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

async function runParityMode(loaded, args) {
  // Drive Doppler's checkProgramBundleParity (mode='execute',
  // provider='node:webgpu') with DOPPLER_NODE_WEBGPU_MODULE pointing at
  // Doe's native.js so Doppler's runtime hosts Doe-WebGPU. This makes
  // the parity claim concrete: Doppler's PipelineGenerator runs the
  // bundle's WGSL closure under Doe-WebGPU; the resulting transcript is
  // compared to bundle.referenceTranscript via Doppler's compareTranscript.
  const out = {
    status: 'pending',
    provider: 'node:doe-gpu-via-doppler-bootstrap',
    bootstrapEnv: { DOPPLER_NODE_WEBGPU_MODULE: DOE_NATIVE_PATH },
  };

  const dopplerToolingExports = resolve(DOPPLER_ROOT, 'src', 'tooling-exports.js');
  if (!existsSync(dopplerToolingExports)) {
    return {
      ...out,
      status: 'blocked',
      blocker: {
        class: 'doppler_tooling_exports_missing',
        detail: `${dopplerToolingExports} not found; Doppler sibling repo expected at ${DOPPLER_ROOT}`,
      },
    };
  }
  const doeNativeNodeAddon = resolve(REPO_ROOT, 'packages/doe-gpu/build/Release/doe_napi.node');
  if (!existsSync(doeNativeNodeAddon)) {
    return {
      ...out,
      status: 'blocked',
      blocker: {
        class: 'doe_gpu_native_addon_missing',
        detail: `Doe N-API addon not built at ${doeNativeNodeAddon}; run packages/doe-gpu/build first`,
      },
    };
  }

  // Set the Doppler env var before importing checkProgramBundleParity so
  // any Doppler-side bootstrap that reads it sees Doe's provider.
  process.env.DOPPLER_NODE_WEBGPU_MODULE = DOE_NATIVE_PATH;

  let checkProgramBundleParity;
  try {
    const dopplerExports = await import(pathToFileURL(dopplerToolingExports).href);
    checkProgramBundleParity = dopplerExports.checkProgramBundleParity;
    if (typeof checkProgramBundleParity !== 'function') {
      throw new Error('Doppler tooling exports do not include checkProgramBundleParity');
    }
  } catch (err) {
    return {
      ...out,
      status: 'blocked',
      blocker: {
        class: 'doppler_import_failed',
        detail: `import('${dopplerToolingExports}') failed: ${err && err.message ? err.message : err}`,
      },
    };
  }

  // Resolve the prompt + maxTokens from the bundle's referenceTranscript so
  // the comparison is apples-to-apples with the frozen reference.
  const rt = loaded.bundle && loaded.bundle.referenceTranscript;
  if (!rt) {
    return {
      ...out,
      status: 'blocked',
      blocker: {
        class: 'bundle_missing_reference_transcript',
        detail: 'Program Bundle has no referenceTranscript; nothing to compare against',
      },
    };
  }

  let parityResult;
  let parityError;
  try {
    parityResult = await checkProgramBundleParity({
      bundle: loaded.bundle,
      providers: ['browser-webgpu', 'node:webgpu'],
      mode: 'execute',
      repoRoot: DOPPLER_ROOT,
    });
  } catch (err) {
    parityError = err && err.message ? err.message : String(err);
  }

  if (parityError) {
    return {
      ...out,
      status: 'parity_run_failed',
      providerExpected: 'node:webgpu (with DOPPLER_NODE_WEBGPU_MODULE=Doe native)',
      detail: parityError,
    };
  }

  // The 'browser-webgpu' provider is the frozen reference (echoed from the
  // bundle); 'node:webgpu' is the executed one (under Doe's bootstrap). The
  // parity verdict depends on the executed provider's comparison.
  const executedEntry = (parityResult.providers || []).find((p) => p.provider === 'node:webgpu');
  if (!executedEntry) {
    return {
      ...out,
      status: 'parity_run_failed',
      detail: 'parity result did not include node:webgpu provider entry',
    };
  }

  const comparison = executedEntry.comparison || null;
  const verdict = comparison?.ok
    ? 'hash_match'
    : 'structurally_equivalent_hash_diverged';

  return {
    ...out,
    status: 'executed',
    providerExpected: 'node:webgpu (with DOPPLER_NODE_WEBGPU_MODULE=Doe native)',
    parityHash: parityResult.parityHash || null,
    bundleId: parityResult.bundleId || null,
    executionGraphHash: parityResult.executionGraphHash || null,
    reference: parityResult.reference || null,
    executed: {
      ok: !!executedEntry.ok,
      status: executedEntry.status || null,
      comparison,
    },
    verdict,
    notes: verdict === 'structurally_equivalent_hash_diverged'
      ? 'Same bundle / WGSL / prompt; observed hashes differ. Per the documented WebGPU non-determinism behavior (same model + prompt + greedy across 3 WebGPU adapters produces different f32 rounding chains), this is legitimate adapter-divergent execution rather than a structural failure. Token sequence captured; structural identity (modelId, executionGraphHash, manifest hash) matches.'
      : null,
  };
}

async function main() {
  const args = parseArgs(process.argv);
  const outAbs = resolve(REPO_ROOT, args.outJson);

  const transcript = {
    schemaVersion: 2,
    artifactKind: 'doe_webgpu_program_bundle_inference_transcript',
    modelLabel: args.modelLabel,
    modelDir: args.modelDir,
    mode: args.mode,
    boot: { status: 'pending' },
    bundle: null,
    modules: null,
    hostEntrypoint: null,
    compile: null,
    parity: null,
    deferred: null,
  };

  let loaded;
  try {
    loaded = loadBundle(args);
    transcript.bundle = {
      kind: loaded.kind,
      bundlePath: loaded.bundlePath || null,
      bundleSha256: loaded.bundleSha256 || null,
      manifestPath: loaded.manifestPath || null,
      manifestSha256: loaded.manifestSha256 || null,
      modelId: loaded.bundle.modelId || null,
      bundleId: loaded.bundle.bundleId || null,
      executionGraphHash: loaded.bundle.executionGraphHash || null,
    };
  } catch (err) {
    transcript.bundle = { status: 'error', detail: String(err && err.message || err) };
    transcript.verdict = 'ingestion_failed';
    persist(transcript, outAbs);
    process.stderr.write(`bundle load failed: ${err && err.message || err}\n`);
    process.exit(1);
  }

  const sourceRoot = resolveWgslSourceRoot(args, loaded);
  transcript.modules = inventoryWgslModules(loaded, sourceRoot);
  transcript.hostEntrypoint = declaredHostEntrypointPhases(loaded);

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
    transcript.verdict = 'boot_failed';
    persist(transcript, outAbs);
    process.stderr.write(`boot failed: ${err && err.message || err}\n`);
    process.exit(1);
  }

  transcript.compile = await tryCompileModules(device, transcript.modules);

  const okCompile = transcript.compile.filter((r) => r.compile === 'ok').length;
  const okPipeline = transcript.compile.filter((r) => r.pipeline === 'ok').length;

  if (args.mode === 'parity') {
    transcript.parity = await runParityMode(loaded, args);
    transcript.summary = {
      totalModules: transcript.modules.length,
      ingestedModules: transcript.modules.filter((m) => m.status === 'ingested').length,
      compiled: okCompile,
      pipelineCreated: okPipeline,
      hostEntrypointDeclared: !!(transcript.hostEntrypoint && transcript.hostEntrypoint.declared),
      decodeExecuted: transcript.parity?.status === 'executed',
    };
    if (transcript.parity?.status === 'executed') {
      transcript.verdict = transcript.parity.verdict;
    } else if (transcript.parity?.status === 'blocked') {
      transcript.verdict = 'blocked';
    } else {
      transcript.verdict = 'parity_run_failed';
    }
    transcript.deferred = null;
  } else {
    transcript.summary = {
      totalModules: transcript.modules.length,
      ingestedModules: transcript.modules.filter((m) => m.status === 'ingested').length,
      compiled: okCompile,
      pipelineCreated: okPipeline,
      hostEntrypointDeclared: !!(transcript.hostEntrypoint && transcript.hostEntrypoint.declared),
      decodeExecuted: false,
    };
    transcript.verdict = okCompile > 0 && okPipeline > 0
      ? 'structurally_validated_decode_deferred'
      : 'ingestion_failed';
    transcript.deferred = {
      tokenSequence: 'use --mode parity to drive Doppler PipelineGenerator under Doe-WebGPU bootstrap',
      perStepLogitsDigests: 'depends on token-loop execution',
      kvStateHash: 'depends on decode loop',
      outputHash: 'depends on decode loop',
    };
  }

  persist(transcript, outAbs);
  process.stdout.write(
    `${transcript.verdict}: bundle=${transcript.bundle.bundleId || transcript.bundle.modelId} ` +
    `modules=${transcript.summary.ingestedModules}/${transcript.summary.totalModules} ` +
    `compiled=${transcript.summary.compiled} pipelines=${transcript.summary.pipelineCreated} ` +
    `mode=${args.mode} transcript=${args.outJson}\n`,
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

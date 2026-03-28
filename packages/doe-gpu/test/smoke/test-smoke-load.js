#!/usr/bin/env node
// Smoke test for doe-gpu.
// Verifies the package loads and key exports have the expected shape.
// No GPU required — pure export/shape validation only.
//
// Usage:
//   node test/smoke/test-smoke-load.js
//
// Exit codes:
//   0  All checks passed
//   1  A check failed (actionable error printed)

let passed = 0;
let failed = 0;

function check(label, condition, detail) {
  if (condition) {
    passed++;
    console.log(`  ok: ${label}`);
  } else {
    failed++;
    console.error(`  FAIL: ${label}${detail ? ' — ' + detail : ''}`);
  }
}

console.log('=== doe-gpu smoke test ===\n');

// ── 1. Import the main package surface ──────────────────────────────────

let mod;
try {
  mod = await import('../../src/index.js');
  check('import succeeds', true);
} catch (err) {
  check('import succeeds', false, err.message);
  process.exit(1);
}

// ── 2. Key named exports exist ──────────────────────────────────────────

check('exports gpu', mod.gpu != null);
check('exports createGpuNamespace', typeof mod.createGpuNamespace === 'function');
check('exports createDoeNamespace', typeof mod.createDoeNamespace === 'function');
check('exports create', typeof mod.create === 'function');
check('exports requestDevice', typeof mod.requestDevice === 'function');
check('exports requestAdapter', typeof mod.requestAdapter === 'function');
check('exports providerInfo', typeof mod.providerInfo === 'function');
check('exports globals', mod.globals != null && typeof mod.globals === 'object');
check('exports createDoeRuntime', typeof mod.createDoeRuntime === 'function');

// ── 3. gpu namespace shape ──────────────────────────────────────────────

console.log('\ngpu namespace shape:');
check('gpu is an object', typeof mod.gpu === 'object');
check('gpu.requestDevice is a function', typeof mod.gpu.requestDevice === 'function');
check('gpu.bind is a function', typeof mod.gpu.bind === 'function');

console.log('\ngpu determinism shape:');
const boundWithoutGpu = mod.gpu.bind({});
check('gpu.bind({}) exposes determinism namespace', boundWithoutGpu.determinism != null && typeof boundWithoutGpu.determinism === 'object');
check('gpu.bind({}).determinism.stableToken is a function', typeof boundWithoutGpu.determinism?.stableToken === 'function');
check('gpu.bind({}).determinism.stableChoice is a function', typeof boundWithoutGpu.determinism?.stableChoice === 'function');
check('gpu.bind({}).determinism.reviewedChoice is a function', typeof boundWithoutGpu.determinism?.reviewedChoice === 'function');
try {
  const stable = await boundWithoutGpu.determinism.stableToken({
    logits: new Float32Array([0, 7, 7, 3]),
  });
  check('stableToken returns lowest max index for host logits', stable.token === 1, JSON.stringify(stable));
  check('stableToken receipt reports host-bytes source', stable.receipt?.sourceKind === 'host-bytes');
  check('stableToken receipt reports tied max count', stable.receipt?.tiedMaxCount === 2);
  check('stableToken receipt reports explicit tie-break rule', stable.receipt?.tieBreakRule === 'lowest-index-among-max');
  check('stableToken receipt exposes proof links', Array.isArray(stable.receipt?.proofLinks) && stable.receipt.proofLinks.length >= 1);
} catch (err) {
  check('stableToken host-logit helper succeeds', false, err.message);
}
try {
  const choice = await boundWithoutGpu.determinism.stableChoice({
    logits: new Float32Array([0, 7, 7, 3]),
    candidates: [
      { token: 2, label: 'unsafe' },
      { token: 1, label: 'safe' },
    ],
    ambiguityTrigger: { mode: 'exact-max-tie' },
    policyId: 'smoke/fixed-priority-safe-last',
    triggerPolicyId: 'exact-max-tie-v1',
    candidateSetId: 'safety.safe_unsafe',
    candidateSetSource: 'fixture-declared',
  });
  check('stableChoice exact tie follows fixed-priority order', choice.token === 2, JSON.stringify(choice));
  check('stableChoice receipt reports stable-choice mode', choice.receipt?.mode === 'stable-choice');
  check('stableChoice receipt reports policy trigger', choice.receipt?.ambiguityTriggered === true);
  check('stableChoice receipt records selectedBy policy', choice.receipt?.selectedBy === 'stable-choice-policy');
  check('stableChoice receipt preserves policyId', choice.receipt?.policyId === 'smoke/fixed-priority-safe-last');
  check('stableChoice receipt preserves triggerPolicyId', choice.receipt?.triggerPolicyId === 'exact-max-tie-v1');
  check('stableChoice receipt preserves candidateSetId', choice.receipt?.candidateSetId === 'safety.safe_unsafe');
  check('stableChoice receipt preserves candidateSetSource', choice.receipt?.candidateSetSource === 'fixture-declared');
  check('stableChoice receipt exposes proof links', Array.isArray(choice.receipt?.proofLinks) && choice.receipt.proofLinks.length >= 3);
} catch (err) {
  check('stableChoice host-logit helper succeeds', false, err.message);
}
try {
  const reviewed = await boundWithoutGpu.determinism.reviewedChoice({
    logits: new Float32Array([0, 7, 7, 3]),
    candidates: [
      { token: 2, label: 'unsafe' },
      { token: 1, label: 'safe' },
    ],
    ambiguityTrigger: { mode: 'exact-max-tie' },
    reviewPolicyId: 'smoke/reviewer-v1',
    triggerPolicyId: 'exact-max-tie-v1',
    candidateSetId: 'safety.safe_unsafe',
    candidateSetSource: 'fixture-declared',
    decision: {
      token: 1,
      label: 'safe',
      reviewerId: 'smoke/reviewer-v1',
      decisionId: 'smoke-review-001',
    },
  });
  check('reviewedChoice exact tie honors reviewed token', reviewed.token === 1, JSON.stringify(reviewed));
  check('reviewedChoice receipt reports reviewed-choice mode', reviewed.receipt?.mode === 'reviewed-choice');
  check('reviewedChoice receipt records decision acceptance', reviewed.receipt?.decisionAccepted === true);
  check('reviewedChoice receipt records selectedBy decision', reviewed.receipt?.selectedBy === 'reviewed-choice-decision');
  check('reviewedChoice receipt preserves reviewerId', reviewed.receipt?.decision?.reviewerId === 'smoke/reviewer-v1');
  check('reviewedChoice receipt exposes proof links', Array.isArray(reviewed.receipt?.proofLinks) && reviewed.receipt.proofLinks.length >= 3);
} catch (err) {
  check('reviewedChoice host-logit helper succeeds', false, err.message);
}

// ── 4. globals has standard WebGPU enum objects ─────────────────────────

console.log('\nglobals shape:');
const g = mod.globals;
check('globals.GPUBufferUsage exists', g.GPUBufferUsage != null);
check('globals.GPUBufferUsage.STORAGE', typeof g.GPUBufferUsage?.STORAGE === 'number');
check('globals.GPUShaderStage exists', g.GPUShaderStage != null);
check('globals.GPUShaderStage.COMPUTE', typeof g.GPUShaderStage?.COMPUTE === 'number');
check('globals.GPUMapMode exists', g.GPUMapMode != null);
check('globals.GPUMapMode.READ', typeof g.GPUMapMode?.READ === 'number');

// ── 5. createGpuNamespace returns same shape as gpu ─────────────────────

console.log('\ncreateGpuNamespace shape:');
const ns = mod.createGpuNamespace();
check('createGpuNamespace() returns object', typeof ns === 'object' && ns != null);
check('namespace.requestDevice', typeof ns.requestDevice === 'function');
check('namespace.bind', typeof ns.bind === 'function');

// ── 6. Compute surface ──────────────────────────────────────────────────

console.log('\ncompute surface:');
let compute;
try {
  compute = await import('../../src/compute.js');
  check('compute import succeeds', true);
} catch (err) {
  check('compute import succeeds', false, err.message);
}

if (compute) {
  check('compute.gpu exists', compute.gpu != null);
  check('compute.createGpuNamespace', typeof compute.createGpuNamespace === 'function');
  check('compute.create', typeof compute.create === 'function');
  check('compute.requestDevice', typeof compute.requestDevice === 'function');
  check('compute.requestAdapter', typeof compute.requestAdapter === 'function');
  check('compute.providerInfo', typeof compute.providerInfo === 'function');
  check('compute.globals exists', compute.globals != null && typeof compute.globals === 'object');
  check('compute.gpu.requestDevice', typeof compute.gpu?.requestDevice === 'function');
  check('compute.gpu.bind', typeof compute.gpu?.bind === 'function');
}

// ── 7. Doe runtime tooling surface ──────────────────────────────────────

console.log('\ndoe runtime tooling surface:');
try {
  const runtime = mod.createDoeRuntime();
  check('createDoeRuntime() returns object', typeof runtime === 'object' && runtime != null);
  check('runtime.runBench is a function', typeof runtime.runBench === 'function');
} catch {
  // createDoeRuntime throws when doe-zig-runtime binary is not built/found.
  // This is expected in CI or before building the runtime — skip gracefully.
  console.log('  skip: createDoeRuntime (doe-zig-runtime binary not found)');
}

// ── Results ─────────────────────────────────────────────────────────────

console.log(`\nResults: ${passed} passed, ${failed} failed`);
process.exitCode = failed > 0 ? 1 : 0;

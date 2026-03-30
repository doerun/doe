#!/usr/bin/env node
// Integration test for doe-gpu namespace.
// Verifies that the gpu namespace works end-to-end with a real device.
// Requires a GPU (or working native addon); tests that cannot acquire a device
// are skipped with an actionable message.
//
// Usage:
//   node test/integration/test-integration-gpu-namespace.js
//
// Exit codes:
//   0  All checks passed (or skipped due to no GPU)
//   1  A check failed (actionable error printed)

import { readFileSync } from 'node:fs';

import { DOE_DETERMINISM_POLICY_REGISTRY } from '../../src/vendor/doe-determinism-policy.js';
import { DOE_NUMERIC_STABILITY_POLICY_REGISTRY } from '../../src/vendor/doe-numeric-stability-policy.js';

let passed = 0;
let failed = 0;
let skipped = 0;

function check(label, condition, detail) {
  if (condition) {
    passed++;
    console.log(`  ok: ${label}`);
  } else {
    failed++;
    console.error(`  FAIL: ${label}${detail ? ' -- ' + detail : ''}`);
  }
}

function skip(label) {
  skipped++;
  console.log(`  SKIP: ${label}`);
}

function isDeviceUnavailableError(err) {
  const msg = err?.message ?? '';
  return (
    msg.includes('not found') ||
    msg.includes('unavailable') ||
    msg.includes('No adapter') ||
    msg.includes('no adapter') ||
    msg.includes('not supported') ||
    msg.includes('ENOENT') ||
    msg.includes('Could not load')
  );
}

console.log('=== doe-gpu integration: gpu namespace ===\n');

// ── Import ──────────────────────────────────────────────────────────────

let mod;
try {
  mod = await import('../../src/index.js');
  check('import doe-gpu succeeds', true);
} catch (err) {
  check('import doe-gpu succeeds', false, err.message);
  process.exit(1);
}

const { gpu, createGpuNamespace, requestDevice } = mod;

// ── 0. determinism policy registry sync ────────────────────────────────

console.log('\n0. determinism policy registry sync');

try {
  const repoRegistry = JSON.parse(
    readFileSync(new URL('../../../../config/determinism-policy.json', import.meta.url), 'utf8'),
  );
  check(
    'determinism policy registry version matches config',
    DOE_DETERMINISM_POLICY_REGISTRY.registryVersion === repoRegistry.registryVersion,
    JSON.stringify({
      package: DOE_DETERMINISM_POLICY_REGISTRY.registryVersion,
      repo: repoRegistry.registryVersion,
    }),
  );
  check(
    'stable-token policy id matches config',
    DOE_DETERMINISM_POLICY_REGISTRY.stableToken.policyId === repoRegistry.stableToken.policyId,
    JSON.stringify({
      package: DOE_DETERMINISM_POLICY_REGISTRY.stableToken.policyId,
      repo: repoRegistry.stableToken.policyId,
    }),
  );
  check(
    'stable-choice default policy id matches config',
    DOE_DETERMINISM_POLICY_REGISTRY.stableChoice.defaultPolicyId === repoRegistry.stableChoice.defaultPolicyId,
    JSON.stringify({
      package: DOE_DETERMINISM_POLICY_REGISTRY.stableChoice.defaultPolicyId,
      repo: repoRegistry.stableChoice.defaultPolicyId,
    }),
  );
  check(
    'reviewed-choice default policy id matches config',
    DOE_DETERMINISM_POLICY_REGISTRY.reviewedChoice.defaultPolicyId === repoRegistry.reviewedChoice.defaultPolicyId,
    JSON.stringify({
      package: DOE_DETERMINISM_POLICY_REGISTRY.reviewedChoice.defaultPolicyId,
      repo: repoRegistry.reviewedChoice.defaultPolicyId,
    }),
  );
} catch (err) {
  check('determinism policy registry sync', false, err.message);
}

console.log('\n0b. numeric stability policy registry sync');

try {
  const repoRegistry = JSON.parse(
    readFileSync(new URL('../../../../config/numeric-stability-policy.json', import.meta.url), 'utf8'),
  );
  check(
    'numeric stability registry version matches config',
    DOE_NUMERIC_STABILITY_POLICY_REGISTRY.registryVersion === repoRegistry.registryVersion,
    JSON.stringify({
      package: DOE_NUMERIC_STABILITY_POLICY_REGISTRY.registryVersion,
      repo: repoRegistry.registryVersion,
    }),
  );
  check(
    'numeric stability policy path matches config contract',
    DOE_NUMERIC_STABILITY_POLICY_REGISTRY.policyRegistryPath === 'config/numeric-stability-policy.json',
    DOE_NUMERIC_STABILITY_POLICY_REGISTRY.policyRegistryPath,
  );
  check(
    'numeric stability default trigger policy matches config',
    DOE_NUMERIC_STABILITY_POLICY_REGISTRY.matmulLogitsSlice.defaultTriggerPolicyId ===
      repoRegistry.triggerPolicies[0].triggerPolicyId,
    JSON.stringify({
      package: DOE_NUMERIC_STABILITY_POLICY_REGISTRY.matmulLogitsSlice.defaultTriggerPolicyId,
      repo: repoRegistry.triggerPolicies[0].triggerPolicyId,
    }),
  );
  check(
    'numeric stability default routing policy matches config',
    DOE_NUMERIC_STABILITY_POLICY_REGISTRY.matmulLogitsSlice.defaultRoutingPolicyId ===
      repoRegistry.routingPolicies[0].policyId,
    JSON.stringify({
      package: DOE_NUMERIC_STABILITY_POLICY_REGISTRY.matmulLogitsSlice.defaultRoutingPolicyId,
      repo: repoRegistry.routingPolicies[0].policyId,
    }),
  );
  check(
    'numeric stability default execution profile matches config',
    DOE_NUMERIC_STABILITY_POLICY_REGISTRY.defaultExecutionProfileId ===
      repoRegistry.defaultExecutionProfileId,
    JSON.stringify({
      package: DOE_NUMERIC_STABILITY_POLICY_REGISTRY.defaultExecutionProfileId,
      repo: repoRegistry.defaultExecutionProfileId,
    }),
  );
  check(
    'numeric stability execution profile count matches config',
    DOE_NUMERIC_STABILITY_POLICY_REGISTRY.executionProfiles.length ===
      repoRegistry.executionProfiles.length,
    JSON.stringify({
      package: DOE_NUMERIC_STABILITY_POLICY_REGISTRY.executionProfiles.length,
      repo: repoRegistry.executionProfiles.length,
    }),
  );
} catch (err) {
  check('numeric stability policy registry sync', false, err.message);
}

console.log('\n0c. numeric stability namespace shape');

{
  const bound = gpu.bind({});
  check('gpu.ordinaryExecution is function', typeof gpu.ordinaryExecution === 'function');
  check('gpu.bind({}).ordinaryExecution is function', typeof bound.ordinaryExecution === 'function');
  check('gpu.bind({}) exposes numericStability', bound.numericStability != null && typeof bound.numericStability === 'object');
  check(
    'gpu.bind({}).numericStability.matmulLogitsSlice is function',
    typeof bound.numericStability?.matmulLogitsSlice === 'function',
  );
  check(
    'gpu.bind({}).numericStability.ordinaryExecution is function',
    typeof bound.numericStability?.ordinaryExecution === 'function',
  );
  check(
    'gpu.bind({}).ordinaryExecution aliases numericStability.ordinaryExecution',
    bound.ordinaryExecution === bound.numericStability?.ordinaryExecution,
  );
}

// ── 1. gpu.requestDevice() — bound namespace shape ──────────────────────

console.log('\n1. gpu.requestDevice() — bound namespace shape');

try {
  const bound = await gpu.requestDevice();
  check('gpu.requestDevice() resolves', true);
  check('bound.device exists', bound.device != null && typeof bound.device === 'object');
  check('bound.buffer is object', bound.buffer != null && typeof bound.buffer === 'object');
  check('bound.buffer.create is function', typeof bound.buffer.create === 'function');
  check('bound.buffer.read is function', typeof bound.buffer.read === 'function');
  check('bound.kernel is object', bound.kernel != null && typeof bound.kernel === 'object');
  check('bound.kernel.create is function', typeof bound.kernel.create === 'function');
  check('bound.kernel.run is function', typeof bound.kernel.run === 'function');
  check('bound.determinism is object', bound.determinism != null && typeof bound.determinism === 'object');
  check('bound.determinism.stableToken is function', typeof bound.determinism.stableToken === 'function');
  check('bound.determinism.reviewedChoice is function', typeof bound.determinism.reviewedChoice === 'function');
  check('bound.compute is function', typeof bound.compute === 'function');
  check('bound.compute.begin is function', typeof bound.compute.begin === 'function');
  check('bound.commandEncoder is object', bound.commandEncoder != null && typeof bound.commandEncoder === 'object');
  check('bound.commandEncoder.create is function', typeof bound.commandEncoder.create === 'function');
  check('bound.determinism.stableChoice is function', typeof bound.determinism.stableChoice === 'function');
  check('bound.ordinaryExecution is function', typeof bound.ordinaryExecution === 'function');
  bound.device.destroy();
} catch (err) {
  if (isDeviceUnavailableError(err)) {
    skip('gpu.requestDevice() (no GPU available)');
  } else {
    check('gpu.requestDevice() resolves', false, err.message);
  }
}

// ── 2. gpu.bind(device) — manual bind ───────────────────────────────────

console.log('\n2. gpu.bind(device) — manual bind');

try {
  const rawDevice = await requestDevice();
  check('raw requestDevice() resolves', true);
  check('raw device is object', rawDevice != null && typeof rawDevice === 'object');

  const bound = gpu.bind(rawDevice);
  check('gpu.bind(device) returns object', bound != null && typeof bound === 'object');
  check('bound.device is same raw device', bound.device === rawDevice);
  check('bound.buffer.create is function', typeof bound.buffer.create === 'function');
  check('bound.buffer.read is function', typeof bound.buffer.read === 'function');
  check('bound.kernel is object', bound.kernel != null && typeof bound.kernel === 'object');
  check('bound.compute is function', typeof bound.compute === 'function');
  check('bound.commandEncoder is object', bound.commandEncoder != null && typeof bound.commandEncoder === 'object');
  rawDevice.destroy();
} catch (err) {
  if (isDeviceUnavailableError(err)) {
    skip('gpu.bind(device) (no GPU available)');
  } else {
    check('gpu.bind(device)', false, err.message);
  }
}

// ── 3. buffer.create() — various usage tokens ───────────────────────────

console.log('\n3. buffer.create() — various usage tokens');

try {
  const bound = await gpu.requestDevice();

  const uploadBuf = bound.buffer.create({ size: 64, usage: 'upload' });
  check('buffer.create upload succeeds', uploadBuf != null);
  check('upload buffer has size', uploadBuf.size === 64);

  const readbackBuf = bound.buffer.create({ size: 128, usage: 'readback' });
  check('buffer.create readback succeeds', readbackBuf != null);
  check('readback buffer has size', readbackBuf.size === 128);

  const storageBuf = bound.buffer.create({ size: 256, usage: 'storageReadWrite' });
  check('buffer.create storageReadWrite succeeds', storageBuf != null);
  check('storageReadWrite buffer has size', storageBuf.size === 256);

  // buffer.create with data
  const dataBuf = bound.buffer.create({ data: new Float32Array([1, 2, 3, 4]) });
  check('buffer.create with data succeeds', dataBuf != null);
  check('data buffer has correct size', dataBuf.size === 16);

  uploadBuf.destroy();
  readbackBuf.destroy();
  storageBuf.destroy();
  dataBuf.destroy();
  bound.device.destroy();
} catch (err) {
  if (isDeviceUnavailableError(err)) {
    skip('buffer.create (no GPU available)');
  } else {
    check('buffer.create', false, err.message);
  }
}

// ── 4. createGpuNamespace() — custom namespace ──────────────────────────

console.log('\n4. createGpuNamespace() — custom namespace');

{
  const ns = createGpuNamespace();
  check('createGpuNamespace() returns object', typeof ns === 'object' && ns != null);
  check('namespace.requestDevice is function', typeof ns.requestDevice === 'function');
  check('namespace.bind is function', typeof ns.bind === 'function');
}

{
  // namespace created with a custom requestDevice
  const ns = createGpuNamespace({ requestDevice });
  check('custom namespace has requestDevice', typeof ns.requestDevice === 'function');
  check('custom namespace has bind', typeof ns.bind === 'function');

  try {
    const bound = await ns.requestDevice();
    check('custom namespace requestDevice resolves', true);
    check('custom namespace bound has device', bound.device != null);
    check('custom namespace bound has buffer', bound.buffer != null);
    check('custom namespace bound has kernel', bound.kernel != null);
    check('custom namespace bound has compute', typeof bound.compute === 'function');
    check('custom namespace bound has commandEncoder', bound.commandEncoder != null);
    bound.device.destroy();
  } catch (err) {
    if (isDeviceUnavailableError(err)) {
      skip('custom namespace requestDevice (no GPU available)');
    } else {
      check('custom namespace requestDevice', false, err.message);
    }
  }
}

// ── 4b. determinism.stableToken() — host and buffer paths ──────────────

console.log('\n4b. determinism.stableToken() — host and buffer paths');

try {
  const bound = await gpu.requestDevice();

  const hostResult = await bound.determinism.stableToken({
    logits: new Float32Array([0, 7, 7, 3]),
  });
  check('stableToken host logits returns lowest tied token', hostResult.token === 1, JSON.stringify(hostResult));
  check('stableToken host logits policyRegistryPath=config/determinism-policy.json', hostResult.receipt.policyRegistryPath === 'config/determinism-policy.json');
  check('stableToken host logits policyRegistryVersion=2026-03-28', hostResult.receipt.policyRegistryVersion === '2026-03-28');
  check('stableToken host logits policyId=stable-token/lowest-index-among-max-v1', hostResult.receipt.policyId === 'stable-token/lowest-index-among-max-v1');
  check('stableToken host logits sourceKind=host-bytes', hostResult.receipt.sourceKind === 'host-bytes');
  check('stableToken host logits tiedMaxCount=2', hostResult.receipt.tiedMaxCount === 2);
  check('stableToken host logits selectedBy=stable-token-policy', hostResult.receipt.selectedBy === 'stable-token-policy');

  const logitsBuffer = bound.buffer.create({
    data: new Float32Array([0, 7, 7, 3]),
    usage: ['storageRead', 'readback'],
  });
  const bufferResult = await bound.determinism.stableToken({
    logits: logitsBuffer,
    vocabSize: 4,
  });
  check('stableToken buffer logits returns lowest tied token', bufferResult.token === 1, JSON.stringify(bufferResult));
  check('stableToken buffer logits sourceKind=buffer-readback', bufferResult.receipt.sourceKind === 'buffer-readback');
  check('stableToken buffer logits tiedMaxCount=2', bufferResult.receipt.tiedMaxCount === 2);
  check(
    'stableToken buffer and host receipts agree on token',
    bufferResult.receipt.token === hostResult.receipt.token,
  );
  check('stableToken receipt exposes proof links', Array.isArray(hostResult.receipt.proofLinks) && hostResult.receipt.proofLinks.length >= 1);

  logitsBuffer.destroy();
  bound.device.destroy();
} catch (err) {
  if (isDeviceUnavailableError(err)) {
    skip('determinism.stableToken (no GPU available)');
  } else {
    check('determinism.stableToken', false, err.message);
  }
}

// ── 4c. determinism.stableChoice() — host and buffer paths ─────────────

console.log('\n4c. determinism.stableChoice() — host and buffer paths');

try {
  const bound = await gpu.requestDevice();

  const hostResult = await bound.determinism.stableChoice({
    logits: new Float32Array([0, 7, 7, 3]),
    candidates: [
      { token: 2, label: 'unsafe' },
      { token: 1, label: 'safe' },
    ],
    ambiguityTrigger: { mode: 'exact-max-tie' },
    policyId: 'integration/fixed-priority-unsafe-first',
    triggerPolicyId: 'exact-max-tie-v1',
    candidateSetId: 'safety.safe_unsafe',
    candidateSetSource: 'fixture-declared',
  });
  check('stableChoice host logits returns fixed-priority candidate', hostResult.token === 2, JSON.stringify(hostResult));
  check('stableChoice host logits policyRegistryPath=config/determinism-policy.json', hostResult.receipt.policyRegistryPath === 'config/determinism-policy.json');
  check('stableChoice host logits policyRegistryVersion=2026-03-28', hostResult.receipt.policyRegistryVersion === '2026-03-28');
  check('stableChoice host logits sourceKind=host-bytes', hostResult.receipt.sourceKind === 'host-bytes');
  check('stableChoice host logits ambiguityTriggered=true', hostResult.receipt.ambiguityTriggered === true);
  check('stableChoice host logits selectedBy=stable-choice-policy', hostResult.receipt.selectedBy === 'stable-choice-policy');
  check('stableChoice host logits preserves triggerPolicyId', hostResult.receipt.triggerPolicyId === 'exact-max-tie-v1');
  check('stableChoice host logits preserves candidateSetId', hostResult.receipt.candidateSetId === 'safety.safe_unsafe');
  check('stableChoice host logits preserves candidateSetSource', hostResult.receipt.candidateSetSource === 'fixture-declared');

  const logitsBuffer = bound.buffer.create({
    data: new Float32Array([0, 7, 7, 3]),
    usage: ['storageRead', 'readback'],
  });
  const bufferResult = await bound.determinism.stableChoice({
    logits: logitsBuffer,
    vocabSize: 4,
    candidates: [
      { token: 2, label: 'unsafe' },
      { token: 1, label: 'safe' },
    ],
    ambiguityTrigger: { mode: 'exact-max-tie' },
    policyId: 'integration/fixed-priority-unsafe-first',
    triggerPolicyId: 'exact-max-tie-v1',
    candidateSetId: 'safety.safe_unsafe',
    candidateSetSource: 'fixture-declared',
  });
  check('stableChoice buffer logits returns fixed-priority candidate', bufferResult.token === 2, JSON.stringify(bufferResult));
  check('stableChoice buffer logits sourceKind=buffer-readback', bufferResult.receipt.sourceKind === 'buffer-readback');
  check('stableChoice buffer and host receipts agree on token', bufferResult.receipt.token === hostResult.receipt.token);

  const marginResult = await bound.determinism.stableChoice({
    logits: new Float32Array([0, 9, 8.97, 3]),
    candidates: [
      { token: 2, label: 'unsafe' },
      { token: 1, label: 'safe' },
    ],
    ambiguityTrigger: { mode: 'candidate-margin-band', epsilon: 0.05 },
    policyId: 'integration/fixed-priority-unsafe-first',
    triggerPolicyId: 'candidate-margin-band-v1',
    candidateSetId: 'safety.safe_unsafe',
    candidateSetSource: 'fixture-declared',
  });
  check('stableChoice margin band can override stable-token fallback', marginResult.token === 2, JSON.stringify(marginResult));
  check('stableChoice margin band records ambiguity trigger mode', marginResult.receipt.ambiguityTrigger.mode === 'candidate-margin-band');
  check('stableChoice margin band preserves triggerPolicyId', marginResult.receipt.triggerPolicyId === 'candidate-margin-band-v1');
  check('stableChoice receipt exposes proof links', Array.isArray(hostResult.receipt.proofLinks) && hostResult.receipt.proofLinks.length >= 3);

  logitsBuffer.destroy();
  bound.device.destroy();
} catch (err) {
  if (isDeviceUnavailableError(err)) {
    skip('determinism.stableChoice (no GPU available)');
  } else {
    check('determinism.stableChoice', false, err.message);
  }
}

// ── 4d. determinism.reviewedChoice() — host and buffer paths ───────────

console.log('\n4d. determinism.reviewedChoice() — host and buffer paths');

try {
  const bound = await gpu.requestDevice();

  const hostResult = await bound.determinism.reviewedChoice({
    logits: new Float32Array([0, 7, 7, 3]),
    candidates: [
      { token: 2, label: 'unsafe' },
      { token: 1, label: 'safe' },
    ],
    ambiguityTrigger: { mode: 'exact-max-tie' },
    reviewPolicyId: 'integration/reviewer-v1',
    triggerPolicyId: 'exact-max-tie-v1',
    candidateSetId: 'safety.safe_unsafe',
    candidateSetSource: 'fixture-declared',
    decision: {
      token: 1,
      label: 'safe',
      reviewerId: 'integration/reviewer-v1',
      decisionId: 'integration-review-001',
      decisionRef: 'receipt://integration-review-001',
    },
  });
  check('reviewedChoice host logits honors reviewed token', hostResult.token === 1, JSON.stringify(hostResult));
  check('reviewedChoice host logits policyRegistryPath=config/determinism-policy.json', hostResult.receipt.policyRegistryPath === 'config/determinism-policy.json');
  check('reviewedChoice host logits policyRegistryVersion=2026-03-28', hostResult.receipt.policyRegistryVersion === '2026-03-28');
  check('reviewedChoice host logits sourceKind=host-bytes', hostResult.receipt.sourceKind === 'host-bytes');
  check('reviewedChoice host logits ambiguityTriggered=true', hostResult.receipt.ambiguityTriggered === true);
  check('reviewedChoice host logits decisionAccepted=true', hostResult.receipt.decisionAccepted === true);
  check('reviewedChoice host logits selectedBy=reviewed-choice-decision', hostResult.receipt.selectedBy === 'reviewed-choice-decision');
  check('reviewedChoice host logits preserves triggerPolicyId', hostResult.receipt.triggerPolicyId === 'exact-max-tie-v1');
  check('reviewedChoice host logits preserves reviewerId', hostResult.receipt.decision.reviewerId === 'integration/reviewer-v1');

  const logitsBuffer = bound.buffer.create({
    data: new Float32Array([0, 7, 7, 3]),
    usage: ['storageRead', 'readback'],
  });
  const bufferResult = await bound.determinism.reviewedChoice({
    logits: logitsBuffer,
    vocabSize: 4,
    candidates: [
      { token: 2, label: 'unsafe' },
      { token: 1, label: 'safe' },
    ],
    ambiguityTrigger: { mode: 'exact-max-tie' },
    reviewPolicyId: 'integration/reviewer-v1',
    triggerPolicyId: 'exact-max-tie-v1',
    candidateSetId: 'safety.safe_unsafe',
    candidateSetSource: 'fixture-declared',
    decision: {
      token: 1,
      label: 'safe',
      reviewerId: 'integration/reviewer-v1',
      decisionId: 'integration-review-001',
    },
  });
  check('reviewedChoice buffer logits honors reviewed token', bufferResult.token === 1, JSON.stringify(bufferResult));
  check('reviewedChoice buffer logits sourceKind=buffer-readback', bufferResult.receipt.sourceKind === 'buffer-readback');
  check('reviewedChoice buffer and host receipts agree on token', bufferResult.receipt.token === hostResult.receipt.token);
  check('reviewedChoice receipt exposes proof links', Array.isArray(hostResult.receipt.proofLinks) && hostResult.receipt.proofLinks.length >= 3);

  logitsBuffer.destroy();
  bound.device.destroy();
} catch (err) {
  if (isDeviceUnavailableError(err)) {
    skip('determinism.reviewedChoice (no GPU available)');
  } else {
    check('determinism.reviewedChoice', false, err.message);
  }
}

// ── 5. Error cases ──────────────────────────────────────────────────────

console.log('\n5. Error cases');

// 5a. namespace without requestDevice impl throws on requestDevice()
{
  const emptyNs = createGpuNamespace();
  try {
    await emptyNs.requestDevice();
    check('empty namespace requestDevice throws', false, 'did not throw');
  } catch (err) {
    check(
      'empty namespace requestDevice throws',
      err.message.includes('unavailable'),
      err.message,
    );
  }
}

// 5b. buffer.create with invalid usage token
try {
  const bound = await gpu.requestDevice();
  try {
    bound.buffer.create({ size: 64, usage: 'invalidToken' });
    check('buffer.create invalid usage throws', false, 'did not throw');
  } catch (err) {
    check(
      'buffer.create invalid usage throws',
      err.message.includes('Unknown') || err.message.includes('unknown') || err.message.includes('usage'),
      err.message,
    );
  }
  bound.device.destroy();
} catch (err) {
  if (isDeviceUnavailableError(err)) {
    skip('buffer.create invalid usage (no GPU available)');
  } else {
    check('buffer.create invalid usage', false, err.message);
  }
}

// 5c. buffer.create without required options
try {
  const bound = await gpu.requestDevice();
  try {
    bound.buffer.create(null);
    check('buffer.create null throws', false, 'did not throw');
  } catch (err) {
    check(
      'buffer.create null throws',
      err.message.includes('object') || err.message.includes('options'),
      err.message,
    );
  }
  bound.device.destroy();
} catch (err) {
  if (isDeviceUnavailableError(err)) {
    skip('buffer.create null (no GPU available)');
  } else {
    check('buffer.create null', false, err.message);
  }
}

// ── Results ─────────────────────────────────────────────────────────────

console.log(`\nResults: ${passed} passed, ${failed} failed, ${skipped} skipped`);
process.exitCode = failed > 0 ? 1 : 0;

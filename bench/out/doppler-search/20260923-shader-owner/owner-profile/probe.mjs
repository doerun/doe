import { instrument } from '/home/x/deco/doe/bench/out/doppler-search/20260923-shader-owner/owner-profile/instrument.mjs';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { openCapsule } from 'doppler-gpu/host';
import { getDevice } from 'doppler-gpu/tooling/device';
import { evaluateRerankReference } from '/var/tmp/doppler-startup-reuse-20260920/consumer/node_modules/doppler-gpu/src/config/rerank-reference.js';
import { destroyBufferPool } from '/var/tmp/doppler-startup-reuse-20260920/consumer/node_modules/doppler-gpu/src/memory/buffer-pool.js';
import { destroyDevice } from '/var/tmp/doppler-startup-reuse-20260920/consumer/node_modules/doppler-gpu/src/gpu/device.js';
import { bootstrapNodeWebGPUProvider } from '/home/x/deco/doe/packages/doe-gpu/src/node-webgpu.js';
const root = '/var/tmp/doppler-release-20260907-restored-02/retained/node-capsule';
const destination = process.env.DOPPLER_TIMING_OUTPUT;
const policy = JSON.parse(await fs.readFile('/home/x/deco/doe/bench/out/doppler-search/20260923-shader-owner/owner-profile/policy.json', 'utf8'));
const selected = process.env.DOPPLER_TIMING_PROVIDER;
assert(['doe', 'dawn'].includes(selected));
await fs.mkdir(destination, { recursive: false });
const read = async path => JSON.parse(await fs.readFile(path, 'utf8'));
const hash = async path => createHash('sha256').update(await fs.readFile(path)).digest('hex');
const options = await read(`${root}/current-open-options.json`);
const referencePath = '/var/tmp/doppler-release-20260907-restored-02/retained/references/reranker-reference.json';
const reference = await read(referencePath);
options.releasePolicy.now = new Date().toISOString();
options.persistReleaseCheckpoint = checkpoint => fs.writeFile(`${destination}/observed-checkpoint.json`, JSON.stringify(checkpoint, null, 2));
const report = { diagnostic: true, passed: false, referencePath, referenceSha256: await hash(referencePath),
 capsuleSha256: await hash(`${root}/distribution/capsule-v3.json`), librarySha256: await hash(selected === 'doe' ? process.env.DOE_WEBGPU_LIB : policy.dawnNative),
 executions: [], networkRequests: [] };
const moduleUrl = selected === 'doe' ? 'file:///home/x/deco/doe/packages/doe-gpu/src/native.js' : 'file:///home/x/deco/doe/bench/node_modules/webgpu/index.js';
const provider = await bootstrapNodeWebGPUProvider(moduleUrl, { provider: {
 id: selected, kind: 'module', module: moduleUrl,
 gpu: {kind:'factory', path:'create', args:[policy.createArgs]},
 globals: Object.fromEntries(['GPUBufferUsage','GPUShaderStage','GPUMapMode','GPUTextureUsage'].map(key => [key, `globals.${key}`])),
} });
report.provider = provider.module.providerInfo?.() ?? provider.receipt;
report.selectedProvider = selected; report.policy = policy; report.startedAt = new Date().toISOString();
report.scriptSha256 = await hash('/home/x/deco/doe/bench/out/doppler-search/20260923-shader-owner/owner-profile/probe.mjs'); report.adapter = provider.session.adapter.info;
console.log('PROVIDER', JSON.stringify(report.provider), JSON.stringify(report.adapter));
let session; let diagnostic;
const originalFetch = globalThis.fetch;
globalThis.fetch = async input => { report.networkRequests.push(String(input)); throw Error('Network disabled for retained-model diagnostic'); };
try {
 report.stage = 'open';
 const loadStart = performance.now();
 session = await openCapsule(`${root}/distribution/capsule-v3.json`, options);
 report.loadMs = performance.now() - loadStart;
 report.plan = session.selectedTargetPlanDigest;
 console.log('OPENED', report.plan);
 const application = options.releaseEvents.at(-1).release.application;
 report.stage = 'rerank'; diagnostic = instrument(getDevice());
 for (let repeat = 0; repeat < policy.warmupRuns + 2; repeat++) {
  if (repeat >= policy.warmupRuns) await diagnostic.start();
  const started = performance.now();
  const receipt = await session.rerank({ application, ...reference.input });
  const elapsedMs = performance.now() - started;
  if (repeat >= policy.warmupRuns) {
   const observed = await diagnostic.stop();
   await fs.writeFile(`${destination}/profile-${repeat}.json`, JSON.stringify(observed));
  }
  const comparison = evaluateRerankReference(reference, { input: reference.input,
   scoringConfig: session.manifest.inference.rerank, outputs: receipt.evidence.scores });
  report.executions.push({ repeat, warmup: repeat < policy.warmupRuns, elapsedMs, receipt, comparison });
  console.log('SAMPLE', JSON.stringify({ repeat, elapsedMs, passed: comparison.passed }));
  assert(comparison.passed, 'Frozen independent source oracle');
  assert.equal(session.selectedTargetPlanDigest, report.plan);
 }
 report.passed = true; report.stage = 'complete';
} catch (error) { report.error = { message: error.message, stack: error.stack }; console.log('FAILURE', error.stack); }
finally {
 diagnostic?.close();
 report.cleanupErrors = [];
 for (const close of [() => session?.close(), () => destroyBufferPool(getDevice()), () => getDevice()?.queue.onSubmittedWorkDone(),
  () => new Promise(resolve => setImmediate(resolve)), destroyDevice, () => provider.session.close()]) {
  try { await close(); } catch (error) { report.cleanupErrors.push(error.message); }
 }
 globalThis.fetch = originalFetch;
 report.passed &&= report.cleanupErrors.length === 0;
 await fs.writeFile(`${destination}/result.json`, JSON.stringify(report, null, 2));
 console.log('CLOSED', JSON.stringify(report.cleanupErrors));
}
if (!report.passed) process.exitCode = 1;

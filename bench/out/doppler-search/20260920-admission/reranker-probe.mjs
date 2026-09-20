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
const destination = '/home/x/deco/doe/bench/out/doppler-search/20260920-admission';
const read = async path => JSON.parse(await fs.readFile(path, 'utf8'));
const hash = async path => createHash('sha256').update(await fs.readFile(path)).digest('hex');
const options = await read(`${root}/current-open-options.json`);
const referencePath = '/var/tmp/doppler-release-20260907-restored-02/retained/references/reranker-reference.json';
const reference = await read(referencePath);
options.releasePolicy.now = new Date().toISOString();
options.persistReleaseCheckpoint = checkpoint => fs.writeFile(`${destination}/observed-checkpoint.json`, JSON.stringify(checkpoint, null, 2));
const report = { diagnostic: true, passed: false, referencePath, referenceSha256: await hash(referencePath),
 capsuleSha256: await hash(`${root}/distribution/capsule-v3.json`), librarySha256: await hash(process.env.DOE_WEBGPU_LIB),
 executions: [], networkRequests: [] };
const provider = await bootstrapNodeWebGPUProvider('file:///home/x/deco/doe/packages/doe-gpu/src/native.js');
report.provider = provider.module.providerInfo(); report.adapter = provider.session.adapter.info;
console.log('PROVIDER', JSON.stringify(report.provider), JSON.stringify(report.adapter));
let session;
const originalFetch = globalThis.fetch;
globalThis.fetch = async input => { report.networkRequests.push(String(input)); throw Error('Network disabled for retained-model diagnostic'); };
try {
 report.stage = 'open';
 session = await openCapsule(`${root}/distribution/capsule-v3.json`, options);
 report.plan = session.selectedTargetPlanDigest;
 console.log('OPENED', report.plan);
 const application = options.releaseEvents.at(-1).release.application;
 report.stage = 'rerank';
 for (let repeat = 0; repeat < 2; repeat++) {
  const receipt = await session.rerank({ application, ...reference.input });
  const comparison = evaluateRerankReference(reference, { input: reference.input,
   scoringConfig: session.manifest.inference.rerank, outputs: receipt.evidence.scores });
  report.executions.push({ repeat, receipt, comparison });
  console.log('COMPARISON', repeat, JSON.stringify(comparison));
  assert(comparison.passed, 'Frozen independent source oracle');
  assert.equal(session.selectedTargetPlanDigest, report.plan);
 }
 report.passed = true; report.stage = 'complete';
} catch (error) { report.error = { message: error.message, stack: error.stack }; console.log('FAILURE', error.stack); }
finally {
 report.cleanupErrors = [];
 for (const close of [() => session?.close(), () => destroyBufferPool(getDevice()), () => getDevice()?.queue.onSubmittedWorkDone(),
  () => new Promise(resolve => setImmediate(resolve)), destroyDevice, () => provider.session.close()]) {
  try { await close(); } catch (error) { report.cleanupErrors.push(error.message); }
 }
 globalThis.fetch = originalFetch;
 report.passed &&= report.cleanupErrors.length === 0;
 await fs.writeFile(`${destination}/reranker-result.json`, JSON.stringify(report, null, 2));
 console.log('CLOSED', JSON.stringify(report.cleanupErrors));
}
if (!report.passed) process.exitCode = 1;

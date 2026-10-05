// Public Doppler full-generation qualification before any performance experiment.
import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { observeDevicePhases } from './observe-phases.mjs';

const [contractPath, providersPath, referencePath, lane, output, mode = 'qualification', processIndex = '0'] = process.argv.slice(2);
assert(['qualification', 'profile', 'timing'].includes(mode));
assert(['doe', 'dawn'].includes(lane), 'Expected doe or dawn lane');
const read = async (path) => JSON.parse(await readFile(path));
const hash = async (path) => createHash('sha256').update(await readFile(path)).digest('hex');
const contract = await read(contractPath);
const providers = await read(providersPath);
const reference = await read(referencePath);
assert.equal(contract.performance.residentRuns, 2, 'This cohort declares one balanced A/B pair');
if (mode !== 'qualification') {
  for (const provider of ['doe', 'dawn']) {
    const receipt = await read(output.replace(/[^/]+$/, `${provider}-qualification.json`));
    assert(receipt.passed, `${provider} baseline is not qualified`);
    assert.equal(receipt.contractSha256, await hash(contractPath));
    assert.equal(receipt.providerManifestSha256, await hash(providersPath));
  }
}
assert.equal(await hash(contractPath), reference.contractSha256);
for (const artifact of [...providers.archives, ...providers.files]) assert.equal(await hash(artifact.path), artifact.sha256, artifact.path);
if (lane === 'doe') process.env.DOE_WEBGPU_LIB = providers.doeLibrary;
const provider = await import(pathToFileURL(providers[`${lane}Module`]).href);
Object.assign(globalThis, provider.globals);
const gpu = provider.create(['backend=vulkan']);
Object.defineProperty(globalThis, 'navigator', { value: { gpu }, configurable: true });
const devices = [];
const destroyed = new WeakSet();
const phaseEvents = [];
let phase = "provider-init";
const requestAdapter = gpu.requestAdapter.bind(gpu);
gpu.requestAdapter = async (options) => {
  const adapter = await requestAdapter(options);
  const requestDevice = adapter.requestDevice.bind(adapter);
  adapter.requestDevice = async (descriptor) => {
    const device = await requestDevice(descriptor);
    const destroy = device.destroy.bind(device);
    device.destroy = () => { const result = destroy();destroyed.add(device);return result; };
    if (mode === 'profile') observeDevicePhases(device, phaseEvents, () => phase);
    devices.push(device);return device;
  };
  return adapter;
};
const api = await import(pathToFileURL(providers.dopplerModule).href);
const rows = [];
let model;
let failure;
let cleanup;
const started = performance.now();
let loadMs;
const recordGeneration = async (test, label) => {
  phase = label;
  const expected = reference.cases.find((entry) => entry.id === test.id);
  const options = { ...contract.generation, maxTokens: test.maxTokens, stopSequences: test.stopSequences };
  delete options.eosTokenIds;
  assert.deepEqual(model.advanced.tokenizePrompt(test.prompt, options), expected.promptTokenIds);
  const tokens = [];
  const chunks = [];
  const stream = [];
  const start = performance.now();
  for await (const chunk of model.generate(test.prompt, { ...options, onToken(id) { tokens.push(id); } })) {
    chunks.push(chunk);stream.push({ elapsedMs: performance.now() - start, chunk });
  }
  const completeMs = performance.now() - start;
  const stats = model.advanced.getStats();
  const observed = { id: test.id, label, tokenIds: tokens, outputText: chunks.join(""), stream, stats,
    firstTokenMs: stream[0]?.elapsedMs ?? null, completeMs, rssBytes: process.memoryUsage().rss };
  rows.push(observed);
  assert.deepEqual(tokens, expected.tokenIds, `${test.id}: complete generated token mismatch`);
  assert.equal(observed.outputText, expected.outputText, `${test.id}: complete decoded stream mismatch`);
  assert.equal(stats.stopReason, { eos: "stop-token", max_tokens: "max-tokens", stop_sequence: "stop-sequence" }[expected.stopReason], `${test.id}: stopping mismatch`);
  console.log(JSON.stringify({ lane, mode, label, id: test.id, firstTokenMs: observed.firstTokenMs, completeMs, stopReason: stats.stopReason }));
};
try {
  phase = 'load';
  const loadStarted = performance.now();
  model = await api.load({ url: pathToFileURL(contract.model.path + '/').href }, { cache: false, isolatedLoader: true, onProgress() {} });
  loadMs = performance.now() - loadStarted;
  const identity = model.deviceInfo;
  assert(!/swiftshader|llvmpipe|software/i.test(JSON.stringify(identity)));
  assert(/amd|radeon/i.test(JSON.stringify(identity)), 'Expected physical AMD adapter');
  console.log(JSON.stringify({ lane, stage: 'loaded', identity, loadMs }));
  if (mode === 'qualification') {
    for (const test of contract.cases) await recordGeneration(test, test.id);
  } else {
    const test = contract.cases[0];
    await recordGeneration(test, 'initial');
    for (let index = 0; index < contract.performance.warmupResidentRuns; index++) await recordGeneration(test, 'warmup');
    for (const label of Number(processIndex) % 2 ? ['B', 'A'] : ['A', 'B']) await recordGeneration(test, label);
  }
  const test = contract.cases[0];
  const controller = new AbortController();
  phase = "cancellation";
  let chunks = 0;
  let cancelledText = "";
  let aborted;
  try {
    const options = { ...contract.generation, maxTokens: test.maxTokens, signal: controller.signal };
    delete options.eosTokenIds;
    for await (const chunk of model.generate(test.prompt, options)) {
      cancelledText += chunk;
      if (++chunks === contract.cancellation.abortAfterStreamChunks) controller.abort();
    }
  } catch (error) { aborted = { name: error.name, message: error.message }; }
  assert(controller.signal.aborted);
  assert.equal(chunks, contract.cancellation.abortAfterStreamChunks, "Late stream chunks after cancellation");
  assert(reference.cases[0].outputText.startsWith(cancelledText));
  for (const device of devices) if (!destroyed.has(device)) await device.queue.onSubmittedWorkDone();
  const options = { ...contract.generation, maxTokens: test.maxTokens };delete options.eosTokenIds;
  let after = '';
  for await (const chunk of model.generate(test.prompt, options)) after += chunk;
  assert.equal(after, reference.cases[0].outputText, 'Conversation after cancellation changed');
  rows.push({ id: 'cancellation', chunks, cancelledText, aborted: aborted ?? null, followingOutputText: after });
} catch (error) { failure = { name: error.name, message: error.message, stack: error.stack }; }
finally {
  try {
    phase = "cleanup";
    const cleanupStart = performance.now();
    await model?.unload();
    for (const device of devices) if (!destroyed.has(device)) { await device.queue.onSubmittedWorkDone();device.destroy(); }
    cleanup = { unloaded: model ? !model.loaded : null, devicesDestroyed: devices.filter((device) => destroyed.has(device)).length, elapsedMs: performance.now() - cleanupStart };
  } catch (error) { cleanup = { error: error.message }; }
  await writeFile(output, JSON.stringify({ schemaVersion: 1, classification: mode, lane, mode, processIndex: Number(processIndex), loadMs, phaseEvents,
    runnerSha256: await hash(fileURLToPath(import.meta.url)), completeProcessWorkMs: performance.now() - started, peakProcessRssBytes: process.resourceUsage().maxRSS * 1024,
    contractSha256: await hash(contractPath), providerManifestSha256: await hash(providersPath),
    referenceSha256: await hash(referencePath), providerInfo: provider.providerInfo?.() ?? null,
    rows, cleanup, passed: !failure && !cleanup.error, failure: failure ?? null }, null, 2) + '\n');
}
if (failure || cleanup.error) { console.error(failure ?? cleanup);process.exitCode = 1; }

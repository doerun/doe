// Observe standalone installation and actual native loading around the unchanged runner.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, realpathSync, existsSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { networkInterfaces } from 'node:os';

const [lane, label] = process.argv.slice(2);
assert(['doe', 'dawn'].includes(lane));
const read = (path) => JSON.parse(readFileSync(path, 'utf8'));
const hash = (path) => createHash('sha256').update(readFileSync(path)).digest('hex');
const installation = read('installation.json');
const providers = read('providers.json');
const contract = read('contract.json');
const auditPath = resolve(`results/${label}-audit.json`);
const receiptPath = resolve(`results/${label}.json`);
const audit = { schemaVersion: 1, lane, label, passed: false, failure: null };
function reject(code, message) {
  throw Object.assign(new Error(message), { code });
}
try {
  audit.workspaceProbes = installation.workspaceRoots.map((path) => ({
    path, accessible: existsSync(path),
  }));
  assert(audit.workspaceProbes.every((item) => !item.accessible), 'Checkout accessible');
  audit.networkInterfaces = networkInterfaces();
  assert(Object.keys(audit.networkInterfaces).every((name) => name === 'lo'),
    'Network namespace exposes an external interface');
  for (const item of installation.packages) {
    const path = `node_modules/${item.name}/package.json`;
    const actual = read(path);
    if (actual.name !== item.name || actual.version !== item.version) {
      reject('INCOMPATIBLE_PACKAGE', `${path}: expected ${item.name}@${item.version}, `
        + `received ${actual.name}@${actual.version}`);
    }
  }
  if (!existsSync(providers.doeLibrary)) {
    reject('MISSING_LIBRARY', `Doe native library is missing: ${providers.doeLibrary}`);
  }
  for (const item of contract.model.files) {
    const path = resolve(contract.model.path, item.path);
    if (!existsSync(path)) reject('MISSING_MODEL', `Model artifact is missing: ${path}`);
    assert.equal(hash(path), item.sha256, `Model artifact SHA-256 mismatch: ${path}`);
  }
  const originalContract = read('inputs/contract.json');
  const comparableContract = { ...contract, workloadId: originalContract.workloadId,
    classification: originalContract.classification,
    model: { ...contract.model, path: originalContract.model.path } };
  assert.deepEqual(comparableContract, originalContract, 'Changed generation workload');
  const originalReference = read('inputs/reference.json');
  const comparableReference = { ...read('reference.json'),
    contractSha256: originalReference.contractSha256 };
  assert.deepEqual(comparableReference, originalReference, 'Changed CPU oracle');
  process.argv = [process.argv[0], resolve('harness/run-generation.mjs'),
    'contract.json', 'providers.json', 'reference.json', lane, receiptPath];
  await import(pathToFileURL(process.argv[1]).href);
  const receipt = read(receiptPath);
  audit.receiptSha256 = hash(receiptPath);
  audit.nativePath = realpathSync(lane === 'doe' ? providers.doeLibrary
    : resolve('node_modules/webgpu/dist/linux-x64.dawn.node'));
  audit.nativeSha256 = hash(audit.nativePath);
  audit.sharedObjects = process.report.getReport().sharedObjects;
  audit.nativeLoaded = audit.sharedObjects.includes(audit.nativePath);
  assert(audit.nativeLoaded, `Selected native library was not loaded: ${audit.nativePath}`);
  audit.addonLoaded = lane === 'doe'
    ? audit.sharedObjects.includes(realpathSync('node_modules/doe-gpu/build/Release/doe_napi.node'))
    : null;
  if (lane === 'doe') assert(audit.addonLoaded, 'Selected Doe addon was not loaded');
  assert(receipt.passed && receipt.cleanup.unloaded === true, 'Generation or cleanup failed');
  assert(receipt.cleanup.devicesDestroyed > 0, 'No device cleanup observed');
  audit.passed = true;
} catch (error) {
  audit.failure = { code: error.code ?? 'QUALIFICATION_FAILED', message: error.message };
  process.exitCode = 1;
}
writeFileSync(auditPath, `${JSON.stringify(audit, null, 2)}\n`);
console.log(JSON.stringify({ lane, label, passed: audit.passed, failure: audit.failure }));

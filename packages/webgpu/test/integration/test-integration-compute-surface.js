import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const TEST_DIR = dirname(fileURLToPath(import.meta.url));
const COMPUTE_SOURCE_PATH = resolve(TEST_DIR, "../../src/compute.js");

async function loadWrapperHelpers() {
  const originalSource = readFileSync(COMPUTE_SOURCE_PATH, "utf8");
  const rewrittenSource = originalSource
    .replace(
      "import * as full from './index.js';",
      "const full = { globals: {}, create() { throw new Error('full.create should not run in compute wrapper tests'); }, providerInfo: () => ({}), createDoeRuntime: () => { throw new Error('createDoeRuntime should not run in compute wrapper tests'); }, runDawnVsDoeCompare: () => { throw new Error('runDawnVsDoeCompare should not run in compute wrapper tests'); } };",
    )
    .replace(
      "import { createDoeNamespace } from '../../webgpu-doe/src/index.js';",
      "const createDoeNamespace = () => ({ bind() { throw new Error('doe namespace should not run in compute wrapper tests'); }, requestDevice() { throw new Error('doe namespace should not run in compute wrapper tests'); } });",
    )
    + "\nexport { wrapCommandEncoder, wrapDevice, wrapBuffer };";

  const tempDir = mkdtempSync(join(os.tmpdir(), "fawn-compute-wrapper-test-"));
  const tempModulePath = join(tempDir, "compute-wrapper-test-module.mjs");
  writeFileSync(tempModulePath, rewrittenSource);
  try {
    return await import(pathToFileURL(tempModulePath).href);
  } finally {
    rmSync(tempDir, { recursive: true, force: true });
  }
}

let passed = 0;
let failed = 0;

function pass(message) {
  passed += 1;
  console.log(`PASS: ${message}`);
}

function fail(message, error) {
  failed += 1;
  console.error(`FAIL: ${message}${error ? `: ${error?.message ?? error}` : ""}`);
}

function section(name) {
  console.log(`\n--- ${name} ---`);
}

const { wrapCommandEncoder, wrapDevice, wrapBuffer } = await loadWrapperHelpers();

section("shader module getCompilationInfo passthrough");
try {
  let compilationInfoCalls = 0;
  const compilationInfo = { messages: [{ type: "info", message: "ok" }] };
  const rawShaderModule = {
    async getCompilationInfo() {
      compilationInfoCalls += 1;
      return compilationInfo;
    },
  };
  const device = wrapDevice({
    queue: {},
    limits: {},
    features: new Set(),
    lost: Promise.resolve({ reason: "unknown", message: "" }),
    createShaderModule() {
      return rawShaderModule;
    },
  });
  const wrappedShaderModule = device.createShaderModule({ code: "@compute fn main() {}" });
  const result = await wrappedShaderModule.getCompilationInfo();
  assert.equal(result, compilationInfo);
  assert.equal(compilationInfoCalls, 1);
  pass("createShaderModule returns the underlying shader module with getCompilationInfo()");
} catch (error) {
  fail("shader module getCompilationInfo passthrough", error);
}

section("command encoder clearBuffer passthrough");
try {
  const clearCalls = [];
  const rawBuffer = { id: "raw-buffer" };
  const wrappedBuffer = wrapBuffer(rawBuffer);
  const encoder = wrapCommandEncoder({
    clearBuffer(buffer, offset, size) {
      clearCalls.push({ buffer, offset, size });
    },
  });
  encoder.clearBuffer(wrappedBuffer, 8, 16);
  assert.deepEqual(clearCalls, [{ buffer: rawBuffer, offset: 8, size: 16 }]);
  pass("clearBuffer() unwraps compute buffers and forwards offset/size");
} catch (error) {
  fail("command encoder clearBuffer passthrough", error);
}

section("command encoder clearBuffer fail-fast");
try {
  const rawBuffer = { id: "raw-buffer" };
  const wrappedBuffer = wrapBuffer(rawBuffer);
  const encoder = wrapCommandEncoder({});
  assert.throws(
    () => encoder.clearBuffer(wrappedBuffer, 0, 4),
    /buffer clearing is unsupported on the compute surface/,
  );
  pass("clearBuffer() fails explicitly when the underlying runtime lacks clearBuffer");
} catch (error) {
  fail("command encoder clearBuffer fail-fast", error);
}

section("device error scopes and lost passthrough");
try {
  const pushCalls = [];
  let popCalls = 0;
  const lost = Promise.resolve({ reason: "destroyed", message: "done" });
  const expectedError = { message: "captured" };
  const device = wrapDevice({
    queue: {},
    limits: {},
    features: new Set(["timestamp-query"]),
    lost,
    pushErrorScope(filter) {
      pushCalls.push(filter);
    },
    async popErrorScope() {
      popCalls += 1;
      return expectedError;
    },
  });
  assert.equal(device.lost, lost);
  device.pushErrorScope("validation");
  const popped = await device.popErrorScope();
  assert.deepEqual(pushCalls, ["validation"]);
  assert.equal(popCalls, 1);
  assert.equal(popped, expectedError);
  pass("pushErrorScope(), popErrorScope(), and lost all pass through the compute facade");
} catch (error) {
  fail("device error scopes and lost passthrough", error);
}

section("device error scope fail-fast");
try {
  const device = wrapDevice({
    queue: {},
    limits: {},
    features: new Set(),
    lost: Promise.resolve({ reason: "unknown", message: "" }),
  });
  assert.throws(
    () => device.pushErrorScope("validation"),
    /error scopes are unsupported on the compute surface/,
  );
  assert.throws(
    () => device.popErrorScope(),
    /error scopes are unsupported on the compute surface/,
  );
  pass("error scopes fail explicitly when the underlying runtime lacks push/pop support");
} catch (error) {
  fail("device error scope fail-fast", error);
}

console.log(`\nResults: ${passed} passed, ${failed} failed`);
process.exitCode = failed > 0 ? 1 : 0;

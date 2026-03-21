import assertStrict from "node:assert/strict";
import { createRequire } from "node:module";
import * as full from "../../src/index.js";

let passed = 0;
let failed = 0;
let skipped = 0;

function assert(condition, message) {
  if (condition) {
    passed += 1;
    return;
  }
  failed += 1;
  console.error(`  FAIL: ${message}`);
}

function skip(message) {
  skipped += 1;
  console.log(`  SKIP: ${message}`);
}

let gpu;
let adapter;
let device;

try {
  gpu = full.create();
  adapter = await gpu.requestAdapter();
  device = await adapter.requestDevice();
} catch (error) {
  console.error(`Setup failed: ${error?.message ?? error}`);
  process.exit(1);
}

const require = createRequire(import.meta.url);

console.log("\n--- a. published limits include maxImmediateSize ---");
try {
  assert(device.limits.maxImmediateSize > 0, "device.limits.maxImmediateSize is published");
} catch (error) {
  failed += 1;
  console.error(`  FAIL (unexpected error): ${error?.message ?? error}`);
}

console.log("\n--- b. addon exports debug and indirect methods ---");
try {
  const addon = require("../../build/Release/doe_napi.node");
  const expectedMethods = [
    "computePassPushDebugGroup",
    "computePassPopDebugGroup",
    "computePassInsertDebugMarker",
    "renderPassDrawIndirect",
    "renderPassDrawIndexedIndirect",
    "renderPassPushDebugGroup",
    "renderPassPopDebugGroup",
    "renderPassInsertDebugMarker",
    "renderBundleEncoderDrawIndirect",
    "renderBundleEncoderDrawIndexedIndirect",
    "renderBundleEncoderPushDebugGroup",
    "renderBundleEncoderPopDebugGroup",
    "renderBundleEncoderInsertDebugMarker",
  ];
  for (const methodName of expectedMethods) {
    assert(typeof addon[methodName] === "function", `${methodName} exported from addon`);
  }
} catch (error) {
  failed += 1;
  console.error(`  FAIL (unexpected error): ${error?.message ?? error}`);
}

console.log("\n--- c. package import keeps surface probe stable ---");
try {
  const imported = await import("../../src/index.js");
  assertStrict.equal(typeof imported.create, "function");
  assert(true, "package surface imports successfully");
} catch (error) {
  failed += 1;
  console.error(`  FAIL (unexpected error): ${error?.message ?? error}`);
}

console.log(`\nSummary: ${passed} passed, ${failed} failed, ${skipped} skipped.`);
process.exitCode = failed > 0 ? 1 : 0;

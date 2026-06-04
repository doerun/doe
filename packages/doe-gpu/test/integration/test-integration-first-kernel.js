#!/usr/bin/env node

import { join } from "node:path";

import { runFirstKernelReceiptTest } from "./first-kernel-receipt-test.js";

await runFirstKernelReceiptTest({
  runtimeHost: "node",
  command: process.execPath,
  exampleFile: join("examples", "node-first-kernel.mjs"),
});

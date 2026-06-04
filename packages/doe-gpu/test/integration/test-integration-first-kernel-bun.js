#!/usr/bin/env bun

import { join } from "node:path";

import { runFirstKernelReceiptTest } from "./first-kernel-receipt-test.js";

await runFirstKernelReceiptTest({
  runtimeHost: "bun",
  command: typeof Bun !== "undefined" ? process.execPath : "bun",
  exampleFile: join("examples", "bun-first-kernel.mjs"),
});

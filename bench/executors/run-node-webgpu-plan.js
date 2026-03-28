#!/usr/bin/env node

import { fileURLToPath } from 'node:url';

import { runPackageWebGpuPlanCli } from './package-webgpu/runner-core.js';

const CLI_PATH = fileURLToPath(import.meta.url);

runPackageWebGpuPlanCli({
  runtimeHost: 'node',
  defaultProvider: 'dawn',
  cliPath: CLI_PATH,
  childEnv: 'DOE_NODE_WEBGPU_CHILD',
  label: 'node-webgpu',
  providerUsage: 'doe|dawn',
  usageCommand: 'node bench/executors/run-node-webgpu-plan.js',
}).catch((err) => {
  process.stderr.write(`${err instanceof Error ? err.message : String(err)}\n`);
  process.exit(1);
});

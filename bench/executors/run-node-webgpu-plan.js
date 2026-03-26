#!/usr/bin/env node

import { parseArgs } from 'node:util';
import { executePlanFile } from './node-webgpu/executor.js';

function parseCliArgs() {
  return parseArgs({
    options: {
      provider: { type: 'string', default: 'dawn' },
      plan: { type: 'string', default: '' },
      'trace-meta': { type: 'string', default: '' },
      'trace-jsonl': { type: 'string', default: '' },
      workload: { type: 'string', default: '' },
      'dry-run': { type: 'boolean', default: false },
    },
  }).values;
}

async function main() {
  const args = parseCliArgs();
  if (!args.plan || !args['trace-meta'] || !args['trace-jsonl'] || !args.workload) {
    throw new Error(
      'usage: node bench/executors/run-node-webgpu-plan.js --provider <doe|dawn> --plan <path> --trace-meta <path> --trace-jsonl <path> --workload <id>',
    );
  }

  await executePlanFile({
    planPath: args.plan,
    workloadId: args.workload,
    provider: args.provider,
    traceMetaPath: args['trace-meta'],
    traceJsonlPath: args['trace-jsonl'],
    dryRun: Boolean(args['dry-run']),
  });
}

main().catch((err) => {
  process.stderr.write(`${err instanceof Error ? err.message : String(err)}\n`);
  process.exit(1);
});

#!/usr/bin/env node
// A terminal workspace for a resident heat field and externally edited WGSL.
import { writeFileSync } from 'node:fs';
import { parseArgs } from 'node:util';
import { DEFAULT_SHADER } from './live-simulation/program.js';
import { runLiveTerminal } from './live-simulation/terminal.js';

const { values } = parseArgs({ options: {
  backend: { type: 'string' }, execution: { type: 'string' },
  'write-shader': { type: 'string' },
} });
if (values['write-shader']) {
  writeFileSync(values['write-shader'], DEFAULT_SHADER, { flag: 'wx' });
  console.log(`Created ${values['write-shader']}`);
} else {
  if (!['vulkan', 'metal'].includes(values.backend)
      || !['gpu-recorded', 'native-recorded', 'webgpu'].includes(values.execution)) {
    throw new Error('Usage: node examples/live-simulation.js --backend vulkan|metal --execution gpu-recorded|native-recorded|webgpu; or --write-shader path.wgsl');
  }
  const terminal = await runLiveTerminal({ backend: values.backend, execution: values.execution });
  const stop = () => { void terminal.close().catch((error) => { console.error(error); process.exitCode = 1; }); };
  process.once('SIGINT', stop);
  process.once('SIGTERM', stop);
  try { await terminal.closed; }
  finally {
    process.off('SIGINT', stop);
    process.off('SIGTERM', stop);
  }
}

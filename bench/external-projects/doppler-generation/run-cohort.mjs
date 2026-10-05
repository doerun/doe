// Frozen sequential provider order; every process and failed receipt is retained.
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
const [contractPath, providersPath, referencePath, outputRoot, cohort] = process.argv.slice(2);
const contract = JSON.parse(await readFile(contractPath));
assert(cohort && /^[a-z0-9-]+$/.test(cohort));
const worker = resolve(dirname(fileURLToPath(import.meta.url)), 'run-generation.mjs');
const executions = [];
for (let processIndex = 0; processIndex < contract.performance.processes; processIndex++) {
  const order = contract.performance.sampleOrder.slice((processIndex % 2) * 2, (processIndex % 2) * 2 + 2);
  for (const lane of order) {
    const output = resolve(outputRoot, `${cohort}-${lane}-${processIndex}.json`);
    const cache = resolve(outputRoot, 'caches', `${cohort}-${lane}-${processIndex}`);
    await mkdir(cache, { recursive: true });
    const child = spawn(process.execPath, [worker, contractPath, providersPath, referencePath, lane, output, 'timing', String(processIndex)],
      { env: { ...process.env, XDG_CACHE_HOME: cache, DOE_PIPELINE_CACHE_DIR: cache,
        DOE_SHADER_CACHE_DIR: cache, MESA_SHADER_CACHE_DIR: cache }, stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';let stderr = '';
    child.stdout.on('data', (bytes) => { stdout += bytes; });
    child.stderr.on('data', (bytes) => { stderr += bytes; });
    const status = await new Promise((done) => child.once('close', (code, signal) => done({ code, signal })));
    await writeFile(output.replace('.json', '.stdout.log'), stdout);
    await writeFile(output.replace('.json', '.stderr.log'), stderr);
    executions.push({ lane, processIndex, output, ...status });
    await writeFile(resolve(outputRoot, `${cohort}-processes.json`), JSON.stringify(executions, null, 2) + '\n');
    console.log(JSON.stringify({ cohort, lane, processIndex, ...status }));
    assert.equal(status.code, 0, `Failed process ${output}; stop without timing promotion`);
  }
}

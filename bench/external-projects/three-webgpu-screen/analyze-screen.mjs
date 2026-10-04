// Retained application screening evidence; no optimizer performance promotion.
import { readFile, writeFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { gunzipSync } from 'node:zlib';
import assert from 'node:assert/strict';

const directory = resolve(process.argv[2]);
const plan = JSON.parse(await readFile(resolve(dirname(fileURLToPath(import.meta.url)), 'screen.json')));
const load = async (name) => JSON.parse(await readFile(resolve(directory, name)));
const median = (values) => {
  assert(values.length > 0, 'No observations');
  const sorted = values.toSorted((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
};
const profile = await load('profile-0.json');
assert(profile.timestampEnabled && profile.backend);
const seen = new Set();
const groups = new Map(plan.scattering.map((value) => [value, []]));
const excludedRows = [];
for (const [index, row] of profile.rows.entries()) {
  const labels = row.timestamps.map((entry) => entry.context.label);
  const complete = ['scene/composite', 'output', 'GaussianBlurNode.horizontal',
    'GaussianBlurNode.vertical'].every((label) => labels.includes(label));
  const repeated = row.timestamps.some((entry) => seen.has(entry.uid));
  for (const entry of row.timestamps) seen.add(entry.uid);
  if (!complete || repeated) {
    excludedRows.push({ index, reason: !complete ? 'incomplete-pass-set' : 'cached-timestamp-uids' });
    continue;
  }
  const total = row.timestamps.reduce((sum, entry) => sum + entry.durationMs, 0);
  const blur = row.timestamps.filter((entry) => entry.context.label.startsWith('GaussianBlurNode.'))
    .reduce((sum, entry) => sum + entry.durationMs, 0);
  groups.get(row.scattering).push({ total, blur, fraction: blur / total });
}
const passObservations = [...groups].map(([scattering, rows]) => ({ scattering,
  observations: rows.length, gpuTotalMedianMs: median(rows.map((row) => row.total)),
  blurGpuMedianMs: median(rows.map((row) => row.blur)),
  blurFractionMedian: median(rows.map((row) => row.fraction)) }));
const aa = [];
for (let process = 0; process < plan.processes; process++) {
  const artifact = `aa-${process}.json`;
  const session = await load(artifact);
  assert.equal(session.timestampEnabled, false);
  assert.equal(session.rows.length, plan.trialLabels.length * 2);
  assert.deepEqual(session.shaders, profile.shaders);
  const pairs = [];
  for (let index = 0; index < session.rows.length; index += 2) {
    const pair = session.rows.slice(index, index + 2);
    assert.deepEqual(pair.map((row) => row.label), plan.trialLabels[(index / 2 + process) % plan.trialLabels.length]);
    const a = pair.find((row) => row.label === 'A').completedMs;
    const b = pair.find((row) => row.label === 'B').completedMs;
    assert(a > 0 && b > 0);
    pairs.push({ differenceMs: b - a, logCostRatio: Math.log(b / a) });
  }
  aa.push({ artifact, pairs, meanDifferenceMs: pairs.reduce((sum, row) => sum + row.differenceMs, 0) / pairs.length,
    meanLogCostRatio: pairs.reduce((sum, row) => sum + row.logCostRatio, 0) / pairs.length });
}
const driverFindings = await load('driver-findings.json');
const rawDriver = gunzipSync(await readFile(resolve(directory, 'driver-capture.log.gz'))).toString()
  .replace(/^.*?pw:browser \[pid=\d+\]\[err\] ?/gm, '');
for (const finding of driverFindings) {
  const text = gunzipSync(await readFile(resolve(directory, finding.artifact))).toString();
  assert(rawDriver.includes(text.trim()), 'Selected native program absent from raw driver capture');
  assert(text.startsWith('shader: MESA_SHADER_FRAGMENT'));
  assert(text.includes(`source_blake3: ${finding.sourceBlake3}`));
  assert(text.includes('0x3ddfbd0d'), 'Gaussian family coefficient signature absent');
  const disasm = text.slice(text.indexOf('disasm:'));
  assert.equal((disasm.match(/^\s*image_sample[^\n]*;/gm) ?? []).length, finding.nativeTextureSamples);
  assert.equal((disasm.match(/^\s*s_buffer_load[^\n]*;/gm) ?? []).length, finding.nativeScalarBufferLoads);
  assert.equal((disasm.match(/^\s*(?:scratch_load|scratch_store)[^\n]*;/gm) ?? []).length, finding.scratchInstructions);
  assert.equal((text.split('ACO shader')[0].match(/load_ubo/g) ?? []).length, finding.nirUniformLoads);
}
for (const admission of await load('doe-admission.json')) {
  assert.equal(admission.exitCode, 0);
  assert.equal(admission.byteIdentical, true);
  assert((await readFile(resolve(directory, admission.shader))).equals(
    await readFile(resolve(directory, admission.shader.replace('.wgsl', '.doe.wgsl')))));
}
const summary = { schemaVersion: 1, classification: 'diagnostic', performancePromoted: false,
  passObservations, excludedRows, aa, driverFindings,
  timingScope: 'Driver-debug instrumented unique complete pass observations; asynchronous pool freshness not qualified per application frame. Uninstrumented A/A complete host frames retained separately.',
  materialApplicationCostQualified: false,
  disposition: 'close-screen-no-worthwhile-automatic-transformation-identified',
  independentOracle: 'Not qualified; no transformed shader executed.',
  nextBatch: 'vulkan_doppler_generation_contract' };
await writeFile(resolve(directory, 'summary.json'), JSON.stringify(summary, null, 2) + '\n');
console.log('Verified retained shaders, native instruction findings, timestamp exclusions and A/A pairs.');

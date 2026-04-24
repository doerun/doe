#!/usr/bin/env node
// Bind TSIR manifest-entry fixtures (bootstrap + real) into a Doppler model
// manifest's `integrityExtensions.lowerings` section.
//
// Reads committed fixtures from:
//   doe/bench/fixtures/tsir-manifest-entries/    (bootstrap — 6 entries)
//   doe/bench/fixtures/tsir-real-entries/        (real      — 4 entries)
//
// Normalizes every entry through Doppler's `normalizeManifestLoweringEntry`
// (which enforces the Doe-schema field names: compilerVersion,
// targetDescriptorCorrectnessHash, structured exactness), validates the
// resulting manifest via `validateManifest`, and writes the manifest back.
//
// The binder is deliberately a thin pass-through — all digest computation is
// upstream. If a fixture is missing or drifts from its generator, the
// corresponding `--check` mode on the generator catches it before this binder
// ever runs.

import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  normalizeManifestLoweringEntry,
} from '../../../doppler/src/tooling/rdrr-integrity-refresh.js';
import {
  validateManifest,
} from '../../../doppler/src/formats/rdrr/validation.js';

const DOE_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const BOOTSTRAP_DIR = path.join(DOE_ROOT, 'bench', 'fixtures', 'tsir-manifest-entries');
const REAL_DIR = path.join(DOE_ROOT, 'bench', 'fixtures', 'tsir-real-entries');

const BOOTSTRAP_FIXTURES = [
  'fused_gemv.webgpu-generic.json',
  'fused_gemv.wse3.json',
  'rms_norm.webgpu-generic.json',
  'rms_norm.wse3.json',
  'gather.webgpu-generic.json',
  'gather.wse3.json',
];

const REAL_FIXTURES = [
  'embed.webgpu-generic.json',
  'embed.wse3.json',
  'lm_head_gemv.webgpu-generic.json',
  'lm_head_gemv.wse3.json',
];

async function readFixture(dir, name) {
  const raw = await fs.readFile(path.join(dir, name), 'utf8');
  return JSON.parse(raw);
}

async function collectEntries() {
  const entries = [];
  for (const name of BOOTSTRAP_FIXTURES) {
    const doc = await readFixture(BOOTSTRAP_DIR, name);
    entries.push(normalizeManifestLoweringEntry(doc, `doe:bootstrap:${name}`));
  }
  for (const name of REAL_FIXTURES) {
    const doc = await readFixture(REAL_DIR, name);
    entries.push(normalizeManifestLoweringEntry(doc, `doe:real:${name}`));
  }
  return entries;
}

async function main() {
  const manifestArg = process.argv[2];
  if (!manifestArg) {
    console.error('usage: bind_tsir_lowerings_to_manifest.js <manifest.json>');
    process.exit(2);
  }
  const manifestPath = path.resolve(manifestArg);
  const manifestRaw = await fs.readFile(manifestPath, 'utf8');
  const manifest = JSON.parse(manifestRaw);

  const entries = await collectEntries();

  const integrityExtensions = { ...(manifest.integrityExtensions ?? {}) };
  if (integrityExtensions.contractVersion !== 1) {
    throw new Error(
      `manifest.integrityExtensions.contractVersion must be 1; got ${integrityExtensions.contractVersion}`,
    );
  }
  integrityExtensions.lowerings = { contractVersion: 1, entries };
  manifest.integrityExtensions = integrityExtensions;

  const validation = validateManifest(manifest);
  if (validation.errors && validation.errors.length > 0) {
    console.error('manifest validation failed:');
    for (const error of validation.errors) console.error('  ' + error);
    process.exit(1);
  }

  const nextRaw = JSON.stringify(manifest, null, 2);
  const trailingNewline = manifestRaw.endsWith('\n') ? '\n' : '';
  await fs.writeFile(manifestPath, nextRaw + trailingNewline, 'utf8');

  console.log(`bound ${entries.length} TSIR lowering entries into ${manifestPath}`);
  const distinctBackends = new Set(entries.map((e) => e.backend));
  const distinctKernels = new Set(entries.map((e) => e.kernelRef));
  console.log(`  kernels: ${[...distinctKernels].sort().join(', ')}`);
  console.log(`  backends: ${[...distinctBackends].sort().join(', ')}`);
}

main().catch((err) => {
  console.error(err.stack ?? err.message ?? String(err));
  process.exit(1);
});

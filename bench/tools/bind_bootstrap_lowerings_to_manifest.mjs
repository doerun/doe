#!/usr/bin/env node
// Bind TSIR bootstrap manifest-entry fixtures into a Doppler model manifest's
// `integrityExtensions.lowerings` section.
//
// Narrow tool: reads the 6 bootstrap fixtures from doe's
// bench/fixtures/tsir-manifest-entries/, normalizes them through Doppler's
// `normalizeManifestLoweringEntry`, validates the resulting manifest via
// `validateManifestInference`, and writes the manifest back.
//
// Not a general-purpose binder — only the 3 bootstrap kernels
// (fused_gemv, rms_norm, gather) are understood here. Real Doppler kernels
// require their own TSIR lowerings.

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
const DOE_FIXTURE_DIR = path.join(DOE_ROOT, 'bench', 'fixtures', 'tsir-manifest-entries');

async function readFixture(name) {
  const raw = await fs.readFile(path.join(DOE_FIXTURE_DIR, name), 'utf8');
  return JSON.parse(raw);
}

async function main() {
  const manifestArg = process.argv[2];
  if (!manifestArg) {
    console.error('usage: bind_bootstrap_lowerings_to_manifest.mjs <manifest.json>');
    process.exit(2);
  }
  const manifestPath = path.resolve(manifestArg);
  const manifestRaw = await fs.readFile(manifestPath, 'utf8');
  const manifest = JSON.parse(manifestRaw);

  const fixtureNames = [
    'fused_gemv.webgpu-generic.json',
    'fused_gemv.wse3.json',
    'rms_norm.webgpu-generic.json',
    'rms_norm.wse3.json',
    'gather.webgpu-generic.json',
    'gather.wse3.json',
  ];
  const entries = [];
  for (const name of fixtureNames) {
    const doc = await readFixture(name);
    entries.push(normalizeManifestLoweringEntry(doc, `doe:${name}`));
  }

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

  console.log(`bound ${entries.length} TSIR bootstrap lowering entries into ${manifestPath}`);
  const distinctBackends = new Set(entries.map((e) => e.backend));
  const distinctKernels = new Set(entries.map((e) => e.kernelRef));
  console.log(`  kernels: ${[...distinctKernels].sort().join(', ')}`);
  console.log(`  backends: ${[...distinctBackends].sort().join(', ')}`);
}

main().catch((err) => {
  console.error(err.stack ?? err.message ?? String(err));
  process.exit(1);
});

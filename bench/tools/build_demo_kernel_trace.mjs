#!/usr/bin/env node

import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, '..', '..');

function parseArgs(argv) {
  const args = {
    out: 'bench/out/scratch/full-model-demo',
    trace: 'bench/out/scratch/csl-kernel-traces/full-model-demo.json',
  };
  for (let i = 2; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === '--out') { args.out = argv[i + 1]; i += 1; }
    else if (a === '--trace') { args.trace = argv[i + 1]; i += 1; }
    else throw new Error(`unknown arg: ${a}`);
  }
  return args;
}

function readI32(path) {
  const buf = readFileSync(path);
  const out = [];
  for (let i = 0; i < buf.byteLength; i += 4) out.push(buf.readInt32LE(i));
  return out;
}

function readF32(path) {
  const buf = readFileSync(path);
  const out = [];
  for (let i = 0; i < buf.byteLength; i += 4) out.push(buf.readFloatLE(i));
  return out;
}

function main() {
  const args = parseArgs(process.argv);
  const outRoot = resolve(REPO_ROOT, args.out);
  const tracePath = resolve(REPO_ROOT, args.trace);

  mkdirSync(outRoot, { recursive: true });
  mkdirSync(dirname(tracePath), { recursive: true });
  const d2hDir = resolve(outRoot, 'd2h');
  mkdirSync(d2hDir, { recursive: true });

  process.stderr.write('step 1: synthesize demo input\n');
  execFileSync('node', [
    resolve(HERE, 'build_demo_full_model_emulator_input.mjs'),
    '--out', outRoot,
  ], { stdio: 'inherit' });

  process.stderr.write('step 2: run emulator with kernel-trace + d2h dump\n');
  execFileSync('node', [
    resolve(HERE, 'run_csl_webgpu_emulator.mjs'),
    '--input', resolve(outRoot, 'demo-input.json'),
    '--out', resolve(outRoot, 'result.json'),
    '--backend', 'cpu',
    '--kernel-trace', tracePath,
    '--d2h-out-dir', d2hDir,
  ], { stdio: 'inherit' });

  process.stderr.write('step 3: merge demoMeta into trace\n');
  const trace = JSON.parse(readFileSync(tracePath, 'utf-8'));
  const meta = JSON.parse(readFileSync(resolve(outRoot, 'demo-meta.json'), 'utf-8'));

  const prefillTokens = readI32(resolve(d2hDir, 'd2h-tokens_out-tokens_out.bin'));
  const decodeTokens = readI32(resolve(d2hDir, 'd2h-tokens_decode_out-tokens_decode_out.bin'));
  const decodeLogits = readF32(resolve(d2hDir, 'd2h-logits_decode-logits_decode.bin'));

  let argmaxIdx = -1;
  let argmaxVal = -Infinity;
  for (let i = 0; i < decodeLogits.length; i += 1) {
    if (Number.isFinite(decodeLogits[i]) && decodeLogits[i] > argmaxVal) {
      argmaxVal = decodeLogits[i];
      argmaxIdx = i;
    }
  }

  trace.demoMeta = {
    ...meta,
    sampledPrefillToken: prefillTokens[0] ?? null,
    sampledDecodeToken: decodeTokens[0] ?? null,
    decodeLogitsArgmax: argmaxIdx,
    logitsAreFinite: argmaxIdx >= 0,
    samplerNote: argmaxIdx >= 0
      ? `argmax(decode logits) = ${argmaxIdx}`
      : 'logits non-finite (random weights NaN-out at this scale) — sampled token = 0 placeholder',
  };

  writeFileSync(tracePath, JSON.stringify(trace, null, 2), 'utf-8');
  process.stderr.write(`merged demoMeta → ${tracePath}\n`);
  process.stderr.write(`prefill token: ${trace.demoMeta.sampledPrefillToken}, decode token: ${trace.demoMeta.sampledDecodeToken}, argmax: ${argmaxIdx}\n`);
}

main();

#!/usr/bin/env node

import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { gpu } from "../../packages/doe-gpu/src/index.js";
import { writeDeterminismTraceMeta } from "./determinism-trace-meta.js";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(SCRIPT_DIR, "..", "..");
const MODE_HOST_BYTES = "host-bytes";
const MODE_BUFFER_READBACK = "buffer-readback";
const VALID_MODES = new Set([MODE_HOST_BYTES, MODE_BUFFER_READBACK]);

function usage() {
  console.log(`Usage:
  node bench/executors/run-doe-stable-token.js --config <path>

Config contract:
  {
    "logitsPath": "/abs/path/to/logits.bin",
    "outputPath": "/abs/path/to/report.json",
    "traceMetaPath": "/abs/path/to/trace-meta.json",
    "vocabSize": 4096,
    "mode": "buffer-readback",
    "topCandidates": 5,
    "label": "optional-label"
  }`);
}

function parseArgs(argv) {
  let configPath = null;
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === "--help") {
      usage();
      process.exit(0);
    }
    if (token === "--config") {
      configPath = argv[index + 1] ?? null;
      index += 1;
      continue;
    }
    throw new Error(`Unknown flag: ${token}`);
  }
  if (!configPath) {
    throw new Error("--config is required");
  }
  return { configPath: path.resolve(configPath) };
}

function sha256Hex(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function relativeOrAbsolute(targetPath) {
  const absolute = path.resolve(targetPath);
  if (absolute === REPO_ROOT || absolute.startsWith(`${REPO_ROOT}${path.sep}`)) {
    return path.relative(REPO_ROOT, absolute);
  }
  return absolute;
}

function ensureConfigShape(config) {
  if (!config || typeof config !== "object" || Array.isArray(config)) {
    throw new Error("config must be a JSON object");
  }
  if (typeof config.logitsPath !== "string" || config.logitsPath.length === 0) {
    throw new Error("config.logitsPath must be a non-empty string");
  }
  if (typeof config.outputPath !== "string" || config.outputPath.length === 0) {
    throw new Error("config.outputPath must be a non-empty string");
  }
  if (config.traceMetaPath != null && (typeof config.traceMetaPath !== "string" || config.traceMetaPath.length === 0)) {
    throw new Error("config.traceMetaPath must be a non-empty string when provided");
  }
  if (!Number.isInteger(config.vocabSize) || config.vocabSize <= 0) {
    throw new Error("config.vocabSize must be a positive integer");
  }
  if (config.topCandidates != null && (!Number.isInteger(config.topCandidates) || config.topCandidates <= 0)) {
    throw new Error("config.topCandidates must be a positive integer when provided");
  }
  const mode = config.mode ?? MODE_BUFFER_READBACK;
  if (!VALID_MODES.has(mode)) {
    throw new Error(`config.mode must be one of: ${Array.from(VALID_MODES).join(", ")}`);
  }
}

async function loadConfig(configPath) {
  const config = JSON.parse(await readFile(configPath, "utf8"));
  ensureConfigShape(config);
  return {
    ...config,
    configPath,
    logitsPath: path.resolve(config.logitsPath),
    outputPath: path.resolve(config.outputPath),
    traceMetaPath: config.traceMetaPath ? path.resolve(config.traceMetaPath) : null,
    mode: config.mode ?? MODE_BUFFER_READBACK,
  };
}

async function run() {
  const { configPath } = parseArgs(process.argv.slice(2));
  const config = await loadConfig(configPath);
  const payload = await readFile(config.logitsPath);
  if (payload.byteLength !== config.vocabSize * 4) {
    throw new Error(
      `logits payload size ${payload.byteLength} does not match vocabSize ${config.vocabSize} * 4`
    );
  }

  let bound = null;
  let buffer = null;
  try {
    if (config.mode === MODE_BUFFER_READBACK) {
      bound = await gpu.requestDevice();
      buffer = bound.buffer.create({
        data: new Uint8Array(payload.buffer, payload.byteOffset, payload.byteLength),
        usage: ["storageRead", "readback"],
        label: config.label ?? undefined,
      });
    } else {
      bound = gpu.bind({});
    }

    const result = await bound.determinism.stableToken({
      logits: buffer ?? new Uint8Array(payload.buffer, payload.byteOffset, payload.byteLength),
      vocabSize: config.vocabSize,
      topCandidates: config.topCandidates,
      label: config.label,
    });
    const traceMeta = await writeDeterminismTraceMeta(config.traceMetaPath, result.receipt);

    const report = {
      schemaVersion: 1,
      source: "doe-stable-token",
      configPath: relativeOrAbsolute(config.configPath),
      mode: config.mode,
      logitsPath: relativeOrAbsolute(config.logitsPath),
      traceMetaPath: config.traceMetaPath ? relativeOrAbsolute(config.traceMetaPath) : null,
      logitsSha256: sha256Hex(payload),
      vocabSize: config.vocabSize,
      traceMeta,
      result,
    };

    await mkdir(path.dirname(config.outputPath), { recursive: true });
    await writeFile(config.outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
    process.stdout.write(
      `${JSON.stringify({ outputPath: relativeOrAbsolute(config.outputPath), token: result.token, mode: config.mode }, null, 2)}\n`
    );
  } finally {
    buffer?.destroy?.();
    bound?.device?.destroy?.();
  }
}

run().catch((error) => {
  process.stderr.write(`Fatal: ${error.message}\n`);
  process.exit(1);
});

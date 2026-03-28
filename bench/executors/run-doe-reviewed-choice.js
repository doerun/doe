#!/usr/bin/env node

import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { gpu } from "../../packages/doe-gpu/src/index.js";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(SCRIPT_DIR, "..", "..");
const MODE_HOST_BYTES = "host-bytes";
const MODE_BUFFER_READBACK = "buffer-readback";
const VALID_MODES = new Set([MODE_HOST_BYTES, MODE_BUFFER_READBACK]);

function usage() {
  console.log(`Usage:
  node bench/executors/run-doe-reviewed-choice.js --config <path>

Config contract:
  {
    "logitsPath": "/abs/path/to/logits.bin",
    "outputPath": "/abs/path/to/report.json",
    "vocabSize": 4096,
    "mode": "buffer-readback",
    "topCandidates": 5,
    "reviewPolicyId": "seatbelt/reviewer-v1",
    "triggerPolicyId": "candidate-margin-band-v1",
    "candidateSetId": "safety.not_safe",
    "candidateSetSource": "source-report-resolved",
    "candidates": [
      { "token": 711, "label": "not" },
      { "token": 6338, "label": "safe" }
    ],
    "ambiguityTrigger": { "mode": "candidate-margin-band", "epsilon": 0.05 },
    "decision": {
      "token": 711,
      "label": "not",
      "reviewerId": "bench/reviewer-v1",
      "decisionId": "seatbelt-review-001",
      "decisionRef": "receipt://seatbelt-review-001",
      "signature": "sha256:deadbeef"
    },
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

function ensureCandidateShape(candidate) {
  if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) {
    throw new Error("config.candidates entries must be objects");
  }
  if (!Number.isInteger(candidate.token) || candidate.token < 0) {
    throw new Error("config.candidates[].token must be a non-negative integer");
  }
  if (candidate.label != null && typeof candidate.label !== "string") {
    throw new Error("config.candidates[].label must be a string when provided");
  }
}

function ensureTriggerShape(trigger) {
  if (!trigger || typeof trigger !== "object" || Array.isArray(trigger)) {
    throw new Error("config.ambiguityTrigger must be an object");
  }
  const mode = trigger.mode;
  if (mode !== "exact-max-tie" && mode !== "candidate-margin-band") {
    throw new Error('config.ambiguityTrigger.mode must be "exact-max-tie" or "candidate-margin-band"');
  }
  if (mode === "candidate-margin-band") {
    if (typeof trigger.epsilon !== "number" || Number.isNaN(trigger.epsilon) || trigger.epsilon < 0) {
      throw new Error("config.ambiguityTrigger.epsilon must be a non-negative number");
    }
  }
}

function ensureDecisionShape(decision) {
  if (!decision || typeof decision !== "object" || Array.isArray(decision)) {
    throw new Error("config.decision must be an object");
  }
  if (!Number.isInteger(decision.token) || decision.token < 0) {
    throw new Error("config.decision.token must be a non-negative integer");
  }
  if (decision.label != null && typeof decision.label !== "string") {
    throw new Error("config.decision.label must be a string when provided");
  }
  if (typeof decision.reviewerId !== "string" || decision.reviewerId.length === 0) {
    throw new Error("config.decision.reviewerId must be a non-empty string");
  }
  for (const field of ["decisionId", "decisionRef", "signature"]) {
    if (decision[field] != null && (typeof decision[field] !== "string" || decision[field].length === 0)) {
      throw new Error(`config.decision.${field} must be a non-empty string when provided`);
    }
  }
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
  if (!Array.isArray(config.candidates) || config.candidates.length < 2) {
    throw new Error("config.candidates must contain at least two entries");
  }
  for (const candidate of config.candidates) {
    ensureCandidateShape(candidate);
  }
  ensureTriggerShape(config.ambiguityTrigger);
  ensureDecisionShape(config.decision);
  if (
    config.reviewPolicyId != null &&
    (typeof config.reviewPolicyId !== "string" || config.reviewPolicyId.length === 0)
  ) {
    throw new Error("config.reviewPolicyId must be a non-empty string when provided");
  }
  if (
    config.triggerPolicyId != null &&
    (typeof config.triggerPolicyId !== "string" || config.triggerPolicyId.length === 0)
  ) {
    throw new Error("config.triggerPolicyId must be a non-empty string when provided");
  }
  if (
    config.candidateSetId != null &&
    (typeof config.candidateSetId !== "string" || config.candidateSetId.length === 0)
  ) {
    throw new Error("config.candidateSetId must be a non-empty string when provided");
  }
  if (
    config.candidateSetSource != null &&
    !["fixture-declared", "registry-resolved", "source-report-resolved"].includes(config.candidateSetSource)
  ) {
    throw new Error("config.candidateSetSource must be fixture-declared, registry-resolved, or source-report-resolved");
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

    const result = await bound.determinism.reviewedChoice({
      logits: buffer ?? new Uint8Array(payload.buffer, payload.byteOffset, payload.byteLength),
      vocabSize: config.vocabSize,
      topCandidates: config.topCandidates,
      candidates: config.candidates,
      ambiguityTrigger: config.ambiguityTrigger,
      reviewPolicyId: config.reviewPolicyId,
      triggerPolicyId: config.triggerPolicyId,
      candidateSetId: config.candidateSetId,
      candidateSetSource: config.candidateSetSource,
      decision: config.decision,
      label: config.label,
    });

    const report = {
      schemaVersion: 1,
      source: "doe-reviewed-choice",
      configPath: relativeOrAbsolute(config.configPath),
      mode: config.mode,
      logitsPath: relativeOrAbsolute(config.logitsPath),
      logitsSha256: sha256Hex(payload),
      vocabSize: config.vocabSize,
      result,
    };

    await mkdir(path.dirname(config.outputPath), { recursive: true });
    await writeFile(config.outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
    process.stdout.write(
      `${JSON.stringify(
        {
          outputPath: relativeOrAbsolute(config.outputPath),
          token: result.token,
          mode: config.mode,
          selectedBy: result.receipt.selectedBy,
          ambiguityTriggered: result.receipt.ambiguityTriggered,
          decisionAccepted: result.receipt.decisionAccepted,
        },
        null,
        2,
      )}\n`
    );
  } finally {
    try {
      if (buffer) {
        buffer.destroy();
      }
    } catch {}
    try {
      if (bound?.device && typeof bound.device.destroy === "function") {
        bound.device.destroy();
      }
    } catch {}
  }
}

run().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});

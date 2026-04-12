#!/usr/bin/env node

import { createHash } from "node:crypto";
import http from "node:http";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, extname, resolve } from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(SCRIPT_DIR, "..", "..", "..");
const ARTIFACTS_ROOT = resolve(ROOT, "browser/chromium/artifacts");
const BENCH_OUT_ROOT = resolve(ROOT, "bench/out");
const BENCH_OUT_SCRATCH_ROOT = resolve(ROOT, "bench/out/scratch");
const HASH_ALGORITHM = "sha256";
const REPORT_SCHEMA_VERSION = 1;
const REPORT_KIND = "chromium-webgpu-playwright-ort-bench";
const TIMING_CLASS = "wall";
const TIMING_SOURCE = "page-performance-now";
const DEFAULT_OUT_FILE = "dawn-vs-doe.browser.playwright-ort-bench.diagnostic.json";
const ONNX_PROTO_PATH = resolve(
  ROOT,
  "bench/node_modules/onnxruntime-web/lib/onnxjs/ort-schema/protobuf/onnx.js",
);
const ORT_MODULE_PATH = "/bench/node_modules/onnxruntime-web/dist/ort.webgpu.mjs";
const DEFAULT_WARMUP_ITERS = 2;
const DEFAULT_STEADY_ITERS = 8;
const DEFAULT_OP_TIMEOUT_MS = 120000;
const DEFAULT_WORKLOAD_SPECS = Object.freeze([
  Object.freeze({
    id: "ort_identity_1x4096_f32",
    name: "ORT identity 1x4096 f32",
    kind: "identity",
    dims: Object.freeze({ m: 1, k: 4096, n: 4096 }),
    warmupIters: DEFAULT_WARMUP_ITERS,
    steadyIters: 16,
  }),
  Object.freeze({
    id: "ort_matmul_1x512_x_512x512_f32",
    name: "ORT matmul 1x512 x 512x512 f32",
    kind: "matmul",
    dims: Object.freeze({ m: 1, k: 512, n: 512 }),
    warmupIters: DEFAULT_WARMUP_ITERS,
    steadyIters: DEFAULT_STEADY_ITERS,
  }),
]);

function defaultChromePath() {
  const envChrome = process.env.FAWN_CHROME_BIN;
  const candidates = [
    envChrome,
    resolve(ROOT, "browser/chromium/out/fawn_release_local/chrome"),
    resolve(ROOT, "browser/chromium_webgpu_lane/out/fawn_release_local/chrome"),
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
  ].filter((value) => typeof value === "string" && value.length > 0);

  for (const candidate of candidates) {
    if (existsSync(candidate)) {
      return candidate;
    }
  }
  return candidates[0];
}

function defaultDoeLibPath() {
  const preferredExt = process.platform === "darwin" ? "dylib" : "so";
  const envDoeLib = process.env.FAWN_DOE_LIB;
  const candidates = [
    envDoeLib,
    resolve(ROOT, `runtime/zig/zig-out/lib/libwebgpu_doe.${preferredExt}`),
    resolve(ROOT, "runtime/zig/zig-out/lib/libwebgpu_doe.so"),
    resolve(ROOT, "runtime/zig/zig-out/lib/libwebgpu_doe.dylib"),
  ].filter((value) => typeof value === "string" && value.length > 0);

  for (const candidate of candidates) {
    if (existsSync(candidate)) {
      return candidate;
    }
  }
  return candidates[0];
}

const DEFAULT_CHROME = defaultChromePath();
const DEFAULT_DOE_LIB = defaultDoeLibPath();

function timestampId() {
  return new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
}

function defaultOutPath() {
  return resolve(
    ARTIFACTS_ROOT,
    timestampId(),
    DEFAULT_OUT_FILE,
  );
}

function usage() {
  console.log(`Usage:
  node browser/chromium/scripts/webgpu-playwright-ort-bench.mjs [options]

Options:
  --mode dawn|doe|both      Runtime mode to run (default: both)
  --chrome PATH             Browser executable path
  --dawn-chrome PATH        Browser executable for dawn mode (defaults to --chrome)
  --doe-chrome PATH         Browser executable for doe mode (defaults to --chrome)
  --doe-lib PATH            libwebgpu_doe.{so,dylib} path (for doe mode)
  --out PATH                Output report JSON path (default: browser/chromium/artifacts/<timestamp>/${DEFAULT_OUT_FILE})
  --allow-bench-out         Allow writing this diagnostic report under bench/out/scratch
  --headless true|false     Launch headless (default: true)
  --chrome-arg ARG          Extra Chromium arg (repeatable)
  --steady-iters N          Override steady-state iterations for all workloads
  --warmup-iters N          Override warmup iterations for all workloads
  --op-timeout-ms N         Browser operation timeout in milliseconds (default: ${DEFAULT_OP_TIMEOUT_MS})
  --strict                  Exit non-zero when any mode or workload fails
  --help                    Show this message
`);
}

function parseBool(text, flag) {
  if (text === "true") return true;
  if (text === "false") return false;
  throw new Error(`${flag} must be true or false`);
}

function parsePositiveInt(text, flag) {
  const value = Number.parseInt(text, 10);
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error(`${flag} must be a positive integer`);
  }
  return value;
}

function readOptionValue(argv, optionIndex, flag) {
  const value = argv[optionIndex + 1];
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`${flag} requires a value`);
  }
  return value;
}

function pathWithin(pathValue, rootPath) {
  const absolutePath = resolve(pathValue);
  const absoluteRoot = resolve(rootPath);
  return absolutePath === absoluteRoot || absolutePath.startsWith(`${absoluteRoot}/`);
}

function ensureAllowedOutPath(outPath, allowBenchOut) {
  if (!pathWithin(outPath, BENCH_OUT_ROOT)) {
    return;
  }
  if (!allowBenchOut) {
    throw new Error(
      `refusing to write diagnostic ORT browser output to ${BENCH_OUT_ROOT}; write under browser/chromium/artifacts or pass --allow-bench-out explicitly`,
    );
  }
  if (!pathWithin(outPath, BENCH_OUT_SCRATCH_ROOT)) {
    throw new Error(
      `diagnostic ORT browser output under bench/out must be in ${BENCH_OUT_SCRATCH_ROOT}`,
    );
  }
}

function parseArgs(argv) {
  const args = {
    mode: "both",
    chromePath: DEFAULT_CHROME,
    dawnChromePath: "",
    doeChromePath: "",
    doeLibPath: DEFAULT_DOE_LIB,
    outPath: defaultOutPath(),
    allowBenchOut: false,
    headless: true,
    chromeArgs: [],
    strict: false,
    steadyIters: 0,
    warmupIters: 0,
    opTimeoutMs: DEFAULT_OP_TIMEOUT_MS,
  };

  for (let index = 2; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === "--help" || token === "-h") {
      usage();
      process.exit(0);
    } else if (token === "--mode") {
      args.mode = readOptionValue(argv, index, "--mode");
      index += 1;
    } else if (token === "--chrome") {
      args.chromePath = readOptionValue(argv, index, "--chrome");
      index += 1;
    } else if (token === "--dawn-chrome") {
      args.dawnChromePath = readOptionValue(argv, index, "--dawn-chrome");
      index += 1;
    } else if (token === "--doe-chrome") {
      args.doeChromePath = readOptionValue(argv, index, "--doe-chrome");
      index += 1;
    } else if (token === "--doe-lib") {
      args.doeLibPath = readOptionValue(argv, index, "--doe-lib");
      index += 1;
    } else if (token === "--out") {
      args.outPath = readOptionValue(argv, index, "--out");
      index += 1;
    } else if (token === "--allow-bench-out") {
      args.allowBenchOut = true;
    } else if (token === "--headless") {
      args.headless = parseBool(readOptionValue(argv, index, "--headless"), "--headless");
      index += 1;
    } else if (token === "--chrome-arg") {
      args.chromeArgs.push(readOptionValue(argv, index, "--chrome-arg"));
      index += 1;
    } else if (token === "--steady-iters") {
      args.steadyIters = parsePositiveInt(readOptionValue(argv, index, "--steady-iters"), "--steady-iters");
      index += 1;
    } else if (token === "--warmup-iters") {
      args.warmupIters = parsePositiveInt(readOptionValue(argv, index, "--warmup-iters"), "--warmup-iters");
      index += 1;
    } else if (token === "--op-timeout-ms") {
      args.opTimeoutMs = parsePositiveInt(readOptionValue(argv, index, "--op-timeout-ms"), "--op-timeout-ms");
      index += 1;
    } else if (token === "--strict") {
      args.strict = true;
    } else {
      throw new Error(`unknown argument: ${token}`);
    }
  }

  if (!["dawn", "doe", "both"].includes(args.mode)) {
    throw new Error("--mode must be one of dawn, doe, both");
  }
  if (!args.chromePath || !existsSync(args.chromePath)) {
    throw new Error(`browser executable not found: ${args.chromePath}`);
  }
  if (args.mode !== "dawn" && !args.doeLibPath) {
    throw new Error("--doe-lib is required for doe mode");
  }
  if (args.mode !== "dawn" && !existsSync(args.doeLibPath)) {
    throw new Error(`doe runtime library not found: ${args.doeLibPath}`);
  }

  ensureAllowedOutPath(args.outPath, args.allowBenchOut);
  return args;
}

function chromePathForMode(mode, args) {
  if (mode === "dawn") {
    return args.dawnChromePath || args.chromePath;
  }
  return args.doeChromePath || args.chromePath;
}

async function loadPlaywrightChromium() {
  try {
    const mod = await import("playwright");
    return mod.chromium;
  } catch {
    // continue
  }
  try {
    const mod = await import("playwright-core");
    return mod.chromium;
  } catch {
    // continue
  }
  const localModuleUrl = pathToFileURL(
    resolve(ROOT, "browser/chromium/node_modules/playwright-core/index.mjs"),
  ).href;
  try {
    const mod = await import(localModuleUrl);
    return mod.chromium;
  } catch {
    // continue
  }
  throw new Error(
    "Playwright not found. Install with: npm install --prefix browser/chromium playwright-core",
  );
}

function startLocalServer() {
  const html = "<!doctype html><meta charset='utf-8'><title>doe-webgpu-ort-bench</title>";
  const server = http.createServer((req, res) => {
    const requestPath = new URL(req.url ?? "/", "http://127.0.0.1").pathname;
    if (requestPath !== "/") {
      const relativePath = requestPath.replace(/^\/+/, "");
      const absolutePath = resolve(ROOT, relativePath);
      if (!pathWithin(absolutePath, ROOT) || !existsSync(absolutePath)) {
        res.statusCode = 404;
        res.end("not found");
        return;
      }
      const extension = extname(absolutePath).toLowerCase();
      const contentType = extension === ".js" || extension === ".mjs"
        ? "text/javascript; charset=utf-8"
        : extension === ".json"
          ? "application/json; charset=utf-8"
          : extension === ".html"
            ? "text/html; charset=utf-8"
            : "application/octet-stream";
      res.statusCode = 200;
      res.setHeader("content-type", contentType);
      res.end(readFileSync(absolutePath));
      return;
    }
    res.statusCode = 200;
    res.setHeader("content-type", "text/html; charset=utf-8");
    res.end(html);
  });

  return new Promise((resolveServer, reject) => {
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        reject(new Error("failed to resolve local server address"));
        return;
      }
      resolveServer({
        server,
        url: `http://127.0.0.1:${address.port}/`,
        port: address.port,
      });
    });
  });
}

function baseLaunchArgs(port) {
  const args = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--ignore-gpu-blocklist",
    "--enable-unsafe-webgpu",
    `--unsafely-treat-insecure-origin-as-secure=http://127.0.0.1:${port}`,
  ];
  if (process.platform === "linux") {
    args.push("--use-angle=vulkan");
  }
  return args;
}

function runtimeArgs(mode, doeLibPath) {
  if (mode === "dawn") {
    return ["--use-webgpu-runtime=dawn"];
  }
  return [
    "--use-webgpu-runtime=doe",
    `--doe-webgpu-library-path=${doeLibPath}`,
  ];
}

function stableObject(value) {
  if (Array.isArray(value)) {
    return value.map((entry) => stableObject(entry));
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, stableObject(value[key])]),
    );
  }
  return value;
}

function hashHex(value) {
  const canonical = JSON.stringify(stableObject(value));
  return createHash(HASH_ALGORITHM).update(canonical).digest("hex");
}

function attachHashChain(entries, moduleName = REPORT_KIND) {
  let previousHash = "0".repeat(64);
  return entries.map((entry, index) => {
    const traceEntry = {
      module: moduleName,
      opCode: "mode_result",
      seq: index + 1,
      ...entry,
    };
    const hash = hashHex({ previousHash, entry: traceEntry });
    const withHash = { ...traceEntry, hash, previousHash };
    previousHash = hash;
    return withHash;
  });
}

function percentile(sortedValues, ratio) {
  if (sortedValues.length === 0) {
    return null;
  }
  const index = Math.min(
    sortedValues.length - 1,
    Math.max(0, Math.ceil(sortedValues.length * ratio) - 1),
  );
  return sortedValues[index];
}

function summarizeSamples(samples) {
  const sorted = [...samples].sort((left, right) => left - right);
  const mean = samples.reduce((sum, value) => sum + value, 0) / samples.length;
  return {
    samplesMs: samples,
    p50Ms: percentile(sorted, 0.5),
    p95Ms: percentile(sorted, 0.95),
    minMs: sorted[0],
    maxMs: sorted[sorted.length - 1],
    meanMs: mean,
  };
}

async function loadOnnx() {
  const mod = await import(pathToFileURL(ONNX_PROTO_PATH).href);
  return mod.onnx || mod.default?.onnx || mod.default || mod;
}

function floatBytes(floatArray) {
  return new Uint8Array(
    floatArray.buffer.slice(
      floatArray.byteOffset,
      floatArray.byteOffset + floatArray.byteLength,
    ),
  );
}

function buildIdentityModelBytes(onnx, dims) {
  const model = onnx.ModelProto.create({
    irVersion: 8,
    opsetImport: [{ version: 13 }],
    graph: {
      name: "identity_graph",
      input: [{
        name: "A",
        type: {
          tensorType: {
            elemType: onnx.TensorProto.DataType.FLOAT,
            shape: { dim: [{ dimValue: dims.m }, { dimValue: dims.k }] },
          },
        },
      }],
      output: [{
        name: "Y",
        type: {
          tensorType: {
            elemType: onnx.TensorProto.DataType.FLOAT,
            shape: { dim: [{ dimValue: dims.m }, { dimValue: dims.k }] },
          },
        },
      }],
      node: [{ opType: "Identity", input: ["A"], output: ["Y"] }],
    },
  });
  return Array.from(onnx.ModelProto.encode(model).finish());
}

function buildMatmulModelBytes(onnx, dims) {
  const weights = new Float32Array(dims.k * dims.n);
  for (let index = 0; index < weights.length; index += 1) {
    weights[index] = ((index % 17) - 8) / 8;
  }
  const model = onnx.ModelProto.create({
    irVersion: 8,
    opsetImport: [{ version: 13 }],
    graph: {
      name: "matmul_graph",
      input: [{
        name: "A",
        type: {
          tensorType: {
            elemType: onnx.TensorProto.DataType.FLOAT,
            shape: { dim: [{ dimValue: dims.m }, { dimValue: dims.k }] },
          },
        },
      }],
      output: [{
        name: "Y",
        type: {
          tensorType: {
            elemType: onnx.TensorProto.DataType.FLOAT,
            shape: { dim: [{ dimValue: dims.m }, { dimValue: dims.n }] },
          },
        },
      }],
      initializer: [{
        name: "B",
        dataType: onnx.TensorProto.DataType.FLOAT,
        dims: [dims.k, dims.n],
        rawData: floatBytes(weights),
      }],
      node: [{ opType: "MatMul", input: ["A", "B"], output: ["Y"] }],
    },
  });
  return Array.from(onnx.ModelProto.encode(model).finish());
}

function inputValuesForSpec(spec) {
  const values = new Float32Array(spec.dims.m * spec.dims.k);
  for (let index = 0; index < values.length; index += 1) {
    values[index] = ((index % 13) + 1) / 13;
  }
  return Array.from(values);
}

async function buildWorkloads(args) {
  const onnx = await loadOnnx();
  return DEFAULT_WORKLOAD_SPECS.map((spec) => ({
    id: spec.id,
    name: spec.name,
    kind: spec.kind,
    dims: spec.dims,
    modelBytes: spec.kind === "identity"
      ? buildIdentityModelBytes(onnx, spec.dims)
      : buildMatmulModelBytes(onnx, spec.dims),
    inputValues: inputValuesForSpec(spec),
    warmupIters: args.warmupIters || spec.warmupIters,
    steadyIters: args.steadyIters || spec.steadyIters,
  }));
}

async function runMode(chromium, mode, args, localUrl, localPort, workloads) {
  const executablePath = chromePathForMode(mode, args);
  const launchArgs = [
    ...baseLaunchArgs(localPort),
    ...args.chromeArgs,
    ...runtimeArgs(mode, args.doeLibPath),
  ];
  const startedAt = Date.now();
  let browser = null;

  try {
    browser = await chromium.launch({
      executablePath,
      headless: args.headless,
      args: launchArgs,
      timeout: args.opTimeoutMs,
    });
    const browserVersion = browser.version();
    const page = await browser.newPage();
    await page.goto(localUrl, { waitUntil: "load", timeout: args.opTimeoutMs });

    const suite = await page.evaluate(
      async ({ baseUrl, workloads: pageWorkloads, opTimeoutMs, ortModulePath }) => {
        const ort = await import(new URL(ortModulePath, baseUrl).href);
        const withOpTimeout = async (label, promiseFactory) => {
          let timeoutId = null;
          try {
            return await Promise.race([
              promiseFactory(),
              new Promise((_, reject) => {
                timeoutId = setTimeout(
                  () => reject(new Error(`${label} timed out after ${opTimeoutMs}ms`)),
                  opTimeoutMs,
                );
              }),
            ]);
          } finally {
            if (timeoutId !== null) {
              clearTimeout(timeoutId);
            }
          }
        };
        const sha256Hex = async (typedArray) => {
          const bytes = new Uint8Array(
            typedArray.buffer.slice(
              typedArray.byteOffset,
              typedArray.byteOffset + typedArray.byteLength,
            ),
          );
          const digest = await crypto.subtle.digest("SHA-256", bytes);
          return Array.from(new Uint8Array(digest))
            .map((value) => value.toString(16).padStart(2, "0"))
            .join("");
        };
        const percentileMs = (samples, ratio) => {
          if (samples.length === 0) {
            return null;
          }
          const sorted = [...samples].sort((left, right) => left - right);
          const index = Math.min(
            sorted.length - 1,
            Math.max(0, Math.ceil(sorted.length * ratio) - 1),
          );
          return sorted[index];
        };
        const summarize = (samples) => ({
          samplesMs: samples,
          p50Ms: percentileMs(samples, 0.5),
          p95Ms: percentileMs(samples, 0.95),
          minMs: Math.min(...samples),
          maxMs: Math.max(...samples),
          meanMs: samples.reduce((sum, value) => sum + value, 0) / samples.length,
        });

        const result = {
          webgpuAvailable: typeof navigator.gpu !== "undefined",
          adapterAvailable: false,
          adapterInfo: null,
          browserUserAgent: navigator.userAgent,
          workloads: [],
          errors: [],
        };

        if (!result.webgpuAvailable) {
          result.errors.push("WebGPU surface is unavailable");
          return result;
        }

        let adapter;
        try {
          adapter = await withOpTimeout("requestAdapter", () => navigator.gpu.requestAdapter());
          if (!adapter) {
            result.errors.push("requestAdapter returned null");
            return result;
          }
          result.adapterAvailable = true;
          result.adapterInfo = "info" in adapter ? adapter.info : null;
          await withOpTimeout("requestDevice", () => adapter.requestDevice());
        } catch (error) {
          result.errors.push(`adapter/device init failed: ${String(error)}`);
          return result;
        }

        for (const workload of pageWorkloads) {
          const entry = {
            id: workload.id,
            name: workload.name,
            kind: workload.kind,
            dims: workload.dims,
            warmupIters: workload.warmupIters,
            steadyIters: workload.steadyIters,
            sessionCreateMs: null,
            firstRunMs: null,
            steadyState: null,
            outputDigest: null,
            outputLength: null,
            outputPreview: null,
            error: null,
          };
          try {
            const modelBytes = new Uint8Array(workload.modelBytes);
            const inputTensor = new ort.Tensor(
              "float32",
              new Float32Array(workload.inputValues),
              [workload.dims.m, workload.dims.k],
            );
            const createStartedAt = performance.now();
            const session = await withOpTimeout(
              `${workload.id} createSession`,
              () => ort.InferenceSession.create(modelBytes, { executionProviders: ["webgpu"] }),
            );
            entry.sessionCreateMs = performance.now() - createStartedAt;

            const firstRunStartedAt = performance.now();
            const firstOutputs = await withOpTimeout(
              `${workload.id} firstRun`,
              () => session.run({ A: inputTensor }),
            );
            entry.firstRunMs = performance.now() - firstRunStartedAt;
            entry.outputDigest = await sha256Hex(firstOutputs.Y.data);
            entry.outputLength = firstOutputs.Y.data.length;
            entry.outputPreview = Array.from(firstOutputs.Y.data.slice(0, 8));

            for (let index = 0; index < workload.warmupIters; index += 1) {
              await withOpTimeout(
                `${workload.id} warmup-${index}`,
                () => session.run({ A: inputTensor }),
              );
            }

            const steadySamples = [];
            for (let index = 0; index < workload.steadyIters; index += 1) {
              const runStartedAt = performance.now();
              await withOpTimeout(
                `${workload.id} steady-${index}`,
                () => session.run({ A: inputTensor }),
              );
              steadySamples.push(performance.now() - runStartedAt);
            }
            entry.steadyState = summarize(steadySamples);
          } catch (error) {
            entry.error = String(error);
          }
          result.workloads.push(entry);
        }

        return result;
      },
      {
        baseUrl: localUrl,
        workloads,
        opTimeoutMs: args.opTimeoutMs,
        ortModulePath: ORT_MODULE_PATH,
      },
    );

    return {
      mode,
      executablePath,
      browserVersion,
      runtimeArgs: launchArgs,
      elapsedMs: Date.now() - startedAt,
      ...suite,
    };
  } catch (error) {
    return {
      mode,
      executablePath,
      browserVersion: null,
      runtimeArgs: launchArgs,
      elapsedMs: Date.now() - startedAt,
      webgpuAvailable: false,
      adapterAvailable: false,
      adapterInfo: null,
      browserUserAgent: null,
      workloads: [],
      errors: [String(error)],
    };
  } finally {
    await browser?.close();
  }
}

function hasFailure(modeResult) {
  if (!modeResult.webgpuAvailable || !modeResult.adapterAvailable) {
    return true;
  }
  if (modeResult.errors.length > 0) {
    return true;
  }
  return modeResult.workloads.some((workload) => workload.error);
}

function safeDeltaPercent(dawnValue, doeValue) {
  if (!Number.isFinite(dawnValue) || !Number.isFinite(doeValue) || dawnValue === 0) {
    return null;
  }
  return ((dawnValue - doeValue) / dawnValue) * 100;
}

function computeComparison(modeResults) {
  const dawn = modeResults.find((entry) => entry.mode === "dawn");
  const doe = modeResults.find((entry) => entry.mode === "doe");
  if (!dawn || !doe) {
    return null;
  }
  const perWorkload = [];
  for (const dawnWorkload of dawn.workloads) {
    const doeWorkload = doe.workloads.find((entry) => entry.id === dawnWorkload.id);
    if (!doeWorkload) {
      continue;
    }
    perWorkload.push({
      id: dawnWorkload.id,
      sessionCreateDeltaPercent: safeDeltaPercent(
        dawnWorkload.sessionCreateMs,
        doeWorkload.sessionCreateMs,
      ),
      firstRunDeltaPercent: safeDeltaPercent(
        dawnWorkload.firstRunMs,
        doeWorkload.firstRunMs,
      ),
      steadyStateP50DeltaPercent: safeDeltaPercent(
        dawnWorkload.steadyState?.p50Ms,
        doeWorkload.steadyState?.p50Ms,
      ),
      steadyStateP95DeltaPercent: safeDeltaPercent(
        dawnWorkload.steadyState?.p95Ms,
        doeWorkload.steadyState?.p95Ms,
      ),
      matchingOutputDigest: Boolean(
        dawnWorkload.outputDigest
        && doeWorkload.outputDigest
        && dawnWorkload.outputDigest === doeWorkload.outputDigest,
      ),
    });
  }
  return { perWorkload };
}

async function main() {
  const args = parseArgs(process.argv);
  const chromium = await loadPlaywrightChromium();
  const workloads = await buildWorkloads(args);
  const { server, url, port } = await startLocalServer();
  const modes = args.mode === "both" ? ["dawn", "doe"] : [args.mode];
  const modeResults = [];
  let failed = false;

  try {
    for (const mode of modes) {
      const result = await runMode(chromium, mode, args, url, port, workloads);
      modeResults.push(result);
      const status = hasFailure(result) ? "FAIL" : "PASS";
      const workloadSummary = result.workloads
        .map((workload) => {
          if (workload.error) {
            return `${workload.id}=ERR`;
          }
          return `${workload.id}=create:${workload.sessionCreateMs?.toFixed(2)}ms first:${workload.firstRunMs?.toFixed(2)}ms p50:${workload.steadyState?.p50Ms?.toFixed(2)}ms`;
        })
        .join(" ");
      console.log(
        `[${status}] ${mode}: webgpu=${result.webgpuAvailable} adapter=${result.adapterAvailable} ${workloadSummary}`,
      );
      if (hasFailure(result)) {
        failed = true;
      }
    }
  } finally {
    server.close();
  }

  const modeResultsWithHashes = attachHashChain(modeResults);
  const report = {
    schemaVersion: REPORT_SCHEMA_VERSION,
    reportKind: REPORT_KIND,
    comparisonStatus: "diagnostic",
    claimStatus: "diagnostic",
    timingClass: TIMING_CLASS,
    timingSource: TIMING_SOURCE,
    generatedAt: new Date().toISOString(),
    hashAlgorithm: HASH_ALGORITHM,
    invocation: {
      argv: process.argv.slice(2),
      cwd: process.cwd(),
      nodeVersion: process.version,
      platform: process.platform,
      arch: process.arch,
    },
    methodology: {
      workloadSpecs: workloads.map((workload) => ({
        id: workload.id,
        kind: workload.kind,
        dims: workload.dims,
        warmupIters: workload.warmupIters,
        steadyIters: workload.steadyIters,
      })),
      operationTimeoutMs: args.opTimeoutMs,
      notes: [
        "This browser ORT harness is diagnostic, not a strict claim lane.",
        "A meaningful Dawn-vs-Doe comparison requires a Doe-enabled Chromium binary for doe mode.",
      ],
    },
    modeResults: modeResultsWithHashes,
    comparison: computeComparison(modeResultsWithHashes),
  };
  report.reportHash = hashHex(report);

  mkdirSync(dirname(args.outPath), { recursive: true });
  writeFileSync(args.outPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  console.log(`report written: ${args.outPath}`);

  if (args.strict && failed) {
    process.exit(1);
  }
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exit(1);
});

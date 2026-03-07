#!/usr/bin/env node
import { createHash } from "node:crypto";
import http from "node:http";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(SCRIPT_DIR, "..", "..", "..");

function defaultChromePath() {
  const releaseLocalOut =
    process.env.FAWN_CHROMIUM_RELEASE_LOCAL_OUT ??
    resolve(ROOT, "nursery/fawn-browser/out/fawn_release_local");
  const envChrome = process.env.FAWN_CHROME_BIN;
  const candidates = [
    envChrome,
    resolve(releaseLocalOut, "chrome"),
    resolve(releaseLocalOut, "Fawn.app/Contents/MacOS/Chromium"),
    resolve(releaseLocalOut, "Chromium.app/Contents/MacOS/Chromium"),
    resolve(ROOT, "nursery/fawn-browser/src/out/fawn_release/chrome"),
    resolve(ROOT, "nursery/fawn-browser/src/out/fawn_release/Fawn.app/Contents/MacOS/Chromium"),
    resolve(ROOT, "nursery/fawn-browser/src/out/fawn_release/Chromium.app/Contents/MacOS/Chromium"),
    resolve(ROOT, "nursery/fawn-browser/src/out/fawn_debug/chrome"),
    resolve(ROOT, "nursery/fawn-browser/src/out/fawn_debug/Fawn.app/Contents/MacOS/Chromium"),
    resolve(ROOT, "nursery/fawn-browser/src/out/fawn_debug/Chromium.app/Contents/MacOS/Chromium"),
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
    resolve(ROOT, `zig/zig-out/lib/libwebgpu_doe.${preferredExt}`),
    resolve(ROOT, "zig/zig-out/lib/libwebgpu_doe.so"),
    resolve(ROOT, "zig/zig-out/lib/libwebgpu_doe.dylib"),
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
const BENCH_OUT_ROOT = resolve(ROOT, "bench/out");
const DEFAULT_OUT_FILE = "dawn-vs-doe.tracka.playwright-smoke.diagnostic.json";
const DEFAULT_UPLOAD_ITERS = 500;
const DEFAULT_DISPATCH_ITERS = 200;
const DEFAULT_SUITE_TIMEOUT_MS = 120000;
const DEFAULT_OPERATION_TIMEOUT_MS = 30000;
const DEFAULT_BROWSER_CLOSE_TIMEOUT_MS = 10000;
const REPORT_SCHEMA_VERSION = 1;
const REPORT_KIND = "chromium-webgpu-playwright-smoke";
const BENCHMARK_CLASS = "diagnostic";
const TIMING_CLASS = "browser-operation-proxy";
const TIMING_SOURCE = "performance.now";
const HASH_ALGORITHM = "sha256";
const UPLOAD_WARMUP_ITERS = 50;
const DISPATCH_WARMUP_ITERS = 20;
const ADAPTER_LIMIT_KEYS = [
  "maxTextureDimension1D",
  "maxTextureDimension2D",
  "maxTextureDimension3D",
  "maxTextureArrayLayers",
  "maxBindGroups",
  "maxBindingsPerBindGroup",
  "maxDynamicUniformBuffersPerPipelineLayout",
  "maxDynamicStorageBuffersPerPipelineLayout",
  "maxSampledTexturesPerShaderStage",
  "maxSamplersPerShaderStage",
  "maxStorageBuffersPerShaderStage",
  "maxStorageTexturesPerShaderStage",
  "maxUniformBuffersPerShaderStage",
  "maxUniformBufferBindingSize",
  "maxStorageBufferBindingSize",
  "maxBufferSize",
  "maxComputeInvocationsPerWorkgroup",
  "maxComputeWorkgroupSizeX",
  "maxComputeWorkgroupSizeY",
  "maxComputeWorkgroupSizeZ",
  "maxComputeWorkgroupsPerDimension",
  "maxComputeWorkgroupStorageSize",
];

function usage() {
  console.log(`Usage:
  node nursery/fawn-browser/scripts/webgpu-playwright-smoke.mjs [options]

Options:
  --mode dawn|doe|both      Runtime mode to run (default: both)
  --chrome PATH             Chrome binary path
  --doe-lib PATH            libwebgpu_doe.{so,dylib} path (for doe mode)
  --out PATH                JSON report output path (default: nursery/fawn-browser/artifacts/<timestamp>/${DEFAULT_OUT_FILE})
  --allow-bench-out         Allow writing this diagnostic report under bench/out
  --headless true|false     Launch headless (default: true)
  --chrome-arg ARG          Extra Chromium arg (repeatable)
  --upload-iters N          queue.writeBuffer timed iterations (default: 500)
  --dispatch-iters N        compute dispatch timed iterations (default: 200)
  --suite-timeout-ms N      Max time for one mode suite run (default: 120000)
  --op-timeout-ms N         Max time for one async WebGPU wait op (default: 30000)
  --strict                  Exit non-zero if any smoke test fails
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

function timeoutError(label, timeoutMs) {
  return new Error(`${label} timed out after ${timeoutMs}ms`);
}

async function withTimeout(promise, timeoutMs, label) {
  let timeoutId = null;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timeoutId = setTimeout(() => reject(timeoutError(label, timeoutMs)), timeoutMs);
      }),
    ]);
  } finally {
    if (timeoutId !== null) {
      clearTimeout(timeoutId);
    }
  }
}

function makeFailedResult(mode, args, launchArgs, browserVersion, startMs, error) {
  const errorText = String(error?.stack ?? error);
  return {
    mode,
    runtimeArgs: runtimeArgs(mode, args.doeLibPath),
    launchArgs,
    browserVersion,
    elapsedMs: Date.now() - startMs,
    webgpuAvailable: false,
    adapterAvailable: false,
    adapterInfo: null,
    features: [],
    limits: {},
    wgslLanguageFeatures: [],
    smoke: {
      computeIncrement: { pass: false, actual: null, expected: [2, 3, 4, 5], error: errorText },
      renderTriangle: { pass: false, centerRgba: null, error: errorText },
    },
    benches: {
      writeBuffer64kbUsPerOp: null,
      computeDispatchUsPerOp: null,
      iterations: { upload: args.uploadIters, dispatch: args.dispatchIters },
      errors: [errorText],
    },
    errors: [errorText],
  };
}

function timestampId() {
  return new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
}

function defaultOutPath() {
  return resolve(
    ROOT,
    "nursery/fawn-browser/artifacts",
    timestampId(),
    DEFAULT_OUT_FILE,
  );
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
  if (!allowBenchOut && pathWithin(outPath, BENCH_OUT_ROOT)) {
    throw new Error(
      `refusing to write diagnostic browser smoke output to ${BENCH_OUT_ROOT}; write under nursery/fawn-browser/artifacts or pass --allow-bench-out explicitly`,
    );
  }
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

function attachHashChain(entries) {
  let previousHash = null;
  return entries.map((entry) => {
    const hash = hashHex({ previousHash, entry });
    const withHash = { ...entry, previousHash, hash };
    previousHash = hash;
    return withHash;
  });
}

function parseArgs(argv) {
  const args = {
    mode: "both",
    chromePath: DEFAULT_CHROME,
    doeLibPath: DEFAULT_DOE_LIB,
    outPath: defaultOutPath(),
    allowBenchOut: false,
    headless: true,
    chromeArgs: [],
    uploadIters: DEFAULT_UPLOAD_ITERS,
    dispatchIters: DEFAULT_DISPATCH_ITERS,
    suiteTimeoutMs: DEFAULT_SUITE_TIMEOUT_MS,
    opTimeoutMs: DEFAULT_OPERATION_TIMEOUT_MS,
    strict: false,
  };

  for (let i = 2; i < argv.length; i += 1) {
    const token = argv[i];
    if (token === "--help" || token === "-h") {
      usage();
      process.exit(0);
    } else if (token === "--strict") {
      args.strict = true;
    } else if (token === "--allow-bench-out") {
      args.allowBenchOut = true;
    } else if (token === "--mode") {
      args.mode = readOptionValue(argv, i, "--mode").toLowerCase();
      i += 1;
    } else if (token === "--chrome") {
      args.chromePath = readOptionValue(argv, i, "--chrome");
      i += 1;
    } else if (token === "--doe-lib") {
      args.doeLibPath = readOptionValue(argv, i, "--doe-lib");
      i += 1;
    } else if (token === "--out") {
      args.outPath = readOptionValue(argv, i, "--out");
      i += 1;
    } else if (token === "--headless") {
      args.headless = parseBool(readOptionValue(argv, i, "--headless"), "--headless");
      i += 1;
    } else if (token === "--chrome-arg") {
      args.chromeArgs.push(readOptionValue(argv, i, "--chrome-arg"));
      i += 1;
    } else if (token === "--upload-iters") {
      args.uploadIters = parsePositiveInt(readOptionValue(argv, i, "--upload-iters"), "--upload-iters");
      i += 1;
    } else if (token === "--dispatch-iters") {
      args.dispatchIters = parsePositiveInt(
        readOptionValue(argv, i, "--dispatch-iters"),
        "--dispatch-iters",
      );
      i += 1;
    } else if (token === "--suite-timeout-ms") {
      args.suiteTimeoutMs = parsePositiveInt(
        readOptionValue(argv, i, "--suite-timeout-ms"),
        "--suite-timeout-ms",
      );
      i += 1;
    } else if (token === "--op-timeout-ms") {
      args.opTimeoutMs = parsePositiveInt(
        readOptionValue(argv, i, "--op-timeout-ms"),
        "--op-timeout-ms",
      );
      i += 1;
    } else {
      throw new Error(`unknown argument: ${token}`);
    }
  }

  if (!["dawn", "doe", "both"].includes(args.mode)) {
    throw new Error("--mode must be one of dawn, doe, both");
  }
  ensureAllowedOutPath(args.outPath, args.allowBenchOut);
  if (!existsSync(args.chromePath)) {
    throw new Error(`chrome binary not found: ${args.chromePath}`);
  }
  if (args.mode !== "dawn" && !existsSync(args.doeLibPath)) {
    throw new Error(`doe runtime library not found: ${args.doeLibPath}`);
  }
  return args;
}

async function loadChromiumDriver() {
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

  throw new Error(
    "Playwright not found. Install with: npm install --prefix nursery/fawn-browser playwright-core",
  );
}

function startLocalServer() {
  const html = "<!doctype html><meta charset='utf-8'><title>doe-webgpu-smoke</title>";
  const server = http.createServer((_, res) => {
    res.statusCode = 200;
    res.setHeader("content-type", "text/html; charset=utf-8");
    res.end(html);
  });

  return new Promise((resolveServer, reject) => {
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const addr = server.address();
      if (!addr || typeof addr === "string") {
        reject(new Error("failed to resolve local server address"));
        return;
      }
      resolveServer({
        server,
        url: `http://127.0.0.1:${addr.port}/`,
        port: addr.port,
      });
    });
  });
}

function baseLaunchArgs(port) {
  return [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--ignore-gpu-blocklist",
    "--enable-unsafe-webgpu",
    `--unsafely-treat-insecure-origin-as-secure=http://127.0.0.1:${port}`,
  ];
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

function safeDeltaPercent(dawnValue, doeValue) {
  if (!Number.isFinite(dawnValue) || !Number.isFinite(doeValue) || dawnValue === 0) {
    return null;
  }
  return ((dawnValue - doeValue) / dawnValue) * 100;
}

function extractModeResult(modeResults, mode) {
  return modeResults.find((entry) => entry.mode === mode) ?? null;
}

async function runMode(chromium, mode, args, localUrl, localPort) {
  const launchArgs = [
    ...baseLaunchArgs(localPort),
    ...args.chromeArgs,
    ...runtimeArgs(mode, args.doeLibPath),
  ];
  const startMs = Date.now();
  let browser = null;
  let browserVersion = null;

  try {
    browser = await chromium.launch({
      executablePath: args.chromePath,
      headless: args.headless,
      args: launchArgs,
      timeout: 120000,
    });
    browserVersion = browser.version();
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto(localUrl, { waitUntil: "load", timeout: 120000 });

    const suite = await withTimeout(
      page.evaluate(
        async ({
          uploadIters,
          dispatchIters,
          uploadWarmupIters,
          dispatchWarmupIters,
          adapterLimitKeys,
          opTimeoutMs,
        }) => {
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

        const result = {
          userAgent: navigator.userAgent,
          webgpuAvailable: typeof navigator.gpu !== "undefined",
          adapterAvailable: false,
          adapterInfo: null,
          features: [],
          limits: {},
          wgslLanguageFeatures: [],
          smoke: {
            computeIncrement: { pass: false, actual: null, expected: [2, 3, 4, 5], error: null },
            renderTriangle: { pass: false, centerRgba: null, error: null },
          },
          benches: {
            writeBuffer64kbUsPerOp: null,
            computeDispatchUsPerOp: null,
            iterations: { upload: uploadIters, dispatch: dispatchIters },
            errors: [],
          },
          errors: [],
        };

        if (!result.webgpuAvailable) {
          result.errors.push("navigator.gpu is unavailable");
          return result;
        }

        let adapter = null;
        let device = null;
        try {
          adapter = await withOpTimeout("requestAdapter", () => navigator.gpu.requestAdapter());
          if (!adapter) {
            result.errors.push("requestAdapter returned null");
            return result;
          }
          result.adapterAvailable = true;
          result.features = Array.from(adapter.features).sort();
          if ("info" in adapter) {
            result.adapterInfo = adapter.info;
          }
          for (const key of adapterLimitKeys) {
            const value = adapter.limits[key];
            if (typeof value === "number") {
              result.limits[key] = value;
            }
          }
          if ("wgslLanguageFeatures" in navigator.gpu) {
            result.wgslLanguageFeatures = Array.from(navigator.gpu.wgslLanguageFeatures).sort();
          }
          device = await withOpTimeout("requestDevice", () => adapter.requestDevice());
        } catch (error) {
          result.errors.push(`adapter/device init failed: ${String(error)}`);
          return result;
        }

        try {
          const input = new Uint32Array([1, 2, 3, 4]);
          const storage = device.createBuffer({
            size: input.byteLength,
            usage:
              GPUBufferUsage.STORAGE |
              GPUBufferUsage.COPY_SRC |
              GPUBufferUsage.COPY_DST,
          });
          device.queue.writeBuffer(storage, 0, input);
          const readback = device.createBuffer({
            size: input.byteLength,
            usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ,
          });

          const shader = device.createShaderModule({
            code: `
              @group(0) @binding(0) var<storage, read_write> data: array<u32>;
              @compute @workgroup_size(1)
              fn main(@builtin(global_invocation_id) gid : vec3<u32>) {
                let idx = gid.x;
                data[idx] = data[idx] + 1u;
              }
            `,
          });
          const pipeline = device.createComputePipeline({
            layout: "auto",
            compute: { module: shader, entryPoint: "main" },
          });
          const bindGroup = device.createBindGroup({
            layout: pipeline.getBindGroupLayout(0),
            entries: [{ binding: 0, resource: { buffer: storage } }],
          });

          const encoder = device.createCommandEncoder();
          const pass = encoder.beginComputePass();
          pass.setPipeline(pipeline);
          pass.setBindGroup(0, bindGroup);
          pass.dispatchWorkgroups(input.length);
          pass.end();
          encoder.copyBufferToBuffer(storage, 0, readback, 0, input.byteLength);
          device.queue.submit([encoder.finish()]);
          await withOpTimeout("computeIncrement readback mapAsync", () =>
            readback.mapAsync(GPUMapMode.READ),
          );
          const actual = Array.from(new Uint32Array(readback.getMappedRange()));
          readback.unmap();
          result.smoke.computeIncrement.actual = actual;
          result.smoke.computeIncrement.pass =
            JSON.stringify(actual) === JSON.stringify(result.smoke.computeIncrement.expected);
        } catch (error) {
          result.smoke.computeIncrement.error = String(error);
        }

        try {
          const width = 64;
          const height = 64;
          const format = "rgba8unorm";
          const texture = device.createTexture({
            size: { width, height, depthOrArrayLayers: 1 },
            format,
            usage: GPUTextureUsage.RENDER_ATTACHMENT | GPUTextureUsage.COPY_SRC,
          });

          const shader = device.createShaderModule({
            code: `
              @vertex
              fn vs(@builtin(vertex_index) index : u32) -> @builtin(position) vec4<f32> {
                var pos = array<vec2<f32>, 3>(
                  vec2<f32>(-0.6, -0.6),
                  vec2<f32>( 0.6, -0.6),
                  vec2<f32>( 0.0,  0.6)
                );
                return vec4<f32>(pos[index], 0.0, 1.0);
              }

              @fragment
              fn fs() -> @location(0) vec4<f32> {
                return vec4<f32>(1.0, 0.0, 0.0, 1.0);
              }
            `,
          });
          const pipeline = device.createRenderPipeline({
            layout: "auto",
            vertex: { module: shader, entryPoint: "vs" },
            fragment: {
              module: shader,
              entryPoint: "fs",
              targets: [{ format }],
            },
            primitive: { topology: "triangle-list" },
          });

          const encoder = device.createCommandEncoder();
          const pass = encoder.beginRenderPass({
            colorAttachments: [
              {
                view: texture.createView(),
                clearValue: { r: 0, g: 0, b: 0, a: 1 },
                loadOp: "clear",
                storeOp: "store",
              },
            ],
          });
          pass.setPipeline(pipeline);
          pass.draw(3);
          pass.end();

          const bytesPerRow = 256;
          const readback = device.createBuffer({
            size: bytesPerRow * height,
            usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ,
          });
          encoder.copyTextureToBuffer(
            { texture },
            { buffer: readback, bytesPerRow, rowsPerImage: height },
            { width, height, depthOrArrayLayers: 1 },
          );
          device.queue.submit([encoder.finish()]);
          await withOpTimeout("renderTriangle readback mapAsync", () =>
            readback.mapAsync(GPUMapMode.READ),
          );
          const data = new Uint8Array(readback.getMappedRange());
          const centerOffset = Math.floor(height / 2) * bytesPerRow + Math.floor(width / 2) * 4;
          const centerRgba = Array.from(data.slice(centerOffset, centerOffset + 4));
          readback.unmap();
          texture.destroy();
          result.smoke.renderTriangle.centerRgba = centerRgba;
          result.smoke.renderTriangle.pass =
            centerRgba[0] > 100 &&
            centerRgba[0] > centerRgba[1] + 20 &&
            centerRgba[0] > centerRgba[2] + 20;
        } catch (error) {
          result.smoke.renderTriangle.error = String(error);
        }

        let benchDevice = device;
        if (!result.smoke.renderTriangle.pass) {
          try {
            benchDevice = await withOpTimeout("bench fallback requestDevice", () =>
              adapter.requestDevice(),
            );
          } catch (error) {
            const message = `bench fallback device init failed: ${String(error)}`;
            result.benches.errors.push(message);
            result.errors.push(message);
            return result;
          }
        }

        try {
          const size = 64 * 1024;
          const payload = new Uint8Array(size);
          const uploadBuffer = benchDevice.createBuffer({
            size,
            usage: GPUBufferUsage.COPY_DST,
          });
          for (let i = 0; i < uploadWarmupIters; i += 1) {
            benchDevice.queue.writeBuffer(uploadBuffer, 0, payload);
          }
          await withOpTimeout("writeBuffer warmup onSubmittedWorkDone", () =>
            benchDevice.queue.onSubmittedWorkDone(),
          );
          const uploadStart = performance.now();
          for (let i = 0; i < uploadIters; i += 1) {
            benchDevice.queue.writeBuffer(uploadBuffer, 0, payload);
          }
          await withOpTimeout("writeBuffer timed onSubmittedWorkDone", () =>
            benchDevice.queue.onSubmittedWorkDone(),
          );
          const uploadEnd = performance.now();
          result.benches.writeBuffer64kbUsPerOp =
            ((uploadEnd - uploadStart) * 1000) / uploadIters;
        } catch (error) {
          result.benches.errors.push(`writeBuffer bench failed: ${String(error)}`);
        }

        try {
          const shader = benchDevice.createShaderModule({
            code: `
              @compute @workgroup_size(1)
              fn main() {}
            `,
          });
          const pipeline = benchDevice.createComputePipeline({
            layout: "auto",
            compute: { module: shader, entryPoint: "main" },
          });
          for (let i = 0; i < dispatchWarmupIters; i += 1) {
            const encoder = benchDevice.createCommandEncoder();
            const pass = encoder.beginComputePass();
            pass.setPipeline(pipeline);
            pass.dispatchWorkgroups(1);
            pass.end();
            benchDevice.queue.submit([encoder.finish()]);
          }
          await withOpTimeout("dispatch warmup onSubmittedWorkDone", () =>
            benchDevice.queue.onSubmittedWorkDone(),
          );
          const dispatchStart = performance.now();
          for (let i = 0; i < dispatchIters; i += 1) {
            const encoder = benchDevice.createCommandEncoder();
            const pass = encoder.beginComputePass();
            pass.setPipeline(pipeline);
            pass.dispatchWorkgroups(1);
            pass.end();
            benchDevice.queue.submit([encoder.finish()]);
          }
          await withOpTimeout("dispatch timed onSubmittedWorkDone", () =>
            benchDevice.queue.onSubmittedWorkDone(),
          );
          const dispatchEnd = performance.now();
          result.benches.computeDispatchUsPerOp =
            ((dispatchEnd - dispatchStart) * 1000) / dispatchIters;
        } catch (error) {
          result.benches.errors.push(`dispatch bench failed: ${String(error)}`);
        }

        return result;
      },
        {
          uploadIters: args.uploadIters,
          dispatchIters: args.dispatchIters,
          uploadWarmupIters: UPLOAD_WARMUP_ITERS,
          dispatchWarmupIters: DISPATCH_WARMUP_ITERS,
          adapterLimitKeys: ADAPTER_LIMIT_KEYS,
          opTimeoutMs: args.opTimeoutMs,
        },
      ),
      args.suiteTimeoutMs,
      `${mode} smoke suite`,
    );

    return {
      mode,
      runtimeArgs: runtimeArgs(mode, args.doeLibPath),
      launchArgs,
      browserVersion,
      elapsedMs: Date.now() - startMs,
      ...suite,
    };
  } catch (error) {
    return makeFailedResult(mode, args, launchArgs, browserVersion, startMs, error);
  } finally {
    if (browser) {
      try {
        await withTimeout(browser.close(), DEFAULT_BROWSER_CLOSE_TIMEOUT_MS, `${mode} browser close`);
      } catch (closeError) {
        console.warn(`[WARN] ${mode}: browser close failed: ${String(closeError)}`);
      }
    }
  }
}

function computeComparison(modeResults) {
  const dawn = extractModeResult(modeResults, "dawn");
  const doe = extractModeResult(modeResults, "doe");
  if (!dawn || !doe) return null;

  return {
    writeBuffer64kbDeltaPercent: safeDeltaPercent(
      dawn.benches.writeBuffer64kbUsPerOp,
      doe.benches.writeBuffer64kbUsPerOp,
    ),
    computeDispatchDeltaPercent: safeDeltaPercent(
      dawn.benches.computeDispatchUsPerOp,
      doe.benches.computeDispatchUsPerOp,
    ),
    bothComputeSmokePass:
      dawn.smoke.computeIncrement.pass && doe.smoke.computeIncrement.pass,
    bothRenderSmokePass: dawn.smoke.renderTriangle.pass && doe.smoke.renderTriangle.pass,
  };
}

function hasFailure(result) {
  if (!result.webgpuAvailable || !result.adapterAvailable) return true;
  if (!result.smoke.computeIncrement.pass) return true;
  if (!result.smoke.renderTriangle.pass) return true;
  return false;
}

async function main() {
  const args = parseArgs(process.argv);
  const chromium = await loadChromiumDriver();
  const { server, url, port } = await startLocalServer();

  const modes = args.mode === "both" ? ["dawn", "doe"] : [args.mode];
  const modeResults = [];
  let failed = false;

  try {
    for (const mode of modes) {
      const result = await runMode(chromium, mode, args, url, port);
      modeResults.push(result);
      const status = hasFailure(result) ? "FAIL" : "PASS";
      console.log(
        `[${status}] ${mode}: webgpu=${result.webgpuAvailable} adapter=${result.adapterAvailable} compute=${result.smoke.computeIncrement.pass} render=${result.smoke.renderTriangle.pass} upload64kb_us=${result.benches.writeBuffer64kbUsPerOp?.toFixed(3) ?? "n/a"} dispatch_us=${result.benches.computeDispatchUsPerOp?.toFixed(3) ?? "n/a"}`,
      );
      if (hasFailure(result)) {
        failed = true;
      }
    }
  } finally {
    server.close();
  }

  const modeResultsWithHashes = attachHashChain(modeResults);
  const generatedAt = new Date().toISOString();
  const report = {
    schemaVersion: REPORT_SCHEMA_VERSION,
    reportKind: REPORT_KIND,
    benchmarkClass: BENCHMARK_CLASS,
    comparisonStatus: "diagnostic",
    claimStatus: "diagnostic",
    timingClass: TIMING_CLASS,
    timingSource: TIMING_SOURCE,
    generatedAt,
    hashAlgorithm: HASH_ALGORITHM,
    invocation: {
      argv: process.argv.slice(2),
      cwd: process.cwd(),
      nodeVersion: process.version,
      platform: process.platform,
      arch: process.arch,
    },
    chromePath: args.chromePath,
    headless: args.headless,
    chromeArgs: args.chromeArgs,
    mode: args.mode,
    methodology: {
      uploadIterations: args.uploadIters,
      dispatchIterations: args.dispatchIters,
      uploadWarmupIterations: UPLOAD_WARMUP_ITERS,
      dispatchWarmupIterations: DISPATCH_WARMUP_ITERS,
      suiteTimeoutMs: args.suiteTimeoutMs,
      operationTimeoutMs: args.opTimeoutMs,
      strictMode: args.strict,
      notes: [
        "Browser harness output is diagnostic and not a strict L0 apples-to-apples claim artifact.",
      ],
    },
    modeResults: modeResultsWithHashes,
    comparison: computeComparison(modeResultsWithHashes),
  };
  report.reportHash = hashHex(report);

  mkdirSync(dirname(args.outPath), { recursive: true });
  writeFileSync(args.outPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  console.log(`report written: ${args.outPath}`);
  if (report.comparison) {
    console.log(
      `delta (diagnostic only; positive=doe faster): writeBuffer64kb=${report.comparison.writeBuffer64kbDeltaPercent?.toFixed(2) ?? "n/a"}% dispatch=${report.comparison.computeDispatchDeltaPercent?.toFixed(2) ?? "n/a"}%`,
    );
  }

  if (args.strict && failed) {
    process.exit(1);
  }
}

main().catch((error) => {
  console.error(String(error?.stack ?? error));
  process.exit(1);
});

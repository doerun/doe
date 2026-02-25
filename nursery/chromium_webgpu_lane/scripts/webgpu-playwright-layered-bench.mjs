#!/usr/bin/env node
import { createHash } from "node:crypto";
import http from "node:http";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(SCRIPT_DIR, "..", "..", "..");
const DEFAULT_CHROME = resolve(
  ROOT,
  "nursery/chromium_webgpu_lane/src/out/fawn_release/chrome",
);
const DEFAULT_DOE_LIB = resolve(ROOT, "zig/zig-out/lib/libdoe_webgpu.so");
const DEFAULT_MANIFEST = resolve(
  ROOT,
  "nursery/chromium_webgpu_lane/bench/generated/browser_projection_manifest.json",
);
const DEFAULT_WORKFLOWS = resolve(
  ROOT,
  "nursery/chromium_webgpu_lane/bench/workflows/browser-workflow-manifest.json",
);
const BENCH_OUT_ROOT = resolve(ROOT, "bench/out");
const BENCH_OUT_SCRATCH_ROOT = resolve(ROOT, "bench/out/scratch");
const ARTIFACTS_ROOT = resolve(ROOT, "nursery/chromium_webgpu_lane/artifacts");
const DEFAULT_OUT_FILE = "dawn-vs-doe.tracka.browser-layered.diagnostic.json";
const HASH_ALGORITHM = "sha256";

const DEFAULT_ITERATIONS = {
  upload: 300,
  dispatch: 200,
  render: 120,
  pipeline: 20,
  asyncPipeline: 10,
  workflow: 80,
};

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
  node nursery/chromium_webgpu_lane/scripts/webgpu-playwright-layered-bench.mjs [options]

Options:
  --mode dawn|doe|both      Runtime mode to run (default: both)
  --chrome PATH             Chrome binary path
  --doe-lib PATH            libdoe_webgpu.so path (for doe mode)
  --manifest PATH           Projection manifest JSON path
  --workflows PATH          Browser workflow manifest JSON path
  --out PATH                Output report JSON path (default: nursery/chromium_webgpu_lane/artifacts/<timestamp>/${DEFAULT_OUT_FILE})
  --allow-bench-out         Allow writing this diagnostic report under bench/out/scratch
  --allow-data-url-fallback Allow data: URL fallback if local server bind fails
  --headless true|false     Launch headless (default: true)
  --chrome-arg ARG          Extra Chromium arg (repeatable)
  --iters-upload N          Upload scenario iterations (default: 300)
  --iters-dispatch N        Dispatch scenario iterations (default: 200)
  --iters-render N          Render scenario iterations (default: 120)
  --iters-pipeline N        Pipeline scenario iterations (default: 20)
  --iters-async-pipeline N  Async pipeline iterations (default: 10)
  --iters-workflow N        Workflow loop iterations (default: 80)
  --strict                  Exit non-zero when required rows fail
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
      `refusing to write diagnostic browser layered output to ${BENCH_OUT_ROOT}; write under nursery/chromium_webgpu_lane/artifacts or pass --allow-bench-out explicitly`,
    );
  }
  if (!pathWithin(outPath, BENCH_OUT_SCRATCH_ROOT)) {
    throw new Error(
      `diagnostic browser layered output under bench/out must be in ${BENCH_OUT_SCRATCH_ROOT}`,
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

function attachHashChain(entries, moduleName) {
  let previousHash = "0".repeat(64);
  return entries.map((entry, index) => {
    const traceEntry = {
      module: moduleName,
      opCode: "mode_result",
      seq: index + 1,
      ...entry,
    };
    const hash = hashHex({
      previousHash,
      entry: traceEntry,
    });
    const withHash = {
      ...traceEntry,
      hash,
      previousHash,
    };
    previousHash = hash;
    return withHash;
  });
}

function parseArgs(argv) {
  const args = {
    mode: "both",
    chromePath: DEFAULT_CHROME,
    doeLibPath: DEFAULT_DOE_LIB,
    manifestPath: DEFAULT_MANIFEST,
    workflowsPath: DEFAULT_WORKFLOWS,
    outPath: defaultOutPath(),
    allowBenchOut: false,
    allowDataUrlFallback: false,
    headless: true,
    chromeArgs: [],
    strict: false,
    iterations: { ...DEFAULT_ITERATIONS },
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
    } else if (token === "--allow-data-url-fallback") {
      args.allowDataUrlFallback = true;
    } else if (token === "--mode") {
      args.mode = readOptionValue(argv, i, "--mode");
      i += 1;
    } else if (token === "--chrome") {
      args.chromePath = readOptionValue(argv, i, "--chrome");
      i += 1;
    } else if (token === "--doe-lib") {
      args.doeLibPath = readOptionValue(argv, i, "--doe-lib");
      i += 1;
    } else if (token === "--manifest") {
      args.manifestPath = readOptionValue(argv, i, "--manifest");
      i += 1;
    } else if (token === "--workflows") {
      args.workflowsPath = readOptionValue(argv, i, "--workflows");
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
    } else if (token === "--iters-upload") {
      args.iterations.upload = parsePositiveInt(
        readOptionValue(argv, i, "--iters-upload"),
        "--iters-upload",
      );
      i += 1;
    } else if (token === "--iters-dispatch") {
      args.iterations.dispatch = parsePositiveInt(
        readOptionValue(argv, i, "--iters-dispatch"),
        "--iters-dispatch",
      );
      i += 1;
    } else if (token === "--iters-render") {
      args.iterations.render = parsePositiveInt(
        readOptionValue(argv, i, "--iters-render"),
        "--iters-render",
      );
      i += 1;
    } else if (token === "--iters-pipeline") {
      args.iterations.pipeline = parsePositiveInt(
        readOptionValue(argv, i, "--iters-pipeline"),
        "--iters-pipeline",
      );
      i += 1;
    } else if (token === "--iters-async-pipeline") {
      args.iterations.asyncPipeline = parsePositiveInt(
        readOptionValue(argv, i, "--iters-async-pipeline"),
        "--iters-async-pipeline",
      );
      i += 1;
    } else if (token === "--iters-workflow") {
      args.iterations.workflow = parsePositiveInt(
        readOptionValue(argv, i, "--iters-workflow"),
        "--iters-workflow",
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
  return args;
}

function loadJsonObject(path) {
  const payload = JSON.parse(readFileSync(path, "utf8"));
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(`invalid JSON object: ${path}`);
  }
  return payload;
}

function requireString(value, label) {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new Error(`missing non-empty string: ${label}`);
  }
  return value;
}

function requireHashHex(value, label) {
  const text = requireString(value, label);
  if (!/^[a-f0-9]{64}$/.test(text)) {
    throw new Error(`invalid sha256 hex for ${label}`);
  }
  return text;
}

function loadProjectionManifest(path) {
  const payload = loadJsonObject(path);
  if (payload.schemaVersion !== 2) {
    throw new Error(`invalid projection manifest schemaVersion, expected 2: ${path}`);
  }
  if (!Array.isArray(payload.rows) || payload.rows.length === 0) {
    throw new Error(`invalid projection manifest: ${path}`);
  }
  const metadata = {
    sourceWorkloadsPath: requireString(payload.sourceWorkloadsPath, "sourceWorkloadsPath"),
    sourceWorkloadsSha256: requireHashHex(payload.sourceWorkloadsSha256, "sourceWorkloadsSha256"),
    rulesPath: requireString(payload.rulesPath, "rulesPath"),
    rulesSha256: requireHashHex(payload.rulesSha256, "rulesSha256"),
    projectionContractHash: requireHashHex(
      payload.projectionContractHash,
      "projectionContractHash",
    ),
    generatedAt: requireString(payload.generatedAt, "generatedAt"),
  };

  const rows = payload.rows.map((row, index) => {
    if (!row || typeof row !== "object" || Array.isArray(row)) {
      throw new Error(`invalid projection row at index ${index}`);
    }
    const projectionClass = requireString(row.projectionClass, `rows[${index}].projectionClass`);
    const requiredStatus = requireString(row.requiredStatus, `rows[${index}].requiredStatus`);
    const comparabilityExpectation = requireString(
      row.comparabilityExpectation,
      `rows[${index}].comparabilityExpectation`,
    );
    const claimScope = requireString(row.claimScope, `rows[${index}].claimScope`);
    if ((projectionClass === "high" || projectionClass === "medium") && requiredStatus !== "ok") {
      throw new Error(`projection row ${index} high/medium must use requiredStatus=ok`);
    }
    if (projectionClass === "non_projectable" && requiredStatus !== "not_applicable") {
      throw new Error(`projection row ${index} non_projectable must use requiredStatus=not_applicable`);
    }
    if (comparabilityExpectation === "strict" && claimScope !== "l1_strict_candidate") {
      throw new Error(`projection row ${index} strict comparability requires l1_strict_candidate`);
    }
    if (comparabilityExpectation === "component" && claimScope !== "l1_component_only") {
      throw new Error(`projection row ${index} component comparability requires l1_component_only`);
    }
    if (comparabilityExpectation === "none" && claimScope !== "l0_only_no_claim") {
      throw new Error(`projection row ${index} none comparability requires l0_only_no_claim`);
    }
    return {
      sourceWorkloadId: requireString(row.sourceWorkloadId, `rows[${index}].sourceWorkloadId`),
      sourceWorkloadName: requireString(
        row.sourceWorkloadName,
        `rows[${index}].sourceWorkloadName`,
      ),
      domain: requireString(row.domain, `rows[${index}].domain`),
      projectionClass,
      layerTarget: requireString(row.layerTarget, `rows[${index}].layerTarget`),
      scenarioTemplate: requireString(
        row.scenarioTemplate,
        `rows[${index}].scenarioTemplate`,
      ),
      comparabilityExpectation,
      requiredStatus,
      claimScope,
      claimLanguage: requireString(row.claimLanguage, `rows[${index}].claimLanguage`),
      projectionNote: requireString(row.projectionNote, `rows[${index}].projectionNote`),
      runtimes: {},
    };
  });
  return { metadata, rows };
}

function loadWorkflowManifest(path) {
  const payload = loadJsonObject(path);
  if (payload.schemaVersion !== 2) {
    throw new Error(`invalid workflow manifest schemaVersion, expected 2: ${path}`);
  }
  if (!Array.isArray(payload.rows) || payload.rows.length === 0) {
    throw new Error(`invalid workflow manifest: ${path}`);
  }
  const promotionGateRequiredApprovals = Array.isArray(payload.promotionGateRequiredApprovals)
    ? payload.promotionGateRequiredApprovals.map((value, index) =>
        requireString(value, `promotionGateRequiredApprovals[${index}]`),
      )
    : null;
  if (!promotionGateRequiredApprovals || promotionGateRequiredApprovals.length === 0) {
    throw new Error("workflow manifest missing promotionGateRequiredApprovals[]");
  }

  const rows = payload.rows.map((row, index) => {
    if (!row || typeof row !== "object" || Array.isArray(row)) {
      throw new Error(`invalid workflow row at index ${index}`);
    }
    if (!Array.isArray(row.metrics)) {
      throw new Error(`workflow row must include metrics[] at index ${index}`);
    }
    const required = Boolean(row.required);
    const requiredStatus = requireString(row.requiredStatus, `rows[${index}].requiredStatus`);
    if (required && requiredStatus !== "ok") {
      throw new Error(`workflow row required=true must use requiredStatus=ok at index ${index}`);
    }
    if (!required && requiredStatus !== "optional") {
      throw new Error(
        `workflow row required=false must use requiredStatus=optional at index ${index}`,
      );
    }
    return {
      id: requireString(row.id, `rows[${index}].id`),
      scenarioTemplate: requireString(
        row.scenarioTemplate,
        `rows[${index}].scenarioTemplate`,
      ),
      description: requireString(row.description, `rows[${index}].description`),
      metrics: row.metrics,
      comparabilityExpectation: requireString(
        row.comparabilityExpectation,
        `rows[${index}].comparabilityExpectation`,
      ),
      requiredStatus,
      claimScope: requireString(row.claimScope, `rows[${index}].claimScope`),
      claimLanguage: requireString(row.claimLanguage, `rows[${index}].claimLanguage`),
      required,
      runtimes: {},
    };
  });
  return { promotionGateRequiredApprovals, rows };
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
    "Playwright not found. Install with: npm install --prefix nursery/chromium_webgpu_lane playwright-core",
  );
}

function startLocalServer() {
  const html =
    "<!doctype html><meta charset='utf-8'><title>doe-webgpu-layered-bench</title>";
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

function makeDataPageUrl() {
  const html =
    "<!doctype html><meta charset='utf-8'><title>doe-webgpu-layered-bench</title>";
  return `data:text/html;charset=utf-8,${encodeURIComponent(html)}`;
}

async function resolvePageTarget(allowDataUrlFallback) {
  try {
    const { server, url, port } = await startLocalServer();
    return {
      kind: "server",
      server,
      url,
      port,
      warning: null,
    };
  } catch (error) {
    if (!allowDataUrlFallback) {
      return {
        kind: "unavailable",
        server: null,
        url: "",
        port: null,
        warning: `local server bind failed (no fallback by default): ${String(error)}`,
      };
    }
    return {
      kind: "data",
      server: null,
      url: makeDataPageUrl(),
      port: null,
      warning: `local server unavailable, using data URL fallback: ${String(error)}`,
    };
  }
}

function baseLaunchArgs(port) {
  const args = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-crash-reporter",
    "--disable-crashpad-for-testing",
    "--ignore-gpu-blocklist",
    "--enable-unsafe-webgpu",
  ];
  if (Number.isInteger(port)) {
    args.push(`--unsafely-treat-insecure-origin-as-secure=http://127.0.0.1:${port}`);
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

async function probeRuntime(page) {
  return page.evaluate(async () => {
    const response = {
      webgpuAvailable: typeof navigator.gpu !== "undefined",
      adapterAvailable: false,
      adapterInfo: null,
      featureCount: 0,
      errors: [],
    };

    if (!response.webgpuAvailable) {
      response.errors.push("navigator.gpu unavailable");
      return response;
    }

    try {
      const adapter = await navigator.gpu.requestAdapter();
      if (!adapter) {
        response.errors.push("requestAdapter returned null");
        return response;
      }
      response.adapterAvailable = true;
      response.featureCount = Array.from(adapter.features).length;
      if ("info" in adapter) {
        response.adapterInfo = adapter.info;
      }
    } catch (error) {
      response.errors.push(String(error));
    }

    return response;
  });
}

async function runScenario(page, template, iterations) {
  return page.evaluate(
    async ({ scenarioTemplate, runIterations }) => {
      const result = {
        status: "fail",
        statusCode: "scenario_runtime_error",
        error: null,
        metrics: {},
      };

      const nowMs = () => performance.now();

      async function initDevice() {
        if (typeof navigator.gpu === "undefined") {
          throw new Error("navigator.gpu unavailable");
        }
        const adapter = await navigator.gpu.requestAdapter();
        if (!adapter) {
          throw new Error("requestAdapter returned null");
        }
        const device = await adapter.requestDevice();
        return { adapter, device };
      }

      async function runWriteBuffer(device) {
        const iterations = runIterations.upload;
        const size = 64 * 1024;
        const payload = new Uint8Array(size);
        const buffer = device.createBuffer({
          size,
          usage: GPUBufferUsage.COPY_DST,
        });
        for (let i = 0; i < 20; i += 1) {
          device.queue.writeBuffer(buffer, 0, payload);
        }
        await device.queue.onSubmittedWorkDone();
        const t0 = nowMs();
        for (let i = 0; i < iterations; i += 1) {
          device.queue.writeBuffer(buffer, 0, payload);
        }
        await device.queue.onSubmittedWorkDone();
        const t1 = nowMs();
        result.metrics.iterations = iterations;
        result.metrics.usPerOp = ((t1 - t0) * 1000) / iterations;
      }

      async function runComputeDispatch(device, dispatchIters) {
        const shader = device.createShaderModule({
          code: `
            @compute @workgroup_size(1)
            fn main() {}
          `,
        });
        const pipeline = device.createComputePipeline({
          layout: "auto",
          compute: { module: shader, entryPoint: "main" },
        });
        for (let i = 0; i < 20; i += 1) {
          const encoder = device.createCommandEncoder();
          const pass = encoder.beginComputePass();
          pass.setPipeline(pipeline);
          pass.dispatchWorkgroups(1);
          pass.end();
          device.queue.submit([encoder.finish()]);
        }
        await device.queue.onSubmittedWorkDone();
        const t0 = nowMs();
        for (let i = 0; i < dispatchIters; i += 1) {
          const encoder = device.createCommandEncoder();
          const pass = encoder.beginComputePass();
          pass.setPipeline(pipeline);
          pass.dispatchWorkgroups(1);
          pass.end();
          device.queue.submit([encoder.finish()]);
        }
        await device.queue.onSubmittedWorkDone();
        const t1 = nowMs();
        result.metrics.iterations = dispatchIters;
        result.metrics.usPerOp = ((t1 - t0) * 1000) / dispatchIters;
      }

      async function runRenderTriangleReadback(device) {
        const width = 64;
        const height = 64;
        const canvas = new OffscreenCanvas(width, height);
        const context = canvas.getContext("webgpu");
        if (!context) {
          throw new Error("OffscreenCanvas.getContext('webgpu') returned null");
        }
        const format = navigator.gpu.getPreferredCanvasFormat();
        context.configure({ device, format, alphaMode: "opaque" });

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
          fragment: { module: shader, entryPoint: "fs", targets: [{ format }] },
          primitive: { topology: "triangle-list" },
        });

        const texture = context.getCurrentTexture();
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
        await readback.mapAsync(GPUMapMode.READ);
        const data = new Uint8Array(readback.getMappedRange());
        const centerOffset = Math.floor(height / 2) * bytesPerRow + Math.floor(width / 2) * 4;
        const centerRgba = Array.from(data.slice(centerOffset, centerOffset + 4));
        readback.unmap();
        result.metrics.centerRgba = centerRgba;
        result.metrics.pass =
          centerRgba[0] > 100 &&
          centerRgba[0] > centerRgba[1] + 20 &&
          centerRgba[0] > centerRgba[2] + 20;
        if (!result.metrics.pass) {
          throw new Error("unexpected render readback color");
        }
      }

      async function runRenderBundleReplay(device) {
        const iterations = runIterations.render;
        const width = 64;
        const height = 64;
        const canvas = new OffscreenCanvas(width, height);
        const context = canvas.getContext("webgpu");
        if (!context) {
          throw new Error("OffscreenCanvas.getContext('webgpu') returned null");
        }
        const format = navigator.gpu.getPreferredCanvasFormat();
        context.configure({ device, format, alphaMode: "opaque" });

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
              return vec4<f32>(0.0, 0.8, 0.0, 1.0);
            }
          `,
        });

        const pipeline = device.createRenderPipeline({
          layout: "auto",
          vertex: { module: shader, entryPoint: "vs" },
          fragment: { module: shader, entryPoint: "fs", targets: [{ format }] },
          primitive: { topology: "triangle-list" },
        });

        const bundleEncoder = device.createRenderBundleEncoder({
          colorFormats: [format],
        });
        bundleEncoder.setPipeline(pipeline);
        bundleEncoder.draw(3);
        const bundle = bundleEncoder.finish();

        for (let i = 0; i < 10; i += 1) {
          const encoder = device.createCommandEncoder();
          const pass = encoder.beginRenderPass({
            colorAttachments: [
              {
                view: context.getCurrentTexture().createView(),
                clearValue: { r: 0, g: 0, b: 0, a: 1 },
                loadOp: "clear",
                storeOp: "store",
              },
            ],
          });
          pass.executeBundles([bundle]);
          pass.end();
          device.queue.submit([encoder.finish()]);
        }
        await device.queue.onSubmittedWorkDone();

        const t0 = nowMs();
        for (let i = 0; i < iterations; i += 1) {
          const encoder = device.createCommandEncoder();
          const pass = encoder.beginRenderPass({
            colorAttachments: [
              {
                view: context.getCurrentTexture().createView(),
                clearValue: { r: 0, g: 0, b: 0, a: 1 },
                loadOp: "clear",
                storeOp: "store",
              },
            ],
          });
          pass.executeBundles([bundle]);
          pass.end();
          device.queue.submit([encoder.finish()]);
        }
        await device.queue.onSubmittedWorkDone();
        const t1 = nowMs();
        result.metrics.iterations = iterations;
        result.metrics.usPerOp = ((t1 - t0) * 1000) / iterations;
      }

      async function runTextureSampleRaster(device) {
        const width = 4;
        const height = 4;
        const texture = device.createTexture({
          size: { width, height, depthOrArrayLayers: 1 },
          format: "rgba8unorm",
          usage:
            GPUTextureUsage.TEXTURE_BINDING |
            GPUTextureUsage.COPY_DST |
            GPUTextureUsage.RENDER_ATTACHMENT,
        });
        const data = new Uint8Array(width * height * 4);
        for (let i = 0; i < data.length; i += 4) {
          data[i] = 255;
          data[i + 3] = 255;
        }
        device.queue.writeTexture(
          { texture },
          data,
          { bytesPerRow: width * 4, rowsPerImage: height },
          { width, height, depthOrArrayLayers: 1 },
        );

        const canvas = new OffscreenCanvas(64, 64);
        const context = canvas.getContext("webgpu");
        if (!context) {
          throw new Error("OffscreenCanvas.getContext('webgpu') returned null");
        }
        const format = navigator.gpu.getPreferredCanvasFormat();
        context.configure({ device, format, alphaMode: "opaque" });

        const shader = device.createShaderModule({
          code: `
            struct VsOut {
              @builtin(position) pos: vec4<f32>,
              @location(0) uv: vec2<f32>,
            };

            @vertex
            fn vs(@builtin(vertex_index) index : u32) -> VsOut {
              var pos = array<vec2<f32>, 3>(
                vec2<f32>(-1.0, -1.0),
                vec2<f32>( 3.0, -1.0),
                vec2<f32>(-1.0,  3.0)
              );
              var uv = array<vec2<f32>, 3>(
                vec2<f32>(0.0, 0.0),
                vec2<f32>(2.0, 0.0),
                vec2<f32>(0.0, 2.0)
              );
              var out: VsOut;
              out.pos = vec4<f32>(pos[index], 0.0, 1.0);
              out.uv = uv[index];
              return out;
            }

            @group(0) @binding(0) var tex: texture_2d<f32>;
            @group(0) @binding(1) var samp: sampler;

            @fragment
            fn fs(in: VsOut) -> @location(0) vec4<f32> {
              return textureSample(tex, samp, in.uv * 0.5);
            }
          `,
        });

        const pipeline = device.createRenderPipeline({
          layout: "auto",
          vertex: { module: shader, entryPoint: "vs" },
          fragment: { module: shader, entryPoint: "fs", targets: [{ format }] },
          primitive: { topology: "triangle-list" },
        });

        const bindGroup = device.createBindGroup({
          layout: pipeline.getBindGroupLayout(0),
          entries: [
            { binding: 0, resource: texture.createView() },
            { binding: 1, resource: device.createSampler({ magFilter: "nearest", minFilter: "nearest" }) },
          ],
        });

        const outTexture = context.getCurrentTexture();
        const encoder = device.createCommandEncoder();
        const pass = encoder.beginRenderPass({
          colorAttachments: [
            {
              view: outTexture.createView(),
              clearValue: { r: 0, g: 0, b: 0, a: 1 },
              loadOp: "clear",
              storeOp: "store",
            },
          ],
        });
        pass.setPipeline(pipeline);
        pass.setBindGroup(0, bindGroup);
        pass.draw(3);
        pass.end();

        const bytesPerRow = 256;
        const readback = device.createBuffer({
          size: bytesPerRow * 64,
          usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ,
        });
        encoder.copyTextureToBuffer(
          { texture: outTexture },
          { buffer: readback, bytesPerRow, rowsPerImage: 64 },
          { width: 64, height: 64, depthOrArrayLayers: 1 },
        );
        device.queue.submit([encoder.finish()]);
        await readback.mapAsync(GPUMapMode.READ);
        const mapped = new Uint8Array(readback.getMappedRange());
        const offset = 32 * bytesPerRow + 32 * 4;
        const center = Array.from(mapped.slice(offset, offset + 4));
        readback.unmap();
        result.metrics.centerRgba = center;
        result.metrics.pass = center[0] > 100;
        if (!result.metrics.pass) {
          throw new Error("texture sample raster check failed");
        }
      }

      async function runTextureWriteQueryDestroy(device) {
        const texture = device.createTexture({
          size: { width: 128, height: 128, depthOrArrayLayers: 1 },
          format: "rgba8unorm",
          usage:
            GPUTextureUsage.TEXTURE_BINDING |
            GPUTextureUsage.COPY_DST |
            GPUTextureUsage.RENDER_ATTACHMENT,
          mipLevelCount: 1,
          sampleCount: 1,
        });

        const payload = new Uint8Array(128 * 128 * 4);
        payload.fill(17);
        device.queue.writeTexture(
          { texture },
          payload,
          { bytesPerRow: 128 * 4, rowsPerImage: 128 },
          { width: 128, height: 128, depthOrArrayLayers: 1 },
        );
        await device.queue.onSubmittedWorkDone();

        const view = texture.createView();
        result.metrics.width = texture.width;
        result.metrics.height = texture.height;
        result.metrics.depthOrArrayLayers = texture.depthOrArrayLayers;
        result.metrics.mipLevelCount = texture.mipLevelCount;
        result.metrics.sampleCount = texture.sampleCount;
        result.metrics.dimension = texture.dimension;
        result.metrics.format = texture.format;
        result.metrics.usage = texture.usage;
        result.metrics.viewCreated = Boolean(view);

        texture.destroy();
        result.metrics.destroyed = true;
      }

      async function runPipelineCompileStress(device, useAsync) {
        const iterations = useAsync ? runIterations.asyncPipeline : runIterations.pipeline;
        const t0 = nowMs();
        for (let i = 0; i < iterations; i += 1) {
          const module = device.createShaderModule({
            code: `
              @compute @workgroup_size(1)
              fn main() {
                let marker : u32 = ${i}u;
                _ = marker;
              }
            `,
          });
          if (useAsync) {
            if (typeof device.createComputePipelineAsync !== "function") {
              throw new Error("createComputePipelineAsync is unavailable");
            }
            await device.createComputePipelineAsync({
              layout: "auto",
              compute: { module, entryPoint: "main" },
            });
          } else {
            device.createComputePipeline({
              layout: "auto",
              compute: { module, entryPoint: "main" },
            });
          }
        }
        const t1 = nowMs();
        result.metrics.iterations = iterations;
        result.metrics.msPerPipeline = (t1 - t0) / iterations;
      }

      async function runSurfacePresent(device) {
        const iterations = runIterations.render;
        const canvas = new OffscreenCanvas(128, 128);
        const context = canvas.getContext("webgpu");
        if (!context) {
          throw new Error("OffscreenCanvas.getContext('webgpu') returned null");
        }
        const format = navigator.gpu.getPreferredCanvasFormat();
        context.configure({ device, format, alphaMode: "opaque" });

        const t0 = nowMs();
        for (let i = 0; i < iterations; i += 1) {
          const encoder = device.createCommandEncoder();
          const pass = encoder.beginRenderPass({
            colorAttachments: [
              {
                view: context.getCurrentTexture().createView(),
                clearValue: { r: 0.2, g: 0.2, b: 0.2, a: 1 },
                loadOp: "clear",
                storeOp: "store",
              },
            ],
          });
          pass.end();
          device.queue.submit([encoder.finish()]);
        }
        await device.queue.onSubmittedWorkDone();
        const t1 = nowMs();
        result.metrics.iterations = iterations;
        result.metrics.usPerFrame = ((t1 - t0) * 1000) / iterations;
      }

      async function runCanvasReconfigureResize(device) {
        const sizes = [64, 96, 128, 160, 192, 256];
        const canvas = new OffscreenCanvas(sizes[0], sizes[0]);
        const context = canvas.getContext("webgpu");
        if (!context) {
          throw new Error("OffscreenCanvas.getContext('webgpu') returned null");
        }
        const format = navigator.gpu.getPreferredCanvasFormat();
        const t0 = nowMs();
        for (const size of sizes) {
          canvas.width = size;
          canvas.height = size;
          context.configure({ device, format, alphaMode: "opaque" });
          const encoder = device.createCommandEncoder();
          const pass = encoder.beginRenderPass({
            colorAttachments: [
              {
                view: context.getCurrentTexture().createView(),
                clearValue: { r: 0, g: 0, b: 0, a: 1 },
                loadOp: "clear",
                storeOp: "store",
              },
            ],
          });
          pass.end();
          device.queue.submit([encoder.finish()]);
        }
        await device.queue.onSubmittedWorkDone();
        const t1 = nowMs();
        result.metrics.resizeCount = sizes.length;
        result.metrics.totalMs = t1 - t0;
        result.metrics.msPerResize = result.metrics.totalMs / sizes.length;
      }

      async function runQueueSubmitBurst(device) {
        const iterations = runIterations.workflow;
        const module = device.createShaderModule({
          code: `
            @compute @workgroup_size(1)
            fn main() {}
          `,
        });
        const pipeline = device.createComputePipeline({
          layout: "auto",
          compute: { module, entryPoint: "main" },
        });

        const t0 = nowMs();
        for (let i = 0; i < iterations; i += 1) {
          const encoder = device.createCommandEncoder();
          const pass = encoder.beginComputePass();
          pass.setPipeline(pipeline);
          pass.dispatchWorkgroups(1);
          pass.end();
          device.queue.submit([encoder.finish()]);
        }
        await device.queue.onSubmittedWorkDone();
        const t1 = nowMs();
        result.metrics.submitCount = iterations;
        result.metrics.totalMs = t1 - t0;
        result.metrics.usPerSubmit = ((t1 - t0) * 1000) / iterations;
      }

      const scenarioStart = nowMs();
      try {
        const { device } = await initDevice();

        if (scenarioTemplate === "write_buffer_upload") {
          await runWriteBuffer(device);
        } else if (scenarioTemplate === "compute_dispatch_basic") {
          await runComputeDispatch(device, runIterations.dispatch);
        } else if (scenarioTemplate === "render_triangle_readback") {
          await runRenderTriangleReadback(device);
        } else if (scenarioTemplate === "render_bundle_replay") {
          await runRenderBundleReplay(device);
        } else if (scenarioTemplate === "texture_sample_raster") {
          await runTextureSampleRaster(device);
        } else if (scenarioTemplate === "texture_write_query_destroy") {
          await runTextureWriteQueryDestroy(device);
        } else if (scenarioTemplate === "pipeline_compile_stress") {
          await runPipelineCompileStress(device, false);
        } else if (scenarioTemplate === "async_pipeline_diagnostics") {
          await runPipelineCompileStress(device, true);
        } else if (scenarioTemplate === "surface_present_basic") {
          await runSurfacePresent(device);
        } else if (scenarioTemplate === "startup_adapter_device") {
          result.metrics.startupMs = nowMs() - scenarioStart;
          result.metrics.adapterAvailable = true;
        } else if (scenarioTemplate === "canvas_reconfigure_resize") {
          await runCanvasReconfigureResize(device);
        } else if (scenarioTemplate === "queue_submit_burst") {
          await runQueueSubmitBurst(device);
        } else if (scenarioTemplate === "async_pipeline_burst") {
          await runPipelineCompileStress(device, true);
        } else if (scenarioTemplate === "generic_webgpu_api") {
          await runComputeDispatch(device, Math.max(1, Math.floor(runIterations.dispatch / 4)));
        } else {
          result.status = "unsupported";
          result.statusCode = "scenario_template_unknown";
          result.error = `unknown scenario template: ${scenarioTemplate}`;
          result.metrics.elapsedMs = nowMs() - scenarioStart;
          return result;
        }

        result.status = "ok";
        result.statusCode = "ok";
      } catch (error) {
        const errorText = String(error);
        if (
          errorText.includes("navigator.gpu unavailable") ||
          errorText.includes("requestAdapter returned null") ||
          errorText.includes("createComputePipelineAsync is unavailable") ||
          errorText.includes("OffscreenCanvas.getContext('webgpu') returned null")
        ) {
          result.status = "unsupported";
          if (errorText.includes("requestAdapter returned null")) {
            result.statusCode = "adapter_null";
          } else if (errorText.includes("createComputePipelineAsync is unavailable")) {
            result.statusCode = "api_unsupported";
          } else {
            result.statusCode = "webgpu_unavailable";
          }
        } else {
          result.status = "fail";
          result.statusCode = "scenario_runtime_error";
        }
        result.error = errorText;
      }

      result.metrics.elapsedMs = nowMs() - scenarioStart;
      return result;
    },
    {
      scenarioTemplate: template,
      runIterations: iterations,
    },
  );
}

function makeModeRowResult(status, statusCode, error = null, metrics = {}) {
  return {
    status,
    statusCode,
    error,
    metrics,
    measuredAt: new Date().toISOString(),
  };
}

function classifyModeFailure(error, stage) {
  const message = String(error);
  const lower = message.toLowerCase();
  const isSandbox =
    lower.includes("operation not permitted") ||
    lower.includes("eperm") ||
    lower.includes("sandbox");
  const isLaunchSurface =
    lower.includes("missing x server") ||
    lower.includes("can't open display") ||
    lower.includes("$display") ||
    lower.includes("ozone_platform_x11");
  const isAdapterNull = lower.includes("requestadapter returned null");
  const isWebgpuUnavailable = lower.includes("navigator.gpu unavailable");

  if (isSandbox) {
    return {
      stage,
      status: "unsupported",
      statusCode: "sandbox_constraint",
      error: message,
    };
  }
  if (isLaunchSurface) {
    return {
      stage,
      status: "unsupported",
      statusCode: "launch_surface_unavailable",
      error: message,
    };
  }
  if (isAdapterNull) {
    return {
      stage,
      status: "unsupported",
      statusCode: "adapter_null",
      error: message,
    };
  }
  if (isWebgpuUnavailable) {
    return {
      stage,
      status: "unsupported",
      statusCode: "webgpu_unavailable",
      error: message,
    };
  }

  return {
    stage,
    status: "fail",
    statusCode: stage === "launch" ? "browser_launch_failed" : "mode_setup_failed",
    error: message,
  };
}

function applyModeWideFailure(l1Rows, l2Rows, rowResultsById, workflowResultsById, failure) {
  for (const row of l1Rows) {
    if (row.layerTarget === "l0_only") {
      rowResultsById.set(row.sourceWorkloadId, makeModeRowResult("l0_only", "l0_only"));
      continue;
    }
    rowResultsById.set(
      row.sourceWorkloadId,
      makeModeRowResult(failure.status, failure.statusCode, failure.error),
    );
  }
  for (const workflow of l2Rows) {
    workflowResultsById.set(
      workflow.id,
      makeModeRowResult(failure.status, failure.statusCode, failure.error),
    );
  }
}

async function runMode(chromium, mode, args, pageTarget, l1Rows, l2Rows) {
  const launchArgs = [
    ...baseLaunchArgs(pageTarget.port),
    ...args.chromeArgs,
    ...runtimeArgs(mode, args.doeLibPath),
  ];
  const startMs = Date.now();
  const rowResultsById = new Map();
  const workflowResultsById = new Map();
  const runtimeEvidence = {
    modeRequested: mode,
    pageTargetKind: pageTarget.kind,
    pageTargetPort: Number.isInteger(pageTarget.port) ? pageTarget.port : null,
    pageTargetWarning: pageTarget.warning ?? null,
    browserVersion: "",
    userAgent: "",
    failureStage: null,
    failureStatusCode: null,
  };
  let runtimeProbe = {
    webgpuAvailable: false,
    adapterAvailable: false,
    adapterInfo: null,
    featureCount: 0,
    errors: [],
  };
  let browser;

  try {
    browser = await chromium.launch({
      executablePath: args.chromePath,
      headless: args.headless,
      args: launchArgs,
      timeout: 120000,
    });
  } catch (error) {
    const failure = classifyModeFailure(error, "launch");
    runtimeEvidence.failureStage = failure.stage;
    runtimeEvidence.failureStatusCode = failure.statusCode;
    applyModeWideFailure(l1Rows, l2Rows, rowResultsById, workflowResultsById, failure);
    return {
      mode,
      launchArgs,
      elapsedMs: Date.now() - startMs,
      runtimeProbe,
      runtimeEvidence,
      modeFailure: failure,
      rowResultsById,
      workflowResultsById,
    };
  }

  try {
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto(pageTarget.url, { waitUntil: "load", timeout: 120000 });
    runtimeEvidence.browserVersion = browser.version();
    runtimeEvidence.userAgent = await page.evaluate(() => navigator.userAgent);
    runtimeProbe = await probeRuntime(page);

    for (const row of l1Rows) {
      if (row.layerTarget === "l0_only") {
        rowResultsById.set(row.sourceWorkloadId, makeModeRowResult("l0_only", "l0_only"));
        continue;
      }
      const scenarioResult = await runScenario(page, row.scenarioTemplate, args.iterations);
      rowResultsById.set(
        row.sourceWorkloadId,
        makeModeRowResult(
          scenarioResult.status,
          scenarioResult.statusCode,
          scenarioResult.error,
          scenarioResult.metrics,
        ),
      );
    }

    for (const workflow of l2Rows) {
      const scenarioResult = await runScenario(
        page,
        workflow.scenarioTemplate,
        args.iterations,
      );
      workflowResultsById.set(
        workflow.id,
        makeModeRowResult(
          scenarioResult.status,
          scenarioResult.statusCode,
          scenarioResult.error,
          scenarioResult.metrics,
        ),
      );
    }

    return {
      mode,
      launchArgs,
      elapsedMs: Date.now() - startMs,
      runtimeProbe,
      runtimeEvidence,
      modeFailure: null,
      rowResultsById,
      workflowResultsById,
    };
  } catch (error) {
    const failure = classifyModeFailure(error, "setup");
    runtimeEvidence.failureStage = failure.stage;
    runtimeEvidence.failureStatusCode = failure.statusCode;
    applyModeWideFailure(l1Rows, l2Rows, rowResultsById, workflowResultsById, failure);
    runtimeProbe.errors = [...runtimeProbe.errors, failure.error];
    return {
      mode,
      launchArgs,
      elapsedMs: Date.now() - startMs,
      runtimeProbe,
      runtimeEvidence,
      modeFailure: failure,
      rowResultsById,
      workflowResultsById,
    };
  } finally {
    await browser.close();
  }
}

function summarizeStatusForRows(rows, modes, kind) {
  const byMode = {};
  for (const mode of modes) {
    byMode[mode] = {
      ok: 0,
      fail: 0,
      unsupported: 0,
      l0_only: 0,
      missing: 0,
      requiredFailures: 0,
      kind,
    };
  }

  for (const row of rows) {
    for (const mode of modes) {
      const result = row.runtimes[mode];
      if (!result) {
        byMode[mode].missing += 1;
        continue;
      }
      const status = result.status;
      if (status === "ok") byMode[mode].ok += 1;
      else if (status === "fail") byMode[mode].fail += 1;
      else if (status === "unsupported") byMode[mode].unsupported += 1;
      else if (status === "l0_only") byMode[mode].l0_only += 1;
      else byMode[mode].missing += 1;

      const required =
        kind === "l1"
          ? row.requiredStatus === "ok"
          : row.requiredStatus === "ok";
      if (required && status !== "ok") {
        byMode[mode].requiredFailures += 1;
      }
    }
  }

  return byMode;
}

function mergeModeSummary(l1Summary, l2Summary, modes) {
  const perMode = {};
  for (const mode of modes) {
    perMode[mode] = {
      l1: l1Summary[mode],
      l2: l2Summary[mode],
      requiredFailures: l1Summary[mode].requiredFailures + l2Summary[mode].requiredFailures,
    };
  }
  let overallRequiredFailures = 0;
  for (const mode of modes) {
    overallRequiredFailures += perMode[mode].requiredFailures;
  }
  return { perMode, overallRequiredFailures };
}

function hasRequiredFailures(summary) {
  return summary.overallRequiredFailures > 0;
}

async function main() {
  const args = parseArgs(process.argv);
  const chromium = await loadChromiumDriver();

  const projectionManifest = loadProjectionManifest(args.manifestPath);
  const workflowManifest = loadWorkflowManifest(args.workflowsPath);
  const l1Rows = projectionManifest.rows;
  const l2Rows = workflowManifest.rows;

  const modes = args.mode === "both" ? ["dawn", "doe"] : [args.mode];
  const modeRunDetails = [];

  const pageTarget = await resolvePageTarget(args.allowDataUrlFallback);
  if (pageTarget.warning) {
    console.log(`[warn] ${pageTarget.warning}`);
  }
  try {
    for (const mode of modes) {
      if (pageTarget.kind === "unavailable") {
        const failure = {
          stage: "page_target",
          status: "unsupported",
          statusCode: "mode_execution_unavailable",
          error: pageTarget.warning ?? "page target unavailable",
        };
        for (const row of l1Rows) {
          if (row.layerTarget === "l0_only") {
            row.runtimes[mode] = makeModeRowResult("l0_only", "l0_only");
          } else {
            row.runtimes[mode] = makeModeRowResult(
              failure.status,
              failure.statusCode,
              failure.error,
            );
          }
        }
        for (const workflow of l2Rows) {
          workflow.runtimes[mode] = makeModeRowResult(
            failure.status,
            failure.statusCode,
            failure.error,
          );
        }
        modeRunDetails.push({
          mode,
          elapsedMs: 0,
          launchArgs: [],
          runtimeProbe: {
            webgpuAvailable: false,
            adapterAvailable: false,
            adapterInfo: null,
            featureCount: 0,
            errors: [failure.error],
          },
          runtimeEvidence: {
            modeRequested: mode,
            pageTargetKind: pageTarget.kind,
            pageTargetPort: null,
            pageTargetWarning: pageTarget.warning ?? null,
            browserVersion: "",
            userAgent: "",
            failureStage: failure.stage,
            failureStatusCode: failure.statusCode,
          },
          modeFailure: failure,
        });
        console.log(
          `[mode=${mode}] runtime.webgpu=false runtime.adapter=false requiredL1Failed=all requiredL2Failed=all`,
        );
        continue;
      }

      const modeRun = await runMode(
        chromium,
        mode,
        args,
        pageTarget,
        l1Rows,
        l2Rows,
      );
      modeRunDetails.push({
        mode: modeRun.mode,
        elapsedMs: modeRun.elapsedMs,
        launchArgs: modeRun.launchArgs,
        runtimeProbe: modeRun.runtimeProbe,
        runtimeEvidence: modeRun.runtimeEvidence,
        modeFailure: modeRun.modeFailure,
      });

      for (const row of l1Rows) {
        row.runtimes[mode] = modeRun.rowResultsById.get(row.sourceWorkloadId) ?? null;
      }
      for (const workflow of l2Rows) {
        workflow.runtimes[mode] = modeRun.workflowResultsById.get(workflow.id) ?? null;
      }

      const requiredL1Rows = l1Rows.filter((row) => row.requiredStatus === "ok");
      const requiredL1Failed = requiredL1Rows.filter((row) => {
        const status = row.runtimes[mode]?.status;
        return status !== "ok";
      }).length;
      const requiredL2Rows = l2Rows.filter((row) => row.requiredStatus === "ok");
      const requiredL2Failed = requiredL2Rows.filter((row) => {
        const status = row.runtimes[mode]?.status;
        return status !== "ok";
      }).length;
      console.log(
        `[mode=${mode}] runtime.webgpu=${modeRun.runtimeProbe.webgpuAvailable} runtime.adapter=${modeRun.runtimeProbe.adapterAvailable} requiredL1Failed=${requiredL1Failed} requiredL2Failed=${requiredL2Failed}`,
      );
    }
  } finally {
    if (pageTarget.server) {
      pageTarget.server.close();
    }
  }

  const l1Summary = summarizeStatusForRows(l1Rows, modes, "l1");
  const l2Summary = summarizeStatusForRows(l2Rows, modes, "l2");
  const mergedSummary = mergeModeSummary(l1Summary, l2Summary, modes);
  const modeRunDetailsWithHashes = attachHashChain(
    modeRunDetails,
    "nursery.chromium_webgpu_lane.browser_layered_bench",
  );

  const report = {
    schemaVersion: 2,
    reportKind: "browser-layered-diagnostic",
    benchmarkClass: "directional",
    comparisonStatus: "diagnostic",
    claimStatus: "diagnostic",
    timingClass: "scenario",
    timingSource: "browser-performance-now",
    generatedAt: new Date().toISOString(),
    outputPath: args.outPath,
    hashAlgorithm: HASH_ALGORITHM,
    projectionContractHash: projectionManifest.metadata.projectionContractHash,
    sourceWorkloadsPath: projectionManifest.metadata.sourceWorkloadsPath,
    sourceWorkloadsSha256: projectionManifest.metadata.sourceWorkloadsSha256,
    projectionRulesPath: projectionManifest.metadata.rulesPath,
    projectionRulesSha256: projectionManifest.metadata.rulesSha256,
    invocation: {
      argv: process.argv.slice(2),
      cwd: process.cwd(),
      nodeVersion: process.version,
      platform: process.platform,
      arch: process.arch,
    },
    chromePath: args.chromePath,
    doeLibPath: args.doeLibPath,
    mode: args.mode,
    modeOrder: modes,
    headless: args.headless,
    chromeArgs: args.chromeArgs,
    manifestPath: args.manifestPath,
    workflowsPath: args.workflowsPath,
    workflowPromotionGateRequiredApprovals: workflowManifest.promotionGateRequiredApprovals,
    browserEnvironmentEvidence: {
      pageTargetKind: pageTarget.kind,
      pageTargetPort: Number.isInteger(pageTarget.port) ? pageTarget.port : null,
      pageTargetWarning: pageTarget.warning ?? null,
      dataUrlFallbackEnabled: args.allowDataUrlFallback,
    },
    methodology: {
      scenarioIterations: args.iterations,
      strictMode: args.strict,
      requiredStatusPolicy: {
        l1: "requiredStatus=ok rows are required",
        l2: "requiredStatus=ok rows are required",
      },
      failureTaxonomy: {
        ok: ["ok"],
        unsupported: [
          "adapter_null",
          "api_unsupported",
          "launch_surface_unavailable",
          "mode_execution_unavailable",
          "runtime_mode_unavailable",
          "sandbox_constraint",
          "scenario_template_unknown",
          "webgpu_unavailable",
        ],
        fail: ["browser_launch_failed", "mode_setup_failed", "mode_execution_failed", "scenario_runtime_error"],
        l0_only: ["l0_only"],
      },
      notes: [
        "Nursery layered browser harness output is diagnostic and not a strict L0 claim artifact.",
        "Comparability and claim scope are carried from projection/workflow contracts and must not be widened.",
      ],
    },
    modeRunDetails: modeRunDetailsWithHashes,
    l1: {
      rowCount: l1Rows.length,
      rows: l1Rows,
    },
    l2: {
      workflowCount: l2Rows.length,
      rows: l2Rows,
    },
    summary: {
      l1: l1Summary,
      l2: l2Summary,
      ...mergedSummary,
    },
  };
  report.reportHash = hashHex(report);

  mkdirSync(dirname(args.outPath), { recursive: true });
  writeFileSync(args.outPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  console.log(`report written: ${args.outPath}`);
  console.log(`overall required failures: ${report.summary.overallRequiredFailures}`);

  if (args.strict && hasRequiredFailures(report.summary)) {
    process.exit(1);
  }
}

main().catch((error) => {
  console.error(String(error?.stack ?? error));
  process.exit(1);
});

const repoRoot = "../../";
const size = 1024;
const bytes = size * 4;
const tolerance = 1e-3;

const paths = {
  manifest: "runtime/zig/examples/execution-v1/gemma-4-e2b-smoke.json",
  graph: "bench/out/e2b-full-graph/gemma-4-e2b-stream-execution-plan.json",
  shaderSource: "bench/tools/doppler_webgpu_reference_export.cjs",
  initialRows: "bench/out/doppler-reference/inputs/input_seed1000_size1024.f32",
  layerInput: "bench/out/doppler-reference/inputs/input_seed2000_size1024.f32",
  storedCslTrace: "bench/out/doppler-reference/csl-L1-reference-trace.json",
  parityReceipt: "examples/doe-csl-reference-parity.gemma-4-e2b-layer-block-L1-webgpu.sample.json",
};

function speedVerdictPath(numLayers) {
  return `bench/out/doppler-reference/csl-emulator-speed-verdict-L${numLayers}.json`;
}

function accuracyVerdictPath(numLayers) {
  return `bench/out/doppler-reference/csl-emulator-accuracy-verdict-L${numLayers}.json`;
}

function allLanesSummaryPath(numLayers) {
  return `bench/out/doe-run/all-lanes-summary-L${numLayers}.json`;
}

const PER_LAYER_BASE = 2000; // matches CSL runner's default
const REQUIRED_CSL_STREAMS = [
  { streamId: "ple_rows_stream", role: "input" },
  { streamId: "ple_projection_stream", role: "input" },
  { streamId: "layer_weights_stream", role: "input" },
  { streamId: "activation_out_stream", role: "output" },
];

function perLayerInputPath(layerIndex) {
  return `bench/out/doppler-reference/inputs/input_seed${PER_LAYER_BASE + layerIndex}_size${size}.f32`;
}

function selectedNumLayers() {
  const v = el("num-layers-select")?.value;
  const n = parseInt(v || "1", 10);
  return Number.isFinite(n) && n > 0 ? n : 1;
}

let webgpuOutput = null;
let cslOutput = null;
let emulatorOutput = null;
let lastCslTracePath = null;
let lastCslNumLayers = null;

const el = (id) => document.getElementById(id);

function setPill(id, text, cls = "pending") {
  const node = el(id);
  node.textContent = text;
  node.className = `status-pill ${cls}`;
}

function preview(array) {
  if (!array) return "-";
  return Array.from(array.slice(0, 12))
    .map((x) => x.toFixed(7))
    .join("\n");
}

function formatMs(ms) {
  if (ms === undefined || ms === null || Number.isNaN(ms)) return "-";
  if (ms < 1000) return `${ms.toFixed(1)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

async function fetchText(path) {
  const response = await fetch(repoRoot + path);
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.text();
}

async function fetchJson(path) {
  const response = await fetch(repoRoot + path);
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

async function fetchF32(path) {
  const response = await fetch(repoRoot + path);
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return new Float32Array(await response.arrayBuffer());
}

async function sha256Hex(bytesLike) {
  const bytesView = bytesLike instanceof Uint8Array
    ? bytesLike
    : new Uint8Array(bytesLike.buffer, bytesLike.byteOffset, bytesLike.byteLength);
  const digest = await crypto.subtle.digest("SHA-256", bytesView);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function extractWgsl(source) {
  const marker = "const WGSL_LAYER_BLOCK = `";
  const start = source.indexOf(marker);
  if (start < 0) throw new Error("WGSL marker not found");
  const bodyStart = start + marker.length;
  const end = source.indexOf("`;", bodyStart);
  if (end < 0) throw new Error("WGSL terminator not found");
  return source.slice(bodyStart, end);
}

async function loadSourceHashes() {
  const [manifest, graph] = await Promise.all([
    fetchJson(paths.parityReceipt),
    fetchJson(paths.graph),
  ]);
  const source = manifest.sourceProgram || {};
  el("source-hashes").innerHTML = `
    <span>manifest: ${source.manifestSha256 || "unknown"}</span>
    <span>graph: ${source.graphSha256 || graph.streamGraphSha256 || "unknown"}</span>
  `;
}

function webGpuAdapterLabel(adapter) {
  const info = adapter.info || {};
  return [
    info.vendor,
    info.architecture,
    info.device,
    info.description,
  ].filter(Boolean).join(" · ") || "adapter granted";
}

async function checkServer() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const status = await response.json();
    setPill(
      "server-status",
      status.csPythonAvailable ? "server: CSL live ready" : "server: no cs_python",
      status.csPythonAvailable ? "pass" : "warn",
    );
  } catch {
    setPill("server-status", "server: static only", "warn");
  }
}

async function executeLayerBlockWebGpu() {
  if (!("gpu" in navigator)) {
    throw new Error("navigator.gpu is unavailable in this browser/origin");
  }
  const numLayers = selectedNumLayers();
  const adapter = await navigator.gpu.requestAdapter();
  if (!adapter) throw new Error("no WebGPU adapter returned");
  const device = await adapter.requestDevice();
  const adapterLabel = webGpuAdapterLabel(adapter);

  // Fetch shader + all per-layer inputs. For an N-layer chain we need
  // initial rows (seed 1000) plus N per-layer inputs (seeds 2000+l).
  // Each per-layer input file serves as both proj and wts for that
  // layer (same-seed fresh-rng semantic mirrors the CSL runner's
  // load_layer_data).
  const perLayerFetches = [];
  for (let l = 0; l < numLayers; l++) {
    perLayerFetches.push(fetchF32(perLayerInputPath(l)));
  }
  const [source, rows, ...perLayer] = await Promise.all([
    fetchText(paths.shaderSource),
    fetchF32(paths.initialRows),
    ...perLayerFetches,
  ]);
  if (rows.length !== size) {
    throw new Error(`initial_rows length ${rows.length} != size ${size}`);
  }
  for (let l = 0; l < numLayers; l++) {
    if (perLayer[l].length !== size) {
      throw new Error(`layer ${l} input length ${perLayer[l].length} != size ${size}`);
    }
  }
  const wgsl = extractWgsl(source);
  const usage = GPUBufferUsage;
  const rowsBuf = device.createBuffer({
    size: bytes,
    usage: usage.STORAGE | usage.COPY_DST | usage.COPY_SRC,
  });
  const projBuf = device.createBuffer({ size: bytes, usage: usage.STORAGE | usage.COPY_DST });
  const wtsBuf = device.createBuffer({ size: bytes, usage: usage.STORAGE | usage.COPY_DST });
  const outBuf = device.createBuffer({
    size: bytes,
    usage: usage.STORAGE | usage.COPY_SRC | usage.COPY_DST,
  });
  const readBuf = device.createBuffer({ size: bytes, usage: usage.COPY_DST | usage.MAP_READ });
  const paramsBuf = device.createBuffer({ size: 16, usage: usage.UNIFORM | usage.COPY_DST });

  const params = new ArrayBuffer(16);
  new Uint32Array(params, 0, 1)[0] = size;
  new Float32Array(params, 4, 1)[0] = 1e-6;
  device.queue.writeBuffer(paramsBuf, 0, params);
  device.queue.writeBuffer(rowsBuf, 0, rows);

  const module = device.createShaderModule({ code: wgsl });
  const pipeline = device.createComputePipeline({
    layout: "auto",
    compute: { module, entryPoint: "layer_block" },
  });
  const bindGroup = device.createBindGroup({
    layout: pipeline.getBindGroupLayout(0),
    entries: [
      { binding: 0, resource: { buffer: rowsBuf } },
      { binding: 1, resource: { buffer: projBuf } },
      { binding: 2, resource: { buffer: wtsBuf } },
      { binding: 3, resource: { buffer: outBuf } },
      { binding: 4, resource: { buffer: paramsBuf } },
    ],
  });

  const start = performance.now();
  // Chain N dispatches. Each layer l: write proj_l and wts_l (same
  // bytes — fresh-rng semantic), dispatch, copyBufferToBuffer(outBuf
  // -> rowsBuf) on the device so the next layer's rows are layer l's
  // activation_out. After the last layer, copy outBuf -> readBuf and
  // map back.
  for (let l = 0; l < numLayers; l++) {
    device.queue.writeBuffer(projBuf, 0, perLayer[l]);
    device.queue.writeBuffer(wtsBuf, 0, perLayer[l]);
    const encoder = device.createCommandEncoder();
    const pass = encoder.beginComputePass();
    pass.setPipeline(pipeline);
    pass.setBindGroup(0, bindGroup);
    pass.dispatchWorkgroups(1);
    pass.end();
    if (l + 1 < numLayers) {
      encoder.copyBufferToBuffer(outBuf, 0, rowsBuf, 0, bytes);
    } else {
      encoder.copyBufferToBuffer(outBuf, 0, readBuf, 0, bytes);
    }
    device.queue.submit([encoder.finish()]);
  }
  await readBuf.mapAsync(GPUMapMode.READ);
  const output = new Float32Array(readBuf.getMappedRange().slice(0));
  readBuf.unmap();
  await device.queue.onSubmittedWorkDone();
  const elapsed = performance.now() - start;
  return { output, elapsed, numLayers, sha: await sha256Hex(output), adapterLabel };
}

async function loadStoredCsl() {
  const trace = await fetchJson(paths.storedCslTrace);
  const outputInfo = ((trace.executedRun || {}).output || {});
  const outputPath = outputInfo.path;
  if (!outputPath) throw new Error("stored CSL trace has no output path");
  const output = await fetchF32(outputPath);
  return {
    output,
    sha: await sha256Hex(output),
    elapsed: (trace.executedRun || {}).elapsedMs,
    tracePath: paths.storedCslTrace,
    status: (trace.executedRun || {}).status || "unknown",
    source: "stored",
    numLayers: (trace.executedRun || {}).numLayersChained || 1,
  };
}

async function runLiveCsl() {
  const numLayers = selectedNumLayers();
  const response = await fetch(`/api/run-csl?num_layers=${numLayers}`, { method: "POST" });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  const payload = await response.json();
  if (!payload.output || !Array.isArray(payload.output)) {
    throw new Error("CSL API returned no output vector");
  }
  return {
    output: new Float32Array(payload.output),
    sha: payload.outputSha256,
    elapsed: payload.elapsedMs,
    tracePath: payload.tracePath,
    status: payload.status,
    source: "live",
    numLayers: payload.numLayersChained || payload.numLayersRequested || numLayers,
    streamTelemetry: payload.streamTelemetry || [],
  };
}

function liveCslTracePath(numLayers) {
  return `bench/out/scratch/gemma4-e2b-csl-sim/csl-L${numLayers}-live-trace.json`;
}

function uniqueStrings(values) {
  return Array.from(new Set(values.filter(Boolean)));
}

async function fetchFirstJson(candidates) {
  const errors = [];
  for (const path of uniqueStrings(candidates)) {
    try {
      return { path, trace: await fetchJson(path) };
    } catch (err) {
      errors.push(`${path}: ${err.message || err}`);
    }
  }
  throw new Error(`no CSL trace available for L=${selectedNumLayers()}\n${errors.join("\n")}`);
}

async function loadCslSemanticTrace(numLayers) {
  const candidates = [];
  if (lastCslTracePath && lastCslNumLayers === numLayers) {
    candidates.push(lastCslTracePath);
  }
  candidates.push(liveCslTracePath(numLayers));
  if (numLayers === 1) {
    candidates.push(paths.storedCslTrace);
  }
  return fetchFirstJson(candidates);
}

function extractHostIoLayout(trace) {
  return trace.hostIoLayout || ((trace.layerBlockSmoke || {}).hostIoLayout) || [];
}

function validateCslStreamSemantics(trace, numLayers) {
  const layout = extractHostIoLayout(trace);
  if (!Array.isArray(layout) || layout.length === 0) {
    throw new Error("CSL trace has no layerBlockSmoke.hostIoLayout");
  }
  const byId = new Map(layout.map((entry) => [entry.streamId, entry]));
  for (const required of REQUIRED_CSL_STREAMS) {
    const entry = byId.get(required.streamId);
    if (!entry) throw new Error(`CSL hostIoLayout missing ${required.streamId}`);
    if (entry.role !== required.role) {
      throw new Error(`${required.streamId} role ${entry.role} != ${required.role}`);
    }
    if (entry.dtype !== "float32") throw new Error(`${required.streamId} dtype ${entry.dtype} != float32`);
    if (entry.order !== "row_major") throw new Error(`${required.streamId} order ${entry.order} != row_major`);
    if (entry.tileBehavior !== "stream") {
      throw new Error(`${required.streamId} tileBehavior ${entry.tileBehavior} != stream`);
    }
    if (entry.elementsPerPe !== size) {
      throw new Error(`${required.streamId} elementsPerPe ${entry.elementsPerPe} != ${size}`);
    }
  }
  const smoke = trace.layerBlockSmoke || {};
  const counts = smoke.sendReceiveCounts || {};
  if (counts.sends !== 3 || counts.receives !== 1) {
    throw new Error(`CSL send/receive counts ${counts.sends}/${counts.receives} != 3/1`);
  }
  const executedLayers = (trace.executedRun || {}).numLayersChained;
  if (executedLayers !== undefined && executedLayers !== numLayers) {
    throw new Error(`CSL trace depth L=${executedLayers} does not match selected L=${numLayers}`);
  }
  return {
    layout,
    counts,
    ioBufferPolicy: smoke.ioBufferPolicy || null,
    ioBufferSizes: smoke.ioBufferSizes || null,
    kernelStage: smoke.kernelStage || "unknown",
  };
}

function summarizeCslSemantics(semantics, tracePath) {
  const streamText = semantics.layout
    .map((entry) => {
      const buffer = entry.ioBufferSize ? `/${entry.ioBufferSize}B` : "";
      return `${entry.streamId}:${entry.role}:${entry.elementsPerPe}${buffer}`;
    })
    .join(" · ");
  return `${tracePath}\n${streamText}\nsend/receive ${semantics.counts.sends}/${semantics.counts.receives}`;
}

async function runCslWebGpuEmulator() {
  const numLayers = selectedNumLayers();
  const traceInfo = await loadCslSemanticTrace(numLayers);
  const semantics = validateCslStreamSemantics(traceInfo.trace, numLayers);
  const result = await executeLayerBlockWebGpu();
  return {
    ...result,
    source: "webgpu_csl_semantic_emulator",
    tracePath: traceInfo.path,
    semantics,
    semanticSummary: summarizeCslSemantics(semantics, traceInfo.path),
  };
}

function diffStats(left, right) {
  const n = Math.min(left.length, right.length);
  let maxAbs = 0;
  let sumAbs = 0;
  for (let i = 0; i < n; i++) {
    const d = Math.abs(left[i] - right[i]);
    if (d > maxAbs) maxAbs = d;
    sumAbs += d;
  }
  return { maxAbs, meanAbs: sumAbs / n, n };
}

function compareOutputs() {
  const pairs = [];
  if (webgpuOutput && cslOutput) {
    pairs.push({ label: "WGSL/CSL", ...diffStats(webgpuOutput, cslOutput) });
  }
  if (emulatorOutput && cslOutput) {
    pairs.push({ label: "emu/CSL", ...diffStats(emulatorOutput, cslOutput) });
  }
  if (pairs.length === 0) {
    el("verdict").textContent = "waiting";
    el("max-diff").textContent = "-";
    drawPlot();
    refreshEvidenceStrip();
    return;
  }
  const pass = pairs.every((pair) => pair.maxAbs <= tolerance);
  el("verdict").textContent = pass ? "passed" : "failed";
  el("verdict").style.color = pass ? "var(--green)" : "var(--red)";
  el("max-diff").textContent = pairs
    .map((pair) => `${pair.label} ${pair.maxAbs.toExponential(3)} · mean ${pair.meanAbs.toExponential(3)}`)
    .join(" | ");
  drawPlot();
  refreshEvidenceStrip();
}

async function refreshEvidenceStrip() {
  const numLayers = selectedNumLayers();
  const speedEl = el("evidence-speedup");
  const accEl = el("evidence-accuracy");
  const idEl = el("evidence-identity");

  // Identity: from the speed verdict if present. Else leave as "-".
  let speedVerdict = null;
  try {
    speedVerdict = await fetchJson(speedVerdictPath(numLayers));
  } catch {
    speedVerdict = null;
  }
  if (speedVerdict) {
    const ident = speedVerdict.programIdentity || {};
    const both = ident.manifestMatched && ident.graphMatched;
    idEl.textContent = both
      ? `matched (manifest+graph, L=${speedVerdict.numLayers})`
      : `not confirmed (L=${speedVerdict.numLayers})`;
    idEl.style.color = both ? "var(--green)" : "var(--amber)";
    const ratio = speedVerdict.emulatorSpeedupOverLocalSimfabric;
    const emuMs = speedVerdict.emulatorElapsedMs;
    const cslMs = speedVerdict.cslSimfabricElapsedMs;
    if (typeof ratio === "number") {
      speedEl.textContent =
        `${ratio.toFixed(1)}x (${formatMs(emuMs)} vs ${formatMs(cslMs)})`;
      speedEl.style.color = ratio > 1.0 ? "var(--green)" : "var(--muted)";
    } else {
      speedEl.textContent = "-";
      speedEl.style.color = "";
    }
  } else {
    idEl.textContent = `no speed verdict for L=${numLayers}`;
    idEl.style.color = "var(--muted)";
    speedEl.textContent = "-";
    speedEl.style.color = "";
  }

  // Per-layer accuracy verdict: separate artifact.
  let accVerdict = null;
  try {
    accVerdict = await fetchJson(accuracyVerdictPath(numLayers));
  } catch {
    accVerdict = null;
  }
  if (accVerdict && accVerdict.summary) {
    const s = accVerdict.summary;
    const pass = s.allLayersWithinAtol;
    accEl.textContent = pass
      ? `all ${accVerdict.numLayers}L within ${accVerdict.atol} (max ${s.maxAbsErrAcrossLayers.toExponential(2)})`
      : `layer ${s.firstFailureLayer?.layer} exceeds ${accVerdict.atol}`;
    accEl.style.color = pass ? "var(--green)" : "var(--red)";
  } else {
    accEl.textContent = `no accuracy verdict for L=${numLayers}`;
    accEl.style.color = "var(--muted)";
  }
}

function drawPlot() {
  const canvas = el("plot");
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--code");
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue("--line");
  ctx.lineWidth = 1;
  for (let i = 1; i < 5; i++) {
    const y = (h * i) / 5;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }
  if (!webgpuOutput && !cslOutput && !emulatorOutput) {
    ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--muted");
    ctx.font = "15px sans-serif";
    ctx.fillText("Run a lane to draw output overlay.", 24, 42);
    el("sample-count").textContent = "0 samples";
    return;
  }
  const series = [webgpuOutput, cslOutput, emulatorOutput].filter(Boolean);
  const all = series.flatMap((arr) => Array.from(arr.slice(0, 256)));
  let min = Math.min(...all);
  let max = Math.max(...all);
  if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) {
    min = -1;
    max = 1;
  }
  const drawSeries = (arr, color) => {
    if (!arr) return;
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    const n = Math.min(256, arr.length);
    for (let i = 0; i < n; i++) {
      const x = (i / (n - 1)) * (w - 32) + 16;
      const y = h - 18 - ((arr[i] - min) / (max - min)) * (h - 36);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  };
  drawSeries(webgpuOutput, "#235789");
  drawSeries(cslOutput, "#16734a");
  drawSeries(emulatorOutput, "#9a6700");
  el("sample-count").textContent = `${Math.min(...series.map((a) => a.length))} samples`;
}

async function onRunWebGpu() {
  const button = el("run-webgpu");
  button.disabled = true;
  setPill("webgpu-status", "running", "warn");
  try {
    const result = await executeLayerBlockWebGpu();
    webgpuOutput = result.output;
    setPill("webgpu-status", "succeeded", "pass");
    el("webgpu-adapter").textContent = result.adapterLabel;
    el("webgpu-elapsed").textContent = formatMs(result.elapsed);
    el("webgpu-sha").textContent = result.sha;
    el("webgpu-preview").textContent = preview(result.output);
    compareOutputs();
  } catch (err) {
    setPill("webgpu-status", "failed", "fail");
    el("webgpu-preview").textContent = String(err.message || err);
  } finally {
    button.disabled = false;
  }
}

async function setCslResult(result) {
  cslOutput = result.output;
  lastCslTracePath = result.tracePath || null;
  lastCslNumLayers = result.numLayers || selectedNumLayers();
  setPill("csl-status", `${result.source} ${result.status}`, result.status === "succeeded" ? "pass" : "warn");
  el("csl-elapsed").textContent = formatMs(result.elapsed);
  el("csl-sha").textContent = result.sha || await sha256Hex(result.output);
  el("csl-trace").textContent = result.tracePath || "-";
  el("csl-preview").textContent = preview(result.output);
  compareOutputs();
}

async function onRunEmulator() {
  const button = el("run-emulator");
  button.disabled = true;
  setPill("emulator-status", "running", "warn");
  try {
    const result = await runCslWebGpuEmulator();
    emulatorOutput = result.output;
    setPill("emulator-status", "succeeded", "pass");
    el("emulator-elapsed").textContent = formatMs(result.elapsed);
    el("emulator-sha").textContent = result.sha;
    el("emulator-semantics").textContent = result.semanticSummary;
    el("emulator-preview").textContent = preview(result.output);
    compareOutputs();
  } catch (err) {
    setPill("emulator-status", "failed", "fail");
    el("emulator-preview").textContent = String(err.message || err);
  } finally {
    button.disabled = false;
  }
}

async function onLoadStoredCsl() {
  const button = el("load-stored-csl");
  button.disabled = true;
  const n = selectedNumLayers();
  if (n !== 1) {
    setPill("csl-status", `stored L=1 mismatches depth=${n}`, "warn");
    el("csl-preview").textContent = (
      `Stored trace at ${paths.storedCslTrace} is an L=1 reference; ` +
      `selected chain depth is L=${n}. Use "Run CSL Simulator" with the ` +
      `local server for a matching-depth trace, or reset the depth to L=1.`
    );
    button.disabled = false;
    return;
  }
  setPill("csl-status", "loading stored", "warn");
  try {
    await setCslResult(await loadStoredCsl());
  } catch (err) {
    setPill("csl-status", "failed", "fail");
    el("csl-preview").textContent = String(err.message || err);
  } finally {
    button.disabled = false;
  }
}

async function onRunLiveCsl() {
  const button = el("run-csl");
  button.disabled = true;
  setPill("csl-status", "running simfabric", "warn");
  try {
    await setCslResult(await runLiveCsl());
  } catch (err) {
    setPill("csl-status", "live unavailable", "fail");
    el("csl-preview").textContent = String(err.message || err);
  } finally {
    button.disabled = false;
  }
}

function updateCslCommand() {
  const node = el("csl-command");
  const n = selectedNumLayers();
  if (node) node.textContent = `e2b_layer_block_smoke.py --num-layers ${n}`;
  const shape = el("runtime-shape");
  if (shape) shape.textContent = `L${n} · ${size} f32`;
}

function onDepthChange() {
  // Changing chain depth invalidates any current outputs because
  // both lanes must compare at the same depth. Clear both caches so
  // the user can't accidentally compare L=1 WebGPU vs L=35 CSL.
  webgpuOutput = null;
  cslOutput = null;
  emulatorOutput = null;
  lastCslTracePath = null;
  lastCslNumLayers = null;
  setPill("webgpu-status", "idle", "pending");
  setPill("csl-status", "idle", "pending");
  setPill("emulator-status", "idle", "pending");
  el("webgpu-elapsed").textContent = "-";
  el("webgpu-sha").textContent = "-";
  el("webgpu-preview").textContent = "Run WebGPU to compute activation_out.";
  el("csl-elapsed").textContent = "-";
  el("csl-sha").textContent = "-";
  el("csl-trace").textContent = "-";
  el("csl-preview").textContent = "Run or load CSL to fetch activation_out.";
  el("emulator-elapsed").textContent = "-";
  el("emulator-sha").textContent = "-";
  el("emulator-semantics").textContent = "-";
  el("emulator-preview").textContent = "Run emulator to compute activation_out.";
  el("verdict").textContent = "waiting";
  el("max-diff").textContent = "-";
  el("sample-count").textContent = "0 samples";
  refreshEvidenceStrip();
  refreshCockpit();
  updateCslCommand();
  const plot = el("plot");
  if (plot) {
    const ctx = plot.getContext("2d");
    if (ctx) ctx.clearRect(0, 0, plot.width, plot.height);
  }
}

function init() {
  el("run-webgpu").addEventListener("click", onRunWebGpu);
  el("run-csl").addEventListener("click", onRunLiveCsl);
  el("run-emulator").addEventListener("click", onRunEmulator);
  el("load-stored-csl").addEventListener("click", onLoadStoredCsl);
  el("num-layers-select")?.addEventListener("change", onDepthChange);
  updateCslCommand();
  if (!window.isSecureContext || !("gpu" in navigator)) {
    el("secure-context-note").hidden = false;
  }
  loadSourceHashes().catch(() => {});
  checkServer();
  drawPlot();
  refreshEvidenceStrip();
  refreshCockpit();
  renderLaneLabels();
}

function badgeSet(id, label, state) {
  const node = el(id);
  if (!node) return;
  node.textContent = `${label}: ${state.label}`;
  node.className = `badge ${state.cls}`;
}

async function renderLaneLabels() {
  const tbody = el("lane-label-body");
  if (!tbody) return;
  // Lane labels are the target-ordering commitment: E2B is the
  // primary correctness target, 31B is the dense scale target,
  // 26B/A4B MoE is a blocked efficiency lane. Pulled from the
  // same JSON files C20 locks in the self-check, so the browser
  // can never disagree with the repo's source of truth.
  const sources = [
    {
      model: "Gemma 4 E2B",
      path: "config/gemma-4-e2b-real-weight-fixture.json",
      labelField: "laneLabel",
      statusSource: "fixture",
    },
    {
      model: "Gemma 4 31B",
      path: "config/gemma-4-31b-real-weight-fixture.json",
      labelField: "laneLabel",
      statusSource: "fixture",
    },
    {
      model: "Gemma 4 26B / A4B MoE",
      path: "bench/out/26b-moe-lane/lane-status.json",
      labelField: "laneLabel",
      statusSource: "laneStatus",
    },
  ];
  const rows = await Promise.all(sources.map(async (s) => {
    try {
      const d = await fetchJson(s.path);
      const label = d[s.labelField] || "(absent)";
      const status = d.laneStatus || "(fixture pin only)";
      return { model: s.model, label, status, path: s.path };
    } catch (err) {
      return {
        model: s.model,
        label: "(load failed)",
        status: err.message || "(absent)",
        path: s.path,
      };
    }
  }));
  tbody.innerHTML = rows.map((r) => (
    `<tr>
      <td>${r.model}</td>
      <td><code>${r.label}</code></td>
      <td>${r.status}</td>
    </tr>`
  )).join("");
}

async function refreshCockpit() {
  const numLayers = selectedNumLayers();
  const sourceLabel = el("cockpit-source");
  const tbody = el("cockpit-body");
  let summary = null;
  try {
    summary = await fetchJson(allLanesSummaryPath(numLayers));
    if (sourceLabel) {
      sourceLabel.textContent = `rollup: ${allLanesSummaryPath(numLayers)}`;
    }
  } catch {
    if (sourceLabel) {
      sourceLabel.textContent = `no rollup for L=${numLayers} · run: python3 bench/tools/summarize_doe_run_lanes.py --num-layers ${numLayers} --out-json ${allLanesSummaryPath(numLayers)}`;
    }
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="5" class="cockpit-empty">no rollup for L=${numLayers}</td></tr>`;
    }
    setClaimBadgesAbsent();
    return;
  }

  const lanes = summary.lanes || [];
  if (tbody) {
    tbody.innerHTML = lanes.map((lane) => {
      const status = lane.status || "-";
      const sha = lane.outputSha256
        ? `<code class="sha">${lane.outputSha256.slice(0, 16)}...</code>`
        : "-";
      const backend = lane.backendId
        ? `<code>${lane.backendId}</code>${lane.backendLane ? ` · ${lane.backendLane}` : ""}`
        : "-";
      const elapsed = lane.elapsedMs !== undefined && lane.elapsedMs !== null
        ? formatMs(lane.elapsedMs) : "-";
      return `<tr>
        <td><code>${lane.lane}</code></td>
        <td>${status}</td>
        <td>${backend}</td>
        <td>${sha}</td>
        <td>${elapsed}</td>
      </tr>`;
    }).join("");
  }

  // Claim badges: reference = webgpu-wgsl; simulator = csl-sdklayout;
  // emulator = csl-webgpu-emulator; hardware = always pending until a
  // hardware_success receipt lands (not in this demo's scope).
  const byLane = {};
  for (const l of lanes) byLane[l.lane] = l;
  const stateFor = (lane) => {
    const l = byLane[lane];
    if (!l || !l.receiptPresent) return { label: "absent", cls: "warn" };
    if (l.status === "succeeded") return { label: "ok", cls: "pass" };
    if (l.status === "blocked") return { label: "blocked", cls: "warn" };
    return { label: l.status || "unknown", cls: "fail" };
  };
  badgeSet("badge-reference", "reference (WebGPU)", stateFor("webgpu-wgsl"));
  badgeSet("badge-simulator", "simulator (CSL)", stateFor("csl-sdklayout"));
  badgeSet("badge-emulator", "emulator (WebGPU)", stateFor("csl-webgpu-emulator"));

  // Real-weight state derived from the rollup's realWeightEvidence:
  // promoted only when ALL 5 criteria are met (weightHashMatched,
  // outputParityPassed, fullModelDepthExecuted, both synthetic-absent
  // flags). Otherwise "absent" — the blocker is the external
  // checkpoint extractor, not a receipt bug.
  const rwe = summary.realWeightEvidence;
  const execStatus = summary.executionStatus;
  let rwBadge = { label: "absent", cls: "warn" };
  if (execStatus === "real_weight_layer_block_success") {
    rwBadge = { label: "promoted", cls: "pass" };
  } else if (rwe && rwe.promotionCriteriaMet) {
    const met = Object.values(rwe.promotionCriteriaMet).filter(Boolean).length;
    const total = Object.values(rwe.promotionCriteriaMet).length;
    rwBadge = { label: `${met}/${total} criteria`, cls: "warn" };
  }
  badgeSet("badge-realweight", "real-weight", rwBadge);

  badgeSet("badge-hardware", "hardware", { label: "pending", cls: "warn" });

  // Bundle badge from /api/bundle-summary (stable route for the
  // evidence-bundle summary.json). Fails closed if the summary hasn't
  // been produced — the cockpit never shows stale state silently.
  try {
    const res = await fetch("/api/bundle-summary", { cache: "no-store" });
    if (res.ok) {
      const b = await res.json();
      if (b && b.ok && b.verdict) {
        const cls = b.verdict === "passed" ? "pass"
                  : b.verdict === "failed" ? "fail" : "warn";
        badgeSet("badge-bundle", "bundle",
                 { label: `${b.verdict} (${b.passedSteps}/${b.totalSteps})`, cls });
      } else {
        badgeSet("badge-bundle", "bundle", { label: "not built", cls: "warn" });
      }
    } else {
      badgeSet("badge-bundle", "bundle", { label: "no server route", cls: "warn" });
    }
  } catch {
    badgeSet("badge-bundle", "bundle", { label: "no server", cls: "warn" });
  }
}

function setClaimBadgesAbsent() {
  for (const [id, label] of [
    ["badge-reference", "reference (WebGPU)"],
    ["badge-simulator", "simulator (CSL)"],
    ["badge-emulator", "emulator (WebGPU)"],
    ["badge-realweight", "real-weight"],
  ]) {
    badgeSet(id, label, { label: "absent", cls: "warn" });
  }
  badgeSet("badge-hardware", "hardware", { label: "pending", cls: "warn" });
  badgeSet("badge-bundle", "bundle", { label: "no rollup", cls: "warn" });
}

init();

const repoRoot = "../../";
const size = 1024;
const bytes = size * 4;
const tolerance = 1e-3;
const defaultNumLayers = 1;

const paths = {
  manifest: "runtime/zig/examples/execution-v1/gemma-4-e2b-smoke.json",
  graph: "bench/out/e2b-full-graph/gemma-4-e2b-stream-execution-plan.json",
  shaderSource: "bench/tools/doppler_webgpu_reference_export.cjs",
  initialRows: "bench/out/doppler-reference/inputs/input_seed1000_size1024.f32",
  layerInput: "bench/out/doppler-reference/inputs/input_seed2000_size1024.f32",
  storedCslTrace: "bench/out/doppler-reference/csl-L1-reference-trace.json",
  parityReceipt: "examples/doe-csl-reference-parity.gemma-4-e2b-layer-block-L1-webgpu.sample.json",
  perLayerParity: "bench/out/doppler-reference/webgpu-vs-numpy-per-layer-parity.json",
  modelRuntimeReceipt: "bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json",
  realWeightParity: "bench/out/gemma-4-e2b-real-weight-parity-L1.json",
  manifestShapeExecution: "bench/out/manifest-shape/gemma-4-e2b-manifest-shape-execution.json",
  hostPlan: "runtime/zig/examples/doe-wgsl-host-plan.gemma-4-e2b-smoke.json",
  thirtyOneBReceipt: "bench/out/31b-full-graph/gemma-4-31b-runtime-receipt.json",
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

const depthCoveragePath = "bench/out/doe-run/depth-coverage-matrix.json";

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
  const n = parseInt(v || String(defaultNumLayers), 10);
  return Number.isFinite(n) && n > 0 ? n : defaultNumLayers;
}

let webgpuOutput = null;
let cslOutput = null;
let emulatorOutput = null;
let lastCslTracePath = null;
let lastCslNumLayers = null;
let latestDirectComparison = { compared: false, pass: null, numLayers: null };
let latestDepthCoverage = null;

const el = (id) => document.getElementById(id);

function setPill(id, text, cls = "pending") {
  const node = el(id);
  if (!node) return;
  node.textContent = text;
  node.className = `status-pill ${cls}`;
}

function setText(id, text) {
  const node = el(id);
  if (node) node.textContent = text;
}

function setTone(id, tone = "") {
  const node = el(id);
  if (node) node.dataset.tone = tone;
}

function depthCoverageFor(numLayers) {
  const coverage = (latestDepthCoverage && latestDepthCoverage.coverage) || [];
  return coverage.find((row) => row.depth === numLayers) || null;
}

function selectedDepthClaimable() {
  const row = depthCoverageFor(selectedNumLayers());
  return Boolean(row && row.evidenceEligibility && row.evidenceEligibility.claimable);
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

// CSL runner stderr preserves ANSI escape codes (e.g. \x1b[34m[INFO]
// from cs_python wrappers). Browsers render them as literal garbage
// in a <pre> block, so strip them before display. Covers SGR (color)
// and cursor-move sequences — enough for the runner output shapes
// the demo actually sees.
function stripAnsi(text) {
  if (typeof text !== "string") return text;
  // eslint-disable-next-line no-control-regex
  return text.replace(/\x1b\[[0-9;]*[A-Za-z]/g, "");
}

// Runner failures from /api/run-csl come back as a JSON body with
// status/returnCode/stderrTail fields. Naive String(err.message)
// shows the raw JSON with \n literals inside the stderrTail string,
// making the stderr unreadable. This helper detects the runner-
// failure JSON shape and pretty-prints it: one header line, then
// the unescaped stderr. For non-JSON errors it returns the input
// unchanged.
function formatRunnerError(text) {
  if (typeof text !== "string") return text;
  const trimmed = text.trim();
  if (!(trimmed.startsWith("{") && trimmed.endsWith("}"))) return text;
  let parsed;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    return text;
  }
  if (!parsed || typeof parsed !== "object") return text;
  const { status, returnCode, stderrTail, numLayersRequested } = parsed;
  if (stderrTail === undefined && returnCode === undefined) return text;
  const headerParts = [];
  if (status) headerParts.push(`status=${status}`);
  if (returnCode !== undefined) headerParts.push(`returnCode=${returnCode}`);
  if (numLayersRequested !== undefined) {
    headerParts.push(`L=${numLayersRequested}`);
  }
  const header = headerParts.join(" · ") || "runner failure";
  const body = typeof stderrTail === "string" ? stderrTail : "";
  return body ? `${header}\n\n${body}` : header;
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
    const cachedDepths = Array.isArray(status.cachedTraceDepths)
      ? status.cachedTraceDepths
      : [];
    if (cachedDepths.length > 0) {
      setPill(
        "server-status",
        `server: CSL traces ready (${cachedDepths.length})`,
        "pass",
      );
    } else {
      setPill(
        "server-status",
        status.csPythonAvailable ? "server: cs_python available" : "server: no cs_python",
        status.csPythonAvailable ? "warn" : "fail",
      );
    }
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
    source: payload.source === "cached_trace" ? "cached trace" : "live simfabric",
    cacheHit: payload.cacheHit === true,
    runnerSkipped: payload.runnerSkipped || null,
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
  // Always run the WGSL path — the emulator's correctness claim is
  // about the shader, not the trace. Attempt the CSL contract check
  // separately: verified when a matching-depth trace exists, marked
  // 'unchecked' with a reason when absent. Without this split,
  // L=2/4/8/35 would 404-fail any host that hasn't captured traces
  // at those depths yet (every non-cs_python environment).
  const result = await executeLayerBlockWebGpu();
  let tracePath = null;
  let semantics = null;
  let contractStatus = { status: "unchecked", reason: "not attempted" };
  try {
    const traceInfo = await loadCslSemanticTrace(numLayers);
    tracePath = traceInfo.path;
    semantics = validateCslStreamSemantics(traceInfo.trace, numLayers);
    contractStatus = { status: "verified", tracePath };
  } catch (err) {
    const reason = (err && err.message) || String(err);
    const missingTrace = /HTTP 404|no CSL trace/i.test(reason);
    contractStatus = {
      status: "unchecked",
      kind: missingTrace ? "missing_trace" : "contract_unchecked",
      reason,
      note: (
        "Emulator WGSL executed successfully; CSL semantic contract " +
        (missingTrace
          ? "check is waiting for a matching-depth CSL trace. "
          : "check was skipped. ") +
        "Output hash is still authoritative for the WGSL kernel."
      ),
    };
  }
  return {
    ...result,
    source: "webgpu_csl_semantic_emulator",
    tracePath,
    semantics,
    semanticSummary: semantics
      ? summarizeCslSemantics(semantics, tracePath)
      : `${contractStatus.kind === "missing_trace"
          ? "CSL trace missing"
          : "CSL contract check: unchecked"}` +
        (contractStatus.reason ? ` — ${contractStatus.reason}` : "") +
        (contractStatus.note ? `\n${contractStatus.note}` : ""),
    cslContract: contractStatus,
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

async function loadAccuracyVerdict(numLayers) {
  if (numLayers !== 1) {
    throw new Error(
      `L=${numLayers} is diagnostic only; no claimable accuracy verdict today`,
    );
  }
  try {
    return await fetchJson(accuracyVerdictPath(numLayers));
  } catch {
    // L1 fallback from the repo-wide isolated per-layer artifact. Deeper
    // depths intentionally do not use this fallback: they need their own
    // promoted receipts before the UI may show a claimable verdict.
    const parity = await fetchJson(paths.perLayerParity);
    const atol = (parity.verdict && parity.verdict.verdictAtol) || 0.001;
    const layers = (parity.perLayer || [])
      .filter((layer) => layer.layer < numLayers);
    if (!layers.length) throw new Error(`no per-layer parity rows for L=${numLayers}`);
    const firstFailure = layers.find((layer) => layer.maxAbsErr > atol);
    const maxAbs = Math.max(...layers.map((layer) => layer.maxAbsErr));
    const meanAbs = layers.reduce((sum, layer) => sum + layer.meanAbsErr, 0) / layers.length;
    return {
      schemaVersion: 1,
      artifactKind: "doe_csl_emulator_accuracy_verdict_normalized",
      sourceArtifact: paths.perLayerParity,
      numLayers,
      atol,
      summary: {
        maxAbsErrAcrossLayers: maxAbs,
        meanAbsErrAcrossLayers: meanAbs,
        allLayersWithinAtol: !firstFailure,
        firstFailureLayer: firstFailure || null,
      },
      perLayer: layers,
      verdict: firstFailure ? "failed" : "passed",
    };
  }
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
    latestDirectComparison = { compared: false, pass: null, numLayers: selectedNumLayers() };
    setText("verdict", "waiting");
    setTone("verdict", "");
    setText("live-scope", "browser final-chain pending");
    setTone("live-scope", "");
    setText("max-diff", "-");
    setTone("max-diff", "");
    drawPlot();
    refreshEvidenceStrip();
    return;
  }
  const pass = pairs.every((pair) => pair.maxAbs <= tolerance);
  latestDirectComparison = {
    compared: true,
    pass,
    numLayers: selectedNumLayers(),
    pairs,
  };
  setText("verdict", pass ? "passed" : "drifted");
  setTone("verdict", pass ? "pass" : "fail");
  setText("live-scope", pass ? "browser chain matched CSL" : "browser chain diverged from CSL");
  setTone("live-scope", pass ? "pass" : "warn");
  setText("max-diff", pairs
    .map((pair) => `${pair.label} ${pair.maxAbs.toExponential(3)} · mean ${pair.meanAbs.toExponential(3)}`)
    .join(" | "));
  setTone("max-diff", pass ? "pass" : "warn");
  drawPlot();
  refreshEvidenceStrip();
}

async function refreshEvidenceStrip() {
  const numLayers = selectedNumLayers();
  const depthRow = depthCoverageFor(numLayers);
  const eligibility = (depthRow && depthRow.evidenceEligibility) || {};
  const isClaimableDepth = eligibility.claimable === true;
  const hasRealWeightSmoke = eligibility.realWeightClaimable === true;
  const speedEl = el("evidence-speedup");
  const accEl = el("evidence-accuracy");
  const idEl = el("evidence-identity");
  const scopeEl = el("evidence-claim-scope");
  const basisEl = el("evidence-basis");
  if (scopeEl) {
    scopeEl.textContent = "local debug only";
    scopeEl.dataset.tone = "";
  }
  if (basisEl) {
    basisEl.textContent = isClaimableDepth
      ? (hasRealWeightSmoke
          ? "synthetic + real-weight L1 smoke"
          : "synthetic L1 layer-block")
      : "diagnostic depth only";
    basisEl.dataset.tone = isClaimableDepth ? "pass" : "warn";
  }
  setText(
    "truth-headline",
    isClaimableDepth
      ? (hasRealWeightSmoke
          ? "Current claim: L1 synthetic + real-weight smoke layer-block"
          : "Current claim: L1 synthetic layer-block only")
      : `Selected L=${numLayers}: diagnostic only, not claimable E2B evidence`,
  );
  setTone("truth-headline", isClaimableDepth ? "pass" : "warn");
  setText(
    "truth-detail",
    isClaimableDepth
      ? (hasRealWeightSmoke
          ? "The promoted boundary is L1: synthetic lane parity plus BF16-derived real-weight smoke parity at atol=1e-3. Full E2B runtime and hardware are still blocked."
          : "The claim is CSL simfabric and WebGPU output parity for one synthetic E2B-shaped layer-block at atol=1e-3.")
      : "Multi-depth promotion, full E2B runtime execution, and Cerebras hardware are still blocked.",
  );

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
    idEl.dataset.tone = both ? "pass" : "warn";
    const ratio = speedVerdict.emulatorSpeedupOverLocalSimfabric;
    const emuMs = speedVerdict.emulatorElapsedMs;
    const cslMs = speedVerdict.cslSimfabricElapsedMs;
    if (typeof ratio === "number") {
      speedEl.textContent =
        `${ratio.toFixed(1)}x (${formatMs(emuMs)} vs ${formatMs(cslMs)})`;
      speedEl.dataset.tone = ratio > 1.0 ? "pass" : "";
    } else {
      speedEl.textContent = "-";
      speedEl.dataset.tone = "";
    }
  } else {
    idEl.textContent = `no speed verdict for L=${numLayers}`;
    idEl.dataset.tone = "";
    speedEl.textContent = "-";
    speedEl.dataset.tone = "";
  }

  // Per-layer accuracy verdict: separate artifact.
  let accVerdict = null;
  try {
    accVerdict = await loadAccuracyVerdict(numLayers);
  } catch {
    accVerdict = null;
  }
  if (accVerdict && accVerdict.summary) {
    const s = accVerdict.summary;
    const pass = s.allLayersWithinAtol;
    accEl.textContent = pass
      ? `all ${accVerdict.numLayers}L within ${accVerdict.atol} (max ${s.maxAbsErrAcrossLayers.toExponential(2)})`
      : `layer ${s.firstFailureLayer?.layer} exceeds ${accVerdict.atol}`;
    accEl.dataset.tone = pass ? "pass" : "fail";
    const direct = latestDirectComparison;
    if (
      pass &&
      direct.compared &&
      direct.numLayers === numLayers &&
      direct.pass === false
    ) {
      setText("verdict", "per-layer pass, chain drift");
      setTone("verdict", "warn");
      setText("live-scope", "live browser chain drifted");
      setTone("live-scope", "warn");
      if (basisEl) {
        basisEl.textContent = "per-layer semantic match";
        basisEl.dataset.tone = "pass";
      }
      if (scopeEl) {
        scopeEl.textContent = "final chain is diagnostic";
        scopeEl.dataset.tone = "warn";
      }
    } else if (
      direct.compared &&
      direct.numLayers === numLayers &&
      direct.pass === true &&
      scopeEl
    ) {
      scopeEl.textContent = "final-chain parity";
      scopeEl.dataset.tone = "pass";
    }
  } else {
    accEl.textContent = `no accuracy verdict for L=${numLayers}`;
    accEl.dataset.tone = isClaimableDepth ? "" : "warn";
    if (!isClaimableDepth) {
      setText("evidence-claim-scope", "blocked depth; diagnostic only");
      setTone("evidence-claim-scope", "warn");
    }
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
  const n = selectedNumLayers();
  button.disabled = true;
  setPill("webgpu-status", `running L=${n}`, "warn");
  try {
    const result = await executeLayerBlockWebGpu();
    webgpuOutput = result.output;
    setPill("webgpu-status", `succeeded L=${n}`, "pass");
    el("webgpu-adapter").textContent = result.adapterLabel;
    el("webgpu-elapsed").textContent = formatMs(result.elapsed);
    el("webgpu-sha").textContent = result.sha;
    el("webgpu-preview").textContent = preview(result.output);
    compareOutputs();
  } catch (err) {
    setPill("webgpu-status", `failed L=${n}`, "fail");
    el("webgpu-preview").textContent = stripAnsi(String(err.message || err));
  } finally {
    button.disabled = false;
  }
}

async function setCslResult(result) {
  cslOutput = result.output;
  lastCslTracePath = result.tracePath || null;
  lastCslNumLayers = result.numLayers || selectedNumLayers();
  setPill(
    "csl-status",
    `${result.source} ${result.status} L=${lastCslNumLayers}`,
    result.status === "succeeded" ? "pass" : "warn",
  );
  el("csl-elapsed").textContent = formatMs(result.elapsed);
  el("csl-sha").textContent = result.sha || await sha256Hex(result.output);
  el("csl-trace").textContent = result.tracePath || "-";
  setText(
    "csl-source-mode",
    result.cacheHit ? "cached local simfabric trace" : result.source,
  );
  el("csl-preview").textContent = preview(result.output);
  compareOutputs();
}

async function onRunEmulator() {
  const button = el("run-emulator");
  const n = selectedNumLayers();
  button.disabled = true;
  setPill("emulator-status", `running L=${n}`, "warn");
  try {
    const result = await runCslWebGpuEmulator();
    emulatorOutput = result.output;
    // Pill distinguishes full contract verification (green) from
    // WGSL-ran-but-contract-unchecked (amber) so a reviewer doesn't
    // mistake "emulator ran" for "emulator ran + matched CSL".
    const contractOk = result.cslContract &&
                       result.cslContract.status === "verified";
    const missingTrace = result.cslContract &&
                         result.cslContract.kind === "missing_trace";
    setPill("emulator-status",
            contractOk
              ? `succeeded L=${n}`
              : missingTrace
                ? `wgsl ran L=${n} · CSL trace missing`
                : `wgsl ran L=${n} · contract unchecked`,
            contractOk ? "pass" : "warn");
    el("emulator-elapsed").textContent = formatMs(result.elapsed);
    el("emulator-sha").textContent = result.sha;
    el("emulator-semantics").textContent = result.semanticSummary;
    el("emulator-preview").textContent = preview(result.output);
    compareOutputs();
  } catch (err) {
    setPill("emulator-status", `failed L=${n}`, "fail");
    el("emulator-preview").textContent = stripAnsi(String(err.message || err));
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
    el("csl-preview").textContent = stripAnsi(String(err.message || err));
  } finally {
    button.disabled = false;
  }
}

async function onRunLiveCsl() {
  const button = el("run-csl");
  const n = selectedNumLayers();
  button.disabled = true;
  setPill("csl-status", `loading CSL L=${n}`, "warn");
  try {
    await setCslResult(await runLiveCsl());
  } catch (err) {
    setPill("csl-status", `live unavailable L=${n}`, "fail");
    el("csl-preview").textContent = stripAnsi(
      formatRunnerError(String(err.message || err))
    );
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

function setInitialDepth() {
  const select = el("num-layers-select");
  if (!select) return;
  const requested = new URLSearchParams(window.location.search).get("layers");
  const allowed = Array.from(select.options).map((option) => option.value);
  select.value = allowed.includes(requested) ? requested : String(defaultNumLayers);
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
  setText("csl-source-mode", "-");
  el("csl-preview").textContent = "Run or load CSL to fetch activation_out.";
  el("emulator-elapsed").textContent = "-";
  el("emulator-sha").textContent = "-";
  el("emulator-semantics").textContent = "-";
  el("emulator-preview").textContent = "Run emulator to compute activation_out.";
  setText("verdict", "waiting");
  setTone("verdict", "");
  setText("live-scope", "browser final-chain pending");
  setTone("live-scope", "");
  setText("max-diff", "-");
  setTone("max-diff", "");
  setText("sample-count", "0 samples");
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
  setInitialDepth();
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

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function artifactLink(path, label) {
  const safePath = escapeHtml(path);
  const safeLabel = escapeHtml(label || path);
  return `<a href="${repoRoot}${safePath}" target="_blank" rel="noreferrer">${safeLabel}</a>`;
}

function statusBadge(label, cls) {
  return `<span class="badge ${cls}">${escapeHtml(label)}</span>`;
}

function blockerText(blockers) {
  const list = Array.isArray(blockers) ? blockers.filter(Boolean) : [];
  return list.length ? list.map(escapeHtml).join("<br>") : "none";
}

function renderEvidenceReceiptRows(rows) {
  const body = el("evidence-receipts-body");
  if (!body) return;
  body.innerHTML = rows.map((row) => (
    `<tr>
      <td>${escapeHtml(row.label)}</td>
      <td>${statusBadge(row.status, row.cls)}</td>
      <td>${row.path ? artifactLink(row.path, row.linkLabel || row.path) : escapeHtml(row.receipt || "-")}</td>
      <td>${blockerText(row.blockers)}</td>
    </tr>`
  )).join("");
}

async function refreshEvidenceReceiptMatrix() {
  const rows = [];
  let sdkModelBadge = { label: "missing", cls: "warn" };

  try {
    const receipt = await fetchJson(paths.modelRuntimeReceipt);
    const sdk = receipt.sdkLayoutModelExecutionEvidence || {};
    const promoted = (
      receipt.executionStatus === "real_weight_layer_block_success"
      && sdk.promotionStatus === "sdk_layout_layer_block_smoke_promoted"
      && sdk.runtimeStop
      && sdk.runtimeStop.reached === true
      && sdk.kernelSource
      && sdk.kernelSource.kernelIsStub === false
      && Array.isArray(sdk.blockers)
      && sdk.blockers.length === 0
    );
    sdkModelBadge = promoted
      ? { label: "promoted L1", cls: "pass" }
      : { label: sdk.promotionStatus || receipt.executionStatus || "diagnostic", cls: "warn" };
    rows.push({
      label: "E2B SdkLayout layer-block",
      status: sdkModelBadge.label,
      cls: sdkModelBadge.cls,
      path: paths.modelRuntimeReceipt,
      linkLabel: "model receipt",
      blockers: [
        ...(sdk.blockers || []),
        ...((sdk.remainingClaimBlockers || []).map((b) => `remaining: ${b}`)),
      ],
    });
    const depth = receipt.sdkLayoutDepthDiagnosticEvidence || {};
    const depthStatus = depth.status || "missing";
    const depthPassed = (
      depthStatus === "full_depth_smoke_diagnostic_passed"
      && depth.claimable === false
      && depth.manifestShapeRuntimeExecuted === false
    );
    rows.push({
      label: "E2B L35 smoke-chain diagnostic",
      status: depthPassed ? "diagnostic passed" : depthStatus,
      cls: depthPassed ? "warn" : "fail",
      path: paths.modelRuntimeReceipt,
      linkLabel: "model receipt",
      blockers: [
        ...((depth.blockers || []).map((b) => `diagnostic: ${b}`)),
        ...((depth.remainingClaimBlockers || []).map((b) => `remaining: ${b}`)),
      ],
    });
  } catch (err) {
    rows.push({
      label: "E2B SdkLayout layer-block",
      status: "missing",
      cls: "warn",
      path: paths.modelRuntimeReceipt,
      linkLabel: "model receipt",
      blockers: [err.message || "unreadable receipt"],
    });
  }

  try {
    const parity = await fetchJson(paths.realWeightParity);
    const pass = parity.verdict === "parity_passed";
    rows.push({
      label: "E2B BF16 real-weight L1 parity",
      status: pass ? "parity_passed" : parity.verdict || "not passed",
      cls: pass ? "pass" : "warn",
      path: paths.realWeightParity,
      linkLabel: "real-weight parity",
      blockers: pass ? [] : ["tolerance parity not promoted"],
    });
  } catch (err) {
    rows.push({
      label: "E2B BF16 real-weight L1 parity",
      status: "missing",
      cls: "warn",
      path: paths.realWeightParity,
      linkLabel: "real-weight parity",
      blockers: [err.message || "unreadable receipt"],
    });
  }

  try {
    const oracle = await fetchJson(paths.manifestShapeExecution);
    const pass = (
      oracle.status === "succeeded"
      && oracle.verdict === "manifest_shape_cpu_full_text_forward_passed"
    );
    rows.push({
      label: "E2B manifest-shape CPU oracle",
      status: pass ? "CPU oracle passed" : oracle.verdict || "not passed",
      cls: pass ? "pass" : "warn",
      path: paths.manifestShapeExecution,
      linkLabel: "manifest-shape oracle",
      blockers: oracle.blockers || [
        "full Doe/CSL manifest-shape runtime receipt still required",
        "hardware receipt still required",
      ],
    });
  } catch (err) {
    rows.push({
      label: "E2B manifest-shape CPU oracle",
      status: "missing",
      cls: "warn",
      path: paths.manifestShapeExecution,
      linkLabel: "manifest-shape oracle",
      blockers: [err.message || "unreadable receipt"],
    });
  }

  try {
    const receipt31 = await fetchJson(paths.thirtyOneBReceipt);
    rows.push({
      label: "31B dense smoke-shape CSL",
      status: "diagnostic",
      cls: "warn",
      path: paths.thirtyOneBReceipt,
      linkLabel: "31B receipt",
      blockers: [
        `current receipt: ${receipt31.executionStatus || "unknown"}`,
        "31B manifest-shape streaming receipt still required",
        "31B real-weight parity receipt still required",
      ],
    });
  } catch (err) {
    rows.push({
      label: "31B dense smoke-shape CSL",
      status: "blocked",
      cls: "warn",
      path: paths.thirtyOneBReceipt,
      linkLabel: "31B receipt",
      blockers: [err.message || "31B receipt missing"],
    });
  }

  rows.push({
    label: "Cerebras hardware",
    status: "pending",
    cls: "warn",
    receipt: "operator receipt not present",
    blockers: [
      "direct cmaddr or WSC appliance execution required",
      "redacted hardware receipt required",
    ],
  });

  badgeSet("badge-sdklayout-model", "SdkLayout model", sdkModelBadge);
  renderEvidenceReceiptRows(rows);
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

async function refreshDepthCoverage() {
  // Source: bench/out/doe-run/depth-coverage-matrix.json. Keeps the
  // aspirational-vs-evidenced split honest for every declared depth
  // without making a viewer click through each selector option.
  const label = el("depth-coverage-label");
  if (!label) return;
  let matrix;
  try {
    matrix = await fetchJson(depthCoveragePath);
  } catch {
    label.textContent = `depth coverage: no matrix at ${depthCoveragePath}`;
    return;
  }
  latestDepthCoverage = matrix;
  const r = matrix.rollup || {};
  const declared = r.declaredCount;
  const anyCount = r.anyEligibleReceiptCount ?? r.anyReceiptCount;
  const fullCount = r.fullEligibleCoverageCount ?? r.fullCoverageCount;
  const tolCount = r.claimableWithinToleranceCount ?? r.withinToleranceCount;
  const depthsFull = (
    r.depthsWithFullEligibleLaneCoverage || r.depthsWithFullLaneCoverage || []
  ).map(d => `L=${d}`);
  const depthsTol = (
    r.depthsClaimableWithinTolerance || r.depthsAllWithinTolerance || []
  ).map(d => `L=${d}`);
  const fullList = depthsFull.length ? ` [${depthsFull.join(", ")}]` : "";
  const tolList = depthsTol.length ? ` [${depthsTol.join(", ")}]` : "";
  label.innerHTML =
    `claimable depth coverage: <strong>${anyCount}/${declared}</strong> any receipt · ` +
    `<strong>${fullCount}/${declared}</strong> full lane${fullList} · ` +
    `<strong>${tolCount}/${declared}</strong> within tolerance${tolList}`;
  renderEvidenceLadder(matrix);
  refreshEvidenceStrip();
}

function renderEvidenceLadder(matrix) {
  const node = el("evidence-ladder");
  if (!node) return;
  const rows = matrix.coverage || [];
  if (!rows.length) {
    node.innerHTML = `<div class="ladder-row"><span>no depth rows</span></div>`;
    return;
  }
  node.innerHTML = rows.map((row) => {
    const eligibility = row.evidenceEligibility || {};
    const claimable = eligibility.claimable === true;
    const raw = row.laneReceiptsPresent || 0;
    const eligible = row.evidenceEligibleLanesPresent || 0;
    const status = claimable ? "claimable" : "blocked";
    const cls = claimable ? "pass" : "warn";
    const scope = eligibility.claimableLabel || eligibility.evidenceTier || "no summary";
    return `<div class="ladder-row">
      <strong>L=${row.depth}</strong>
      <span class="badge ${cls}">${status}</span>
      <span>${scope}</span>
      <code>${eligible}/5 eligible · ${raw}/5 raw</code>
    </div>`;
  }).join("");
}

async function refreshCockpit() {
  const numLayers = selectedNumLayers();
  const sourceLabel = el("cockpit-source");
  const tbody = el("cockpit-body");
  await refreshDepthCoverage();
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
    setText("evidence-rollup", `no rollup for L=${numLayers}`);
    setTone("evidence-rollup", "warn");
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="5" class="cockpit-empty">no rollup for L=${numLayers}</td></tr>`;
    }
    const emptyParityBody = el("parity-matrix-body");
    const emptyParityRollup = el("parity-rollup");
    if (emptyParityBody) {
      emptyParityBody.innerHTML =
        `<tr><td colspan="5" class="cockpit-empty">parity matrix not loaded</td></tr>`;
    }
    if (emptyParityRollup) emptyParityRollup.textContent = "rollup: -";
    setClaimBadgesAbsent();
    return;
  }

  const lanes = summary.lanes || [];
  const eligibility = summary.evidenceEligibility || {};
  const isClaimableSummary = eligibility.claimable === true;
  const rollupTone = isClaimableSummary &&
    summary.verdict === "all_lanes_identity_and_parity_matched"
    ? "pass"
    : "warn";
  const toleranceVerdict = (
    (summary.runtimeParityTolerance || {}).rollupVerdict || "not_evaluated"
  );
  setText(
    "evidence-rollup",
    `${isClaimableSummary ? "claimable" : "diagnostic"} · ` +
    `${summary.verdict || "unknown"} · ${toleranceVerdict}`,
  );
  setTone("evidence-rollup", rollupTone);
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

  // Runtime-lane parity matrix with tolerance-aware verdicts. Digest
  // equality is bit-level; tolerance verdict is the accuracy gate.
  // A "digest_mismatch + within_tolerance" pair is a PASS under the
  // declared atol — float-order drift across backends legitimately
  // produces different digests while staying well inside the E2B
  // layer-block tolerance declared in the fixture.
  const parityBody = el("parity-matrix-body");
  const parityRollup = el("parity-rollup");
  const matrix = summary.outputParityMatrix || [];
  const rpt = summary.runtimeParityTolerance || null;
  if (parityRollup) {
    if (rpt) {
      const verdict = rpt.rollupVerdict || "not_evaluated";
      const cls = verdict === "all_within_tolerance" ? "pass"
                : verdict === "exceeds_tolerance" ? "fail"
                : verdict === "shape_or_non_finite_failure" ? "fail"
                : "warn";
      parityRollup.innerHTML =
        `rollup: <span class="badge ${cls}">${verdict}</span> ` +
        `· atol=${rpt.atol} (<code>${rpt.atolSource}</code>) ` +
        `· within ${rpt.withinToleranceCount}/${rpt.informativePairCount}`;
    } else {
      parityRollup.textContent = "rollup: not evaluated";
    }
  }
  if (parityBody) {
    if (!matrix.length) {
      parityBody.innerHTML =
        `<tr><td colspan="5" class="cockpit-empty">no parity pairs</td></tr>`;
    } else {
      parityBody.innerHTML = matrix.map((p) => {
        const digest = p.verdict || "-";
        const digestCls = digest === "bit_exact_match" ? "pass" : "warn";
        const tol = p.toleranceVerdict || "not_evaluated";
        const tolCls = tol === "within_tolerance" ? "pass"
                     : tol === "exceeds_tolerance" ? "fail"
                     : tol === "shape_mismatch" ? "fail"
                     : tol === "non_finite" ? "fail"
                     : "warn";
        const maxAbs = (typeof p.maxAbsDiff === "number")
          ? p.maxAbsDiff.toExponential(3) : "-";
        const atol = (typeof p.toleranceAtol === "number")
          ? p.toleranceAtol.toExponential(0) : "-";
        return `<tr>
          <td><code>${p.left}</code> ↔ <code>${p.right}</code></td>
          <td><span class="badge ${digestCls}">${digest}</span></td>
          <td><span class="badge ${tolCls}">${tol}</span></td>
          <td>${maxAbs}</td>
          <td>${atol}</td>
        </tr>`;
      }).join("");
    }
  }

  // Claim badges: reference = webgpu-wgsl; simulator = csl-sdklayout;
  // emulator = csl-webgpu-emulator; hardware = always pending until a
  // hardware_success receipt lands (not in this demo's scope).
  const byLane = {};
  for (const l of lanes) byLane[l.lane] = l;
  const stateFor = (lane) => {
    const l = byLane[lane];
    if (!l || !l.receiptPresent) return { label: "absent", cls: "warn" };
    if (!isClaimableSummary) return { label: "diagnostic", cls: "warn" };
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

  await refreshEvidenceArtifactBadges(summary);
  await refreshEvidenceReceiptMatrix();

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

async function refreshEvidenceArtifactBadges(summary) {
  try {
    const hostPlan = await fetchJson(paths.hostPlan);
    const minimumVersion = (
      ((hostPlan.cslc || {}).validation || {}).minimumVersion
    );
    badgeSet(
      "badge-sdk",
      "SDK floor",
      minimumVersion === "2.10.0"
        ? { label: "2.10.0", cls: "pass" }
        : { label: minimumVersion || "unknown", cls: "warn" },
    );
  } catch {
    badgeSet("badge-sdk", "SDK floor", { label: "missing", cls: "warn" });
  }

  let executionStatus = summary && summary.executionStatus;
  if (!executionStatus) {
    try {
      const receipt = await fetchJson(paths.modelRuntimeReceipt);
      executionStatus = receipt.executionStatus;
    } catch {
      executionStatus = null;
    }
  }
  if (executionStatus === "real_weight_layer_block_success") {
    badgeSet(
      "badge-runtime-receipt",
      "model receipt",
      { label: "real-weight L1", cls: "pass" },
    );
  } else if (executionStatus) {
    badgeSet(
      "badge-runtime-receipt",
      "model receipt",
      { label: executionStatus, cls: "warn" },
    );
  } else {
    badgeSet(
      "badge-runtime-receipt",
      "model receipt",
      { label: "absent", cls: "warn" },
    );
  }

  try {
    const oracle = await fetchJson(paths.manifestShapeExecution);
    const exec = oracle.executionSummary || {};
    const layers = exec.layersExecuted;
    const total = exec.numLayers;
    const pass = (
      oracle.status === "succeeded"
      && oracle.verdict === "manifest_shape_cpu_full_text_forward_passed"
      && exec.allLayerOutputsFinite === true
      && layers === total
    );
    badgeSet(
      "badge-manifest-shape",
      "manifest-shape",
      pass
        ? { label: `CPU oracle ${layers}/${total}L`, cls: "pass" }
        : { label: oracle.verdict || "not passed", cls: "warn" },
    );
  } catch {
    badgeSet(
      "badge-manifest-shape",
      "manifest-shape",
      { label: "missing", cls: "warn" },
    );
  }
}

function setClaimBadgesAbsent() {
  for (const [id, label] of [
    ["badge-reference", "reference (WebGPU)"],
    ["badge-simulator", "simulator (CSL)"],
    ["badge-emulator", "emulator (WebGPU)"],
    ["badge-realweight", "real-weight"],
    ["badge-sdk", "SDK floor"],
    ["badge-runtime-receipt", "model receipt"],
    ["badge-sdklayout-model", "SdkLayout model"],
    ["badge-manifest-shape", "manifest-shape"],
  ]) {
    badgeSet(id, label, { label: "absent", cls: "warn" });
  }
  renderEvidenceReceiptRows([{
    label: "receipt matrix",
    status: "absent",
    cls: "warn",
    receipt: "no rollup",
    blockers: ["summary rollup not loaded"],
  }]);
  badgeSet("badge-hardware", "hardware", { label: "pending", cls: "warn" });
  badgeSet("badge-bundle", "bundle", { label: "no rollup", cls: "warn" });
}

init();

const repoRoot = "../../";

const el = (id) => document.getElementById(id);

function redactEnabled() {
  return el("redact-toggle")?.checked === true;
}

function maybeRedact(value) {
  if (!redactEnabled()) return value;
  if (!value) return value;
  // Keep the last path component only, replace leading dirs with '…'.
  const str = String(value);
  const parts = str.split("/");
  if (parts.length <= 1) return "[redacted]";
  return `…/${parts[parts.length - 1]}`;
}

function redactShaKeepPrefix(hex) {
  if (!hex) return "[absent]";
  return (hex + "").slice(0, 8) + "…";  // keep prefix even in redacted mode — it's a hash, not a path
}

function setPill(id, text, cls = "pending") {
  const node = el(id);
  if (!node) return;
  node.textContent = text;
  node.className = `status-pill ${cls}`;
}

function setSdkCommand(artifactDir) {
  const node = el("sdk-command");
  if (!node) return;
  if (!artifactDir) {
    node.textContent = "sdk_debug_shell visualize --artifact_dir <set artifact dir above>";
    return;
  }
  // The command itself is operator-runnable; hide the dir path when
  // redacted mode is on so the screen-share only shows the shape.
  const shown = redactEnabled() ? maybeRedact(artifactDir) : artifactDir;
  node.textContent = `sdk_debug_shell visualize --artifact_dir ${shown}`;
}

function setArtifactSummary(artifactDir) {
  const node = el("artifact-summary");
  if (!node) return;
  if (!artifactDir) {
    node.innerHTML = "<span>artifact dir: not configured</span>";
    return;
  }
  const shown = redactEnabled() ? maybeRedact(artifactDir) : artifactDir;
  node.innerHTML = `<span>artifact dir: <code>${shown}</code></span>`;
}

async function inspectArtifactDir(artifactDir) {
  setSdkCommand(artifactDir);
  setArtifactSummary(artifactDir);
  setPill("artifact-status", "inspecting", "warn");

  let info = null;
  try {
    const res = await fetch(
      `/api/artifact-dir-info?path=${encodeURIComponent(artifactDir)}`,
      { cache: "no-store" },
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    info = await res.json();
  } catch (err) {
    setPill("artifact-status", "server required", "fail");
    for (const id of ["panel-fabric", "panel-pe", "panel-source",
                       "panel-trace", "panel-io", "panel-evidence"]) {
      const node = el(id);
      if (!node) continue;
      node.classList.add("placeholder");
      node.innerHTML = (
        `this viewer requires the E2B demo server running on the ` +
        `same origin — its /api/artifact-dir-info route enumerates ` +
        `the directory. Start via: python3 ` +
        `demos/gemma4-e2b-csl-sim/server.py --port 8020`
      );
    }
    return;
  }

  if (info && info.ok === false) {
    setPill("artifact-status", "invalid path", "fail");
    for (const id of ["panel-fabric", "panel-pe", "panel-source",
                       "panel-trace", "panel-io", "panel-evidence"]) {
      const node = el(id);
      if (!node) continue;
      node.classList.add("placeholder");
      node.innerHTML = `server rejected path: <code>${info.error}</code>`;
    }
    return;
  }

  setPill("artifact-status",
          `${info.numFiles} files, ${info.numSdkArtifacts} SDK artifacts`,
          "pass");

  // Fabric panel: surface colors.json routing if present.
  const fabric = el("panel-fabric");
  if (fabric) {
    fabric.classList.remove("placeholder");
    if (info.colorsJson && !info.colorsJson.error) {
      const names = (info.colorsJson.colorNames || []).slice(0, 16).join(", ");
      fabric.innerHTML = (
        `<strong>colors.json</strong>: ${info.colorsJson.numColors} colors` +
        (names ? `<br>${names}` : "")
      );
    } else if (info.colorsJson && info.colorsJson.error) {
      fabric.innerHTML = `colors.json: <code>${info.colorsJson.error}</code>`;
    } else {
      fabric.innerHTML = `no colors.json in ${info.pathChecked}`;
    }
  }

  // Source panel: list SDK-artifact files with sizes.
  const source = el("panel-source");
  if (source) {
    source.classList.remove("placeholder");
    const sdkFiles = (info.files || []).filter(
      (f) => f.kind === "sdk_artifact",
    );
    if (!sdkFiles.length) {
      source.innerHTML = "no SDK artifact files detected";
    } else {
      const rows = sdkFiles.map((f) =>
        `${f.name}: ${f.sizeBytes} bytes`
      ).join("<br>");
      source.innerHTML = `<strong>SDK artifacts:</strong><br>${rows}`;
    }
  }

  // PE drilldown panel: show subdirs (generated/, etc).
  const pe = el("panel-pe");
  if (pe) {
    pe.classList.remove("placeholder");
    const subs = (info.subdirs || []).join(", ");
    pe.innerHTML = (
      `subdirs: <code>${subs || "(none)"}</code><br>` +
      `map file: <code>${info.mapFile ? info.mapFile.path + ' (' + info.mapFile.sizeBytes + 'B)' : "(absent)"}</code>`
    );
  }

  // Host-IO + trace panels both read from the same trace JSON.
  // Fetch once, render twice.
  await renderHostIoAndTracePanels(artifactDir);

  // Evidence overlay: cross-runtime parity verdict from the repo.
  await renderEvidencePanel(artifactDir);
}

async function renderHostIoAndTracePanels(artifactDir) {
  const ioNode = el("panel-io");
  const traceNode = el("panel-trace");
  const tracePath = deriveTracePath(artifactDir);
  if (!tracePath) {
    if (ioNode) {
      ioNode.classList.add("placeholder");
      ioNode.innerHTML = (
        "host I/O contract requires a CSL runner trace path. " +
        "Accepted convention: <code>bench/out/scratch/gemma4-e2b-csl-sim/" +
        "compile-L&lt;N&gt;</code> (auto-derives sibling " +
        "<code>csl-L&lt;N&gt;-live-trace.json</code>) or paste a trace path " +
        "directly into the input above."
      );
    }
    if (traceNode) {
      traceNode.classList.add("placeholder");
      traceNode.innerHTML = "no trace path derivable from the artifact dir";
    }
    return;
  }
  let info = null;
  try {
    const res = await fetch(
      `/api/trace-host-io-contract?trace=${encodeURIComponent(tracePath)}`,
      { cache: "no-store" },
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    info = await res.json();
  } catch (err) {
    const msg = `could not reach /api/trace-host-io-contract — is the demo server running? <code>${err.message}</code>`;
    for (const n of [ioNode, traceNode]) {
      if (n) { n.classList.add("placeholder"); n.innerHTML = msg; }
    }
    return;
  }
  if (!info.ok) {
    const msg = `trace at <code>${tracePath}</code>: ${info.error}`;
    for (const n of [ioNode, traceNode]) {
      if (n) { n.classList.add("placeholder"); n.innerHTML = msg; }
    }
    return;
  }
  renderHostIoPanelFromInfo(ioNode, tracePath, info);
  renderTracePanelFromInfo(traceNode, tracePath, info);
}

function renderHostIoPanelFromInfo(node, tracePath, info) {
  if (!node) return;
  node.classList.remove("placeholder");
  const layoutRows = (info.hostIoLayout || []).map((e) => (
    `${e.streamId}: ${e.role}/${e.dtype}, ${e.elementsPerPe} elts, ` +
    `bufSize=${e.ioBufferSize ?? '?'}B, payload=${e.planPayloadBytes ?? '?'}B`
  )).join("<br>");
  const counts = info.sendReceiveCounts || {};
  const shownTrace = redactEnabled() ? maybeRedact(tracePath) : tracePath;
  node.innerHTML = (
    `<strong>trace:</strong> ${shownTrace}<br>` +
    `<strong>depth:</strong> ${info.numLayersChained ?? '?'} layers chained<br>` +
    `<strong>send/recv:</strong> ${counts.sends ?? '?'}/${counts.receives ?? '?'}<br>` +
    `<strong>kernel sha:</strong> <code>${(info.kernelSourceSha256 || '').slice(0, 16)}...</code><br>` +
    `<strong>streams:</strong><br>${layoutRows || '(empty)'}`
  );
}

function renderTracePanelFromInfo(node, tracePath, info) {
  if (!node) return;
  node.classList.remove("placeholder");
  const telemetry = info.streamTelemetry || {};
  const counters = info.perStreamCounters || [];
  const events = info.streamEventsTail || [];
  const counterRows = counters.map((c) => (
    `${c.streamId} (${c.role}/${c.operation}): ` +
    `issued=${c.issuedCount ?? '?'}, completed=${c.completedCount ?? '?'}, ` +
    `pending=${c.pendingCount ?? '?'}, maxQ=${c.maxQueueDepth ?? '?'}`
  )).join("<br>");
  const eventRows = events.slice(0, 12).map((ev) => (
    `[${ev.event || '?'}] ${ev.streamId}/${ev.operation} L${ev.layerIndex ?? '?'}`
  )).join("<br>");
  const truncNote = info.streamEventsTruncated
    ? ` (showing 12 of ${info.streamEventsTotalInTrace} total, server cap ${events.length})`
    : ` (${events.length} events total)`;
  node.innerHTML = (
    `<strong>executedRun.status:</strong> <code>${info.executedRunStatus ?? '?'}</code><br>` +
    `<strong>measurementSource:</strong> <code>${telemetry.measurementSource ?? '?'}</code><br>` +
    `<strong>perStream counters:</strong><br>${counterRows || '(empty)'}<br>` +
    `<strong>streamEventsTail${truncNote}:</strong><br>${eventRows || '(empty)'}`
  );
}

async function renderEvidencePanel(artifactDir) {
  const node = el("panel-evidence");
  if (!node) return;
  // Cross-runtime parity verdict covers the E2B layer-block today;
  // we surface it alongside the artifact dir so the reviewer can
  // see whether the *repo's* receipts attest to the program this
  // artifact dir was compiled for. The verdict itself is a static
  // file — just fetch it.
  const parityPath =
    "/bench/out/streaming-executor/e2b-layer-block-cross-runtime-parity-check.json";
  try {
    const res = await fetch(parityPath, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const verdict = await res.json();
    const v = verdict.verdict || {};
    const runnerTrace = verdict.runnerTrace || {};
    const syntheticTrace = verdict.syntheticTrace || {};
    const kernel = verdict.kernelSource || {};
    const met = (v.preconditionsMet || []).length;
    const missing = (v.preconditionsMissing || []).length;
    const total = met + missing;
    const eligible = v.promotionEligible === true;

    const driftTag = runnerTrace.shaDrift
      ? `<span style="color:var(--red)">shaDrift=true</span>`
      : `<span style="color:var(--green)">shaDrift=false</span>`;
    const eligibleTag = eligible
      ? `<span style="color:var(--green)">promotionEligible=true</span>`
      : `<span style="color:var(--amber)">promotionEligible=false</span>`;

    node.classList.remove("placeholder");
    const liveKernelSha = (kernel.liveSha256 || '').slice(0, 16);
    const runnerKernelSha = (runnerTrace.kernelSourceSha256InTrace || '').slice(0, 16);
    const syntheticSha = (syntheticTrace.sha256 || '').slice(0, 16);
    const shownArtifact = redactEnabled() ? maybeRedact(artifactDir) : artifactDir;
    node.innerHTML = (
      `<strong>artifact dir:</strong> <code>${shownArtifact}</code><br>` +
      `<strong>live kernel sha:</strong> <code>${liveKernelSha}...</code><br>` +
      `<strong>runner-recorded kernel sha:</strong> <code>${runnerKernelSha}...</code> ${driftTag}<br>` +
      `<strong>synthetic trace sha:</strong> <code>${syntheticSha}...</code><br>` +
      `<strong>preconditions:</strong> ${met}/${total} met (${missing} missing)<br>` +
      `<strong>verdict:</strong> ${eligibleTag}<br>` +
      `<span style="color:var(--muted);font-size:11px">` +
      `parity verdict loaded from <code>${parityPath}</code> — ` +
      `scope is the layer-block kernel, not the whole compile dir.` +
      `</span>`
    );
  } catch (err) {
    node.classList.add("placeholder");
    node.innerHTML = (
      `evidence overlay needs the parity verdict to be served on this ` +
      `origin. Start the E2B demo server at the repo root to reach ` +
      `<code>${parityPath}</code>. Error: <code>${err.message}</code>`
    );
  }
}

function deriveTracePath(artifactDir) {
  // Best-effort: for "bench/out/scratch/gemma4-e2b-csl-sim/compile-L<N>"
  // → "bench/out/scratch/gemma4-e2b-csl-sim/csl-L<N>-live-trace.json"
  const m = artifactDir.match(
    /^(bench\/out\/scratch\/gemma4-e2b-csl-sim)\/compile-L(\d+)\/?$/
  );
  if (m) return `${m[1]}/csl-L${m[2]}-live-trace.json`;
  // Accept an explicit trace path too (if user pastes one).
  if (/\/.*trace.*\.json$/.test(artifactDir)) return artifactDir;
  return null;
}

async function onLoadArtifact() {
  const input = el("artifact-dir-input");
  const raw = (input?.value || "").trim();
  if (!raw) {
    setPill("artifact-status", "path required", "fail");
    return;
  }
  await inspectArtifactDir(raw);
}

async function onCopySdkCommand() {
  const node = el("sdk-command");
  const btn = el("sdk-command-copy");
  if (!node || !btn) return;
  const text = (node.textContent || "").trim();
  try {
    await navigator.clipboard.writeText(text);
    const original = btn.textContent;
    btn.textContent = "copied";
    btn.disabled = true;
    setTimeout(() => {
      btn.textContent = original || "copy";
      btn.disabled = false;
    }, 1500);
  } catch (err) {
    btn.textContent = "copy failed";
    setTimeout(() => { btn.textContent = "copy"; }, 1500);
  }
}

function init() {
  el("load-artifact")?.addEventListener("click", onLoadArtifact);
  el("sdk-command-copy")?.addEventListener("click", onCopySdkCommand);
  el("artifact-dir-input")?.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") onLoadArtifact();
  });
  // Redact toggle: persist across refreshes, re-inspect on change so
  // all panels redraw consistently.
  const redactBox = el("redact-toggle");
  if (redactBox) {
    redactBox.checked = sessionStorage.getItem("sdk-gui-redact") === "1";
    redactBox.addEventListener("change", () => {
      sessionStorage.setItem(
        "sdk-gui-redact",
        redactBox.checked ? "1" : "0",
      );
      const current = el("artifact-dir-input")?.value?.trim();
      if (current) inspectArtifactDir(current);
      else {
        setSdkCommand(null);
        setArtifactSummary(null);
      }
    });
  }

  // URL ?artifact=<rel-path> auto-populates the input and runs
  // inspection so a dashboard link can open this viewer pinned to a
  // specific artifact directory.
  const params = new URLSearchParams(window.location.search);
  const qsArtifact = params.get("artifact");
  if (qsArtifact) {
    const input = el("artifact-dir-input");
    if (input) input.value = qsArtifact;
    inspectArtifactDir(qsArtifact);
  } else {
    setSdkCommand(null);
    setArtifactSummary(null);
  }
}

init();

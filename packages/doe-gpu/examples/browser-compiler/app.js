import { createDoeCompiler } from '../../src/browser-compiler.js';
import { compilerArtifact } from '../../src/browser-compiler-artifact.js';
import { sha256 } from '../../src/browser-compiler-cache.js';
import { initialParticles, referenceParticles, compareParticles } from './particles.js';
import { createParticleSession, measureMode, modes } from './benchmark.js';

const $ = (id) => document.getElementById(id);
const labels = { browser: 'Browser', disabled: 'Adapter · passes off', enabled: 'Doe · passes on' };
const median = (values) => [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];
const ms = (value) => value === null ? 'Unavailable'
  : value === 0 ? '< clock resolution' : `${value.toFixed(2)} ms`;
const contract = await (await fetch('contract.json')).json();
const code = await (await fetch('particles.wgsl')).text();
if (contract.schemaVersion !== 1 || contract.workgroupSize !== 128
    || contract.dt !== Math.fround(contract.dt)) throw new Error('Unsupported particle contract');
const initial = initialParticles(contract.particleCount, contract.seed);
let device;
let context;
let format;
let compiler;
let compilerPromise;
let preview;
let previewFrame;
let running = false;
let mode = 'browser';
let locked = false;
let report;
const switches = [];

function fail(error) {
  $('error').hidden = false;
  $('error').textContent = error.message;
  $('preview-status').textContent = 'Stopped';
}

function lock(value) {
  locked = value;
  $('compare').disabled = value;
  $('capacity').disabled = value || !report;
  for (const button of document.querySelectorAll('[data-mode]')) button.disabled = value;
}

async function getCompiler() {
  if (!compilerPromise) compilerPromise = createDoeCompiler({ artifact: {
    url: new URL(`../../assets/${compilerArtifact.asset}`, import.meta.url).href,
    sha256: compilerArtifact.sha256, byteLength: compilerArtifact.byteLength,
  } }).then((value) => {
    compiler = value;
    $('compiler-info').textContent = JSON.stringify({ artifact: compilerArtifact,
      initialization: value.initialization }, null, 2);
    return value;
  }).catch((error) => {
    compilerPromise = null;
    throw error;
  });
  return compilerPromise;
}

function options(selected, state, configuration = contract, timestamps = false, shader = code) {
  return { device, context, format, code: shader, compiler, mode: selected,
    initial: state, contract: configuration, timestamps };
}

async function pause() {
  running = false;
  cancelAnimationFrame(previewFrame);
  if (!preview) return initial.slice();
  const state = await preview.snapshot();
  await preview.close();
  preview = null;
  return state;
}

let inFlight = Promise.resolve();
async function pausePreview() {
  running = false;
  cancelAnimationFrame(previewFrame);
  await inFlight;
  return pause();
}

async function resume(selected, state) {
  if (selected !== 'browser') await getCompiler();
  const next = await createParticleSession(options(selected, state));
  try {
    const restored = await next.snapshot();
    const verification = compareParticles(restored, state, { absolute: 0, relative: 0 });
    if (!verification.passed) throw new Error('Restored snapshot verification failed');
    switches.push({ from: mode, to: selected, stateHash: await sha256(state), verification });
  } catch (error) {
    await next.close();
    throw error;
  }
  preview = next;
  mode = selected;
  for (const button of document.querySelectorAll('[data-mode]')) {
    button.setAttribute('aria-pressed', String(button.dataset.mode === selected));
  }
  running = !matchMedia('(prefers-reduced-motion: reduce)').matches;
  const tick = async () => {
    if (!running) return;
    inFlight = preview.run(1, false);
    try {
      const { metrics } = await inFlight;
      $('preview-status').textContent = `${labels[mode]} · ${ms(metrics.completeOperationMs)}`;
      if (running) previewFrame = requestAnimationFrame(tick);
    } catch (error) {
      running = false;
      fail(error);
    }
  };
  if (running) previewFrame = requestAnimationFrame(tick);
  else await preview.run(1, false);
}

function display(rows) {
  $('rows').replaceChildren();
  for (const selected of modes) {
    const samples = rows.filter((row) => row.mode === selected);
    if (!samples.length) continue;
    const row = document.createElement('tr');
    const values = [labels[selected],
      ms(median(samples.map((value) => value.pipelinePreparationMs))),
      ms(median(samples.map((value) => value.recordMs + value.submitMs))),
      samples[0].gpuComputeMs === null ? 'Unavailable'
        : ms(median(samples.map((value) => value.gpuComputeMs))),
      ms(median(samples.map((value) => value.completeOperationMs))),
      samples.every((value) => value.oracle.passed) ? 'Verified' : 'FAILED'];
    values.forEach((text, index) => {
      const cell = document.createElement(index === 0 ? 'th' : 'td');
      cell.textContent = text;
      if (index === 5) cell.className = 'pass';
      row.append(cell);
    });
    $('rows').append(row);
  }
}

async function compare({ timestamps = device.features.has('timestamp-query') } = {}) {
  const repeats = contract.repeats;
  if (locked) throw new Error('Demo is busy');
  lock(true);
  await pausePreview();
  try {
    $('error').hidden = true;
    $('preview-status').textContent = 'Preview paused';
    const expected = referenceParticles(initial, contract.steps, contract.dt);
    const rows = [];
    let baseline;
    const started = performance.now();
    for (let repeat = 0; repeat < repeats; repeat++) {
      const order = modes.map((_, index) => modes[(index + repeat) % modes.length]);
      for (const selected of order) {
        $('progress').textContent = `${labels[selected]} · cohort ${repeat + 1}/${repeats}`;
        if (selected !== 'browser') await getCompiler();
        const measured = await measureMode(options(selected, initial, contract, timestamps),
          expected, baseline);
        if (selected === 'browser' && !baseline) baseline = measured.positions;
        rows.push({ cohort: repeat, ...measured.row });
        display(rows);
      }
    }
    const perMode = Object.fromEntries(modes.map((selected) => [selected,
      median(rows.filter((row) => row.mode === selected).map((row) => row.applicationMs))]));
    const netRatio = perMode.browser / perMode.enabled;
    const passRatio = perMode.disabled / perMode.enabled;
    $('verdict').textContent = netRatio >= contract.materialGainRatio
      ? `${netRatio.toFixed(2)}× warm application gain · repeat to confirm`
      : `No material warm gain · ${(perMode.enabled / perMode.browser).toFixed(2)}× browser time`;
    $('progress').textContent = `${repeats} cohorts · all components verified`;
    report = {
      schemaVersion: 1, label: 'Doe-assisted WebGPU', classification: 'diagnostic',
      executionOwner: 'browser', nativeDoeRuntime: false, contract,
      userAgent: navigator.userAgent, adapter: window.doeParticleLab.adapter,
      canvas: { width: $('view').width, height: $('view').height },
      originalWGSLHash: await sha256(new TextEncoder().encode(code)),
      initialStateHash: await sha256(initial), compilerArtifact,
      compilerInitialization: compiler.initialization,
      scope: 'Fresh buffers and pipelines per sample; shared browser device and compiler Worker. '
        + 'Browser driver caches are not reset. Application timing excludes one-time compiler '
        + 'delivery, which is reported separately. Timestamp intervals overlap host work.',
      rows, switches: [...switches], summaries: { applicationMedianMs: perMode, netRatio, passRatio },
      experimentWallMs: performance.now() - started,
    };
    $('export').disabled = false;
    window.doeParticleLab.report = report;
    return report;
  } finally {
    lock(false);
    await resume(mode, initial);
  }
}

async function offlineCompare(shader, { timestamps = device.features.has('timestamp-query') } = {}) {
  if (locked) throw new Error('Demo is busy');
  lock(true);
  await pausePreview();
  try {
    const expected = referenceParticles(initial, contract.steps, contract.dt);
    await getCompiler();
    const disabled = await compiler.compile(code, { optimize: false });
    if (disabled.wgsl !== code) throw new Error('Disabled compiler changed WGSL');
    const variants = { original: code, disabled: disabled.wgsl, transformed: shader };
    const names = Object.keys(variants);
    const rows = [];
    let reference;
    for (let cohort = 0; cohort < contract.repeats; cohort++) {
      for (const name of names.map((_, index) => names[(index + cohort) % names.length])) {
        const measured = await measureMode(options('offline', initial, contract, timestamps, variants[name]),
          expected, reference);
        reference ??= measured.positions;
        rows.push({ cohort, variant: name, ...measured.row });
      }
    }
    const summaries = Object.fromEntries(names.map((name) => [name, Object.fromEntries(
      ['pipelinePreparationMs', 'gpuComputeMs', 'completeOperationMs', 'applicationMs'].map((metric) =>
        [metric, rows[0][metric] === null ? null
          : median(rows.filter((row) => row.variant === name).map((row) => row[metric]))]))]));
    return { schemaVersion: 1, classification: 'diagnostic', contract, timestamps,
      scope: 'All WGSL is prepared before measurement. No optimizer Worker request runs inside samples. '
        + 'Sequential rotated cohorts share the browser device and driver caches; fresh pipelines and buffers.',
      rows, summaries, baseline: rows.find((row) => row.variant === 'original'),
      candidate: rows.find((row) => row.variant === 'transformed') };
  } finally {
    lock(false);
    await resume(mode, initial);
  }
}

async function capacity() {
  if (!report || locked) throw new Error('Complete fixed-work comparison first');
  lock(true);
  await pausePreview();
  try {
    const cap = contract.capacity;
    const limit = Math.min(cap.limit, Math.floor(device.limits.maxStorageBufferBindingSize / 16));
    const rows = [];
    for (const selected of modes) {
      for (let count = cap.start; count <= limit; count *= 2) {
        $('capacity-result').textContent = `${labels[selected]} · ${count.toLocaleString()} particles`;
        const state = initialParticles(count, contract.seed);
        const expected = referenceParticles(state, contract.steps, contract.dt);
        const samples = [];
        for (let sample = 0; sample < cap.samples; sample++) {
          const measured = await measureMode(options(selected, state), expected);
          samples.push(measured.row);
        }
        const operationMedianMs = median(samples.map((row) => row.completeOperationMs));
        const passedBudget = operationMedianMs <= cap.operationBudgetMs;
        rows.push({ mode: selected, count, operationMedianMs, passedBudget, samples });
        if (!passedBudget) break;
      }
    }
    report.capacity = { contract: cap, limit, rows,
      scope: 'Separate experiment; budget includes draw, completion and readback. '
        + 'A ceiling at the configured limit is not the hardware maximum.' };
    $('capacity-result').textContent = modes.map((selected) => {
      const admitted = rows.filter((row) => row.mode === selected && row.passedBudget);
      const maximum = admitted.at(-1)?.count ?? 0;
      return `${labels[selected]}: ${maximum.toLocaleString()}${maximum === limit ? '+' : ''}`;
    }).join(' · ');
    return report.capacity;
  } finally {
    lock(false);
    await resume(mode, initial);
  }
}

try {
  if (!navigator.gpu) throw new Error('WebGPU unavailable. Use a supported browser on HTTPS or localhost.');
  const gpu = navigator.gpu;
  const adapter = await gpu.requestAdapter({ powerPreference: 'high-performance' });
  if (!adapter) throw new Error('No WebGPU adapter available');
  const adapterInfo = adapter.info;
  const identity = { vendor: adapterInfo.vendor, architecture: adapterInfo.architecture,
    device: adapterInfo.device, description: adapterInfo.description,
    isFallbackAdapter: adapterInfo.isFallbackAdapter ?? adapter.isFallbackAdapter ?? null,
    timestampQuery: adapter.features.has('timestamp-query') };
  device = await adapter.requestDevice({
    requiredFeatures: adapter.features.has('timestamp-query') ? ['timestamp-query'] : [],
  });
  device.lost.then((info) => {
    running = false;
    compiler?.close();
    lock(true);
    fail(new Error(`GPU device lost: ${info.reason} · ${info.message}`));
  });
  device.addEventListener('uncapturederror', (event) => fail(event.error));
  context = $('view').getContext('webgpu');
  format = navigator.gpu.getPreferredCanvasFormat();
  context.configure({ device, format, alphaMode: 'opaque' });
  $('device-info').textContent = JSON.stringify(identity, null, 2);
  window.doeParticleLab = { adapter: identity, compare, offlineCompare, capacity,
    getCompiler, async switchMode(selected) {
      if (!modes.includes(selected) || locked) throw new Error('Invalid or busy mode switch');
      lock(true);
      try { await resume(selected, await pausePreview()); } finally { lock(false); }
      if (navigator.gpu !== gpu) throw new Error('Browser GPU identity changed');
      return switches.at(-1);
    }, async pause() { return pausePreview(); },
    switches, contract, initial, code,
  };
  $('compare').onclick = () => compare().catch(fail);
  $('capacity').onclick = () => capacity().catch(fail);
  for (const button of document.querySelectorAll('[data-mode]')) {
    button.onclick = () => window.doeParticleLab.switchMode(button.dataset.mode).catch(fail);
  }
  $('export').onclick = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)],
      { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'doe-assisted-webgpu.json';
    link.click();
    URL.revokeObjectURL(url);
  };
  await resume('browser', initial);
  window.doeParticleLab.ready = true;
  window.addEventListener('pagehide', () => {
    running = false;
    compiler?.close();
    device.destroy();
  }, { once: true });
} catch (error) {
  lock(true);
  fail(error);
}

#!/usr/bin/env node
/**
 * Doppler-side Node+WebGPU reference export for the E2B layer-block
 * contract. Uses the same `webgpu` npm package Doppler uses (Dawn-based
 * WebGPU under Node) so the output represents what browser/Node WebGPU
 * would produce — not a scalar-f32 numpy mirror.
 *
 * CURRENT SCOPE: stage 1 only (pre-attn RMSNorm). Other stages land in
 * follow-up ticks. A multi-stage reference covering all 4 stages +
 * num_layers chain is the end goal; each tick adds one rung.
 *
 * The emitted artifacts match doppler_reference_export_stub.py's
 * contract:
 *   <out-dir>/
 *     activation_out.f32      -- the f32 output vector from WebGPU
 *     export_receipt.json     -- runtime=doppler_node_webgpu,
 *                                manifest/graph/input/weight/output shas
 *
 * Usage:
 *   node bench/tools/doppler_webgpu_reference_export.js \
 *     --manifest runtime/zig/examples/execution-v1/gemma-4-e2b-smoke.json \
 *     --graph   bench/out/e2b-full-graph/gemma-4-e2b-stream-execution-plan.json \
 *     --size 1024 --num-layers 1 \
 *     --initial-rows-seed 1000 --per-layer-base 2000 \
 *     --out-dir bench/out/doppler-reference/gemma-4-e2b-layer-block-webgpu
 *
 * Stage-1-only means we dump the RMSNorm output instead of the full
 * layer-block output. The parity gate can compare this against the
 * CSL runner's stage-1 intermediate (if emitted) with tolerance.
 */

'use strict';

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const REPO_ROOT = path.resolve(__dirname, '..', '..');

function parseArgs() {
  const argv = process.argv.slice(2);
  const opts = {
    manifest: 'runtime/zig/examples/execution-v1/gemma-4-e2b-smoke.json',
    graph: 'bench/out/e2b-full-graph/gemma-4-e2b-stream-execution-plan.json',
    size: 1024,
    numLayers: 1,
    initialRowsSeed: 1000,
    perLayerBase: 2000,
    outDir: 'bench/out/doppler-reference/gemma-4-e2b-layer-block-webgpu',
  };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    const v = argv[i + 1];
    if (k === '--manifest') { opts.manifest = v; i++; }
    else if (k === '--graph') { opts.graph = v; i++; }
    else if (k === '--size') { opts.size = parseInt(v, 10); i++; }
    else if (k === '--num-layers') { opts.numLayers = parseInt(v, 10); i++; }
    else if (k === '--initial-rows-seed') { opts.initialRowsSeed = parseInt(v, 10); i++; }
    else if (k === '--per-layer-base') { opts.perLayerBase = parseInt(v, 10); i++; }
    else if (k === '--out-dir') { opts.outDir = v; i++; }
  }
  return opts;
}

function resolvePath(p) {
  return path.isAbsolute(p) ? p : path.resolve(REPO_ROOT, p);
}

function sha256File(p) {
  const h = crypto.createHash('sha256');
  h.update(fs.readFileSync(p));
  return h.digest('hex');
}

function sha256Bytes(buf) {
  const h = crypto.createHash('sha256');
  h.update(buf);
  return h.digest('hex');
}

// Numpy's default_rng(seed).standard_normal(size, f32) is PCG64 +
// polar / ziggurat. We cannot replicate it exactly in JS. For this
// stage-1 smoke, we accept that JS's reference produces DIFFERENT
// seeded inputs than numpy. This is still a valid cross-runtime
// proof IF we use the SAME inputs on both sides. The contract says:
// "same inputs, same output." So Doppler must consume the inputs
// produced on the numpy side, not re-generate them.
//
// For this tick we read the input tensor bytes that the CSL runner
// would have generated (replicating numpy's default_rng via a
// pre-computed fixture) from a side-channel file.
function loadInputTensorF32(seed, size) {
  // Simple portable stub: pull input bytes from the Doppler-reference-
  // export stub's intermediate file if present, else bail with a
  // clear error. The stub already knows numpy's PRNG output; we
  // reuse its bytes.
  const fixturePath = resolvePath(
    `bench/out/doppler-reference/inputs/input_seed${seed}_size${size}.f32`
  );
  if (!fs.existsSync(fixturePath)) {
    throw new Error(
      `Input fixture missing: ${fixturePath}. Run ` +
      `\`python3 bench/tools/doppler_prepare_webgpu_inputs.py --size ${size} ` +
      `--seeds ${seed}\` to materialize numpy PRNG inputs for WebGPU ` +
      `consumption.`
    );
  }
  const buf = fs.readFileSync(fixturePath);
  if (buf.byteLength !== size * 4) {
    throw new Error(
      `Input fixture wrong size: ${buf.byteLength} bytes, expected ${size * 4}`
    );
  }
  return new Float32Array(
    buf.buffer, buf.byteOffset, size
  );
}

// Full WGSL layer-block: stages 1 + 2 + 2c + 3 + 4 in one compute
// dispatch. Single workgroup, single thread — matches the CSL kernel's
// scalar in-order semantic as closely as WebGPU permits. Driver may
// still fuse FMA / vectorize reductions; that's expected drift the
// tolerance-parity gate accepts (atol=1e-3 is the tested threshold).
//
// Storage buffers:
//   rows (read)    -- stage 1's input; for layer L>0 this is layer L-1's
//                     activation_out fed back by the host.
//   proj (read)    -- stage 1 gamma (same-seed fixture as wts).
//   wts (read)     -- per-head KV region + gamma2 + MLP gate/up weights.
//   buf_out (rw)   -- stage-1 rmsnorm output, stage-2c residual output,
//                     stage-3 post_norm output, and stage-4 final
//                     activation_out (the emitted reference bytes).
//
// Hardcoded CSL-matching constants: num_heads=8, head_dim=8,
// kv_len_per_head=4. size must be multiple of num_heads*head_dim=64
// and must be >= num_heads*2*head_dim*kv_len_per_head + 2*qs where
// qs = size/4. For default size=1024 both hold.
const WGSL_LAYER_BLOCK = `
@group(0) @binding(0) var<storage, read> rows: array<f32>;
@group(0) @binding(1) var<storage, read> proj: array<f32>;
@group(0) @binding(2) var<storage, read> wts: array<f32>;
@group(0) @binding(3) var<storage, read_write> buf_out: array<f32>;

struct Params { size: u32, eps: f32 };
@group(0) @binding(4) var<uniform> params: Params;

// Rope cos table: indexed by (pair_d, position_p). Matches the 20
// CSL/numpy 9-decimal-digit literals that round-trip bit-exact in f32.
fn rope_cos_at(p: u32, d: u32) -> f32 {
  if (d == 0u) {
    if (p == 0u) { return 1.0; }
    if (p == 1u) { return 0.540302277; }
    if (p == 2u) { return -0.416146845; }
    if (p == 3u) { return -0.989992499; }
    return -0.653643608;
  }
  if (d == 1u) {
    if (p == 0u) { return 1.0; }
    if (p == 1u) { return 0.995004177; }
    if (p == 2u) { return 0.980066597; }
    if (p == 3u) { return 0.955336511; }
    return 0.921060979;
  }
  if (d == 2u) {
    if (p == 0u) { return 1.0; }
    if (p == 1u) { return 0.999949992; }
    if (p == 2u) { return 0.999800026; }
    if (p == 3u) { return 0.999550045; }
    return 0.999200106;
  }
  // d == 3
  if (p == 0u) { return 1.0; }
  if (p == 1u) { return 0.999999523; }
  if (p == 2u) { return 0.999997973; }
  if (p == 3u) { return 0.999995530; }
  return 0.999992013;
}

fn rope_sin_at(p: u32, d: u32) -> f32 {
  if (d == 0u) {
    if (p == 0u) { return 0.0; }
    if (p == 1u) { return 0.841470957; }
    if (p == 2u) { return 0.909297407; }
    if (p == 3u) { return 0.141120002; }
    return -0.756802499;
  }
  if (d == 1u) {
    if (p == 0u) { return 0.0; }
    if (p == 1u) { return 0.0998334140; }
    if (p == 2u) { return 0.198669329; }
    if (p == 3u) { return 0.295520216; }
    return 0.389418334;
  }
  if (d == 2u) {
    if (p == 0u) { return 0.0; }
    if (p == 1u) { return 0.00999983307; }
    if (p == 2u) { return 0.0199986659; }
    if (p == 3u) { return 0.029995501; }
    return 0.0399893336;
  }
  // d == 3
  if (p == 0u) { return 0.0; }
  if (p == 1u) { return 0.000999999815; }
  if (p == 2u) { return 0.00199999870; }
  if (p == 3u) { return 0.00299999560; }
  return 0.00399998948;
}

@compute @workgroup_size(1)
fn layer_block() {
  let size: u32 = params.size;
  let eps: f32 = params.eps;
  let qs: u32 = size / 4u;

  // Stage 1: pre-attn RMSNorm. Writes buf_out = rmsnorm(rows) * proj.
  var sum_sq: f32 = 0.0;
  for (var i: u32 = 0u; i < size; i = i + 1u) {
    sum_sq = sum_sq + rows[i] * rows[i];
  }
  let mean_sq: f32 = sum_sq / f32(size);
  let rms: f32 = sqrt(mean_sq + eps);
  let inv_rms: f32 = 1.0 / rms;
  for (var i: u32 = 0u; i < size; i = i + 1u) {
    buf_out[i] = (rows[i] * inv_rms) * proj[i];
  }

  // Stage 2: 8-head MHA with PER-HEAD VECTOR Q/K/V and MULTI-PAIR ROPE.
  let num_heads: u32 = 8u;
  let head_dim: u32 = 8u;
  let kv_len: u32 = 4u;
  let num_pairs: u32 = head_dim / 2u; // 4
  let per_head_K_len: u32 = head_dim * kv_len; // 32
  let per_head_stride: u32 = 2u * per_head_K_len; // 64
  let attn_flat_len: u32 = num_heads * head_dim; // 64

  var attn_vals: array<f32, 64>;
  for (var i: u32 = 0u; i < attn_flat_len; i = i + 1u) {
    attn_vals[i] = 0.0;
  }

  for (var h: u32 = 0u; h < num_heads; h = h + 1u) {
    let base_h: u32 = qs + h * per_head_stride;
    let q_base: u32 = h * head_dim;

    // Rope-rotate Q_h at position kv_len.
    var q_rot: array<f32, 8>;
    for (var d: u32 = 0u; d < num_pairs; d = d + 1u) {
      let a: u32 = 2u * d;
      let q0: f32 = buf_out[q_base + a + 0u];
      let q1: f32 = buf_out[q_base + a + 1u];
      let qc: f32 = rope_cos_at(kv_len, d);
      let qs_: f32 = rope_sin_at(kv_len, d);
      q_rot[a + 0u] = (qc * q0) - (qs_ * q1);
      q_rot[a + 1u] = (qs_ * q0) + (qc * q1);
    }

    // Pass 1: seed lmax from j=0 then scan j in [0,kv_len) for max.
    var k_rot: array<f32, 8>;
    var lmax: f32 = 0.0;
    {
      for (var d: u32 = 0u; d < num_pairs; d = d + 1u) {
        let a: u32 = 2u * d;
        let k0: f32 = wts[base_h + a + 0u];
        let k1: f32 = wts[base_h + a + 1u];
        let kc: f32 = rope_cos_at(0u, d);
        let ks: f32 = rope_sin_at(0u, d);
        k_rot[a + 0u] = (kc * k0) - (ks * k1);
        k_rot[a + 1u] = (ks * k0) + (kc * k1);
      }
      var l_seed: f32 = 0.0;
      for (var dd: u32 = 0u; dd < head_dim; dd = dd + 1u) {
        l_seed = l_seed + (q_rot[dd] * k_rot[dd]);
      }
      lmax = l_seed;
    }
    for (var j: u32 = 0u; j < kv_len; j = j + 1u) {
      for (var d: u32 = 0u; d < num_pairs; d = d + 1u) {
        let a: u32 = 2u * d;
        let k0: f32 = wts[base_h + j * head_dim + a + 0u];
        let k1: f32 = wts[base_h + j * head_dim + a + 1u];
        let kc: f32 = rope_cos_at(j, d);
        let ks: f32 = rope_sin_at(j, d);
        k_rot[a + 0u] = (kc * k0) - (ks * k1);
        k_rot[a + 1u] = (ks * k0) + (kc * k1);
      }
      var l: f32 = 0.0;
      for (var dd: u32 = 0u; dd < head_dim; dd = dd + 1u) {
        l = l + (q_rot[dd] * k_rot[dd]);
      }
      if (l > lmax) { lmax = l; }
    }

    // Pass 2: poly_c1 softmax weights + per-d weighted V.
    var sum_w: f32 = 0.0;
    var weighted_v: array<f32, 8>;
    for (var d2: u32 = 0u; d2 < head_dim; d2 = d2 + 1u) {
      weighted_v[d2] = 0.0;
    }
    for (var j: u32 = 0u; j < kv_len; j = j + 1u) {
      for (var d: u32 = 0u; d < num_pairs; d = d + 1u) {
        let a: u32 = 2u * d;
        let k0: f32 = wts[base_h + j * head_dim + a + 0u];
        let k1: f32 = wts[base_h + j * head_dim + a + 1u];
        let kc: f32 = rope_cos_at(j, d);
        let ks: f32 = rope_sin_at(j, d);
        k_rot[a + 0u] = (kc * k0) - (ks * k1);
        k_rot[a + 1u] = (ks * k0) + (kc * k1);
      }
      var l: f32 = 0.0;
      for (var dd: u32 = 0u; dd < head_dim; dd = dd + 1u) {
        l = l + (q_rot[dd] * k_rot[dd]);
      }
      let x: f32 = l - lmax;
      var wj: f32 = 0.0;
      if (x > -1.0) {
        let xp1: f32 = x + 1.0;
        let sq: f32 = xp1 * xp1;
        wj = 0.25 * sq;
      }
      sum_w = sum_w + wj;
      for (var dd: u32 = 0u; dd < head_dim; dd = dd + 1u) {
        let v_hjd: f32 = wts[base_h + per_head_K_len + j * head_dim + dd];
        weighted_v[dd] = weighted_v[dd] + (wj * v_hjd);
      }
    }
    for (var dd: u32 = 0u; dd < head_dim; dd = dd + 1u) {
      attn_vals[q_base + dd] = weighted_v[dd] / sum_w;
    }
  }

  // Stage 2c: residual. attn_out = flat attn_val + rows.
  for (var i: u32 = 0u; i < size; i = i + 1u) {
    let k_idx: u32 = i - (i / attn_flat_len) * attn_flat_len;
    buf_out[i] = attn_vals[k_idx] + rows[i];
  }

  // Stage 3: post-attn RMSNorm with gamma2 broadcast 4x.
  var sum_sq2: f32 = 0.0;
  for (var i: u32 = 0u; i < size; i = i + 1u) {
    sum_sq2 = sum_sq2 + buf_out[i] * buf_out[i];
  }
  let mean_sq2: f32 = sum_sq2 / f32(size);
  let rms2: f32 = sqrt(mean_sq2 + eps);
  let inv_rms2: f32 = 1.0 / rms2;
  for (var i: u32 = 0u; i < size; i = i + 1u) {
    var g_idx: u32 = i;
    if (g_idx >= qs) { g_idx = g_idx - qs; }
    if (g_idx >= qs) { g_idx = g_idx - qs; }
    if (g_idx >= qs) { g_idx = g_idx - qs; }
    buf_out[i] = (buf_out[i] * inv_rms2) * wts[g_idx];
  }

  // Stage 4: gated MLP with poly_c1 GELU.
  let mlp_len: u32 = qs / 2u;
  let gate_base: u32 = 3u * qs;
  var gate: f32 = 0.0;
  for (var k: u32 = 0u; k < mlp_len; k = k + 1u) {
    gate = gate + wts[gate_base + k] * buf_out[k];
  }
  let up_base: u32 = gate_base + mlp_len;
  var up: f32 = 0.0;
  for (var k: u32 = 0u; k < mlp_len; k = k + 1u) {
    up = up + wts[up_base + k] * buf_out[mlp_len + k];
  }
  for (var i: u32 = 0u; i < size; i = i + 1u) {
    let pre_act: f32 = up * buf_out[i];
    var act: f32 = 0.0;
    if (pre_act >= 1.0) {
      act = pre_act;
    } else {
      if (pre_act > -1.0) {
        let xp1: f32 = pre_act + 1.0;
        let sq: f32 = xp1 * xp1;
        act = 0.25 * sq;
      }
    }
    buf_out[i] = (gate * act) + buf_out[i];
  }
}
`;

async function main() {
  const opts = parseArgs();
  const manifestPath = resolvePath(opts.manifest);
  const graphPath = resolvePath(opts.graph);
  for (const [label, p] of [['manifest', manifestPath], ['graph', graphPath]]) {
    if (!fs.existsSync(p)) {
      console.error(`ERROR: --${label} missing: ${p}`);
      process.exit(2);
    }
  }
  const outDir = resolvePath(opts.outDir);
  fs.mkdirSync(outDir, { recursive: true });

  // Load per-layer numpy-PRNG fixtures. Runner's convention:
  //   rows_layer_0 = default_rng(initialRowsSeed).standard_normal
  //   rows_layer_l>0 = activation_out of layer l-1 (fed back by host)
  //   proj_l, wts_l = default_rng(perLayerBase + l).standard_normal
  //                   (fresh rng per call -> proj_l == wts_l)
  const size = opts.size;
  const bytes = size * 4;

  let initialRowsF32;
  const perLayerInputsF32 = [];
  try {
    initialRowsF32 = loadInputTensorF32(opts.initialRowsSeed, size);
    for (let l = 0; l < opts.numLayers; l++) {
      perLayerInputsF32.push(
        loadInputTensorF32(opts.perLayerBase + l, size)
      );
    }
  } catch (e) {
    console.error(`BLOCKER: ${e.message}`);
    process.exit(3);
  }
  const inputTensorSha = sha256Bytes(
    Buffer.from(initialRowsF32.buffer, initialRowsF32.byteOffset, bytes)
  );
  const weightShaAgg = crypto.createHash('sha256');
  for (const arr of perLayerInputsF32) {
    weightShaAgg.update(
      Buffer.from(arr.buffer, arr.byteOffset, bytes)
    );
  }
  const weightSha = weightShaAgg.digest('hex');

  // Init Node+WebGPU via the same package Doppler uses. The webgpu
  // npm package is installed in the Doppler tree; require via an
  // absolute path so the export runs from any cwd. Falls back to
  // the usual resolver if that path is absent.
  const dopplerWebgpu = '/home/x/deco/doppler/node_modules/webgpu';
  const webgpuMod = fs.existsSync(dopplerWebgpu)
    ? require(dopplerWebgpu)
    : require('webgpu');
  const { create, globals } = webgpuMod;
  for (const [k, v] of Object.entries(globals || {})) {
    if (globalThis[k] === undefined) globalThis[k] = v;
  }
  const gpu = create([]);
  const adapter = await gpu.requestAdapter();
  if (!adapter) { console.error('ERROR: no WebGPU adapter'); process.exit(4); }
  const device = await adapter.requestDevice();

  // Buffers:
  //   rowsBuf: input stage-1 rows. Bound as <storage, read>. Rewritten
  //            each layer (initial or previous layer's buf_out).
  //   projBuf: per-layer projection (stage-1 gamma). Rewritten each layer.
  //   wtsBuf:  per-layer weights (stage-2/3/4). Rewritten each layer.
  //   bufOut:  shared intermediate + final output for each layer.
  //            Read back via staging buffer after each layer AND at end.
  const rowsBuf = device.createBuffer({
    size: bytes,
    usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST,
  });
  const projBuf = device.createBuffer({
    size: bytes,
    usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST,
  });
  const wtsBuf = device.createBuffer({
    size: bytes,
    usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST,
  });
  const bufOut = device.createBuffer({
    size: bytes,
    usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_SRC | GPUBufferUsage.COPY_DST,
  });
  const stagingBuf = device.createBuffer({
    size: bytes,
    usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ,
  });
  const paramsBuf = device.createBuffer({
    size: 16, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
  });

  // params: size(u32), eps(f32), + 8 bytes padding to 16
  const paramsArr = new ArrayBuffer(16);
  new Uint32Array(paramsArr, 0, 1)[0] = size;
  new Float32Array(paramsArr, 4, 1)[0] = 1e-6;
  device.queue.writeBuffer(paramsBuf, 0, paramsArr);

  const module_ = device.createShaderModule({ code: WGSL_LAYER_BLOCK });
  const pipeline = device.createComputePipeline({
    layout: 'auto',
    compute: { module: module_, entryPoint: 'layer_block' },
  });
  const bindGroup = device.createBindGroup({
    layout: pipeline.getBindGroupLayout(0),
    entries: [
      { binding: 0, resource: { buffer: rowsBuf } },
      { binding: 1, resource: { buffer: projBuf } },
      { binding: 2, resource: { buffer: wtsBuf } },
      { binding: 3, resource: { buffer: bufOut } },
      { binding: 4, resource: { buffer: paramsBuf } },
    ],
  });

  // Chain num_layers dispatches. For layer 0, rowsBuf = initialRows.
  // For layer l>0, rowsBuf = bufOut of layer l-1 (copied on-device).
  // After all layers, copy final bufOut to staging and read back.
  const t0 = Date.now();
  const perLayerShas = [];
  let lastBuf = null;
  for (let l = 0; l < opts.numLayers; l++) {
    // Write rows for this layer. For l=0 use initialRows; for l>0
    // we already copied bufOut -> rowsBuf on the device at end of
    // the prior iteration.
    if (l === 0) {
      device.queue.writeBuffer(
        rowsBuf, 0, initialRowsF32.buffer,
        initialRowsF32.byteOffset, bytes
      );
    }
    device.queue.writeBuffer(
      projBuf, 0, perLayerInputsF32[l].buffer,
      perLayerInputsF32[l].byteOffset, bytes
    );
    device.queue.writeBuffer(
      wtsBuf, 0, perLayerInputsF32[l].buffer,
      perLayerInputsF32[l].byteOffset, bytes
    );

    const enc = device.createCommandEncoder();
    const pass = enc.beginComputePass();
    pass.setPipeline(pipeline);
    pass.setBindGroup(0, bindGroup);
    pass.dispatchWorkgroups(1);
    pass.end();
    // Copy bufOut -> rowsBuf for next layer. (For last layer this is
    // harmless; we still staging-copy after the loop.)
    if (l + 1 < opts.numLayers) {
      enc.copyBufferToBuffer(bufOut, 0, rowsBuf, 0, bytes);
    }
    device.queue.submit([enc.finish()]);

    // Optional: per-layer digest would require staging read each
    // layer. For speed, skip it and emit a single per-layer-final
    // digest at end. (If needed, add staging read here.)
    perLayerShas.push(null);
  }

  // Final staging readback of the last layer's bufOut.
  const encFinal = device.createCommandEncoder();
  encFinal.copyBufferToBuffer(bufOut, 0, stagingBuf, 0, bytes);
  device.queue.submit([encFinal.finish()]);
  await stagingBuf.mapAsync(GPUMapMode.READ);
  const mapped = stagingBuf.getMappedRange();
  const outF32 = new Float32Array(mapped.slice(0));
  stagingBuf.unmap();

  const outPath = path.join(outDir, 'activation_out.f32');
  fs.writeFileSync(outPath, Buffer.from(outF32.buffer));
  const elapsedMs = Date.now() - t0;

  const outputSha = sha256File(outPath);
  const receipt = {
    schemaVersion: 1,
    artifactKind: 'doppler_reference_export',
    manifestPath: opts.manifest,
    manifestSha256: sha256File(manifestPath),
    graphPath: opts.graph,
    graphSha256: sha256File(graphPath),
    inputTensorSha256: inputTensorSha,
    weightSha256: weightSha,
    size,
    numLayers: opts.numLayers,
    stagesCovered: ['stage1_rmsnorm', 'stage2_mha', 'stage2c_residual', 'stage3_postnorm', 'stage4_gated_mlp', 'multi_layer_chain'],
    initialRowsSeed: opts.initialRowsSeed,
    perLayerBase: opts.perLayerBase,
    runtime: 'doppler_node_webgpu',
    outputPath: path.relative(REPO_ROOT, outPath),
    outputSha256: outputSha,
    outputShape: [size],
    outputDtype: 'float32',
    elapsedMs,
    adapterInfo: {
      vendor: adapter.info?.vendor || null,
      device: adapter.info?.device || adapter.info?.description || null,
      architecture: adapter.info?.architecture || null,
    },
    runtimeContractNote: (
      'Full layer-block (all 4 stages + multi-layer chain) executed ' +
      'via Dawn-based WebGPU compute shader. Single workgroup, single ' +
      'thread — matches CSL scalar f32 in-order semantic. Expected ' +
      'drift vs scalar numpy is a few ULP per operation under driver ' +
      'FMA/vectorization/sqrt-recip; tolerance-parity gate validates ' +
      'with atol=1e-3.'
    ),
  };
  fs.writeFileSync(
    path.join(outDir, 'export_receipt.json'),
    JSON.stringify(receipt, null, 2) + '\n'
  );

  console.log(
    `Doppler Node+WebGPU layer-block export complete (${opts.numLayers} layers, ${elapsedMs}ms):` +
    `\n  out-dir: ${path.relative(REPO_ROOT, outDir)}` +
    `\n  activation_out.f32: ${outputSha.slice(0, 16)}... (${size} floats)` +
    `\n  runtime: doppler_node_webgpu (Dawn-based WebGPU via \`webgpu\` npm)` +
    `\n  adapter: ${receipt.adapterInfo.vendor}/${receipt.adapterInfo.device}` +
    `\n  stagesCovered: ${receipt.stagesCovered.join(', ')}`
  );
}

main().catch((e) => {
  console.error('FAIL:', e.stack || e.message);
  process.exit(5);
});

#!/usr/bin/env node

import { createHash } from 'node:crypto';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, '..', '..');

const VOCAB = 32;
const HIDDEN = 16;
const HEAD_DIM = HIDDEN;
const FFN = 32;
const MAX_SEQ_LEN = 16;
const PROMPT_STRING = 'The color of the sky is';
const PROMPT_IDS = [20, 3, 15, 20, 19, 9];
const PROMPT_TOKENS = PROMPT_IDS.length;
const DECODE_TOKENS = 1;

function parseArgs(argv) {
  const args = { out: 'bench/out/scratch/full-model-demo' };
  for (let i = 2; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === '--out') { args.out = argv[i + 1]; i += 1; }
    else throw new Error(`unknown arg: ${a}`);
  }
  return args;
}

function lcg(seed) {
  let s = seed >>> 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return ((s & 0xffffff) / 0xffffff) - 0.5;
  };
}

function randF32(seed, n, scale = 0.4) {
  const r = lcg(seed);
  const out = new Float32Array(n);
  for (let i = 0; i < n; i += 1) out[i] = r() * scale;
  return out;
}

function onesF32(n) {
  const out = new Float32Array(n);
  for (let i = 0; i < n; i += 1) out[i] = 1.0;
  return out;
}

function sha256Bytes(bytes) {
  return `sha256:${createHash('sha256').update(bytes).digest('hex')}`;
}

function writeFixture(root, name, typedArray, ext = 'bin') {
  const buf = Buffer.from(typedArray.buffer, typedArray.byteOffset, typedArray.byteLength);
  const path = resolve(root, `${name}.${ext}`);
  writeFileSync(path, buf);
  return { path, sha256: sha256Bytes(buf), byteLength: buf.byteLength };
}

function writeStub(path, body) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, body, 'utf-8');
  return { path, sha256: sha256Bytes(Buffer.from(body, 'utf-8')) };
}

function repoRel(p) {
  return relative(REPO_ROOT, p);
}

function makeSymbol(name, byteLength, dtype = 'f32') {
  return {
    name,
    type: dtype === 'u32' ? '[*]u32' : '[*]f32',
    mutable: true,
    kind: 'device_variable',
    byteLength,
  };
}

function memcpyOp(opId, kind, deviceSymbol, byteLength, dtype = 'MEMCPY_32BIT', nonblock = true) {
  return {
    operationId: opId,
    kind,
    targetKind: 'device_symbol',
    deviceSymbol,
    roi: { x: 0, y: 0, width: 1, height: 1 },
    elementsPerPE: byteLength / 4,
    dataType: dtype,
    order: 'ROW_MAJOR',
    streaming: false,
    nonblock,
  };
}

function launchOp(opId, target, bindings, params = {}, fnName = 'compute') {
  return {
    operationId: opId,
    kind: 'launch',
    functionName: fnName,
    args: [],
    nonblock: false,
    unblockCheckpointRequired: true,
    target,
    symbolBindings: bindings,
    extraParams: params,
  };
}

function main() {
  const args = parseArgs(process.argv);
  const outRoot = resolve(REPO_ROOT, args.out);
  const fixturesRoot = resolve(outRoot, 'fixtures');
  const compileRoot = resolve(outRoot, 'compile');
  mkdirSync(fixturesRoot, { recursive: true });
  mkdirSync(compileRoot, { recursive: true });

  const tokenIds = new Uint32Array(PROMPT_IDS);
  const fixtures = {};
  fixtures.token_ids = writeFixture(fixturesRoot, 'token_ids', tokenIds);
  fixtures.token_id_decode = writeFixture(fixturesRoot, 'token_id_decode', new Uint32Array([PROMPT_IDS[PROMPT_TOKENS - 1]]));
  fixtures.decode_position = writeFixture(fixturesRoot, 'decode_position', new Uint32Array([PROMPT_TOKENS]));
  fixtures.embed_table = writeFixture(fixturesRoot, 'embed_table', randF32(0x10, VOCAB * HIDDEN, 0.5));
  fixtures.norm1_w = writeFixture(fixturesRoot, 'norm1_w', randF32(0x21, HIDDEN, 0.05));
  fixtures.q_w = writeFixture(fixturesRoot, 'q_w', randF32(0x33, HIDDEN * HIDDEN, 0.3));
  fixtures.k_w = writeFixture(fixturesRoot, 'k_w', randF32(0x44, HIDDEN * HIDDEN, 0.3));
  fixtures.v_w = writeFixture(fixturesRoot, 'v_w', randF32(0x55, HIDDEN * HIDDEN, 0.3));
  fixtures.o_w = writeFixture(fixturesRoot, 'o_w', randF32(0x66, HIDDEN * HIDDEN, 0.3));
  fixtures.norm2_w = writeFixture(fixturesRoot, 'norm2_w', randF32(0x77, HIDDEN, 0.05));
  fixtures.up_w = writeFixture(fixturesRoot, 'up_w', randF32(0x88, HIDDEN * FFN, 0.3));
  fixtures.down_w = writeFixture(fixturesRoot, 'down_w', randF32(0x99, FFN * HIDDEN, 0.3));
  fixtures.final_norm_w = writeFixture(fixturesRoot, 'final_norm_w', randF32(0xaa, HIDDEN, 0.05));
  fixtures.lm_head_w = writeFixture(fixturesRoot, 'lm_head_w', randF32(0xbb, HIDDEN * VOCAB, 0.3));

  const stubMarker = (semantic) => {
    switch (semantic) {
      case 'gather': return '// embedding gather kernel stub\n';
      case 'rms_norm': return '// rms_norm with mean_sq and inv_rms\n';
      case 'tiled_matmul': return '// SUMMA tiled matmul stub\n';
      case 'gelu': return '// gelu approximation 0.044715 * math.tanh\n';
      case 'residual_add': return '// pe local: output[i] = input[i] + residual[i]\n';
      case 'attention_tiled': return '// tiled Flash Attention with m_state and l_state\n';
      case 'sample': return '// argmax output_token sampling\n';
      default: return '// kernel stub\n';
    }
  };

  const VIZ_PREFILL = { viz_fabric_width: PROMPT_TOKENS, viz_fabric_height: 1 };
  const VIZ_PREFILL_HIDDEN = { ...VIZ_PREFILL, viz_elements_per_pe: HIDDEN };
  const VIZ_PREFILL_FFN = { ...VIZ_PREFILL, viz_elements_per_pe: FFN };
  const VIZ_PREFILL_VOCAB = { ...VIZ_PREFILL, viz_elements_per_pe: VOCAB };

  const kernels = [
    { name: 'embed_prefill', semantic: 'gather', params: { tokens_per_chunk: PROMPT_TOKENS, hidden_per_pe: HIDDEN, rows_per_pe: VOCAB, width: 1, height: 1, ...VIZ_PREFILL_HIDDEN } },
    { name: 'norm1_prefill', semantic: 'rms_norm', params: { width: 1, height: 1, hidden_size: HIDDEN, ...VIZ_PREFILL_HIDDEN } },
    { name: 'q_proj_prefill', semantic: 'tiled_matmul', params: { width: 1, height: 1, P: 1, Mt: PROMPT_TOKENS, Kt: HIDDEN, Nt: HIDDEN, ...VIZ_PREFILL_HIDDEN } },
    { name: 'k_proj_prefill', semantic: 'tiled_matmul', params: { width: 1, height: 1, P: 1, Mt: PROMPT_TOKENS, Kt: HIDDEN, Nt: HIDDEN, ...VIZ_PREFILL_HIDDEN } },
    { name: 'v_proj_prefill', semantic: 'tiled_matmul', params: { width: 1, height: 1, P: 1, Mt: PROMPT_TOKENS, Kt: HIDDEN, Nt: HIDDEN, ...VIZ_PREFILL_HIDDEN } },
    { name: 'attn_compute_prefill', semantic: 'attention_tiled', params: { width: 1, height: 1, head_dim: HEAD_DIM, q_len_per_pe: PROMPT_TOKENS, block_size: PROMPT_TOKENS, scale: 1.0 / Math.sqrt(HEAD_DIM), ...VIZ_PREFILL_HIDDEN } },
    { name: 'kv_write_prefill', semantic: 'kv_write', params: { width: 1, height: 1, head_dim: HEAD_DIM, max_seq_len: MAX_SEQ_LEN } },
    { name: 'attn_finalize_prefill', semantic: 'attention_tiled', params: { width: 1, height: 1, head_dim: HEAD_DIM, q_len_per_pe: PROMPT_TOKENS, block_size: PROMPT_TOKENS, scale: 1.0 / Math.sqrt(HEAD_DIM), ...VIZ_PREFILL_HIDDEN } },
    { name: 'o_proj_prefill', semantic: 'tiled_matmul', params: { width: 1, height: 1, P: 1, Mt: PROMPT_TOKENS, Kt: HIDDEN, Nt: HIDDEN, ...VIZ_PREFILL_HIDDEN } },
    { name: 'attn_residual_prefill', semantic: 'residual_add', params: { width: 1, height: 1, chunk_size: PROMPT_TOKENS * HIDDEN, ...VIZ_PREFILL_HIDDEN } },
    { name: 'norm2_prefill', semantic: 'rms_norm', params: { width: 1, height: 1, hidden_size: HIDDEN, ...VIZ_PREFILL_HIDDEN } },
    { name: 'up_proj_prefill', semantic: 'tiled_matmul', params: { width: 1, height: 1, P: 1, Mt: PROMPT_TOKENS, Kt: HIDDEN, Nt: FFN, ...VIZ_PREFILL_FFN } },
    { name: 'gelu_prefill', semantic: 'gelu', params: { width: 1, height: 1, chunk_size: PROMPT_TOKENS * FFN, ...VIZ_PREFILL_FFN } },
    { name: 'down_proj_prefill', semantic: 'tiled_matmul', params: { width: 1, height: 1, P: 1, Mt: PROMPT_TOKENS, Kt: FFN, Nt: HIDDEN, ...VIZ_PREFILL_HIDDEN } },
    { name: 'ffn_residual_prefill', semantic: 'residual_add', params: { width: 1, height: 1, chunk_size: PROMPT_TOKENS * HIDDEN, ...VIZ_PREFILL_HIDDEN } },
    { name: 'final_norm_prefill', semantic: 'rms_norm', params: { width: 1, height: 1, hidden_size: HIDDEN, ...VIZ_PREFILL_HIDDEN } },
    { name: 'lm_head_prefill', semantic: 'tiled_matmul', params: { width: 1, height: 1, P: 1, Mt: PROMPT_TOKENS, Kt: HIDDEN, Nt: VOCAB, ...VIZ_PREFILL_VOCAB } },
    { name: 'sample_prefill', semantic: 'sample', params: { width: 1, chunk_size: PROMPT_TOKENS * VOCAB } },

    { name: 'embed_decode', semantic: 'gather', params: { tokens_per_chunk: 1, hidden_per_pe: HIDDEN, rows_per_pe: VOCAB, width: 1, height: 1 } },
    { name: 'norm1_decode', semantic: 'rms_norm', params: { width: 1, height: 1, hidden_size: HIDDEN } },
    { name: 'q_proj_decode', semantic: 'tiled_matmul', params: { width: 1, height: 1, P: 1, Mt: 1, Kt: HIDDEN, Nt: HIDDEN } },
    { name: 'k_proj_decode', semantic: 'tiled_matmul', params: { width: 1, height: 1, P: 1, Mt: 1, Kt: HIDDEN, Nt: HIDDEN } },
    { name: 'v_proj_decode', semantic: 'tiled_matmul', params: { width: 1, height: 1, P: 1, Mt: 1, Kt: HIDDEN, Nt: HIDDEN } },
    { name: 'kv_write_decode', semantic: 'kv_write', params: { width: 1, height: 1, head_dim: HEAD_DIM, max_seq_len: MAX_SEQ_LEN } },
    { name: 'attn_decode', semantic: 'attention_decode', params: { width: 1, height: 1, head_dim: HEAD_DIM, kv_chunk: PROMPT_TOKENS, scale: 1.0 / Math.sqrt(HEAD_DIM) } },
    { name: 'o_proj_decode', semantic: 'tiled_matmul', params: { width: 1, height: 1, P: 1, Mt: 1, Kt: HIDDEN, Nt: HIDDEN } },
    { name: 'attn_residual_decode', semantic: 'residual_add', params: { width: 1, height: 1, chunk_size: HIDDEN } },
    { name: 'norm2_decode', semantic: 'rms_norm', params: { width: 1, height: 1, hidden_size: HIDDEN } },
    { name: 'up_proj_decode', semantic: 'tiled_matmul', params: { width: 1, height: 1, P: 1, Mt: 1, Kt: HIDDEN, Nt: FFN } },
    { name: 'gelu_decode', semantic: 'gelu', params: { width: 1, height: 1, chunk_size: FFN } },
    { name: 'down_proj_decode', semantic: 'tiled_matmul', params: { width: 1, height: 1, P: 1, Mt: 1, Kt: FFN, Nt: HIDDEN } },
    { name: 'ffn_residual_decode', semantic: 'residual_add', params: { width: 1, height: 1, chunk_size: HIDDEN } },
    { name: 'final_norm_decode', semantic: 'rms_norm', params: { width: 1, height: 1, hidden_size: HIDDEN } },
    { name: 'lm_head_decode', semantic: 'tiled_matmul', params: { width: 1, height: 1, P: 1, Mt: 1, Kt: HIDDEN, Nt: VOCAB } },
    { name: 'sample_decode', semantic: 'sample', params: { width: 1, chunk_size: VOCAB } },
  ];

  const compileTargets = kernels.map((k) => {
    const layoutPath = resolve(compileRoot, k.name, 'layout.csl');
    const peProgramPath = resolve(compileRoot, k.name, 'pe_program.csl');
    writeStub(layoutPath, `// layout for ${k.name}\n${stubMarker(k.semantic)}`);
    writeStub(peProgramPath, `// pe_program for ${k.name}\n${stubMarker(k.semantic)}\nfn compute() void { sys_mod.unblock_cmd_stream(); }\n`);
    return {
      name: k.name,
      layout: { path: repoRel(layoutPath), sha256: sha256Bytes(Buffer.from(`// layout for ${k.name}\n${stubMarker(k.semantic)}`)) },
      peProgram: { path: repoRel(peProgramPath), sha256: sha256Bytes(Buffer.from(`// pe_program for ${k.name}\n${stubMarker(k.semantic)}\nfn compute() void { sys_mod.unblock_cmd_stream(); }\n`)) },
      compileParams: k.params,
    };
  });

  const symbols = {
    token_ids: { dtype: 'u32', bytes: PROMPT_TOKENS * 4 },
    token_id_decode: { dtype: 'u32', bytes: 4 },
    decode_position: { dtype: 'u32', bytes: 4 },
    embed_table: { dtype: 'f32', bytes: VOCAB * HIDDEN * 4 },
    norm1_w: { dtype: 'f32', bytes: HIDDEN * 4 },
    q_w: { dtype: 'f32', bytes: HIDDEN * HIDDEN * 4 },
    k_w: { dtype: 'f32', bytes: HIDDEN * HIDDEN * 4 },
    v_w: { dtype: 'f32', bytes: HIDDEN * HIDDEN * 4 },
    o_w: { dtype: 'f32', bytes: HIDDEN * HIDDEN * 4 },
    norm2_w: { dtype: 'f32', bytes: HIDDEN * 4 },
    up_w: { dtype: 'f32', bytes: HIDDEN * FFN * 4 },
    down_w: { dtype: 'f32', bytes: FFN * HIDDEN * 4 },
    final_norm_w: { dtype: 'f32', bytes: HIDDEN * 4 },
    lm_head_w: { dtype: 'f32', bytes: HIDDEN * VOCAB * 4 },

    x: { dtype: 'f32', bytes: PROMPT_TOKENS * HIDDEN * 4 },
    x_n: { dtype: 'f32', bytes: PROMPT_TOKENS * HIDDEN * 4 },
    q: { dtype: 'f32', bytes: PROMPT_TOKENS * HIDDEN * 4 },
    k_act: { dtype: 'f32', bytes: PROMPT_TOKENS * HIDDEN * 4 },
    v_act: { dtype: 'f32', bytes: PROMPT_TOKENS * HIDDEN * 4 },
    attn_out: { dtype: 'f32', bytes: PROMPT_TOKENS * HIDDEN * 4 },
    attn_proj: { dtype: 'f32', bytes: PROMPT_TOKENS * HIDDEN * 4 },
    x_res: { dtype: 'f32', bytes: PROMPT_TOKENS * HIDDEN * 4 },
    x_res_n: { dtype: 'f32', bytes: PROMPT_TOKENS * HIDDEN * 4 },
    up: { dtype: 'f32', bytes: PROMPT_TOKENS * FFN * 4 },
    up_g: { dtype: 'f32', bytes: PROMPT_TOKENS * FFN * 4 },
    mlp_out: { dtype: 'f32', bytes: PROMPT_TOKENS * HIDDEN * 4 },
    final_x: { dtype: 'f32', bytes: PROMPT_TOKENS * HIDDEN * 4 },
    final_x_n: { dtype: 'f32', bytes: PROMPT_TOKENS * HIDDEN * 4 },
    logits: { dtype: 'f32', bytes: PROMPT_TOKENS * VOCAB * 4 },
    tokens_out: { dtype: 'u32', bytes: 4 },

    key_cache: { dtype: 'f32', bytes: MAX_SEQ_LEN * HEAD_DIM * 4 },
    val_cache: { dtype: 'f32', bytes: MAX_SEQ_LEN * HEAD_DIM * 4 },
    x_d: { dtype: 'f32', bytes: HIDDEN * 4 },
    x_d_n: { dtype: 'f32', bytes: HIDDEN * 4 },
    q_d: { dtype: 'f32', bytes: HIDDEN * 4 },
    k_d: { dtype: 'f32', bytes: HIDDEN * 4 },
    v_d: { dtype: 'f32', bytes: HIDDEN * 4 },
    attn_out_d: { dtype: 'f32', bytes: HIDDEN * 4 },
    attn_proj_d: { dtype: 'f32', bytes: HIDDEN * 4 },
    x_res_d: { dtype: 'f32', bytes: HIDDEN * 4 },
    x_res_d_n: { dtype: 'f32', bytes: HIDDEN * 4 },
    up_d: { dtype: 'f32', bytes: FFN * 4 },
    up_d_g: { dtype: 'f32', bytes: FFN * 4 },
    mlp_out_d: { dtype: 'f32', bytes: HIDDEN * 4 },
    final_x_d: { dtype: 'f32', bytes: HIDDEN * 4 },
    final_x_d_n: { dtype: 'f32', bytes: HIDDEN * 4 },
    logits_decode: { dtype: 'f32', bytes: VOCAB * 4 },
    tokens_decode_out: { dtype: 'u32', bytes: 4 },
  };
  const exportedSymbols = Object.entries(symbols).map(([name, info]) => makeSymbol(name, info.bytes, info.dtype));

  const ops = [];
  for (const sym of ['token_ids', 'token_id_decode', 'decode_position', 'embed_table', 'norm1_w', 'q_w', 'k_w', 'v_w', 'o_w', 'norm2_w', 'up_w', 'down_w', 'final_norm_w', 'lm_head_w']) {
    ops.push(memcpyOp(`h2d-${sym}`, 'memcpy_h2d', sym, symbols[sym].bytes));
  }

  ops.push(launchOp('p1.embed', 'embed_prefill', { indices: 'token_ids', table: 'embed_table', output: 'x' }));
  ops.push(launchOp('p1.norm1', 'norm1_prefill', { input: 'x', weight: 'norm1_w', output: 'x_n' }));
  ops.push(launchOp('p1.q_proj', 'q_proj_prefill', { a: 'x_n', b: 'q_w', c: 'q' }));
  ops.push(launchOp('p1.k_proj', 'k_proj_prefill', { a: 'x_n', b: 'k_w', c: 'k_act' }));
  ops.push(launchOp('p1.v_proj', 'v_proj_prefill', { a: 'x_n', b: 'v_w', c: 'v_act' }));
  ops.push({
    operationId: 'p1.attn_compute', kind: 'launch', functionName: 'compute', args: [], nonblock: false, unblockCheckpointRequired: true,
    target: 'attn_compute_prefill', symbolBindings: { query: 'q', key: 'k_act', val: 'v_act', output: 'attn_out' },
  });
  ops.push({
    operationId: 'p1.attn_finalize', kind: 'launch', functionName: 'finalize', args: [], nonblock: false, unblockCheckpointRequired: true,
    target: 'attn_finalize_prefill', symbolBindings: { query: 'q', key: 'k_act', val: 'v_act', output: 'attn_out' },
  });
  ops.push(launchOp('p1.o_proj', 'o_proj_prefill', { a: 'attn_out', b: 'o_w', c: 'attn_proj' }));
  ops.push(launchOp('p1.attn_residual', 'attn_residual_prefill', { input: 'attn_proj', residual: 'x', output: 'x_res' }));
  ops.push(launchOp('p1.norm2', 'norm2_prefill', { input: 'x_res', weight: 'norm2_w', output: 'x_res_n' }));
  ops.push(launchOp('p1.up_proj', 'up_proj_prefill', { a: 'x_res_n', b: 'up_w', c: 'up' }));
  ops.push(launchOp('p1.gelu', 'gelu_prefill', { input: 'up', output: 'up_g' }));
  ops.push(launchOp('p1.down_proj', 'down_proj_prefill', { a: 'up_g', b: 'down_w', c: 'mlp_out' }));
  ops.push(launchOp('p1.ffn_residual', 'ffn_residual_prefill', { input: 'mlp_out', residual: 'x_res', output: 'final_x' }));
  ops.push(launchOp('p1.final_norm', 'final_norm_prefill', { input: 'final_x', weight: 'final_norm_w', output: 'final_x_n' }));
  ops.push(launchOp('p1.lm_head', 'lm_head_prefill', { a: 'final_x_n', b: 'lm_head_w', c: 'logits' }));
  ops.push(launchOp('p1.sample', 'sample_prefill', { logits: 'logits', tokens: 'tokens_out' }));

  ops.push(launchOp('d1.embed', 'embed_decode', { indices: 'token_id_decode', table: 'embed_table', output: 'x_d' }));
  ops.push(launchOp('d1.norm1', 'norm1_decode', { input: 'x_d', weight: 'norm1_w', output: 'x_d_n' }));
  ops.push(launchOp('d1.q_proj', 'q_proj_decode', { a: 'x_d_n', b: 'q_w', c: 'q_d' }));
  ops.push(launchOp('d1.k_proj', 'k_proj_decode', { a: 'x_d_n', b: 'k_w', c: 'k_d' }));
  ops.push(launchOp('d1.v_proj', 'v_proj_decode', { a: 'x_d_n', b: 'v_w', c: 'v_d' }));
  ops.push(launchOp('d1.kv_write', 'kv_write_decode', { key_proj: 'k_d', val_proj: 'v_d', key_cache: 'key_cache', val_cache: 'val_cache', position: 'decode_position' }));
  ops.push(launchOp('d1.attn', 'attn_decode', { query: 'q_d', key: 'k_act', val: 'v_act', output: 'attn_out_d', position: 'decode_position', sliding_window: 'decode_position' }));
  ops.push(launchOp('d1.o_proj', 'o_proj_decode', { a: 'attn_out_d', b: 'o_w', c: 'attn_proj_d' }));
  ops.push(launchOp('d1.attn_residual', 'attn_residual_decode', { input: 'attn_proj_d', residual: 'x_d', output: 'x_res_d' }));
  ops.push(launchOp('d1.norm2', 'norm2_decode', { input: 'x_res_d', weight: 'norm2_w', output: 'x_res_d_n' }));
  ops.push(launchOp('d1.up_proj', 'up_proj_decode', { a: 'x_res_d_n', b: 'up_w', c: 'up_d' }));
  ops.push(launchOp('d1.gelu', 'gelu_decode', { input: 'up_d', output: 'up_d_g' }));
  ops.push(launchOp('d1.down_proj', 'down_proj_decode', { a: 'up_d_g', b: 'down_w', c: 'mlp_out_d' }));
  ops.push(launchOp('d1.ffn_residual', 'ffn_residual_decode', { input: 'mlp_out_d', residual: 'x_res_d', output: 'final_x_d' }));
  ops.push(launchOp('d1.final_norm', 'final_norm_decode', { input: 'final_x_d', weight: 'final_norm_w', output: 'final_x_d_n' }));
  ops.push(launchOp('d1.lm_head', 'lm_head_decode', { a: 'final_x_d_n', b: 'lm_head_w', c: 'logits_decode' }));
  ops.push(launchOp('d1.sample', 'sample_decode', { logits: 'logits_decode', tokens: 'tokens_decode_out' }));

  ops.push(memcpyOp('d2h-logits', 'memcpy_d2h', 'logits', symbols.logits.bytes, 'MEMCPY_32BIT', false));
  ops.push(memcpyOp('d2h-tokens_out', 'memcpy_d2h', 'tokens_out', symbols.tokens_out.bytes, 'MEMCPY_32BIT', false));
  ops.push(memcpyOp('d2h-logits_decode', 'memcpy_d2h', 'logits_decode', symbols.logits_decode.bytes, 'MEMCPY_32BIT', false));
  ops.push(memcpyOp('d2h-tokens_decode_out', 'memcpy_d2h', 'tokens_decode_out', symbols.tokens_decode_out.bytes, 'MEMCPY_32BIT', false));

  const operationGraph = {
    schemaVersion: 1,
    artifactKind: 'csl_operation_graph',
    graphId: 'demo-mini-transformer',
    orchestrationMode: 'memcpy',
    executionPattern: 'rpc_launch',
    sdkVersionFloor: '2.10.0',
    compile: {
      arch: 'wse3',
      fabricDims: [16, 4],
      fabricOffsets: [4, 1],
      peGrid: { width: 1, height: 1 },
      channels: 1,
      memcpy: true,
      params: [],
      importPaths: [],
      outputDir: 'compile/compiled',
      compileTargets: compileTargets.map((t) => ({ name: t.name, layout: t.layout.path, peProgram: t.peProgram.path, compileParams: { width: 1, height: 1 } })),
    },
    exportedSymbols,
    kernelPatterns: kernels.map((k) => ({ targetName: k.name, pattern: k.semantic, count: 1 })),
    operations: ops,
  };

  const fixtureFiles = [];
  const h2dSymbols = ['token_ids', 'token_id_decode', 'decode_position', 'embed_table', 'norm1_w', 'q_w', 'k_w', 'v_w', 'o_w', 'norm2_w', 'up_w', 'down_w', 'final_norm_w', 'lm_head_w'];
  for (const sym of h2dSymbols) {
    fixtureFiles.push({
      deviceSymbol: sym,
      operationId: `h2d-${sym}`,
      path: repoRel(fixtures[sym].path),
      sha256: fixtures[sym].sha256,
      byteLength: fixtures[sym].byteLength,
    });
  }

  const input = {
    schemaVersion: 1,
    artifactKind: 'csl_webgpu_emulator_input',
    contract: 'csl_source_to_webgpu_semantic_emulation',
    claimScope: { claimable: false, summary: `Demo: prefill ${PROMPT_TOKENS} tokens of "${PROMPT_STRING}" then decode ${DECODE_TOKENS} token. Synthetic vocab=${VOCAB}, hidden=${HIDDEN}, ffn=${FFN}, layers=1. Real semantic emulator dispatches; no parity claim against Doppler reference.` },
    emulator: {
      targetSurface: 'webgpu_compute',
      hostController: 'node',
      deviceCompute: 'wgsl',
      sourceMode: 'csl_semantic_emulation',
      executionModel: 'logical_pe',
      supportedSubset: ['gather', 'rms_norm', 'gelu', 'residual_add', 'tiled_matmul', 'attention_tiled', 'sample'],
    },
    sources: {
      bundleRoot: { path: repoRel(outRoot) },
      compileRoot: { path: repoRel(compileRoot) },
      operationGraphSource: 'synthesized_inline',
    },
    compileTargets,
    operationGraph,
    operationGraphSha256: sha256Bytes(Buffer.from(JSON.stringify(operationGraph))),
    hostInputs: {
      mode: 'fixtures',
      fixtureFiles,
      notes: 'Synthetic random weights. Token IDs are arbitrary.',
    },
  };

  const inputPath = resolve(outRoot, 'demo-input.json');
  writeFileSync(inputPath, JSON.stringify(input, null, 2), 'utf-8');
  process.stderr.write(`wrote demo emulator input → ${repoRel(inputPath)}\n`);
  process.stderr.write(`compile targets: ${kernels.length}, operations: ${ops.length}, fixtures: ${fixtureFiles.length}\n`);
}

main();

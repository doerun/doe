#!/usr/bin/env node

import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';

const QK_K = 256;
const Q4K_BLOCK_BYTES = 144;

function parseArgs(argv) {
  const args = { kernel: null, out: null, params: {} };
  for (let i = 2; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];
    if (arg === '--kernel') { args.kernel = next; i += 1; }
    else if (arg === '--out') { args.out = next; i += 1; }
    else if (arg === '--param') {
      const eq = next.indexOf('=');
      if (eq < 0) throw new Error(`--param expects key=value, got ${next}`);
      const k = next.slice(0, eq);
      const v = next.slice(eq + 1);
      args.params[k] = Number.isFinite(Number(v)) ? Number(v) : v;
      i += 1;
    } else throw new Error(`unknown arg: ${arg}`);
  }
  if (!args.kernel) throw new Error('--kernel is required');
  if (!args.out) throw new Error('--out is required');
  return args;
}

function pseudoRandomF32(seed, n) {
  const out = new Float32Array(n);
  let s = seed >>> 0;
  for (let i = 0; i < n; i += 1) {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    out[i] = ((s & 0xffff) / 0xffff) - 0.5;
  }
  return out;
}

function summary(buf, base, len) {
  if (len <= 0) return { mean: 0, absMax: 0, head: [] };
  let sum = 0;
  let absMax = 0;
  for (let i = 0; i < len; i += 1) {
    const v = buf[base + i];
    sum += v;
    const a = Math.abs(v);
    if (a > absMax) absMax = a;
  }
  const headLen = Math.min(4, len);
  const head = Array.from(buf.subarray(base, base + headLen)).map((v) => Number(v.toFixed(4)));
  return { mean: Number((sum / len).toFixed(4)), absMax: Number(absMax.toFixed(4)), head };
}

function buildSummaTrace(params) {
  const P = Math.max(2, Math.min(16, Number(params.P ?? 4)));
  const Mt = Math.max(1, Number(params.Mt ?? 4));
  const Kt = Math.max(1, Number(params.Kt ?? 4));
  const Nt = Math.max(1, Number(params.Nt ?? 4));
  const peCount = P * P;
  const A = pseudoRandomF32(0xa17ec0, peCount * Mt * Kt);
  const B = pseudoRandomF32(0xb0b1e7, peCount * Kt * Nt);
  const C = new Float32Array(peCount * Mt * Nt);

  const fullInit = () => {
    const peStates = [];
    for (let py = 0; py < P; py += 1) {
      for (let px = 0; px < P; px += 1) {
        const pe = py * P + px;
        peStates.push({
          pe: [px, py],
          buffers: {
            a: summary(A, pe * Mt * Kt, Mt * Kt),
            b: summary(B, pe * Kt * Nt, Kt * Nt),
            c: summary(C, pe * Mt * Nt, Mt * Nt),
          },
        });
      }
    }
    return peStates;
  };
  const cDeltaAll = () => {
    const out = [];
    for (let py = 0; py < P; py += 1) {
      for (let px = 0; px < P; px += 1) {
        const pe = py * P + px;
        out.push({ pe: [px, py], buffers: { c: summary(C, pe * Mt * Nt, Mt * Nt) } });
      }
    }
    return out;
  };

  const phases = [];
  phases.push({ phase: 'init', label: `Initial: A and B tiles staged on each PE; C is zero`, peDelta: fullInit(), flows: [] });
  for (let step = 0; step < P; step += 1) {
    const flowsA = [];
    for (let py = 0; py < P; py += 1) {
      for (let px = 0; px < P; px += 1) {
        if (px !== step) flowsA.push({ from: [step, py], to: [px, py], buffer: 'a' });
      }
    }
    phases.push({
      phase: 'broadcast_a',
      step,
      label: `Step ${step}/${P - 1}: A column ${step} broadcasts along each row`,
      peDelta: [],
      flows: flowsA,
    });
    const flowsB = [];
    for (let py = 0; py < P; py += 1) {
      for (let px = 0; px < P; px += 1) {
        if (py !== step) flowsB.push({ from: [px, step], to: [px, py], buffer: 'b' });
      }
    }
    phases.push({
      phase: 'broadcast_b',
      step,
      label: `Step ${step}/${P - 1}: B row ${step} broadcasts along each column`,
      peDelta: [],
      flows: flowsB,
    });
    for (let py = 0; py < P; py += 1) {
      for (let px = 0; px < P; px += 1) {
        const dstPe = py * P + px;
        const cBase = dstPe * Mt * Nt;
        const aBase = (py * P + step) * Mt * Kt;
        const bBase = (step * P + px) * Kt * Nt;
        for (let i = 0; i < Mt; i += 1) {
          for (let j = 0; j < Nt; j += 1) {
            let acc = C[cBase + i * Nt + j];
            for (let k = 0; k < Kt; k += 1) {
              acc += A[aBase + i * Kt + k] * B[bBase + j * Kt + k];
            }
            C[cBase + i * Nt + j] = acc;
          }
        }
      }
    }
    phases.push({
      phase: 'fmac',
      step,
      label: `Step ${step}/${P - 1}: each PE FMACs broadcast A·B into local C`,
      peDelta: cDeltaAll(),
      flows: [],
    });
  }
  phases.push({ phase: 'done', label: `All ${P} SUMMA steps complete; C is the matmul output`, peDelta: [], flows: [] });

  return {
    schemaVersion: 1,
    artifactKind: 'csl_kernel_trace',
    kernel: {
      pattern: 'summa_tiled_matmul',
      params: { P, Mt, Kt, Nt },
      fabric: { width: P, height: P },
      buffers: ['a', 'b', 'c'],
      semantics: 'Tile-along-K SUMMA: for each step k in [0,P), broadcast A column k along rows and B row k along columns, then each PE accumulates C += A·B. Source: bench/tools/run_csl_webgpu_emulator.mjs::executeTiledMatmulCpu.',
    },
    notWhat: 'Synthetic inputs. Arithmetic shape matches the CPU reference; values are seeded for legibility, not parity vs simfabric.',
    phases,
  };
}

function buildGemvTrace(params) {
  const width = Math.max(1, Number(params.width ?? 11));
  const height = Math.max(1, Number(params.height ?? 16));
  const outDimPerPe = Math.max(1, Number(params.out_dim_per_pe ?? 8));
  const inDimPerPe = Math.max(1, Number(params.in_dim_per_pe ?? 32));
  const numBlocksPerRow = Math.max(1, Number(params.num_blocks_per_row ?? 1));
  const peCount = width * height;
  const activation = pseudoRandomF32(0xac11a7, peCount * inDimPerPe);
  const weight = new Uint8Array(peCount * outDimPerPe * numBlocksPerRow * Q4K_BLOCK_BYTES);
  for (let i = 0; i < weight.length; i += 1) {
    weight[i] = (i * 17 + 7) & 0xff;
  }
  for (let pe = 0; pe < peCount; pe += 1) {
    for (let row = 0; row < outDimPerPe; row += 1) {
      for (let block = 0; block < numBlocksPerRow; block += 1) {
        const blockBase = pe * outDimPerPe * numBlocksPerRow * Q4K_BLOCK_BYTES
          + row * numBlocksPerRow * Q4K_BLOCK_BYTES
          + block * Q4K_BLOCK_BYTES;
        weight[blockBase] = 0x00;
        weight[blockBase + 1] = 0x3c;
      }
    }
  }
  const output = new Float32Array(peCount * outDimPerPe);

  const fullSnap = () => {
    const peStates = [];
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const pe = y * width + x;
        peStates.push({
          pe: [x, y],
          buffers: {
            activation: summary(activation, pe * inDimPerPe, inDimPerPe),
            output: summary(output, pe * outDimPerPe, outDimPerPe),
          },
        });
      }
    }
    return peStates;
  };
  const peDeltaForOutput = (x, y) => {
    const pe = y * width + x;
    return [{ pe: [x, y], buffers: { output: summary(output, pe * outDimPerPe, outDimPerPe) } }];
  };

  const phases = [];
  phases.push({
    phase: 'init',
    label: `Fabric ${width}×${height} = ${peCount} PEs · ${outDimPerPe} output rows / PE · ${numBlocksPerRow} Q4K block(s) per row · ${inDimPerPe} activation lanes / PE`,
    peDelta: fullSnap(),
    flows: [],
  });

  for (let y = 0; y < height; y += 1) {
    const prefix = new Float32Array(outDimPerPe);
    for (let x = 0; x < width; x += 1) {
      const pe = y * width + x;
      const actBase = pe * inDimPerPe;
      const outBase = pe * outDimPerPe;
      const weightBase = pe * outDimPerPe * numBlocksPerRow * Q4K_BLOCK_BYTES;
      phases.push({
        phase: 'dequant',
        active: { x, y },
        label: `PE (${x},${y}) row ${y}: dequant ${numBlocksPerRow} Q4K block(s) per output row, ${outDimPerPe} rows total`,
        peDelta: [],
        flows: [],
      });
      for (let row = 0; row < outDimPerPe; row += 1) {
        let partial = 0.0;
        const rowBase = weightBase + row * numBlocksPerRow * Q4K_BLOCK_BYTES;
        for (let block = 0; block < numBlocksPerRow; block += 1) {
          const blockBase = rowBase + block * Q4K_BLOCK_BYTES;
          const scaleBits = weight[blockBase] | (weight[blockBase + 1] << 8);
          const scale = float16ToFloat32(scaleBits);
          const dataOff = blockBase + 16;
          const actOff = actBase + block * QK_K;
          const lanes = Math.min(128, Math.floor(inDimPerPe / Math.max(1, numBlocksPerRow * 2)));
          for (let i = 0; i < lanes; i += 1) {
            const byte = weight[dataOff + i];
            const a0 = activation[actOff + i * 2] ?? 0;
            const a1 = activation[actOff + i * 2 + 1] ?? 0;
            partial += ((byte & 0x0f) * scale) * a0;
            partial += ((byte >> 4) * scale) * a1;
          }
        }
        prefix[row] += partial;
        output[outBase + row] = prefix[row];
      }
      phases.push({
        phase: 'fmac',
        active: { x, y },
        label: `PE (${x},${y}): partial += dequant · activation, accumulated into prefix and written to local output`,
        peDelta: peDeltaForOutput(x, y),
        flows: [],
      });
      if (x < width - 1) {
        phases.push({
          phase: 'row_reduce',
          active: { x, y },
          label: `Row ${y}: prefix flows from (${x},${y}) → (${x + 1},${y}) along the collectives_2d row reduce`,
          peDelta: [],
          flows: [{ from: [x, y], to: [x + 1, y], buffer: 'partial' }],
        });
      }
    }
    phases.push({
      phase: 'row_done',
      active: { x: width - 1, y },
      label: `Row ${y} complete; output[(${width - 1},${y})] holds the row's reduction`,
      peDelta: peDeltaForOutput(width - 1, y),
      flows: [],
    });
  }
  phases.push({
    phase: 'done',
    label: 'All rows complete; GEMV output is final',
    peDelta: [],
    flows: [],
  });

  return {
    schemaVersion: 1,
    artifactKind: 'csl_kernel_trace',
    kernel: {
      pattern: 'fused_gemv_dequant',
      params: { width, height, out_dim_per_pe: outDimPerPe, in_dim_per_pe: inDimPerPe, num_blocks_per_row: numBlocksPerRow },
      fabric: { width, height },
      buffers: ['activation', 'weight', 'output'],
      semantics: 'Per-row GEMV with Q4K weights dequanted on-PE: for each row y, sweep PEs (0..width-1, y), compute per-PE partial = sum(dequant·activation) per output row, accumulate into the row prefix, and reduce along x via collectives_2d. Source: bench/tools/run_csl_webgpu_emulator.mjs::executeFusedGemvDequantCpu.',
    },
    notWhat: 'Synthetic activation and synthetic Q4K weights. Reduction order matches the CPU reference; values are seeded for legibility, not parity vs simfabric.',
    phases,
  };
}

function float16ToFloat32(bits) {
  const sign = (bits & 0x8000) ? -1 : 1;
  const exponent = (bits >> 10) & 0x1f;
  const fraction = bits & 0x03ff;
  if (exponent === 0) return sign * Math.pow(2, -14) * (fraction / 1024);
  if (exponent === 31) return fraction === 0 ? sign * Infinity : NaN;
  return sign * Math.pow(2, exponent - 15) * (1 + fraction / 1024);
}

function main() {
  const args = parseArgs(process.argv);
  let trace;
  if (args.kernel === 'summa_tiled_matmul') trace = buildSummaTrace(args.params);
  else if (args.kernel === 'fused_gemv_dequant') trace = buildGemvTrace(args.params);
  else throw new Error(`unsupported kernel pattern: ${args.kernel}; supported: summa_tiled_matmul, fused_gemv_dequant`);
  mkdirSync(dirname(args.out), { recursive: true });
  writeFileSync(args.out, JSON.stringify(trace));
  process.stderr.write(`wrote ${trace.phases.length} phases for ${args.kernel} → ${args.out}\n`);
}

main();

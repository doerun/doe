#!/usr/bin/env node
// Dispatch one WGSL compute shader through Doe's Node WebGPU runtime,
// using fixture inputs from a TSIR bootstrap-input JSON, and write
// the sha256 of the output buffer to a hash file.
//
// Used by bench/tools/doe_parity.py:run_backend("webgpu", ...) to
// produce a real backend hash for the parity comparison's WebGPU
// lane (Task 4 in docs/cerebras-north-star.md remaining gaps).
//
// Scope: supports compute shaders with @group(0) bindings where
// inputs are read-only storage buffers, an optional uniform buffer,
// and exactly one read_write storage buffer (treated as the output).
// Workgroup count is computed from the fixture inputs' largest
// dimension or from the uniform's `hidden_size` field if present.
// More structured kernel metadata can be added later if needed.

import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, '..', '..');
const DOE_NODE_WEBGPU_PATH = resolve(REPO_ROOT, 'packages/doe-gpu/src/node-webgpu.js');
const BYTES_PER_SCALAR = 4;
const UNIFORM_ALIGNMENT_BYTES = 16;

function parseArgs(argv) {
  const args = {
    wgslPath: null,
    inputsPath: null,
    outputHashOutPath: null,
    entryPoint: 'main',
    workgroupSizeX: 64,
    expectedOutputElements: null,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];
    switch (arg) {
      case '--wgsl':
        args.wgslPath = next;
        i += 1;
        break;
      case '--inputs':
        args.inputsPath = next;
        i += 1;
        break;
      case '--output-hash-out':
        args.outputHashOutPath = next;
        i += 1;
        break;
      case '--entry-point':
        args.entryPoint = next;
        i += 1;
        break;
      case '--workgroup-size-x':
        args.workgroupSizeX = Number(next);
        i += 1;
        break;
      case '--expected-output-elements': {
        const n = Number(next);
        if (!Number.isInteger(n) || n < 1) {
          throw new Error('--expected-output-elements must be a positive integer');
        }
        args.expectedOutputElements = n;
        i += 1;
        break;
      }
      default:
        throw new Error(`unrecognized argument: ${arg}`);
    }
  }
  if (!args.wgslPath) throw new Error('--wgsl is required');
  if (!args.inputsPath) throw new Error('--inputs is required');
  if (!args.outputHashOutPath) {
    throw new Error('--output-hash-out is required');
  }
  return args;
}

function reflectBindings(wgsl) {
  // Match @group(N) @binding(M) var<storage|uniform, mode?> name : type
  const bindingRe = /@group\((\d+)\)\s+@binding\((\d+)\)\s+var<\s*([a-z]+)\s*(?:,\s*([a-z_]+)\s*)?>\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([^;]+);/g;
  const bindings = [];
  let match;
  while ((match = bindingRe.exec(wgsl)) !== null) {
    const [, group, binding, addressSpace, accessMode, name, type] = match;
    bindings.push({
      group: Number(group),
      binding: Number(binding),
      addressSpace,
      accessMode: accessMode || (addressSpace === 'uniform' ? 'read' : 'read'),
      name,
      type: type.trim(),
    });
  }
  return bindings;
}

function parseFixtureInputs(inputsJsonPath) {
  const text = readFileSync(inputsJsonPath, 'utf-8');
  const doc = JSON.parse(text);
  if (!doc.kernel || typeof doc.kernel !== 'string') {
    throw new Error(`fixture missing string 'kernel': ${inputsJsonPath}`);
  }
  if (!doc.inputs || typeof doc.inputs !== 'object') {
    throw new Error(`fixture missing 'inputs' object: ${inputsJsonPath}`);
  }
  return { kernel: doc.kernel, inputs: doc.inputs };
}

function packStorageBuffer(values, elem) {
  if (elem === 'f32') {
    const buf = new Float32Array(values.length);
    for (let i = 0; i < values.length; i += 1) buf[i] = values[i];
    return buf.buffer;
  }
  if (elem === 'u32') {
    const buf = new Uint32Array(values.length);
    for (let i = 0; i < values.length; i += 1) buf[i] = values[i];
    return buf.buffer;
  }
  if (elem === 'i32') {
    const buf = new Int32Array(values.length);
    for (let i = 0; i < values.length; i += 1) buf[i] = values[i];
    return buf.buffer;
  }
  throw new Error(`unsupported storage elem type: ${elem}`);
}

function normalizedKernelName(kernel) {
  if (kernel === 'rmsnorm' || kernel === 'rms-norm') return 'rms_norm';
  if (kernel === 'fused-gemv') return 'fused_gemv';
  return kernel;
}

function shapeProduct(shape) {
  if (!Array.isArray(shape) || shape.length === 0) return 0;
  return shape.reduce((a, b) => a * b, 1);
}

function requireShape(inputs, name, dims) {
  const entry = inputs[name];
  if (!entry || !Array.isArray(entry.shape) || entry.shape.length !== dims) {
    throw new Error(`fixture input '${name}' must have rank-${dims} shape`);
  }
  return entry.shape;
}

function inferUniformValues(kernel, uniformName, fixtureInputs) {
  const normalized = normalizedKernelName(kernel);
  if (uniformName !== 'u') return null;
  if (normalized === 'fused_gemv') {
    const [m, k] = requireShape(fixtureInputs, 'W', 2);
    const xShape = requireShape(fixtureInputs, 'x', 1);
    if (xShape[0] !== k) {
      throw new Error(`fused_gemv fixture shape mismatch: W.K=${k}, x=${xShape[0]}`);
    }
    return { M: m, K: k };
  }
  if (normalized === 'gather') {
    const [numTokens] = requireShape(fixtureInputs, 'indices', 1);
    const [vocab, hidden] = requireShape(fixtureInputs, 'table', 2);
    return { num_tokens: numTokens, hidden, vocab };
  }
  if (normalized === 'rms_norm') {
    const [hiddenSize] = requireShape(fixtureInputs, 'input', 1);
    const weightShape = requireShape(fixtureInputs, 'weight', 1);
    if (weightShape[0] !== hiddenSize) {
      throw new Error(`rms_norm fixture shape mismatch: input=${hiddenSize}, weight=${weightShape[0]}`);
    }
    const explicit = fixtureInputs[uniformName];
    const eps = Array.isArray(explicit?.values) && explicit.values.length >= 2
      ? explicit.values[1]
      : 1.0e-5;
    return { hidden_size: hiddenSize, eps };
  }
  return null;
}

function reflectStructFields(wgsl, structName) {
  const escapedName = structName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const structRe = new RegExp(`struct\\s+${escapedName}\\s*\\{([\\s\\S]*?)\\};?`, 'm');
  const match = structRe.exec(wgsl);
  if (!match) return [];
  const fieldRe = /([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([A-Za-z0-9_<>]+)\s*,?/g;
  const fields = [];
  let fieldMatch;
  while ((fieldMatch = fieldRe.exec(match[1])) !== null) {
    fields.push({ name: fieldMatch[1], type: fieldMatch[2] });
  }
  return fields;
}

function uniformValueByField(uniformInputs, fields) {
  if (Array.isArray(uniformInputs?.values)) {
    const values = {};
    for (let i = 0; i < fields.length; i += 1) {
      values[fields[i].name] = uniformInputs.values[i];
    }
    return values;
  }
  if (uniformInputs && typeof uniformInputs === 'object') {
    return uniformInputs;
  }
  return null;
}

function packUniformBuffer(uniformInputs, fields) {
  if (!fields || fields.length === 0) {
    throw new Error('cannot pack uniform buffer without reflected struct fields');
  }
  const byteLength = Math.max(
    UNIFORM_ALIGNMENT_BYTES,
    Math.ceil((fields.length * BYTES_PER_SCALAR) / UNIFORM_ALIGNMENT_BYTES) *
      UNIFORM_ALIGNMENT_BYTES,
  );
  const buf = new ArrayBuffer(byteLength);
  const view = new DataView(buf);
  for (let i = 0; i < fields.length; i += 1) {
    const field = fields[i];
    const value = uniformInputs[field.name];
    if (typeof value !== 'number') {
      throw new Error(`uniform field '${field.name}' must be numeric`);
    }
    const offset = i * BYTES_PER_SCALAR;
    if (field.type === 'u32') {
      view.setUint32(offset, value, true);
    } else if (field.type === 'i32') {
      view.setInt32(offset, value, true);
    } else if (field.type === 'f32') {
      view.setFloat32(offset, value, true);
    } else {
      throw new Error(`unsupported uniform field type: ${field.type}`);
    }
  }
  return buf;
}

function uniformPayloadForBinding(kernel, wgsl, binding, fixtureInputs) {
  const fields = reflectStructFields(wgsl, binding.type);
  const inferred = inferUniformValues(kernel, binding.name, fixtureInputs);
  if (inferred) return packUniformBuffer(inferred, fields);
  const explicit = uniformValueByField(fixtureInputs[binding.name], fields);
  if (!explicit) {
    throw new Error(`fixture missing uniform for binding '${binding.name}'`);
  }
  return packUniformBuffer(explicit, fields);
}

function deriveOutputElementCount(kernel, fixtureInputs) {
  const normalized = normalizedKernelName(kernel);
  if (normalized === 'fused_gemv') {
    return requireShape(fixtureInputs, 'W', 2)[0];
  }
  if (normalized === 'gather') {
    const [numTokens] = requireShape(fixtureInputs, 'indices', 1);
    const [, hidden] = requireShape(fixtureInputs, 'table', 2);
    return numTokens * hidden;
  }
  if (normalized === 'rms_norm') {
    return requireShape(fixtureInputs, 'input', 1)[0];
  }
  let maxElementCount = 0;
  for (const [, v] of Object.entries(fixtureInputs)) {
    maxElementCount = Math.max(maxElementCount, shapeProduct(v?.shape));
  }
  return maxElementCount || 4;
}

function deriveWorkgroupDims(kernel, fixtureInputs, fallbackSize) {
  const normalized = normalizedKernelName(kernel);
  if (normalized === 'gather') {
    const [numTokens] = requireShape(fixtureInputs, 'indices', 1);
    const [, hidden] = requireShape(fixtureInputs, 'table', 2);
    return [Math.max(1, Math.ceil(hidden / fallbackSize)), Math.max(1, numTokens), 1];
  }
  const outputElements = deriveOutputElementCount(normalized, fixtureInputs);
  return [Math.max(1, Math.ceil(outputElements / fallbackSize)), 1, 1];
}

function outputByteLength(kernel, fixtureInputs) {
  return Math.max(BYTES_PER_SCALAR, deriveOutputElementCount(kernel, fixtureInputs) * BYTES_PER_SCALAR);
}

function packUniformBufferLegacy(uniformInputs, deviceLimits) {
  if (deviceLimits) {
    // Preserve the parameter to keep older call sites obvious during review.
  }
  if (!uniformInputs || typeof uniformInputs !== 'object') {
    throw new Error('uniform inputs must be an object');
  }
  if (Array.isArray(uniformInputs.values)) {
    return packStorageBuffer(uniformInputs.values, uniformInputs.elem || 'f32');
  }
  const words = [];
  for (const [, value] of Object.entries(uniformInputs)) {
    if (typeof value !== 'number') {
      throw new Error('uniform fields must be scalars');
    }
    words.push(value);
  }
  const buf = new Float32Array(words);
  return buf.buffer;
}

function packStorageBufferLegacy(values, elem) {
  if (elem !== 'f32') {
    throw new Error(`unsupported storage elem type: ${elem}`);
  }
  const buf = new Float32Array(values.length);
  for (let i = 0; i < values.length; i += 1) buf[i] = values[i];
  return buf.buffer;
}

function pickOutputBinding(bindings, fixtureInputs) {
  // Output = single read_write storage binding not present in fixture inputs.
  const writable = bindings.filter((b) => (
    b.addressSpace === 'storage' && b.accessMode === 'read_write'
  ));
  if (writable.length === 0) {
    throw new Error('no read_write storage binding found (no output)');
  }
  // If exactly one, that's the output.
  if (writable.length === 1) return writable[0];
  // Otherwise, prefer one whose name is not in fixtureInputs.
  for (const b of writable) {
    if (!(b.name in fixtureInputs)) return b;
  }
  throw new Error(
    `cannot disambiguate output binding among: ${writable.map((b) => b.name).join(', ')}`,
  );
}

async function main() {
  const args = parseArgs(process.argv);
  const wgslAbs = resolve(args.wgslPath);
  const inputsAbs = resolve(args.inputsPath);
  const outHashAbs = resolve(args.outputHashOutPath);

  if (!existsSync(wgslAbs)) {
    throw new Error(`WGSL file not found: ${wgslAbs}`);
  }
  if (!existsSync(inputsAbs)) {
    throw new Error(`inputs JSON not found: ${inputsAbs}`);
  }

  const wgslSource = readFileSync(wgslAbs, 'utf-8');
  const { kernel, inputs } = parseFixtureInputs(inputsAbs);
  const bindings = reflectBindings(wgslSource);
  if (bindings.length === 0) {
    throw new Error('WGSL has no @group/@binding declarations');
  }

  // Install the Doe-owned Node WebGPU provider. If no usable provider is
  // available, surface the error so doe_parity.py records a typed failure.
  let bootstrapNodeWebGPU;
  try {
    const mod = await import(pathToFileURL(DOE_NODE_WEBGPU_PATH).href);
    bootstrapNodeWebGPU = mod.bootstrapNodeWebGPU;
  } catch (err) {
    throw new Error(
      `cannot load Doe Node WebGPU bootstrap: ${err && err.message ? err.message : err}`,
    );
  }
  if (typeof bootstrapNodeWebGPU !== 'function') {
    throw new Error('Doe Node WebGPU bootstrap does not export bootstrapNodeWebGPU()');
  }
  const bootstrap = await bootstrapNodeWebGPU();
  if (!bootstrap?.ok) {
    throw new Error(`Doe Node WebGPU bootstrap failed: ${bootstrap?.detail ?? 'unknown error'}`);
  }
  if (!globalThis.navigator?.gpu) {
    throw new Error('Doe Node WebGPU bootstrap did not install navigator.gpu');
  }
  const gpu = globalThis.navigator.gpu;
  const adapter = await gpu.requestAdapter();
  if (!adapter) throw new Error('no WebGPU adapter');
  const device = await adapter.requestDevice();

  const module = device.createShaderModule({ code: wgslSource });
  const pipeline = device.createComputePipeline({
    layout: 'auto',
    compute: { module, entryPoint: args.entryPoint },
  });

  const outBinding = pickOutputBinding(bindings, inputs);
  const bindGroupEntries = [];
  let outputBuffer = null;
  let outputBytes = 0;

  for (const b of bindings) {
    if (b.name === outBinding.name) {
      // Caller (e.g. doe_parity reading the transcript's
      // kernelProbe.outputElementCount) overrides the inferred output
      // size. Inference falls back to the kernel-specific path when
      // the override is absent. This decouples the dispatcher from
      // having to learn every new kernel's output-shape rule — the
      // transcript already declares it.
      const overrideElements = args.expectedOutputElements;
      outputBytes = overrideElements != null
        ? Math.max(BYTES_PER_SCALAR, overrideElements * BYTES_PER_SCALAR)
        : outputByteLength(kernel, inputs);
      outputBuffer = device.createBuffer({
        size: outputBytes,
        usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_SRC,
      });
      bindGroupEntries.push({
        binding: b.binding,
        resource: { buffer: outputBuffer },
      });
      continue;
    }
    if (b.addressSpace === 'storage') {
      const fixtureEntry = inputs[b.name];
      if (!fixtureEntry) {
        throw new Error(`fixture missing input for binding '${b.name}'`);
      }
      const arr = packStorageBuffer(fixtureEntry.values, fixtureEntry.elem || 'f32');
      const buf = device.createBuffer({
        size: arr.byteLength,
        usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST,
      });
      device.queue.writeBuffer(buf, 0, arr);
      bindGroupEntries.push({ binding: b.binding, resource: { buffer: buf } });
      continue;
    }
    if (b.addressSpace === 'uniform') {
      const arr = uniformPayloadForBinding(kernel, wgslSource, b, inputs);
      const buf = device.createBuffer({
        size: arr.byteLength,
        usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
      });
      device.queue.writeBuffer(buf, 0, arr);
      bindGroupEntries.push({ binding: b.binding, resource: { buffer: buf } });
      continue;
    }
    throw new Error(`unsupported address space: ${b.addressSpace}`);
  }

  const bindGroup = device.createBindGroup({
    layout: pipeline.getBindGroupLayout(0),
    entries: bindGroupEntries,
  });

  const [workgroupCountX, workgroupCountY, workgroupCountZ] = deriveWorkgroupDims(
    kernel,
    inputs,
    args.workgroupSizeX,
  );
  const encoder = device.createCommandEncoder();
  const pass = encoder.beginComputePass();
  pass.setPipeline(pipeline);
  pass.setBindGroup(0, bindGroup);
  pass.dispatchWorkgroups(workgroupCountX, workgroupCountY, workgroupCountZ);
  pass.end();

  if (!outputBuffer) throw new Error('no output buffer was created');
  const readback = device.createBuffer({
    size: outputBytes,
    usage: GPUBufferUsage.MAP_READ | GPUBufferUsage.COPY_DST,
  });
  encoder.copyBufferToBuffer(outputBuffer, 0, readback, 0, outputBytes);
  device.queue.submit([encoder.finish()]);
  await readback.mapAsync(GPUMapMode.READ);
  const view = new Uint8Array(readback.getMappedRange().slice(0));
  readback.unmap();

  const hash = createHash('sha256').update(view).digest('hex');
  const outDir = dirname(outHashAbs);
  if (!existsSync(outDir)) mkdirSync(outDir, { recursive: true });
  writeFileSync(outHashAbs, `${hash}\n`, 'utf-8');
  process.stdout.write(`OK ${hash}\n`);
}

main().catch((err) => {
  process.stderr.write(`FAIL ${err && err.message ? err.message : err}\n`);
  process.exit(1);
});

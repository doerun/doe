// Trust, ABI and ownership checks for the shipped browser compiler artifact.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { compilerArtifact } from '../../src/browser-compiler-artifact.js';
import { sha256, acquireCompilerBytes } from '../../src/browser-compiler-cache.js';
import { createDoeCompiler, createDoeShaderAdapter } from '../../src/browser-compiler.js';
import { createParticleSession } from '../../examples/browser-compiler/benchmark.js';

const bytes = await readFile(new URL(`../../assets/${compilerArtifact.asset}`, import.meta.url));
assert.equal(await sha256(bytes), compilerArtifact.sha256);
assert.equal(bytes.length, compilerArtifact.byteLength);
const module = await WebAssembly.compile(bytes);
assert.deepEqual(WebAssembly.Module.imports(module), []);
const { exports: wasm } = await WebAssembly.instantiate(module);
function compile(source, enabled = true) {
  const encoded = new TextEncoder().encode(source);
  const input = wasm.reserve_source(encoded.length);
  assert(input);
  new Uint8Array(wasm.memory.buffer, input, encoded.length).set(encoded);
  const output = wasm.compile(encoded.length, Number(enabled));
  assert(output);
  const result = JSON.parse(new TextDecoder().decode(
    new Uint8Array(wasm.memory.buffer, output, wasm.output_length())));
  wasm.release_job();
  return result;
}
const source = 'fn f(x: u32) -> u32 { return x / 8u + x % 4u; }';
assert.equal(compile(source).rewrites, 2);
assert.equal(compile(source, false).wgsl, source);
const failure = compile('fn alias() {}');
assert.equal(failure.ok, false);
assert.equal(failure.diagnostic.byteOffset, 3);
for (let index = 0; index < 300; index++) assert(compile(source).ok);
wasm.release_job();
assert.equal(wasm.output_length(), 0);
assert.equal(wasm.reserve_source(wasm.source_limit() + 1), 0);
assert.equal(wasm.reserve_source(0), 0);
assert.equal(wasm.compile(0, 2), 0);
assert.throws(() => wasm.memory.grow(1024));

const originalFetch = globalThis.fetch;
let downloads = 0;
globalThis.fetch = async () => {
  downloads++;
  return new Response(bytes);
};
const artifact = { url: 'https://example.invalid/compiler.wasm',
  sha256: compilerArtifact.sha256, byteLength: bytes.length, cache: false };
try {
  const acquired = await acquireCompilerBytes(artifact);
  assert.equal(acquired.cacheStatus, 'disabled');
  assert.equal(acquired.bytesDownloaded, bytes.length);
  await assert.rejects(acquireCompilerBytes({ ...artifact, sha256: '0'.repeat(64) }), /digest mismatch/);
  await assert.rejects(acquireCompilerBytes({ ...artifact, byteLength: bytes.length - 1 }), /byte budget/);
  await assert.rejects(acquireCompilerBytes({ ...artifact, byteLength: bytes.length + 1 }), /size mismatch/);
  await assert.rejects(acquireCompilerBytes({ ...artifact, sha256: 'untrusted' }), /trusted SHA/);
  const navigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
  let aborted = false;
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: {
    storage: { async getDirectory() { return {
      async getDirectoryHandle() { return {
        async getFileHandle(name, options) {
          if (!options?.create) throw new DOMException('Absent cache', 'NotFoundError');
          return { async createWritable() { return {
            async write() { throw new DOMException('Quota exhausted', 'QuotaExceededError'); },
            async abort() { aborted = true; },
          }; } };
        },
      }; },
    }; } },
  } });
  try {
    const quota = await acquireCompilerBytes({ ...artifact, cache: true });
    assert.equal(quota.cacheStatus, 'miss-write-failed:QuotaExceededError');
    assert.equal(await sha256(quota.bytes), artifact.sha256);
    assert(aborted);
  } finally {
    Object.defineProperty(globalThis, 'navigator', navigatorDescriptor);
  }
} finally {
  globalThis.fetch = originalFetch;
}
assert.equal(downloads, 5);

const originalWorker = globalThis.Worker;
const originalLocation = globalThis.location;
let worker;
let transmissions = 0;
let completeCompile = false;
globalThis.location = { href: 'https://example.invalid/application/' };
globalThis.Worker = class {
  constructor() { worker = this; }
  postMessage(message) {
    transmissions++;
    if (message.kind === 'init') queueMicrotask(() => this.onmessage({ data: {
      id: message.id, value: { sourceLimit: 65536 },
    } }));
    if (message.kind === 'compile' && completeCompile) queueMicrotask(() => this.onmessage({ data: {
      id: message.id, value: { wgsl: message.code },
    } }));
  }
  terminate() { this.terminated = true; }
};
try {
  const opening = createDoeCompiler({ artifact });
  const expectedDigest = artifact.sha256;
  artifact.sha256 = '0'.repeat(64);
  const compiler = await opening;
  assert.equal(compiler.identity.sha256, expectedDigest);
  artifact.sha256 = expectedDigest;
  const beforeRejected = transmissions;
  await assert.rejects(compiler.compile('x'.repeat(65537), { optimize: true }), /source budget/);
  await assert.rejects(compiler.compile('é'.repeat(32769), { optimize: true }), /source budget/);
  assert.equal(transmissions, beforeRejected, 'Oversized UTF-8 must not reach postMessage');
  completeCompile = true;
  for (const text of ['x'.repeat(65535), 'x'.repeat(65536), 'é'.repeat(32768), source]) {
    assert.equal((await compiler.compile(text, { optimize: false })).wgsl, text);
  }
  assert.equal(transmissions, beforeRejected + 4);
  completeCompile = false;
  const pending = compiler.compile(source, { optimize: true });
  await assert.rejects(compiler.compile(source, { optimize: false }), /pending work/);
  compiler.close();
  compiler.close();
  await assert.rejects(pending, /closed/);
  assert(worker.terminated);
  await assert.rejects(compiler.compile(source, { optimize: true }), /closed/);
  const deadline = await createDoeCompiler({ artifact, timeoutMs: 1 });
  await assert.rejects(deadline.compile(source, { optimize: true }), /deadline exceeded/);
  assert(worker.terminated);
  let creates = 0;
  const adapter = createDoeShaderAdapter({
    device: { createShaderModule({ code }) {
      creates++;
      assert.equal(code, 'emitted');
      return { async getCompilationInfo() { return { messages: [] }; } };
    } },
    compiler: { async compile(code, { optimize }) {
      assert.equal(code, source);
      assert.equal(optimize, true);
      return { wgsl: 'emitted', rewrites: 2 };
    } }, optimize: true,
  });
  await adapter.createShaderModule({ code: source });
  assert.equal(adapter.executionOwner, 'browser');
  assert.equal(creates, 1);
} finally {
  globalThis.Worker = originalWorker;
  globalThis.location = originalLocation;
}
console.log('ok: browser compiler digest, ABI, memory bound, close, deadline and adapter contract');

const originalUsage = globalThis.GPUBufferUsage;
globalThis.GPUBufferUsage = { STORAGE: 1, COPY_DST: 2, COPY_SRC: 4, UNIFORM: 8, MAP_READ: 16 };
let allocations = 0;
let destroyed = 0;
let scopes = 0;
const allocationFailure = new Error('Injected allocation failure');
const fakeDevice = {
  pushErrorScope() { scopes++; },
  async popErrorScope() { scopes--; return null; },
  createShaderModule() { return { async getCompilationInfo() { return { messages: [] }; } }; },
  async createComputePipelineAsync() { return {}; },
  async createRenderPipelineAsync() { return {}; },
  createBuffer({ size }) {
    if (++allocations === 3) throw allocationFailure;
    return { size, destroy() { destroyed++; } };
  },
  queue: { writeBuffer() {} },
};
try {
  await assert.rejects(createParticleSession({ device: fakeDevice, mode: 'browser', code: source,
    initial: new Float32Array(16), format: 'rgba8unorm', contract: { dt: 1 / 64 } }),
  (error) => error === allocationFailure);
  assert.equal(destroyed, 2);
  assert.equal(scopes, 0);
} finally {
  globalThis.GPUBufferUsage = originalUsage;
}
console.log('ok: failed session allocation releases owned buffers and retains the original cause');

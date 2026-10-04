// One isolated compiler instance; no GPU handles or native host imports.
import { acquireCompilerBytes } from './browser-compiler-cache.js';

let compiler;
let busy = false;
const encoder = new TextEncoder();
const decoder = new TextDecoder('utf-8', { fatal: true });

self.onmessage = async ({ data }) => {
  const { id, kind } = data;
  if (busy) {
    self.postMessage({ id, error: { message: 'Compiler Worker is busy' } });
    return;
  }
  busy = true;
  try {
    if (kind === 'init') {
      if (compiler) throw new Error('Compiler already initialized');
      const acquired = await acquireCompilerBytes(data.artifact);
      const started = performance.now();
      const { instance } = await WebAssembly.instantiate(acquired.bytes, {});
      compiler = instance.exports;
      self.postMessage({ id, value: {
        ...acquired.timings,
        instantiateMs: performance.now() - started,
        cacheStatus: acquired.cacheStatus,
        bytesDownloaded: acquired.bytesDownloaded,
        sourceLimit: compiler.source_limit(),
      } });
    } else if (kind === 'compile') {
      if (!compiler) throw new Error('Compiler not initialized');
      if (typeof data.code !== 'string' || typeof data.optimize !== 'boolean') {
        throw new TypeError('WGSL text and explicit optimize boolean are required');
      }
      if (data.code.length > compiler.source_limit()) {
        throw new RangeError('WGSL exceeds the compiler source budget');
      }
      const source = encoder.encode(data.code);
      if (source.length === 0 || source.length > compiler.source_limit()) {
        throw new RangeError('WGSL exceeds the compiler source budget');
      }
      const started = performance.now();
      try {
        const input = compiler.reserve_source(source.length);
        if (!input) throw new Error('Compiler input allocation failed');
        new Uint8Array(compiler.memory.buffer, input, source.length).set(source);
        const output = compiler.compile(source.length, Number(data.optimize));
        const length = compiler.output_length();
        if (!output || !length) throw new Error('Compiler output allocation failed');
        const value = JSON.parse(decoder.decode(
          new Uint8Array(compiler.memory.buffer, output, length)));
        if (value.schemaVersion !== 1) throw new Error('Unsupported compiler response');
        if (!value.ok) {
          const error = new Error(value.diagnostic.message);
          error.diagnostic = value.diagnostic;
          throw error;
        }
        self.postMessage({ id, value: { ...value, compileMs: performance.now() - started } });
      } finally {
        compiler.release_job();
      }
    } else {
      throw new Error('Unsupported compiler request');
    }
  } catch (error) {
    self.postMessage({ id, error: {
      name: error.name, message: error.message, diagnostic: error.diagnostic ?? null,
    } });
  } finally {
    busy = false;
  }
};

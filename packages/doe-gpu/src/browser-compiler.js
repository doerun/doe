// doe-gpu/browser-compiler — explicitly injected Doe-assisted WebGPU.

/** Create one Worker-owned compiler. The application pins artifact.sha256. */
export async function createDoeCompiler({ artifact, cache = true, timeoutMs = 30000 } = {}) {
  if (!artifact || !Number.isFinite(timeoutMs) || timeoutMs <= 0) {
    throw new TypeError('A pinned compiler artifact and positive timeoutMs are required');
  }
  const pinned = Object.freeze({
    url: new URL(artifact.url, globalThis.location.href).href,
    sha256: artifact.sha256, byteLength: artifact.byteLength,
  });
  const worker = new Worker(new URL('./browser-compiler-worker.js', import.meta.url),
    { type: 'module', name: 'Doe WGSL compiler' });
  let pending = null;
  let closed = false;
  let sequence = 0;
  function close(reason = new Error('Doe compiler closed')) {
    if (closed) return;
    closed = true;
    worker.terminate();
    if (pending) {
      const current = pending;
      pending = null;
      clearTimeout(current.timer);
      current.reject(reason);
    }
  }
  worker.onerror = (event) => close(new Error(event.message || 'Compiler Worker failed'));
  worker.onmessage = ({ data }) => {
    if (!pending || pending.id !== data.id) return;
    const current = pending;
    pending = null;
    clearTimeout(current.timer);
    if (data.error) {
      const error = new Error(data.error.message);
      error.name = data.error.name ?? 'Error';
      error.diagnostic = data.error.diagnostic;
      current.reject(error);
    } else {
      current.resolve(data.value);
    }
  };
  function request(kind, values) {
    if (closed) return Promise.reject(new Error('Doe compiler closed'));
    if (pending) return Promise.reject(new Error('Doe compiler already has pending work'));
    return new Promise((resolve, reject) => {
      const id = ++sequence;
      const timer = setTimeout(() => close(new Error('Doe compiler deadline exceeded')), timeoutMs);
      pending = { id, resolve, reject, timer };
      try {
        worker.postMessage({ id, kind, ...values });
      } catch (error) {
        close(error);
      }
    });
  }
  const started = performance.now();
  let initialization;
  try {
    initialization = await request('init', {
      artifact: { ...pinned, cache },
    });
  } catch (error) {
    close(error);
    throw error;
  }
  return Object.freeze({
    identity: Object.freeze({ label: 'Doe-assisted WebGPU', sha256: pinned.sha256 }),
    initialization: Object.freeze({ ...initialization, totalMs: performance.now() - started }),
    compile(code, { optimize } = {}) {
      if (typeof code !== 'string' || typeof optimize !== 'boolean') {
        return Promise.reject(new TypeError('WGSL text and an explicit optimize boolean are required'));
      }
      if (code.length > initialization.sourceLimit
          || new TextEncoder().encode(code).byteLength > initialization.sourceLimit) {
        return Promise.reject(new RangeError('WGSL exceeds the compiler source budget'));
      }
      return request('compile', { code, optimize });
    },
    close,
  });
}

/** Only shader preparation is adapted; the injected device owns GPU execution. */
export function createDoeShaderAdapter({ device, compiler, optimize }) {
  if (!device || !compiler || typeof optimize !== 'boolean') {
    throw new TypeError('Explicit device, compiler and optimize boolean are required');
  }
  return Object.freeze({
    label: 'Doe-assisted WebGPU',
    executionOwner: 'browser',
    async createShaderModule({ code, label = '' }) {
      const started = performance.now();
      const result = await compiler.compile(code, { optimize });
      const workerRoundTripMs = performance.now() - started;
      const module = device.createShaderModule({ code: result.wgsl, label });
      const info = await module.getCompilationInfo();
      if (info.messages.some((message) => message.type === 'error')) {
        const error = new Error('Browser rejected emitted WGSL');
        error.source = 'emitted-wgsl';
        error.wgsl = result.wgsl;
        error.messages = Array.from(info.messages);
        throw error;
      }
      return { module, ...result, workerRoundTripMs };
    },
  });
}

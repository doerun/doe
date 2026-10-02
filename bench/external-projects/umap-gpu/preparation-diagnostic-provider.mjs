// Diagnostic provider wrapper for the unchanged UMAP workload. It observes
// public API boundaries and is never used for an application speed claim.
import { writeFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const modulePath = process.env.DOE_PREPARATION_PROVIDER_MODULE;
const outputPath = process.env.DOE_PREPARATION_DIAGNOSTIC_OUT;
if (!modulePath || !outputPath) {
  throw new Error('DOE_PREPARATION_PROVIDER_MODULE and DOE_PREPARATION_DIAGNOSTIC_OUT are required');
}

const importStart = process.hrtime.bigint();
const provider = await import(pathToFileURL(modulePath).href);
const importNs = Number(process.hrtime.bigint() - importStart);
const methods = new Map();

function flush() {
  writeFileSync(outputPath, `${JSON.stringify({
    artifactKind: 'umap-public-api-preparation-diagnostic',
    providerModule: modulePath,
    importNs,
    methods: Object.fromEntries(methods),
  }, null, 2)}\n`);
}

function observe(name, operation) {
  const start = process.hrtime.bigint();
  try {
    return operation();
  } finally {
    const elapsedNs = Number(process.hrtime.bigint() - start);
    const row = methods.get(name) ?? { calls: 0, elapsedNs: 0 };
    row.calls += 1;
    row.elapsedNs += elapsedNs;
    methods.set(name, row);
    if (name === 'device.createComputePipeline' ||
        name === 'device.destroy' ||
        (name === 'queue.submit' && row.calls % 501 === 0)) flush();
  }
}

function wrap(target, label, replacements = {}) {
  return new Proxy(target, {
    get(object, property) {
      if (Object.hasOwn(replacements, property)) return replacements[property];
      const value = Reflect.get(object, property, object);
      if (typeof value !== 'function') return value;
      return (...args) => observe(`${label}.${String(property)}`, () => value.apply(object, args));
    },
  });
}

function wrapDevice(device) {
  const queue = wrap(device.queue, 'queue');
  return wrap(device, 'device', { queue });
}

function wrapAdapter(adapter) {
  return wrap(adapter, 'adapter', {
    requestDevice: async (...args) => {
      const start = process.hrtime.bigint();
      const device = await adapter.requestDevice(...args);
      const elapsedNs = Number(process.hrtime.bigint() - start);
      const row = methods.get('adapter.requestDevice') ?? { calls: 0, elapsedNs: 0 };
      row.calls += 1;
      row.elapsedNs += elapsedNs;
      methods.set('adapter.requestDevice', row);
      return wrapDevice(device);
    },
  });
}

export const globals = provider.globals;
export const providerInfo = provider.providerInfo;
export function create(...args) {
  const gpu = observe('provider.create', () => provider.create(...args));
  return wrap(gpu, 'gpu', {
    requestAdapter: async (...requestArgs) => {
      const start = process.hrtime.bigint();
      const adapter = await gpu.requestAdapter(...requestArgs);
      const elapsedNs = Number(process.hrtime.bigint() - start);
      const row = methods.get('gpu.requestAdapter') ?? { calls: 0, elapsedNs: 0 };
      row.calls += 1;
      row.elapsedNs += elapsedNs;
      methods.set('gpu.requestAdapter', row);
      return adapter ? wrapAdapter(adapter) : adapter;
    },
  });
}

process.once('exit', flush);

import { dlopen, FFIType, JSCallback } from 'bun:ffi';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';

const LIB_EXTENSION_BY_PLATFORM = {
  darwin: 'dylib',
  linux: 'so',
  win32: 'dll',
};

const DOE_PROVIDER_MODE = resolveDoeProviderMode();
const DOE_LIBRARY_PATH = resolveDoeLibraryPath();
let doeRuntime = null;
let doeRuntimeError = null;

const PROVIDER_MODULE_SPECIFIER = resolveProviderModuleSpecifier();
const DEFAULT_PROVIDER_CREATE_ARGS = parseCreateArgsFromEnv(
  process.env.FAWN_WEBGPU_CREATE_ARGS
);
let providerNamespace = null;
let providerLoadError = null;

try {
  providerNamespace = await import(PROVIDER_MODULE_SPECIFIER);
} catch (error) {
  providerLoadError = error;
}
initializeDoeRuntime();

function resolveDoeProviderMode() {
  const raw = process.env.FAWN_WEBGPU_BUN_PROVIDER;
  if (typeof raw !== 'string') return 'auto';
  const normalized = raw.trim().toLowerCase();
  if (normalized === 'doe') return 'required';
  if (normalized === 'provider') return 'disabled';
  return 'auto';
}

function firstExistingPath(paths) {
  for (const path of paths) {
    if (!path) continue;
    if (existsSync(path)) return path;
  }
  return null;
}

function resolveDoeLibraryPath() {
  const preferredExt = LIB_EXTENSION_BY_PLATFORM[process.platform] ?? 'so';
  return firstExistingPath([
    process.env.FAWN_DOE_LIB,
    resolve(process.cwd(), `zig/zig-out/lib/libdoe_webgpu.${preferredExt}`),
    resolve(process.cwd(), 'zig/zig-out/lib/libdoe_webgpu.dylib'),
    resolve(process.cwd(), 'zig/zig-out/lib/libdoe_webgpu.so'),
    resolve(process.cwd(), 'zig/zig-out/lib/libdoe_webgpu.dll'),
  ]);
}

function initializeDoeRuntime() {
  if (DOE_PROVIDER_MODE === 'disabled') return;
  if (!DOE_LIBRARY_PATH) {
    if (DOE_PROVIDER_MODE === 'required') {
      throw new Error(
        'FAWN_WEBGPU_BUN_PROVIDER=doe requested Doe runtime, but libdoe_webgpu was not found. Set FAWN_DOE_LIB.'
      );
    }
    return;
  }
  try {
    doeRuntime = loadDoeWebGPU(DOE_LIBRARY_PATH);
  } catch (error) {
    doeRuntimeError = error;
    if (DOE_PROVIDER_MODE === 'required') throw error;
  }
}

function resolveProviderModuleSpecifier() {
  const candidate = process.env.FAWN_WEBGPU_NODE_PROVIDER_MODULE;
  if (typeof candidate === 'string' && candidate.trim().length > 0) {
    return candidate.trim();
  }
  return 'webgpu';
}

function parseCreateArgsFromEnv(raw) {
  if (typeof raw !== 'string' || raw.trim().length === 0) return [];
  return raw
    .split(';')
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0);
}

function normalizeCreateArgs(createArgs) {
  if (createArgs == null) return [...DEFAULT_PROVIDER_CREATE_ARGS];
  if (!Array.isArray(createArgs)) {
    throw new Error('create(...) expects an array of string args.');
  }
  const normalized = [];
  for (const [index, value] of createArgs.entries()) {
    if (typeof value !== 'string') {
      throw new Error(`create(...) arg[${index}] must be a string, got ${typeof value}`);
    }
    const trimmed = value.trim();
    if (trimmed.length > 0) normalized.push(trimmed);
  }
  return normalized;
}

function resolveProviderCreateFunction() {
  if (!providerNamespace) {
    const message = providerLoadError
      ? providerLoadError.message || String(providerLoadError)
      : 'provider module did not load';
    throw new Error(
      `Could not load WebGPU provider module '${PROVIDER_MODULE_SPECIFIER}': ${message}. ` +
        'Install the "webgpu" npm package or set FAWN_WEBGPU_NODE_PROVIDER_MODULE.'
    );
  }
  const fromNamespace = providerNamespace.create;
  const fromDefault = providerNamespace.default?.create;
  const createFn = typeof fromNamespace === 'function' ? fromNamespace : fromDefault;
  if (typeof createFn !== 'function') {
    throw new Error(
      `Provider module '${PROVIDER_MODULE_SPECIFIER}' does not export create(...).`
    );
  }
  return createFn;
}

function buildProviderGlobals() {
  if (!providerNamespace) return {};
  const direct = providerNamespace.globals;
  const nested = providerNamespace.default?.globals;
  const source = direct && typeof direct === 'object' ? direct : nested;
  if (!source || typeof source !== 'object') return {};
  return { ...source };
}

function defineGlobalIfMissing(target, name, value) {
  if (!target || typeof target !== 'object') return;
  if (value === undefined || value === null) return;
  if (target[name] !== undefined) return;
  Object.defineProperty(target, name, {
    value,
    writable: true,
    configurable: true,
    enumerable: false,
  });
}

export const globals = buildProviderGlobals();

export function create(createArgs = null) {
  if (doeRuntime) {
    return {
      requestAdapter: async (adapterOptions = undefined) =>
        doeRuntime.requestAdapter(adapterOptions),
      createAdapter: async (adapterOptions = undefined) =>
        doeRuntime.createAdapter(adapterOptions),
      releaseInstance: () => doeRuntime.releaseInstance(),
    };
  }
  const createFn = resolveProviderCreateFunction();
  const args = normalizeCreateArgs(createArgs);
  const gpu = createFn(args);
  if (!gpu || typeof gpu.requestAdapter !== 'function') {
    throw new Error(
      `Provider module '${PROVIDER_MODULE_SPECIFIER}' returned an invalid GPU object from create(...).`
    );
  }
  return gpu;
}

export function setupGlobals(target = globalThis, createArgs = null) {
  for (const [name, value] of Object.entries(globals)) {
    defineGlobalIfMissing(target, name, value);
  }
  const gpu = create(createArgs);
  if (typeof target.navigator === 'undefined') {
    Object.defineProperty(target, 'navigator', {
      value: { gpu },
      writable: true,
      configurable: true,
      enumerable: false,
    });
  } else if (!target.navigator.gpu) {
    Object.defineProperty(target.navigator, 'gpu', {
      value: gpu,
      writable: true,
      configurable: true,
      enumerable: false,
    });
  }
  return gpu;
}

export async function requestAdapter(adapterOptions = undefined, createArgs = null) {
  const gpu = create(createArgs);
  return gpu.requestAdapter(adapterOptions);
}

export async function requestDevice(options = {}) {
  const adapterOptions = options?.adapterOptions;
  const deviceDescriptor = options?.deviceDescriptor;
  const createArgs = options?.createArgs ?? null;
  const adapter = await requestAdapter(adapterOptions, createArgs);
  if (!adapter || typeof adapter.requestDevice !== 'function') {
    throw new Error('Provider returned an invalid adapter object.');
  }
  return adapter.requestDevice(deviceDescriptor);
}

export function providerInfo() {
  return {
    module: PROVIDER_MODULE_SPECIFIER,
    loaded: !!providerNamespace,
    loadError: providerLoadError
      ? providerLoadError.message || String(providerLoadError)
      : '',
    defaultCreateArgs: [...DEFAULT_PROVIDER_CREATE_ARGS],
    doeProviderMode: DOE_PROVIDER_MODE,
    doeRuntimeActive: !!doeRuntime,
    doeLibraryPath: DOE_LIBRARY_PATH ?? '',
    doeLoadError: doeRuntimeError
      ? doeRuntimeError.message || String(doeRuntimeError)
      : '',
  };
}

const CALLBACK_MODE_WAIT_ANY_ONLY = 1;
const WAIT_STATUS_SUCCESS = 1;
const REQUEST_ADAPTER_STATUS_SUCCESS = 1;
const REQUEST_DEVICE_STATUS_SUCCESS = 1;
const WAIT_TIMEOUT_NS = BigInt(5_000_000_000);

export function loadDoeWebGPU(ffiPath) {
  const wgpu = dlopen(ffiPath, {
    wgpuCreateInstance: { args: [FFIType.ptr], returns: FFIType.ptr },
    doeRequestAdapterFlat: {
      args: [FFIType.ptr, FFIType.ptr, FFIType.u32, FFIType.ptr, FFIType.ptr, FFIType.ptr],
      returns: FFIType.u64,
    },
    wgpuInstanceWaitAny: {
      args: [FFIType.ptr, FFIType.u64, FFIType.ptr, FFIType.u64],
      returns: FFIType.u32,
    },
    wgpuInstanceProcessEvents: { args: [FFIType.ptr], returns: FFIType.void },
    doeRequestDeviceFlat: {
      args: [FFIType.ptr, FFIType.ptr, FFIType.u32, FFIType.ptr, FFIType.ptr, FFIType.ptr],
      returns: FFIType.u64,
    },
    wgpuDeviceGetQueue: { args: [FFIType.ptr], returns: FFIType.ptr },
    wgpuAdapterRelease: { args: [FFIType.ptr], returns: FFIType.void },
    wgpuDeviceRelease: { args: [FFIType.ptr], returns: FFIType.void },
    wgpuInstanceRelease: { args: [FFIType.ptr], returns: FFIType.void },
  });

  let instancePtr = null;

  function ensureInstance() {
    if (instancePtr) return instancePtr;
    instancePtr = wgpu.symbols.wgpuCreateInstance(null);
    if (!instancePtr) throw new Error('[webgpu-doe] Failed to create WGPUInstance via FFI');
    return instancePtr;
  }

  async function doeRequestAdapter() {
    const inst = ensureInstance();
    let resolvedAdapter = null;
    let resolvedStatus = null;
    const callback = new JSCallback(
      (status, adapter) => { resolvedStatus = status; resolvedAdapter = adapter; },
      { args: [FFIType.u32, FFIType.ptr, FFIType.ptr, FFIType.u64, FFIType.ptr, FFIType.ptr], returns: FFIType.void }
    );
    try {
      const futureId = wgpu.symbols.doeRequestAdapterFlat(inst, null, CALLBACK_MODE_WAIT_ANY_ONLY, callback.ptr, null, null);
      const waitInfo = new ArrayBuffer(16);
      const waitView = new DataView(waitInfo);
      waitView.setBigUint64(0, BigInt(futureId), true);
      waitView.setUint32(8, 0, true);
      const waitStatus = wgpu.symbols.wgpuInstanceWaitAny(inst, BigInt(1), waitInfo, WAIT_TIMEOUT_NS);
      if (waitStatus !== WAIT_STATUS_SUCCESS) throw new Error(`[webgpu-doe] wgpuInstanceWaitAny failed with status ${waitStatus}`);
      if (resolvedStatus !== REQUEST_ADAPTER_STATUS_SUCCESS || !resolvedAdapter) throw new Error(`[webgpu-doe] requestAdapter failed with status ${resolvedStatus}`);
      return resolvedAdapter;
    } finally { callback.close(); }
  }

  async function doeRequestDevice(adapterPtr) {
    const inst = ensureInstance();
    let resolvedDevice = null;
    let resolvedStatus = null;
    const callback = new JSCallback(
      (status, device) => { resolvedStatus = status; resolvedDevice = device; },
      { args: [FFIType.u32, FFIType.ptr, FFIType.ptr, FFIType.u64, FFIType.ptr, FFIType.ptr], returns: FFIType.void }
    );
    try {
      const futureId = wgpu.symbols.doeRequestDeviceFlat(adapterPtr, null, CALLBACK_MODE_WAIT_ANY_ONLY, callback.ptr, null, null);
      const waitInfo = new ArrayBuffer(16);
      const waitView = new DataView(waitInfo);
      waitView.setBigUint64(0, BigInt(futureId), true);
      waitView.setUint32(8, 0, true);
      const waitStatus = wgpu.symbols.wgpuInstanceWaitAny(inst, BigInt(1), waitInfo, WAIT_TIMEOUT_NS);
      if (waitStatus !== WAIT_STATUS_SUCCESS) throw new Error(`[webgpu-doe] wgpuInstanceWaitAny (device) failed with status ${waitStatus}`);
      if (resolvedStatus !== REQUEST_DEVICE_STATUS_SUCCESS || !resolvedDevice) throw new Error(`[webgpu-doe] requestDevice failed with status ${resolvedStatus}`);
      return resolvedDevice;
    } finally { callback.close(); }
  }

  function buildAdapterObject(adapterPtr) {
    return {
      ptr: adapterPtr,
      tag: 'DoeAdapter',
      requestDevice: async (deviceDescriptor) => {
        const devicePtr = await doeRequestDevice(adapterPtr, deviceDescriptor);
        const queuePtr = wgpu.symbols.wgpuDeviceGetQueue(devicePtr);
        return {
          ptr: devicePtr,
          queue: queuePtr ? { ptr: queuePtr, tag: 'DoeQueue' } : null,
          tag: 'DoeDevice',
          release: () => wgpu.symbols.wgpuDeviceRelease(devicePtr),
        };
      },
      release: () => wgpu.symbols.wgpuAdapterRelease(adapterPtr),
    };
  }

  return {
    createAdapter: async (adapterOptions) => buildAdapterObject(await doeRequestAdapter(adapterOptions)),
    requestAdapter: async (adapterOptions) => buildAdapterObject(await doeRequestAdapter(adapterOptions)),
    releaseInstance: () => {
      if (instancePtr) {
        wgpu.symbols.wgpuInstanceRelease(instancePtr);
        instancePtr = null;
      }
    },
  };
}

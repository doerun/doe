import { createRequire } from 'node:module';
import { existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);

const addon = loadAddon();
const DOE_LIB_PATH = resolveDoeLibraryPath();
let libraryLoaded = false;

function loadAddon() {
  try {
    return require('../build/Release/doe_napi.node');
  } catch {
    try {
      return require('../build/Debug/doe_napi.node');
    } catch {
      return null;
    }
  }
}

function resolveDoeLibraryPath() {
  const ext = process.platform === 'darwin' ? 'dylib'
    : process.platform === 'win32' ? 'dll' : 'so';

  const candidates = [
    process.env.DOE_WEBGPU_LIB,
    resolve(__dirname, '..', 'prebuilds', `${process.platform}-${process.arch}`, `libdoe_webgpu.${ext}`),
    resolve(__dirname, '..', '..', '..', 'zig', 'zig-out', 'lib', `libdoe_webgpu.${ext}`),
    resolve(process.cwd(), 'zig', 'zig-out', 'lib', `libdoe_webgpu.${ext}`),
  ];

  for (const candidate of candidates) {
    if (candidate && existsSync(candidate)) return candidate;
  }
  return null;
}

function ensureLibrary() {
  if (libraryLoaded) return;
  if (!addon) {
    throw new Error(
      '@simulatte/webgpu-doe: Native addon not found. Run `npm run build` or `npx node-gyp rebuild`.'
    );
  }
  if (!DOE_LIB_PATH) {
    throw new Error(
      '@simulatte/webgpu-doe: libdoe_webgpu not found. Build it with `cd fawn/zig && zig build dropin` or set DOE_WEBGPU_LIB.'
    );
  }
  addon.loadLibrary(DOE_LIB_PATH);
  libraryLoaded = true;
}

// WebGPU enum constants (standard values).
export const globals = {
  GPUBufferUsage: {
    MAP_READ:      0x0001,
    MAP_WRITE:     0x0002,
    COPY_SRC:      0x0004,
    COPY_DST:      0x0008,
    INDEX:         0x0010,
    VERTEX:        0x0020,
    UNIFORM:       0x0040,
    STORAGE:       0x0080,
    INDIRECT:      0x0100,
    QUERY_RESOLVE: 0x0200,
  },
  GPUShaderStage: {
    VERTEX:   0x1,
    FRAGMENT: 0x2,
    COMPUTE:  0x4,
  },
  GPUMapMode: {
    READ:  0x0001,
    WRITE: 0x0002,
  },
  GPUTextureUsage: {
    COPY_SRC:          0x01,
    COPY_DST:          0x02,
    TEXTURE_BINDING:   0x04,
    STORAGE_BINDING:   0x08,
    RENDER_ATTACHMENT: 0x10,
  },
};

class DoeGPUBuffer {
  constructor(native, instance, size, usage) {
    this._native = native;
    this._instance = instance;
    this.size = size;
    this.usage = usage;
  }

  async mapAsync(mode, offset = 0, size = this.size) {
    addon.bufferMapSync(this._instance, this._native, mode, offset, size);
  }

  getMappedRange(offset = 0, size = this.size) {
    return addon.bufferGetMappedRange(this._native, offset, size);
  }

  unmap() {
    addon.bufferUnmap(this._native);
  }

  destroy() {
    addon.bufferRelease(this._native);
    this._native = null;
  }
}

class DoeGPUComputePassEncoder {
  constructor(native) { this._native = native; }

  setPipeline(pipeline) {
    addon.computePassSetPipeline(this._native, pipeline._native);
  }

  setBindGroup(index, bindGroup) {
    addon.computePassSetBindGroup(this._native, index, bindGroup._native);
  }

  dispatchWorkgroups(x, y = 1, z = 1) {
    addon.computePassDispatchWorkgroups(this._native, x, y, z);
  }

  end() {
    addon.computePassEnd(this._native);
  }
}

class DoeGPUCommandEncoder {
  constructor(native) { this._native = native; }

  beginComputePass(descriptor) {
    const pass = addon.beginComputePass(this._native);
    return new DoeGPUComputePassEncoder(pass);
  }

  copyBufferToBuffer(src, srcOffset, dst, dstOffset, size) {
    addon.commandEncoderCopyBufferToBuffer(
      this._native, src._native, srcOffset, dst._native, dstOffset, size);
  }

  finish() {
    const cmd = addon.commandEncoderFinish(this._native);
    return { _native: cmd };
  }
}

class DoeGPUQueue {
  constructor(native) { this._native = native; }

  submit(commandBuffers) {
    const natives = commandBuffers.map((c) => c._native);
    addon.queueSubmit(this._native, natives);
  }

  writeBuffer(buffer, bufferOffset, data, dataOffset = 0, size) {
    let view = data;
    if (dataOffset > 0 || size !== undefined) {
      const byteOffset = data.byteOffset + dataOffset * (data.BYTES_PER_ELEMENT || 1);
      const byteLength = size !== undefined
        ? size * (data.BYTES_PER_ELEMENT || 1)
        : data.byteLength - dataOffset * (data.BYTES_PER_ELEMENT || 1);
      view = new Uint8Array(data.buffer, byteOffset, byteLength);
    }
    addon.queueWriteBuffer(this._native, buffer._native, bufferOffset, view);
  }
}

class DoeGPUShaderModule {
  constructor(native) { this._native = native; }
}

class DoeGPUComputePipeline {
  constructor(native) { this._native = native; }
}

class DoeGPUBindGroupLayout {
  constructor(native) { this._native = native; }
}

class DoeGPUBindGroup {
  constructor(native) { this._native = native; }
}

class DoeGPUPipelineLayout {
  constructor(native) { this._native = native; }
}

class DoeGPUDevice {
  constructor(native, instance) {
    this._native = native;
    this._instance = instance;
    const q = addon.deviceGetQueue(native);
    this.queue = new DoeGPUQueue(q);
  }

  createBuffer(descriptor) {
    const buf = addon.createBuffer(this._native, descriptor);
    return new DoeGPUBuffer(buf, this._instance, descriptor.size, descriptor.usage);
  }

  createShaderModule(descriptor) {
    const code = descriptor.code || descriptor.source;
    if (!code) throw new Error('createShaderModule: descriptor.code is required');
    const mod = addon.createShaderModule(this._native, code);
    return new DoeGPUShaderModule(mod);
  }

  createComputePipeline(descriptor) {
    const shader = descriptor.compute?.module;
    const entryPoint = descriptor.compute?.entryPoint || 'main';
    const layout = descriptor.layout === 'auto' ? null : descriptor.layout;
    const native = addon.createComputePipeline(
      this._native, shader._native, entryPoint,
      layout?._native ?? null);
    return new DoeGPUComputePipeline(native);
  }

  createBindGroupLayout(descriptor) {
    const entries = (descriptor.entries || []).map((e) => ({
      binding: e.binding,
      visibility: e.visibility,
      buffer: e.buffer ? {
        type: e.buffer.type || 'uniform',
        hasDynamicOffset: e.buffer.hasDynamicOffset || false,
        minBindingSize: e.buffer.minBindingSize || 0,
      } : undefined,
      storageTexture: e.storageTexture,
    }));
    const native = addon.createBindGroupLayout(this._native, entries);
    return new DoeGPUBindGroupLayout(native);
  }

  createBindGroup(descriptor) {
    const entries = (descriptor.entries || []).map((e) => {
      const entry = {
        binding: e.binding,
        buffer: e.resource?.buffer?._native ?? e.resource?._native ?? null,
        offset: e.resource?.offset ?? 0,
      };
      if (e.resource?.size !== undefined) entry.size = e.resource.size;
      return entry;
    });
    const native = addon.createBindGroup(
      this._native, descriptor.layout._native, entries);
    return new DoeGPUBindGroup(native);
  }

  createPipelineLayout(descriptor) {
    const layouts = (descriptor.bindGroupLayouts || []).map((l) => l._native);
    const native = addon.createPipelineLayout(this._native, layouts);
    return new DoeGPUPipelineLayout(native);
  }

  createCommandEncoder(descriptor) {
    const native = addon.createCommandEncoder(this._native);
    return new DoeGPUCommandEncoder(native);
  }

  destroy() {
    addon.deviceRelease(this._native);
    this._native = null;
  }
}

class DoeGPUAdapter {
  constructor(native, instance) {
    this._native = native;
    this._instance = instance;
  }

  async requestDevice(descriptor) {
    const device = addon.requestDevice(this._instance, this._native);
    return new DoeGPUDevice(device, this._instance);
  }

  destroy() {
    addon.adapterRelease(this._native);
    this._native = null;
  }
}

class DoeGPU {
  constructor(instance) {
    this._instance = instance;
  }

  async requestAdapter(options) {
    const adapter = addon.requestAdapter(this._instance);
    return new DoeGPUAdapter(adapter, this._instance);
  }
}

export function create(createArgs = null) {
  ensureLibrary();
  const instance = addon.createInstance();
  return new DoeGPU(instance);
}

export function setupGlobals(target = globalThis, createArgs = null) {
  for (const [name, value] of Object.entries(globals)) {
    if (target[name] === undefined) {
      Object.defineProperty(target, name, {
        value,
        writable: true,
        configurable: true,
        enumerable: false,
      });
    }
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
  const createArgs = options?.createArgs ?? null;
  const adapter = await requestAdapter(options?.adapterOptions, createArgs);
  return adapter.requestDevice(options?.deviceDescriptor);
}

export function providerInfo() {
  return {
    module: '@simulatte/webgpu-doe',
    loaded: !!addon && !!DOE_LIB_PATH,
    loadError: !addon ? 'native addon not found' : !DOE_LIB_PATH ? 'libdoe_webgpu not found' : '',
    defaultCreateArgs: [],
    doeNative: true,
    doeLibraryPath: DOE_LIB_PATH ?? '',
  };
}

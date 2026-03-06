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
  const prebuildPath = resolve(__dirname, '..', 'prebuilds', `${process.platform}-${process.arch}`, 'doe_napi.node');
  try {
    return require(prebuildPath);
  } catch {
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
  constructor(native, instance, size, usage, queue) {
    this._native = native;
    this._instance = instance;
    this._queue = queue;
    this.size = size;
    this.usage = usage;
  }

  async mapAsync(mode, offset = 0, size = this.size) {
    if (this._queue) addon.queueFlush(this._queue);
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

  dispatchWorkgroupsIndirect(indirectBuffer, indirectOffset = 0) {
    addon.computePassDispatchWorkgroupsIndirect(this._native, indirectBuffer._native, indirectOffset);
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

  beginRenderPass(descriptor) {
    const colorAttachments = (descriptor.colorAttachments || []).map((a) => ({
      view: a.view._native,
      clearValue: a.clearValue || { r: 0, g: 0, b: 0, a: 1 },
    }));
    const pass = addon.beginRenderPass(this._native, colorAttachments);
    return new DoeGPURenderPassEncoder(pass);
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

  async onSubmittedWorkDone() {
    addon.queueFlush(this._native);
  }
}

class DoeGPURenderPassEncoder {
  constructor(native) { this._native = native; }

  setPipeline(pipeline) {
    addon.renderPassSetPipeline(this._native, pipeline._native);
  }

  draw(vertexCount, instanceCount = 1, firstVertex = 0, firstInstance = 0) {
    addon.renderPassDraw(this._native, vertexCount, instanceCount, firstVertex, firstInstance);
  }

  end() {
    addon.renderPassEnd(this._native);
  }
}

class DoeGPUTexture {
  constructor(native) { this._native = native; }

  createView(descriptor) {
    const view = addon.textureCreateView(this._native);
    return new DoeGPUTextureView(view);
  }

  destroy() {
    addon.textureRelease(this._native);
    this._native = null;
  }
}

class DoeGPUTextureView {
  constructor(native) { this._native = native; }
}

class DoeGPUSampler {
  constructor(native) { this._native = native; }
}

class DoeGPURenderPipeline {
  constructor(native) { this._native = native; }
}

class DoeGPUShaderModule {
  constructor(native) { this._native = native; }
}

class DoeGPUComputePipeline {
  constructor(native) { this._native = native; }

  getBindGroupLayout(index) {
    const layout = addon.computePipelineGetBindGroupLayout(this._native, index);
    return new DoeGPUBindGroupLayout(layout);
  }
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

// Metal defaults for Apple Silicon — matches doe_device_caps.zig METAL_LIMITS.
const DOE_LIMITS = Object.freeze({
  maxTextureDimension1D: 16384,
  maxTextureDimension2D: 16384,
  maxTextureDimension3D: 2048,
  maxTextureArrayLayers: 2048,
  maxBindGroups: 4,
  maxBindGroupsPlusVertexBuffers: 24,
  maxBindingsPerBindGroup: 1000,
  maxDynamicUniformBuffersPerPipelineLayout: 8,
  maxDynamicStorageBuffersPerPipelineLayout: 4,
  maxSampledTexturesPerShaderStage: 16,
  maxSamplersPerShaderStage: 16,
  maxStorageBuffersPerShaderStage: 8,
  maxStorageTexturesPerShaderStage: 4,
  maxUniformBuffersPerShaderStage: 12,
  maxUniformBufferBindingSize: 65536,
  maxStorageBufferBindingSize: 134217728,
  minUniformBufferOffsetAlignment: 256,
  minStorageBufferOffsetAlignment: 32,
  maxVertexBuffers: 8,
  maxBufferSize: 268435456,
  maxVertexAttributes: 16,
  maxVertexBufferArrayStride: 2048,
  maxInterStageShaderVariables: 16,
  maxColorAttachments: 8,
  maxColorAttachmentBytesPerSample: 32,
  maxComputeWorkgroupStorageSize: 32768,
  maxComputeInvocationsPerWorkgroup: 1024,
  maxComputeWorkgroupSizeX: 1024,
  maxComputeWorkgroupSizeY: 1024,
  maxComputeWorkgroupSizeZ: 64,
  maxComputeWorkgroupsPerDimension: 65535,
});

const DOE_FEATURES = Object.freeze(new Set(['shader-f16']));

class DoeGPUDevice {
  constructor(native, instance) {
    this._native = native;
    this._instance = instance;
    const q = addon.deviceGetQueue(native);
    this.queue = new DoeGPUQueue(q);
    this.limits = DOE_LIMITS;
    this.features = DOE_FEATURES;
  }

  createBuffer(descriptor) {
    const buf = addon.createBuffer(this._native, descriptor);
    return new DoeGPUBuffer(buf, this._instance, descriptor.size, descriptor.usage, this.queue._native);
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

  async createComputePipelineAsync(descriptor) {
    return this.createComputePipeline(descriptor);
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

  createTexture(descriptor) {
    const native = addon.createTexture(this._native, {
      format: descriptor.format || 'rgba8unorm',
      width: descriptor.size?.[0] ?? descriptor.size?.width ?? descriptor.size ?? 1,
      height: descriptor.size?.[1] ?? descriptor.size?.height ?? 1,
      depthOrArrayLayers: descriptor.size?.[2] ?? descriptor.size?.depthOrArrayLayers ?? 1,
      usage: descriptor.usage || 0,
      mipLevelCount: descriptor.mipLevelCount || 1,
    });
    return new DoeGPUTexture(native);
  }

  createSampler(descriptor = {}) {
    const native = addon.createSampler(this._native, descriptor);
    return new DoeGPUSampler(native);
  }

  createRenderPipeline(descriptor) {
    const native = addon.createRenderPipeline(this._native);
    return new DoeGPURenderPipeline(native);
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
    this.features = DOE_FEATURES;
    this.limits = DOE_LIMITS;
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

import {
  UINT32_MAX,
  failValidation,
  initResource,
  assertObject,
  assertArray,
  assertNonEmptyString,
  assertIntegerInRange,
  assertLiveResource,
  destroyResource,
} from './resource-lifecycle.js';
import {
  assertBufferDescriptor,
  assertTextureSize,
  assertBindGroupResource,
  normalizeTextureDimension,
  normalizeBindGroupLayoutEntry,
} from './validation.js';
import {
  shaderCheckFailure,
} from './compiler-errors.js';

function validateWriteBufferInput(data, dataOffset, size, path) {
  assertIntegerInRange(dataOffset, path, 'dataOffset', { min: 0 });
  if (
    !ArrayBuffer.isView(data)
    && !(data instanceof ArrayBuffer)
    && !Buffer.isBuffer(data)
  ) {
    failValidation(path, 'data must be a TypedArray, DataView, ArrayBuffer, or Buffer');
  }
  if (dataOffset === 0 && size === undefined) {
    return data;
  }
  if (!ArrayBuffer.isView(data)) {
    failValidation(path, 'dataOffset and size slicing require a TypedArray or DataView input');
  }
  if (size !== undefined) {
    assertIntegerInRange(size, path, 'size', { min: 0 });
  }
  const elementSize = data.BYTES_PER_ELEMENT || 1;
  const byteOffset = data.byteOffset + dataOffset * elementSize;
  const byteLength = size !== undefined
    ? size * elementSize
    : data.byteLength - dataOffset * elementSize;
  return new Uint8Array(data.buffer, byteOffset, byteLength);
}

const NEVER_RESOLVED = new Promise(() => {});
const EMPTY_ADAPTER_INFO = Object.freeze({
  vendor: '',
  architecture: '',
  device: '',
  description: '',
  subgroupMinSize: 0,
  subgroupMaxSize: 0,
});

function createFullSurfaceClasses({
  globals,
  backend,
  encoderClasses,
}) {
  let classes = null;
  const ERROR_FILTER_MAP = Object.freeze({
    validation: 0x00000001,
    'out-of-memory': 0x00000002,
    internal: 0x00000003,
  });

  function normalizeErrorFilter(filter, path) {
    const encoded = ERROR_FILTER_MAP[filter];
    if (encoded === undefined) {
      failValidation(path, `invalid filter "${filter}"; must be "validation", "out-of-memory", or "internal"`);
    }
    return encoded;
  }

  class DoeGPUBuffer {
    constructor(native, instance, size, usage, queue, owner) {
      this._native = native;
      this._instance = instance;
      this._queue = queue;
      this.size = size;
      this.usage = usage;
      this.label = '';
      initResource(this, 'GPUBuffer', owner);
      if (backend.initBufferState) {
        backend.initBufferState(this);
      }
    }

    async mapAsync(mode, offset = 0, size = Math.max(0, this.size - offset)) {
      const native = assertLiveResource(this, 'GPUBuffer.mapAsync', 'GPUBuffer');
      assertIntegerInRange(mode, 'GPUBuffer.mapAsync', 'mode', { min: 0, max: UINT32_MAX });
      assertIntegerInRange(offset, 'GPUBuffer.mapAsync', 'offset', { min: 0 });
      assertIntegerInRange(size, 'GPUBuffer.mapAsync', 'size', { min: 0 });
      if (offset + size > this.size) {
        failValidation('GPUBuffer.mapAsync', `mapped range ${offset}+${size} exceeds buffer size ${this.size}`);
      }
      await backend.bufferMapAsync(this, native, mode, offset, size);
    }

    getMappedRange(offset = 0, size = Math.max(0, this.size - offset)) {
      const native = assertLiveResource(this, 'GPUBuffer.getMappedRange', 'GPUBuffer');
      assertIntegerInRange(offset, 'GPUBuffer.getMappedRange', 'offset', { min: 0 });
      assertIntegerInRange(size, 'GPUBuffer.getMappedRange', 'size', { min: 0 });
      if (offset + size > this.size) {
        failValidation('GPUBuffer.getMappedRange', `mapped range ${offset}+${size} exceeds buffer size ${this.size}`);
      }
      return backend.bufferGetMappedRange(this, native, offset, size);
    }

    _readCopy(offset = 0, size = Math.max(0, this.size - offset)) {
      const native = assertLiveResource(this, 'GPUBuffer._readCopy', 'GPUBuffer');
      assertIntegerInRange(offset, 'GPUBuffer._readCopy', 'offset', { min: 0 });
      assertIntegerInRange(size, 'GPUBuffer._readCopy', 'size', { min: 0 });
      if (offset + size > this.size) {
        failValidation('GPUBuffer._readCopy', `mapped range ${offset}+${size} exceeds buffer size ${this.size}`);
      }
      if (typeof backend.bufferReadCopy === 'function') {
        return backend.bufferReadCopy(this, native, offset, size);
      }
      return backend.bufferGetMappedRange(this, native, offset, size).slice(0);
    }

    assertMappedPrefixF32(expected, count) {
      const native = assertLiveResource(this, 'GPUBuffer.assertMappedPrefixF32', 'GPUBuffer');
      assertIntegerInRange(count, 'GPUBuffer.assertMappedPrefixF32', 'count', { min: 0, max: UINT32_MAX });
      if (Array.isArray(expected)) {
        if (expected.length < count) {
          failValidation('GPUBuffer.assertMappedPrefixF32', `expected array must contain at least ${count} values`);
        }
        const actual = new Float32Array(this.getMappedRange(0, count * Float32Array.BYTES_PER_ELEMENT));
        for (let index = 0; index < count; index += 1) {
          if (actual[index] !== expected[index]) {
            failValidation(
              'GPUBuffer.assertMappedPrefixF32',
              `expected readback[${index}] === ${expected[index]}, got ${actual[index]}`,
            );
          }
        }
        return;
      }
      if (typeof expected !== 'number') {
        failValidation('GPUBuffer.assertMappedPrefixF32', 'expected must be a number or array of numbers');
      }
      if (typeof backend.bufferAssertMappedPrefixF32 === 'function') {
        return backend.bufferAssertMappedPrefixF32(this, native, expected, count);
      }
      const actual = new Float32Array(this.getMappedRange(0, count * Float32Array.BYTES_PER_ELEMENT));
      for (let index = 0; index < count; index += 1) {
        if (actual[index] !== expected) {
          failValidation(
            'GPUBuffer.assertMappedPrefixF32',
            `expected readback[${index}] === ${expected}, got ${actual[index]}`,
          );
        }
      }
    }

    _mapReadCopyUnmap(mode, offset = 0, size = Math.max(0, this.size - offset)) {
      assertLiveResource(this, 'GPUBuffer._mapReadCopyUnmap', 'GPUBuffer');
      if (typeof backend.bufferMapReadCopyUnmap === 'function') {
        return backend.bufferMapReadCopyUnmap(this, mode, offset, size);
      }
      return null;
    }

    unmap() {
      backend.bufferUnmap(assertLiveResource(this, 'GPUBuffer.unmap', 'GPUBuffer'), this);
    }

    destroy() {
      destroyResource(this, (native) => backend.bufferDestroy(native, this));
    }
  }

  class DoeGPUQueue {
    constructor(native, instance, device) {
      this._native = native;
      this._instance = instance;
      this._device = device;
      this.label = '';
      initResource(this, 'GPUQueue', device);
      if (backend.initQueueState) {
        backend.initQueueState(this);
      }
    }

    hasPendingSubmissions() {
      assertLiveResource(this, 'GPUQueue.hasPendingSubmissions', 'GPUQueue');
      return backend.queueHasPendingSubmissions(this);
    }

    markSubmittedWorkDone() {
      assertLiveResource(this, 'GPUQueue.markSubmittedWorkDone', 'GPUQueue');
      backend.queueMarkSubmittedWorkDone(this);
    }

    submit(commandBuffers) {
      const native = assertLiveResource(this, 'GPUQueue.submit', 'GPUQueue');
      const buffers = assertArray(commandBuffers, 'GPUQueue.submit', 'commandBuffers');
      if (buffers.length === 0) {
        return;
      }
      return backend.queueSubmit(this, native, buffers);
    }

    writeBuffer(buffer, bufferOffset, data, dataOffset = 0, size) {
      const native = assertLiveResource(this, 'GPUQueue.writeBuffer', 'GPUQueue');
      const bufferNative = assertLiveResource(buffer, 'GPUQueue.writeBuffer', 'GPUBuffer');
      assertIntegerInRange(bufferOffset, 'GPUQueue.writeBuffer', 'bufferOffset', { min: 0 });
      const view = validateWriteBufferInput(data, dataOffset, size, 'GPUQueue.writeBuffer');
      return backend.queueWriteBuffer(this, native, bufferNative, bufferOffset, view);
    }

    writeTexture(destination, data, dataLayout, size) {
      const native = assertLiveResource(this, 'GPUQueue.writeTexture', 'GPUQueue');
      const destinationObject = assertObject(destination, 'GPUQueue.writeTexture', 'destination');
      const layoutObject = assertObject(dataLayout, 'GPUQueue.writeTexture', 'dataLayout');
      const sizeObject = assertObject(size, 'GPUQueue.writeTexture', 'size');
      const view = validateWriteBufferInput(data, 0, undefined, 'GPUQueue.writeTexture');
      return backend.queueWriteTexture(
        this,
        native,
        {
          texture: assertLiveResource(destinationObject.texture, 'GPUQueue.writeTexture', 'GPUTexture'),
          mipLevel: destinationObject.mipLevel ?? 0,
          origin: {
            x: destinationObject.origin?.x ?? 0,
            y: destinationObject.origin?.y ?? 0,
            z: destinationObject.origin?.z ?? 0,
          },
          aspect: destinationObject.aspect,
        },
        view,
        {
          offset: layoutObject.offset ?? 0,
          bytesPerRow: layoutObject.bytesPerRow ?? 0,
          rowsPerImage: layoutObject.rowsPerImage ?? 0,
        },
        {
          width: sizeObject.width,
          height: sizeObject.height,
          depthOrArrayLayers: sizeObject.depthOrArrayLayers ?? 1,
        },
      );
    }

    async onSubmittedWorkDone() {
      const native = assertLiveResource(this, 'GPUQueue.onSubmittedWorkDone', 'GPUQueue');
      if (!this.hasPendingSubmissions()) {
        return;
      }
      await backend.queueOnSubmittedWorkDone(this, native);
      this.markSubmittedWorkDone();
    }

    copyExternalImageToTexture(source, destination, copySize) {
      const native = assertLiveResource(this, 'GPUQueue.copyExternalImageToTexture', 'GPUQueue');
      const sourceObject = assertObject(source, 'GPUQueue.copyExternalImageToTexture', 'source');
      const destinationObject = assertObject(destination, 'GPUQueue.copyExternalImageToTexture', 'destination');
      const sizeObject = assertObject(copySize, 'GPUQueue.copyExternalImageToTexture', 'copySize');
      if (typeof backend.queueCopyExternalImageToTexture !== 'function') {
        failValidation(
          'GPUQueue.copyExternalImageToTexture',
          'copyExternalImageToTexture is not supported on this package surface',
        );
      }
      return backend.queueCopyExternalImageToTexture(this, native, sourceObject, destinationObject, sizeObject);
    }
  }

  class DoeGPUTexture {
    constructor(native, owner, meta) {
      this._native = native;
      this.width = meta?.width ?? 1;
      this.height = meta?.height ?? 1;
      this.depthOrArrayLayers = meta?.depthOrArrayLayers ?? 1;
      this.mipLevelCount = meta?.mipLevelCount ?? 1;
      this.sampleCount = meta?.sampleCount ?? 1;
      this.dimension = meta?.dimension ?? '2d';
      this.format = meta?.format ?? 'rgba8unorm';
      this.usage = meta?.usage ?? 0;
      this.label = '';
      initResource(this, 'GPUTexture', owner);
    }

    createView(descriptor) {
      const view = backend.textureCreateView(this, assertLiveResource(this, 'GPUTexture.createView', 'GPUTexture'), descriptor);
      const tv = new DoeGPUTextureView(view, this);
      tv.label = descriptor?.label ?? '';
      return tv;
    }

    destroy() {
      destroyResource(this, (native) => backend.textureDestroy(native, this));
    }
  }

  class DoeGPUTextureView {
    constructor(native, owner) {
      this._native = native;
      this.label = '';
      initResource(this, 'GPUTextureView', owner);
    }
  }

  class DoeGPUSampler {
    constructor(native, owner) {
      this._native = native;
      this.label = '';
      initResource(this, 'GPUSampler', owner);
    }
  }

  class DoeGPURenderPipeline {
    constructor(native, owner) {
      this._native = native;
      this.label = '';
      initResource(this, 'GPURenderPipeline', owner);
    }

    getBindGroupLayout(index) {
      assertLiveResource(this, 'GPURenderPipeline.getBindGroupLayout', 'GPURenderPipeline');
      assertIntegerInRange(index, 'GPURenderPipeline.getBindGroupLayout', 'index', { min: 0, max: UINT32_MAX });
      return backend.renderPipelineGetBindGroupLayout(this, index, classes);
    }
  }

  class DoeGPUShaderModule {
    constructor(native, code, owner) {
      this._native = native;
      this._code = code;
      this.label = '';
      initResource(this, 'GPUShaderModule', owner);
    }

    async getCompilationInfo() {
      const native = assertLiveResource(this, 'GPUShaderModule.getCompilationInfo', 'GPUShaderModule');
      if (typeof backend.shaderModuleGetCompilationInfo === 'function') {
        return backend.shaderModuleGetCompilationInfo(this, native);
      }
      return { messages: [] };
    }

    destroy() {
      if (typeof backend.shaderModuleDestroy !== 'function') {
        return;
      }
      destroyResource(this, (native) => backend.shaderModuleDestroy(native, this));
    }
  }

  class DoeGPUComputePipeline {
    constructor(native, device, explicitLayout, autoLayoutEntriesByGroup) {
      this._native = native;
      this._device = device;
      this._explicitLayout = explicitLayout;
      this._autoLayoutEntriesByGroup = autoLayoutEntriesByGroup;
      this._cachedLayouts = new Map();
      this.label = '';
      initResource(this, 'GPUComputePipeline', device);
    }

    getBindGroupLayout(index) {
      assertLiveResource(this, 'GPUComputePipeline.getBindGroupLayout', 'GPUComputePipeline');
      assertIntegerInRange(index, 'GPUComputePipeline.getBindGroupLayout', 'index', { min: 0, max: UINT32_MAX });
      if (this._explicitLayout) {
        return this._explicitLayout;
      }
      if (this._cachedLayouts.has(index)) {
        return this._cachedLayouts.get(index);
      }
      const layout = backend.computePipelineGetBindGroupLayout(this, index, classes);
      this._cachedLayouts.set(index, layout);
      return layout;
    }
  }

  class DoeGPUBindGroupLayout {
    constructor(native, owner) {
      this._native = native;
      this.label = '';
      initResource(this, 'GPUBindGroupLayout', owner);
    }
  }

  class DoeGPUBindGroup {
    constructor(native, owner) {
      this._native = native;
      this.label = '';
      initResource(this, 'GPUBindGroup', owner);
    }
  }

  class DoeGPUPipelineLayout {
    constructor(native, owner) {
      this._native = native;
      this.label = '';
      initResource(this, 'GPUPipelineLayout', owner);
    }
  }

  class DoeGPUQuerySet {
    constructor(native, type, count, owner) {
      this._native = native;
      this.type = type;
      this.count = count;
      this.label = '';
      initResource(this, 'GPUQuerySet', owner);
    }

    destroy() {
      destroyResource(this, (native) => backend.querySetDestroy(native));
    }
  }

  class DoeGPUDevice {
    constructor(native, instance, inheritedLimits = null, inheritedFeatures = null) {
      this._native = native;
      this._instance = instance;
      this._onuncapturederror = null;
      this.label = '';
      initResource(this, 'GPUDevice');
      if (typeof backend.initDeviceState === 'function') {
        backend.initDeviceState(this);
      }
      this.queue = new DoeGPUQueue(backend.deviceGetQueue(native), instance, this);
      this.limits = inheritedLimits ?? backend.deviceLimits(native);
      this.features = inheritedFeatures ?? backend.deviceFeatures(native);
    }

    addEventListener(_type, _listener) {}

    removeEventListener(_type, _listener) {}

    get lost() {
      if (typeof backend.deviceGetLost === 'function') {
        const native = assertLiveResource(this, 'GPUDevice.lost', 'GPUDevice');
        return backend.deviceGetLost(this, native);
      }
      return NEVER_RESOLVED;
    }

    get adapterInfo() {
      if (typeof backend.deviceGetAdapterInfo === 'function') {
        const native = assertLiveResource(this, 'GPUDevice.adapterInfo', 'GPUDevice');
        return backend.deviceGetAdapterInfo(this, native);
      }
      return EMPTY_ADAPTER_INFO;
    }

    pushErrorScope(filter) {
      const native = assertLiveResource(this, 'GPUDevice.pushErrorScope', 'GPUDevice');
      const encodedFilter = normalizeErrorFilter(filter, 'GPUDevice.pushErrorScope');
      if (typeof backend.devicePushErrorScope === 'function') {
        backend.devicePushErrorScope(this, native, filter, encodedFilter);
      }
    }

    popErrorScope() {
      const native = assertLiveResource(this, 'GPUDevice.popErrorScope', 'GPUDevice');
      if (typeof backend.devicePopErrorScope === 'function') {
        return backend.devicePopErrorScope(this, native);
      }
      return Promise.resolve(null);
    }

    get onuncapturederror() {
      if (typeof backend.deviceGetOnUncapturedError === 'function') {
        const native = assertLiveResource(this, 'GPUDevice.onuncapturederror', 'GPUDevice');
        return backend.deviceGetOnUncapturedError(this, native);
      }
      return this._onuncapturederror;
    }

    set onuncapturederror(handler) {
      if (typeof backend.deviceSetOnUncapturedError === 'function') {
        const native = assertLiveResource(this, 'GPUDevice.onuncapturederror', 'GPUDevice');
        backend.deviceSetOnUncapturedError(this, native, handler ?? null);
        return;
      }
      this._onuncapturederror = handler ?? null;
    }

    createBuffer(descriptor) {
      const validated = assertBufferDescriptor(descriptor, 'GPUDevice.createBuffer');
      const native = backend.deviceCreateBuffer(this, validated);
      const buffer = new DoeGPUBuffer(native, this._instance, validated.size, validated.usage, this.queue, this);
      buffer.label = descriptor?.label ?? '';
      if (validated.mappedAtCreation && typeof backend.bufferMarkMappedAtCreation === 'function') {
        backend.bufferMarkMappedAtCreation(buffer);
      }
      return buffer;
    }

    createShaderModule(descriptor) {
      const objectDescriptor = assertObject(descriptor, 'GPUDevice.createShaderModule', 'descriptor');
      const code = objectDescriptor.code ?? objectDescriptor.source;
      assertNonEmptyString(code, 'GPUDevice.createShaderModule', 'descriptor.code');
      const preflight = backend.preflightShaderSource(code);
      if (!preflight.ok) {
        shaderCheckFailure('GPUDevice.createShaderModule', preflight);
      }
      const hints = objectDescriptor.compilationHints ?? null;
      const native = backend.deviceCreateShaderModule(this, code, hints);
      const module = new DoeGPUShaderModule(native, code, this);
      module.label = objectDescriptor.label ?? '';
      return module;
    }

    createComputePipeline(descriptor) {
      const pipelineDescriptor = assertObject(descriptor, 'GPUDevice.createComputePipeline', 'descriptor');
      const compute = assertObject(pipelineDescriptor.compute, 'GPUDevice.createComputePipeline', 'descriptor.compute');
      const shader = compute.module;
      const shaderNative = assertLiveResource(shader, 'GPUDevice.createComputePipeline', 'GPUShaderModule');
      const entryPoint = compute.entryPoint ?? 'main';
      assertNonEmptyString(entryPoint, 'GPUDevice.createComputePipeline', 'descriptor.compute.entryPoint');
      const layout = pipelineDescriptor.layout === 'auto' || pipelineDescriptor.layout === undefined
        ? null
        : pipelineDescriptor.layout;
      if (layout !== null) {
        assertLiveResource(layout, 'GPUDevice.createComputePipeline', 'GPUPipelineLayout');
      }
      const autoLayoutEntriesByGroup = layout
        ? null
        : backend.requireAutoLayoutEntriesFromNative(
          shader,
          globals.GPUShaderStage.COMPUTE,
          'GPUDevice.createComputePipeline',
        );
      const constants = compute.constants ?? null;
      const label = pipelineDescriptor.label || undefined;
      const native = backend.deviceCreateComputePipeline(this, shaderNative, entryPoint, layout?._native ?? null, constants, label);
      const pipeline = new DoeGPUComputePipeline(native, this, layout, autoLayoutEntriesByGroup);
      pipeline.label = pipelineDescriptor.label ?? '';
      return pipeline;
    }

    async createComputePipelineAsync(descriptor) {
      return this.createComputePipeline(descriptor);
    }

    createBindGroupLayout(descriptor) {
      const layoutDescriptor = assertObject(descriptor, 'GPUDevice.createBindGroupLayout', 'descriptor');
      const entries = assertArray(layoutDescriptor.entries ?? [], 'GPUDevice.createBindGroupLayout', 'descriptor.entries')
        .map((entry, index) => normalizeBindGroupLayoutEntry(entry, index, 'GPUDevice.createBindGroupLayout'));
      const native = backend.deviceCreateBindGroupLayout(this, entries, layoutDescriptor.label || undefined);
      const bgl = new DoeGPUBindGroupLayout(native, this);
      bgl.label = layoutDescriptor.label ?? '';
      return bgl;
    }

    createBindGroup(descriptor) {
      const bindGroupDescriptor = assertObject(descriptor, 'GPUDevice.createBindGroup', 'descriptor');
      const layoutNative = assertLiveResource(bindGroupDescriptor.layout, 'GPUDevice.createBindGroup', 'GPUBindGroupLayout');
      const entries = assertArray(bindGroupDescriptor.entries ?? [], 'GPUDevice.createBindGroup', 'descriptor.entries')
        .map((entry, index) => {
          const binding = assertObject(entry, 'GPUDevice.createBindGroup', `descriptor.entries[${index}]`);
          const resource = assertBindGroupResource(binding.resource, 'GPUDevice.createBindGroup');
          const normalized = {
            binding: assertIntegerInRange(binding.binding, 'GPUDevice.createBindGroup', `descriptor.entries[${index}].binding`, { min: 0, max: UINT32_MAX }),
            buffer: resource.buffer,
            sampler: resource.sampler,
            textureView: resource.textureView,
            offset: resource.offset ?? 0,
          };
          if (resource.size !== undefined) {
            normalized.size = resource.size;
          }
          return normalized;
        });
      const native = backend.deviceCreateBindGroup(this, layoutNative, entries, bindGroupDescriptor.label || undefined);
      const bg = new DoeGPUBindGroup(native, this);
      bg.label = bindGroupDescriptor.label ?? '';
      return bg;
    }

    createPipelineLayout(descriptor) {
      const layoutDescriptor = assertObject(descriptor, 'GPUDevice.createPipelineLayout', 'descriptor');
      const layouts = assertArray(layoutDescriptor.bindGroupLayouts ?? [], 'GPUDevice.createPipelineLayout', 'descriptor.bindGroupLayouts')
        .map((layout, index) => assertLiveResource(layout, 'GPUDevice.createPipelineLayout', `descriptor.bindGroupLayouts[${index}]`));
      const native = backend.deviceCreatePipelineLayout(this, layouts, layoutDescriptor.label || undefined);
      const pl = new DoeGPUPipelineLayout(native, this);
      pl.label = layoutDescriptor.label ?? '';
      return pl;
    }

    createTexture(descriptor) {
      const textureDescriptor = assertObject(descriptor, 'GPUDevice.createTexture', 'descriptor');
      const size = assertTextureSize(textureDescriptor.size, 'GPUDevice.createTexture');
      const usage = assertIntegerInRange(textureDescriptor.usage, 'GPUDevice.createTexture', 'descriptor.usage', { min: 1 });
      const dimension = normalizeTextureDimension(textureDescriptor.dimension, 'GPUDevice.createTexture');
      const native = backend.deviceCreateTexture(this, {
        ...textureDescriptor,
        dimension,
      }, size, usage);
      const texture = new DoeGPUTexture(native, this, {
        width: size.width,
        height: size.height,
        depthOrArrayLayers: size.depthOrArrayLayers,
        mipLevelCount: textureDescriptor.mipLevelCount ?? 1,
        sampleCount: textureDescriptor.sampleCount ?? 1,
        dimension,
        format: textureDescriptor.format ?? 'rgba8unorm',
        usage,
      });
      texture.label = textureDescriptor.label ?? '';
      return texture;
    }

    createSampler(descriptor = {}) {
      assertObject(descriptor, 'GPUDevice.createSampler', 'descriptor');
      const native = backend.deviceCreateSampler(this, descriptor);
      const sampler = new DoeGPUSampler(native, this);
      sampler.label = descriptor?.label ?? '';
      return sampler;
    }

    createRenderPipeline(descriptor) {
      const renderDescriptor = assertObject(descriptor, 'GPUDevice.createRenderPipeline', 'descriptor');
      const vertex = assertObject(renderDescriptor.vertex, 'GPUDevice.createRenderPipeline', 'descriptor.vertex');
      const fragment = assertObject(renderDescriptor.fragment, 'GPUDevice.createRenderPipeline', 'descriptor.fragment');
      const vertexModule = assertLiveResource(vertex.module, 'GPUDevice.createRenderPipeline', 'GPUShaderModule');
      const fragmentModule = assertLiveResource(fragment.module, 'GPUDevice.createRenderPipeline', 'GPUShaderModule');
      const targets = assertArray(fragment.targets ?? [], 'GPUDevice.createRenderPipeline', 'descriptor.fragment.targets');
      if (targets.length === 0) {
        failValidation('GPUDevice.createRenderPipeline', 'descriptor.fragment.targets must contain at least one target');
      }
      const vertexBuffers = vertex.buffers === undefined
        ? []
        : assertArray(vertex.buffers, 'GPUDevice.createRenderPipeline', 'descriptor.vertex.buffers');
      const layout = renderDescriptor.layout && renderDescriptor.layout !== 'auto'
        ? assertLiveResource(renderDescriptor.layout, 'GPUDevice.createRenderPipeline', 'GPUPipelineLayout')
        : null;
      const native = backend.deviceCreateRenderPipeline(this, {
        layout,
        vertexModule,
        vertexEntryPoint: vertex.entryPoint ?? 'main',
        vertexBuffers,
        fragmentModule,
        fragmentEntryPoint: fragment.entryPoint ?? 'main',
        colorFormat: assertNonEmptyString(targets[0].format, 'GPUDevice.createRenderPipeline', 'descriptor.fragment.targets[0].format'),
        primitive: renderDescriptor.primitive ?? null,
        depthStencil: renderDescriptor.depthStencil ?? null,
        multisample: renderDescriptor.multisample ?? null,
      });
      const rp = new DoeGPURenderPipeline(native, this);
      rp.label = renderDescriptor.label ?? '';
      return rp;
    }

    async createRenderPipelineAsync(descriptor) {
      return this.createRenderPipeline(descriptor);
    }

    createRenderBundleEncoder(descriptor) {
      const bundleDescriptor = assertObject(descriptor, 'GPUDevice.createRenderBundleEncoder', 'descriptor');
      assertLiveResource(this, 'GPUDevice.createRenderBundleEncoder', 'GPUDevice');
      if (!encoderClasses?.DoeGPURenderBundleEncoder) {
        failValidation('GPUDevice.createRenderBundleEncoder', 'render bundle encoder surface unavailable on this package build');
      }
      const rbe = backend.deviceCreateRenderBundleEncoder(this, bundleDescriptor, encoderClasses);
      rbe.label = bundleDescriptor.label ?? '';
      return rbe;
    }

    createQuerySet(descriptor) {
      assertLiveResource(this, 'GPUDevice.createQuerySet', 'GPUDevice');
      const queryDescriptor = assertObject(descriptor, 'GPUDevice.createQuerySet', 'descriptor');
      if (queryDescriptor.type !== 'timestamp') {
        failValidation('GPUDevice.createQuerySet', `unsupported query type "${queryDescriptor.type}"; only "timestamp" is supported`);
      }
      assertIntegerInRange(queryDescriptor.count, 'GPUDevice.createQuerySet', 'descriptor.count', { min: 1, max: UINT32_MAX });
      const native = backend.deviceCreateQuerySet(this, queryDescriptor);
      if (native == null) {
        failValidation('GPUDevice.createQuerySet', 'timestamp query sets are not supported on this backend/device');
      }
      const qs = new DoeGPUQuerySet(native, queryDescriptor.type, queryDescriptor.count, this);
      qs.label = queryDescriptor.label ?? '';
      return qs;
    }

    createCommandEncoder(descriptor) {
      if (descriptor !== undefined) {
        assertObject(descriptor, 'GPUDevice.createCommandEncoder', 'descriptor');
      }
      assertLiveResource(this, 'GPUDevice.createCommandEncoder', 'GPUDevice');
      const encoder = backend.deviceCreateCommandEncoder(this, descriptor, classes);
      encoder.label = descriptor?.label ?? '';
      return encoder;
    }

    importExternalTexture(descriptor) {
      const native = assertLiveResource(this, 'GPUDevice.importExternalTexture', 'GPUDevice');
      const textureDescriptor = assertObject(descriptor, 'GPUDevice.importExternalTexture', 'descriptor');
      if (typeof backend.deviceImportExternalTexture !== 'function') {
        failValidation(
          'GPUDevice.importExternalTexture',
          'importExternalTexture is not supported on this package surface',
        );
      }
      return backend.deviceImportExternalTexture(this, native, textureDescriptor, classes);
    }

    destroy() {
      destroyResource(this, (native) => backend.deviceDestroy(native));
    }
  }

  class DoeGPUAdapter {
    constructor(native, instance) {
      this._native = native;
      this._instance = instance;
      this._info = null;
      this.label = '';
      this.features = backend.adapterFeatures(native);
      this.limits = backend.adapterLimits(native);
      initResource(this, 'GPUAdapter');
    }

    get info() {
      if (this._info !== null) {
        return this._info;
      }
      if (typeof backend.adapterGetInfo === 'function') {
        this._info = backend.adapterGetInfo(this, this._native);
        return this._info;
      }
      this._info = Object.freeze({
        vendor: '',
        architecture: '',
        device: '',
        description: '',
        subgroupMinSize: 0,
        subgroupMaxSize: 0,
      });
      return this._info;
    }

    async requestDevice(descriptor) {
      return backend.adapterRequestDevice(this, descriptor, classes);
    }

    destroy() {
      destroyResource(this, (native) => backend.adapterDestroy(native));
    }
  }

  const WGSL_LANGUAGE_FEATURES = Object.freeze(new Set([
    'readonly-and-readwrite-storage-textures',
  ]));

  class DoeGPU {
    constructor(instance) {
      this._instance = instance;
    }

    get wgslLanguageFeatures() {
      return WGSL_LANGUAGE_FEATURES;
    }

    getPreferredCanvasFormat() {
      return 'bgra8unorm';
    }

    async requestAdapter(options) {
      return backend.gpuRequestAdapter(this, options, classes);
    }
  }

  classes = {
    DoeGPUBuffer,
    DoeGPUQueue,
    DoeGPUTexture,
    DoeGPUTextureView,
    DoeGPUSampler,
    DoeGPURenderPipeline,
    DoeGPUShaderModule,
    DoeGPUComputePipeline,
    DoeGPUBindGroupLayout,
    DoeGPUBindGroup,
    DoeGPUPipelineLayout,
    DoeGPUQuerySet,
    DoeGPUDevice,
    DoeGPUAdapter,
    DoeGPU,
  };
  return classes;
}

export {
  createFullSurfaceClasses,
};

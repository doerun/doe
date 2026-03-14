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

function createFullSurfaceClasses({
  globals,
  backend,
}) {
  let classes = null;

  class DoeGPUBuffer {
    constructor(native, instance, size, usage, queue, owner) {
      this._native = native;
      this._instance = instance;
      this._queue = queue;
      this.size = size;
      this.usage = usage;
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

    async onSubmittedWorkDone() {
      const native = assertLiveResource(this, 'GPUQueue.onSubmittedWorkDone', 'GPUQueue');
      if (!this.hasPendingSubmissions()) {
        return;
      }
      await backend.queueOnSubmittedWorkDone(this, native);
      this.markSubmittedWorkDone();
    }
  }

  class DoeGPUTexture {
    constructor(native, owner) {
      this._native = native;
      initResource(this, 'GPUTexture', owner);
    }

    createView(descriptor) {
      const view = backend.textureCreateView(this, assertLiveResource(this, 'GPUTexture.createView', 'GPUTexture'), descriptor);
      return new DoeGPUTextureView(view, this);
    }

    destroy() {
      destroyResource(this, (native) => backend.textureDestroy(native, this));
    }
  }

  class DoeGPUTextureView {
    constructor(native, owner) {
      this._native = native;
      initResource(this, 'GPUTextureView', owner);
    }
  }

  class DoeGPUSampler {
    constructor(native, owner) {
      this._native = native;
      initResource(this, 'GPUSampler', owner);
    }
  }

  class DoeGPURenderPipeline {
    constructor(native, owner) {
      this._native = native;
      initResource(this, 'GPURenderPipeline', owner);
    }
  }

  class DoeGPUShaderModule {
    constructor(native, code, owner) {
      this._native = native;
      this._code = code;
      initResource(this, 'GPUShaderModule', owner);
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
      initResource(this, 'GPUBindGroupLayout', owner);
    }
  }

  class DoeGPUBindGroup {
    constructor(native, owner) {
      this._native = native;
      initResource(this, 'GPUBindGroup', owner);
    }
  }

  class DoeGPUPipelineLayout {
    constructor(native, owner) {
      this._native = native;
      initResource(this, 'GPUPipelineLayout', owner);
    }
  }

  class DoeGPUDevice {
    constructor(native, instance, inheritedLimits = null) {
      this._native = native;
      this._instance = instance;
      initResource(this, 'GPUDevice');
      this.queue = new DoeGPUQueue(backend.deviceGetQueue(native), instance, this);
      this.limits = inheritedLimits ?? backend.deviceLimits(native);
      this.features = backend.deviceFeatures(native);
    }

    createBuffer(descriptor) {
      const validated = assertBufferDescriptor(descriptor, 'GPUDevice.createBuffer');
      const native = backend.deviceCreateBuffer(this, validated);
      return new DoeGPUBuffer(native, this._instance, validated.size, validated.usage, this.queue, this);
    }

    createShaderModule(descriptor) {
      const objectDescriptor = assertObject(descriptor, 'GPUDevice.createShaderModule', 'descriptor');
      const code = objectDescriptor.code ?? objectDescriptor.source;
      assertNonEmptyString(code, 'GPUDevice.createShaderModule', 'descriptor.code');
      const preflight = backend.preflightShaderSource(code);
      if (!preflight.ok) {
        shaderCheckFailure('GPUDevice.createShaderModule', preflight);
      }
      const native = backend.deviceCreateShaderModule(this, code);
      return new DoeGPUShaderModule(native, code, this);
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
      const native = backend.deviceCreateComputePipeline(this, shaderNative, entryPoint, layout?._native ?? null);
      return new DoeGPUComputePipeline(native, this, layout, autoLayoutEntriesByGroup);
    }

    async createComputePipelineAsync(descriptor) {
      return this.createComputePipeline(descriptor);
    }

    createBindGroupLayout(descriptor) {
      const layoutDescriptor = assertObject(descriptor, 'GPUDevice.createBindGroupLayout', 'descriptor');
      const entries = assertArray(layoutDescriptor.entries ?? [], 'GPUDevice.createBindGroupLayout', 'descriptor.entries')
        .map((entry, index) => normalizeBindGroupLayoutEntry(entry, index, 'GPUDevice.createBindGroupLayout'));
      const native = backend.deviceCreateBindGroupLayout(this, entries);
      return new DoeGPUBindGroupLayout(native, this);
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
      const native = backend.deviceCreateBindGroup(this, layoutNative, entries);
      return new DoeGPUBindGroup(native, this);
    }

    createPipelineLayout(descriptor) {
      const layoutDescriptor = assertObject(descriptor, 'GPUDevice.createPipelineLayout', 'descriptor');
      const layouts = assertArray(layoutDescriptor.bindGroupLayouts ?? [], 'GPUDevice.createPipelineLayout', 'descriptor.bindGroupLayouts')
        .map((layout, index) => assertLiveResource(layout, 'GPUDevice.createPipelineLayout', `descriptor.bindGroupLayouts[${index}]`));
      const native = backend.deviceCreatePipelineLayout(this, layouts);
      return new DoeGPUPipelineLayout(native, this);
    }

    createTexture(descriptor) {
      const textureDescriptor = assertObject(descriptor, 'GPUDevice.createTexture', 'descriptor');
      const size = assertTextureSize(textureDescriptor.size, 'GPUDevice.createTexture');
      const usage = assertIntegerInRange(textureDescriptor.usage, 'GPUDevice.createTexture', 'descriptor.usage', { min: 1 });
      const native = backend.deviceCreateTexture(this, textureDescriptor, size, usage);
      return new DoeGPUTexture(native, this);
    }

    createSampler(descriptor = {}) {
      assertObject(descriptor, 'GPUDevice.createSampler', 'descriptor');
      const native = backend.deviceCreateSampler(this, descriptor);
      return new DoeGPUSampler(native, this);
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
      return new DoeGPURenderPipeline(native, this);
    }

    createCommandEncoder(descriptor) {
      if (descriptor !== undefined) {
        assertObject(descriptor, 'GPUDevice.createCommandEncoder', 'descriptor');
      }
      assertLiveResource(this, 'GPUDevice.createCommandEncoder', 'GPUDevice');
      return backend.deviceCreateCommandEncoder(this, descriptor, classes);
    }

    destroy() {
      destroyResource(this, (native) => backend.deviceDestroy(native));
    }
  }

  class DoeGPUAdapter {
    constructor(native, instance) {
      this._native = native;
      this._instance = instance;
      this.features = backend.adapterFeatures(native);
      this.limits = backend.adapterLimits(native);
      initResource(this, 'GPUAdapter');
    }

    async requestDevice(descriptor) {
      return backend.adapterRequestDevice(this, descriptor, classes);
    }

    destroy() {
      destroyResource(this, (native) => backend.adapterDestroy(native));
    }
  }

  class DoeGPU {
    constructor(instance) {
      this._instance = instance;
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
    DoeGPUDevice,
    DoeGPUAdapter,
    DoeGPU,
  };
  return classes;
}

export {
  createFullSurfaceClasses,
};

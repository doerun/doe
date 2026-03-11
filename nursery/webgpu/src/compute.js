import * as full from './index.js';
import { doe } from './doe.js';

function unwrap(value) {
  return value && typeof value === 'object' && '_raw' in value ? value._raw : value;
}

function wrap_buffer(raw) {
  return {
    _raw: raw,
    size: raw.size,
    usage: raw.usage,
    async mapAsync(mode, offset, size) {
      return raw.mapAsync(mode, offset, size);
    },
    getMappedRange(offset, size) {
      return raw.getMappedRange(offset, size);
    },
    assertMappedPrefixF32(expected, count) {
      return raw.assertMappedPrefixF32(expected, count);
    },
    unmap() {
      return raw.unmap();
    },
    destroy() {
      return raw.destroy();
    },
  };
}

function wrap_bind_group_layout(raw) {
  return { _raw: raw };
}

function wrap_bind_group(raw) {
  return { _raw: raw };
}

function wrap_pipeline_layout(raw) {
  return { _raw: raw };
}

function wrap_compute_pipeline(raw) {
  return {
    _raw: raw,
    getBindGroupLayout(index) {
      return wrap_bind_group_layout(raw.getBindGroupLayout(index));
    },
  };
}

function wrap_compute_pass(raw) {
  return {
    _raw: raw,
    setPipeline(pipeline) {
      return raw.setPipeline(unwrap(pipeline));
    },
    setBindGroup(index, bind_group) {
      return raw.setBindGroup(index, unwrap(bind_group));
    },
    dispatchWorkgroups(x, y = 1, z = 1) {
      return raw.dispatchWorkgroups(x, y, z);
    },
    dispatchWorkgroupsIndirect(indirect_buffer, indirect_offset = 0) {
      return raw.dispatchWorkgroupsIndirect(unwrap(indirect_buffer), indirect_offset);
    },
    writeTimestamp(query_set, query_index) {
      if (typeof raw.writeTimestamp !== 'function') {
        throw new Error('timestamp query writes are unsupported on the compute surface');
      }
      return raw.writeTimestamp(unwrap(query_set), query_index);
    },
    end() {
      return raw.end();
    },
  };
}

function wrap_command_encoder(raw) {
  return {
    _raw: raw,
    beginComputePass(descriptor) {
      return wrap_compute_pass(raw.beginComputePass(descriptor));
    },
    copyBufferToBuffer(source, source_offset, target, target_offset, size) {
      return raw.copyBufferToBuffer(
        unwrap(source),
        source_offset,
        unwrap(target),
        target_offset,
        size,
      );
    },
    resolveQuerySet(query_set, first_query, query_count, destination, destination_offset) {
      if (typeof raw.resolveQuerySet !== 'function') {
        throw new Error('query resolution is unsupported on the compute surface');
      }
      return raw.resolveQuerySet(
        unwrap(query_set),
        first_query,
        query_count,
        unwrap(destination),
        destination_offset,
      );
    },
    finish() {
      return raw.finish();
    },
  };
}

function wrap_queue(raw) {
  return {
    _raw: raw,
    submit(command_buffers) {
      return raw.submit(command_buffers.map(unwrap));
    },
    writeBuffer(buffer, buffer_offset, data, data_offset, size) {
      return raw.writeBuffer(unwrap(buffer), buffer_offset, data, data_offset, size);
    },
    async onSubmittedWorkDone() {
      if (typeof raw.onSubmittedWorkDone === 'function') {
        return raw.onSubmittedWorkDone();
      }
    },
  };
}

function wrap_query_set(raw) {
  return {
    _raw: raw,
    destroy() {
      return raw.destroy();
    },
  };
}

function wrap_device(raw) {
  return {
    _raw: raw,
    queue: wrap_queue(raw.queue),
    limits: raw.limits,
    features: raw.features,
    createBuffer(descriptor) {
      return wrap_buffer(raw.createBuffer(descriptor));
    },
    createShaderModule(descriptor) {
      return raw.createShaderModule(descriptor);
    },
    createComputePipeline(descriptor) {
      return wrap_compute_pipeline(raw.createComputePipeline(descriptor));
    },
    async createComputePipelineAsync(descriptor) {
      return wrap_compute_pipeline(await raw.createComputePipelineAsync(descriptor));
    },
    createBindGroupLayout(descriptor) {
      return wrap_bind_group_layout(raw.createBindGroupLayout(descriptor));
    },
    createBindGroup(descriptor) {
      const entries = (descriptor.entries ?? []).map((entry) => ({
        ...entry,
        resource: entry.resource && typeof entry.resource === 'object' && 'buffer' in entry.resource
          ? { ...entry.resource, buffer: unwrap(entry.resource.buffer) }
          : entry.resource,
      }));
      return wrap_bind_group(raw.createBindGroup({
        ...descriptor,
        layout: unwrap(descriptor.layout),
        entries,
      }));
    },
    createPipelineLayout(descriptor) {
      return wrap_pipeline_layout(raw.createPipelineLayout({
        ...descriptor,
        bindGroupLayouts: (descriptor.bindGroupLayouts ?? []).map(unwrap),
      }));
    },
    createCommandEncoder(descriptor) {
      return wrap_command_encoder(raw.createCommandEncoder(descriptor));
    },
    createQuerySet(descriptor) {
      if (typeof raw.createQuerySet !== 'function') {
        throw new Error('query sets are unsupported on the compute surface');
      }
      return wrap_query_set(raw.createQuerySet(descriptor));
    },
    destroy() {
      return raw.destroy();
    },
  };
}

function wrap_adapter(raw) {
  return {
    _raw: raw,
    features: raw.features,
    limits: raw.limits,
    async requestDevice(descriptor) {
      return wrap_device(await raw.requestDevice(descriptor));
    },
    destroy() {
      return raw.destroy();
    },
  };
}

function wrap_gpu(raw) {
  return {
    _raw: raw,
    async requestAdapter(options) {
      return wrap_adapter(await raw.requestAdapter(options));
    },
  };
}

export const globals = full.globals;

export function create(create_args = null) {
  return wrap_gpu(full.create(create_args));
}

export function setupGlobals(target = globalThis, create_args = null) {
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
  const gpu = create(create_args);
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

export async function requestAdapter(adapter_options = undefined, create_args = null) {
  return create(create_args).requestAdapter(adapter_options);
}

export async function requestDevice(options = {}) {
  const adapter = await requestAdapter(options?.adapterOptions, options?.createArgs ?? null);
  return adapter.requestDevice(options?.deviceDescriptor);
}

export const providerInfo = full.providerInfo;
export const createDoeRuntime = full.createDoeRuntime;
export const runDawnVsDoeCompare = full.runDawnVsDoeCompare;

export default {
  create,
  globals,
  setupGlobals,
  requestAdapter,
  requestDevice,
  providerInfo,
  createDoeRuntime,
  runDawnVsDoeCompare,
  doe,
};

export { doe };

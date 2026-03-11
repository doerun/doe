const DOE_GPU_BUFFER_USAGE = {
  MAP_READ: 0x0001,
  COPY_SRC: 0x0004,
  COPY_DST: 0x0008,
  UNIFORM: 0x0040,
  STORAGE: 0x0080,
};

const DOE_GPU_SHADER_STAGE = {
  COMPUTE: 0x4,
};

const DOE_GPU_MAP_MODE = {
  READ: 0x0001,
};

const DOE_BUFFER_META = new WeakMap();

function resolve_buffer_usage_token(token) {
  switch (token) {
    case 'upload':
      return DOE_GPU_BUFFER_USAGE.COPY_DST;
    case 'readback':
      return DOE_GPU_BUFFER_USAGE.COPY_SRC | DOE_GPU_BUFFER_USAGE.COPY_DST | DOE_GPU_BUFFER_USAGE.MAP_READ;
    case 'uniform':
      return DOE_GPU_BUFFER_USAGE.UNIFORM | DOE_GPU_BUFFER_USAGE.COPY_DST;
    case 'storage-read':
      return DOE_GPU_BUFFER_USAGE.STORAGE | DOE_GPU_BUFFER_USAGE.COPY_DST;
    case 'storage-readwrite':
      return DOE_GPU_BUFFER_USAGE.STORAGE | DOE_GPU_BUFFER_USAGE.COPY_DST | DOE_GPU_BUFFER_USAGE.COPY_SRC;
    default:
      throw new Error(`Unknown Doe buffer usage token: ${token}`);
  }
}

function resolve_buffer_usage(usage) {
  if (typeof usage === 'number') return usage;
  if (typeof usage === 'string') return resolve_buffer_usage_token(usage);
  if (Array.isArray(usage)) {
    return usage.reduce((mask, token) => mask | resolve_buffer_usage_token(token), 0);
  }
  throw new Error('Doe buffer usage must be a number, string, or string array.');
}

function infer_binding_access_token(token) {
  switch (token) {
    case 'uniform':
      return 'uniform';
    case 'storage-read':
      return 'storage-read';
    case 'storage-readwrite':
      return 'storage-readwrite';
    default:
      return null;
  }
}

function infer_binding_access(usage) {
  if (typeof usage === 'number' || usage == null) return null;
  const tokens = typeof usage === 'string'
    ? [usage]
    : Array.isArray(usage)
      ? usage
      : null;
  if (!tokens) {
    throw new Error('Doe buffer usage must be a number, string, or string array.');
  }
  const inferred = [...new Set(tokens.map(infer_binding_access_token).filter(Boolean))];
  if (inferred.length > 1) {
    throw new Error(`Doe buffer usage cannot imply multiple binding access modes: ${inferred.join(', ')}`);
  }
  return inferred[0] ?? null;
}

function remember_buffer_usage(buffer, usage) {
  DOE_BUFFER_META.set(buffer, {
    binding_access: infer_binding_access(usage),
  });
  return buffer;
}

function inferred_binding_access_for_buffer(buffer) {
  return DOE_BUFFER_META.get(buffer)?.binding_access ?? null;
}

function normalize_workgroups(workgroups) {
  if (typeof workgroups === 'number') {
    return [workgroups, 1, 1];
  }
  if (Array.isArray(workgroups) && workgroups.length === 3) {
    return workgroups;
  }
  throw new Error('Doe workgroups must be a number or a [x, y, z] tuple.');
}

function normalize_data_view(data) {
  if (ArrayBuffer.isView(data)) {
    return new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
  }
  if (data instanceof ArrayBuffer) {
    return new Uint8Array(data);
  }
  throw new Error('Doe buffer data must be an ArrayBuffer or ArrayBufferView.');
}

function normalize_binding(binding, index) {
  const entry = binding && typeof binding === 'object' && 'buffer' in binding
    ? binding
    : { buffer: binding };
  const access = entry.access ?? inferred_binding_access_for_buffer(entry.buffer);
  if (!access) {
    throw new Error(
      'Doe binding access is required for buffers without Doe helper usage metadata. ' +
      'Pass { buffer, access } or create the buffer through doe.createBuffer* with a bindable usage token.'
    );
  }
  return {
    binding: index,
    buffer: entry.buffer,
    access,
  };
}

function bind_group_layout_entry(binding) {
  const buffer_type = binding.access === 'uniform'
    ? 'uniform'
    : binding.access === 'storage-read'
      ? 'read-only-storage'
      : 'storage';
  return {
    binding: binding.binding,
    visibility: DOE_GPU_SHADER_STAGE.COMPUTE,
    buffer: { type: buffer_type },
  };
}

function bind_group_entry(binding) {
  return {
    binding: binding.binding,
    resource: { buffer: binding.buffer },
  };
}

class DoeKernel {
  constructor(device, pipeline, layout, entry_point) {
    this.device = device;
    this.pipeline = pipeline;
    this.layout = layout;
    this.entryPoint = entry_point;
  }

  async dispatch(options) {
    const bindings = (options.bindings ?? []).map(normalize_binding);
    const workgroups = normalize_workgroups(options.workgroups);
    const bind_group = this.device.createBindGroup({
      label: options.label ?? undefined,
      layout: this.layout,
      entries: bindings.map(bind_group_entry),
    });
    const encoder = this.device.createCommandEncoder({ label: options.label ?? undefined });
    const pass = encoder.beginComputePass({ label: options.label ?? undefined });
    pass.setPipeline(this.pipeline);
    if (bindings.length > 0) {
      pass.setBindGroup(0, bind_group);
    }
    pass.dispatchWorkgroups(workgroups[0], workgroups[1], workgroups[2]);
    pass.end();
    this.device.queue.submit([encoder.finish()]);
    if (typeof this.device.queue.onSubmittedWorkDone === 'function') {
      await this.device.queue.onSubmittedWorkDone();
    }
  }
}

function create_bound_doe(device) {
  return {
    device,
    createBuffer(options) {
      return doe.createBuffer(device, options);
    },
    createBufferFromData(data, options = {}) {
      return doe.createBufferFromData(device, data, options);
    },
    readBuffer(buffer, type, options = {}) {
      return doe.readBuffer(device, buffer, type, options);
    },
    runCompute(options) {
      return doe.runCompute(device, options);
    },
    compileCompute(options) {
      return doe.compileCompute(device, options);
    },
  };
}

function compile_compute(device, options) {
  const bindings = (options.bindings ?? []).map(normalize_binding);
  const shader = device.createShaderModule({ code: options.code });
  const bind_group_layout = device.createBindGroupLayout({
    entries: bindings.map(bind_group_layout_entry),
  });
  const pipeline_layout = device.createPipelineLayout({
    bindGroupLayouts: [bind_group_layout],
  });
  const pipeline = device.createComputePipeline({
    layout: pipeline_layout,
    compute: {
      module: shader,
      entryPoint: options.entryPoint ?? 'main',
    },
  });
  return new DoeKernel(device, pipeline, bind_group_layout, options.entryPoint ?? 'main');
}

export const doe = {
  bind(device) {
    return create_bound_doe(device);
  },

  createBuffer(device, options) {
    return remember_buffer_usage(device.createBuffer({
      label: options.label ?? undefined,
      size: options.size,
      usage: resolve_buffer_usage(options.usage),
      mappedAtCreation: options.mappedAtCreation ?? false,
    }), options.usage);
  },

  createBufferFromData(device, data, options = {}) {
    const view = normalize_data_view(data);
    const usage = options.usage ?? 'storage-read';
    const buffer = remember_buffer_usage(device.createBuffer({
      label: options.label ?? undefined,
      size: view.byteLength,
      usage: resolve_buffer_usage(usage),
    }), usage);
    device.queue.writeBuffer(buffer, 0, view);
    return buffer;
  },

  async readBuffer(device, buffer, type, options = {}) {
    const offset = options.offset ?? 0;
    const size = options.size ?? Math.max(0, (buffer.size ?? 0) - offset);
    const staging = device.createBuffer({
      label: options.label ?? undefined,
      size,
      usage: DOE_GPU_BUFFER_USAGE.COPY_DST | DOE_GPU_BUFFER_USAGE.MAP_READ,
    });
    const encoder = device.createCommandEncoder({ label: options.label ?? undefined });
    encoder.copyBufferToBuffer(buffer, offset, staging, 0, size);
    device.queue.submit([encoder.finish()]);
    await staging.mapAsync(DOE_GPU_MAP_MODE.READ);
    const copy = staging.getMappedRange().slice(0);
    staging.unmap();
    if (typeof staging.destroy === 'function') {
      staging.destroy();
    }
    return new type(copy);
  },

  async runCompute(device, options) {
    const kernel = compile_compute(device, options);
    await kernel.dispatch({
      bindings: options.bindings ?? [],
      workgroups: options.workgroups,
      label: options.label,
    });
  },

  compileCompute(device, options) {
    return compile_compute(device, options);
  },
};

export default doe;

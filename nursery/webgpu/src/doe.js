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

function resolveBufferUsageToken(token, combined = false) {
  switch (token) {
    case 'upload':
      return DOE_GPU_BUFFER_USAGE.COPY_DST;
    case 'readback':
      return combined
        ? DOE_GPU_BUFFER_USAGE.COPY_SRC
        : DOE_GPU_BUFFER_USAGE.COPY_SRC | DOE_GPU_BUFFER_USAGE.COPY_DST | DOE_GPU_BUFFER_USAGE.MAP_READ;
    case 'uniform':
      return DOE_GPU_BUFFER_USAGE.UNIFORM | DOE_GPU_BUFFER_USAGE.COPY_DST;
    case 'storageRead':
      return DOE_GPU_BUFFER_USAGE.STORAGE | DOE_GPU_BUFFER_USAGE.COPY_DST;
    case 'storageReadWrite':
      return DOE_GPU_BUFFER_USAGE.STORAGE | DOE_GPU_BUFFER_USAGE.COPY_DST | DOE_GPU_BUFFER_USAGE.COPY_SRC;
    default:
      throw new Error(`Unknown Doe buffer usage token: ${token}`);
  }
}

function resolveBufferUsage(usage) {
  if (typeof usage === 'number') return usage;
  if (typeof usage === 'string') return resolveBufferUsageToken(usage);
  if (Array.isArray(usage)) {
    const combined = usage.length > 1;
    return usage.reduce((mask, token) => mask | (
      typeof token === 'number'
        ? token
        : resolveBufferUsageToken(token, combined)
    ), 0);
  }
  throw new Error('Doe buffer usage must be a number, string, or string array.');
}

function inferBindingAccessToken(token) {
  switch (token) {
    case 'uniform':
      return 'uniform';
    case 'storageRead':
      return 'storageRead';
    case 'storageReadWrite':
      return 'storageReadWrite';
    default:
      return null;
  }
}

function inferBindingAccess(usage) {
  if (typeof usage === 'number' || usage == null) return null;
  const tokens = typeof usage === 'string'
    ? [usage]
    : Array.isArray(usage)
      ? usage.filter((token) => typeof token !== 'number')
      : null;
  if (!tokens) {
    throw new Error('Doe buffer usage must be a number, string, or string array.');
  }
  const inferred = [...new Set(tokens.map(inferBindingAccessToken).filter(Boolean))];
  if (inferred.length > 1) {
    throw new Error(`Doe buffer usage cannot imply multiple binding access modes: ${inferred.join(', ')}`);
  }
  return inferred[0] ?? null;
}

function rememberBufferUsage(buffer, usage) {
  DOE_BUFFER_META.set(buffer, {
    bindingAccess: inferBindingAccess(usage),
  });
  return buffer;
}

function inferredBindingAccessForBuffer(buffer) {
  return DOE_BUFFER_META.get(buffer)?.bindingAccess ?? null;
}

function normalizeWorkgroups(workgroups) {
  if (typeof workgroups === 'number') {
    return [workgroups, 1, 1];
  }
  if (Array.isArray(workgroups) && workgroups.length === 2) {
    return [workgroups[0], workgroups[1], 1];
  }
  if (Array.isArray(workgroups) && workgroups.length === 3) {
    return workgroups;
  }
  throw new Error('Doe workgroups must be a number, [x, y], or [x, y, z].');
}

function validatePositiveInteger(value, label) {
  if (!Number.isInteger(value) || value < 1) {
    throw new Error(`${label} must be a positive integer.`);
  }
}

function validateWorkgroups(device, workgroups) {
  const normalized = normalizeWorkgroups(workgroups);
  const limits = device?.limits ?? {};
  const [x, y, z] = normalized;

  validatePositiveInteger(x, 'Doe workgroups.x');
  validatePositiveInteger(y, 'Doe workgroups.y');
  validatePositiveInteger(z, 'Doe workgroups.z');

  if (limits.maxComputeWorkgroupsPerDimension) {
    if (x > limits.maxComputeWorkgroupsPerDimension ||
        y > limits.maxComputeWorkgroupsPerDimension ||
        z > limits.maxComputeWorkgroupsPerDimension) {
      throw new Error(
        `Doe workgroups exceed maxComputeWorkgroupsPerDimension (${limits.maxComputeWorkgroupsPerDimension}).`
      );
    }
  }
  if (limits.maxComputeWorkgroupSizeX && x > limits.maxComputeWorkgroupSizeX) {
    throw new Error(
      `Doe workgroups.x (${x}) exceeds maxComputeWorkgroupSizeX (${limits.maxComputeWorkgroupSizeX}).`
    );
  }
  if (limits.maxComputeWorkgroupSizeY && y > limits.maxComputeWorkgroupSizeY) {
    throw new Error(
      `Doe workgroups.y (${y}) exceeds maxComputeWorkgroupSizeY (${limits.maxComputeWorkgroupSizeY}).`
    );
  }
  if (limits.maxComputeWorkgroupSizeZ && z > limits.maxComputeWorkgroupSizeZ) {
    throw new Error(
      `Doe workgroups.z (${z}) exceeds maxComputeWorkgroupSizeZ (${limits.maxComputeWorkgroupSizeZ}).`
    );
  }
  if (limits.maxComputeInvocationsPerWorkgroup) {
    const invocations = x * y * z;
    if (invocations > limits.maxComputeInvocationsPerWorkgroup) {
      throw new Error(
        `Doe workgroups (${invocations} invocations) exceed maxComputeInvocationsPerWorkgroup (${limits.maxComputeInvocationsPerWorkgroup}).`
      );
    }
  }

  return normalized;
}

function normalizeDataView(data) {
  if (ArrayBuffer.isView(data)) {
    return new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
  }
  if (data instanceof ArrayBuffer) {
    return new Uint8Array(data);
  }
  throw new Error('Doe buffer data must be an ArrayBuffer or ArrayBufferView.');
}

function resolveBufferSize(source) {
  if (source && typeof source === 'object' && typeof source.size === 'number') {
    return source.size;
  }
  if (ArrayBuffer.isView(source)) {
    return source.byteLength;
  }
  if (source instanceof ArrayBuffer) {
    return source.byteLength;
  }
  throw new Error('Doe buffer-like source must expose a byte size or be ArrayBuffer-backed data.');
}

function normalizeBinding(binding, index) {
  const entry = binding && typeof binding === 'object' && 'buffer' in binding
    ? binding
    : { buffer: binding };
  const access = entry.access ?? inferredBindingAccessForBuffer(entry.buffer);
  if (!access) {
    throw new Error(
      'Doe binding access is required for buffers without Doe helper usage metadata. ' +
      'Pass { buffer, access } or create the buffer through gpu.buffer.* with a bindable usage token.'
    );
  }
  return {
    binding: index,
    buffer: entry.buffer,
    access,
  };
}

function bindGroupLayoutEntry(binding) {
  const buffer_type = binding.access === 'uniform'
    ? 'uniform'
    : binding.access === 'storageRead'
      ? 'read-only-storage'
      : 'storage';
  return {
    binding: binding.binding,
    visibility: DOE_GPU_SHADER_STAGE.COMPUTE,
    buffer: { type: buffer_type },
  };
}

function bindGroupEntry(binding) {
  return {
    binding: binding.binding,
    resource: { buffer: binding.buffer },
  };
}

/**
 * Reusable compute kernel compiled by `gpu.kernel.create(...)`.
 *
 * Surface: Doe API `gpu.kernel`.
 * Input: Created from WGSL source, an entry point, and an initial binding shape.
 * Returns: A reusable kernel object with `dispatch(...)`.
 *
 * This object keeps the compiled pipeline and bind-group layout for a repeated
 * WGSL compute shape. Use it when you will dispatch the same shader more than
 * once and want to avoid recompiling on every call.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * const kernel = gpu.kernel.create({
 *   code,
 *   bindings: [src, dst],
 * });
 *
 * await kernel.dispatch({
 *   bindings: [src, dst],
 *   workgroups: 1,
 * });
 * ```
 *
 * - See `gpu.kernel.run(...)` for the one-shot explicit path.
 * - See `gpu.compute.once(...)` for the narrower typed-array workflow.
 * - Instances are returned through the bound Doe API and are not exported directly.
 */
class DoeKernel {
  constructor(device, pipeline, layout, entryPoint) {
    this.device = device;
    this.pipeline = pipeline;
    this.layout = layout;
    this.entryPoint = entryPoint;
  }

  /**
   * Dispatch this compiled kernel once.
   *
   * Surface: Doe API `gpu.kernel`.
   * Input: A binding list, workgroup counts, and an optional label.
   * Returns: A promise that resolves after submission completes.
   *
   * This records one compute pass for the compiled pipeline, submits it, and
   * waits for completion when the underlying queue exposes
   * `onSubmittedWorkDone()`.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * await kernel.dispatch({
   *   bindings: [src, dst],
   *   workgroups: [4, 1, 1],
   * });
   * ```
   *
   * - `workgroups` may be `number`, `[x, y]`, or `[x, y, z]`.
   * - Bare buffers without Doe helper metadata require `{ buffer, access }`.
   * - See `gpu.kernel.run(...)` when you do not need reuse.
   */
  async dispatch(options) {
    const bindings = (options.bindings ?? []).map(normalizeBinding);
    const workgroups = validateWorkgroups(this.device, options.workgroups);
    const bindGroup = this.device.createBindGroup({
      label: options.label ?? undefined,
      layout: this.layout,
      entries: bindings.map(bindGroupEntry),
    });
    const encoder = this.device.createCommandEncoder({ label: options.label ?? undefined });
    const pass = encoder.beginComputePass({ label: options.label ?? undefined });
    pass.setPipeline(this.pipeline);
    if (bindings.length > 0) {
      pass.setBindGroup(0, bindGroup);
    }
    pass.dispatchWorkgroups(workgroups[0], workgroups[1], workgroups[2]);
    pass.end();
    this.device.queue.submit([encoder.finish()]);
    if (typeof this.device.queue.onSubmittedWorkDone === 'function') {
      await this.device.queue.onSubmittedWorkDone();
    }
  }
}

function createKernel(device, options) {
  const bindings = (options.bindings ?? []).map(normalizeBinding);
  const shader = device.createShaderModule({ code: options.code });
  const bindGroupLayout = device.createBindGroupLayout({
    entries: bindings.map(bindGroupLayoutEntry),
  });
  const pipelineLayout = device.createPipelineLayout({
    bindGroupLayouts: [bindGroupLayout],
  });
  const pipeline = device.createComputePipeline({
    layout: pipelineLayout,
    compute: {
      module: shader,
      entryPoint: options.entryPoint ?? 'main',
    },
  });
  return new DoeKernel(device, pipeline, bindGroupLayout, options.entryPoint ?? 'main');
}

function createBuffer(device, options) {
  if (!options || typeof options !== 'object') {
    throw new Error('Doe buffer options must be an object.');
  }
  validatePositiveInteger(options.size, 'Doe buffer size');
  return rememberBufferUsage(device.createBuffer({
    label: options.label ?? undefined,
    size: options.size,
    usage: resolveBufferUsage(options.usage),
    mappedAtCreation: options.mappedAtCreation ?? false,
  }), options.usage);
}

function createBufferFromData(device, data, options = {}) {
  const view = normalizeDataView(data);
  const usage = options.usage ?? 'storageRead';
  const buffer = rememberBufferUsage(device.createBuffer({
    label: options.label ?? undefined,
    size: view.byteLength,
    usage: resolveBufferUsage(usage),
  }), usage);
  device.queue.writeBuffer(buffer, 0, view);
  return buffer;
}

function createBufferLike(device, source, options = {}) {
  return createBuffer(device, {
    ...options,
    size: options.size ?? resolveBufferSize(source),
  });
}

async function readBuffer(device, buffer, type, options = {}) {
  if (typeof type !== 'function') {
    throw new Error('Doe readBuffer type must be a typed-array constructor.');
  }
  const offset = options.offset ?? 0;
  const size = options.size ?? Math.max(0, (buffer.size ?? 0) - offset);
  if (!Number.isInteger(offset) || offset < 0) {
    throw new Error('Doe readBuffer offset must be a non-negative integer.');
  }
  if (!Number.isInteger(size) || size < 0) {
    throw new Error('Doe readBuffer size must be a non-negative integer.');
  }
  if (((buffer.usage ?? 0) & DOE_GPU_BUFFER_USAGE.MAP_READ) !== 0) {
    await buffer.mapAsync(DOE_GPU_MAP_MODE.READ, offset, size);
    const copy = buffer.getMappedRange(offset, size).slice(0);
    buffer.unmap();
    return new type(copy);
  }
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
}

async function runKernel(device, options) {
  const kernel = createKernel(device, options);
  await kernel.dispatch({
    bindings: options.bindings ?? [],
    workgroups: options.workgroups,
    label: options.label,
  });
}

function usesRawNumericFlags(usage) {
  return typeof usage === 'number' || (Array.isArray(usage) && usage.some((token) => typeof token === 'number'));
}

function assertLayer3Usage(usage, access, path) {
  if (usesRawNumericFlags(usage) && !access) {
    throw new Error(`Doe ${path} accepts raw numeric usage flags only when explicit access is also provided.`);
  }
}

function normalizeOnceInput(device, input, index) {
  if (ArrayBuffer.isView(input) || input instanceof ArrayBuffer) {
    const buffer = createBufferFromData(device, input, {});
    return {
      binding: buffer,
      buffer,
      byte_length: resolveBufferSize(input),
      owned: true,
    };
  }

  if (input && typeof input === 'object' && 'data' in input) {
    assertLayer3Usage(input.usage, input.access, `compute.once input ${index} usage`);
    const buffer = createBufferFromData(device, input.data, {
      usage: input.usage ?? 'storageRead',
      label: input.label,
    });
    return {
      binding: input.access ? { buffer, access: input.access } : buffer,
      buffer,
      byte_length: resolveBufferSize(input.data),
      owned: true,
    };
  }

  if (input && typeof input === 'object' && 'buffer' in input) {
    return {
      binding: input,
      buffer: input.buffer,
      byte_length: resolveBufferSize(input.buffer),
      owned: false,
    };
  }

  if (input && typeof input === 'object' && typeof input.size === 'number') {
    return {
      binding: input,
      buffer: input,
      byte_length: input.size,
      owned: false,
    };
  }

  throw new Error(`Doe compute.once input ${index} must be data, a Doe input spec, or a buffer.`);
}

function normalizeOnceOutput(device, output, inputs) {
  if (!output || typeof output !== 'object') {
    throw new Error('Doe compute.once output is required.');
  }
  if (typeof output.type !== 'function') {
    throw new Error('Doe compute.once output.type must be a typed-array constructor.');
  }

  const fallbackInputIndex = inputs.length > 0 ? 0 : null;
  const likeInputIndex = output.likeInput ?? fallbackInputIndex;
  if (likeInputIndex != null && (!Number.isInteger(likeInputIndex) || likeInputIndex < 0 || likeInputIndex >= inputs.length)) {
    throw new Error(`Doe compute.once output.likeInput must reference an input index in [0, ${Math.max(inputs.length - 1, 0)}].`);
  }
  const size = output.size ?? (
    likeInputIndex != null && inputs[likeInputIndex]
      ? inputs[likeInputIndex].byte_length
      : null
  );

  if (!(size > 0)) {
    throw new Error('Doe compute.once output size must be provided or derived from likeInput.');
  }

  assertLayer3Usage(output.usage, output.access, 'compute.once output usage');
  const buffer = createBuffer(device, {
    size,
    usage: output.usage ?? 'storageReadWrite',
    label: output.label,
  });
  return {
    binding: output.access ? { buffer, access: output.access } : buffer,
    buffer,
    type: output.type,
    read_options: output.read ?? {},
  };
}

async function computeOnce(device, options) {
  const inputs = (options.inputs ?? []).map((input, index) => normalizeOnceInput(device, input, index));
  const output = normalizeOnceOutput(device, options.output, inputs);
  validateWorkgroups(device, options.workgroups);
  try {
    await runKernel(device, {
      code: options.code,
      entryPoint: options.entryPoint,
      bindings: [...inputs.map((input) => input.binding), output.binding],
      workgroups: options.workgroups,
      label: options.label,
    });
    return await readBuffer(device, output.buffer, output.type, output.read_options);
  } finally {
    if (typeof output.buffer.destroy === 'function') {
      output.buffer.destroy();
    }
    for (const input of inputs) {
      if (input.owned && typeof input.buffer.destroy === 'function') {
        input.buffer.destroy();
      }
    }
  }
}

function createBoundDoe(device) {
  return {
    device,
    buffer: {
      /**
       * Create a buffer with explicit size and Doe usage tokens.
       *
       * Surface: Doe API `gpu.buffer`.
       * Input: A buffer size, usage, and optional label or mapping flag.
       * Returns: A GPU buffer with Doe usage metadata attached when possible.
       *
       * This is the explicit Doe helper over `device.createBuffer(...)`. It
       * accepts Doe usage tokens such as `storageReadWrite` and remembers the
       * resulting binding access so later Doe API calls can infer how the
       * buffer should be bound.
       *
       * This example shows the API in its basic form.
       *
       * ```js
       * const dst = gpu.buffer.create({
       *   size: 1024,
       *   usage: "storageReadWrite",
       * });
       * ```
       *
       * - Raw numeric usage flags are allowed here for explicit control.
       * - Buffers created with raw numeric flags may later require `{ buffer, access }`.
       * - See `gpu.buffer.fromData(...)` to create and upload in one step.
       */
      create(options) {
        return createBuffer(device, options);
      },
      /**
       * Create a buffer from host data and upload it immediately.
       *
       * Surface: Doe API `gpu.buffer`.
       * Input: An `ArrayBuffer` or typed-array view plus optional usage and label.
       * Returns: A GPU buffer initialized with the provided bytes.
       *
       * This helper allocates a buffer, writes the provided host data into it,
       * and records Doe usage metadata for later binding inference.
       *
       * This example shows the API in its basic form.
       *
       * ```js
       * const src = gpu.buffer.fromData(new Float32Array([1, 2, 3, 4]));
       * ```
       *
       * - Defaults to `storageRead` usage when none is provided.
       * - Raw numeric usage flags are allowed, but they may disable Doe access inference.
       * - See `gpu.buffer.create(...)` when you need an uninitialized buffer.
       */
      fromData(data, options = {}) {
        return createBufferFromData(device, data, options);
      },
      /**
       * Create a buffer sized from another buffer or host-data source.
       *
       * Surface: Doe API `gpu.buffer`.
       * Input: A buffer-like source and optional overrides such as `usage` or `size`.
       * Returns: A new GPU buffer whose size defaults from the source.
       *
       * This removes common `size: src.size` boilerplate when you need an
       * output or scratch buffer that matches an existing source.
       *
       * This example shows the API in its basic form.
       *
       * ```js
       * const dst = gpu.buffer.like(src, { usage: "storageReadWrite" });
       * ```
       *
       * - `source` may be a GPU buffer, a typed array, or an `ArrayBuffer`.
       * - If the source has no byte size, this throws instead of guessing.
       * - See `gpu.buffer.create(...)` for fully explicit allocation.
       */
      like(source, options = {}) {
        return createBufferLike(device, source, options);
      },
      /**
       * Read a buffer back into a typed array.
       *
       * Surface: Doe API `gpu.buffer`.
       * Input: A source buffer, a typed-array constructor, and optional offset or size.
       * Returns: A promise for a newly allocated typed array.
       *
       * This reads GPU buffer contents back to JS. If the buffer is already
       * mappable for read, Doe maps it directly; otherwise Doe stages the copy
       * through a temporary readback buffer.
       *
       * This example shows the API in its basic form.
       *
       * ```js
       * const out = await gpu.buffer.read(dst, Float32Array);
       * ```
       *
       * - `options.offset` and `options.size` let you read a subrange.
       * - The typed-array constructor must accept a plain `ArrayBuffer`.
       * - See raw `buffer.mapAsync(...)` when you need manual readback control.
       */
      read(buffer, type, options = {}) {
        return readBuffer(device, buffer, type, options);
      },
    },
    kernel: {
      /**
       * Compile and dispatch a one-off compute job.
       *
       * Surface: Doe API `gpu.kernel`.
       * Input: WGSL source, bindings, workgroups, and an optional entry point or label.
       * Returns: A promise that resolves after submission completes.
       *
       * This is the explicit one-shot compute path. It builds the pipeline for
       * the provided shader, dispatches once, and waits for completion.
       *
       * This example shows the API in its basic form.
       *
       * ```js
       * await gpu.kernel.run({
       *   code,
       *   bindings: [src, dst],
       *   workgroups: 1,
       * });
       * ```
       *
       * - `workgroups` may be `number`, `[x, y]`, or `[x, y, z]`.
       * - Bare buffers without Doe helper metadata require `{ buffer, access }`.
       * - See `gpu.kernel.create(...)` when you will reuse the shader shape.
       * - See `gpu.compute.once(...)` for the narrower typed-array workflow.
       */
      run(options) {
        return runKernel(device, options);
      },
      /**
       * Compile a reusable compute kernel.
       *
       * Surface: Doe API `gpu.kernel`.
       * Input: WGSL source, an optional entry point, and an initial binding shape.
       * Returns: A `DoeKernel` object with `dispatch(...)`.
       *
       * This creates the shader module, bind-group layout, and compute
       * pipeline once so the same WGSL shape can be dispatched repeatedly.
       *
       * This example shows the API in its basic form.
       *
       * ```js
       * const kernel = gpu.kernel.create({
       *   code,
       *   bindings: [src, dst],
       * });
       * ```
       *
       * - Binding access is inferred from the bindings passed at compile time.
       * - See `kernel.dispatch(...)` to run the compiled kernel.
       * - See `gpu.kernel.run(...)` when reuse does not matter.
       */
      create(options) {
        return createKernel(device, options);
      },
    },
    compute: {
      /**
       * Run a one-shot typed-array compute workflow.
       *
       * Surface: Doe API `gpu.compute`.
       * Input: WGSL source, typed-array or buffer inputs, an output spec, and workgroups.
       * Returns: A promise for the requested typed-array output.
       *
       * This is the most opinionated Doe helper. It creates temporary buffers
       * as needed, uploads host data, dispatches the compute shader once,
       * reads back the requested output, and destroys temporary resources
       * before returning.
       *
       * This example shows the API in its basic form.
       *
       * ```js
       * const out = await gpu.compute.once({
       *   code,
       *   inputs: [new Float32Array([1, 2, 3, 4])],
       *   output: { type: Float32Array },
       *   workgroups: 1,
       * });
       * ```
       *
       * - Raw numeric usage flags are accepted only when explicit Doe access is also provided.
       * - Output size defaults from `likeInput` or the first input when possible.
       * - See `gpu.kernel.run(...)` or `gpu.kernel.create(...)` when you need explicit resource ownership.
       */
      once(options) {
        return computeOnce(device, options);
      },
    },
  };
}

export function createDoeNamespace({ requestDevice } = {}) {
  return {
    /**
     * Request a device and return the bound Doe API in one step.
     *
     * Surface: Doe API namespace.
     * Input: Optional package-local request options.
     * Returns: A promise for the bound `gpu` helper object.
     *
     * This calls the package-local `requestDevice(...)` implementation and
     * then wraps the resulting raw device in the bound Doe API.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * const gpu = await doe.requestDevice();
     * ```
     *
     * - Throws if this namespace was created without a `requestDevice` implementation.
     * - `gpu.device` exposes the underlying raw device when you need lower-level control.
     * - See `doe.bind(device)` when you already have a raw device.
     */
    async requestDevice(options = {}) {
      if (typeof requestDevice !== 'function') {
        throw new Error('Doe requestDevice() is unavailable in this context.');
      }
      return createBoundDoe(await requestDevice(options));
    },

    /**
     * Wrap an existing device in the bound Doe API.
     *
     * Surface: Doe API namespace.
     * Input: A raw device returned by the package surface.
     * Returns: The bound `gpu` helper object for that device.
     *
     * Use this when you need the raw device first, but still want to opt into
     * Doe helpers afterward.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * const device = await requestDevice();
     * const gpu = doe.bind(device);
     * ```
     *
     * - No async work happens here; it only wraps the device you already have.
     * - See `doe.requestDevice(...)` for the one-step helper entrypoint.
     */
    bind(device) {
      return createBoundDoe(device);
    },
  };
}

export const doe = createDoeNamespace();

export default doe;

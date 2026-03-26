import { createHash } from 'node:crypto';
import { existsSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { basename, extname, resolve } from 'node:path';

const ALLOWED_BUFFER_USAGES = new Set([
  'storage',
  'copy_dst',
  'copy_src',
  'map_read',
  'map_write',
  'uniform',
]);

const ALLOWED_DATA_KINDS = new Set(['u8', 'u32', 'f32', 'bytes', 'utf8']);
const ALLOWED_STEP_KINDS = new Set(['writeBuffer', 'dispatch', 'copyBufferToBuffer', 'readBuffer']);
const ALLOWED_BINDING_BUFFER_TYPES = new Set(['storage', 'read-only-storage', 'uniform']);
const BUFFER_USAGE_ORDER = ['storage', 'copy_dst', 'copy_src', 'map_read', 'map_write', 'uniform'];
const REPO_ROOT = resolve(fileURLToPath(new URL('../../..', import.meta.url)));

function isPlainObject(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function stableStringify(value) {
  if (value === undefined) {
    return 'null';
  }
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((entry) => stableStringify(entry)).join(',')}]`;
  }
  const entries = Object.keys(value)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`);
  return `{${entries.join(',')}}`;
}

function sha256Text(text) {
  return createHash('sha256').update(text, 'utf8').digest('hex');
}

function loadJsonFile(path) {
  return readFile(path, 'utf8').then((text) => JSON.parse(text));
}

function normalizeCommandBindingType(value) {
  const normalized = typeof value === 'string' ? value.trim().toLowerCase() : '';
  if (normalized === 'readonly' || normalized === 'read-only-storage') {
    return 'read-only-storage';
  }
  if (normalized === 'uniform') {
    return 'uniform';
  }
  return 'storage';
}

function inferKernelSourcePath(kernel) {
  const candidates = [
    resolve(REPO_ROOT, 'bench/inference-pipeline/kernels', kernel),
    resolve(REPO_ROOT, 'bench/kernels', kernel),
  ];
  for (const candidate of candidates) {
    if (existsSync(candidate)) {
      return candidate.slice(REPO_ROOT.length + 1);
    }
  }
  return `bench/inference-pipeline/kernels/${kernel}`;
}

function commandPlanToNeutralPlan(plan) {
  const commands = Array.isArray(plan.commands) ? plan.commands : [];
  const buffers = new Map();
  const modules = new Map();
  const steps = [];

  function ensureBuffer(handle, size, options = {}) {
    const { bindingType = '', writable = false } = options;
    const id = `buffer_${handle}`;
    const existing = buffers.get(id) ?? {
      id,
      size,
      usage: new Set(),
    };
    existing.size = Math.max(existing.size, size);
    if (bindingType === 'uniform') {
      existing.usage.add('uniform');
    } else if (bindingType) {
      existing.usage.add('storage');
    }
    if (writable) {
      existing.usage.add('copy_dst');
    }
    buffers.set(id, existing);
    return id;
  }

  commands.forEach((command, index) => {
    if (!isPlainObject(command)) {
      return;
    }
    const kind = typeof command.kind === 'string' ? command.kind : '';
    if (kind === 'buffer_write') {
      const handle = Number(command.handle);
      const bufferSize = Number(command.bufferSize ?? 0);
      const values = Array.isArray(command.data)
        ? command.data.map((value) => Number(value) >>> 0)
        : [];
      const bufferId = ensureBuffer(handle, bufferSize, { writable: true });
      steps.push({
        id: `step-${index}`,
        kind: 'writeBuffer',
        bufferId,
        offset: 0,
        data: { kind: 'u32', values },
      });
      return;
    }
    if (kind === 'kernel_dispatch') {
      const kernel = typeof command.kernel === 'string' ? command.kernel : '';
      const moduleId = basename(kernel, extname(kernel)) || `module_${index}`;
      if (!modules.has(moduleId)) {
        modules.set(moduleId, {
          id: moduleId,
          kind: 'compute',
          entryPoint: 'main',
          source: {
            kind: 'file',
            path: inferKernelSourcePath(kernel),
          },
        });
      }
      const bindings = Array.isArray(command.bindings)
        ? command.bindings.map((binding) => {
            const bufferType = normalizeCommandBindingType(binding.buffer_type);
            const bufferId = ensureBuffer(
              Number(binding.resource_handle),
              Number(binding.buffer_size ?? 0),
              { bindingType: bufferType },
            );
            return {
              binding: Number(binding.binding ?? 0),
              bufferId,
              bufferType,
              visibility: ['compute'],
            };
          })
        : [];
      steps.push({
        id: `step-${index}`,
        kind: 'dispatch',
        moduleId,
        workgroups: [
          Number(command.x ?? 1),
          Number(command.y ?? 1),
          Number(command.z ?? 1),
        ],
        bindings,
      });
    }
  });

  return {
    schemaVersion: 1,
    planId: plan.planSha256 ?? plan.compatibilityCommandsSha256 ?? plan.workloadId,
    executorId: 'dawn_node_webgpu',
    workloadId: typeof plan.workloadId === 'string' ? plan.workloadId : 'generated_command_plan',
    domain: 'compute',
    comparable: true,
    description: typeof plan.description === 'string' ? plan.description : '',
    timing: {
      iterations: 1,
      warmup: 0,
      timingSource: 'doe-execution-total-ns',
      timingClass: 'operation',
    },
    adapter: {
      powerPreference: 'high-performance',
      requiredFeatures: [],
      requiredLimits: {},
    },
    buffers: [...buffers.values()].map((buffer) => ({
      id: buffer.id,
      size: buffer.size,
      usage: BUFFER_USAGE_ORDER.filter((entry) => buffer.usage.has(entry)),
    })),
    modules: [...modules.values()],
    steps,
  };
}

function canonicalizePlan(plan) {
  if (isPlainObject(plan) && Array.isArray(plan.commands) && !Array.isArray(plan.steps)) {
    return commandPlanToNeutralPlan(plan);
  }
  return plan;
}

function normalizeUsageList(usage) {
  if (!Array.isArray(usage)) {
    return [];
  }
  const deduped = new Set();
  for (const entry of usage) {
    if (typeof entry === 'string' && ALLOWED_BUFFER_USAGES.has(entry)) {
      deduped.add(entry);
    }
  }
  return BUFFER_USAGE_ORDER.filter((entry) => deduped.has(entry));
}

function normalizeData(data) {
  if (!isPlainObject(data)) {
    return null;
  }
  const kind = typeof data.kind === 'string' ? data.kind : '';
  if (!ALLOWED_DATA_KINDS.has(kind)) {
    return null;
  }
  if (kind === 'utf8') {
    return { kind, text: String(data.text ?? '') };
  }
  if (kind === 'bytes') {
    return { kind, values: Array.isArray(data.values) ? data.values.map((value) => Number(value) & 0xff) : [] };
  }
  const values = Array.isArray(data.values) ? data.values.map((value) => Number(value)) : [];
  return { kind, values };
}

function normalizeWorkgroups(workgroups, location, problems) {
  if (Array.isArray(workgroups) && workgroups.length === 3) {
    const normalized = workgroups.map((value) => Number(value));
    if (normalized.every((value) => Number.isInteger(value) && value > 0)) {
      return normalized;
    }
  }
  problems.push(`${location}: workgroups must be an array of three positive integers`);
  return [1, 1, 1];
}

function normalizeBinding(binding, index, location, problems) {
  if (!isPlainObject(binding)) {
    problems.push(`${location}[${index}] must be an object`);
    return null;
  }
  const bindingIndex = Number(binding.binding);
  const bufferId = typeof binding.bufferId === 'string' ? binding.bufferId : '';
  const bufferType = typeof binding.bufferType === 'string' ? binding.bufferType : 'storage';
  const visibility = Array.isArray(binding.visibility) ? binding.visibility.map((value) => String(value)) : ['compute'];
  const offset = Number(binding.offset ?? 0);
  const size = binding.size === undefined ? undefined : Number(binding.size);
  if (!Number.isInteger(bindingIndex) || bindingIndex < 0) {
    problems.push(`${location}[${index}].binding must be a non-negative integer`);
  }
  if (!bufferId) {
    problems.push(`${location}[${index}].bufferId must be a non-empty string`);
  }
  if (!ALLOWED_BINDING_BUFFER_TYPES.has(bufferType)) {
    problems.push(`${location}[${index}].bufferType must be one of ${[...ALLOWED_BINDING_BUFFER_TYPES].join(', ')}`);
  }
  if (!Number.isInteger(offset) || offset < 0) {
    problems.push(`${location}[${index}].offset must be a non-negative integer`);
  }
  if (size !== undefined && (!Number.isInteger(size) || size <= 0)) {
    problems.push(`${location}[${index}].size must be a positive integer when present`);
  }
  return {
    binding: Number.isInteger(bindingIndex) && bindingIndex >= 0 ? bindingIndex : 0,
    bufferId,
    bufferType,
    visibility,
    offset: Number.isInteger(offset) && offset >= 0 ? offset : 0,
    ...(size === undefined || !Number.isInteger(size) || size <= 0 ? {} : { size }),
  };
}

function normalizeBuffer(buffer, index, problems) {
  if (!isPlainObject(buffer)) {
    problems.push(`buffers[${index}] must be an object`);
    return null;
  }
  const id = typeof buffer.id === 'string' ? buffer.id : '';
  const size = Number(buffer.size);
  const usage = normalizeUsageList(buffer.usage);
  const data = normalizeData(buffer.initialData ?? buffer.data ?? null);
  if (!id) {
    problems.push(`buffers[${index}].id must be a non-empty string`);
  }
  if (!Number.isInteger(size) || size <= 0) {
    problems.push(`buffers[${index}].size must be a positive integer`);
  }
  if (!usage.length) {
    problems.push(`buffers[${index}].usage must include at least one valid usage`);
  }
  if (data && data.kind !== 'utf8') {
    const elementCount = data.values.length;
    if (data.kind === 'bytes') {
      if (elementCount > size) {
        problems.push(`buffers[${index}].data exceeds declared size`);
      }
    } else {
      const byteLength = data.kind === 'u8' ? elementCount : elementCount * 4;
      if (byteLength > size) {
        problems.push(`buffers[${index}].data exceeds declared size`);
      }
    }
  }
  if (data && data.kind === 'utf8' && new TextEncoder().encode(data.text).length > size) {
    problems.push(`buffers[${index}].data exceeds declared size`);
  }
  return {
    id,
    size: Number.isInteger(size) && size > 0 ? size : 0,
    usage,
    data,
    label: typeof buffer.label === 'string' ? buffer.label : undefined,
  };
}

function normalizeModule(module, index, problems) {
  if (!isPlainObject(module)) {
    problems.push(`modules[${index}] must be an object`);
    return null;
  }
  const id = typeof module.id === 'string' ? module.id : '';
  const kind = typeof module.kind === 'string' ? module.kind : 'compute';
  const entryPoint = typeof module.entryPoint === 'string' ? module.entryPoint : 'main';
  const source = isPlainObject(module.source) ? module.source : null;
  if (!id) {
    problems.push(`modules[${index}].id must be a non-empty string`);
  }
  if (kind !== 'compute') {
    problems.push(`modules[${index}].kind must be compute`);
  }
  if (!source) {
    problems.push(`modules[${index}].source must be an object`);
  } else if (source.kind !== 'inline' && source.kind !== 'file') {
    problems.push(`modules[${index}].source.kind must be inline or file`);
  } else if (source.kind === 'inline' && typeof source.code !== 'string') {
    problems.push(`modules[${index}].source.code must be a string`);
  } else if (source.kind === 'file' && typeof source.path !== 'string') {
    problems.push(`modules[${index}].source.path must be a string`);
  }
  return {
    id,
    kind,
    entryPoint,
    source,
    label: typeof module.label === 'string' ? module.label : undefined,
  };
}

function normalizeStep(step, index, problems) {
  if (!isPlainObject(step)) {
    problems.push(`steps[${index}] must be an object`);
    return null;
  }
  const kind = typeof step.kind === 'string' ? step.kind : '';
  if (!ALLOWED_STEP_KINDS.has(kind)) {
    problems.push(`steps[${index}].kind must be one of ${[...ALLOWED_STEP_KINDS].join(', ')}`);
    return null;
  }

  if (kind === 'writeBuffer') {
    const bufferId = typeof step.bufferId === 'string' ? step.bufferId : '';
    const offset = Number(step.offset ?? 0);
    const data = normalizeData(step.data ?? null);
    if (!bufferId) {
      problems.push(`steps[${index}].bufferId must be a non-empty string`);
    }
    if (!Number.isInteger(offset) || offset < 0) {
      problems.push(`steps[${index}].offset must be a non-negative integer`);
    }
    if (!data) {
      problems.push(`steps[${index}].data must be present and valid`);
    }
    return { kind, bufferId, offset, data };
  }

  if (kind === 'dispatch') {
    const moduleId = typeof step.moduleId === 'string' ? step.moduleId : '';
    if (!moduleId) {
      problems.push(`steps[${index}].moduleId must be a non-empty string`);
    }
    return {
      kind,
      moduleId,
      entryPoint: typeof step.entryPoint === 'string' ? step.entryPoint : undefined,
      workgroups: normalizeWorkgroups(step.workgroups, `steps[${index}].workgroups`, problems),
      bindings: Array.isArray(step.bindings)
        ? step.bindings.map((binding, bindingIndex) => normalizeBinding(binding, bindingIndex, `steps[${index}].bindings`, problems)).filter(Boolean)
        : [],
    };
  }

  if (kind === 'copyBufferToBuffer') {
    const srcBufferId = typeof step.srcBufferId === 'string' ? step.srcBufferId : '';
    const dstBufferId = typeof step.dstBufferId === 'string' ? step.dstBufferId : '';
    const sizeBytes = Number(step.sizeBytes);
    if (!srcBufferId) {
      problems.push(`steps[${index}].srcBufferId must be a non-empty string`);
    }
    if (!dstBufferId) {
      problems.push(`steps[${index}].dstBufferId must be a non-empty string`);
    }
    if (!Number.isInteger(sizeBytes) || sizeBytes <= 0) {
      problems.push(`steps[${index}].sizeBytes must be a positive integer`);
    }
    return { kind, srcBufferId, dstBufferId, sizeBytes: Number.isInteger(sizeBytes) && sizeBytes > 0 ? sizeBytes : 0 };
  }

  const bufferId = typeof step.bufferId === 'string' ? step.bufferId : '';
  if (!bufferId) {
    problems.push(`steps[${index}].bufferId must be a non-empty string`);
  }
  return {
    kind,
    bufferId,
    validate: isPlainObject(step.validate) ? step.validate : null,
  };
}

export function validatePlan(plan) {
  const candidate = canonicalizePlan(plan);
  const problems = [];
  if (!isPlainObject(candidate)) {
    return ['plan must be a JSON object'];
  }
  if (Number(candidate.schemaVersion) !== 1) {
    problems.push('schemaVersion must equal 1');
  }
  if (typeof candidate.planId !== 'string' || candidate.planId.length === 0) {
    problems.push('planId must be a non-empty string');
  }
  if (typeof candidate.executorId !== 'string' || candidate.executorId.length === 0) {
    problems.push('executorId must be a non-empty string');
  }
  if (typeof candidate.workloadId !== 'string' || candidate.workloadId.length === 0) {
    problems.push('workloadId must be a non-empty string');
  }
  if (typeof candidate.domain !== 'string' || candidate.domain.length === 0) {
    problems.push('domain must be a non-empty string');
  }
  if (typeof candidate.comparable !== 'boolean') {
    problems.push('comparable must be a boolean');
  }

  const timing = isPlainObject(candidate.timing) ? candidate.timing : null;
  if (!timing) {
    problems.push('timing must be an object');
  } else {
    for (const field of ['iterations', 'warmup']) {
      const value = Number(timing[field]);
      if (!Number.isInteger(value) || value < 0) {
        problems.push(`timing.${field} must be a non-negative integer`);
      }
    }
    if (typeof timing.timingSource !== 'string' || timing.timingSource.length === 0) {
      problems.push('timing.timingSource must be a non-empty string');
    }
    if (typeof timing.timingClass !== 'string' || timing.timingClass.length === 0) {
      problems.push('timing.timingClass must be a non-empty string');
    }
  }

  const buffers = Array.isArray(candidate.buffers) ? candidate.buffers : [];
  const modules = Array.isArray(candidate.modules) ? candidate.modules : [];
  const steps = Array.isArray(candidate.steps) ? candidate.steps : [];

  if (buffers.length === 0) {
    problems.push('buffers must contain at least one buffer definition');
  }
  if (modules.length === 0) {
    problems.push('modules must contain at least one module definition');
  }
  if (steps.length === 0) {
    problems.push('steps must contain at least one step');
  }

  const normalizedBuffers = buffers.map((buffer, index) => normalizeBuffer(buffer, index, problems)).filter(Boolean);
  const normalizedModules = modules.map((module, index) => normalizeModule(module, index, problems)).filter(Boolean);
  const normalizedSteps = steps.map((step, index) => normalizeStep(step, index, problems)).filter(Boolean);

  const bufferIds = new Set();
  for (const buffer of normalizedBuffers) {
    if (bufferIds.has(buffer.id)) {
      problems.push(`duplicate buffer id: ${buffer.id}`);
    }
    bufferIds.add(buffer.id);
  }

  const moduleIds = new Set();
  for (const module of normalizedModules) {
    if (moduleIds.has(module.id)) {
      problems.push(`duplicate module id: ${module.id}`);
    }
    moduleIds.add(module.id);
  }

  let seenReadbackStep = false;
  normalizedSteps.forEach((step, index) => {
    if (step.kind === 'readBuffer') {
      seenReadbackStep = true;
      return;
    }
    if (seenReadbackStep) {
      problems.push(`steps[${index}].kind=${step.kind} cannot appear after readBuffer steps`);
    }
  });

  for (const step of normalizedSteps) {
    if (step.kind === 'dispatch') {
      if (!moduleIds.has(step.moduleId)) {
        problems.push(`dispatch references unknown module: ${step.moduleId}`);
      }
      for (const binding of step.bindings) {
        if (!bufferIds.has(binding.bufferId)) {
          problems.push(`dispatch references unknown buffer: ${binding.bufferId}`);
        }
      }
    } else if (step.kind === 'writeBuffer') {
      if (!bufferIds.has(step.bufferId)) {
        problems.push(`writeBuffer references unknown buffer: ${step.bufferId}`);
      }
    } else if (step.kind === 'copyBufferToBuffer') {
      if (!bufferIds.has(step.srcBufferId)) {
        problems.push(`copyBufferToBuffer references unknown source buffer: ${step.srcBufferId}`);
      }
      if (!bufferIds.has(step.dstBufferId)) {
        problems.push(`copyBufferToBuffer references unknown destination buffer: ${step.dstBufferId}`);
      }
    } else if (step.kind === 'readBuffer') {
      if (!bufferIds.has(step.bufferId)) {
        problems.push(`readBuffer references unknown buffer: ${step.bufferId}`);
      }
    }
  }

  const bufferById = new Map(normalizedBuffers.map((buffer) => [buffer.id, buffer]));
  for (const buffer of normalizedBuffers) {
    if (buffer.data && !buffer.usage.includes('copy_dst')) {
      problems.push(`buffer ${buffer.id}: initial data requires copy_dst usage`);
    }
  }
  for (const step of normalizedSteps) {
    if (step.kind === 'writeBuffer') {
      const buffer = bufferById.get(step.bufferId);
      if (buffer && !buffer.usage.includes('copy_dst')) {
        problems.push(`writeBuffer target ${step.bufferId} requires copy_dst usage`);
      }
    } else if (step.kind === 'readBuffer') {
      const buffer = bufferById.get(step.bufferId);
      if (buffer && !buffer.usage.includes('map_read')) {
        problems.push(`readBuffer target ${step.bufferId} requires map_read usage`);
      }
    } else if (step.kind === 'dispatch') {
      for (const binding of step.bindings) {
        const buffer = bufferById.get(binding.bufferId);
        if (!buffer) continue;
        if (binding.bufferType === 'uniform' && !buffer.usage.includes('uniform')) {
          problems.push(`dispatch binding ${binding.bufferId} requires uniform usage`);
        }
        if ((binding.bufferType === 'storage' || binding.bufferType === 'read-only-storage') && !buffer.usage.includes('storage')) {
          problems.push(`dispatch binding ${binding.bufferId} requires storage usage`);
        }
      }
    }
  }

  return problems;
}

export function normalizePlan(plan) {
  const candidate = canonicalizePlan(plan);
  const problems = validatePlan(candidate);
  if (problems.length) {
    throw new Error(`invalid neutral plan:\n- ${problems.join('\n- ')}`);
  }

  const normalized = {
    schemaVersion: 1,
    planId: candidate.planId,
    executorId: candidate.executorId,
    workloadId: candidate.workloadId,
    domain: candidate.domain,
    comparable: candidate.comparable,
    description: typeof candidate.description === 'string' ? candidate.description : '',
    timing: {
      iterations: Number(candidate.timing.iterations),
      warmup: Number(candidate.timing.warmup),
      timingSource: candidate.timing.timingSource,
      timingClass: candidate.timing.timingClass,
    },
    adapter: isPlainObject(candidate.adapter)
      ? {
          powerPreference: typeof candidate.adapter.powerPreference === 'string' ? candidate.adapter.powerPreference : 'high-performance',
          requiredFeatures: Array.isArray(candidate.adapter.requiredFeatures)
            ? candidate.adapter.requiredFeatures.map((value) => String(value)).sort()
            : [],
          requiredLimits: isPlainObject(candidate.adapter.requiredLimits) ? candidate.adapter.requiredLimits : {},
        }
      : {
          powerPreference: 'high-performance',
          requiredFeatures: [],
          requiredLimits: {},
        },
    buffers: candidate.buffers.map((buffer) => ({
      id: buffer.id,
      size: buffer.size,
      usage: normalizeUsageList(buffer.usage),
      data: normalizeData(buffer.initialData ?? buffer.data ?? null),
      label: typeof buffer.label === 'string' ? buffer.label : undefined,
    })),
    modules: candidate.modules.map((module) => ({
      id: module.id,
      kind: module.kind,
      entryPoint: module.entryPoint,
      source: module.source.kind === 'file'
        ? { kind: 'file', path: module.source.path }
        : { kind: 'inline', code: module.source.code },
      label: typeof module.label === 'string' ? module.label : undefined,
    })),
    steps: candidate.steps.map((step) => {
      if (step.kind === 'dispatch') {
        return {
          kind: step.kind,
          moduleId: step.moduleId,
          entryPoint: step.entryPoint,
          workgroups: step.workgroups,
          bindings: step.bindings,
          ...(typeof step.id === 'string' ? { id: step.id } : {}),
        };
      }
      if (step.kind === 'copyBufferToBuffer') {
        return step;
      }
      if (step.kind === 'writeBuffer') {
        return step;
      }
      return step;
    }),
  };

  const stable = JSON.parse(stableStringify(normalized));
  const planHash = sha256Text(stableStringify(stable));
  const executionShape = {
    bufferCount: normalized.buffers.length,
    moduleCount: normalized.modules.length,
    stepCount: normalized.steps.length,
    writeBufferCount: normalized.steps.filter((step) => step.kind === 'writeBuffer').length,
    dispatchCount: normalized.steps.filter((step) => step.kind === 'dispatch').length,
    copyBufferToBufferCount: normalized.steps.filter((step) => step.kind === 'copyBufferToBuffer').length,
    readBufferCount: normalized.steps.filter((step) => step.kind === 'readBuffer').length,
  };

  return {
    ...stable,
    planHash,
    executionShape,
  };
}

export function planSummary(plan) {
  const normalized = normalizePlan(plan);
  return {
    schemaVersion: normalized.schemaVersion,
    planId: normalized.planId,
    executorId: normalized.executorId,
    workloadId: normalized.workloadId,
    domain: normalized.domain,
    comparable: normalized.comparable,
    timing: normalized.timing,
    planHash: normalized.planHash,
    executionShape: normalized.executionShape,
  };
}

export function materializeBufferData(bufferData) {
  if (!bufferData) {
    return null;
  }
  if (bufferData.kind === 'u8' || bufferData.kind === 'bytes') {
    return Uint8Array.from(bufferData.values);
  }
  if (bufferData.kind === 'u32') {
    return Uint32Array.from(bufferData.values);
  }
  if (bufferData.kind === 'f32') {
    return Float32Array.from(bufferData.values);
  }
  if (bufferData.kind === 'utf8') {
    return new TextEncoder().encode(bufferData.text);
  }
  return null;
}

export function validateSampleExpectation(view, expectation) {
  if (!isPlainObject(expectation)) {
    return { ok: true };
  }
  if (expectation.kind === 'f32PrefixEquals') {
    const values = Array.isArray(expectation.values) ? expectation.values.map((value) => Number(value)) : [];
    const actual = new Float32Array(view.buffer, view.byteOffset, Math.min(values.length, view.byteLength / 4));
    for (let index = 0; index < values.length; index += 1) {
      if (actual[index] !== values[index]) {
        return {
          ok: false,
          detail: `expected float32[${index}] === ${values[index]}, got ${actual[index]}`,
        };
      }
    }
    return { ok: true };
  }
  if (expectation.kind === 'u32PrefixEquals') {
    const values = Array.isArray(expectation.values) ? expectation.values.map((value) => Number(value)) : [];
    const actual = new Uint32Array(view.buffer, view.byteOffset, Math.min(values.length, view.byteLength / 4));
    for (let index = 0; index < values.length; index += 1) {
      if (actual[index] !== values[index]) {
        return {
          ok: false,
          detail: `expected uint32[${index}] === ${values[index]}, got ${actual[index]}`,
        };
      }
    }
    return { ok: true };
  }
  if (expectation.kind === 'bytesPrefixEquals') {
    const values = Array.isArray(expectation.values) ? expectation.values.map((value) => Number(value) & 0xff) : [];
    const actual = new Uint8Array(view.buffer, view.byteOffset, Math.min(values.length, view.byteLength));
    for (let index = 0; index < values.length; index += 1) {
      if (actual[index] !== values[index]) {
        return {
          ok: false,
          detail: `expected bytes[${index}] === ${values[index]}, got ${actual[index]}`,
        };
      }
    }
    return { ok: true };
  }
  return {
    ok: false,
    detail: `unknown expectation kind: ${expectation.kind}`,
  };
}

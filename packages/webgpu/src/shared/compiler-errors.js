function shaderCheckFailure(path, result) {
  const stage = typeof result?.stage === 'string' && result.stage.length > 0 ? result.stage : 'unknown';
  const kind = typeof result?.kind === 'string' && result.kind.length > 0 ? result.kind : 'ShaderCheckFailed';
  const message = typeof result?.message === 'string' && result.message.length > 0
    ? result.message
    : 'shader check failed without native detail';
  const error = new Error(`${path}: ${message}`);
  error.code = kind;
  error.stage = stage;
  if (typeof result?.line === 'number' && result.line > 0) {
    error.line = result.line;
  }
  if (typeof result?.column === 'number' && result.column > 0) {
    error.column = result.column;
  }
  throw error;
}

/**
 * Attach structured compiler error fields to a native error object.
 *
 * Prefers structured `fields` (stage, kind, line, column) from the native ABI
 * over regex parsing of the message string. Falls back to regex when `fields`
 * is not provided, for compatibility with older native layers that do not
 * export `doeNativeGetLastErrorLine` / `doeNativeGetLastErrorColumn`.
 *
 * @param {Error} error - The thrown error from the native call.
 * @param {string} path - The WebGPU API path label (e.g. "GPUDevice.createShaderModule").
 * @param {{ stage?: string, kind?: string, line?: number, column?: number } | null} [fields]
 *   Optional structured fields from the native ABI. When provided, skips regex parsing.
 */
function enrichNativeCompilerError(error, path, fields = null) {
  if (!(error instanceof Error)) return error;
  if (fields !== null && typeof fields === 'object') {
    if (typeof fields.stage === 'string' && fields.stage.length > 0) {
      error.stage = fields.stage;
    }
    if (typeof fields.kind === 'string' && fields.kind.length > 0) {
      error.kind = fields.kind;
      if (!error.code || error.code === 'DOE_ERROR') {
        error.code = fields.kind;
      }
    }
    if (typeof fields.line === 'number' && fields.line > 0) {
      error.line = fields.line;
    }
    if (typeof fields.column === 'number' && fields.column > 0) {
      error.column = fields.column;
    }
    // Prefix the message with the API path but leave the body intact.
    const bodyMatch = /^\[([A-Za-z0-9_]+)(?:\/([A-Za-z0-9_]+))?\]\s+([\s\S]+)$/.exec(error.message);
    error.message = `${path}: ${bodyMatch ? bodyMatch[3] : error.message}`;
    return error;
  }
  // Fallback: parse [stage/kind] prefix from the message string.
  const match = /^\[([A-Za-z0-9_]+)(?:\/([A-Za-z0-9_]+))?\]\s+([\s\S]+)$/.exec(error.message);
  if (match) {
    error.stage = match[1];
    if (match[2]) {
      error.kind = match[2];
      if (!error.code || error.code === 'DOE_ERROR') {
        error.code = match[2];
      }
    }
    error.message = `${path}: ${match[3]}`;
  }
  return error;
}

function compilerErrorFromMessage(path, message, fields = null) {
  return enrichNativeCompilerError(new Error(message), path, fields);
}

function pipelineErrorReason(error, fields = null) {
  if (error?.reason === 'validation' || error?.reason === 'internal') {
    return error.reason;
  }
  const kind = fields?.kind ?? error?.kind ?? error?.code ?? '';
  if (typeof kind === 'string' && kind.length > 0) {
    if (kind === 'OutOfMemory') {
      return 'internal';
    }
    if (
      kind.startsWith('Invalid')
      || kind === 'EntryPointNotFound'
      || kind === 'OverrideConstantsUnavailable'
      || kind === 'InvalidOverrideConstants'
      || kind === 'UnsupportedShaderFormat'
    ) {
      return 'validation';
    }
  }
  const message = error?.message ?? '';
  if (typeof message === 'string' && message.length > 0) {
    if (/out of memory/i.test(message)) {
      return 'internal';
    }
    if (
      message.startsWith('GPUDevice.createComputePipeline')
      || message.startsWith('GPUDevice.createComputePipelineAsync')
      || message.startsWith('GPUDevice.createRenderPipeline')
      || message.startsWith('GPUDevice.createRenderPipelineAsync')
      || message.startsWith('createComputePipeline requires')
      || message.startsWith('createRenderPipeline requires')
      || message.startsWith('createComputePipeline:')
      || message.startsWith('createRenderPipeline:')
    ) {
      return 'validation';
    }
  }
  return 'internal';
}

function pipelineErrorFromError(error, path, fields = null) {
  if (!(error instanceof Error)) return error;
  const enriched = enrichNativeCompilerError(error, path, fields);
  enriched.name = 'GPUPipelineError';
  enriched.reason = pipelineErrorReason(enriched, fields);
  return enriched;
}

function pipelineErrorFromMessage(path, message, fields = null) {
  return pipelineErrorFromError(new Error(message), path, fields);
}

export {
  shaderCheckFailure,
  enrichNativeCompilerError,
  compilerErrorFromMessage,
  pipelineErrorFromError,
  pipelineErrorFromMessage,
};

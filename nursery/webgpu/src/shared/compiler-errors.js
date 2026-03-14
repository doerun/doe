function shaderCheckFailure(path, result) {
  const stage = typeof result?.stage === 'string' && result.stage.length > 0 ? result.stage : 'unknown';
  const kind = typeof result?.kind === 'string' && result.kind.length > 0 ? result.kind : 'ShaderCheckFailed';
  const message = typeof result?.message === 'string' && result.message.length > 0
    ? result.message
    : 'shader check failed without native detail';
  const error = new Error(`${path}: ${message}`);
  error.code = kind;
  error.stage = stage;
  throw error;
}

function enrichNativeCompilerError(error, path) {
  if (!(error instanceof Error)) return error;
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

function compilerErrorFromMessage(path, message) {
  return enrichNativeCompilerError(new Error(message), path);
}

export {
  shaderCheckFailure,
  enrichNativeCompilerError,
  compilerErrorFromMessage,
};

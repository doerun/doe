// doe-gpu/hybrid — local-first inference with cloud fallback
//
// import { createHybridProvider } from 'doe-gpu/hybrid';
// const ai = await createHybridProvider({ cloudApiKey: '...' });
// for await (const token of ai.generate('Hello')) { ... }

const DEFAULT_LOCAL_TIMEOUT_MS = 10000;
const DEFAULT_LOCAL_MODEL = 'gemma3-270m';
const DEFAULT_CLOUD_MODEL = 'gpt-4o-mini';
const DEFAULT_MODE = 'prefer-local';

function resolveMode(mode) {
  const valid = ['prefer-local', 'prefer-cloud', 'local-only', 'cloud-only'];
  if (!mode) return DEFAULT_MODE;
  if (!valid.includes(mode)) {
    throw new Error(
      `Invalid hybrid routing mode "${mode}". Expected one of: ${valid.join(', ')}`
    );
  }
  return mode;
}

function detectGpuCapability() {
  if (typeof globalThis.navigator !== 'undefined' && globalThis.navigator?.gpu) {
    return true;
  }
  if (typeof process !== 'undefined' && process.versions?.node) {
    return true;
  }
  return false;
}

async function tryLoadLocal(modelId, timeoutMs) {
  let doppler;
  try {
    const mod = await import('@simulatte/doppler');
    doppler = mod.doppler;
  } catch {
    return null;
  }
  if (typeof doppler?.load !== 'function') return null;

  const loadPromise = doppler.load(modelId);
  const timeoutPromise = new Promise((_, reject) =>
    setTimeout(() => reject(new Error('Local model load timed out')), timeoutMs)
  );

  try {
    return await Promise.race([loadPromise, timeoutPromise]);
  } catch {
    return null;
  }
}

async function* streamLocal(model, prompt) {
  const gen = model.generate(prompt);
  for await (const token of gen) {
    yield token;
  }
}

async function* streamCloud(endpoint, apiKey, model, prompt) {
  const url = endpoint.replace(/\/+$/, '') + '/chat/completions';
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model,
      messages: [{ role: 'user', content: prompt }],
      stream: true,
    }),
  });

  if (!response.ok) {
    const body = await response.text().catch(() => '');
    throw new Error(`Cloud API error ${response.status}: ${body}`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('Cloud API response has no readable body');
  }

  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.startsWith('data: ')) continue;
        const data = trimmed.slice(6);
        if (data === '[DONE]') return;

        let parsed;
        try {
          parsed = JSON.parse(data);
        } catch {
          continue;
        }

        const content = parsed.choices?.[0]?.delta?.content;
        if (typeof content === 'string' && content.length > 0) {
          yield content;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export async function createHybridProvider(config = {}) {
  const mode = resolveMode(config.mode);
  const localModel = config.localModel ?? DEFAULT_LOCAL_MODEL;
  const cloudEndpoint = config.cloudEndpoint ?? 'https://api.openai.com/v1';
  const cloudApiKey = config.cloudApiKey ?? null;
  const cloudModel = config.cloudModel ?? DEFAULT_CLOUD_MODEL;
  const localTimeoutMs = config.localTimeoutMs ?? DEFAULT_LOCAL_TIMEOUT_MS;
  const maxLocalTokens = config.maxLocalTokens ?? Infinity;

  let model = null;
  let localHealthy = false;

  const canUseLocal = mode !== 'cloud-only';
  const canUseCloud = mode !== 'local-only';

  if (canUseLocal && detectGpuCapability()) {
    model = await tryLoadLocal(localModel, localTimeoutMs);
    localHealthy = model !== null && model.loaded !== false;
  }

  if (!localHealthy && !canUseCloud) {
    throw new Error(
      'Hybrid provider in local-only mode but local model failed to load'
    );
  }

  if (!localHealthy && canUseCloud && !cloudApiKey) {
    throw new Error(
      'Local model unavailable and no cloudApiKey provided for cloud fallback'
    );
  }

  function isLocalReady() {
    return localHealthy && model !== null && model.loaded !== false;
  }

  function requireCloud() {
    if (!canUseCloud) {
      throw new Error('Cloud fallback is disabled in local-only mode');
    }
    if (!cloudApiKey) {
      throw new Error('Cloud API key is required for cloud generation');
    }
  }

  async function* generate(prompt) {
    const useLocal =
      (mode === 'local-only') ||
      (mode === 'prefer-local' && isLocalReady()) ||
      (mode === 'prefer-cloud' && !cloudApiKey && isLocalReady());

    if (useLocal && isLocalReady()) {
      let tokenCount = 0;
      try {
        for await (const token of streamLocal(model, prompt)) {
          tokenCount++;
          yield token;
          if (tokenCount >= maxLocalTokens && canUseCloud && cloudApiKey) {
            break;
          }
        }
        if (tokenCount < maxLocalTokens) return;
      } catch (err) {
        if (!canUseCloud) throw err;
        localHealthy = false;
      }

      if (tokenCount >= maxLocalTokens) {
        requireCloud();
        yield* streamCloud(cloudEndpoint, cloudApiKey, cloudModel, prompt);
        return;
      }
    }

    requireCloud();
    yield* streamCloud(cloudEndpoint, cloudApiKey, cloudModel, prompt);
  }

  async function generateText(prompt) {
    let output = '';
    for await (const token of generate(prompt)) {
      output += token;
    }
    return output;
  }

  async function dispose() {
    if (model && typeof model.unload === 'function') {
      await model.unload();
    }
    model = null;
    localHealthy = false;
  }

  return {
    generate,
    generateText,
    dispose,
    get localReady() { return isLocalReady(); },
    get mode() { return mode; },
  };
}

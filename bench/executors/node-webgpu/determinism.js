import { createDoeNamespace } from '../../../packages/doe-gpu/src/vendor/doe-namespace.js';
import { buildDeterminismTraceMetaBlock } from '../determinism-trace-meta.js';

const DOE_HOST_DETERMINISM = createDoeNamespace().bind({}).determinism;
const DETERMINISM_SUPPORTED_MODES = new Set(['stable-token', 'stable-choice', 'reviewed-choice']);
const DETERMINISM_PROVIDER_BOUNDARIES = new Set(['doe', 'all']);

function asUint8Array(view) {
  if (view instanceof Uint8Array) {
    return view;
  }
  if (ArrayBuffer.isView(view)) {
    return new Uint8Array(view.buffer, view.byteOffset, view.byteLength);
  }
  if (view instanceof ArrayBuffer) {
    return new Uint8Array(view);
  }
  return new Uint8Array();
}

function decodeU32Token(bytes) {
  const view = asUint8Array(bytes);
  if (view.byteLength < 4) {
    return null;
  }
  return new DataView(view.buffer, view.byteOffset, view.byteLength).getUint32(0, true);
}

function captureLookupKey(tokenIndex, phase) {
  return `${tokenIndex}:${phase}`;
}

export function normalizeDeterminismConfig(config, problems, location = 'determinism') {
  if (config == null) {
    return null;
  }
  if (!config || typeof config !== 'object' || Array.isArray(config)) {
    problems.push(`${location} must be an object when provided`);
    return null;
  }
  const mode = typeof config.mode === 'string' ? config.mode : '';
  if (!DETERMINISM_SUPPORTED_MODES.has(mode)) {
    problems.push(`${location}.mode must be one of ${Array.from(DETERMINISM_SUPPORTED_MODES).join(', ')}`);
    return null;
  }
  const providerBoundary = config.providerBoundary ?? 'doe';
  if (typeof providerBoundary !== 'string' || !DETERMINISM_PROVIDER_BOUNDARIES.has(providerBoundary)) {
    problems.push(`${location}.providerBoundary must be one of ${Array.from(DETERMINISM_PROVIDER_BOUNDARIES).join(', ')}`);
  }
  const semanticTokenIndex = Number(config.semanticTokenIndex ?? 0);
  if (!Number.isInteger(semanticTokenIndex) || semanticTokenIndex < 0) {
    problems.push(`${location}.semanticTokenIndex must be a non-negative integer when provided`);
  }
  const topCandidates = config.topCandidates === undefined ? undefined : Number(config.topCandidates);
  if (
    config.topCandidates !== undefined
    && (!Number.isInteger(topCandidates) || topCandidates <= 0)
  ) {
    problems.push(`${location}.topCandidates must be a positive integer when provided`);
  }
  if (config.policyId != null && (typeof config.policyId !== 'string' || config.policyId.trim().length === 0)) {
    problems.push(`${location}.policyId must be a non-empty string when provided`);
  }
  if (config.reviewPolicyId != null && (typeof config.reviewPolicyId !== 'string' || config.reviewPolicyId.trim().length === 0)) {
    problems.push(`${location}.reviewPolicyId must be a non-empty string when provided`);
  }
  if (config.triggerPolicyId != null && (typeof config.triggerPolicyId !== 'string' || config.triggerPolicyId.trim().length === 0)) {
    problems.push(`${location}.triggerPolicyId must be a non-empty string when provided`);
  }
  if (config.candidateSetId != null && (typeof config.candidateSetId !== 'string' || config.candidateSetId.trim().length === 0)) {
    problems.push(`${location}.candidateSetId must be a non-empty string when provided`);
  }
  if (
    config.candidateSetSource != null
    && !['fixture-declared', 'registry-resolved', 'source-report-resolved'].includes(config.candidateSetSource)
  ) {
    problems.push(
      `${location}.candidateSetSource must be fixture-declared, registry-resolved, or source-report-resolved when provided`,
    );
  }
  const candidates = Array.isArray(config.candidates) ? config.candidates : null;
  if (mode !== 'stable-token') {
    if (!candidates || candidates.length < 2) {
      problems.push(`${location}.candidates must contain at least two entries for ${mode}`);
    } else {
      candidates.forEach((candidate, index) => {
        if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate)) {
          problems.push(`${location}.candidates[${index}] must be an object`);
          return;
        }
        if (!Number.isInteger(candidate.token) || candidate.token < 0) {
          problems.push(`${location}.candidates[${index}].token must be a non-negative integer`);
        }
        if (candidate.label != null && typeof candidate.label !== 'string') {
          problems.push(`${location}.candidates[${index}].label must be a string when provided`);
        }
      });
    }
    if (!config.ambiguityTrigger || typeof config.ambiguityTrigger !== 'object' || Array.isArray(config.ambiguityTrigger)) {
      problems.push(`${location}.ambiguityTrigger must be an object for ${mode}`);
    } else {
      const triggerMode = config.ambiguityTrigger.mode;
      if (triggerMode !== 'exact-max-tie' && triggerMode !== 'candidate-margin-band') {
        problems.push(`${location}.ambiguityTrigger.mode must be exact-max-tie or candidate-margin-band`);
      }
      if (
        triggerMode === 'candidate-margin-band'
        && (typeof config.ambiguityTrigger.epsilon !== 'number' || Number.isNaN(config.ambiguityTrigger.epsilon) || config.ambiguityTrigger.epsilon < 0)
      ) {
        problems.push(`${location}.ambiguityTrigger.epsilon must be a non-negative number`);
      }
    }
  }
  if (mode === 'reviewed-choice') {
    if (!config.decision || typeof config.decision !== 'object' || Array.isArray(config.decision)) {
      problems.push(`${location}.decision must be an object for reviewed-choice`);
    } else {
      if (!Number.isInteger(config.decision.token) || config.decision.token < 0) {
        problems.push(`${location}.decision.token must be a non-negative integer`);
      }
      if (typeof config.decision.reviewerId !== 'string' || config.decision.reviewerId.trim().length === 0) {
        problems.push(`${location}.decision.reviewerId must be a non-empty string`);
      }
    }
  }
  return {
    mode,
    providerBoundary: typeof providerBoundary === 'string' ? providerBoundary : 'doe',
    semanticTokenIndex: Number.isInteger(semanticTokenIndex) && semanticTokenIndex >= 0 ? semanticTokenIndex : 0,
    ...(Number.isInteger(topCandidates) && topCandidates > 0 ? { topCandidates } : {}),
    ...(typeof config.policyId === 'string' ? { policyId: config.policyId } : {}),
    ...(typeof config.reviewPolicyId === 'string' ? { reviewPolicyId: config.reviewPolicyId } : {}),
    ...(typeof config.triggerPolicyId === 'string' ? { triggerPolicyId: config.triggerPolicyId } : {}),
    ...(typeof config.candidateSetId === 'string' ? { candidateSetId: config.candidateSetId } : {}),
    ...(typeof config.candidateSetSource === 'string' ? { candidateSetSource: config.candidateSetSource } : {}),
    ...(candidates ? { candidates: candidates.map((candidate) => ({
      token: candidate.token,
      ...(candidate.label == null ? {} : { label: candidate.label }),
    })) } : {}),
    ...(config.ambiguityTrigger ? { ambiguityTrigger: { ...config.ambiguityTrigger } } : {}),
    ...(config.decision ? { decision: { ...config.decision } } : {}),
  };
}

export function extractDeterminismCapture(rows, tokenIndex, phase) {
  return rows.get(captureLookupKey(tokenIndex, phase)) ?? null;
}

export async function evaluateExecutionDeterminism({
  determinismConfig,
  provider,
  captureRows,
}) {
  if (!determinismConfig) {
    return null;
  }
  if (
    determinismConfig.providerBoundary === 'doe'
    && provider !== 'doe'
  ) {
    return null;
  }
  const tokenIndex = determinismConfig.semanticTokenIndex ?? 0;
  const logitsCapture = extractDeterminismCapture(captureRows, tokenIndex, 'final_logits');
  if (!logitsCapture || !logitsCapture.bytes || logitsCapture.bytes.byteLength === 0) {
    return null;
  }
  const logits = asUint8Array(logitsCapture.bytes);
  let result;
  if (determinismConfig.mode === 'stable-token') {
    result = await DOE_HOST_DETERMINISM.stableToken({
      logits,
      vocabSize: Math.floor(logits.byteLength / 4),
      ...(determinismConfig.topCandidates == null ? {} : { topCandidates: determinismConfig.topCandidates }),
    });
  } else if (determinismConfig.mode === 'stable-choice') {
    result = await DOE_HOST_DETERMINISM.stableChoice({
      logits,
      vocabSize: Math.floor(logits.byteLength / 4),
      ...(determinismConfig.topCandidates == null ? {} : { topCandidates: determinismConfig.topCandidates }),
      ...(determinismConfig.policyId == null ? {} : { policyId: determinismConfig.policyId }),
      ...(determinismConfig.triggerPolicyId == null ? {} : { triggerPolicyId: determinismConfig.triggerPolicyId }),
      ...(determinismConfig.candidateSetId == null ? {} : { candidateSetId: determinismConfig.candidateSetId }),
      ...(determinismConfig.candidateSetSource == null ? {} : { candidateSetSource: determinismConfig.candidateSetSource }),
      candidates: determinismConfig.candidates,
      ambiguityTrigger: determinismConfig.ambiguityTrigger,
    });
  } else {
    result = await DOE_HOST_DETERMINISM.reviewedChoice({
      logits,
      vocabSize: Math.floor(logits.byteLength / 4),
      ...(determinismConfig.topCandidates == null ? {} : { topCandidates: determinismConfig.topCandidates }),
      ...(determinismConfig.reviewPolicyId == null ? {} : { reviewPolicyId: determinismConfig.reviewPolicyId }),
      ...(determinismConfig.triggerPolicyId == null ? {} : { triggerPolicyId: determinismConfig.triggerPolicyId }),
      ...(determinismConfig.candidateSetId == null ? {} : { candidateSetId: determinismConfig.candidateSetId }),
      ...(determinismConfig.candidateSetSource == null ? {} : { candidateSetSource: determinismConfig.candidateSetSource }),
      candidates: determinismConfig.candidates,
      ambiguityTrigger: determinismConfig.ambiguityTrigger,
      decision: determinismConfig.decision,
    });
  }
  const rawTokenCapture = extractDeterminismCapture(captureRows, tokenIndex, 'output_token')
    ?? extractDeterminismCapture(captureRows, tokenIndex, 'sample_token');
  return {
    tokenIndex,
    rawToken: rawTokenCapture ? decodeU32Token(rawTokenCapture.bytes) : null,
    receipt: result.receipt,
    determinism: buildDeterminismTraceMetaBlock(result.receipt),
  };
}

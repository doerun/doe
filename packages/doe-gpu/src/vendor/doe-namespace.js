// Legacy Doe helper surface carried forward into the consolidated doe-gpu package.
// Local imports are limited to config-backed registry metadata used by receipts.

import { DOE_DETERMINISM_POLICY_REGISTRY } from './doe-determinism-policy.js';
import { DOE_NUMERIC_STABILITY_POLICY_REGISTRY } from './doe-numeric-stability-policy.js';

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
const DOE_READBACK_STAGING = new WeakMap();
const DOE_PENDING_ENCODERS = new WeakMap();
const DOE_F32_BYTE_WIDTH = 4;
const DOE_DEFAULT_STABLE_TOKEN_TOP_CANDIDATES = 5;
const DOE_MAX_STABLE_TOKEN_TIED_INDEX_PREFIX = 16;
const DOE_STABLE_TOKEN_MODE = 'stable-token';
const DOE_STABLE_CHOICE_MODE = 'stable-choice';
const DOE_REVIEWED_CHOICE_MODE = 'reviewed-choice';
const DOE_STABLE_CHOICE_TRIGGER_EXACT_MAX_TIE = 'exact-max-tie';
const DOE_STABLE_CHOICE_TRIGGER_CANDIDATE_MARGIN_BAND = 'candidate-margin-band';
const DOE_NUMERIC_STABILITY_MODE = 'numeric-stability';
const DOE_DETERMINISM_POLICY_REGISTRY_PATH = DOE_DETERMINISM_POLICY_REGISTRY.policyRegistryPath;
const DOE_DETERMINISM_POLICY_REGISTRY_VERSION = DOE_DETERMINISM_POLICY_REGISTRY.registryVersion;
const DOE_STABLE_TOKEN_POLICY = DOE_DETERMINISM_POLICY_REGISTRY.stableToken;
const DOE_STABLE_CHOICE_POLICY = DOE_DETERMINISM_POLICY_REGISTRY.stableChoice;
const DOE_REVIEWED_CHOICE_POLICY = DOE_DETERMINISM_POLICY_REGISTRY.reviewedChoice;
const DOE_NUMERIC_STABILITY_POLICY_REGISTRY_PATH =
  DOE_NUMERIC_STABILITY_POLICY_REGISTRY.policyRegistryPath;
const DOE_NUMERIC_STABILITY_POLICY_REGISTRY_VERSION =
  DOE_NUMERIC_STABILITY_POLICY_REGISTRY.registryVersion;
const DOE_NUMERIC_STABILITY_ROUTE_DECISIONS = new Set(
  DOE_NUMERIC_STABILITY_POLICY_REGISTRY.routeDecisions
);
const DOE_NUMERIC_STABILITY_MATMUL_LOGITS_SLICE =
  DOE_NUMERIC_STABILITY_POLICY_REGISTRY.matmulLogitsSlice;
const DOE_STABLE_TOKEN_TIE_BREAK_RULE = DOE_STABLE_TOKEN_POLICY.tieBreakRule;
const DOE_STABLE_TOKEN_COMPARATOR = DOE_STABLE_TOKEN_POLICY.comparator;
const DOE_STABLE_TOKEN_SELECTED_BY_POLICY = DOE_STABLE_TOKEN_POLICY.selectedBy;
const DOE_STABLE_CHOICE_BASE_RULE_ID = DOE_STABLE_CHOICE_POLICY.baseRuleId;
const DOE_STABLE_CHOICE_EVALUATOR_KIND = DOE_STABLE_CHOICE_POLICY.evaluatorKind;
const DOE_STABLE_CHOICE_SELECTED_BY_POLICY = DOE_STABLE_CHOICE_POLICY.selectedBy.policy;
const DOE_STABLE_CHOICE_SELECTED_BY_FALLBACK = DOE_STABLE_CHOICE_POLICY.selectedBy.fallback;
const DOE_REVIEWED_CHOICE_EVALUATOR_KIND = DOE_REVIEWED_CHOICE_POLICY.evaluatorKind;
const DOE_REVIEWED_CHOICE_SELECTED_BY_DECISION = DOE_REVIEWED_CHOICE_POLICY.selectedBy.decision;
const DOE_REVIEWED_CHOICE_SELECTED_BY_FALLBACK = DOE_REVIEWED_CHOICE_POLICY.selectedBy.fallback;
const DOE_REVIEWED_CHOICE_ACCEPTED = DOE_REVIEWED_CHOICE_POLICY.decisionAcceptanceReasons.accepted;
const DOE_REVIEWED_CHOICE_FALLBACK_NOT_TRIGGERED = DOE_REVIEWED_CHOICE_POLICY.decisionAcceptanceReasons.notTriggered;
const DOE_REVIEWED_CHOICE_FALLBACK_NOT_IN_CANDIDATE_SET = DOE_REVIEWED_CHOICE_POLICY.decisionAcceptanceReasons.notInCandidateSet;
const DOE_REVIEWED_CHOICE_FALLBACK_NOT_AMBIGUOUS = DOE_REVIEWED_CHOICE_POLICY.decisionAcceptanceReasons.notAmbiguous;
const DOE_STABLE_CHOICE_CANDIDATE_SET_SOURCES = new Set(DOE_DETERMINISM_POLICY_REGISTRY.candidateSetSources);

function deferCommandBuffer(device, commandBuffer) {
  if (!commandBuffer || typeof commandBuffer !== 'object') {
    return;
  }
  let pending = DOE_PENDING_ENCODERS.get(device);
  if (!pending) {
    pending = [];
    DOE_PENDING_ENCODERS.set(device, pending);
  }
  pending.push(commandBuffer);
}

function drainPendingEncoders(device) {
  const pending = DOE_PENDING_ENCODERS.get(device);
  if (!pending || pending.length === 0) return [];
  DOE_PENDING_ENCODERS.set(device, []);
  return pending.filter((commandBuffer) => commandBuffer && typeof commandBuffer === 'object');
}

function resolveBufferUsageToken(token, combined = false) {
  switch (token) {
    case 'upload':
      return DOE_GPU_BUFFER_USAGE.COPY_DST;
    case 'readback':
      return combined
        ? DOE_GPU_BUFFER_USAGE.COPY_SRC
        : DOE_GPU_BUFFER_USAGE.COPY_DST | DOE_GPU_BUFFER_USAGE.MAP_READ;
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

function validateNonNegativeInteger(value, label) {
  if (!Number.isInteger(value) || value < 0) {
    throw new Error(`${label} must be a non-negative integer.`);
  }
}

function resolveStableTokenTieBreakRule(value) {
  const rule = value ?? DOE_STABLE_TOKEN_TIE_BREAK_RULE;
  if (rule !== DOE_STABLE_TOKEN_TIE_BREAK_RULE) {
    throw new Error(
      `Doe determinism.stableToken tieBreakRule must be "${DOE_STABLE_TOKEN_TIE_BREAK_RULE}".`
    );
  }
  return rule;
}

function resolveStableTokenTopCandidates(value) {
  const count = value ?? DOE_DEFAULT_STABLE_TOKEN_TOP_CANDIDATES;
  validatePositiveInteger(count, 'Doe determinism.stableToken topCandidates');
  return count;
}

function resolveStableChoicePolicyId(value) {
  if (value == null) {
    return DOE_STABLE_CHOICE_POLICY.defaultPolicyId;
  }
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new Error('Doe determinism.stableChoice policyId must be a non-empty string when provided.');
  }
  return value;
}

function resolveStableChoiceTriggerPolicyId(value) {
  if (value == null) {
    return null;
  }
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new Error('Doe determinism.stableChoice triggerPolicyId must be a non-empty string when provided.');
  }
  return value;
}

function resolveStableChoiceCandidateSetId(value) {
  if (value == null) {
    return null;
  }
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new Error('Doe determinism.stableChoice candidateSetId must be a non-empty string when provided.');
  }
  return value;
}

function resolveStableChoiceCandidateSetSource(value) {
  if (value == null) {
    return null;
  }
  if (!DOE_STABLE_CHOICE_CANDIDATE_SET_SOURCES.has(value)) {
    throw new Error('Doe determinism.stableChoice candidateSetSource is not recognized.');
  }
  return value;
}

function cloneProofLinks(proofLinks) {
  return proofLinks.map((proofLink) => ({ ...proofLink }));
}

function stableTokenProofLinks() {
  return cloneProofLinks(DOE_STABLE_TOKEN_POLICY.proofLinks);
}

function stableChoiceProofLinks(mode) {
  return cloneProofLinks(DOE_STABLE_CHOICE_POLICY.proofLinksByTriggerMode[mode]);
}

function reviewedChoiceProofLinks(mode) {
  return cloneProofLinks(DOE_REVIEWED_CHOICE_POLICY.proofLinksByTriggerMode[mode]);
}

function normalizeStableChoiceCandidate(rawCandidate, priority) {
  if (Number.isInteger(rawCandidate) && rawCandidate >= 0) {
    return {
      token: rawCandidate,
      label: null,
      priority,
    };
  }
  if (!rawCandidate || typeof rawCandidate !== 'object' || Array.isArray(rawCandidate)) {
    throw new Error('Doe determinism.stableChoice candidates must be token integers or { token, label } objects.');
  }
  const token = rawCandidate.token;
  if (!Number.isInteger(token) || token < 0) {
    throw new Error('Doe determinism.stableChoice candidate.token must be a non-negative integer.');
  }
  const label = rawCandidate.label == null ? null : String(rawCandidate.label);
  return {
    token,
    label,
    priority,
  };
}

function normalizeReviewedChoiceDecision(rawDecision, vocabSize) {
  if (!rawDecision || typeof rawDecision !== 'object' || Array.isArray(rawDecision)) {
    throw new Error('Doe determinism.reviewedChoice decision must be an object.');
  }
  const token = rawDecision.token;
  if (!Number.isInteger(token) || token < 0) {
    throw new Error('Doe determinism.reviewedChoice decision.token must be a non-negative integer.');
  }
  if (token >= vocabSize) {
    throw new Error(
      `Doe determinism.reviewedChoice decision token ${token} exceeds logits vocabSize ${vocabSize}.`
    );
  }
  const reviewerId = rawDecision.reviewerId;
  if (typeof reviewerId !== 'string' || reviewerId.trim().length === 0) {
    throw new Error('Doe determinism.reviewedChoice decision.reviewerId must be a non-empty string.');
  }
  const normalizeOptional = (value, label) => {
    if (value == null) {
      return null;
    }
    if (typeof value !== 'string' || value.trim().length === 0) {
      throw new Error(`Doe determinism.reviewedChoice decision.${label} must be a non-empty string when provided.`);
    }
    return value;
  };
  return {
    token,
    label: rawDecision.label == null ? null : String(rawDecision.label),
    reviewerId,
    decisionId: normalizeOptional(rawDecision.decisionId, 'decisionId'),
    decisionRef: normalizeOptional(rawDecision.decisionRef, 'decisionRef'),
    signature: normalizeOptional(rawDecision.signature, 'signature'),
  };
}

function resolveStableChoiceCandidates(candidates, vocabSize) {
  if (!Array.isArray(candidates) || candidates.length < 2) {
    throw new Error('Doe determinism.stableChoice candidates must contain at least two entries.');
  }
  const normalized = candidates.map((candidate, priority) => normalizeStableChoiceCandidate(candidate, priority));
  const seen = new Set();
  for (const candidate of normalized) {
    if (candidate.token >= vocabSize) {
      throw new Error(
        `Doe determinism.stableChoice candidate token ${candidate.token} exceeds logits vocabSize ${vocabSize}.`
      );
    }
    if (seen.has(candidate.token)) {
      throw new Error(`Doe determinism.stableChoice candidate token ${candidate.token} is duplicated.`);
    }
    seen.add(candidate.token);
  }
  return normalized;
}

function resolveStableChoiceTrigger(trigger) {
  if (!trigger || typeof trigger !== 'object' || Array.isArray(trigger)) {
    throw new Error('Doe determinism.stableChoice ambiguityTrigger must be an object.');
  }
  const mode = trigger.mode;
  if (mode !== DOE_STABLE_CHOICE_TRIGGER_EXACT_MAX_TIE && mode !== DOE_STABLE_CHOICE_TRIGGER_CANDIDATE_MARGIN_BAND) {
    throw new Error(
      `Doe determinism.stableChoice ambiguityTrigger.mode must be "${DOE_STABLE_CHOICE_TRIGGER_EXACT_MAX_TIE}" ` +
      `or "${DOE_STABLE_CHOICE_TRIGGER_CANDIDATE_MARGIN_BAND}".`
    );
  }
  if (mode === DOE_STABLE_CHOICE_TRIGGER_CANDIDATE_MARGIN_BAND) {
    const epsilon = trigger.epsilon;
    if (typeof epsilon !== 'number' || Number.isNaN(epsilon) || epsilon < 0) {
      throw new Error('Doe determinism.stableChoice ambiguityTrigger.epsilon must be a non-negative number.');
    }
    return { mode, epsilon };
  }
  return { mode, epsilon: null };
}

function resolveStableTokenByteSize(totalBytes, offset, size, vocabSize, labelPrefix) {
  validateNonNegativeInteger(offset, `${labelPrefix} offset`);
  if (offset > totalBytes) {
    throw new Error(`${labelPrefix} offset ${offset} exceeds byteLength ${totalBytes}.`);
  }
  const remainingBytes = totalBytes - offset;
  let resolvedSize = size;
  if (resolvedSize == null && vocabSize != null) {
    validatePositiveInteger(vocabSize, `${labelPrefix} vocabSize`);
    resolvedSize = vocabSize * DOE_F32_BYTE_WIDTH;
  }
  if (resolvedSize == null) {
    resolvedSize = remainingBytes;
  }
  validateNonNegativeInteger(resolvedSize, `${labelPrefix} size`);
  if (resolvedSize > remainingBytes) {
    throw new Error(`${labelPrefix} size ${resolvedSize} exceeds remaining byteLength ${remainingBytes}.`);
  }
  if (resolvedSize === 0) {
    throw new Error(`${labelPrefix} size must be greater than zero.`);
  }
  if (resolvedSize % DOE_F32_BYTE_WIDTH !== 0) {
    throw new Error(`${labelPrefix} size ${resolvedSize} must be a multiple of ${DOE_F32_BYTE_WIDTH} bytes.`);
  }
  if (vocabSize != null && resolvedSize !== vocabSize * DOE_F32_BYTE_WIDTH) {
    throw new Error(
      `${labelPrefix} size ${resolvedSize} does not match vocabSize ${vocabSize} * ${DOE_F32_BYTE_WIDTH}.`
    );
  }
  return resolvedSize;
}

function toStableTokenFloat32Array(data, offset, byteSize) {
  const bytes = normalizeDataView(data).subarray(offset, offset + byteSize).slice();
  return new Float32Array(bytes.buffer);
}

async function sha256HexFromBytes(bytes) {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle || typeof subtle.digest !== 'function') {
    throw new Error('Doe determinism.stableToken requires crypto.subtle.digest support.');
  }
  const digest = await subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

function collectStableTokenSummary(logits, topCandidateCount) {
  const topCandidates = [];
  let bestIndex = 0;
  let bestLogit = Number.NEGATIVE_INFINITY;
  let sawFinite = false;
  let tiedMaxCount = 0;
  let tiedMaxIndicesPrefix = [];

  for (let index = 0; index < logits.length; index += 1) {
    const logit = logits[index];
    if (Number.isNaN(logit)) {
      continue;
    }
    sawFinite = true;

    let insertAt = 0;
    while (insertAt < topCandidates.length) {
      const current = topCandidates[insertAt];
      if (logit > current.logit || (logit === current.logit && index < current.index)) {
        break;
      }
      insertAt += 1;
    }
    if (insertAt < topCandidateCount) {
      topCandidates.splice(insertAt, 0, { index, logit });
      if (topCandidates.length > topCandidateCount) {
        topCandidates.pop();
      }
    }

    if (logit > bestLogit) {
      bestLogit = logit;
      bestIndex = index;
      tiedMaxCount = 1;
      tiedMaxIndicesPrefix = [index];
      continue;
    }
    if (logit === bestLogit) {
      tiedMaxCount += 1;
      if (tiedMaxIndicesPrefix.length < DOE_MAX_STABLE_TOKEN_TIED_INDEX_PREFIX) {
        tiedMaxIndicesPrefix.push(index);
      }
    }
  }

  if (!sawFinite) {
    throw new Error('Doe determinism.stableToken requires at least one finite logit value.');
  }

  return {
    token: bestIndex,
    maxLogit: bestLogit,
    tiedMaxCount,
    tiedMaxIndicesPrefix,
    tiedMaxIndicesOmittedCount: Math.max(0, tiedMaxCount - tiedMaxIndicesPrefix.length),
    topCandidates,
  };
}

function collectChoiceCandidateContext(logits, options, methodLabel) {
  const candidates = resolveStableChoiceCandidates(options.candidates, logits.length);
  const ambiguityTrigger = resolveStableChoiceTrigger(options.ambiguityTrigger);
  const candidateSet = candidates
    .map((candidate) => ({
      token: candidate.token,
      label: candidate.label,
      priority: candidate.priority,
      logit: logits[candidate.token],
    }))
    .filter((candidate) => !Number.isNaN(candidate.logit))
    .sort((left, right) => {
      if (right.logit !== left.logit) {
        return right.logit - left.logit;
      }
      if (left.priority !== right.priority) {
        return left.priority - right.priority;
      }
      return left.token - right.token;
    });
  if (candidateSet.length < 2) {
    throw new Error(`${methodLabel} requires at least two finite candidate logits.`);
  }
  const topCandidate = candidateSet[0];
  const runnerUp = candidateSet[1];
  let ambiguousCandidates = [];
  if (ambiguityTrigger.mode === DOE_STABLE_CHOICE_TRIGGER_EXACT_MAX_TIE) {
    ambiguousCandidates = candidateSet.filter((candidate) => candidate.logit === topCandidate.logit);
  } else {
    ambiguousCandidates = candidateSet.filter(
      (candidate) => (topCandidate.logit - candidate.logit) <= ambiguityTrigger.epsilon
    );
  }
  return {
    ambiguityTrigger,
    candidateSet,
    ambiguityTriggered: ambiguousCandidates.length >= 2,
    ambiguityTopGap: topCandidate.logit - runnerUp.logit,
    ambiguousCandidates,
  };
}

function collectStableChoiceSummary(logits, stableTokenSummary, options) {
  const policyId = resolveStableChoicePolicyId(options.policyId);
  const triggerPolicyId = resolveStableChoiceTriggerPolicyId(options.triggerPolicyId);
  const candidateSetId = resolveStableChoiceCandidateSetId(options.candidateSetId);
  const candidateSetSource = resolveStableChoiceCandidateSetSource(options.candidateSetSource);
  const choiceContext = collectChoiceCandidateContext(logits, options, 'Doe determinism.stableChoice');
  const ambiguityTriggered = choiceContext.ambiguityTriggered;
  const selectedCandidate = ambiguityTriggered
    ? choiceContext.ambiguousCandidates.reduce((best, candidate) => {
      if (candidate.priority !== best.priority) {
        return candidate.priority < best.priority ? candidate : best;
      }
      return candidate.token < best.token ? candidate : best;
    })
    : null;
  return {
    policyId,
    triggerPolicyId,
    candidateSetId,
    candidateSetSource,
    ...choiceContext,
    token: selectedCandidate ? selectedCandidate.token : stableTokenSummary.token,
    selectedBy: selectedCandidate ? DOE_STABLE_CHOICE_SELECTED_BY_POLICY : DOE_STABLE_CHOICE_SELECTED_BY_FALLBACK,
  };
}

function resolveReviewedChoicePolicyId(value) {
  if (value == null) {
    return DOE_REVIEWED_CHOICE_POLICY.defaultPolicyId;
  }
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new Error('Doe determinism.reviewedChoice reviewPolicyId must be a non-empty string when provided.');
  }
  return value;
}

function collectReviewedChoiceSummary(logits, stableTokenSummary, options) {
  const reviewPolicyId = resolveReviewedChoicePolicyId(options.reviewPolicyId);
  const triggerPolicyId = resolveStableChoiceTriggerPolicyId(options.triggerPolicyId);
  const candidateSetId = resolveStableChoiceCandidateSetId(options.candidateSetId);
  const candidateSetSource = resolveStableChoiceCandidateSetSource(options.candidateSetSource);
  const choiceContext = collectChoiceCandidateContext(logits, options, 'Doe determinism.reviewedChoice');
  const decision = normalizeReviewedChoiceDecision(options.decision, logits.length);
  const candidateMatch = choiceContext.candidateSet.find((candidate) => candidate.token === decision.token) ?? null;
  const ambiguousMatch = choiceContext.ambiguousCandidates.find((candidate) => candidate.token === decision.token) ?? null;
  let token = stableTokenSummary.token;
  let selectedBy = DOE_REVIEWED_CHOICE_SELECTED_BY_FALLBACK;
  let decisionAccepted = false;
  let decisionAcceptanceReason = DOE_REVIEWED_CHOICE_FALLBACK_NOT_TRIGGERED;
  if (choiceContext.ambiguityTriggered) {
    if (!candidateMatch) {
      decisionAcceptanceReason = DOE_REVIEWED_CHOICE_FALLBACK_NOT_IN_CANDIDATE_SET;
    } else if (!ambiguousMatch) {
      decisionAcceptanceReason = DOE_REVIEWED_CHOICE_FALLBACK_NOT_AMBIGUOUS;
    } else {
      token = decision.token;
      selectedBy = DOE_REVIEWED_CHOICE_SELECTED_BY_DECISION;
      decisionAccepted = true;
      decisionAcceptanceReason = DOE_REVIEWED_CHOICE_ACCEPTED;
    }
  }
  return {
    reviewPolicyId,
    triggerPolicyId,
    candidateSetId,
    candidateSetSource,
    decision,
    decisionAccepted,
    decisionAcceptanceReason,
    ...choiceContext,
    token,
    selectedBy,
  };
}

async function resolveDeterminismPayload(device, options, methodLabel) {
  if (!options || typeof options !== 'object') {
    throw new Error(`${methodLabel} options must be an object.`);
  }
  const tieBreakRule = resolveStableTokenTieBreakRule(options.tieBreakRule);
  const topCandidateCount = resolveStableTokenTopCandidates(options.topCandidates);
  const logits = options.logits;
  if (logits == null) {
    throw new Error(`${methodLabel} requires logits.`);
  }

  if (ArrayBuffer.isView(logits) || logits instanceof ArrayBuffer) {
    const bytes = normalizeDataView(logits);
    const offset = options.offset ?? 0;
    const byteSize = resolveStableTokenByteSize(
      bytes.byteLength,
      offset,
      options.size,
      options.vocabSize,
      `${methodLabel} host logits`,
    );
    return {
      logits: toStableTokenFloat32Array(logits, offset, byteSize),
      bytesRead: byteSize,
      sourceKind: 'host-bytes',
      tieBreakRule,
      topCandidateCount,
    };
  }

  if (!device || typeof device !== 'object') {
    throw new Error(
      `${methodLabel} buffer readback requires a bound Doe device; use typed-array logits instead.`
    );
  }
  if (typeof logits !== 'object' || typeof logits.size !== 'number') {
    throw new Error(
      `${methodLabel} logits must be a GPU buffer, ArrayBuffer, or ArrayBufferView.`
    );
  }
  const offset = options.offset ?? 0;
  const byteSize = resolveStableTokenByteSize(
    logits.size,
    offset,
    options.size,
    options.vocabSize,
    `${methodLabel} buffer logits`,
  );
  return {
    logits: await readBuffer(device, logits, Float32Array, {
      offset,
      size: byteSize,
      label: options.label,
    }),
    bytesRead: byteSize,
    sourceKind: 'buffer-readback',
    tieBreakRule,
    topCandidateCount,
  };
}

async function stableTokenResult(device, options) {
  const payload = await resolveDeterminismPayload(device, options, 'Doe determinism.stableToken');
  const logitsBytes = new Uint8Array(payload.logits.buffer, payload.logits.byteOffset, payload.logits.byteLength);
  const summary = collectStableTokenSummary(payload.logits, payload.topCandidateCount);
  return {
    token: summary.token,
    receipt: {
      mode: DOE_STABLE_TOKEN_MODE,
      policyRegistryPath: DOE_DETERMINISM_POLICY_REGISTRY_PATH,
      policyRegistryVersion: DOE_DETERMINISM_POLICY_REGISTRY_VERSION,
      policyId: DOE_STABLE_TOKEN_POLICY.policyId,
      comparator: DOE_STABLE_TOKEN_COMPARATOR,
      tieBreakRule: payload.tieBreakRule,
      sourceKind: payload.sourceKind,
      vocabSize: payload.logits.length,
      bytesRead: payload.bytesRead,
      logitsSha256: await sha256HexFromBytes(logitsBytes),
      token: summary.token,
      maxLogit: summary.maxLogit,
      tiedMaxCount: summary.tiedMaxCount,
      tiedMaxIndicesPrefix: summary.tiedMaxIndicesPrefix,
      tiedMaxIndicesOmittedCount: summary.tiedMaxIndicesOmittedCount,
      selectedBy: DOE_STABLE_TOKEN_SELECTED_BY_POLICY,
      topCandidates: summary.topCandidates,
      proofLinks: stableTokenProofLinks(),
    },
  };
}

async function stableChoiceResult(device, options) {
  if (!options || typeof options !== 'object') {
    throw new Error('Doe determinism.stableChoice options must be an object.');
  }
  const payload = await resolveDeterminismPayload(device, options, 'Doe determinism.stableChoice');
  const logitsBytes = new Uint8Array(payload.logits.buffer, payload.logits.byteOffset, payload.logits.byteLength);
  const stableSummary = collectStableTokenSummary(payload.logits, payload.topCandidateCount);
  const choiceSummary = collectStableChoiceSummary(payload.logits, stableSummary, options);
  return {
    token: choiceSummary.token,
    receipt: {
      mode: DOE_STABLE_CHOICE_MODE,
      policyRegistryPath: DOE_DETERMINISM_POLICY_REGISTRY_PATH,
      policyRegistryVersion: DOE_DETERMINISM_POLICY_REGISTRY_VERSION,
      comparator: DOE_STABLE_TOKEN_COMPARATOR,
      baseRuleId: DOE_STABLE_CHOICE_BASE_RULE_ID,
      evaluatorKind: DOE_STABLE_CHOICE_EVALUATOR_KIND,
      policyId: choiceSummary.policyId,
      triggerPolicyId: choiceSummary.triggerPolicyId,
      candidateSetId: choiceSummary.candidateSetId,
      candidateSetSource: choiceSummary.candidateSetSource,
      sourceKind: payload.sourceKind,
      vocabSize: payload.logits.length,
      bytesRead: payload.bytesRead,
      logitsSha256: await sha256HexFromBytes(logitsBytes),
      token: choiceSummary.token,
      stableTokenToken: stableSummary.token,
      stableTokenTiedMaxCount: stableSummary.tiedMaxCount,
      stableTokenTiedMaxIndicesPrefix: stableSummary.tiedMaxIndicesPrefix,
      stableTokenTiedMaxIndicesOmittedCount: stableSummary.tiedMaxIndicesOmittedCount,
      ambiguityTrigger: {
        mode: choiceSummary.ambiguityTrigger.mode,
        epsilon: choiceSummary.ambiguityTrigger.epsilon,
      },
      ambiguityTriggered: choiceSummary.ambiguityTriggered,
      ambiguityTopGap: choiceSummary.ambiguityTopGap,
      selectedBy: choiceSummary.selectedBy,
      candidateSet: choiceSummary.candidateSet,
      ambiguousCandidateCount: choiceSummary.ambiguousCandidates.length,
      ambiguousCandidateIndicesPrefix: choiceSummary.ambiguousCandidates
        .slice(0, DOE_MAX_STABLE_TOKEN_TIED_INDEX_PREFIX)
        .map((candidate) => candidate.token),
      ambiguousCandidateIndicesOmittedCount: Math.max(
        0,
        choiceSummary.ambiguousCandidates.length - DOE_MAX_STABLE_TOKEN_TIED_INDEX_PREFIX
      ),
      topCandidates: stableSummary.topCandidates,
      proofLinks: stableChoiceProofLinks(choiceSummary.ambiguityTrigger.mode),
    },
  };
}

async function reviewedChoiceResult(device, options) {
  if (!options || typeof options !== 'object') {
    throw new Error('Doe determinism.reviewedChoice options must be an object.');
  }
  const payload = await resolveDeterminismPayload(device, options, 'Doe determinism.reviewedChoice');
  const logitsBytes = new Uint8Array(payload.logits.buffer, payload.logits.byteOffset, payload.logits.byteLength);
  const stableSummary = collectStableTokenSummary(payload.logits, payload.topCandidateCount);
  const reviewedSummary = collectReviewedChoiceSummary(payload.logits, stableSummary, options);
  return {
    token: reviewedSummary.token,
    receipt: {
      mode: DOE_REVIEWED_CHOICE_MODE,
      policyRegistryPath: DOE_DETERMINISM_POLICY_REGISTRY_PATH,
      policyRegistryVersion: DOE_DETERMINISM_POLICY_REGISTRY_VERSION,
      comparator: DOE_STABLE_TOKEN_COMPARATOR,
      baseRuleId: DOE_REVIEWED_CHOICE_POLICY.baseRuleId,
      evaluatorKind: DOE_REVIEWED_CHOICE_EVALUATOR_KIND,
      reviewPolicyId: reviewedSummary.reviewPolicyId,
      triggerPolicyId: reviewedSummary.triggerPolicyId,
      candidateSetId: reviewedSummary.candidateSetId,
      candidateSetSource: reviewedSummary.candidateSetSource,
      sourceKind: payload.sourceKind,
      vocabSize: payload.logits.length,
      bytesRead: payload.bytesRead,
      logitsSha256: await sha256HexFromBytes(logitsBytes),
      token: reviewedSummary.token,
      stableTokenToken: stableSummary.token,
      stableTokenTiedMaxCount: stableSummary.tiedMaxCount,
      stableTokenTiedMaxIndicesPrefix: stableSummary.tiedMaxIndicesPrefix,
      stableTokenTiedMaxIndicesOmittedCount: stableSummary.tiedMaxIndicesOmittedCount,
      ambiguityTrigger: {
        mode: reviewedSummary.ambiguityTrigger.mode,
        epsilon: reviewedSummary.ambiguityTrigger.epsilon,
      },
      ambiguityTriggered: reviewedSummary.ambiguityTriggered,
      ambiguityTopGap: reviewedSummary.ambiguityTopGap,
      selectedBy: reviewedSummary.selectedBy,
      decision: reviewedSummary.decision,
      decisionAccepted: reviewedSummary.decisionAccepted,
      decisionAcceptanceReason: reviewedSummary.decisionAcceptanceReason,
      candidateSet: reviewedSummary.candidateSet,
      ambiguousCandidateCount: reviewedSummary.ambiguousCandidates.length,
      ambiguousCandidateIndicesPrefix: reviewedSummary.ambiguousCandidates
        .slice(0, DOE_MAX_STABLE_TOKEN_TIED_INDEX_PREFIX)
        .map((candidate) => candidate.token),
      ambiguousCandidateIndicesOmittedCount: Math.max(
        0,
        reviewedSummary.ambiguousCandidates.length - DOE_MAX_STABLE_TOKEN_TIED_INDEX_PREFIX
      ),
      topCandidates: stableSummary.topCandidates,
      proofLinks: reviewedChoiceProofLinks(reviewedSummary.ambiguityTrigger.mode),
    },
  };
}

function isNodeDoeRuntimeAvailable() {
  return typeof process === 'object' && process != null && !!process.versions?.node;
}

function normalizeFiniteNumber(value, label) {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`${label} must be a finite number.`);
  }
  return value;
}

function normalizeNumericArray(values, label) {
  if (ArrayBuffer.isView(values)) {
    return Array.from(values, (value, index) => normalizeFiniteNumber(value, `${label}[${index}]`));
  }
  if (Array.isArray(values)) {
    return values.map((value, index) => normalizeFiniteNumber(value, `${label}[${index}]`));
  }
  throw new Error(`${label} must be an array or typed array of finite numbers.`);
}

function normalizeNumericStabilityString(value, fallback, label) {
  const resolved = value ?? fallback;
  if (typeof resolved !== 'string' || resolved.trim().length === 0) {
    throw new Error(`${label} must be a non-empty string.`);
  }
  return resolved;
}

function normalizeNumericStabilityCandidate(candidate, hiddenStateLength, index) {
  if (!candidate || typeof candidate !== 'object') {
    throw new Error(`Doe numericStability.matmulLogitsSlice candidates[${index}] must be an object.`);
  }
  validateNonNegativeInteger(candidate.tokenId, `Doe numericStability.matmulLogitsSlice candidates[${index}].tokenId`);
  if (candidate.label != null && (typeof candidate.label !== 'string' || candidate.label.trim().length === 0)) {
    throw new Error(`Doe numericStability.matmulLogitsSlice candidates[${index}].label must be a non-empty string when provided.`);
  }
  const weights = normalizeNumericArray(
    candidate.weights,
    `Doe numericStability.matmulLogitsSlice candidates[${index}].weights`
  );
  if (weights.length !== hiddenStateLength) {
    throw new Error(
      `Doe numericStability.matmulLogitsSlice candidates[${index}].weights length ${weights.length} must match hiddenState length ${hiddenStateLength}.`
    );
  }
  const bias = candidate.bias == null
    ? null
    : normalizeFiniteNumber(
        candidate.bias,
        `Doe numericStability.matmulLogitsSlice candidates[${index}].bias`
      );
  return {
    tokenId: candidate.tokenId,
    label: candidate.label ?? null,
    weights,
    bias,
  };
}

function normalizeNumericStabilityMatmulLogitsSliceOptions(options) {
  if (!options || typeof options !== 'object') {
    throw new Error('Doe numericStability.matmulLogitsSlice options must be an object.');
  }
  const hiddenState = normalizeNumericArray(
    options.hiddenState,
    'Doe numericStability.matmulLogitsSlice hiddenState'
  );
  if (hiddenState.length === 0) {
    throw new Error('Doe numericStability.matmulLogitsSlice hiddenState must contain at least one element.');
  }
  if (!Array.isArray(options.candidates) || options.candidates.length < 2) {
    throw new Error('Doe numericStability.matmulLogitsSlice candidates must contain at least two entries.');
  }
  const candidates = options.candidates.map((candidate, index) =>
    normalizeNumericStabilityCandidate(candidate, hiddenState.length, index)
  );
  return {
    hiddenState,
    candidates,
    operatorFamily: normalizeNumericStabilityString(
      options.operatorFamily,
      DOE_NUMERIC_STABILITY_MATMUL_LOGITS_SLICE.operatorFamily,
      'Doe numericStability.matmulLogitsSlice operatorFamily'
    ),
    semanticOpId: normalizeNumericStabilityString(
      options.semanticOpId,
      DOE_NUMERIC_STABILITY_MATMUL_LOGITS_SLICE.semanticOpId,
      'Doe numericStability.matmulLogitsSlice semanticOpId'
    ),
    semanticStage: normalizeNumericStabilityString(
      options.semanticStage,
      DOE_NUMERIC_STABILITY_MATMUL_LOGITS_SLICE.semanticStage,
      'Doe numericStability.matmulLogitsSlice semanticStage'
    ),
    semanticPhase: normalizeNumericStabilityString(
      options.semanticPhase,
      DOE_NUMERIC_STABILITY_MATMUL_LOGITS_SLICE.semanticPhase,
      'Doe numericStability.matmulLogitsSlice semanticPhase'
    ),
    triggerPolicyId: normalizeNumericStabilityString(
      options.triggerPolicyId,
      DOE_NUMERIC_STABILITY_MATMUL_LOGITS_SLICE.defaultTriggerPolicyId,
      'Doe numericStability.matmulLogitsSlice triggerPolicyId'
    ),
    routingPolicyId: normalizeNumericStabilityString(
      options.routingPolicyId,
      DOE_NUMERIC_STABILITY_MATMUL_LOGITS_SLICE.defaultRoutingPolicyId,
      'Doe numericStability.matmulLogitsSlice routingPolicyId'
    ),
    fastPolicyId: normalizeNumericStabilityString(
      options.fastPolicyId,
      DOE_NUMERIC_STABILITY_MATMUL_LOGITS_SLICE.fastPolicyId,
      'Doe numericStability.matmulLogitsSlice fastPolicyId'
    ),
    stablePolicyId: normalizeNumericStabilityString(
      options.stablePolicyId,
      DOE_NUMERIC_STABILITY_MATMUL_LOGITS_SLICE.stablePolicyId,
      'Doe numericStability.matmulLogitsSlice stablePolicyId'
    ),
    runtime: options.runtime ?? null,
    runtimeOptions: options.runtimeOptions ?? null,
    policyPath: options.policyPath ?? null,
    moduleRunnerPath: options.moduleRunnerPath ?? null,
    receiptPath: options.receiptPath ?? null,
    traceMetaPath: options.traceMetaPath ?? null,
    cwd: options.cwd ?? null,
  };
}

function normalizeOptionalNonEmptyString(value, label) {
  if (value == null) {
    return null;
  }
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new Error(`${label} must be a non-empty string when provided.`);
  }
  return value;
}

function normalizeOptionalStringArray(values, label) {
  if (values == null) {
    return null;
  }
  if (!Array.isArray(values)) {
    throw new Error(`${label} must be an array of strings when provided.`);
  }
  return values.map((value, index) => {
    if (typeof value !== 'string' || value.trim().length === 0) {
      throw new Error(`${label}[${index}] must be a non-empty string.`);
    }
    return value;
  });
}

function matchesExpectedPolicyRegistryPath(actualPath, expectedPath) {
  if (actualPath === expectedPath) {
    return true;
  }
  if (typeof actualPath !== 'string' || typeof expectedPath !== 'string') {
    return false;
  }
  return (
    actualPath.endsWith(`/${expectedPath}`) ||
    actualPath.endsWith(`\\${expectedPath}`)
  );
}

function normalizeNumericStabilityOrdinaryExecutionOptions(
  options,
  pathPrefix = 'Doe ordinaryExecution'
) {
  if (!options || typeof options !== 'object') {
    throw new Error(`${pathPrefix} options must be an object.`);
  }
  const commandsPath = normalizeOptionalNonEmptyString(
    options.commandsPath,
    `${pathPrefix} commandsPath`
  );
  if (commandsPath == null) {
    throw new Error(`${pathPrefix} commandsPath is required.`);
  }
  const uploadSubmitEvery = options.uploadSubmitEvery == null
    ? null
    : validateNonNegativeInteger(
        options.uploadSubmitEvery,
        `${pathPrefix} uploadSubmitEvery`
      );
  if (uploadSubmitEvery != null && uploadSubmitEvery <= 0) {
    throw new Error(`${pathPrefix} uploadSubmitEvery must be greater than zero.`);
  }
  return {
    commandsPath,
    quirksPath: normalizeOptionalNonEmptyString(
      options.quirksPath,
      `${pathPrefix} quirksPath`
    ),
    kernelRoot: normalizeOptionalNonEmptyString(
      options.kernelRoot,
      `${pathPrefix} kernelRoot`
    ),
    numericStabilityPolicyPath: normalizeOptionalNonEmptyString(
      options.policyPath,
      `${pathPrefix} policyPath`
    ),
    numericStabilityExecutionProfileId: normalizeOptionalNonEmptyString(
      options.executionProfileId,
      `${pathPrefix} executionProfileId`
    ),
    vendor: normalizeOptionalNonEmptyString(
      options.vendor,
      `${pathPrefix} vendor`
    ),
    api: normalizeOptionalNonEmptyString(
      options.api,
      `${pathPrefix} api`
    ),
    family: normalizeOptionalNonEmptyString(
      options.family,
      `${pathPrefix} family`
    ),
    driver: normalizeOptionalNonEmptyString(
      options.driver,
      `${pathPrefix} driver`
    ),
    backendLane: normalizeOptionalNonEmptyString(
      options.backendLane,
      `${pathPrefix} backendLane`
    ),
    traceJsonlPath: normalizeOptionalNonEmptyString(
      options.traceJsonlPath,
      `${pathPrefix} traceJsonlPath`
    ),
    traceMetaPath: normalizeOptionalNonEmptyString(
      options.traceMetaPath,
      `${pathPrefix} traceMetaPath`
    ),
    uploadBufferUsage: normalizeOptionalNonEmptyString(
      options.uploadBufferUsage,
      `${pathPrefix} uploadBufferUsage`
    ),
    uploadSubmitEvery,
    queueWaitMode: normalizeOptionalNonEmptyString(
      options.queueWaitMode,
      `${pathPrefix} queueWaitMode`
    ),
    queueSyncMode: normalizeOptionalNonEmptyString(
      options.queueSyncMode,
      `${pathPrefix} queueSyncMode`
    ),
    extraArgs: normalizeOptionalStringArray(
      options.extraArgs,
      `${pathPrefix} extraArgs`
    ),
    runtime: options.runtime ?? null,
    runtimeOptions: options.runtimeOptions ?? null,
    cwd: normalizeOptionalNonEmptyString(
      options.cwd,
      `${pathPrefix} cwd`
    ),
  };
}

async function numericStabilityMatmulLogitsSliceResult(device, options) {
  void device;
  const normalized = normalizeNumericStabilityMatmulLogitsSliceOptions(options);
  if (!isNodeDoeRuntimeAvailable()) {
    throw new Error(
      'Doe gpu.numericStability.matmulLogitsSlice is unavailable in this surface. ' +
      'Use doe-gpu or doe-gpu/compute with the Doe native runtime.'
    );
  }
  const runtimeCli = await import('./webgpu/runtime-cli.js');
  const runtime = normalized.runtime ?? runtimeCli.createDoeRuntime(normalized.runtimeOptions ?? {});
  if (typeof runtime?.runNumericStabilityMatmulLogitsSlice !== 'function') {
    throw new Error('Doe numeric stability runtime helper is unavailable in this context.');
  }
  const result = runtime.runNumericStabilityMatmulLogitsSlice({
    hiddenState: normalized.hiddenState,
    candidates: normalized.candidates,
    operatorFamily: normalized.operatorFamily,
    semanticOpId: normalized.semanticOpId,
    semanticStage: normalized.semanticStage,
    semanticPhase: normalized.semanticPhase,
    triggerPolicyId: normalized.triggerPolicyId,
    routingPolicyId: normalized.routingPolicyId,
    fastPolicyId: normalized.fastPolicyId,
    stablePolicyId: normalized.stablePolicyId,
    policyPath: normalized.policyPath,
    moduleRunnerPath: normalized.moduleRunnerPath,
    receiptPath: normalized.receiptPath,
    traceMetaPath: normalized.traceMetaPath,
    cwd: normalized.cwd,
  });
  if (!DOE_NUMERIC_STABILITY_ROUTE_DECISIONS.has(result.routeDecision)) {
    throw new Error(`Doe numeric stability returned unknown route decision: ${String(result.routeDecision)}`);
  }
  if (!result.receipt || result.receipt.mode !== DOE_NUMERIC_STABILITY_MODE) {
    throw new Error('Doe numeric stability service returned an invalid receipt.');
  }
  if (!matchesExpectedPolicyRegistryPath(result.receipt.policyRegistryPath, DOE_NUMERIC_STABILITY_POLICY_REGISTRY_PATH)) {
    throw new Error('Doe numeric stability receipt reported an unexpected policy registry path.');
  }
  if (result.receipt.policyRegistryVersion !== DOE_NUMERIC_STABILITY_POLICY_REGISTRY_VERSION) {
    throw new Error('Doe numeric stability receipt reported an unexpected policy registry version.');
  }
  return {
    token: result.token,
    routeDecision: result.routeDecision,
    receipt: result.receipt,
  };
}

async function numericStabilityOrdinaryExecutionResult(device, options) {
  void device;
  const normalized = normalizeNumericStabilityOrdinaryExecutionOptions(
    options,
    'Doe numericStability.ordinaryExecution'
  );
  if (!isNodeDoeRuntimeAvailable()) {
    throw new Error(
      'Doe gpu.numericStability.ordinaryExecution is unavailable in this surface. ' +
      'Use doe-gpu or doe-gpu/compute with the Doe native runtime.'
    );
  }
  const runtimeCli = await import('./webgpu/runtime-cli.js');
  const runtime = normalized.runtime ?? runtimeCli.createDoeRuntime(normalized.runtimeOptions ?? {});
  if (typeof runtime?.runNumericStabilityOrdinaryExecution !== 'function') {
    throw new Error('Doe numeric stability ordinary-execution helper is unavailable in this context.');
  }
  const result = runtime.runNumericStabilityOrdinaryExecution({
    commandsPath: normalized.commandsPath,
    quirksPath: normalized.quirksPath,
    kernelRoot: normalized.kernelRoot,
    numericStabilityPolicyPath: normalized.numericStabilityPolicyPath,
    numericStabilityExecutionProfileId: normalized.numericStabilityExecutionProfileId,
    vendor: normalized.vendor,
    api: normalized.api,
    family: normalized.family,
    driver: normalized.driver,
    backendLane: normalized.backendLane,
    traceJsonlPath: normalized.traceJsonlPath,
    traceMetaPath: normalized.traceMetaPath,
    uploadBufferUsage: normalized.uploadBufferUsage,
    uploadSubmitEvery: normalized.uploadSubmitEvery,
    queueWaitMode: normalized.queueWaitMode,
    queueSyncMode: normalized.queueSyncMode,
    extraArgs: normalized.extraArgs,
    cwd: normalized.cwd,
  });
  for (const decision of result.routeDecisions ?? []) {
    if (!DOE_NUMERIC_STABILITY_ROUTE_DECISIONS.has(decision)) {
      throw new Error(`Doe numeric stability ordinary execution returned unknown route decision: ${String(decision)}`);
    }
  }
  for (const receipt of result.receipts ?? []) {
    if (!receipt || receipt.mode !== DOE_NUMERIC_STABILITY_MODE) {
      throw new Error('Doe numeric stability ordinary execution returned an invalid receipt.');
    }
    if (
      normalized.numericStabilityPolicyPath == null &&
      !matchesExpectedPolicyRegistryPath(
        receipt.policyRegistryPath,
        DOE_NUMERIC_STABILITY_POLICY_REGISTRY_PATH,
      )
    ) {
      throw new Error('Doe numeric stability receipt reported an unexpected policy registry path.');
    }
    if (receipt.policyRegistryVersion !== DOE_NUMERIC_STABILITY_POLICY_REGISTRY_VERSION) {
      throw new Error('Doe numeric stability receipt reported an unexpected policy registry version.');
    }
  }
  return {
    traceJsonlPath: result.traceJsonlPath,
    traceMetaPath: result.traceMetaPath,
    traceMeta: result.traceMeta,
    executionProfileId: result.executionProfileId ?? null,
    receiptPath: result.receiptPath,
    receipts: result.receipts,
    routeDecisions: result.routeDecisions,
    latestReceipt: result.latestReceipt,
    latestRouteDecision: result.latestRouteDecision,
    latestToken: result.latestToken,
  };
}

async function ordinaryExecutionResult(device, options) {
  void device;
  const normalized = normalizeNumericStabilityOrdinaryExecutionOptions(
    options,
    'Doe ordinaryExecution'
  );
  if (!isNodeDoeRuntimeAvailable()) {
    throw new Error(
      'Doe ordinaryExecution is unavailable in this surface. ' +
      'Use doe-gpu or doe-gpu/compute with the Doe native runtime.'
    );
  }
  const runtimeCli = await import('./webgpu/runtime-cli.js');
  const runtime = normalized.runtime ?? runtimeCli.createDoeRuntime(normalized.runtimeOptions ?? {});
  if (typeof runtime?.runOrdinaryExecution === 'function') {
    return runtime.runOrdinaryExecution({
      commandsPath: normalized.commandsPath,
      quirksPath: normalized.quirksPath,
      kernelRoot: normalized.kernelRoot,
      numericStabilityPolicyPath: normalized.numericStabilityPolicyPath,
      numericStabilityExecutionProfileId: normalized.numericStabilityExecutionProfileId,
      vendor: normalized.vendor,
      api: normalized.api,
      family: normalized.family,
      driver: normalized.driver,
      backendLane: normalized.backendLane,
      traceJsonlPath: normalized.traceJsonlPath,
      traceMetaPath: normalized.traceMetaPath,
      uploadBufferUsage: normalized.uploadBufferUsage,
      uploadSubmitEvery: normalized.uploadSubmitEvery,
      queueWaitMode: normalized.queueWaitMode,
      queueSyncMode: normalized.queueSyncMode,
      extraArgs: normalized.extraArgs,
      cwd: normalized.cwd,
    });
  }
  return numericStabilityOrdinaryExecutionResult(device, options);
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

function createBindingSet(kernel, bindings, options = {}) {
  const normalized = (bindings ?? []).map(normalizeBinding);
  if (normalized.length !== kernel.bindingCount) {
    throw new Error(
      `Doe binding set shape does not match kernel layout: expected ${kernel.bindingCount} binding(s), received ${normalized.length}.`
    );
  }
  const bind_group = normalized.length > 0
    ? kernel.device.createBindGroup({
      label: options.label ?? undefined,
      layout: kernel.layout,
      entries: normalized.map(bindGroupEntry),
    })
    : null;
  return new DoeBindingSet(kernel, bind_group, options.label);
}

function resolveBindingSet(kernel, bindings, options = {}) {
  if (bindings == null) {
    return createBindingSet(kernel, [], options);
  }
  if (bindings instanceof DoeBindingSet) {
    if (bindings.kernel !== kernel) {
      throw new Error('Doe binding sets can only be used with the kernel that created them.');
    }
    return bindings;
  }
  return createBindingSet(kernel, bindings, options);
}

function resolvePassTarget(target, label) {
  if (target instanceof DoeComputeBatch) {
    return target._ensurePass(label);
  }
  if (target instanceof DoeComputePass) {
    return target._pass;
  }
  throw new Error('Doe kernel.encode(...) requires a Doe compute batch or Doe compute pass target.');
}

function submitCommands(device, encoder) {
  deferCommandBuffer(device, encoder.finish());
}

/**
 * Reusable bind group compiled for a specific `DoeKernel`.
 *
 * Surface: Doe API `kernel.bindings`.
 * Input: Created from a `DoeKernel` and a binding list.
 * Returns: A reusable binding-set object.
 *
 * This object holds a bind group that matches one compiled kernel layout so
 * repeated dispatches can reuse the same resource binding shape without
 * rebuilding it on every call.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * const kernel = gpu.kernel.create({ code, bindings: [src, dst] });
 * const bindings = kernel.bindings.create([src, dst]);
 * ```
 *
 * - Binding sets are kernel-scoped and cannot be reused across different kernels.
 * - See `kernel.dispatch(...)` for the simplest path.
 * - See `gpu.compute.begin(...)` when you want to batch many dispatches under one submit.
 */
class DoeBindingSet {
  constructor(kernel, bindGroup, label) {
    this.kernel = kernel;
    this.bindGroup = bindGroup;
    this.label = label;
  }
}

/**
 * Binding-set namespace exposed on each `DoeKernel`.
 *
 * Surface: Doe API `gpu.kernel`.
 * Input: Created internally for one `DoeKernel`.
 * Returns: An object with `create(...)`.
 *
 * This namespace exists because binding sets are scoped to one kernel layout.
 * It lets you build a bind group once and reuse it across many dispatches of
 * that same kernel.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * const bindings = kernel.bindings.create([src, dst]);
 * ```
 *
 * - Binding sets cannot be shared across different kernels.
 * - See `gpu.compute.begin(...)` or `gpu.commandEncoder.create(...)` for where reusable binding sets matter most.
 */
class DoeKernelBindingsNamespace {
  constructor(kernel) {
    this.kernel = kernel;
  }

  /**
   * Create a reusable binding set for this kernel.
   *
   * Surface: Doe API `gpu.kernel`.
   * Input: A binding list and an optional label.
   * Returns: A reusable Doe binding-set object.
   *
   * This resolves Doe binding access, validates the shape against the compiled
   * kernel layout, and creates a bind group you can reuse across repeated
   * dispatches.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * const bindings = kernel.bindings.create([src, dst]);
   * ```
   *
   * - The returned binding set may be passed to `kernel.dispatch(...)`, `batch.dispatch(...)`, or `kernel.encode(...)`.
   * - See `kernel.dispatch(...)` when one-shot simplicity matters more than reuse.
   */
  create(bindings, options = {}) {
    return createBindingSet(this.kernel, bindings, options);
  }
}

/**
 * Batched compute submission builder created by `gpu.compute.begin(...)`.
 *
 * Surface: Doe API `gpu.compute`.
 * Input: Created from a bound Doe API object and an optional label.
 * Returns: A batch object with `dispatch(...)` and `submit()`.
 *
 * Use this when you want several dispatches to share one command encoder, one
 * compute pass, and one queue submit.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * const batch = gpu.compute.begin();
 * batch.dispatch(kernel, { bindings, workgroups: [4, 1, 1] });
 * batch.dispatch(otherKernel, { bindings: otherBindings, workgroups: [2, 1, 1] });
 * await batch.submit();
 * ```
 *
 * - `batch.dispatch(...)` records work but does not submit it yet.
 * - `submit()` ends the shared compute pass automatically.
 * - See `gpu.commandEncoder.create(...)` for the lower-level explicit path.
 */
class DoeComputeBatch {
  constructor(device, options = {}) {
    this.device = device;
    this.label = options.label;
    this._encoder = device.createCommandEncoder({ label: options.label ?? undefined });
    this._pass = null;
    this._submitted = false;
  }

  _ensurePass(label) {
    if (this._submitted) {
      throw new Error('Doe compute batch cannot be reused after submit().');
    }
    if (!this._pass) {
      this._pass = this._encoder.beginComputePass({ label: label ?? this.label ?? undefined });
    }
    return this._pass;
  }

  /**
   * Record one dispatch into this batch.
   *
   * Surface: Doe API `gpu.compute`.
   * Input: A `DoeKernel`, a binding list or reusable binding set, and workgroups.
   * Returns: The same batch for chaining.
   *
   * This records one dispatch into the shared compute pass and defers queue
   * submission until `submit()` is called.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * batch.dispatch(kernel, {
   *   bindings,
   *   workgroups: [4, 1, 1],
   * });
   * ```
   *
   * - `bindings` may be a raw binding list or a `kernel.bindings.create(...)` result.
   * - See `kernel.encode(...)` for the lower-level pass-oriented form.
   */
  dispatch(kernel, options) {
    kernel.encode(this, options);
    return this;
  }

  /**
   * Submit this batch and wait for completion when supported.
   *
   * Surface: Doe API `gpu.compute`.
   * Input: No arguments.
   * Returns: A promise that resolves after queued work completes.
   *
   * This closes the shared compute pass, submits the finished command buffer,
   * and waits for queue completion when the bound runtime exposes
   * `onSubmittedWorkDone()`.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * await batch.submit();
   * ```
   *
   * - A batch can only be submitted once.
   * - See `gpu.commandEncoder.create(...)` when you need multiple pass types in one submission.
   */
  async submit() {
    if (this._submitted) {
      throw new Error('Doe compute batch submit() can only be called once.');
    }
    this._submitted = true;
    if (this._pass) {
      this._pass.end();
      this._pass = null;
    }
    submitCommands(this.device, this._encoder);
  }
}

/**
 * Compute pass wrapper created by `gpu.commandEncoder.create().beginComputePass()`.
 *
 * Surface: Doe API `gpu.commandEncoder`.
 * Input: Created from a Doe command encoder.
 * Returns: A pass object with `dispatch(...)` and `end()`.
 *
 * Use this when you want explicit control over pass lifetime while still using
 * Doe kernels and binding sets for encoding.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * const encoder = gpu.commandEncoder.create();
 * const pass = encoder.beginComputePass();
 * kernel.encode(pass, { bindings, workgroups: [4, 1, 1] });
 * pass.end();
 * await encoder.submit();
 * ```
 *
 * - `dispatch(...)` is a convenience wrapper around `kernel.encode(...)`.
 * - A pass must be ended before its encoder is submitted.
 */
class DoeComputePass {
  constructor(encoder, pass) {
    this.encoder = encoder;
    this._pass = pass;
    this._ended = false;
  }

  /**
   * Record one dispatch into this pass.
   *
   * Surface: Doe API `gpu.commandEncoder`.
   * Input: A `DoeKernel`, a binding list or reusable binding set, and workgroups.
   * Returns: The same pass for chaining.
   *
   * This keeps the pass open so you can encode several dispatches before
   * ending it explicitly.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * pass.dispatch(kernel, {
   *   bindings,
   *   workgroups: [4, 1, 1],
   * });
   * ```
   *
   * - See `kernel.encode(...)` when you want the call to read “kernel first”.
   * - See `gpu.compute.begin(...)` for the simpler batching helper.
   */
  dispatch(kernel, options) {
    kernel.encode(this, options);
    return this;
  }

  /**
   * End this compute pass.
   *
   * Surface: Doe API `gpu.commandEncoder`.
   * Input: No arguments.
   * Returns: The same pass.
   *
   * This must be called before `encoder.submit()`.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * pass.end();
   * ```
   *
   * - A pass can only be ended once.
   */
  end() {
    if (this._ended) {
      throw new Error('Doe compute pass end() can only be called once.');
    }
    this._pass.end();
    this._ended = true;
    this.encoder._clearPass(this);
    return this;
  }
}

/**
 * Command encoder wrapper created by `gpu.commandEncoder.create(...)`.
 *
 * Surface: Doe API `gpu.commandEncoder`.
 * Input: Created from a bound Doe API object and an optional label.
 * Returns: A command encoder object with `beginComputePass()` and `submit()`.
 *
 * Use this when you need to keep submission boundaries explicit while still
 * using Doe helpers for compute encoding.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * const encoder = gpu.commandEncoder.create();
 * const pass = encoder.beginComputePass();
 * kernel.encode(pass, { bindings, workgroups: [4, 1, 1] });
 * pass.end();
 * await encoder.submit();
 * ```
 *
 * - This helper currently focuses on compute passes.
 * - See `gpu.compute.begin(...)` for the simpler “batch many dispatches, then submit once” path.
 */
class DoeCommandEncoder {
  constructor(device, options = {}) {
    this.device = device;
    this.label = options.label;
    this._encoder = device.createCommandEncoder({ label: options.label ?? undefined });
    this._activePass = null;
    this._submitted = false;
  }

  _clearPass(pass) {
    if (this._activePass === pass) {
      this._activePass = null;
    }
  }

  /**
   * Begin one compute pass on this encoder.
   *
   * Surface: Doe API `gpu.commandEncoder`.
   * Input: An optional label.
   * Returns: A Doe compute pass object.
   *
   * This creates one explicit compute pass that stays open until `pass.end()`
   * is called.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * const pass = encoder.beginComputePass();
   * ```
   *
   * - Only one active pass is supported at a time.
   */
  beginComputePass(options = {}) {
    if (this._submitted) {
      throw new Error('Doe command encoder cannot begin new passes after submit().');
    }
    if (this._activePass) {
      throw new Error('Doe command encoder already has an active compute pass.');
    }
    const pass = new DoeComputePass(
      this,
      this._encoder.beginComputePass({ label: options.label ?? this.label ?? undefined }),
    );
    this._activePass = pass;
    return pass;
  }

  /**
   * Submit this encoder and wait for completion when supported.
   *
   * Surface: Doe API `gpu.commandEncoder`.
   * Input: No arguments.
   * Returns: A promise that resolves after queued work completes.
   *
   * This finalizes the command encoder and submits one command buffer.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * await encoder.submit();
   * ```
   *
   * - All passes must be ended before submission.
   * - An encoder can only be submitted once.
   */
  async submit() {
    if (this._submitted) {
      throw new Error('Doe command encoder submit() can only be called once.');
    }
    if (this._activePass) {
      throw new Error('Doe command encoder submit() requires all passes to be ended first.');
    }
    this._submitted = true;
    submitCommands(this.device, this._encoder);
  }
}

/**
 * Reusable compute kernel compiled by `gpu.kernel.create(...)`.
 *
 * Surface: Doe API `gpu.kernel`.
 * Input: Created from WGSL source, an entry point, and an initial binding shape.
 * Returns: A reusable kernel object with `bindings.create(...)`, `encode(...)`, and `dispatch(...)`.
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
 * - See `gpu.compute.begin(...)` for the lower-overhead batched path.
 * - See `gpu.compute(...)` for the narrower typed-array workflow.
 * - Instances are returned through the bound Doe API and are not exported directly.
 */
class DoeKernel {
  constructor(device, pipeline, layout, entryPoint, bindingCount) {
    this.device = device;
    this.pipeline = pipeline;
    this.layout = layout;
    this.entryPoint = entryPoint;
    this.bindingCount = bindingCount;
    this.bindings = new DoeKernelBindingsNamespace(this);
  }

  /**
   * Encode this compiled kernel into a Doe batch or compute pass.
   *
   * Surface: Doe API `gpu.kernel`.
   * Input: A Doe compute batch or Doe compute pass, plus bindings and workgroups.
   * Returns: The same target that received the encoded dispatch.
   *
   * This is the lower-level explicit path. It records the dispatch into an
   * existing Doe batch or pass instead of allocating a new encoder and submit
   * boundary for each call.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * kernel.encode(batch, {
   *   bindings,
   *   workgroups: [4, 1, 1],
   * });
   * ```
   *
   * - `bindings` may be a raw binding list or a `kernel.bindings.create(...)` result.
   * - See `kernel.dispatch(...)` for the simplest one-shot path.
   * - See `gpu.compute.begin(...)` for the recommended batched path.
   */
  encode(target, options) {
    const binding_set = resolveBindingSet(this, options.bindings ?? [], options);
    const workgroups = validateWorkgroups(this.device, options.workgroups);
    const pass = resolvePassTarget(target, options.label);
    pass.setPipeline(this.pipeline);
    if (binding_set.bindGroup) {
      if (target._doeLastBindGroup0 !== binding_set.bindGroup) {
        pass.setBindGroup(0, binding_set.bindGroup);
        target._doeLastBindGroup0 = binding_set.bindGroup;
      }
    }
    pass.dispatchWorkgroups(workgroups[0], workgroups[1], workgroups[2]);
    return target;
  }

  /**
   * Dispatch this compiled kernel once.
   *
   * Surface: Doe API `gpu.kernel`.
   * Input: A binding list, workgroup counts, and an optional label.
   * Returns: A promise that resolves after submission completes.
   *
   * This is the simplest reusable-kernel path. It creates a one-shot batch for
   * you, encodes one dispatch, submits once, and waits for completion when the
   * underlying queue exposes `onSubmittedWorkDone()`.
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
   * - `bindings` may be a raw binding list or a `kernel.bindings.create(...)` result.
   * - See `gpu.compute.begin(...)` when you want to batch many dispatches.
   * - See `kernel.encode(...)` for the lower-level pass-oriented path.
   */
  async dispatch(options) {
    const batch = new DoeComputeBatch(this.device, { label: options.label });
    this.encode(batch, options);
    await batch.submit();
  }
}

function createKernel(device, options) {
  const bindings = (options.bindings ?? []).map(normalizeBinding);
  const shader = device.createShaderModule({ code: options.code });
  const compute = {
    module: shader,
    entryPoint: options.entryPoint ?? 'main',
  };
  let pipeline = device.createComputePipeline({
    layout: 'auto',
    compute,
  });
  let bindGroupLayout = null;
  if (bindings.length === 0) {
    bindGroupLayout = device.createBindGroupLayout({ entries: [] });
  } else if (typeof pipeline?.getBindGroupLayout === 'function') {
    bindGroupLayout = pipeline.getBindGroupLayout(0);
  } else {
    bindGroupLayout = device.createBindGroupLayout({
      entries: bindings.map(bindGroupLayoutEntry),
    });
    const pipelineLayout = device.createPipelineLayout({
      bindGroupLayouts: [bindGroupLayout],
    });
    pipeline = device.createComputePipeline({
      layout: pipelineLayout,
      compute,
    });
  }
  return new DoeKernel(device, pipeline, bindGroupLayout, options.entryPoint ?? 'main', bindings.length);
}

function createBuffer(device, options) {
  if (!options || typeof options !== 'object') {
    throw new Error('Doe buffer options must be an object.');
  }
  if (options.data != null) {
    const view = normalizeDataView(options.data);
    const usage = options.usage ?? 'storageRead';
    const buffer = rememberBufferUsage(device.createBuffer({
      label: options.label ?? undefined,
      size: options.size ?? view.byteLength,
      usage: resolveBufferUsage(usage),
    }), usage);
    device.queue.writeBuffer(buffer, 0, view);
    return buffer;
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

async function readBuffer(device, buffer, type, options = {}) {
  if (arguments.length === 2 && buffer && typeof buffer === 'object') {
    return readBuffer(device, buffer.buffer, buffer.type, buffer);
  }
  if (!buffer || typeof buffer !== 'object') {
    throw new Error('Doe buffer.read requires a buffer.');
  }
  if (typeof type !== 'function') {
    throw new Error('Doe buffer.read type must be a typed-array constructor.');
  }
  const offset = options.offset ?? 0;
  const size = options.size ?? Math.max(0, (buffer.size ?? 0) - offset);
  if (!Number.isInteger(offset) || offset < 0) {
    throw new Error('Doe buffer.read offset must be a non-negative integer.');
  }
  if (!Number.isInteger(size) || size < 0) {
    throw new Error('Doe buffer.read size must be a non-negative integer.');
  }
  if (((buffer.usage ?? 0) & DOE_GPU_BUFFER_USAGE.MAP_READ) !== 0) {
    const pendingCommands = drainPendingEncoders(device);
    if (pendingCommands.length > 0) {
      device.queue.submit(pendingCommands);
      if (typeof device.queue.onSubmittedWorkDone === 'function') {
        await device.queue.onSubmittedWorkDone();
      }
    }
    await buffer.mapAsync(DOE_GPU_MAP_MODE.READ, offset, size);
    const copy = typeof buffer._readCopy === 'function'
      ? buffer._readCopy(offset, size)
      : buffer.getMappedRange(offset, size).slice(0);
    buffer.unmap();
    return new type(copy);
  }
  let staging = DOE_READBACK_STAGING.get(buffer) ?? null;
  if (!staging || staging.size < size || staging._destroyed) {
    staging = device.createBuffer({
      label: options.label ?? undefined,
      size,
      usage: DOE_GPU_BUFFER_USAGE.COPY_DST | DOE_GPU_BUFFER_USAGE.MAP_READ,
    });
    DOE_READBACK_STAGING.set(buffer, staging);
  }
  const pendingCommands = drainPendingEncoders(device);
  const commands = [];
  if (pendingCommands.length > 0) {
    commands.push(...pendingCommands);
  }
  const encoder = device.createCommandEncoder({ label: options.label ?? undefined });
  encoder.copyBufferToBuffer(buffer, offset, staging, 0, size);
  commands.push(encoder.finish());
  device.queue.submit(commands);
  if (typeof device.queue.onSubmittedWorkDone === 'function') {
    await device.queue.onSubmittedWorkDone();
  }
  await staging.mapAsync(DOE_GPU_MAP_MODE.READ);
  const copy = typeof staging._readCopy === 'function'
    ? staging._readCopy(0, size)
    : staging.getMappedRange().slice(0);
  staging.unmap();
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
    assertLayer3Usage(input.usage, input.access, `compute input ${index} usage`);
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

  throw new Error(`Doe compute input ${index} must be data, a Doe input spec, or a buffer.`);
}

function normalizeOnceOutput(device, output, inputs) {
  if (!output || typeof output !== 'object') {
    throw new Error('Doe compute output is required.');
  }
  if (typeof output.type !== 'function') {
    throw new Error('Doe compute output.type must be a typed-array constructor.');
  }

  const fallbackInputIndex = inputs.length > 0 ? 0 : null;
  const likeInputIndex = output.likeInput ?? fallbackInputIndex;
  if (likeInputIndex != null && (!Number.isInteger(likeInputIndex) || likeInputIndex < 0 || likeInputIndex >= inputs.length)) {
    throw new Error(`Doe compute output.likeInput must reference an input index in [0, ${Math.max(inputs.length - 1, 0)}].`);
  }
  const size = output.size ?? (
    likeInputIndex != null && inputs[likeInputIndex]
      ? inputs[likeInputIndex].byte_length
      : null
  );

  if (!(size > 0)) {
    throw new Error('Doe compute output size must be provided or derived from likeInput.');
  }

  assertLayer3Usage(output.usage, output.access, 'compute output usage');
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
  const ordinaryExecution = (options) => ordinaryExecutionResult(device, options);

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
   * const out = await gpu.compute({
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
   * - See `gpu.compute.begin(...)` when you want to batch explicit dispatches under one submit.
   */
  const compute = function compute(options) {
    return computeOnce(device, options);
  };
  /**
   * Begin a reusable batched compute submission.
   *
   * Surface: Doe API `gpu.compute`.
   * Input: An optional label.
   * Returns: A Doe compute batch object with `dispatch(...)` and `submit()`.
   *
   * Use this when you want multiple dispatches to share one command encoder,
   * one compute pass, and one queue submit.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * const batch = gpu.compute.begin();
   * batch.dispatch(kernel, { bindings, workgroups: [4, 1, 1] });
   * await batch.submit();
   * ```
   *
   * - See `gpu.commandEncoder.create(...)` for the lower-level explicit encoder path.
   * - See `gpu.compute(...)` for the narrower typed-array workflow.
   */
  compute.begin = function begin(options = {}) {
    return new DoeComputeBatch(device, options);
  };
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
       * accepts Doe usage tokens such as `storageReadWrite`, and when `data`
       * is provided it allocates and uploads in one step. Doe remembers the
       * resulting binding access so later helper calls can infer how the
       * buffer should be bound.
       *
       * This example shows the API in its basic form.
       *
       * ```js
       * const src = gpu.buffer.create({ data: new Float32Array([1, 2, 3, 4]) });
       * const dst = gpu.buffer.create({ size: src.size, usage: "storageReadWrite" });
       * ```
       *
       * - When `data` is provided, usage defaults to `storageRead`.
       * - Raw numeric usage flags are allowed here for explicit control.
       * - Buffers created with raw numeric flags may later require `{ buffer, access }`.
       */
      create(options) {
        return createBuffer(device, options);
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
      read(options_or_buffer, type, options = {}) {
        if (arguments.length === 1 && options_or_buffer && typeof options_or_buffer === 'object') {
          return readBuffer(device, options_or_buffer);
        }
        return readBuffer(device, options_or_buffer, type, options);
      },
    },
    commandEncoder: {
      /**
       * Create a Doe command encoder for explicit compute submission control.
       *
       * Surface: Doe API `gpu.commandEncoder`.
       * Input: An optional label.
       * Returns: A Doe command encoder object with `beginComputePass()` and `submit()`.
       *
       * This is the lowest-level explicit Doe path above raw WebGPU. It keeps
       * submission boundaries explicit while still letting kernels encode
       * through Doe binding and workgroup validation.
       *
       * This example shows the API in its basic form.
       *
       * ```js
       * const encoder = gpu.commandEncoder.create();
       * ```
       *
       * - See `gpu.compute.begin(...)` for the simpler batched path.
       * - See `gpu.device.createCommandEncoder(...)` when you want the raw runtime object directly.
       */
      create(options = {}) {
        return new DoeCommandEncoder(device, options);
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
       * - See `gpu.compute(...)` for the narrower typed-array workflow.
       * - See `gpu.compute.begin(...)` when you want to batch many dispatches under one submit.
       */
      run(options) {
        return runKernel(device, options);
      },
      /**
       * Compile a reusable compute kernel.
       *
       * Surface: Doe API `gpu.kernel`.
       * Input: WGSL source, an optional entry point, and an initial binding shape.
       * Returns: A `DoeKernel` object with `bindings.create(...)`, `encode(...)`, and `dispatch(...)`.
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
       * - See `kernel.bindings.create(...)` to amortize bind-group creation across repeated dispatches.
       * - See `kernel.dispatch(...)` for the simplest reusable path.
       * - See `kernel.encode(...)` and `gpu.compute.begin(...)` for lower-overhead batching.
       * - See `gpu.kernel.run(...)` when reuse does not matter.
       */
      create(options) {
        return createKernel(device, options);
      },
    },
    determinism: {
      /**
       * Select a stable greedy token with an explicit scalar tie-break rule.
       *
       * Surface: Doe API `gpu.determinism`.
       * Input: Host logits bytes or a GPU buffer containing `f32` logits.
       * Returns: A promise for `{ token, receipt }`.
       *
       * This helper is the explicit Doe determinism contract for greedy
       * decoding. It reads `f32` logits, applies scalar CPU argmax with the
       * documented `lowest-index-among-max` tie-break rule, and emits a receipt
       * describing the exact policy and observed max set.
       *
       * This example shows the API in its basic form.
       *
       * ```js
       * const { token, receipt } = await gpu.determinism.stableToken({
       *   logits: new Float32Array([0, 7, 7, 3]),
       * });
       * ```
       *
      * - Host inputs may be `ArrayBuffer` or `ArrayBufferView`.
      * - Buffer inputs use Doe readback first, then the same scalar tie-break policy.
      * - The current contract supports only `lowest-index-among-max`.
      */
      stableToken(options) {
        return stableTokenResult(device, options);
      },
      /**
       * Resolve ambiguity inside a bounded candidate set with a deterministic policy.
       *
       * Surface: Doe API `gpu.determinism`.
       * Input: Host logits bytes or a GPU buffer plus a candidate set and trigger.
       * Returns: A promise for `{ token, receipt }`.
       *
       * This helper builds on Doe's scalar stable-token boundary. It first
       * computes the scalar greedy token, then checks a bounded candidate set
       * for ambiguity (`exact-max-tie` or `candidate-margin-band`). If the
       * trigger fires, it applies the explicit `fixed-priority` policy over the
       * ambiguous candidate subset; otherwise it falls back to the scalar
       * stable-token result.
       *
       * ```js
       * const { token, receipt } = await gpu.determinism.stableChoice({
       *   logits: new Float32Array([0, 7, 7, 3]),
       *   candidates: [{ token: 2, label: 'unsafe' }, { token: 1, label: 'safe' }],
       *   ambiguityTrigger: { mode: 'exact-max-tie' },
       * });
       * ```
       *
       * - Candidate order is the deterministic priority order for `fixed-priority`.
       * - The ambiguity trigger is evaluated only over the provided candidate set.
       * - If the trigger does not fire, the helper returns the scalar stable-token result.
       */
      stableChoice(options) {
        return stableChoiceResult(device, options);
      },
      /**
       * Apply an explicit reviewed decision over a bounded ambiguous candidate set.
       *
       * Surface: Doe API `gpu.determinism`.
       * Input: Host logits bytes or a GPU buffer plus a candidate set, trigger, and reviewed decision.
       * Returns: A promise for `{ token, receipt }`.
       *
       * This helper keeps the same bounded ambiguity trigger model as
       * `stableChoice(...)`, but the evaluator is an explicit reviewed decision
       * instead of the built-in fixed-priority program. If the trigger fires
       * and the reviewed token is present in the ambiguous subset, Doe returns
       * that token and emits a receipt that records the reviewed source.
       * Otherwise it falls back to the scalar stable-token result.
       *
       * ```js
       * const { token, receipt } = await gpu.determinism.reviewedChoice({
       *   logits: new Float32Array([0, 7, 7, 3]),
       *   candidates: [{ token: 2, label: 'unsafe' }, { token: 1, label: 'safe' }],
       *   ambiguityTrigger: { mode: 'exact-max-tie' },
       *   decision: { token: 1, label: 'safe', reviewerId: 'demo/reviewer' },
       * });
       * ```
       *
       * - The reviewed decision is accepted only when the ambiguity trigger fires.
       * - The reviewed token must belong to the bounded candidate set and the ambiguous subset.
       * - The receipt keeps the decision source and fallback reason explicit.
       */
      reviewedChoice(options) {
        return reviewedChoiceResult(device, options);
      },
    },
    /**
     * Run an ordinary Doe command stream and inherit the runtime numeric-governance path.
     *
     * Surface: Doe API `gpu.ordinaryExecution`.
     * Input: A normal runtime command stream plus optional runtime bench settings.
     * Returns: A promise for the traced run and any in-path numeric-stability receipt rows.
     *
     * This is the preferred package entrypoint for ordinary command-stream
     * execution with Doe's current in-path numeric-governance contract. It
     * uses the same runtime path as `gpu.numericStability.ordinaryExecution(...)`
     * without requiring callers to enter through the numeric-stability
     * namespace first.
     */
    ordinaryExecution,
    numericStability: {
      /**
       * Evaluate a bounded LM-head slice under fast, stable, and reference numeric policies.
       *
       * Surface: Doe API `gpu.numericStability`.
       * Input: A hidden-state vector plus bounded candidate rows for one LM-head slice.
       * Returns: A promise for `{ token, routeDecision, receipt }`.
       *
       * This helper is the explicit Doe runtime-owned numeric-stability v1
       * contract. It calls the Zig module service for `matmul.logits`,
       * compares fast/stable/reference results for the bounded candidate set,
       * and returns the governed route decision with a first-divergence receipt.
       *
       * ```js
       * const result = await gpu.numericStability.matmulLogitsSlice({
       *   hiddenState: [1, 1, 1],
       *   candidates: [
       *     { tokenId: 817, label: 'go', weights: [10000, 0.01, -10000] },
       *     { tokenId: 4721, label: 'stop', weights: [0, 0.001, 0] },
       *   ],
       * });
       * ```
       *
       * - This v1 path is explicit; it does not intercept ordinary WebGPU execution.
       * - The browser shim does not support this helper yet.
       * - The current route vocabulary is `accept-fast`, `prefer-stable`, or `abstain`.
       */
      matmulLogitsSlice(options) {
        return numericStabilityMatmulLogitsSliceResult(device, options);
      },
      /**
       * Run an ordinary Doe command stream and surface any in-path numeric-stability receipts.
       *
       * Surface: Doe API `gpu.numericStability`.
       * Input: A normal runtime command stream plus optional runtime bench settings.
       * Returns: A promise for the traced run and any numeric-stability receipt rows.
       *
       * This helper reuses the ordinary `doe-zig-runtime` execution path instead
       * of the explicit bounded-slice service. The runtime executes the command
       * stream, auto-detects supported sensitive operators such as
       * `matmul.logits`, and then returns the live receipt rows emitted during
       * that execution.
       *
       * - This path requires Doe native runtime support and a trace-meta output.
       * - Receipts may be empty when no supported numeric-stability event fired.
       * - Current ordinary-execution support is runtime-driven; browser shims do
       *   not provide it yet.
       */
      ordinaryExecution,
    },
    compute,
  };
}

export function createDoeNamespace({ requestDevice } = {}) {
  return {
    /**
     * Run an ordinary Doe command stream and inherit the runtime numeric-governance path.
     *
     * Surface: Doe API namespace.
     * Input: A normal runtime command stream plus optional runtime bench settings.
     * Returns: A promise for the traced run and any in-path numeric-stability receipt rows.
     *
     * This is the package-level entrypoint for ordinary Doe execution when no
     * pre-bound device helper is needed.
     */
    ordinaryExecution(options) {
      return ordinaryExecutionResult(null, options);
    },
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

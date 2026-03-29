import { createHash } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

import { DOE_DETERMINISM_POLICY_REGISTRY } from '../../packages/doe-gpu/src/vendor/doe-determinism-policy.js';

const TRACE_META_MODULE = 'doe-gpu/determinism';
const TRACE_META_EMPTY_PREVIOUS_HASH = `sha256:${'0'.repeat(64)}`;

function sha256HexText(text) {
  return createHash('sha256').update(text).digest('hex');
}

function buildProofSummary(receipt) {
  return {
    proofArtifactPath: receipt.proofLinks[0]?.artifactPath ?? DOE_DETERMINISM_POLICY_REGISTRY.proofArtifactPath,
    proofTheorems: receipt.proofLinks.map((proofLink) => proofLink.theorem),
  };
}

function buildStableTokenDeterminism(receipt) {
  return {
    mode: receipt.mode,
    policyRegistryPath: receipt.policyRegistryPath,
    policyRegistryVersion: receipt.policyRegistryVersion,
    policyId: receipt.policyId,
    comparator: receipt.comparator,
    tieBreakRule: receipt.tieBreakRule,
    selectedBy: receipt.selectedBy,
    logitsSha256: receipt.logitsSha256,
    token: receipt.token,
    ...buildProofSummary(receipt),
  };
}

function buildStableChoiceDeterminism(receipt) {
  return {
    mode: receipt.mode,
    policyRegistryPath: receipt.policyRegistryPath,
    policyRegistryVersion: receipt.policyRegistryVersion,
    policyId: receipt.policyId,
    baseRuleId: receipt.baseRuleId,
    comparator: receipt.comparator,
    evaluatorKind: receipt.evaluatorKind,
    triggerPolicyId: receipt.triggerPolicyId,
    candidateSetId: receipt.candidateSetId,
    candidateSetSource: receipt.candidateSetSource,
    selectedBy: receipt.selectedBy,
    ambiguityTriggered: receipt.ambiguityTriggered,
    ambiguityTopGap: receipt.ambiguityTopGap,
    stableTokenToken: receipt.stableTokenToken,
    logitsSha256: receipt.logitsSha256,
    token: receipt.token,
    ...buildProofSummary(receipt),
  };
}

function buildReviewedChoiceDeterminism(receipt) {
  return {
    mode: receipt.mode,
    policyRegistryPath: receipt.policyRegistryPath,
    policyRegistryVersion: receipt.policyRegistryVersion,
    reviewPolicyId: receipt.reviewPolicyId,
    baseRuleId: receipt.baseRuleId,
    comparator: receipt.comparator,
    evaluatorKind: receipt.evaluatorKind,
    triggerPolicyId: receipt.triggerPolicyId,
    candidateSetId: receipt.candidateSetId,
    candidateSetSource: receipt.candidateSetSource,
    selectedBy: receipt.selectedBy,
    ambiguityTriggered: receipt.ambiguityTriggered,
    ambiguityTopGap: receipt.ambiguityTopGap,
    stableTokenToken: receipt.stableTokenToken,
    decisionAccepted: receipt.decisionAccepted,
    decisionAcceptanceReason: receipt.decisionAcceptanceReason,
    decisionToken: receipt.decision.token,
    decisionReviewerId: receipt.decision.reviewerId,
    decisionId: receipt.decision.decisionId,
    decisionRef: receipt.decision.decisionRef,
    decisionSignature: receipt.decision.signature,
    logitsSha256: receipt.logitsSha256,
    token: receipt.token,
    ...buildProofSummary(receipt),
  };
}

export function buildDeterminismTraceMetaBlock(receipt) {
  if (receipt.mode === 'stable-token') {
    return buildStableTokenDeterminism(receipt);
  }
  if (receipt.mode === 'stable-choice') {
    return buildStableChoiceDeterminism(receipt);
  }
  if (receipt.mode === 'reviewed-choice') {
    return buildReviewedChoiceDeterminism(receipt);
  }
  throw new Error(`unsupported determinism receipt mode: ${receipt.mode}`);
}

export function buildDeterminismTraceMeta(receipt) {
  const determinism = buildDeterminismTraceMetaBlock(receipt);
  const hash = `sha256:${sha256HexText(JSON.stringify(determinism))}`;
  return {
    traceVersion: 1,
    module: TRACE_META_MODULE,
    seqMax: 0,
    rowCount: 0,
    commandCount: 0,
    hash,
    previousHash: TRACE_META_EMPTY_PREVIOUS_HASH,
    determinism,
  };
}

export async function writeDeterminismTraceMeta(traceMetaPath, receipt) {
  if (!traceMetaPath) {
    return null;
  }
  const meta = buildDeterminismTraceMeta(receipt);
  await mkdir(path.dirname(traceMetaPath), { recursive: true });
  await writeFile(traceMetaPath, `${JSON.stringify(meta, null, 2)}\n`, 'utf8');
  return meta;
}

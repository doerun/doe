export const DOE_NUMERIC_STABILITY_POLICY_REGISTRY = Object.freeze({
  schemaVersion: 2,
  registryVersion: '2026-03-29-route-taxonomy-v2',
  policyRegistryPath: 'config/numeric-stability-policy.json',
  routeTaxonomyVersion: 'numeric-stability-routes-v1',
  proofArtifactPath: 'pipeline/lean/artifacts/proven-conditions.json',
  routeDecisions: Object.freeze([
    'accept-fast',
    'prefer-stable',
    'abstain',
  ]),
  matmulLogitsSlice: Object.freeze({
    operatorFamily: 'lm-head-slice',
    semanticOpId: 'matmul.logits',
    semanticStage: 'lm_head_slice',
    semanticPhase: 'logits',
    fastPolicyId: 'lm-head-slice/forward-f16accum-v1',
    stablePolicyId: 'lm-head-slice/forward-serial-v1',
    referencePolicyId: 'lm-head-slice/cpu-f64-serial-v1',
    defaultTriggerPolicyId:
      'numeric-instability/selected-token-disagreement-with-reference-improvement-v1',
    defaultRoutingPolicyId:
      'numeric-stability/prefer-stable-on-selected-token-disagreement-v1',
  }),
});

export const DOE_NUMERIC_STABILITY_POLICY_REGISTRY = Object.freeze({
  schemaVersion: 3,
  registryVersion: '2026-03-29-execution-profiles-v1',
  policyRegistryPath: 'config/numeric-stability-policy.json',
  routeTaxonomyVersion: 'numeric-stability-routes-v1',
  proofArtifactPath: 'pipeline/lean/artifacts/proven-conditions.json',
  defaultExecutionProfileId: 'numeric-stability/default-ordinary-execution-v1',
  routeDecisions: Object.freeze([
    'accept-fast',
    'prefer-stable',
    'abstain',
  ]),
  executionProfiles: Object.freeze([
    Object.freeze({
      profileId: 'numeric-stability/default-ordinary-execution-v1',
      surface: 'ordinary-execution',
      description:
        'Default ordinary execution mode: prefer the stable result when the selected-token reference-improvement trigger fires; otherwise keep the fast result.',
      routingPolicyId:
        'numeric-stability/prefer-stable-on-selected-token-disagreement-v1',
    }),
    Object.freeze({
      profileId: 'numeric-stability/cautious-ordinary-execution-v1',
      surface: 'ordinary-execution',
      description:
        'Cautious ordinary execution mode: abstain instead of forcing a winner when the selected-token reference-improvement trigger fires.',
      routingPolicyId:
        'numeric-stability/abstain-on-selected-token-disagreement-v1',
    }),
    Object.freeze({
      profileId: 'numeric-stability/observe-only-ordinary-execution-v1',
      surface: 'ordinary-execution',
      description:
        'Observe-only ordinary execution mode: emit receipts and route metadata, but always keep the fast result.',
      routingPolicyId:
        'numeric-stability/accept-fast-on-selected-token-disagreement-v1',
    }),
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

import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {stats} from '/home/x/deco/doe/bench/shared/lib/stats.js';
const root='/home/x/deco/doe/bench/out/doppler-search/20260923-shader-owner/owner-compare';
const policy=JSON.parse(await fs.readFile(`${root}/policy.json`,'utf8'));
const runs=[];
for (const [index,provider] of policy.order.entries()) {
 const result=JSON.parse(await fs.readFile(`${root}/${index}-${provider}/result.json`,'utf8'));
 const activity=JSON.parse(await fs.readFile(`${root}/${index}-${provider}-activity.json`,'utf8'));
 assert(result.passed && activity.admitted);
 const samples=result.executions.filter(e=>!e.warmup);
 assert.equal(samples.length,policy.timedRuns);
 for (const e of samples) assert(e.comparison.passed);
 runs.push({index,provider,result,activity,stats:stats(samples.map(e=>e.elapsedMs))});
}
function shape(e) {
 const v=e.receipt.evidence;const s=v.stats;
 return {modelId:v.resolution.logicalModelId,artifactVariant:v.resolution.resolvedArtifactVariantId,inputHash:v.inputHash,query:v.query,documents:v.documents,
 tokenIds:v.scores.map(x=>x.tokenIds),kernelPath:s.executionPlan?.primary,
 recordedOps:s.prefillRecordOps,recordedPasses:s.prefillRecordPasses};
}
function executionContract(e) {
 const identity=structuredClone(e.receipt.evidence.executionIdentity);
 // These are provider-reported hardware observations, not program selection.
 delete identity.backendIdentity.adapter;
 delete identity.backendIdentity.maxBufferSize;
 return identity;
}
const first=runs[0]; const reference=shape(first.result.executions[0]);
for (const run of runs) {
 assert.equal(run.result.plan,first.result.plan);
 assert.equal(run.result.referenceSha256,first.result.referenceSha256);
 assert.equal(run.result.capsuleSha256,first.result.capsuleSha256);
 assert.equal(run.result.scriptSha256,first.result.scriptSha256);
 assert.deepEqual(run.activity.target,first.activity.target);
 for (const e of run.result.executions) {
  assert.deepEqual(shape(e),reference);
  assert.deepEqual(executionContract(e),executionContract(first.result.executions[0]));
 }
}
const combined={};
for (const provider of ['baseline','candidate','dawn']) {
 const own=runs.filter(r=>r.provider===provider);
 combined[provider]={queryMs:stats(own.flatMap(r=>r.result.executions.filter(e=>!e.warmup).map(e=>e.elapsedMs))),
 runs:own.map(r=>({index:r.index,queryMs:r.stats,loadMs:r.result.loadMs})),
 librarySha256:own[0].result.librarySha256};
}
const report={schemaVersion:1,classification:'local-diagnostic-not-release-claim',workload:'qwen3-reranker-three-documents',backend:'amd-vulkan',
 comparator:'Candidate Doe versus predecessor Doe and Node webgpu 0.4.0 (Dawn)',policy,checks:{independentOraclePassed:true,retainedPlanAndInputMatch:true,declaredAndRecordedExecutionShapeMatch:true,processBoundaryGpuActivityAdmitted:true},
 providerObservationDifferences:['Adapter spelling and architecture labels differ between providers.','Reported maximum buffer size differs by three bytes; neither changes this workload allocation shape.','Resolved execution digests include those provider observations and are expected to differ.'],
 limitations:['Process-boundary GPU observation cannot see every short-lived client.','Recorded operation counters are model observations, not a native GPU trace.','This measures one warm reranking workload, not complete search or general model performance.'],
 results:combined,
 candidateOverBaselineMedian:combined.candidate.queryMs.median/combined.baseline.queryMs.median,
 candidateOverBaselineP95:combined.candidate.queryMs.p95/combined.baseline.queryMs.p95,
 candidateOverDawnMedian:combined.candidate.queryMs.median/combined.dawn.queryMs.median,
 candidateOverDawnP95:combined.candidate.queryMs.p95/combined.dawn.queryMs.p95};
await fs.writeFile(`${root}/comparison.json`,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));

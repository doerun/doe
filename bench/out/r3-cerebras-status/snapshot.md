# Cerebras lane snapshot

This file is **generated** by `bench/tools/cerebras_status_snapshot.py`.
Do not edit by hand. Re-run the tool to refresh.

Generated: `2026-05-06T15:24:24.146651+00:00`

| Lane | Verdict | Scope | Blocker | Artifact mtime | Artifact |
| --- | --- | --- | --- | --- | --- |
| `compile.cross_model_parity` | ✅ bound | requiredLanes=gemma4_31b_af32,qwen3_6_27b_af32 |  | 2026-05-05T17:47:31.404227+00:00 | `bench/out/r3-cross-model-parity/receipt.json` |
| `gemma.per_kernel.summary` | ❌ blocked |  | 1/1 kernels not bound: lm_head_prefill_width_tile_x0_w32 | 2026-05-05T16:37:55.906294+00:00 | `bench/out/r3-1-31b-af16-manifest-simfabric-per-kernel/summary.json` |
| `gemma.per_kernel.lm_head_prefill_width_tile_x0_w32` | ❌ blocked |  | simfabric_d2h_copyback_stall_after_launch_complete [dispatchTimedOut] | 2026-05-05T16:37:55.905836+00:00 | `bench/out/r3-1-31b-af16-manifest-simfabric-per-kernel/lm_head_prefill_width_tile_x0_w32.json` |
| `qwen.per_kernel.summary` | ❓ missing |  |  | n/a | `bench/out/r3-2-27b-af16-manifest-simfabric-per-kernel/summary.json` |
| `qwen.per_kernel.attn_decode` | ❌ blocked |  | dry_run | 2026-04-29T20:44:37.436985+00:00 | `bench/out/r3-2-27b-af16-manifest-simfabric-per-kernel/attn_decode.json` |
| `qwen.per_kernel.attn_prefill_kv_axis_sharded` | ❌ blocked |  | dry_run | 2026-04-29T20:44:37.150389+00:00 | `bench/out/r3-2-27b-af16-manifest-simfabric-per-kernel/attn_prefill_kv_axis_sharded.json` |
| `qwen.per_kernel.embed` | ❌ blocked |  | dry_run | 2026-04-29T20:44:34.374552+00:00 | `bench/out/r3-2-27b-af16-manifest-simfabric-per-kernel/embed.json` |
| `qwen.per_kernel.gemv` | ❌ blocked |  | dry_run | 2026-04-29T20:44:37.428040+00:00 | `bench/out/r3-2-27b-af16-manifest-simfabric-per-kernel/gemv.json` |
| `qwen.per_kernel.kv_write` | ❌ blocked |  | dry_run | 2026-04-29T20:44:37.433215+00:00 | `bench/out/r3-2-27b-af16-manifest-simfabric-per-kernel/kv_write.json` |
| `qwen.per_kernel.o_gate` | ❌ blocked |  | dry_run | 2026-04-29T20:44:37.154169+00:00 | `bench/out/r3-2-27b-af16-manifest-simfabric-per-kernel/o_gate.json` |
| `qwen.per_kernel.residual` | ❌ blocked |  | dry_run | 2026-04-29T20:44:37.157508+00:00 | `bench/out/r3-2-27b-af16-manifest-simfabric-per-kernel/residual.json` |
| `qwen.per_kernel.residual_decode` | ❌ blocked |  | dry_run | 2026-04-29T20:44:37.161309+00:00 | `bench/out/r3-2-27b-af16-manifest-simfabric-per-kernel/residual_decode.json` |
| `qwen.per_kernel.residual_prefill` | ❌ blocked |  | dry_run | 2026-04-29T20:44:37.160759+00:00 | `bench/out/r3-2-27b-af16-manifest-simfabric-per-kernel/residual_prefill.json` |
| `qwen.per_kernel.rmsnorm` | ❌ blocked |  | dry_run | 2026-04-29T20:44:34.380062+00:00 | `bench/out/r3-2-27b-af16-manifest-simfabric-per-kernel/rmsnorm.json` |
| `qwen.per_kernel.rmsnorm_decode` | ❌ blocked |  | dry_run | 2026-04-29T20:44:34.385545+00:00 | `bench/out/r3-2-27b-af16-manifest-simfabric-per-kernel/rmsnorm_decode.json` |
| `qwen.per_kernel.rmsnorm_prefill` | ❌ blocked |  | dry_run | 2026-04-29T20:44:34.384749+00:00 | `bench/out/r3-2-27b-af16-manifest-simfabric-per-kernel/rmsnorm_prefill.json` |
| `qwen.per_kernel.rope_partial` | ❌ blocked |  | dry_run | 2026-04-29T20:44:34.476921+00:00 | `bench/out/r3-2-27b-af16-manifest-simfabric-per-kernel/rope_partial.json` |
| `qwen.per_kernel.sample` | ✅ bound |  |  | 2026-04-30T02:49:30.107192+00:00 | `bench/out/r3-2-27b-af16-manifest-simfabric-per-kernel/sample.json` |
| `qwen.per_kernel.silu_gated` | ❌ blocked |  | dry_run | 2026-04-29T20:44:37.164527+00:00 | `bench/out/r3-2-27b-af16-manifest-simfabric-per-kernel/silu_gated.json` |
| `qwen.per_kernel.ssm_conv1d_depthwise` | ❌ blocked |  | dry_run | 2026-04-29T20:44:34.386889+00:00 | `bench/out/r3-2-27b-af16-manifest-simfabric-per-kernel/ssm_conv1d_depthwise.json` |
| `qwen.per_kernel.ssm_l2_normalize` | ❌ blocked |  | dry_run | 2026-04-29T20:44:34.387573+00:00 | `bench/out/r3-2-27b-af16-manifest-simfabric-per-kernel/ssm_l2_normalize.json` |
| `qwen.per_kernel.ssm_linear_attention` | ❌ blocked |  | dry_run | 2026-04-29T20:44:34.388716+00:00 | `bench/out/r3-2-27b-af16-manifest-simfabric-per-kernel/ssm_linear_attention.json` |
| `qwen.per_kernel.tiled` | ❌ blocked |  | dry_run | 2026-04-29T20:44:34.474985+00:00 | `bench/out/r3-2-27b-af16-manifest-simfabric-per-kernel/tiled.json` |
| `gemma.bounded_smoke` | ❌ blocked |  | inference_evidence_gate.session_transcript_not_output_ready (+9 more) | 2026-05-05T17:02:40.250607+00:00 | `bench/out/r3-1-31b-af16-bounded-inference-smoke/receipt.json` |
| `gemma.local_simfabric_ceiling` | ❌ blocked | memcpy_d2h_start | simfabric_d2h_copyback_stall_after_launch_complete | 2026-05-06T15:18:45.318537+00:00 | `bench/out/r3-1-31b-af16-local-simfabric-ceiling/receipt.json` |
| `gemma.doppler_csl_splice.single_block_hidden` | ❌ blocked | single_block_hidden, layer=59, promptTokens=7, handoffPromptTokens=7 | launch[1]_blocked:prefill_q4k_gemv_tile_dispatch_budget_exhausted:1<259 | 2026-05-06T15:22:48.583650+00:00 | `bench/out/r3-1-31b-af16-doppler-csl-splice/single_block_hidden-run.json` |
| `gemma.doppler_csl_splice.last_layer_tail_token` | ❌ blocked | last_layer_tail_token, layer=59, promptTokens=7 | csl_splice_token_absent | 2026-05-06T15:22:55.665658+00:00 | `bench/out/r3-1-31b-af16-doppler-csl-splice/last-layer-tail-token.json` |
| `gemma.doppler_csl_splice.selected_logit` | ✅ bound | selected_lm_head_logit, layer=59, promptTokens=7, token=3730, logitAbsDiff=0.0087417 |  | 2026-05-06T15:22:55.520622+00:00 | `bench/out/r3-1-31b-af16-doppler-csl-splice/selected-logit-splice/selected-logit-splice.json` |
| `qwen.doppler_csl_splice.selected_logit` | ✅ bound | selected_lm_head_logit, layer=63, promptTokens=18, token=760, logitAbsDiff=0.0133286 |  | 2026-05-06T15:11:51.171939+00:00 | `bench/out/r3-2-27b-af16-doppler-csl-splice/selected-logit-splice/selected-logit-splice.json` |
| `qwen.multi_token_decode` | ❌ blocked |  | boundKernelCount=0/3 | 2026-05-04T14:51:01.824465+00:00 | `bench/out/r3-2-27b-qwen-multi-token-decode/receipt.json` |
| `gemma.simfabric_cells` | ⚠️ pass_with_documented_canary_constraints |  |  | 2026-05-06T15:18:45.285968+00:00 | `bench/out/r3-1-31b-gemma-af16-simfabric-cells/summary-receipt.json` |
| `qwen.simfabric_cells` | ⚠️ pass_with_documented_canary_constraints |  |  | 2026-05-04T14:50:55.394919+00:00 | `bench/out/r3-2-27b-qwen-simfabric-cells/summary-receipt.json` |
| `gemma.phase7_session` | 🔄 in_progress |  | lastCompleteLaunch=26; lastEvent=prefill_q4k_gemv_group_start; target=tiled_31b | 2026-05-05T06:16:22.884942+00:00 | `bench/out/r3-1-31b-af16-hostplan-session-bos-raw-sky-color-is-fast-embed512/progress.jsonl` |
| `gemma.phase7_trace_synth` | ❌ blocked |  | manifest_kernel_dispatch_not_bound | 2026-05-04T17:37:55.344452+00:00 | `bench/out/r3-1-31b-af16-hostplan-streaming/trace-bos-raw-sky-color-is-fast-embed512-exec.json` |

const std = @import("std");
const support = @import("host_hotpath_bench_support.zig");
const cases = @import("host_hotpath_bench_cases.zig");

comptime {
    _ = support;
    _ = cases;
}

pub fn main() !void {
    var arena_impl = std.heap.ArenaAllocator.init(std.heap.page_allocator);
    defer arena_impl.deinit();
    const arena = arena_impl.allocator();

    const args = try std.process.argsAlloc(arena);
    defer std.process.argsFree(arena, args);
    const cfg = try support.parseArgs(args[1..]);

    const medium_escape = "trace phase mismatch -> setup=0 encode=1 submit/wait; user=\"bench\" path=kernel_dispatch";
    const long_escape = try support.buildLongEscapeInput(arena);
    const large_wgsl = try support.buildLargeWgsl(arena);

    const lhs = try arena.alloc(f64, support.NUMERIC_VECTOR_LEN);
    const rhs = try arena.alloc(f64, support.NUMERIC_VECTOR_LEN);
    const values = try arena.alloc(f64, support.NUMERIC_VECTOR_LEN);
    const q = try arena.alloc(f64, support.ATTENTION_HEAD_DIM);
    const k = try arena.alloc(f64, support.ATTENTION_SEQ_LEN * support.ATTENTION_HEAD_DIM);
    const v = try arena.alloc(f64, support.ATTENTION_SEQ_LEN * support.ATTENTION_VALUE_DIM);
    support.fillNumericData(lhs, rhs, values, q, k, v);

    const scalar_weighted = try arena.alloc(f64, support.ATTENTION_SEQ_LEN);
    const simd_weighted = try arena.alloc(f64, support.ATTENTION_SEQ_LEN);
    const scalar_output = try arena.alloc(f64, support.ATTENTION_VALUE_DIM);
    const simd_output = try arena.alloc(f64, support.ATTENTION_VALUE_DIM);

    var case_results: std.ArrayList(support.CaseResult) = .empty;
    try case_results.append(arena, try cases.createTraceCase(arena, cfg, "trace_json_escape_short_plain", "Short trace JSON string with no escapes.", "kernel_dispatch_ok"));
    try case_results.append(arena, try cases.createTraceCase(arena, cfg, "trace_json_escape_medium_mixed", "Medium trace JSON string with quotes, backslashes, and separators.", medium_escape));
    try case_results.append(arena, try cases.createTraceCase(arena, cfg, "trace_json_escape_long_dense", "Long trace JSON string with repeated escaping and control characters.", long_escape));
    try case_results.append(arena, try cases.createStatusCase(arena, cfg, "trace_status_normalize_medium", "Medium execution-status normalization workload.", "Shader module failed: invalid-entry_point / stage=compute", "unknown_error"));
    try case_results.append(arena, try cases.createStatusCase(arena, cfg, "trace_status_normalize_long", "Long execution-status normalization workload.", "queue submit wait failed after 3 retries :: status=DEVICE_LOST :: adapter=unknown :: fallback to explicit unsupported", "device_lost"));
    try case_results.append(arena, try cases.createLexerCase(arena, cfg, "lexer_small_shader", "Tokenize a compact WGSL corpus.", support.SMALL_WGSL));
    try case_results.append(arena, try cases.createLexerCase(arena, cfg, "lexer_large_shader", "Tokenize a large WGSL corpus with comments and repeated declarations.", large_wgsl));
    try case_results.append(arena, try cases.createDotCase(arena, cfg, lhs, rhs));
    try case_results.append(arena, try cases.createSumCase(arena, cfg, values));

    var attention = cases.AttentionBench{
        .q = q,
        .k = k,
        .v = v,
        .scalar_weighted = scalar_weighted,
        .simd_weighted = simd_weighted,
        .scalar_output = scalar_output,
        .simd_output = simd_output,
        .scale = 1.0 / @sqrt(@as(f64, support.ATTENTION_HEAD_DIM)),
    };
    try case_results.append(arena, try cases.createAttentionCase(arena, cfg, &attention));

    var linked_queue = cases.LinkedQueueBench{ .allocator = std.heap.c_allocator };
    var ring_queue = try cases.RingQueueBench.init(arena);
    defer ring_queue.deinit(arena);
    try case_results.append(arena, try cases.createQueueCase(arena, cfg, &linked_queue, &ring_queue));

    const waiter_nodes = try cases.makeWaiterNodes(arena);
    var flat_singleflight = cases.FlatSingleflightBench{
        .allocator = arena,
        .nodes = waiter_nodes,
    };
    defer flat_singleflight.deinit();
    var intrusive_singleflight = cases.IntrusiveSingleflightBench{ .nodes = waiter_nodes };
    try case_results.append(arena, try cases.createSingleflightCase(arena, cfg, &flat_singleflight, &intrusive_singleflight));

    const artifact = support.Artifact{
        .host = try support.makeHostMetadata(arena),
        .cases = try case_results.toOwnedSlice(arena),
    };
    try support.writeArtifact(arena, artifact, cfg.out_path);
}

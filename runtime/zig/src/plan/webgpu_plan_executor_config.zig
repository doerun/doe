pub const RunOptions = struct {
    plan_path: []const u8,
    trace_meta_path: []const u8,
    trace_jsonl_path: []const u8,
    workload_id: []const u8,
    dry_run: bool = false,
    backend_id_override: ?[]const u8 = null,
};

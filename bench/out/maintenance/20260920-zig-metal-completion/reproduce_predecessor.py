"""Exercise the predecessor's actual deferred rollover with a recording bridge."""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile

BASE = "bd1a81618031db0ebc7d759d863fd6a7027fd003"


def extract_function(source: str, name: str) -> str:
    start = source.index("fn " + name + "(")
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def main() -> int:
    root = Path.cwd()
    output = Path(__file__).resolve().parent
    source = subprocess.check_output(
        ["git", "show", BASE + ":runtime/zig/src/backend/metal/metal_runtime_queue_ops.zig"], text=True)
    probe = '''const std = @import("std");
const bridge = struct {
    var lost_failed_submission = false;
    var commits: usize = 0;
    fn metal_bridge_release(_: ?*anyopaque) void { lost_failed_submission = true; }
    fn metal_bridge_command_buffer_commit(_: ?*anyopaque) void { commits += 1; }
    fn metal_bridge_command_buffer_encode_signal_event(_: ?*anyopaque, _: ?*anyopaque, _: u64) void {}
    fn metal_bridge_end_compute_encoding(_: ?*anyopaque) void {}
    fn metal_bridge_render_encoder_end(_: ?*anyopaque) void {}
    fn metal_bridge_end_blit_encoding(_: ?*anyopaque) void {}
};
fn flush_queue(_: anytype) !u64 { return 0; }
const Owner = struct {
    streaming_cmd_buf: ?*anyopaque = null,
    outstanding_cmd_buf: ?*anyopaque = null,
    streaming_compute_encoder: ?*anyopaque = null,
    streaming_render_encoder: ?*anyopaque = null,
    streaming_blit_encoder: ?*anyopaque = null,
    streaming_gpu_timestamps_active: bool = false,
    streaming_compute_dispatch_count: u32 = 0,
    streaming_has_render: bool = false,
    streaming_has_copy: bool = false,
    streaming_max_upload_bytes: usize = 0,
    shared_event: ?*anyopaque = null,
    fence_value: u64 = 0,
    has_deferred_submissions: bool = false,
};
'''
    for name in ("retire_outstanding_handle", "finalize_streaming_encoders", "transition_streaming_submission_deferred"):
        probe += extract_function(source, name) + "\n"
    probe += '''test "rollover must preserve the earlier failed submission for status inspection" {
    var first: u8 = 0;
    var second: u8 = 0;
    var owner = Owner{ .streaming_cmd_buf = &first };
    try transition_streaming_submission_deferred(&owner);
    owner.streaming_cmd_buf = &second;
    try transition_streaming_submission_deferred(&owner);
    try std.testing.expectEqual(@as(usize, 2), bridge.commits);
    try std.testing.expect(!bridge.lost_failed_submission);
}
'''
    (output / "predecessor-rollover-probe.zig").write_text(probe, encoding="utf-8")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".zig", dir=root / "runtime/zig", prefix=".completion-predecessor-", encoding="utf-8") as temporary:
        temporary.write(probe)
        temporary.flush()
        command = ["zig", "test", temporary.name]
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    (output / "predecessor-rollover.log").write_text(
        f"Base: {BASE}\nCommand: {' '.join(command)}\n{result.stdout}\nexitCode={result.returncode}\n", encoding="utf-8")
    print(result.stdout)
    return int(result.returncode == 0 or "FAIL (TestUnexpectedResult)" not in result.stdout)


if __name__ == "__main__":
    raise SystemExit(main())

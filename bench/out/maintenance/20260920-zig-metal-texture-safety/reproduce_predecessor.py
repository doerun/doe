"""Reproduce undersized staging with the predecessor's actual allocation helper."""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile

BASE = "4eec28db09a06df1ff977e7cddfe7dfdb831e220"


def main() -> int:
    root = Path.cwd()
    output = Path(__file__).resolve().parent
    source = subprocess.check_output(
        ["git", "show", BASE + ":runtime/zig/src/backend/metal/metal_copy_runtime.zig"], text=True)
    start = source.index("fn alignedStagingSize(")
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    probe = '''const std = @import("std");
const model_resource_types = @import("src/contracts/model/model_resource_types.zig");
''' + source[start:end] + '''
test "predecessor must retain the padded texture footprint" {
    const cmd = model_resource_types.CopyCommand{
        .direction = .texture_to_texture,
        .src = .{ .handle = 1, .width = 4, .height = 4, .depth_or_array_layers = 2, .bytes_per_row = 256, .rows_per_image = 6 },
        .dst = .{ .handle = 2 },
        .bytes = 128,
        .uses_temporary_buffer = true,
        .temporary_buffer_alignment = 256,
    };
    try std.testing.expectEqual(@as(u64, 2560), try alignedStagingSize(cmd));
}
'''
    (output / "predecessor-staging-probe.zig").write_text(probe, encoding="utf-8")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".zig", prefix=".texture-predecessor-", dir=root / "runtime/zig", encoding="utf-8") as temporary:
        temporary.write(probe)
        temporary.flush()
        command = ["zig", "test", temporary.name]
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    (output / "predecessor-staging.log").write_text(
        f"Base: {BASE}\nCommand: {' '.join(command)}\n{result.stdout}\nexitCode={result.returncode}\n", encoding="utf-8")
    print(result.stdout)
    return int(result.returncode == 0 or "expected 2560, found 256" not in result.stdout)


if __name__ == "__main__":
    raise SystemExit(main())

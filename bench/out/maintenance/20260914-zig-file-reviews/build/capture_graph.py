"""Capture build option bytes and native link recipes without installing code."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess


NATIVE_ARTIFACTS = (
    "dropin_lib", "exe", "module_runner", "doe_plan_executor",
    "core_dropin_lib", "full_dropin_lib", "test_exec", "core_test_exec",
    "full_test_exec", "d3d12_test_exec", "metal_compute_bench",
    "metal_staged_write_bench",
)
TARGETS = ("x86_64-linux-gnu", "x86_64-windows-gnu", "aarch64-macos")
GRAPH_CAPTURE = r'''
    var review_graph = std.ArrayList(u8).empty;
    for ([_]*std.Build.Step.Compile{ARTIFACTS}) |artifact| {
        const module = artifact.root_module;
        review_graph.print(b.allocator, "{s}\tlibc\t{any}\n", .{artifact.name, module.link_libc}) catch @panic("capture allocation");
        for (module.link_objects.items) |object| switch (object) {
            .system_lib => |library| {
                const detail = std.json.Stringify.valueAlloc(b.allocator, library, .{}) catch @panic("capture library");
                review_graph.print(b.allocator, "{s}\tlibrary\t{s}\n", .{artifact.name, detail}) catch @panic("capture allocation");
            },
            .c_source_file => |source| {
                const relative = std.fs.path.relative(b.allocator, b.path(".").getPath(b), source.file.getPath(b)) catch @panic("capture path");
                const flags = std.json.Stringify.valueAlloc(b.allocator, source.flags, .{}) catch @panic("capture flags");
                review_graph.print(b.allocator, "{s}\tc_source\t{s}\t{s}\n", .{artifact.name, relative, flags}) catch @panic("capture allocation");
            },
            else => @panic("unrecorded native link object"),
        };
        for (module.frameworks.keys(), module.frameworks.values()) |name, options| {
            const detail = std.json.Stringify.valueAlloc(b.allocator, options, .{}) catch @panic("capture framework");
            review_graph.print(b.allocator, "{s}\tframework\t{s}\t{s}\n", .{artifact.name, name, detail}) catch @panic("capture allocation");
        }
    }
    std.fs.cwd().writeFile(.{.sub_path = "DESTINATION/graph.tsv", .data = review_graph.items}) catch @panic("capture graph output");
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("before", "after"))
    args = parser.parse_args()
    evidence = Path(__file__).resolve().parent
    repo = evidence.parents[4]
    runtime = repo / "runtime/zig"
    original = (runtime / "build.zig").read_text(encoding="utf-8")
    probe = runtime / "build.review_probe.zig"
    if probe.exists():
        raise FileExistsError(probe)
    try:
        for target in TARGETS:
            for verified in (False, True):
                mode = str(verified).lower()
                output = evidence / args.phase / target / mode
                output.mkdir(parents=True, exist_ok=True)
                injection = GRAPH_CAPTURE.replace("ARTIFACTS", ", ".join(NATIVE_ARTIFACTS))
                injection = injection.replace("DESTINATION", output.as_posix())
                for name in ("build_options", "compute_build_options", "full_build_options"):
                    injection += (
                        '    std.fs.cwd().writeFile(.{ .sub_path = "'
                        + (output / (name + ".txt")).as_posix()
                        + '", .data = ' + name
                        + '.contents.items }) catch @panic("capture options");\n'
                    )
                marker = "    const shader_bench_exe = b.addExecutable(.{"
                if original.count(marker) != 1:
                    raise ValueError("expected one graph insertion point")
                probe.write_text(original.replace(marker, injection + marker), encoding="utf-8")
                result = subprocess.run(
                    ["zig", "build", "--build-file", probe.name,
                     f"-Dtarget={target}", f"-Dlean-verified={mode}", "--help"],
                    cwd=runtime, capture_output=True, check=False,
                )
                (output / "capture.log").write_bytes(result.stdout + result.stderr)
                result.check_returncode()
                print(f"captured {args.phase}: {target}, lean_verified={mode}")
    finally:
        probe.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

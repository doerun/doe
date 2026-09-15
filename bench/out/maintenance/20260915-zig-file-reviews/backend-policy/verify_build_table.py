"""Capture native build recipes and generated options around policy generation."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
RUNTIME = HERE / "build-scratch/runtime/zig"
OPTION_NAMES = ("build_options", "compute_build_options", "full_build_options")
TARGETS = ("x86_64-linux-gnu", "x86_64-windows-gnu", "aarch64-macos")
PREDECESSOR = "b271907c4"


def main() -> None:
    helper = REPO / "bench/out/maintenance/20260914-zig-file-reviews/build/capture_graph.py"
    spec = importlib.util.spec_from_file_location("capture_graph", helper)
    assert spec is not None and spec.loader is not None
    capture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(capture)
    before = subprocess.check_output(
        ["git", "show", f"{PREDECESSOR}:runtime/zig/build.zig"], cwd=REPO, text=True,
    )
    after = (REPO / "runtime/zig/build.zig").read_text()
    probe = RUNTIME / "build.review_probe.zig"
    assert not probe.exists()
    marker = "    const shader_bench_exe = b.addExecutable(.{"
    rows = ["target\tproof\tnativeGraphEqual\toldOptionsPreserved\n"]
    try:
        for target in TARGETS:
            for proof in ("false", "true"):
                outputs = []
                for phase, source in (("before", before), ("after", after)):
                    assert source.count(marker) == 1
                    output = HERE / "build-table" / target / proof / phase
                    output.mkdir(parents=True, exist_ok=True)
                    injection = capture.GRAPH_CAPTURE.replace("ARTIFACTS", ", ".join(capture.NATIVE_ARTIFACTS))
                    injection = injection.replace("DESTINATION", output.as_posix())
                    for name in OPTION_NAMES:
                        injection += (
                            '    std.fs.cwd().writeFile(.{ .sub_path = "'
                            + (output / (name + ".txt")).as_posix()
                            + '", .data = ' + name + '.contents.items }) catch @panic("capture options");\n'
                        )
                    probe.write_text(source.replace(marker, injection + marker))
                    result = subprocess.run(
                        ["/home/x/.local/bin/zig", "build", "--build-file", probe.name,
                         f"-Dtarget={target}", f"-Dlean-verified={proof}", "--help"],
                        cwd=RUNTIME, capture_output=True, check=False,
                    )
                    (output / "capture.log").write_bytes(result.stdout + result.stderr)
                    result.check_returncode()
                    outputs.append(output)
                old, new = outputs
                assert (old / "graph.tsv").read_bytes() == (new / "graph.tsv").read_bytes()
                for name in OPTION_NAMES:
                    old_options = (old / (name + ".txt")).read_bytes()
                    new_options = (new / (name + ".txt")).read_bytes()
                    assert new_options.endswith(old_options), (target, proof, name)
                    assert b"pub const backend_runtime_policy:" in new_options[: -len(old_options)]
                rows.append(f"{target}\t{proof}\ttrue\ttrue\n")
                (HERE / "build-table.tsv").write_text("".join(rows))
                print(target, proof, "pass", flush=True)
    finally:
        probe.unlink(missing_ok=True)


if __name__ == "__main__":
    main()

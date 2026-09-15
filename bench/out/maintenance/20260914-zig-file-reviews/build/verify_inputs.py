"""Exercise required-input errors through the actual build module."""
from pathlib import Path
import resource
import subprocess


def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    evidence = Path(__file__).resolve().parent
    runtime = evidence.parents[4] / "runtime/zig"
    source = (runtime / "build.zig").read_text()
    probe = runtime / "build.review_input_probe.zig"
    if probe.exists():
        raise FileExistsError(probe)
    cases = (
        ("missing", "__doe_review_missing_input__", 1, "FileNotFound"),
        ("oversized", "build.zig", 1, "FileTooBig"),
    )
    rows = ["case\texitCode\tpath\texpectedError\tmatched"]
    try:
        for name, path, limit, error in cases:
            marker = "pub fn build(b: *std.Build) void {"
            injection = f'\n    _ = readFileAlloc(b.allocator, "{path}", {limit});'
            assert source.count(marker) == 1
            probe.write_text(source.replace(marker, marker + injection))
            result = subprocess.run(
                ["zig", "build", "--build-file", probe.name, "--help"],
                cwd=runtime, capture_output=True, check=False,
            )
            output = result.stdout + result.stderr
            (evidence / f"input-{name}.log").write_bytes(output)
            matched = result.returncode != 0 and path.encode() in output and error.encode() in output
            rows.append(f"{name}\t{result.returncode}\t{path}\t{error}\t{matched}")
            if not matched:
                raise AssertionError(output.decode(errors="replace"))
    finally:
        probe.unlink(missing_ok=True)
        (evidence / "input-errors.tsv").write_text("\n".join(rows) + "\n")


if __name__ == "__main__":
    main()

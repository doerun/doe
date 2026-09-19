"""Bind the retained public regression observations to native shader events."""
from __future__ import annotations

from collections import Counter
import json
import subprocess
from pathlib import Path


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.startswith("{")]


def main() -> int:
    root = Path(__file__).resolve().parent
    public = rows(root / "validated-trace.log")
    ordinary = rows(root / "validated-ordinary.log")
    native = rows(root / "validated-native.jsonl")
    compute = [row for row in public if "dispatch" in row]
    encoded = [row for row in native if row["event"] == "dispatch_encoded"]
    expected = Counter((row["sourceSha256"], row["entryPoint"], row["dispatch"])
                       for row in compute)
    observed = Counter((row["wgslSha256"], row["entryPoint"], row["workgroups"][0])
                       for row in encoded)
    if not expected or expected != observed:
        raise ValueError("public sources, entrypoints and dispatches differ from native events")
    if any(row["workgroups"][1:] != [1, 1] for row in encoded):
        raise ValueError("native dispatch Y/Z dimensions differ from public inputs")
    for run in (public, ordinary):
        for row in run:
            if "expected" in row and row["actual"] != row["expected"]:
                raise ValueError(f"incorrect output: {row['label']}")
    outputs = lambda run: [(row["label"], row.get("path"), row["actual"])
                           for row in run if "actual" in row]
    if outputs(public) != outputs(ordinary):
        raise ValueError("diagnostic and ordinary output observations differ")
    render = [row for row in public if "actual" in row and "dispatch" not in row]
    draws = [row for row in native if row["event"] == "render_draw_executed"]
    if len(render) != 1 or len(draws) != 1:
        raise ValueError("expected exactly one render observation and native draw")
    if render[0]["actual"] != [9, 5, 8, 10]:
        raise ValueError("incorrect render output")
    draw = draws[0]
    if any(draw[key] != render[0]["sourceSha256"] for key in
           ("vertexWgslSha256", "fragmentWgslSha256")):
        raise ValueError("render source identity differs from native stages")
    if draw["args"] != [3, 1, 0, 0]:
        raise ValueError("native draw arguments differ from public inputs")
    artifact_fields = ("backendArtifactFile", "vertexBackendArtifactFile",
                       "fragmentBackendArtifactFile")
    artifacts = {row[key] for row in native for key in artifact_fields if key in row}
    for artifact in sorted(artifacts):
        subprocess.run(["spirv-val", "--target-env", "vulkan1.1",
                        str(root / artifact)], check=True)
    print(f"PASS: Vulkan-target SPIR-V artifacts validated: {len(artifacts)}")
    print(f"PASS: public/native compute invocations matched: {len(compute)}")
    print("PASS: render source and draw identity matched")
    print("PASS: diagnostic and ordinary outputs matched independent byte oracles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

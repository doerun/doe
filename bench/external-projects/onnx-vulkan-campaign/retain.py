"""Retain raw campaign observations and exact local binary custody, without promotion."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import tarfile


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run", type=Path, required=True, help="Completed campaign directory"
    )
    parser.add_argument(
        "--report", type=Path, required=True, help="New retained report directory"
    )
    parser.add_argument(
        "--custody", type=Path, required=True, help="New ignored custody archive"
    )
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[3]
    args.run = args.run.resolve()
    args.report.mkdir(parents=True, exist_ok=False)
    args.custody.parent.mkdir(parents=True, exist_ok=True)
    files = {}

    def retain(source: Path, relative: str) -> None:
        data = source.read_bytes()
        compress = source.suffix == ".log" or len(data) > 200000
        target_name = relative + (".gz" if compress else "")
        target = args.report / target_name
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = gzip.compress(data, mtime=0) if compress else data
        target.write_bytes(payload)
        files[target_name] = {
            "sha256": sha(payload),
            "contentSha256": sha(data),
            "originalPath": str(source.resolve()),
            "compression": "gzip" if compress else "none",
        }

    for path in sorted(args.run.iterdir()):
        if path.is_file() and path.suffix in [".json", ".log", ".cc", ".cmake"]:
            retain(path, "raw/" + path.name)
    for directory in [
        "measurement",
        "measurement-qualified",
        "warm-profile",
        "compiler-reproduction",
        "bridge-matched",
        "control-reproduction",
        "application-matched",
        "reference",
        "execution-harness",
        "historical-source",
        "upstream/onnx-headers",
        "deployment-final/results",
    ]:
        for path in sorted((args.run / directory).rglob("*")):
            if (
                path.is_file()
                and not path.is_symlink()
                and path.suffix
                in [
                    ".json",
                    ".log",
                    ".observations",
                    ".wgsl",
                    ".zig",
                    ".h",
                    ".cpp",
                    ".cc",
                    ".cmake",
                    ".patch",
                    ".py",
                    ".mjs",
                    ".c",
                    ".spv",
                ]
            ):
                retain(path, "raw/" + str(path.relative_to(args.run)))
    for path in sorted((args.run / "doppler-offline-final").iterdir()):
        if path.is_file() and path.suffix == ".json":
            retain(path, "raw/doppler-offline-final/" + path.name)
    for path in sorted((args.run / "doppler-offline-final/results").iterdir()):
        if path.is_file():
            retain(path, "raw/doppler-offline-final/results/" + path.name)
    retain(args.run / "upstream/c_cxx/squeezenet/main.cpp", "raw/upstream/main.cpp")
    retain(args.run / "upstream/LICENSE", "raw/upstream/LICENSE")
    for path in sorted((args.run / "safety").iterdir()):
        if path.is_file() and path.suffix in [".json", ".log"]:
            retain(path, "raw/safety/" + path.name)
    for directory, labels in [
        ("doppler-replay", ["retirement-original"]),
        ("doppler-delivered", ["delivered-final-first", "delivered-final-reopen"]),
    ]:
        for path in sorted((args.run / "safety" / directory / "results").iterdir()):
            if path.is_file() and any(path.name.startswith(label) for label in labels):
                retain(path, "raw/safety/" + directory + "/results/" + path.name)
    for name in [
        "providers.json",
        "installation.json",
        "package.json",
        "package-lock.json",
    ]:
        retain(
            args.run / "safety/doppler-delivered" / name,
            "raw/safety/doppler-delivered/" + name,
        )
    retain(
        repo / "runtime/zig/zig-out/share/doe-build-metadata.json",
        "native-build-metadata.json",
    )
    retain(args.run / "deployment-final/application/bundle.json", "bundle.json")
    retain(repo / "config/onnx-vulkan-campaign.json", "policy.json")
    for name in ["cache-audit.json", "measurement-summary.json"]:
        retain(args.run / name, name)
    retain(
        repo
        / "bench/out/onnx-webgpu-substitution/20261005/adapter/build/CMakeCache.txt",
        "raw/consumer/CMakeCache.txt",
    )
    retain(
        repo / "bench/out/onnx-webgpu-substitution/20261005/adapter/build/build.ninja",
        "raw/consumer/build.ninja",
    )
    retain(
        repo
        / "reports/benchmarks/amd-vulkan/20261005-onnx-proc-adapter/source-build.json",
        "raw/consumer/source-build.json",
    )
    entries = {}
    roots = [
        (args.run / "deployment-final/application", "application"),
        (args.run / "custody-inputs", "build"),
        (args.run / "doppler-offline-final", "doppler"),
    ]
    with args.custody.open("xb") as stream:
        with gzip.GzipFile(
            fileobj=stream, mode="wb", mtime=0, compresslevel=1
        ) as compressed:
            with tarfile.open(fileobj=compressed, mode="w|") as archive:
                for root, prefix in roots:
                    for path in sorted(root.rglob("*")):
                        if not path.is_file() and not path.is_symlink():
                            continue
                        relative = prefix + "/" + str(path.relative_to(root))
                        archive.add(path, arcname=relative, recursive=False)
                        if path.is_symlink():
                            entries[relative] = {
                                "kind": "symlink",
                                "target": str(path.readlink()),
                            }
                        else:
                            entries[relative] = {
                                "kind": "file",
                                "sha256": sha(path.read_bytes()),
                                "bytes": path.stat().st_size,
                                "originalPath": str(path.resolve()),
                            }
    entries_path = args.run / "custody-entries.json"
    entries_path.write_text(json.dumps(entries, indent=2, sort_keys=True) + "\n")
    retain(entries_path, "custody-entries.json")
    sources = {}
    paths = list((repo / "bench/external-projects/onnx-vulkan-campaign").glob("*"))
    paths += [
        repo / name
        for name in [
            "runtime/bridge/dawn-proc-table/adapter.zig",
            "bench/external-projects/onnx-webgpu-substitution/build_adapter.py",
            "runtime/zig/src/compiler/wgsl/emit/spirv/emit_spirv_builtins.zig",
            "runtime/zig/tests/wgsl/emit_spirv_builtin_test.zig",
            "config/onnx-vulkan-campaign.json",
        ]
    ]
    for path in sorted(paths):
        if path.is_file():
            sources[str(path.relative_to(repo))] = sha(path.read_bytes())
    manifest = {
        "schemaVersion": 1,
        "classification": "bounded-vulkan-campaign-custody",
        "files": files,
        "sources": sources,
        "custody": {
            "archivePath": str(args.custody.resolve()),
            "archiveSha256": sha(args.custody.read_bytes()),
            "entriesPath": "custody-entries.json.gz",
            "entryCount": len(entries),
            "availability": "local-only",
        },
        "historicalReport": {
            "path": "reports/benchmarks/amd-vulkan/20261005-onnx-proc-adapter/manifest.json",
            "sha256": sha(
                (
                    repo
                    / "reports/benchmarks/amd-vulkan/20261005-onnx-proc-adapter/manifest.json"
                ).read_bytes()
            ),
            "sourceSnapshotCommit": "b599d2e3a",
        },
        "dopplerCommit": "5a50a0e1",
        "performanceCorrections": 0,
    }
    (args.report / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    measurement = json.loads(
        (args.run / "measurement-qualified/measurement.json").read_text()
    )
    metadata = {
        "traceVersion": 1,
        "module": "onnx-vulkan/squeezenet-session-run",
        "seqMax": len(measurement["rows"]),
        "rowCount": len(measurement["rows"]),
        "hash": sha((args.run / "measurement-qualified/measurement.json").read_bytes()),
        "previousHash": sha((repo / "config/onnx-vulkan-campaign.json").read_bytes()),
        "timingSource": "steady-clock-complete-session-run-wall-ns",
        "timingClass": "independent-process-median-complete-session-run-wall-ns",
    }
    (args.report / "trace-meta.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

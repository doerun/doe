"""Retain CPU observations and exact local binary custody without speed promotion."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

from probe import identity


def retain(run: Path, report: Path, custody: Path) -> None:
    """Store lossless raw evidence, explicit exploratory scope, and executable bytes."""
    report.mkdir(parents=True, exist_ok=False)
    custody.parent.mkdir(parents=True, exist_ok=True)
    if custody.exists():
        raise ValueError("Custody archive must be new")
    repo = Path(__file__).resolve().parents[3]
    files = {}

    def save(source: Path, relative: Path, compress: bool = True) -> None:
        content = source.read_bytes()
        target = report / relative
        if compress:
            target = target.with_name(target.name + ".gz")
        target.parent.mkdir(parents=True, exist_ok=True)
        data = gzip.compress(content, mtime=0) if compress else content
        target.write_bytes(data)
        files[str(target.relative_to(report))] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "contentSha256": hashlib.sha256(content).hexdigest(),
            "contentBytes": len(content),
            "compression": "gzip" if compress else "none",
        }

    save(run / "decision-final.json", Path("decision.json"), False)
    save(run / "caller-collection/policy.json", Path("policy.json"), False)
    libraries = {}
    for collection in ["collection", "caller-collection"]:
        save(run / collection / "policy.json", Path("raw") / collection / "policy.json")
        for directory in sorted((run / collection).iterdir()):
            if not directory.is_dir():
                continue
            for source in sorted(directory.iterdir()):
                if source.is_file() and (
                    source.suffix in [".json", ".log", ".bin"]
                    or source.name in ["observations", "maps"]
                ):
                    save(
                        source, Path("raw") / collection / directory.name / source.name
                    )
            for profile in directory.glob("profile*.json"):
                value = json.loads(profile.read_text())
                for item in value.get("modules", []):
                    libraries[item["library"]["path"]] = item["library"]["sha256"]
    for name in [
        "pilot-doe",
        "owner-doe-0",
        "negative-doe-native",
        "negative-doe-oracle",
        "negative-dawn-native",
        "negative-dawn-oracle",
    ]:
        for source in sorted((run / name).iterdir()):
            if source.is_file():
                save(source, Path("raw") / name / source.name)
    for source in sorted(run.glob("safety-*")):
        if source.suffix in [".json", ".log", ".onnx"]:
            save(source, Path("raw") / source.name)
    for version in [
        "diagnostic",
        "diagnostic-v2",
        "diagnostic-v3",
        "diagnostic-v4",
        "diagnostic-v5",
    ]:
        directory = run / version
        save(directory / "build.json", Path("raw") / version / "build.json")
        for name in ["main.cpp", "application-provider.h"]:
            save(directory / name, Path("raw") / version / name)
        for source in sorted((directory / "sources").glob("*")):
            save(source, Path("raw") / version / "sources" / source.name)
        for source in sorted((directory / "bridge").glob("*.zig")):
            save(source, Path("raw") / version / "bridge" / source.name)
        for source in sorted((directory / "bridge/generated/include").rglob("*.h")):
            save(source, Path("raw") / version / source.relative_to(directory))
        for name in [
            "application",
            "libcpu_probe.so",
            "bridge/libdoe_dawn_bridge.so",
            "libonnxruntime.so.1",
            "squeezenet.onnx",
        ]:
            path = directory / name
            if path.is_file():
                libraries[str(path.resolve())] = identity(path)["sha256"]
    qualified = repo / "bench/out/onnx-vulkan-campaign/20261005"
    for arm in ["doe", "dawn"]:
        source = qualified / f"{arm}-matched.json"
        save(source, Path("raw/qualification") / source.name)
        q = json.loads(source.read_text())
        for item in q["inputs"].values():
            libraries[item["path"]] = item["sha256"]
    for source in [
        qualified / "application-matched/preparation.json",
        qualified / "bridge-matched/build.json",
    ]:
        save(source, Path("raw/qualification") / source.name)
    owned = [
        "runtime/zig/src/native/resource/doe_bind_group_native.zig",
        "runtime/zig/src/native/compute/doe_compute_ext_native.zig",
        "runtime/zig/src/native/command/doe_command_recording.zig",
        "runtime/zig/src/native/vulkan/vulkan_compute_native.zig",
        "runtime/zig/src/native/queue/doe_queue_submit_vulkan.zig",
        "runtime/zig/src/native/support/doe_native_object_helpers.zig",
        "runtime/zig/src/native/support/doe_label_store.zig",
    ]
    for name in owned:
        save(repo / name, Path("raw/native-source") / name)
    current_sources = {
        str(path.relative_to(repo)): identity(path)["sha256"]
        for path in sorted(Path(__file__).resolve().parent.glob("*"))
        if path.is_file()
    }
    entries = []
    with tarfile.open(custody, "w:gz") as archive:
        for index, (name, expected) in enumerate(sorted(libraries.items())):
            path = Path(name)
            if identity(path)["sha256"] != expected:
                raise ValueError("Observed binary changed before custody: " + name)
            member = f"libraries/{index:03d}/{path.name}"
            archive.add(path, arcname=member, recursive=False)
            entries.append({"path": name, "member": member, "sha256": expected})
    historical = (
        repo
        / "reports/benchmarks/amd-vulkan/20261005-onnx-vulkan-campaign/manifest.json"
    )
    manifest = {
        "schemaVersion": 1,
        "classification": "vulkan-cpu-attribution-manifest",
        "files": files,
        "sources": current_sources,
        "nativeSources": {name: identity(repo / name)["sha256"] for name in owned},
        "baseCommit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "historicalManifest": identity(historical),
        "performanceCorrections": 0,
        "custody": {"archive": identity(custody), "entries": entries},
        "scope": {
            "callerCollection": "source-bound-accepted-diagnostic",
            "earlierPrototypes": "exploratory-some-builder-sources-not-retained",
            "performance": "no-candidate-no-claim",
        },
    }
    (report / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run", type=Path, required=True, help="Completed CPU investigation"
    )
    parser.add_argument(
        "--report", type=Path, required=True, help="New retained report"
    )
    parser.add_argument(
        "--custody",
        type=Path,
        required=True,
        help="New ignored local executable archive",
    )
    args = parser.parse_args()
    retain(args.run.resolve(), args.report.resolve(), args.custody.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

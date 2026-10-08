"""Seal device lifecycle evidence separately from earlier application/performance decisions."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[3]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--exploratory", type=Path, help="Rejected prior attempts retained separately"
    )
    args = parser.parse_args()
    run = args.run.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    require_new = out / "manifest.json"
    if require_new.exists():
        parser.error("Manifest already exists; retain it instead of overwriting")

    def retain(source: Path, name: str, compress: bool = False) -> str:
        target = out / (name + (".gz" if compress else ""))
        target.parent.mkdir(parents=True, exist_ok=True)
        data = source.read_bytes()
        target.write_bytes(gzip.compress(data, mtime=0) if compress else data)
        return str(target.relative_to(out))

    retain(ROOT / "config/native-device-lifecycle-contract.json", "policy.json")
    for source in (run / "controls-qualified").iterdir():
        if source.is_file() and source.name != "lifecycle":
            retain(source, "controls/" + source.name)
    profiles = {}
    for arm in ("doe", "dawn"):
        safety_name = "safety-" + arm
        safety = json.loads((run / (safety_name + ".json")).read_text())
        retain(run / (safety_name + ".json"), f"safety/{arm}.json")
        retain(run / (safety_name + ".runner.log"), f"safety/{arm}.log", True)
        retain(Path(safety["profile"]["path"]), f"safety/{arm}-profile.json", True)
        name = f"application-{arm}-qualified"
        app = json.loads((run / (name + ".json")).read_text())
        retain(run / (name + ".json"), f"application/{arm}.json")
        retain(run / (name + ".log"), f"application/{arm}.log", True)
        retain(run / (name + ".observations"), f"application/{arm}.observations")
        profiles[arm] = retain(
            Path(app["profile"]["path"]), f"application/{arm}-profile.json", True
        )
        retain(
            run / f"application-{arm}-disabled.json", f"application/{arm}-disabled.json"
        )
        retain(
            run / f"application-{arm}-disabled.log",
            f"application/{arm}-disabled.log",
            True,
        )
    retain(
        run / "application-doe-oracle-negative.json", "application/oracle-negative.json"
    )
    retain(
        run / "application-doe-oracle-negative.log",
        "application/oracle-negative.log",
        True,
    )
    retain(run / "altered-reference.f32", "inputs/altered-reference.f32", True)
    old = ROOT / "bench/out/onnx-vulkan-campaign/20261005"
    for source, name in [
        (old / "bridge-matched/build.json", "inputs/bridge-build.json"),
        (
            old / "application-matched/preparation.json",
            "inputs/application-preparation.json",
        ),
        (
            run / "native/share/doe-build-metadata.json",
            "inputs/native-build-metadata.json",
        ),
    ]:
        retain(source, name)
    # Failed/intermediate attempts remain evidence, never final admission inputs.
    for source in run.iterdir():
        if source.is_file() and (
            "exploratory" in source.name
            or "-v" in source.name
            or source.suffix == ".log"
        ):
            retain(source, "exploratory/" + source.name, True)
    for directory in ("controls-final", "reproduction"):
        if not (run / directory).exists():
            continue
        for source in (run / directory).iterdir():
            if source.is_file() and source.suffix in (
                ".json",
                ".jsonl",
                ".stderr",
                ".cpp",
            ):
                retain(source, f"exploratory/{directory}/{source.name}", True)
    for name in (
        "zig-qualified.log",
        "native-build-settled.log",
        "native_async_pipeline.log",
        "historical-callback-qualified.log",
    ):
        retain(run / name, "validation/" + name, True)
    for name in (
        "schema-final.log",
        "catscan-final.json",
    ):
        retain(run / name, "validation/" + name, True)
    if args.exploratory:
        parent = args.exploratory.resolve()
        for source in sorted(parent.rglob("*")):
            if (
                source.is_file()
                and not source.is_relative_to(run)
                and source.suffix in (".json", ".jsonl", ".stderr", ".cpp", ".log")
                and not any(
                    part.endswith(".cache") for part in source.relative_to(parent).parts
                )
            ):
                retain(
                    source,
                    "exploratory/prior-attempts/" + str(source.relative_to(parent)),
                    True,
                )
    paths = subprocess.check_output(
        ["git", "diff", "--name-only"], cwd=ROOT, text=True
    ).splitlines()
    paths += [
        str(p.relative_to(ROOT))
        for p in (
            ROOT / "bench/external-projects/onnx-vulkan-device-lifecycle"
        ).iterdir()
        if p.is_file()
    ]
    paths += subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT, text=True
    ).splitlines()
    paths += [
        str(p.relative_to(ROOT))
        for p in (ROOT / "bench/external-projects/onnx-vulkan-callbacks").iterdir()
        if p.is_file()
    ]
    paths += [
        "bench/external-projects/onnx-vulkan-campaign/run_application.py",
        "bench/external-projects/onnx-vulkan-campaign/safety.py",
    ]
    paths += [
        "runtime/zig/src/native/support/doe_device_loss.zig",
        "config/native-device-lifecycle-contract.json",
        "config/native-device-lifecycle-contract.schema.json",
        "config/native-device-lifecycle-evidence.schema.json",
        "bench/tests/test_native_device_lifecycle_evidence.py",
    ]
    snapshots = {}
    for name in sorted(set(paths)):
        if (
            name.startswith(
                (
                    "runtime/zig/",
                    "bench/external-projects/onnx-vulkan-device-lifecycle/",
                    "config/",
                    "bench/external-projects/onnx-vulkan-callbacks/",
                    "bench/external-projects/onnx-vulkan-campaign/",
                    "bench/tests/test_native_device_lifecycle_evidence.py",
                )
            )
            and name != "config/schema-targets.json"
        ):
            source = ROOT / name
            snapshots[name] = {
                "snapshot": retain(source, "sources/" + name, True),
                "sha256": digest(source.read_bytes()),
            }
    retain(run / "consumer-qualification.json", "consumer-qualification.json")
    retain(ROOT / "config/native-callback-contract.json", "callback-policy.json")
    for source in (run / "callback-controls").iterdir():
        if source.is_file() and source.name != "callbacks":
            retain(source, "callback-controls/" + source.name)
    receipt = json.loads((run / "controls-qualified/receipt.json").read_text())
    assets = {Path(v["path"]) for v in receipt["inputs"].values()}
    regression = json.loads((run / "callback-controls/receipt.json").read_text())
    assets.update(Path(v["path"]) for v in regression["inputs"].values())
    assets.add(Path(regression["executable"]["path"]))
    assets.add(Path(receipt["executable"]["path"]))
    assets.update(Path(v["path"]) for v in receipt["headers"].values())
    for arm in ("doe", "dawn"):
        app = json.loads((out / f"application/{arm}.json").read_text())
        assets.update(Path(v["path"]) for v in app["inputs"].values())
    assets.add(run / "native_async_pipeline")
    assets.add(old / "librecovery_control.so")
    archive_path = run / "device-lifecycle-custody.tar.gz"
    members = []
    with tarfile.open(archive_path, "w:gz") as archive:
        for index, path in enumerate(sorted(assets)):
            member = f"{index:02d}/{path.name}"
            archive.add(path, arcname=member)
            members.append(
                {
                    "member": member,
                    "path": str(path),
                    "sha256": digest(path.read_bytes()),
                }
            )
    history = {}
    for name in (
        "20261005-onnx-vulkan-campaign",
        "20261008-onnx-vulkan-cpu-attribution",
        "20261008-onnx-vulkan-callbacks",
    ):
        path = f"reports/benchmarks/amd-vulkan/{name}/manifest.json"
        history[path] = digest((ROOT / path).read_bytes())
    manifest = {
        "schemaVersion": 1,
        "classification": "bounded-native-vulkan-device-lifecycle-evidence",
        "verdict": "qualified-tested-paths",
        "performanceClaim": False,
        "generalConformance": False,
        "sourceBaseCommit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "sourceSnapshots": snapshots,
        "applicationProfiles": profiles,
        "historicalManifests": history,
        "custody": {
            "archive": {
                "path": str(archive_path),
                "sha256": digest(archive_path.read_bytes()),
            },
            "members": members,
        },
        "files": {},
    }
    for path in sorted(out.rglob("*")):
        if path.is_file():
            data = path.read_bytes()
            manifest["files"][str(path.relative_to(out))] = {
                "sha256": digest(data),
                "contentSha256": digest(
                    gzip.decompress(data) if path.suffix == ".gz" else data
                ),
            }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Build a deterministic evaluation archive from checksum-pinned qualified inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True

from distribution import archive, digest, inventory, member_path, verify, write_json

ROOT = Path(__file__).resolve().parents[3]


def build(plan_path: Path, out: Path, input_package: Path | None = None) -> Path:
    """Preserve qualified bytes and produce a relocatable consumer package."""
    import jsonschema

    plan = json.loads(plan_path.read_text("utf-8"))
    schema = json.loads(
        (ROOT / "config/onnx-vulkan-release.schema.json").read_text("utf-8")
    )
    jsonschema.Draft202012Validator(schema).validate(plan)
    if set(plan["inputs"]) & set(plan["ownedFiles"]):
        raise ValueError("Pinned inputs and owned files must not overlap")
    if input_package is not None:
        verify(input_package)
    sources = {}
    for name, source in plan["inputs"].items():
        path = (
            member_path(input_package, name)
            if input_package is not None
            else ROOT / source["path"]
        )
        if digest(path) != source["sha256"]:
            raise ValueError(f"Pinned release input changed: {path}")
        sources[name] = path
    out.mkdir(parents=True, exist_ok=False)
    package = out / "package"
    package.mkdir()
    for name, source in plan["inputs"].items():
        target = member_path(package, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(sources[name], target)
        target.chmod(source["mode"])
    for name, source in plan["ownedFiles"].items():
        target = member_path(package, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / source, target)
        target.chmod(0o644)
    write_json(package / "release-inputs.json", plan)
    (package / "release-inputs.json").chmod(0o644)
    manifest = {
        "schemaVersion": 1,
        "kind": "doe-onnx-vulkan-evaluation",
        "version": plan["version"],
        "target": plan["target"],
        "qualification": plan["qualification"],
        "compatibility": plan["compatibility"],
        "files": inventory(package),
    }
    manifest_schema = json.loads(
        (ROOT / "config/onnx-vulkan-installation.schema.json").read_text("utf-8")
    )
    jsonschema.Draft202012Validator(manifest_schema).validate(manifest)
    write_json(package / "manifest.json", manifest)
    (package / "manifest.json").chmod(0o644)
    path = out / f"doe-onnx-vulkan-{plan['version']}-linux-x64.tar.gz"
    archive(package, path)
    checksum = digest(path)
    (out / (path.name + ".sha256")).write_text(
        f"{checksum}  {path.name}\n", encoding="utf-8"
    )
    write_json(
        out / "build.json",
        {
            "schemaVersion": 1,
            "kind": "doe-onnx-vulkan-archive",
            "version": plan["version"],
            "archive": {
                "path": path.name,
                "sha256": checksum,
                "size": path.stat().st_size,
            },
            "manifestSha256": digest(package / "manifest.json"),
            "planSha256": digest(plan_path),
            "builderSha256": digest(Path(__file__)),
        },
    )
    print(path)
    print(checksum)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan",
        type=Path,
        default=ROOT / "config/onnx-vulkan-release.json",
        help="Pinned release inputs",
    )
    parser.add_argument(
        "--out", type=Path, required=True, help="New artifact directory"
    )
    parser.add_argument(
        "--input-package",
        type=Path,
        help="Verified prior installation supplying pinned inputs without producer paths",
    )
    args = parser.parse_args()
    build(args.plan, args.out, args.input_package)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

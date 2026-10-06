"""Reconstruct the safety-qualified Doppler package and corrected native offline."""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path: Path, value: dict | list) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, required=True, help="Safety-qualified installed snapshot"
    )
    parser.add_argument(
        "--native", type=Path, required=True, help="Qualified corrected native library"
    )
    parser.add_argument(
        "--metadata", type=Path, required=True, help="Build metadata for that library"
    )
    parser.add_argument("--out", type=Path, required=True, help="New delivery snapshot")
    parser.add_argument(
        "--populate-cache",
        action="store_true",
        help="Populate dependency cache during preparation; execution remains isolated and offline",
    )
    args = parser.parse_args()
    root = args.out.resolve()
    shutil.copytree(
        args.source,
        root,
        ignore=shutil.ignore_patterns(
            "results",
            "node_modules",
            "retained-cached-doppler",
            "retained-previous-doppler",
        ),
    )
    (root / "results").mkdir()
    path = (
        Path(__file__).resolve().parent.parent
        / "doppler-generation/installed-generation.py"
    )
    spec = importlib.util.spec_from_file_location("installed_generation", path)
    installation_tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installation_tool)
    archive = root / "archives/doe-source-bound-retirement.tgz"
    replacements = {
        "doe/native/libwebgpu_doe.so": args.native,
        "doe/native/doe-build-metadata.json": args.metadata,
    }
    changed = []
    with tarfile.open(
        root / "archives/doe-source-bound-provider.tgz"
    ) as source, tarfile.open(archive, "w:gz") as target:
        for member in source:
            data = source.extractfile(member).read() if member.isfile() else None
            if member.name in replacements:
                updated = replacements[member.name].read_bytes()
                changed.append(
                    {
                        "path": member.name,
                        "beforeSha256": hashlib.sha256(data).hexdigest(),
                        "afterSha256": hashlib.sha256(updated).hexdigest(),
                    }
                )
                data = updated
                member.size = len(data)
            target.addfile(member, io.BytesIO(data) if data is not None else None)
    if len(changed) != len(replacements):
        raise ValueError("Native archive replacement boundary drift")
    package = json.loads((root / "package.json").read_text())
    package["dependencies"]["doe-gpu"] = "file:archives/doe-source-bound-retirement.tgz"
    write(root / "package.json", package)
    lock = json.loads((root / "package-lock.json").read_text())
    lock["packages"][""]["dependencies"] = package["dependencies"]
    lock["packages"]["node_modules/doe-gpu"]["resolved"] = package["dependencies"][
        "doe-gpu"
    ]
    lock["packages"]["node_modules/doe-gpu"]["integrity"] = (
        "sha512-"
        + base64.b64encode(hashlib.sha512(archive.read_bytes()).digest()).decode()
    )
    write(root / "package-lock.json", lock)
    command = [
        "npm",
        "install",
        *([] if args.populate_cache else ["--offline"]),
        "--ignore-scripts",
        "--omit=optional",
        "--no-audit",
        "--no-fund",
        "--cache",
        str(root / "npm-cache"),
    ]
    with (root / "results/prepare-offline.log").open("w") as log:
        subprocess.run(
            command, cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True
        )
    providers = json.loads((root / "providers.json").read_text())
    providers["archives"] = [
        {
            "path": "/application/"
            + package["dependencies"][name].removeprefix("file:"),
            "sha256": digest(
                root / package["dependencies"][name].removeprefix("file:")
            ),
        }
        for name in ["doppler-gpu", "webgpu", "doe-gpu"]
    ]
    providers["dopplerDependencyLockSha256"] = digest(root / "package-lock.json")
    for item in providers["files"]:
        item["sha256"] = digest(root / item["path"].removeprefix("/application/"))
    write(root / "providers.json", providers)
    installation = json.loads((root / "installation.json").read_text())
    installation["packages"] = []
    for name, dependency in package["dependencies"].items():
        relative = dependency.removeprefix("file:")
        leaf = root / "node_modules" / name
        installation_tool.verify_archive_install(root / relative, leaf)
        installation["packages"].append(
            {
                "name": name,
                "archive": relative,
                "sha256": digest(root / relative),
                "version": json.loads((leaf / "package.json").read_text())["version"],
            }
        )
    files = [
        item["path"]
        for item in installation["files"]
        if not item["path"].startswith("archives/") and item["path"] != "inventory.json"
    ]
    files += [item["archive"] for item in installation["packages"]]
    installation["files"] = [
        {"path": name, "sha256": digest(root / name)} for name in sorted(set(files))
    ]
    write(root / "installation.json", installation)
    write(root / "inventory.json", installation_tool.inventory(root))
    write(
        root / "delivery.json",
        {
            "schemaVersion": 1,
            "classification": "offline-native-archive-reconstruction",
            "originalProviderArchiveSha256": digest(
                root / "archives/doe-source-bound-provider.tgz"
            ),
            "derivedProviderArchiveSha256": digest(archive),
            "replacements": changed,
            "nativeSha256": digest(args.native),
            "dopplerArchiveSha256": digest(
                root / "archives/doppler-retirement-final.tgz"
            ),
            "scope": "Local Linux package snapshot; no registry publication",
            "command": command,
            "preparationNetwork": "enabled" if args.populate_cache else "offline",
        },
    )
    args.destination = root
    installation_tool.execute(args)
    installation_tool.verify(args)
    for label in ["doe-first", "doe-reopen"]:
        if (
            "Deferred destruction failed"
            in (root / "results" / (label + ".log")).read_text()
        ):
            raise ValueError("Retirement warning persists in reconstructed delivery")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

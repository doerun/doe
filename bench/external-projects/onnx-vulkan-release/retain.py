"""Retain reproducible archives and installed raw acceptance without changing history."""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True

from distribution import digest, verify, write_json
from verify_evidence import verify_results

ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("first", "second", "consumer", "out"):
        parser.add_argument(
            "--" + name,
            required=True,
            type=Path,
            help="Selected " + name + " directory",
        )
    args = parser.parse_args()
    builds = []
    for build in (args.first, args.second):
        record = json.loads((build / "build.json").read_text("utf-8"))
        verify(build / "package")
        if digest(build / record["archive"]["path"]) != record["archive"]["sha256"]:
            raise ValueError("Archive bytes do not match producer record")
        if digest(build / "package/manifest.json") != record["manifestSha256"]:
            raise ValueError("Package manifest differs from producer record")
        builds.append(record)
    if builds[0] != builds[1]:
        raise ValueError("Repeated builds are not byte-identical")
    installation = json.loads((args.consumer / "installation.json").read_text("utf-8"))
    if (
        installation["exitCode"] != 0
        or installation["archiveSha256"] != builds[0]["archive"]["sha256"]
        or installation["logSha256"] != digest(args.consumer / "installation.log")
        or "--unshare-net" not in installation["command"]
        or "--clearenv" not in installation["command"]
    ):
        raise ValueError("Installation evidence failed or belongs to another archive")
    acceptance = verify_results(args.consumer / "installed", args.consumer / "results")
    if acceptance["manifestSha256"] != builds[0]["manifestSha256"]:
        raise ValueError("Installed qualification used a different package")
    example = json.loads(
        (args.consumer / "example-results/qualification.json").read_text("utf-8")
    )
    if (
        not example["passed"]
        or example["manifestSha256"] != acceptance["manifestSha256"]
    ):
        raise ValueError("Installed example did not pass with delivered bytes")
    args.out.mkdir(parents=True, exist_ok=False)
    for source, name in (
        (args.first / "build.json", "build-one.json"),
        (args.second / "build.json", "build-two.json"),
        (args.second / "package/manifest.json", "package-manifest.json"),
        (args.consumer / "results/qualification.json", "qualification.json"),
        (args.consumer / "example-results/qualification.json", "example.json"),
        (args.consumer / "installation.json", "installation.json"),
        (args.consumer / "installation.log", "installation.log"),
    ):
        shutil.copyfile(source, args.out / name)
    evidence = args.out / "evidence.tar.gz"
    with evidence.open("xb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode="w") as tar:
                for directory in ("results", "example-results"):
                    for path in sorted((args.consumer / directory).rglob("*")):
                        if path.is_file():
                            info = tar.gettarinfo(
                                path, path.relative_to(args.consumer).as_posix()
                            )
                            info.uid = info.gid = info.mtime = 0
                            info.uname = info.gname = ""
                            with path.open("rb") as stream:
                                tar.addfile(info, stream)
    archive = args.second / builds[1]["archive"]["path"]
    source_hashes = {
        str(path.relative_to(ROOT)): digest(path)
        for path in sorted(Path(__file__).parent.glob("*.py"))
    }
    record = {
        "schemaVersion": 1,
        "kind": "doe-onnx-vulkan-delivery",
        "version": builds[0]["version"],
        "sourceBaseCommit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "producerSourceHashes": source_hashes,
        "archive": {
            "path": str(archive.resolve().relative_to(ROOT)),
            "sha256": digest(archive),
            "size": archive.stat().st_size,
        },
        "manifestSha256": acceptance["manifestSha256"],
        "reproducible": True,
        "qualificationPassed": True,
        "externalReproduction": False,
        "externalAdoption": False,
        "performanceClaim": False,
        "files": {path.name: digest(path) for path in sorted(args.out.iterdir())},
    }
    write_json(args.out / "delivery.json", record)
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Deterministic archives and verified, relocatable ONNX evaluation installs."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import tarfile
import tempfile
from typing import Any

MANIFEST = "manifest.json"


def digest(path: Path) -> str:
    """Hash file bytes without loading a native library into memory."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, value: Any) -> None:
    """Write canonical JSON with a final newline."""
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def member_path(root: Path, name: str) -> Path:
    """Admit only canonical relative member paths without symlinks."""
    relative = PurePosixPath(name)
    if (
        not name
        or relative.is_absolute()
        or ".." in relative.parts
        or str(relative) != name
        or "\\" in name
        or name == "."
    ):
        raise ValueError(f"Invalid package member: {name!r}")
    target = root / name
    for parent in [target, *target.parents]:
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError(f"Symlink in package member: {name}")
    return target


def inventory(root: Path) -> dict[str, dict[str, Any]]:
    """Bind every regular member, including its executable permissions."""
    result = {}
    for path in sorted(root.rglob("*")):
        name = path.relative_to(root).as_posix()
        member_path(root, name)
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"Nonregular package member: {name}")
        if name != MANIFEST:
            result[name] = {
                "sha256": digest(path),
                "size": path.stat().st_size,
                "mode": stat.S_IMODE(path.stat().st_mode),
            }
    return result


def verify(root: Path) -> dict[str, Any]:
    """Reject missing, changed, additional, and redirected package members."""
    root = root.resolve()
    manifest = json.loads(member_path(root, MANIFEST).read_text("utf-8"))
    if manifest.get("schemaVersion") != 1:
        raise ValueError("Unsupported evaluation manifest version")
    if manifest.get("kind") != "doe-onnx-vulkan-evaluation":
        raise ValueError("Not a Doe ONNX Vulkan evaluation package")
    if manifest["files"] != inventory(root):
        raise ValueError("Package inventory mismatch; reinstall verified archive")
    plan = json.loads((root / "release-inputs.json").read_text("utf-8"))
    for field in ("version", "target", "qualification", "compatibility"):
        if manifest[field] != plan[field]:
            raise ValueError(f"Manifest differs from frozen input plan: {field}")
    expected = set(plan["inputs"]) | set(plan["ownedFiles"]) | {"release-inputs.json"}
    if set(manifest["files"]) != expected:
        raise ValueError("Manifest member set differs from frozen input plan")
    for name, source in plan["inputs"].items():
        for field in ("sha256", "mode"):
            if manifest["files"][name][field] != source[field]:
                raise ValueError(f"Pinned member changed: {name}")
    return manifest


def archive(root: Path, output: Path) -> None:
    """Emit identical gzip/tar bytes for identical input files and modes."""
    verify(root)
    with output.open("xb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode="w") as tar:
                for path in sorted(root.rglob("*")):
                    if not path.is_file():
                        continue
                    info = tar.gettarinfo(path, path.relative_to(root).as_posix())
                    info.uid = info.gid = info.mtime = 0
                    info.uname = info.gname = ""
                    info.pax_headers = {}
                    with path.open("rb") as stream:
                        tar.addfile(info, stream)


def install(archive_path: Path, expected: str, prefix: Path) -> None:
    """Verify and atomically install into a new version-specific directory."""
    if digest(archive_path) != expected:
        raise ValueError("Archive SHA-256 mismatch")
    prefix = prefix.absolute()
    if prefix.exists() or prefix.is_symlink():
        raise FileExistsError(f"Install prefix already exists: {prefix}")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".doe-install-", dir=prefix.parent) as temp:
        staging = Path(temp) / "package"
        staging.mkdir()
        seen = set()
        with tarfile.open(archive_path, "r:gz") as tar:
            for item in tar:
                target = member_path(staging, item.name)
                if item.name in seen or not item.isfile():
                    raise ValueError(
                        f"Invalid or duplicate archive member: {item.name}"
                    )
                if item.mode not in (0o644, 0o755):
                    raise ValueError(f"Invalid archive permissions: {item.name}")
                seen.add(item.name)
                target.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(item)
                if source is None:
                    raise ValueError(f"Unreadable archive member: {item.name}")
                with source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
                target.chmod(item.mode)
        verify(staging)
        if prefix.exists():
            raise FileExistsError(f"Install prefix appeared: {prefix}")
        staging.rename(prefix)

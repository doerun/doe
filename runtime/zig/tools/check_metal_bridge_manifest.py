from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = ROOT.parent
MANIFEST_PATH = ROOT / "zig" / "tools" / "bridge_manifests" / "metal_bridge_manifest.json"
DECL_RE = re.compile(r"^pub extern fn ([A-Za-z0-9_]+)\(")


def load_manifest() -> dict:
    with MANIFEST_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def extract_declared_symbols(path: Path) -> list[str]:
    symbols: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = DECL_RE.match(line)
        if match:
            symbols.append(match.group(1))
    return symbols


def main() -> int:
    manifest = load_manifest()
    signature_owner_rel = manifest["signatureOwner"]
    signature_owner = REPO_ROOT / signature_owner_rel
    declared_symbols = extract_declared_symbols(signature_owner)

    errors: list[str] = []
    manifest_symbols: list[str] = []

    for group in manifest.get("groups", []):
        source_file_rel = group["sourceFile"]
        source_file = REPO_ROOT / source_file_rel
        if not source_file.is_file():
            errors.append(f"missing bridge source file: {source_file_rel}")
            continue
        source_text = source_file.read_text(encoding="utf-8")
        for symbol in group.get("symbols", []):
            manifest_symbols.append(symbol)
            if re.search(rf"\b{re.escape(symbol)}\s*\(", source_text) is None:
                errors.append(f"{source_file_rel}: missing symbol implementation for {symbol}")

    declared_set = set(declared_symbols)
    manifest_set = set(manifest_symbols)

    if len(declared_set) != len(declared_symbols):
        errors.append(f"{signature_owner_rel}: duplicate extern symbol declarations detected")
    if len(manifest_set) != len(manifest_symbols):
        errors.append(f"{MANIFEST_PATH.relative_to(REPO_ROOT)}: duplicate manifest symbol entries detected")

    missing_from_manifest = sorted(declared_set - manifest_set)
    extra_in_manifest = sorted(manifest_set - declared_set)
    if missing_from_manifest:
        errors.append(
            f"{MANIFEST_PATH.relative_to(REPO_ROOT)}: symbols missing from manifest: {', '.join(missing_from_manifest)}"
        )
    if extra_in_manifest:
        errors.append(
            f"{MANIFEST_PATH.relative_to(REPO_ROOT)}: symbols not declared in signature owner: {', '.join(extra_in_manifest)}"
        )

    if not errors:
        return 0

    print("metal bridge manifest drift detected:", file=sys.stderr)
    for entry in errors:
        print(entry, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3

import argparse
import io
import json
import re
import subprocess
import tarfile
import urllib.request
from datetime import date
from pathlib import Path


NPM_PACKAGE = "@webgpu/types"
API_REFERENCE_ROOT = "https://gpuweb.github.io/types/"
INTERFACE_REFERENCE_ROOT = f"{API_REFERENCE_ROOT}interfaces"

DICTIONARY_SUFFIXES = (
    "Attachment",
    "Binding",
    "BufferLayout",
    "Component",
    "Configuration",
    "Descriptor",
    "Dict",
    "Entry",
    "Hint",
    "Info",
    "Init",
    "Layout",
    "Out",
    "State",
    "TimestampWrites",
)

CONSTANT_INTERFACES = {
    "GPUBufferUsage",
    "GPUColorWrite",
    "GPUMapMode",
    "GPUShaderStage",
    "GPUTextureUsage",
}


def load_package_metadata() -> dict:
    output = subprocess.check_output(
        ["npm", "view", NPM_PACKAGE, "version", "dist.tarball", "--json"],
        text=True,
    )
    return json.loads(output)


def download_types_file(tarball_url: str) -> str:
    with urllib.request.urlopen(tarball_url) as response:
        payload = response.read()
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        member = archive.getmember("package/dist/index.d.ts")
        extracted = archive.extractfile(member)
        if extracted is None:
            raise RuntimeError("failed to extract package/dist/index.d.ts from @webgpu/types tarball")
        return extracted.read().decode("utf-8")


def interface_kind(name: str) -> str:
    if name.endswith("Mixin"):
        return "mixin"
    if name in CONSTANT_INTERFACES:
        return "constant-interface"
    if name.endswith(DICTIONARY_SUFFIXES):
        return "dictionary"
    return "interface"


def parse_interfaces(types_text: str) -> list[dict]:
    interfaces: dict[str, dict] = {}
    lines = types_text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        start_match = re.match(r"^interface\s+(GPU[A-Za-z0-9_]*)\b", line)
        if not start_match:
            index += 1
            continue
        name = start_match.group(1)
        header = [line]
        while "{" not in header[-1]:
            index += 1
            header.append(lines[index])
        header_text = " ".join(part.strip() for part in header)
        extends: list[str] = []
        extends_match = re.search(r"\bextends\s+(.+?)\s*\{", header_text)
        if extends_match:
            extends = [
                part.strip()
                for part in extends_match.group(1).split(",")
                if part.strip().startswith("GPU")
            ]
        brace_depth = sum(part.count("{") - part.count("}") for part in header)
        body: list[str] = []
        index += 1
        while index < len(lines):
            body.append(lines[index])
            brace_depth += lines[index].count("{") - lines[index].count("}")
            if brace_depth == 0:
                break
            index += 1
        direct_members: list[dict] = []
        for raw_line in body[:-1]:
            if not raw_line.startswith("  ") or raw_line.startswith("    "):
                continue
            line = raw_line.strip()
            if not line or line.startswith("/**") or line.startswith("*") or line.startswith("//"):
                continue
            property_match = re.match(r"^(?:readonly\s+)?([A-Za-z0-9_]+)\??\s*:", line)
            if property_match:
                member_name = property_match.group(1)
                if member_name == "__brand":
                    continue
                entry = {"name": member_name, "memberKind": "property"}
                if entry not in direct_members:
                    direct_members.append(entry)
                continue
            method_match = re.match(r"^([A-Za-z0-9_]+)\??(?:<[^>]*)?\s*\(", line)
            if method_match:
                entry = {"name": method_match.group(1), "memberKind": "method"}
                if entry not in direct_members:
                    direct_members.append(entry)
        entry = interfaces.setdefault(name, {"extends": [], "directMembers": []})
        for inherited in extends:
            if inherited not in entry["extends"]:
                entry["extends"].append(inherited)
        for member in direct_members:
            if member not in entry["directMembers"]:
                entry["directMembers"].append(member)
        index += 1

    resolved_cache: dict[str, list[dict]] = {}

    def effective_members(name: str, stack: set[str] | None = None) -> list[dict]:
        if name in resolved_cache:
            return resolved_cache[name]
        if stack is None:
            stack = set()
        if name in stack:
            return []
        stack.add(name)
        entry = interfaces.get(name, {"extends": [], "directMembers": []})
        merged_members = list(entry["directMembers"])
        for inherited in entry["extends"]:
            for member in effective_members(inherited, stack):
                if member not in merged_members:
                    merged_members.append(member)
        resolved_cache[name] = merged_members
        return merged_members

    entries = []
    for name in sorted(interfaces):
        members = sorted(effective_members(name), key=lambda item: (item["memberKind"], item["name"]))
        entries.append(
            {
                "name": name,
                "interfaceKind": interface_kind(name),
                "specUrl": f"{INTERFACE_REFERENCE_ROOT}/{name}.html",
                "memberCount": len(members),
                "extends": interfaces[name]["extends"],
                "members": members,
            }
        )
    return entries


def parse_string_unions(types_text: str) -> list[dict]:
    pattern = re.compile(
        r"^type\s+(GPU[A-Za-z0-9_]+)\s*=\n([\s\S]*?);\n",
        re.MULTILINE,
    )
    entries = []
    for name, body in pattern.findall(types_text):
        values = re.findall(r'"([^"]+)"', body)
        if not values:
            continue
        entries.append(
            {
                "name": name,
                "unionKind": "string-union",
                "specUrl": API_REFERENCE_ROOT,
                "valueCount": len(values),
                "values": values,
            }
        )
    entries.sort(key=lambda item: item["name"])
    return entries


def build_index() -> dict:
    metadata = load_package_metadata()
    version = metadata["version"]
    tarball_url = metadata["dist.tarball"]
    types_text = download_types_file(tarball_url)
    interfaces = parse_interfaces(types_text)
    string_unions = parse_string_unions(types_text)
    interface_member_count = sum(entry["memberCount"] for entry in interfaces)
    string_union_value_count = sum(entry["valueCount"] for entry in string_unions)
    return {
        "schemaVersion": 1,
        "lastUpdated": date.today().isoformat(),
        "specFamily": "webgpu-api",
        "source": {
            "kind": "npm-package",
            "package": NPM_PACKAGE,
            "version": version,
            "tarballUrl": tarball_url,
            "apiReference": API_REFERENCE_ROOT,
        },
        "notes": [
            "First-pass WebGPU API surface index generated from the official @webgpu/types package.",
            "This file tracks WebGPU API interfaces and string-union spec enums; it does not yet cover WGSL builtins or CTS evidence.",
            "CTS pass/fail evidence belongs in config/webgpu-cts-evidence.json.",
        ],
        "stats": {
            "interfaceCount": len(interfaces),
            "interfaceMemberCount": interface_member_count,
            "stringUnionCount": len(string_unions),
            "stringUnionValueCount": string_union_value_count,
        },
        "interfaces": interfaces,
        "stringUnions": string_unions,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="config/webgpu-spec-index.json",
        help="path to write the generated spec index JSON",
    )
    args = parser.parse_args()
    index = build_index()
    output_path = Path(args.output)
    output_path.write_text(json.dumps(index, indent=2) + "\n")
    print(f"wrote {output_path}")
    print(
        f"interfaces={index['stats']['interfaceCount']} "
        f"members={index['stats']['interfaceMemberCount']} "
        f"string_unions={index['stats']['stringUnionCount']} "
        f"union_values={index['stats']['stringUnionValueCount']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

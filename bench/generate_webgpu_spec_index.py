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
CHECKLIST_BACKENDS = ("metal", "vulkan", "d3d12", "browser")
IMPLEMENTATION_STATUS = (
    "unreviewed",
    "implemented",
    "partial",
    "not_wired",
    "blocked",
    "out_of_scope",
)
CORRECTNESS_STATUS = (
    "unreviewed",
    "unit",
    "integration",
    "cts",
    "governed",
)
PERFORMANCE_STATUS = (
    "unreviewed",
    "diagnostic",
    "comparable",
    "claimable",
    "not_meaningful",
)

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


def default_backend_cell() -> dict:
    return {
        "implementation": {
            "status": "unreviewed",
            "notes": [],
            "sourceRefs": [],
        },
        "correctness": {
            "status": "unreviewed",
            "notes": [],
            "sourceRefs": [],
        },
        "performance": {
            "status": "unreviewed",
            "notes": [],
            "sourceRefs": [],
        },
    }


def default_checklist() -> dict:
    return {
        "metal": default_backend_cell(),
        "vulkan": default_backend_cell(),
        "d3d12": default_backend_cell(),
        "browser": default_backend_cell(),
    }


def normalize_evidence_cell(raw: dict | None, *, vocabulary: tuple[str, ...]) -> dict:
    cell = {
        "status": "unreviewed",
        "notes": [],
        "sourceRefs": [],
    }
    if not isinstance(raw, dict):
        return cell
    status = raw.get("status")
    if status in vocabulary:
        cell["status"] = status
    notes = raw.get("notes")
    if isinstance(notes, list):
        cell["notes"] = [item for item in notes if isinstance(item, str)]
    source_refs = raw.get("sourceRefs")
    if isinstance(source_refs, list):
        cell["sourceRefs"] = [item for item in source_refs if isinstance(item, str)]
    return cell


def normalize_checklist(raw: dict | None) -> dict:
    checklist = default_checklist()
    if not isinstance(raw, dict):
        return checklist
    for backend in CHECKLIST_BACKENDS:
        value = raw.get(backend)
        if isinstance(value, str) and value in IMPLEMENTATION_STATUS:
            # Preserve v2 data shape by migrating the old flat backend status into
            # the new implementation layer.
            checklist[backend]["implementation"]["status"] = value
            notes = raw.get("notes")
            if isinstance(notes, list):
                checklist[backend]["implementation"]["notes"] = [
                    item for item in notes if isinstance(item, str)
                ]
            source_refs = raw.get("sourceRefs")
            if isinstance(source_refs, list):
                checklist[backend]["implementation"]["sourceRefs"] = [
                    item for item in source_refs if isinstance(item, str)
                ]
            continue
        if isinstance(value, dict):
            checklist[backend] = {
                "implementation": normalize_evidence_cell(
                    value.get("implementation"),
                    vocabulary=IMPLEMENTATION_STATUS,
                ),
                "correctness": normalize_evidence_cell(
                    value.get("correctness"),
                    vocabulary=CORRECTNESS_STATUS,
                ),
                "performance": normalize_evidence_cell(
                    value.get("performance"),
                    vocabulary=PERFORMANCE_STATUS,
                ),
            }
    return checklist


def load_existing_index(output_path: Path) -> dict | None:
    if not output_path.exists():
        return None
    try:
        return json.loads(output_path.read_text())
    except json.JSONDecodeError:
        return None


def build_existing_checklists(existing_index: dict | None) -> tuple[dict[str, dict], dict[str, dict], dict[str, dict], dict[str, dict]]:
    interface_checklists: dict[str, dict] = {}
    member_checklists: dict[str, dict] = {}
    string_union_checklists: dict[str, dict] = {}
    string_union_value_checklists: dict[str, dict] = {}
    if not isinstance(existing_index, dict):
        return interface_checklists, member_checklists, string_union_checklists, string_union_value_checklists

    for interface in existing_index.get("interfaces", []):
        if not isinstance(interface, dict):
            continue
        interface_name = interface.get("name")
        if isinstance(interface_name, str):
            interface_checklists[interface_name] = normalize_checklist(interface.get("checklist"))
        for member in interface.get("members", []):
            if not isinstance(member, dict):
                continue
            member_name = member.get("name")
            member_kind = member.get("memberKind")
            if isinstance(interface_name, str) and isinstance(member_name, str) and isinstance(member_kind, str):
                member_checklists[f"{interface_name}::{member_kind}::{member_name}"] = normalize_checklist(member.get("checklist"))

    for string_union in existing_index.get("stringUnions", []):
        if not isinstance(string_union, dict):
            continue
        union_name = string_union.get("name")
        if isinstance(union_name, str):
            string_union_checklists[union_name] = normalize_checklist(string_union.get("checklist"))
        for value in string_union.get("values", []):
            if isinstance(value, dict):
                value_name = value.get("name")
                if isinstance(union_name, str) and isinstance(value_name, str):
                    string_union_value_checklists[f"{union_name}::{value_name}"] = normalize_checklist(value.get("checklist"))

    return (
        interface_checklists,
        member_checklists,
        string_union_checklists,
        string_union_value_checklists,
    )


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


def parse_interfaces(types_text: str, existing_index: dict | None = None) -> list[dict]:
    interface_checklists, member_checklists, _, _ = build_existing_checklists(existing_index)
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
                entry = {
                    "name": member_name,
                    "memberKind": "property",
                    "checklist": member_checklists.get(
                        f"{name}::property::{member_name}",
                        default_checklist(),
                    ),
                }
                if entry not in direct_members:
                    direct_members.append(entry)
                continue
            method_match = re.match(r"^([A-Za-z0-9_]+)\??(?:<[^>]*)?\s*\(", line)
            if method_match:
                method_name = method_match.group(1)
                entry = {
                    "name": method_name,
                    "memberKind": "method",
                    "checklist": member_checklists.get(
                        f"{name}::method::{method_name}",
                        default_checklist(),
                    ),
                }
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
                "checklist": interface_checklists.get(name, default_checklist()),
                "members": members,
            }
        )
    return entries


def parse_string_unions(types_text: str, existing_index: dict | None = None) -> list[dict]:
    _, _, string_union_checklists, string_union_value_checklists = build_existing_checklists(existing_index)
    pattern = re.compile(
        r"^type\s+(GPU[A-Za-z0-9_]+)\s*=\n([\s\S]*?);\n",
        re.MULTILINE,
    )
    entries = []
    for name, body in pattern.findall(types_text):
        values = re.findall(r'"([^"]+)"', body)
        if not values:
            continue
        value_entries = [
            {
                "name": value,
                "checklist": string_union_value_checklists.get(
                    f"{name}::{value}",
                    default_checklist(),
                ),
            }
            for value in values
        ]
        entries.append(
            {
                "name": name,
                "unionKind": "string-union",
                "specUrl": API_REFERENCE_ROOT,
                "valueCount": len(values),
                "checklist": string_union_checklists.get(name, default_checklist()),
                "values": value_entries,
            }
        )
    entries.sort(key=lambda item: item["name"])
    return entries


def build_index(output_path: Path) -> dict:
    metadata = load_package_metadata()
    version = metadata["version"]
    tarball_url = metadata["dist.tarball"]
    types_text = download_types_file(tarball_url)
    existing_index = load_existing_index(output_path)
    interfaces = parse_interfaces(types_text, existing_index)
    string_unions = parse_string_unions(types_text, existing_index)
    interface_member_count = sum(entry["memberCount"] for entry in interfaces)
    string_union_value_count = sum(entry["valueCount"] for entry in string_unions)
    return {
        "schemaVersion": 3,
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
            "This file tracks WebGPU API interfaces and string-union spec enums, and now carries per-backend checklist cells for implementation, correctness, and performance review.",
            "Checklist cells default to unreviewed until reviewed statuses and sourceRefs are attached.",
            "CTS pass/fail evidence belongs in config/webgpu-cts-evidence.json.",
        ],
        "checklist": {
            "backends": list(CHECKLIST_BACKENDS),
            "implementationStatusVocabulary": list(IMPLEMENTATION_STATUS),
            "correctnessStatusVocabulary": list(CORRECTNESS_STATUS),
            "performanceStatusVocabulary": list(PERFORMANCE_STATUS),
            "defaultImplementationStatus": "unreviewed",
            "defaultCorrectnessStatus": "unreviewed",
            "defaultPerformanceStatus": "unreviewed",
            "notes": [
                "The checklist is the canonical backend review layer for the WebGPU API spec index.",
                "Keep implementation, correctness, and performance statuses separate for every backend cell.",
                "Use implemented, partial, not_wired, blocked, or out_of_scope only when sourceRefs justify the implementation classification.",
            ],
        },
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
    output_path = Path(args.output)
    index = build_index(output_path)
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

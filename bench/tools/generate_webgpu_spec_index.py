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

DEFAULTS = {"impl": "unreviewed", "correct": "unreviewed", "perf": "unreviewed"}


def compact_cell(verbose_cell):
    """Convert a verbose backend cell to compact form, omitting defaults."""
    result = {}
    s = verbose_cell.get("implementation", {}).get("status", "unreviewed")
    if s != DEFAULTS["impl"]:
        result["impl"] = s
    s = verbose_cell.get("correctness", {}).get("status", "unreviewed")
    if s != DEFAULTS["correct"]:
        result["correct"] = s
    s = verbose_cell.get("performance", {}).get("status", "unreviewed")
    if s != DEFAULTS["perf"]:
        result["perf"] = s
    notes = []
    for dim in ["implementation", "correctness", "performance"]:
        for n in verbose_cell.get(dim, {}).get("notes", []):
            if n and n not in notes:
                notes.append(n)
    if notes:
        result["notes"] = notes
    return result


def compact_checklist(verbose_checklist):
    """Convert verbose checklist dict to flat backend keys, omitting all-default backends."""
    result = {}
    for backend in CHECKLIST_BACKENDS:
        cell = verbose_checklist.get(backend, {})
        cc = compact_cell(cell)
        if cc:
            result[backend] = cc
    return result


def load_existing_jsonl(output_path):
    """Load existing JSONL and build lookup maps for preserving checklist data."""
    if not output_path.exists():
        return {}, {}, {}, {}
    interface_cells = {}
    member_cells = {}
    union_cells = {}
    value_cells = {}
    try:
        with open(output_path) as f:
            for line in f:
                row = json.loads(line)
                kind = row.get("kind")
                if kind == "interface":
                    backends = {b: row[b] for b in CHECKLIST_BACKENDS if b in row}
                    if backends:
                        interface_cells[row["name"]] = backends
                elif kind == "member":
                    backends = {b: row[b] for b in CHECKLIST_BACKENDS if b in row}
                    if backends:
                        member_cells[f"{row['parent']}::{row['memberKind']}::{row['name']}"] = backends
                elif kind == "union":
                    backends = {b: row[b] for b in CHECKLIST_BACKENDS if b in row}
                    if backends:
                        union_cells[row["name"]] = backends
                elif kind == "value":
                    backends = {b: row[b] for b in CHECKLIST_BACKENDS if b in row}
                    if backends:
                        value_cells[f"{row['parent']}::{row['name']}"] = backends
    except (json.JSONDecodeError, KeyError):
        return {}, {}, {}, {}
    return interface_cells, member_cells, union_cells, value_cells


def load_package_metadata():
    output = subprocess.check_output(
        ["npm", "view", NPM_PACKAGE, "version", "dist.tarball", "--json"],
        text=True,
    )
    return json.loads(output)


def download_types_file(tarball_url):
    with urllib.request.urlopen(tarball_url) as response:
        payload = response.read()
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        member = archive.getmember("package/dist/index.d.ts")
        extracted = archive.extractfile(member)
        if extracted is None:
            raise RuntimeError("failed to extract package/dist/index.d.ts from @webgpu/types tarball")
        return extracted.read().decode("utf-8")


def interface_kind(name):
    if name.endswith("Mixin"):
        return "mixin"
    if name in CONSTANT_INTERFACES:
        return "constant-interface"
    if name.endswith(DICTIONARY_SUFFIXES):
        return "dictionary"
    return "interface"


def parse_interfaces(types_text, existing_members, existing_interfaces):
    interfaces = {}
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
        extends = []
        extends_match = re.search(r"\bextends\s+(.+?)\s*\{", header_text)
        if extends_match:
            extends = [
                part.strip()
                for part in extends_match.group(1).split(",")
                if part.strip().startswith("GPU")
            ]
        brace_depth = sum(part.count("{") - part.count("}") for part in header)
        body = []
        index += 1
        while index < len(lines):
            body.append(lines[index])
            brace_depth += lines[index].count("{") - lines[index].count("}")
            if brace_depth == 0:
                break
            index += 1
        direct_members = []
        for raw_line in body[:-1]:
            if not raw_line.startswith("  ") or raw_line.startswith("    "):
                continue
            mline = raw_line.strip()
            if not mline or mline.startswith("/**") or mline.startswith("*") or mline.startswith("//"):
                continue
            property_match = re.match(r"^(?:readonly\s+)?([A-Za-z0-9_]+)\??\s*:", mline)
            if property_match:
                member_name = property_match.group(1)
                if member_name == "__brand":
                    continue
                entry = {"name": member_name, "memberKind": "property"}
                if entry not in direct_members:
                    direct_members.append(entry)
                continue
            method_match = re.match(r"^([A-Za-z0-9_]+)\??(?:<[^>]*)?\s*\(", mline)
            if method_match:
                method_name = method_match.group(1)
                entry = {"name": method_name, "memberKind": "method"}
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

    resolved_cache = {}

    def effective_members(name, stack=None):
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

    results = []
    for name in sorted(interfaces):
        members = sorted(effective_members(name), key=lambda item: (item["memberKind"], item["name"]))
        iface_row = {
            "kind": "interface",
            "name": name,
            "interfaceKind": interface_kind(name),
            "specUrl": f"{INTERFACE_REFERENCE_ROOT}/{name}.html",
            "memberCount": len(members),
        }
        if interfaces[name]["extends"]:
            iface_row["extends"] = interfaces[name]["extends"]
        # Preserve existing checklist data
        existing = existing_interfaces.get(name, {})
        for backend in CHECKLIST_BACKENDS:
            if backend in existing:
                iface_row[backend] = existing[backend]

        member_rows = []
        for m in members:
            mrow = {
                "kind": "member",
                "parent": name,
                "name": m["name"],
                "memberKind": m["memberKind"],
            }
            key = f"{name}::{m['memberKind']}::{m['name']}"
            existing_m = existing_members.get(key, {})
            for backend in CHECKLIST_BACKENDS:
                if backend in existing_m:
                    mrow[backend] = existing_m[backend]
            member_rows.append(mrow)

        results.append((iface_row, member_rows))

    return results


def parse_string_unions(types_text, existing_unions, existing_values):
    pattern = re.compile(
        r"^type\s+(GPU[A-Za-z0-9_]+)\s*=\n([\s\S]*?);\n",
        re.MULTILINE,
    )
    results = []
    for name, body in pattern.findall(types_text):
        values = re.findall(r'"([^"]+)"', body)
        if not values:
            continue
        union_row = {
            "kind": "union",
            "name": name,
            "specUrl": API_REFERENCE_ROOT,
            "valueCount": len(values),
        }
        existing_u = existing_unions.get(name, {})
        for backend in CHECKLIST_BACKENDS:
            if backend in existing_u:
                union_row[backend] = existing_u[backend]

        value_rows = []
        for value in values:
            vrow = {
                "kind": "value",
                "parent": name,
                "name": value,
            }
            key = f"{name}::{value}"
            existing_v = existing_values.get(key, {})
            for backend in CHECKLIST_BACKENDS:
                if backend in existing_v:
                    vrow[backend] = existing_v[backend]
            value_rows.append(vrow)

        results.append((union_row, value_rows))

    results.sort(key=lambda item: item[0]["name"])
    return results


def build_index(output_path):
    metadata = load_package_metadata()
    version = metadata["version"]
    tarball_url = metadata["dist.tarball"]
    types_text = download_types_file(tarball_url)

    existing_interfaces, existing_members, existing_unions, existing_values = load_existing_jsonl(output_path)

    interfaces = parse_interfaces(types_text, existing_members, existing_interfaces)
    string_unions = parse_string_unions(types_text, existing_unions, existing_values)

    interface_count = len(interfaces)
    member_count = sum(len(members) for _, members in interfaces)
    union_count = len(string_unions)
    value_count = sum(len(values) for _, values in string_unions)

    header = {
        "kind": "header",
        "schemaVersion": 4,
        "lastUpdated": date.today().isoformat(),
        "specFamily": "webgpu-api",
        "source": {
            "kind": "npm-package",
            "package": NPM_PACKAGE,
            "version": version,
            "tarballUrl": tarball_url,
            "apiReference": API_REFERENCE_ROOT,
        },
        "backends": list(CHECKLIST_BACKENDS),
        "defaults": DEFAULTS,
        "implVocab": list(IMPLEMENTATION_STATUS),
        "correctVocab": list(CORRECTNESS_STATUS),
        "perfVocab": list(PERFORMANCE_STATUS),
        "stats": {
            "interfaceCount": interface_count,
            "interfaceMemberCount": member_count,
            "stringUnionCount": union_count,
            "stringUnionValueCount": value_count,
        },
    }

    rows = [header]
    for iface_row, member_rows in interfaces:
        rows.append(iface_row)
        rows.extend(member_rows)
    for union_row, value_rows in string_unions:
        rows.append(union_row)
        rows.extend(value_rows)

    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="config/webgpu-spec-index.jsonl",
        help="path to write the generated spec index JSONL",
    )
    args = parser.parse_args()
    output_path = Path(args.output)
    rows = build_index(output_path)
    with open(output_path, "w") as f:
        for row in rows:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
    header = rows[0]
    stats = header["stats"]
    print(f"wrote {output_path}")
    print(
        f"interfaces={stats['interfaceCount']} "
        f"members={stats['interfaceMemberCount']} "
        f"string_unions={stats['stringUnionCount']} "
        f"union_values={stats['stringUnionValueCount']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

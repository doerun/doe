"""Resolve CPU PCs using ELF load segments and retain diagnostic uncertainty."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import statistics
import struct
import subprocess

from probe import identity


def executable_segments(path: Path) -> list[tuple[int, int, int]]:
    """Return file offset, virtual address, and file size of executable PT_LOADs."""
    with path.open("rb") as stream:
        header = stream.read(64)
        if header[:6] != b"\x7fELF\x02\x01":
            raise ValueError("Expected little-endian ELF64: " + str(path))
        offset = struct.unpack_from("<Q", header, 32)[0]
        size, count = struct.unpack_from("<HH", header, 54)
        stream.seek(offset)
        entries = [stream.read(size) for _ in range(count)]
    return [
        (offset, address, length)
        for entry in entries
        for kind, flags, offset, address, _, length, _, _ in [
            struct.unpack("<IIQQQQQQ", entry)
        ]
        if kind == 1 and flags & 1
    ]


def resolve_mapping(
    start: int, offset: int, path: Path, page_size: int | None = None
) -> int:
    """Return load bias; ELF virtual addresses need not equal their file offsets."""
    if page_size is None:
        page_size = os.sysconf("SC_PAGE_SIZE")
    for file_offset, address, length in executable_segments(path):
        file_page = file_offset // page_size * page_size
        if file_page <= offset < file_offset + length:
            return start - (address - file_offset + offset)
    raise ValueError("Executable mapping has no ELF segment: " + str(path))


def profile(directory: Path) -> dict:
    """Aggregate instruction locations, never infer an unavailable call stack."""
    receipt = json.loads((directory / "run.json").read_text())
    if receipt["exitCode"]:
        raise ValueError("Failed application")
    content = (directory / "application.log").read_text()
    if "CampaignCleanupFailure" in content:
        raise ValueError("Failed cleanup")
    observations = [
        line.split() for line in (directory / "observations").read_text().splitlines()
    ]
    if len(observations) != receipt["runs"]:
        raise ValueError("Incomplete invocation population")
    result = {
        "schemaVersion": 1,
        "classification": "diagnostic-cpu-profile",
        "run": identity(directory / "run.json"),
        "medianWallNs": statistics.median(int(row[1]) for row in observations),
        "medianCpuNs": statistics.median(float(row[2]) for row in observations),
        "summary": None,
        "samples": 0,
        "overruns": 0,
        "unmappedSamples": 0,
        "threadIds": [],
        "modules": [],
        "locations": [],
        "procs": [],
    }
    summaries = [
        line.split()[1:]
        for line in content.splitlines()
        if line.startswith("CpuProbeSummary ")
    ]
    if summaries:
        runs, thread, process, dropped = map(int, summaries[0])
        if runs != receipt["runs"] or dropped:
            raise ValueError("Lost CPU observations")
        result["summary"] = {
            "runs": runs,
            "threadCpuNs": thread,
            "processCpuNs": process,
            "mainThreadCpuShare": thread / process,
            "dropped": dropped,
        }
    for line in content.splitlines():
        if line.startswith("CpuProbeProc "):
            index, count, inclusive, exclusive = map(int, line.split()[1:])
            result["procs"].append(
                {
                    "index": index,
                    "count": count,
                    "inclusiveCpuNs": inclusive,
                    "exclusiveCpuNs": exclusive,
                }
            )
    if not receipt["samples"]:
        return result
    data = (directory / "samples.bin").read_bytes()
    record_bytes = receipt.get("sampleRecordBytes", 32)
    if record_bytes not in [32, 128] or len(data) % record_bytes:
        raise ValueError("Truncated CPU sample record")
    records = list(struct.iter_unpack("<" + "Q" * (record_bytes // 8), data))
    result["samples"] = len(records)
    result["overruns"] = sum(row[2] for row in records)
    result["threadIds"] = sorted({row[1] for row in records})
    site_counts = Counter(row[3] for row in records)
    qualification = json.loads(Path(receipt["qualification"]["path"]).read_text())
    names = json.loads(
        (
            Path(qualification["inputs"]["bridge"]["path"]).parent / "build.json"
        ).read_text()
    )["procNames"]
    result["sites"] = [
        {
            "name": names[index] if index < len(names) else "outside-bridge",
            "index": index,
            "samples": count,
        }
        for index, count in site_counts.most_common()
    ]
    mappings = []
    for line in (directory / "maps").read_text().splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) != 6 or "x" not in fields[1] or not Path(fields[5]).is_file():
            continue
        start, end = [int(value, 16) for value in fields[0].split("-")]
        path = Path(fields[5])
        bias = resolve_mapping(start, int(fields[2], 16), path)
        mappings.append((start, end, bias, path))
    addresses: dict[Path, Counter] = defaultdict(Counter)
    callers = defaultdict(Counter)
    for row in records:
        if record_bytes == 128 and row[4] > 8:
            raise ValueError("Invalid frame candidate count")
        pc, tid, overrun, site = row[:4]
        for start, end, bias, path in mappings:
            if start <= pc < end:
                addresses[path][pc - bias] += 1
                if record_bytes == 128:
                    for index in range(row[4]):
                        caller = row[5 + index]
                        for a, b, load_bias, library in mappings:
                            if a <= caller - 1 < b:
                                callers[(library, caller - 1 - load_bias)][
                                    (path, pc - bias)
                                ] += 1
                                break
                break
        else:
            result["unmappedSamples"] += 1
    for path, counts in addresses.items():
        result["modules"].append(
            {"library": identity(path), "samples": sum(counts.values())}
        )
        pcs = sorted(counts)
        decoded = subprocess.run(
            ["addr2line", "-a", "-i", "-f", "-C", "-e", str(path)],
            input="\n".join(hex(pc) for pc in pcs) + "\n",
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        frames = {}
        current = None
        for line in decoded:
            if line.startswith("0x"):
                current = int(line, 16)
                frames[current] = []
            elif current is not None:
                frames[current].append(line)
            else:
                raise ValueError("Unexpected symbolizer output")
        if sorted(frames) != pcs or any(len(lines) % 2 for lines in frames.values()):
            raise ValueError("Incomplete symbolizer output")
        for index, pc in enumerate(pcs):
            stack = frames[pc]
            result["locations"].append(
                {
                    "libraryPath": str(path),
                    "address": hex(pc),
                    "function": stack[0],
                    "source": stack[1],
                    "inlineFrames": [
                        {"function": stack[i], "source": stack[i + 1]}
                        for i in range(0, len(stack), 2)
                    ],
                    "samples": counts[pc],
                }
            )
    result["locations"].sort(key=lambda item: item["samples"], reverse=True)
    result["modules"].sort(key=lambda item: item["samples"], reverse=True)
    result["frameCandidates"] = []
    for (path, caller), leaves in callers.items():
        decoded = subprocess.run(
            ["addr2line", "-f", "-C", "-e", str(path), hex(caller)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        result["frameCandidates"].append(
            {
                "libraryPath": str(path),
                "address": hex(caller),
                "function": decoded[0],
                "source": decoded[1],
                "samples": sum(leaves.values()),
                "leaves": [
                    {"libraryPath": str(p), "address": hex(pc), "samples": count}
                    for (p, pc), count in leaves.items()
                ],
            }
        )
    result["frameCandidates"].sort(key=lambda item: item["samples"], reverse=True)
    result["mappingLoads"] = [
        {
            "start": start,
            "end": end,
            "loadBias": bias,
            "library": identity(path),
            "segments": [
                {"offset": offset, "virtualAddress": address, "fileBytes": size}
                for offset, address, size in executable_segments(path)
            ],
        }
        for start, end, bias, path in mappings
    ]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run", type=Path, required=True, help="Diagnostic run directory"
    )
    parser.add_argument("--out", type=Path, required=True, help="New resolved profile")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Profile must be new")
    args.out.write_text(json.dumps(profile(args.run), indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

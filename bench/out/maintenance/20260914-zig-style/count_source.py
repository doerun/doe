"""Inventory tracked Zig text, separating active code from retained snapshots."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import subprocess


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("before", "after"))
    args = parser.parse_args()
    output = Path(__file__).resolve().parent
    repo = output.parents[3]
    manifest = json.loads(
        (repo / "runtime/zig/source-layout.json").read_text(encoding="utf-8")
    )
    generated = {
        "runtime/zig/" + path
        for path in manifest["architecture"]["generatedSourceContracts"]
    }
    tracked = subprocess.check_output(
        ["git", "ls-files", "-z", "--", "*.zig"], cwd=repo
    ).decode().split("\0")
    # Only build.zig changed between these inventories. Assert that assumption
    # before reconstructing its predecessor without checking out old sources.
    changed = subprocess.check_output(
        ["git", "diff", "ded78ed29", "--name-only", "--", "*.zig"], cwd=repo,
        text=True,
    ).splitlines()
    if set(changed) - {"runtime/zig/build.zig"}:
        raise ValueError(f"unexpected changed Zig sources: {changed}")
    groups: dict[str, list[int]] = defaultdict(lambda: [0] * 5)
    rows = ["path\tcategory\tphysical\tblank\tcomment_only\tcode\tsha256"]
    for name in sorted(filter(None, tracked)):
        data = (repo / name).read_bytes()
        if args.phase == "before" and name == "runtime/zig/build.zig":
            data = subprocess.check_output(
                ["git", "show", "ded78ed29:" + name], cwd=repo
            )
        lines = data.splitlines()
        physical = len(lines)
        blank = sum(not line.strip() for line in lines)
        comments = sum(line.lstrip().startswith(b"//") for line in lines)
        code = physical - blank - comments
        if name.startswith("bench/out/"):
            category = "retained_snapshots"
        elif name in generated:
            category = "production_generated"
        elif name.startswith("runtime/zig/src/"):
            category = "production_handwritten"
        elif name.startswith("runtime/zig/tests/"):
            category = "tests"
        elif name.startswith("runtime/zig/test_suite"):
            category = "generated_test_roots"
        elif name.startswith("runtime/zig/"):
            category = "build_bench_tools"
        else:
            raise ValueError(f"unclassified source: {name}")
        values = [1, physical, blank, comments, code]
        for group in (category, "repository_total"):
            groups[group] = [a + b for a, b in zip(groups[group], values)]
        if name.startswith("runtime/zig/"):
            groups["active_total"] = [
                a + b for a, b in zip(groups["active_total"], values)
            ]
        digest = hashlib.sha256(data).hexdigest()
        rows.append(f"{name}\t{category}\t{physical}\t{blank}\t{comments}\t{code}\t{digest}")
    summary = ["category\tfiles\tphysical\tblank\tcomment_only\tcode"]
    for group, values in sorted(groups.items()):
        summary.append(group + "\t" + "\t".join(map(str, values)))
    (output / f"{args.phase}-files.tsv").write_text(
        "\n".join(rows) + "\n", encoding="utf-8"
    )
    (output / f"{args.phase}-counts.tsv").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
    )
    print("\n".join(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

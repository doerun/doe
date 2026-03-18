#!/usr/bin/env python3
"""Promote Metal interface-level status based on member implementation coverage.

If all members of an interface are 'implemented', promote the interface to 'implemented'.
If some members are 'implemented' and none are 'unreviewed', promote to 'partial'.
If some members are 'implemented' but some are still 'unreviewed', promote to 'partial'.
"""

import json

SPEC_INDEX_PATH = "config/webgpu-spec-index.jsonl"


def main():
    with open(SPEC_INDEX_PATH) as f:
        rows = [json.loads(line) for line in f]

    # Group members by parent interface
    members_by_parent = {}
    for row in rows:
        if row.get("kind") == "member":
            members_by_parent.setdefault(row["parent"], []).append(row)

    promoted = 0
    for row in rows:
        if row.get("kind") != "interface":
            continue

        name = row["name"]
        metal = row.get("metal", {})
        iface_status = metal.get("impl", "unreviewed")
        if iface_status == "implemented":
            continue

        members = members_by_parent.get(name, [])
        if not members:
            continue

        member_statuses = [
            m.get("metal", {}).get("impl", "unreviewed") for m in members
        ]
        implemented_count = member_statuses.count("implemented")
        total = len(member_statuses)

        if implemented_count == 0:
            continue

        if implemented_count == total:
            new_status = "implemented"
        elif implemented_count > 0:
            new_status = "partial"
        else:
            continue

        if iface_status != new_status:
            metal = row.setdefault("metal", {})
            metal["impl"] = new_status
            metal["notes"] = [f"Auto-promoted: {implemented_count}/{total} members implemented."]
            promoted += 1
            print(f"  {name}: {iface_status} -> {new_status} ({implemented_count}/{total} members)")

    # Update header timestamp
    for row in rows:
        if row.get("kind") == "header":
            row["lastUpdated"] = "2026-03-17"
            break

    with open(SPEC_INDEX_PATH, "w") as f:
        for row in rows:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")

    print(f"\n{promoted} Metal interface(s) promoted.")


if __name__ == "__main__":
    main()

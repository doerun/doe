#!/usr/bin/env python3
"""Promote Metal interface-level status based on member implementation coverage.

If all members of an interface are 'implemented', promote the interface to 'implemented'.
If some members are 'implemented' and none are 'unreviewed', promote to 'partial'.
If some members are 'implemented' but some are still 'unreviewed', promote to 'partial'.
"""

import json

SPEC_INDEX_PATH = "config/webgpu-spec-index.json"


def main():
    with open(SPEC_INDEX_PATH, "r") as f:
        data = json.load(f)

    promoted = 0
    for iface in data.get("interfaces", []):
        metal = iface.get("checklist", {}).get("metal")
        if not metal:
            continue

        iface_status = metal.get("implementation", {}).get("status")
        if iface_status == "implemented":
            continue  # already done

        members = iface.get("members", [])
        if not members:
            continue

        member_statuses = []
        for member in members:
            mm = member.get("checklist", {}).get("metal", {})
            ms = mm.get("implementation", {}).get("status", "missing")
            member_statuses.append(ms)

        if not member_statuses:
            continue

        implemented_count = member_statuses.count("implemented")
        total = len(member_statuses)

        if implemented_count == 0:
            continue

        # All members implemented → interface implemented
        # Mix of implemented + (partial|not_wired|out_of_scope|blocked) → partial
        non_implemented = [s for s in member_statuses if s != "implemented"]
        all_accounted = all(s in ("implemented", "partial", "not_wired", "out_of_scope", "blocked") for s in member_statuses)

        if implemented_count == total:
            new_status = "implemented"
        elif all_accounted and implemented_count > 0:
            new_status = "partial"
        elif implemented_count > 0:
            new_status = "partial"
        else:
            continue

        if iface_status != new_status:
            metal["implementation"]["status"] = new_status
            if "notes" not in metal["implementation"]:
                metal["implementation"]["notes"] = []
            metal["implementation"]["notes"] = [
                f"Auto-promoted: {implemented_count}/{total} members implemented."
            ]
            promoted += 1
            print(f"  {iface['name']}: {iface_status} → {new_status} ({implemented_count}/{total} members)")

    data["lastUpdated"] = "2026-03-17"

    with open(SPEC_INDEX_PATH, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    print(f"\n{promoted} Metal interface(s) promoted.")


if __name__ == "__main__":
    main()

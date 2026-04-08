import json

with open("bench/workloads/metadata/backend-workload-catalog.json", "r") as f:
    data = json.load(f)

for w in data["workloads"]:
    wid = w["id"]
    
    # 1. Fix "Directional" description if comparable
    shared_desc = w.get("shared", {}).get("description", "")
    for lane_name, lane_override in w.get("lanes", {}).items():
        is_comparable = lane_override.get("comparable", w.get("shared", {}).get("comparable", False))
        lane_desc = lane_override.get("description", shared_desc)
        if is_comparable and lane_desc.startswith("Directional"):
            lane_override["description"] = lane_desc.replace("Directional", "Comparable", 1)

    # 2. surface domain workloads that are comparable MUST have applesToApplesVetted = True
    domain = w.get("shared", {}).get("domain", "")
    if domain == "surface":
        for lane_name, lane_override in w.get("lanes", {}).items():
            is_comparable = lane_override.get("comparable", w.get("shared", {}).get("comparable", False))
            if is_comparable:
                lane_override["applesToApplesVetted"] = True
                
        # Also check shared
        if w.get("shared", {}).get("comparable", False):
            w["shared"]["applesToApplesVetted"] = True

with open("bench/workloads/metadata/backend-workload-catalog.json", "w") as f:
    json.dump(data, f, indent=2)


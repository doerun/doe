import json

with open("bench/workloads/metadata/backend-workload-catalog.json", "r") as f:
    data = json.load(f)

for w in data["workloads"]:
    shared_desc = w.get("shared", {}).get("description", "")
    for lane_name, lane_override in w.get("lanes", {}).items():
        is_comparable = lane_override.get("comparable", w.get("shared", {}).get("comparable", False))
        lane_desc = lane_override.get("description", shared_desc)
        if is_comparable and lane_desc.startswith("Directional"):
            new_desc = lane_desc.replace("Directional", "Comparable", 1)
            lane_override["description"] = new_desc

with open("bench/workloads/metadata/backend-workload-catalog.json", "w") as f:
    json.dump(data, f, indent=2)


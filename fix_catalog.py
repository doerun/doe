import json

with open("bench/workloads/metadata/backend-workload-catalog.json", "r") as f:
    data = json.load(f)

for w in data["workloads"]:
    wid = w["id"]
    
    # 1. copy_texture_to_texture: missing fieldOrder keys
    if wid == "copy_texture_to_texture":
        idx = w["fieldOrder"].index("baselineTimingDivisor")
        w["fieldOrder"].insert(idx + 1, "comparisonTimingDivisor")
        w["fieldOrder"].insert(idx + 1, "comparisonCommandRepeat")
            
    # 2. compute_dispatch_fallback / compute_dispatch_grid / etc: Fix "Directional" description if comparable
    shared_desc = w.get("shared", {}).get("description", "")
    for lane_name, lane_override in w.get("lanes", {}).items():
        is_comparable = lane_override.get("comparable", w.get("shared", {}).get("comparable", False))
        lane_desc = lane_override.get("description", shared_desc)
        if is_comparable and lane_desc.startswith("Directional"):
            lane_override["description"] = lane_desc.replace("Directional", "Comparable", 1)

    # 3. surface_full_presentation: must be applesToApplesVetted since it is comparable
    if wid == "surface_full_presentation":
        w["shared"]["applesToApplesVetted"] = True
        
    # 4. surface_presentation: must be applesToApplesVetted since it is comparable in amd_vulkan_superset
    if wid == "surface_presentation":
        if "amd_vulkan_superset" in w["lanes"]:
            w["lanes"]["amd_vulkan_superset"]["applesToApplesVetted"] = True

with open("bench/workloads/metadata/backend-workload-catalog.json", "w") as f:
    json.dump(data, f, indent=2)

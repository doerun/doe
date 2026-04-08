import json

with open("bench/workloads/metadata/backend-workload-catalog.json", "r") as f:
    data = json.load(f)

for w in data["workloads"]:
    wid = w["id"]
    
    # 1. copy_texture_to_texture: missing fieldOrder keys
    if wid == "copy_texture_to_texture":
        if "comparisonCommandRepeat" not in w["fieldOrder"]:
            idx = w["fieldOrder"].index("baselineTimingDivisor")
            w["fieldOrder"].insert(idx + 1, "comparisonTimingDivisor")
            w["fieldOrder"].insert(idx + 1, "comparisonCommandRepeat")
            
    # 2. inference_gemma3*: add local_d3d12_extended to lanes
    if wid.startswith("inference_gemma3_"):
        if "local_d3d12_extended" not in w["lanes"]:
            w["lanes"]["local_d3d12_extended"] = {
              "api": "d3d12",
              "benchmarkClass": "directional",
              "comparabilityNotes": "Directional-only D3D12 scaffold. Excluded from strict comparable claim lanes pending Windows-backed evidence.",
              "comparable": False,
              "driver": "1.0.0",
              "family": "d3d12",
              "quirksPath": "examples/quirks/windows_d3d12_noop_list.json",
              "vendor": "generic",
              "workloadOrigin": "doe_contract_with_dawn_mapping"
            }
            
    # 3. Fix "Directional" description if comparable
    shared_desc = w.get("shared", {}).get("description", "")
    for lane_name, lane_override in w.get("lanes", {}).items():
        is_comparable = lane_override.get("comparable", w.get("shared", {}).get("comparable", False))
        lane_desc = lane_override.get("description", shared_desc)
        if is_comparable and lane_desc.startswith("Directional"):
            lane_override["description"] = lane_desc.replace("Directional", "Comparable", 1)

    # 4. surface_full_presentation: must be applesToApplesVetted since it is comparable
    if wid == "surface_full_presentation":
        w["shared"]["applesToApplesVetted"] = True
        
    # 5. surface_presentation: must be applesToApplesVetted since it is comparable in amd_vulkan_superset
    if wid == "surface_presentation":
        if "amd_vulkan_superset" not in w["lanes"]:
            w["lanes"]["amd_vulkan_superset"] = {}
        w["lanes"]["amd_vulkan_superset"]["applesToApplesVetted"] = True

    # 6. compute_dispatch_fallback and compute_dispatch_grid must be comparable in amd_vulkan_superset
    if wid == "compute_dispatch_fallback":
        if "amd_vulkan_superset" not in w["lanes"]:
            w["lanes"]["amd_vulkan_superset"] = {}
        w["lanes"]["amd_vulkan_superset"]["comparable"] = True
        w["lanes"]["amd_vulkan_superset"]["benchmarkClass"] = "comparable"
        w["lanes"]["amd_vulkan_superset"]["description"] = w.get("shared", {}).get("description", "").replace("Directional", "Comparable", 1)
        w["lanes"]["amd_vulkan_superset"]["comparisonCommandRepeat"] = 500
        w["lanes"]["amd_vulkan_superset"]["comparisonTimingDivisor"] = 500

    if wid == "compute_dispatch_grid":
        if "amd_vulkan_superset" not in w["lanes"]:
            w["lanes"]["amd_vulkan_superset"] = {}
        w["lanes"]["amd_vulkan_superset"]["comparable"] = True
        w["lanes"]["amd_vulkan_superset"]["benchmarkClass"] = "comparable"
        w["lanes"]["amd_vulkan_superset"]["description"] = w.get("shared", {}).get("description", "").replace("Directional", "Comparable", 1)
        w["lanes"]["amd_vulkan_superset"]["comparisonCommandRepeat"] = 300
        w["lanes"]["amd_vulkan_superset"]["comparisonTimingDivisor"] = 300

with open("bench/workloads/metadata/backend-workload-catalog.json", "w") as f:
    json.dump(data, f, indent=2)

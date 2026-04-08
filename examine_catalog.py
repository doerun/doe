import json

with open("bench/workloads/metadata/backend-workload-catalog.json", "r") as f:
    data = json.load(f)

with open("config/backend-workload-cohorts.json", "r") as f:
    cohorts = json.load(f)

vulkan_governed = cohorts["profiles"]["amd_vulkan"]["governed"]

for w in data["workloads"]:
    wid = w["id"]
    if wid in vulkan_governed:
        shared = w.get("shared", {})
        vk_lane = w.get("lanes", {}).get("amd_vulkan_superset", {})
        
        comparable = vk_lane.get("comparable", shared.get("comparable", False))
        if not comparable:
            print(f"{wid} is not comparable in amd_vulkan_superset!")


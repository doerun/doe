import json

with open("bench/workloads/metadata/backend-workload-catalog.json", "r") as f:
    data = json.load(f)

for w in data["workloads"]:
    domain = w.get("shared", {}).get("domain", "")
    if domain == "surface":
        is_vetted = w.get("shared", {}).get("applesToApplesVetted", False)
        if not is_vetted:
            w["shared"]["comparable"] = False
            w["shared"]["benchmarkClass"] = "directional"
            w["shared"]["claimEligible"] = False
            
            for lane_name, lane_override in w.get("lanes", {}).items():
                if "comparable" in lane_override:
                    lane_override["comparable"] = False
                if "benchmarkClass" in lane_override:
                    lane_override["benchmarkClass"] = "directional"
                if "claimEligible" in lane_override:
                    lane_override["claimEligible"] = False

with open("bench/workloads/metadata/backend-workload-catalog.json", "w") as f:
    json.dump(data, f, indent=2)


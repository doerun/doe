import json

with open("bench/workloads/metadata/backend-workload-catalog.json", "r") as f:
    data = json.load(f)

for w in data["workloads"]:
    if w["id"].startswith("inference_gemma3_"):
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

with open("bench/workloads/metadata/backend-workload-catalog.json", "w") as f:
    json.dump(data, f, indent=2)


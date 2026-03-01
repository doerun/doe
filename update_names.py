import json
import sys

mapping = {
    "buffer_upload_1kb": "par_buffer_upload_1kb",
    "buffer_upload_64kb": "par_buffer_upload_64kb",
    "buffer_upload_1mb": "par_buffer_upload_1mb",
    "buffer_upload_4mb": "par_buffer_upload_4mb",
    "buffer_upload_16mb": "par_buffer_upload_16mb",
    "render_draw_throughput_proxy": "exp_render_draw_throughput_proxy",
    "render_draw_state_bindings": "par_render_draw_state_bindings",
    "render_draw_redundant_pipeline_bindings": "par_render_draw_redundant_pipeline_bindings",
    "render_bundle_dynamic_bindings": "par_render_bundle_dynamic_bindings",
    "render_bundle_dynamic_pipeline_bindings": "par_render_bundle_dynamic_pipeline_bindings",
    "texture_sampler_write_query_destroy_contract": "ctr_texture_sampler_write_query_destroy_contract",
    "texture_sampler_write_query_destroy_contract_mip8": "ctr_texture_sampler_write_query_destroy_contract_mip8",
    "async_pipeline_diagnostics_contract": "ctr_async_pipeline_diagnostics_contract",
    "p1_resource_table_immediates_macro_500": "ctr_resource_table_immediates_macro_500",
    "texture_sampler_write_query_destroy_macro_500": "ctr_texture_sampler_write_query_destroy_macro_500",
    "p0_resource_lifecycle_contract": "ctr_resource_lifecycle_contract",
    "p0_render_pixel_local_storage_barrier_macro_500": "ctr_render_pixel_local_storage_barrier_macro_500",
    "concurrent_execution_single_contract": "ctr_concurrent_execution_single_contract",
    "uniform_buffer_update_writebuffer_partial_single": "par_uniform_buffer_update_writebuffer_partial_single"
}

path = "bench/out/20260301T003456Z/metal.macos.final.local.comparable.latest.json"

try:
    with open(path, "r") as f:
        data = json.load(f)

    changed = False
    for w in data.get("workloads", []):
        old_id = w.get("id")
        if old_id in mapping:
            w["id"] = mapping[old_id]
            changed = True
            
    if changed:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        print("Updated workload IDs successfully.")
    else:
        print("No workloads needed updating (already updated?).")
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)

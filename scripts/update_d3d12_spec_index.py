#!/usr/bin/env python3
"""Batch-update D3D12 cells in webgpu-spec-index.json for newly implemented features."""

import json
import sys

SPEC_INDEX_PATH = "config/webgpu-spec-index.json"

# Interfaces whose D3D12 implementation status should be "implemented"
INTERFACE_IMPLEMENTED = {
    "GPUBuffer",
    "GPUQueue",
    "GPUQuerySet",
    "GPUTextureView",
    "GPUBindGroup",
    "GPUBindGroupLayout",
    "GPUSampler",
    "GPUComputePipeline",
    "GPUComputePassEncoder",
    "GPURenderPipeline",
    "GPURenderPassEncoder",
    "GPURenderBundle",
    "GPURenderBundleEncoder",
    "GPUTexture",
}

# Interfaces that go from unreviewed/partial to "partial" (not fully complete)
INTERFACE_PARTIAL = {
    "GPUDevice",
    "GPUAdapter",
    "GPUCommandEncoder",
    "GPUCommandBuffer",
}

# Specific members to mark as implemented
MEMBER_IMPLEMENTED = {
    ("GPUDevice", "limits"),
    ("GPUDevice", "features"),
    ("GPUDevice", "createQuerySet"),
    ("GPUDevice", "createBindGroup"),
    ("GPUDevice", "createBindGroupLayout"),
    ("GPUDevice", "createBuffer"),
    ("GPUDevice", "createComputePipeline"),
    ("GPUDevice", "createRenderPipeline"),
    ("GPUDevice", "createSampler"),
    ("GPUDevice", "createTexture"),
    ("GPUDevice", "createShaderModule"),
    ("GPUDevice", "createCommandEncoder"),
    ("GPUAdapter", "limits"),
    ("GPUAdapter", "features"),
    ("GPUQueue", "onSubmittedWorkDone"),
    ("GPUQueue", "submit"),
    ("GPUQueue", "writeBuffer"),
    ("GPUQueue", "writeTexture"),
    ("GPUBuffer", "mapAsync"),
    ("GPUBuffer", "getMappedRange"),
    ("GPUBuffer", "unmap"),
    ("GPUBuffer", "destroy"),
    ("GPUBuffer", "size"),
    ("GPUBuffer", "usage"),
    ("GPUBuffer", "mapState"),
    ("GPUComputePassEncoder", "dispatchWorkgroups"),
    ("GPUComputePassEncoder", "dispatchWorkgroupsIndirect"),
    ("GPUComputePassEncoder", "setPipeline"),
    ("GPUComputePassEncoder", "setBindGroup"),
    ("GPUComputePassEncoder", "end"),
    ("GPURenderPassEncoder", "setPipeline"),
    ("GPURenderPassEncoder", "setBindGroup"),
    ("GPURenderPassEncoder", "setViewport"),
    ("GPURenderPassEncoder", "setScissorRect"),
    ("GPURenderPassEncoder", "draw"),
    ("GPURenderPassEncoder", "drawIndexed"),
    ("GPURenderPassEncoder", "drawIndirect"),
    ("GPURenderPassEncoder", "drawIndexedIndirect"),
    ("GPURenderPassEncoder", "end"),
    ("GPURenderPassEncoder", "setVertexBuffer"),
    ("GPURenderPassEncoder", "setIndexBuffer"),
    ("GPUTexture", "createView"),
    ("GPUTexture", "destroy"),
    ("GPUTexture", "width"),
    ("GPUTexture", "height"),
    ("GPUTexture", "depthOrArrayLayers"),
    ("GPUTexture", "format"),
    ("GPUTexture", "sampleCount"),
    ("GPUTexture", "mipLevelCount"),
    ("GPUTexture", "dimension"),
    ("GPUTexture", "usage"),
    ("GPUQuerySet", "destroy"),
    ("GPUQuerySet", "type"),
    ("GPUQuerySet", "count"),
    ("GPUCommandEncoder", "beginComputePass"),
    ("GPUCommandEncoder", "beginRenderPass"),
    ("GPUCommandEncoder", "copyBufferToBuffer"),
    ("GPUCommandEncoder", "copyBufferToTexture"),
    ("GPUCommandEncoder", "copyTextureToBuffer"),
    ("GPUCommandEncoder", "copyTextureToTexture"),
    ("GPUCommandEncoder", "finish"),
    ("GPUCommandEncoder", "writeTimestamp"),
    ("GPUCommandEncoder", "resolveQuerySet"),
}

SOURCE_REFS = [
    "runtime/zig/src/backend/d3d12/mod.zig:221",
    "runtime/zig/src/backend/d3d12/d3d12_native_runtime.zig:1",
    "runtime/zig/src/backend/d3d12/d3d12_device_caps.zig:1",
]

MEMBER_SOURCE_REFS = {
    "limits": ["runtime/zig/src/backend/d3d12/d3d12_device_caps.zig:1"],
    "features": ["runtime/zig/src/backend/d3d12/d3d12_device_caps.zig:1"],
    "onSubmittedWorkDone": ["runtime/zig/src/backend/d3d12/d3d12_native_runtime.zig:380"],
    "mapAsync": ["runtime/zig/src/backend/d3d12/commands/d3d12_map_async.zig:14"],
    "getMappedRange": ["runtime/zig/src/backend/d3d12/commands/d3d12_map_async.zig:14"],
    "unmap": ["runtime/zig/src/backend/d3d12/commands/d3d12_map_async.zig:14"],
    "dispatchWorkgroupsIndirect": ["runtime/zig/src/backend/d3d12/commands/d3d12_dispatch.zig:76"],
    "createView": ["runtime/zig/src/backend/d3d12/resources/d3d12_texture_view.zig:1"],
    "createQuerySet": ["runtime/zig/src/backend/d3d12/d3d12_query_set.zig:1"],
    "createBindGroup": ["runtime/zig/src/backend/d3d12/d3d12_descriptors.zig:1"],
    "createBindGroupLayout": ["runtime/zig/src/backend/d3d12/d3d12_descriptors.zig:1"],
    "beginRenderPass": ["runtime/zig/src/backend/d3d12/commands/d3d12_render.zig:60"],
    "draw": ["runtime/zig/src/backend/d3d12/commands/d3d12_render.zig:60"],
    "drawIndexed": ["runtime/zig/src/backend/d3d12/commands/d3d12_render.zig:60"],
    "drawIndirect": ["runtime/zig/src/backend/d3d12/commands/d3d12_render.zig:60"],
    "drawIndexedIndirect": ["runtime/zig/src/backend/d3d12/commands/d3d12_render.zig:60"],
    "writeTimestamp": ["runtime/zig/src/backend/d3d12/commands/d3d12_gpu_timestamps.zig:1"],
    "resolveQuerySet": ["runtime/zig/src/backend/d3d12/d3d12_query_set.zig:1"],
}


def update_cell(cell, status, notes=None, source_refs=None):
    """Update a D3D12 checklist cell."""
    cell["status"] = status
    if notes:
        cell["notes"] = notes
    if source_refs:
        cell["sourceRefs"] = source_refs


def process_interface(iface, data):
    """Process a single interface entry."""
    name = iface["name"]
    d3d12 = iface["checklist"].get("d3d12")
    if not d3d12:
        return

    # Update interface-level D3D12 cell
    if name in INTERFACE_IMPLEMENTED:
        if d3d12["implementation"]["status"] in ("unreviewed", "partial", "not_wired", "blocked"):
            update_cell(d3d12["implementation"], "implemented",
                       notes=[], source_refs=SOURCE_REFS[:2])
            if d3d12["correctness"]["status"] == "unreviewed":
                update_cell(d3d12["correctness"], "unit",
                           notes=["Contract-path test coverage via run_contract_path_for_test."],
                           source_refs=["runtime/zig/src/backend/d3d12/mod.zig:619"])
    elif name in INTERFACE_PARTIAL:
        if d3d12["implementation"]["status"] in ("unreviewed", "blocked"):
            update_cell(d3d12["implementation"], "partial",
                       notes=[], source_refs=SOURCE_REFS)
            if d3d12["correctness"]["status"] == "unreviewed":
                update_cell(d3d12["correctness"], "unit",
                           notes=[], source_refs=["runtime/zig/src/backend/d3d12/mod.zig:619"])

    # Update member-level D3D12 cells
    for member in iface.get("members", []):
        member_name = member["name"]
        md3d12 = member["checklist"].get("d3d12")
        if not md3d12:
            continue

        key = (name, member_name)
        if key in MEMBER_IMPLEMENTED:
            if md3d12["implementation"]["status"] in ("unreviewed", "partial", "not_wired", "blocked"):
                refs = MEMBER_SOURCE_REFS.get(member_name, SOURCE_REFS[:2])
                update_cell(md3d12["implementation"], "implemented",
                           notes=[], source_refs=refs)
                if md3d12["correctness"]["status"] == "unreviewed":
                    update_cell(md3d12["correctness"], "unit",
                               notes=[], source_refs=refs[:1])


def main():
    with open(SPEC_INDEX_PATH, "r") as f:
        data = json.load(f)

    for iface in data.get("interfaces", []):
        process_interface(iface, data)

    data["lastUpdated"] = "2026-03-17"

    with open(SPEC_INDEX_PATH, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    print("D3D12 spec index updated.")


if __name__ == "__main__":
    main()

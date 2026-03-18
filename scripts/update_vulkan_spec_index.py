#!/usr/bin/env python3
"""Batch-update Vulkan cells in webgpu-spec-index.json for newly implemented features."""

import json
import sys

SPEC_INDEX_PATH = "config/webgpu-spec-index.json"

# Interfaces whose Vulkan implementation status should be "implemented"
INTERFACE_IMPLEMENTED = {
    "GPUBuffer",
    "GPUQueue",
    "GPUTexture",
    "GPUSampler",
    "GPUComputePipeline",
    "GPUComputePassEncoder",
    "GPURenderPipeline",
    "GPURenderPassEncoder",
    "GPUBindGroup",
    "GPUBindGroupLayout",
    "GPUShaderModule",
}

# Interfaces that go from unreviewed/partial to "partial" (not fully complete)
INTERFACE_PARTIAL = {
    "GPUDevice",
    "GPUAdapter",
    "GPUCommandEncoder",
    "GPUCommandBuffer",
    "GPUTextureView",
}

# Specific members to mark as implemented
MEMBER_IMPLEMENTED = {
    ("GPUDevice", "limits"),
    ("GPUDevice", "features"),
    ("GPUDevice", "createBuffer"),
    ("GPUDevice", "createTexture"),
    ("GPUDevice", "createSampler"),
    ("GPUDevice", "createShaderModule"),
    ("GPUDevice", "createComputePipeline"),
    ("GPUDevice", "createRenderPipeline"),
    ("GPUDevice", "createBindGroup"),
    ("GPUDevice", "createBindGroupLayout"),
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
    ("GPUCommandEncoder", "beginComputePass"),
    ("GPUCommandEncoder", "beginRenderPass"),
    ("GPUCommandEncoder", "copyBufferToBuffer"),
    ("GPUCommandEncoder", "copyBufferToTexture"),
    ("GPUCommandEncoder", "finish"),
    ("GPUCommandEncoder", "clearBuffer"),
}

# Members explicitly unsupported on Vulkan (won't be marked implemented)
MEMBER_UNSUPPORTED = {
    ("GPUCommandEncoder", "copyTextureToBuffer"),
    ("GPUCommandEncoder", "copyTextureToTexture"),
}

SOURCE_REFS = [
    "runtime/zig/src/backend/vulkan/mod.zig:1",
    "runtime/zig/src/backend/vulkan/native_runtime.zig:1",
]

MEMBER_SOURCE_REFS = {
    "limits": ["runtime/zig/src/doe_device_caps.zig:1"],
    "features": ["runtime/zig/src/doe_device_caps.zig:1"],
    "onSubmittedWorkDone": ["runtime/zig/src/doe_queue_submit_native.zig:1"],
    "mapAsync": ["runtime/zig/src/backend/vulkan/native_runtime.zig:1"],
    "getMappedRange": ["runtime/zig/src/backend/vulkan/native_runtime.zig:1"],
    "unmap": ["runtime/zig/src/backend/vulkan/native_runtime.zig:1"],
    "copyBufferToBuffer": ["runtime/zig/src/doe_encoder_native.zig:1"],
    "copyBufferToTexture": ["runtime/zig/src/doe_encoder_native.zig:1"],
    "clearBuffer": ["runtime/zig/src/doe_command_texture_native.zig:1"],
    "writeBuffer": ["runtime/zig/src/doe_queue_submit_native.zig:1"],
    "writeTexture": ["runtime/zig/src/doe_command_texture_native.zig:1"],
    "dispatchWorkgroupsIndirect": ["runtime/zig/src/doe_vulkan_compute_native.zig:1"],
    "createView": ["runtime/zig/src/backend/vulkan/native_runtime.zig:1"],
    "drawIndirect": ["runtime/zig/src/doe_vulkan_render_native.zig:1"],
    "drawIndexedIndirect": ["runtime/zig/src/doe_vulkan_render_native.zig:1"],
}


def update_cell(cell, status, notes=None, source_refs=None):
    """Update a Vulkan checklist cell."""
    cell["status"] = status
    if notes:
        cell["notes"] = notes
    if source_refs:
        cell["sourceRefs"] = source_refs


def process_interface(iface, data):
    """Process a single interface entry."""
    name = iface["name"]
    vulkan = iface["checklist"].get("vulkan")
    if not vulkan:
        return

    # Update interface-level Vulkan cell
    if name in INTERFACE_IMPLEMENTED:
        if vulkan["implementation"]["status"] in ("unreviewed", "partial", "not_wired", "blocked"):
            update_cell(vulkan["implementation"], "implemented",
                       notes=[], source_refs=SOURCE_REFS[:2])
            if vulkan["correctness"]["status"] == "unreviewed":
                update_cell(vulkan["correctness"], "unit",
                           notes=["Vulkan native runtime test coverage."],
                           source_refs=["runtime/zig/tests/vulkan/"])
    elif name in INTERFACE_PARTIAL:
        if vulkan["implementation"]["status"] in ("unreviewed", "blocked"):
            update_cell(vulkan["implementation"], "partial",
                       notes=[], source_refs=SOURCE_REFS)
            if vulkan["correctness"]["status"] == "unreviewed":
                update_cell(vulkan["correctness"], "unit",
                           notes=[], source_refs=["runtime/zig/tests/vulkan/"])

    # Update member-level Vulkan cells
    for member in iface.get("members", []):
        member_name = member["name"]
        mvulkan = member["checklist"].get("vulkan")
        if not mvulkan:
            continue

        key = (name, member_name)
        if key in MEMBER_IMPLEMENTED:
            if mvulkan["implementation"]["status"] in ("unreviewed", "partial", "not_wired", "blocked"):
                refs = MEMBER_SOURCE_REFS.get(member_name, SOURCE_REFS[:2])
                update_cell(mvulkan["implementation"], "implemented",
                           notes=[], source_refs=refs)
                if mvulkan["correctness"]["status"] == "unreviewed":
                    update_cell(mvulkan["correctness"], "unit",
                               notes=[], source_refs=refs[:1])
        elif key in MEMBER_UNSUPPORTED:
            if mvulkan["implementation"]["status"] in ("unreviewed", "partial", "not_wired", "blocked"):
                update_cell(mvulkan["implementation"], "not_wired",
                           notes=["Explicit unsupported on Vulkan — logs warning."],
                           source_refs=SOURCE_REFS[:1])


def main():
    with open(SPEC_INDEX_PATH, "r") as f:
        data = json.load(f)

    for iface in data.get("interfaces", []):
        process_interface(iface, data)

    data["lastUpdated"] = "2026-03-17"

    with open(SPEC_INDEX_PATH, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    print("Vulkan spec index updated.")


if __name__ == "__main__":
    main()

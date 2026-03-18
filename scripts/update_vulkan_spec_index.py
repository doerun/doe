#!/usr/bin/env python3
"""Batch-update Vulkan cells in webgpu-spec-index.jsonl for newly implemented features."""

import json

SPEC_INDEX_PATH = "config/webgpu-spec-index.jsonl"

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


def get_vulkan(row):
    return row.setdefault("vulkan", {})


def update_interface(row):
    name = row["name"]
    vulkan = get_vulkan(row)
    status = vulkan.get("impl", "unreviewed")

    if name in INTERFACE_IMPLEMENTED:
        if status in ("unreviewed", "partial", "not_wired", "blocked"):
            vulkan["impl"] = "implemented"
            if vulkan.get("correct", "unreviewed") == "unreviewed":
                vulkan["correct"] = "unit"
                vulkan["notes"] = ["Vulkan native runtime test coverage."]
    elif name in INTERFACE_PARTIAL:
        if status in ("unreviewed", "blocked"):
            vulkan["impl"] = "partial"
            if vulkan.get("correct", "unreviewed") == "unreviewed":
                vulkan["correct"] = "unit"


def update_member(row):
    key = (row["parent"], row["name"])
    vulkan = get_vulkan(row)
    status = vulkan.get("impl", "unreviewed")

    if key in MEMBER_IMPLEMENTED:
        if status in ("unreviewed", "partial", "not_wired", "blocked"):
            vulkan["impl"] = "implemented"
            if vulkan.get("correct", "unreviewed") == "unreviewed":
                vulkan["correct"] = "unit"
    elif key in MEMBER_UNSUPPORTED:
        if status in ("unreviewed", "partial", "not_wired", "blocked"):
            vulkan["impl"] = "not_wired"
            vulkan["notes"] = ["Explicit unsupported on Vulkan — logs warning."]


def main():
    with open(SPEC_INDEX_PATH) as f:
        lines = f.readlines()

    rows = [json.loads(line) for line in lines]

    for row in rows:
        kind = row.get("kind")
        if kind == "header":
            row["lastUpdated"] = "2026-03-17"
        elif kind == "interface":
            update_interface(row)
        elif kind == "member":
            update_member(row)

    with open(SPEC_INDEX_PATH, "w") as f:
        for row in rows:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")

    print("Vulkan spec index updated.")


if __name__ == "__main__":
    main()

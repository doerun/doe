#!/usr/bin/env python3
"""Batch-update D3D12 cells in webgpu-spec-index.jsonl for newly implemented features."""

import json

SPEC_INDEX_PATH = "config/webgpu-spec-index.jsonl"

# Interfaces whose D3D12 implementation status should be "implemented"
INTERFACE_IMPLEMENTED = {
    "GPUBuffer",
    "GPUQueue",
    "GPUQuerySet",
    "GPUTextureView",
    "GPUBindGroup",
    "GPUBindGroupLayout",
    "GPUSampler",
    "GPUShaderModule",
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
    "GPUPipelineLayout",
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
    ("GPUDevice", "createPipelineLayout"),
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


def get_d3d12(row):
    return row.setdefault("d3d12", {})


def update_interface(row):
    name = row["name"]
    d3d12 = get_d3d12(row)
    status = d3d12.get("impl", "unreviewed")

    if name in INTERFACE_IMPLEMENTED:
        if status in ("unreviewed", "partial", "not_wired", "blocked"):
            d3d12["impl"] = "implemented"
            if d3d12.get("correct", "unreviewed") == "unreviewed":
                d3d12["correct"] = "unit"
                d3d12["notes"] = ["Contract-path test coverage via run_contract_path_for_test."]
    elif name in INTERFACE_PARTIAL:
        if status in ("unreviewed", "blocked"):
            d3d12["impl"] = "partial"
            if d3d12.get("correct", "unreviewed") == "unreviewed":
                d3d12["correct"] = "unit"


def update_member(row):
    key = (row["parent"], row["name"])
    d3d12 = get_d3d12(row)
    status = d3d12.get("impl", "unreviewed")

    if key in MEMBER_IMPLEMENTED:
        if status in ("unreviewed", "partial", "not_wired", "blocked"):
            d3d12["impl"] = "implemented"
            if d3d12.get("correct", "unreviewed") == "unreviewed":
                d3d12["correct"] = "unit"


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

    print("D3D12 spec index updated.")


if __name__ == "__main__":
    main()

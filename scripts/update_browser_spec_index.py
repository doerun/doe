#!/usr/bin/env python3
"""Batch-update browser cells in webgpu-spec-index.json based on browser test evidence.

Browser backend = Chromium Track A, where Fawn replaces Dawn as the WebGPU
implementation.  The browser runtime routes through the Doe Zig runtime exposed
via Chromium WebGPU bindings.

Evidence sources:
  - browser/fawn-browser/scripts/webgpu-playwright-smoke.mjs
    (compute increment, render triangle, writeBuffer bench, dispatch bench,
     canvas API probing)
  - browser/fawn-browser/scripts/webgpu-playwright-layered-bench.mjs
    (write_buffer_upload, compute_dispatch_basic, render_triangle_readback,
     render_bundle_replay, texture_sample_raster, texture_write_query_destroy,
     pipeline_compile_stress, async_pipeline_diagnostics, surface_present_basic,
     canvas_reconfigure_resize, queue_submit_burst, async_pipeline_burst,
     startup_adapter_device)
  - browser/fawn-browser/artifacts/ (passing Doe mode results)

Classification rules:
  - "implemented"  = API exercised and verified in browser Playwright tests
  - "partial"      = runtime implements the capability but browser-specific
                     test has not exercised it (or only partially)
  - "unreviewed"   = no browser evidence at all
  - "out_of_scope" = not applicable to browser path
"""

import json
import sys

SPEC_INDEX_PATH = "config/webgpu-spec-index.json"

SMOKE_REF = "browser/fawn-browser/scripts/webgpu-playwright-smoke.mjs"
LAYERED_REF = "browser/fawn-browser/scripts/webgpu-playwright-layered-bench.mjs"
ARTIFACT_REF = "browser/fawn-browser/artifacts/20260309T015018Z"

# ---------------------------------------------------------------------------
# Interfaces with browser test evidence for implementation status.
# "implemented" = the full interface is exercised in browser tests.
# "partial" = some members work, but coverage is incomplete.
# ---------------------------------------------------------------------------

INTERFACE_IMPLEMENTED = {
    "GPU",
    "GPUAdapter",
    "GPUBuffer",
    "GPUBindGroup",
    "GPUBindGroupLayout",
    "GPUCanvasContext",
    "GPUCommandBuffer",
    "GPUCommandEncoder",
    "GPUComputePassEncoder",
    "GPUComputePipeline",
    "GPUDevice",
    "GPUMapMode",
    "GPUQueue",
    "GPURenderBundle",
    "GPURenderBundleEncoder",
    "GPURenderPassEncoder",
    "GPURenderPipeline",
    "GPUSampler",
    "GPUShaderModule",
    "GPUShaderStage",
    "GPUTexture",
    "GPUTextureView",
    "GPUBufferUsage",
    "GPUTextureUsage",
}

INTERFACE_PARTIAL = {
    "GPUAdapterInfo",
    "GPUComputePipelineDescriptor",
    "GPUPipelineLayout",
    "GPURenderPipelineDescriptor",
    "GPUSupportedLimits",
}

# Dictionaries used as parameter objects in browser tests.
# These are fully exercised when the API that consumes them works.
DICT_IMPLEMENTED = {
    "GPUBindGroupDescriptor",
    "GPUBindGroupEntry",
    "GPUBindGroupLayoutDescriptor",
    "GPUBindGroupLayoutEntry",
    "GPUBlendComponent",
    "GPUBlendState",
    "GPUBufferBinding",
    "GPUBufferBindingLayout",
    "GPUBufferDescriptor",
    "GPUCanvasConfiguration",
    "GPUColorDict",
    "GPUColorTargetState",
    "GPUComputePassDescriptor",
    "GPUDeviceDescriptor",
    "GPUExtent3DDict",
    "GPUFragmentState",
    "GPUMultisampleState",
    "GPUPrimitiveState",
    "GPURenderBundleEncoderDescriptor",
    "GPURenderPassColorAttachment",
    "GPURenderPassDescriptor",
    "GPUSamplerDescriptor",
    "GPUShaderModuleDescriptor",
    "GPUTexelCopyBufferInfo",
    "GPUTexelCopyTextureInfo",
    "GPUTextureDescriptor",
    "GPUVertexState",
}

DICT_PARTIAL = {
    "GPUDepthStencilState",
    "GPUPipelineLayoutDescriptor",
    "GPURenderPassDepthStencilAttachment",
    "GPURenderPassLayout",
    "GPUStencilFaceState",
    "GPUTextureBindingLayout",
    "GPUTextureViewDescriptor",
    "GPUStorageTextureBindingLayout",
    "GPUSamplerBindingLayout",
}

# ---------------------------------------------------------------------------
# Member-level overrides: (InterfaceName, MemberName) -> status
# ---------------------------------------------------------------------------

MEMBER_IMPLEMENTED = {
    # GPU
    ("GPU", "requestAdapter"),
    ("GPU", "getPreferredCanvasFormat"),
    ("GPU", "wgslLanguageFeatures"),
    # GPUAdapter
    ("GPUAdapter", "requestDevice"),
    ("GPUAdapter", "features"),
    ("GPUAdapter", "info"),
    ("GPUAdapter", "limits"),
    # GPUDevice
    ("GPUDevice", "createBuffer"),
    ("GPUDevice", "createTexture"),
    ("GPUDevice", "createSampler"),
    ("GPUDevice", "createShaderModule"),
    ("GPUDevice", "createComputePipeline"),
    ("GPUDevice", "createComputePipelineAsync"),
    ("GPUDevice", "createRenderPipeline"),
    ("GPUDevice", "createBindGroup"),
    ("GPUDevice", "createBindGroupLayout"),
    ("GPUDevice", "createCommandEncoder"),
    ("GPUDevice", "createRenderBundleEncoder"),
    ("GPUDevice", "features"),
    ("GPUDevice", "limits"),
    ("GPUDevice", "queue"),
    ("GPUDevice", "label"),
    # GPUQueue
    ("GPUQueue", "submit"),
    ("GPUQueue", "writeBuffer"),
    ("GPUQueue", "writeTexture"),
    ("GPUQueue", "onSubmittedWorkDone"),
    ("GPUQueue", "label"),
    # GPUBuffer
    ("GPUBuffer", "mapAsync"),
    ("GPUBuffer", "getMappedRange"),
    ("GPUBuffer", "unmap"),
    ("GPUBuffer", "destroy"),
    ("GPUBuffer", "size"),
    ("GPUBuffer", "usage"),
    ("GPUBuffer", "label"),
    # GPUTexture
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
    ("GPUTexture", "label"),
    # GPUTextureView
    ("GPUTextureView", "label"),
    # GPUShaderModule
    ("GPUShaderModule", "label"),
    # GPUComputePipeline
    ("GPUComputePipeline", "getBindGroupLayout"),
    ("GPUComputePipeline", "label"),
    # GPURenderPipeline
    ("GPURenderPipeline", "getBindGroupLayout"),
    ("GPURenderPipeline", "label"),
    # GPUCommandEncoder
    ("GPUCommandEncoder", "beginComputePass"),
    ("GPUCommandEncoder", "beginRenderPass"),
    ("GPUCommandEncoder", "copyBufferToBuffer"),
    ("GPUCommandEncoder", "copyTextureToBuffer"),
    ("GPUCommandEncoder", "finish"),
    ("GPUCommandEncoder", "label"),
    # GPUComputePassEncoder
    ("GPUComputePassEncoder", "setPipeline"),
    ("GPUComputePassEncoder", "setBindGroup"),
    ("GPUComputePassEncoder", "dispatchWorkgroups"),
    ("GPUComputePassEncoder", "end"),
    ("GPUComputePassEncoder", "label"),
    # GPURenderPassEncoder
    ("GPURenderPassEncoder", "setPipeline"),
    ("GPURenderPassEncoder", "setBindGroup"),
    ("GPURenderPassEncoder", "draw"),
    ("GPURenderPassEncoder", "end"),
    ("GPURenderPassEncoder", "executeBundles"),
    ("GPURenderPassEncoder", "setViewport"),
    ("GPURenderPassEncoder", "setScissorRect"),
    ("GPURenderPassEncoder", "label"),
    # GPURenderBundleEncoder
    ("GPURenderBundleEncoder", "setPipeline"),
    ("GPURenderBundleEncoder", "draw"),
    ("GPURenderBundleEncoder", "finish"),
    ("GPURenderBundleEncoder", "label"),
    # GPURenderBundle
    ("GPURenderBundle", "label"),
    # GPUSampler
    ("GPUSampler", "label"),
    # GPUBindGroup
    ("GPUBindGroup", "label"),
    # GPUBindGroupLayout
    ("GPUBindGroupLayout", "label"),
    # GPUCommandBuffer
    ("GPUCommandBuffer", "label"),
    # GPUCanvasContext
    ("GPUCanvasContext", "configure"),
    ("GPUCanvasContext", "getCurrentTexture"),
    ("GPUCanvasContext", "canvas"),
    # GPUMapMode
    ("GPUMapMode", "READ"),
    # GPUBufferUsage
    ("GPUBufferUsage", "COPY_DST"),
    ("GPUBufferUsage", "COPY_SRC"),
    ("GPUBufferUsage", "STORAGE"),
    ("GPUBufferUsage", "MAP_READ"),
    ("GPUBufferUsage", "MAP_WRITE"),
    # GPUTextureUsage
    ("GPUTextureUsage", "RENDER_ATTACHMENT"),
    ("GPUTextureUsage", "COPY_SRC"),
    ("GPUTextureUsage", "COPY_DST"),
    ("GPUTextureUsage", "TEXTURE_BINDING"),
    # GPUShaderStage
    ("GPUShaderStage", "COMPUTE"),
    ("GPUShaderStage", "VERTEX"),
    ("GPUShaderStage", "FRAGMENT"),
}

# Members with partial evidence (runtime has it, browser test hasn't
# explicitly exercised it but the interface works in browser context).
MEMBER_PARTIAL = {
    ("GPUDevice", "createPipelineLayout"),
    ("GPUDevice", "createQuerySet"),
    ("GPUDevice", "createRenderPipelineAsync"),
    ("GPUDevice", "destroy"),
    ("GPUDevice", "pushErrorScope"),
    ("GPUDevice", "popErrorScope"),
    ("GPUDevice", "addEventListener"),
    ("GPUDevice", "removeEventListener"),
    ("GPUDevice", "adapterInfo"),
    ("GPUDevice", "lost"),
    ("GPUDevice", "onuncapturederror"),
    ("GPUBuffer", "mapState"),
    ("GPUComputePassEncoder", "dispatchWorkgroupsIndirect"),
    ("GPURenderPassEncoder", "drawIndexed"),
    ("GPURenderPassEncoder", "drawIndirect"),
    ("GPURenderPassEncoder", "drawIndexedIndirect"),
    ("GPURenderPassEncoder", "setVertexBuffer"),
    ("GPURenderPassEncoder", "setIndexBuffer"),
    ("GPURenderPassEncoder", "setBlendConstant"),
    ("GPURenderPassEncoder", "setStencilReference"),
    ("GPURenderPassEncoder", "beginOcclusionQuery"),
    ("GPURenderPassEncoder", "endOcclusionQuery"),
    ("GPURenderPassEncoder", "insertDebugMarker"),
    ("GPURenderPassEncoder", "pushDebugGroup"),
    ("GPURenderPassEncoder", "popDebugGroup"),
    ("GPURenderBundleEncoder", "drawIndexed"),
    ("GPURenderBundleEncoder", "drawIndirect"),
    ("GPURenderBundleEncoder", "drawIndexedIndirect"),
    ("GPURenderBundleEncoder", "setBindGroup"),
    ("GPURenderBundleEncoder", "setVertexBuffer"),
    ("GPURenderBundleEncoder", "setIndexBuffer"),
    ("GPURenderBundleEncoder", "insertDebugMarker"),
    ("GPURenderBundleEncoder", "pushDebugGroup"),
    ("GPURenderBundleEncoder", "popDebugGroup"),
    ("GPUCommandEncoder", "copyBufferToTexture"),
    ("GPUCommandEncoder", "copyTextureToTexture"),
    ("GPUCommandEncoder", "clearBuffer"),
    ("GPUCommandEncoder", "resolveQuerySet"),
    ("GPUCommandEncoder", "insertDebugMarker"),
    ("GPUCommandEncoder", "pushDebugGroup"),
    ("GPUCommandEncoder", "popDebugGroup"),
    ("GPUComputePassEncoder", "insertDebugMarker"),
    ("GPUComputePassEncoder", "pushDebugGroup"),
    ("GPUComputePassEncoder", "popDebugGroup"),
    ("GPUCanvasContext", "unconfigure"),
    ("GPUCanvasContext", "getConfiguration"),
    ("GPUQueue", "copyExternalImageToTexture"),
    ("GPUMapMode", "WRITE"),
    ("GPUBufferUsage", "INDEX"),
    ("GPUBufferUsage", "INDIRECT"),
    ("GPUBufferUsage", "VERTEX"),
    ("GPUBufferUsage", "UNIFORM"),
    ("GPUBufferUsage", "QUERY_RESOLVE"),
    ("GPUTextureUsage", "STORAGE_BINDING"),
    ("GPUTextureUsage", "TRANSIENT_ATTACHMENT"),
}

# ---------------------------------------------------------------------------
# String unions exercised in browser tests
# ---------------------------------------------------------------------------

STRING_UNION_IMPLEMENTED = {
    "GPUAutoLayoutMode",
    "GPULoadOp",
    "GPUStoreOp",
    "GPUPrimitiveTopology",
    "GPUFilterMode",
    "GPUCanvasAlphaMode",
    "GPUTextureDimension",
}

STRING_UNION_PARTIAL = {
    "GPUAddressMode",
    "GPUBlendFactor",
    "GPUBlendOperation",
    "GPUBufferBindingType",
    "GPUBufferMapState",
    "GPUCompareFunction",
    "GPUCullMode",
    "GPUFrontFace",
    "GPUIndexFormat",
    "GPUMipmapFilterMode",
    "GPUTextureAspect",
    "GPUTextureFormat",
    "GPUTextureSampleType",
    "GPUTextureViewDimension",
    "GPUVertexFormat",
    "GPUVertexStepMode",
    "GPUFeatureName",
    "GPUPowerPreference",
    "GPUQueryType",
    "GPUSamplerBindingType",
    "GPUStencilOperation",
    "GPUStorageTextureAccess",
    "GPUErrorFilter",
}

# String union values explicitly verified in browser tests
STRING_VALUE_IMPLEMENTED = {
    ("GPUAutoLayoutMode", "auto"),
    ("GPULoadOp", "clear"),
    ("GPULoadOp", "load"),
    ("GPUStoreOp", "store"),
    ("GPUStoreOp", "discard"),
    ("GPUPrimitiveTopology", "triangle-list"),
    ("GPUFilterMode", "nearest"),
    ("GPUFilterMode", "linear"),
    ("GPUCanvasAlphaMode", "opaque"),
    ("GPUCanvasAlphaMode", "premultiplied"),
    ("GPUTextureDimension", "2d"),
    ("GPUTextureFormat", "rgba8unorm"),
    ("GPUTextureFormat", "bgra8unorm"),
    ("GPUTextureFormat", "rgba8unorm-srgb"),
    ("GPUTextureFormat", "bgra8unorm-srgb"),
    ("GPUBufferBindingType", "storage"),
    ("GPUBufferBindingType", "uniform"),
    ("GPUTextureSampleType", "float"),
    ("GPUTextureViewDimension", "2d"),
    ("GPUTextureAspect", "all"),
}

# Source references for browser cells
BROWSER_SOURCE_REFS = [
    f"{SMOKE_REF}:1",
    f"{LAYERED_REF}:1",
    f"{ARTIFACT_REF}/dawn-vs-doe.browser-layered.superset.summary.json",
]

SMOKE_SOURCE_REFS = [
    f"{SMOKE_REF}:1",
    f"{ARTIFACT_REF}/dawn-vs-doe.browser.playwright-smoke.diagnostic.json",
]

LAYERED_SOURCE_REFS = [
    f"{LAYERED_REF}:1",
    f"{ARTIFACT_REF}/dawn-vs-doe.browser-layered.superset.diagnostic.json",
]


def default_cell():
    return {
        "status": "unreviewed",
        "notes": [],
        "sourceRefs": [],
    }


def update_cell(cell, status, notes=None, source_refs=None):
    """Set browser checklist cell fields."""
    cell["status"] = status
    if notes is not None:
        cell["notes"] = notes
    if source_refs is not None:
        cell["sourceRefs"] = source_refs


def resolve_source_refs(iface_name, member_name=None):
    """Pick the most relevant source refs for a given interface/member."""
    # Canvas APIs are exercised in layered bench
    canvas_interfaces = {"GPUCanvasContext", "GPUCanvasConfiguration",
                         "GPUCanvasConfigurationOut", "GPUCanvasToneMapping"}
    if iface_name in canvas_interfaces:
        return LAYERED_SOURCE_REFS
    return BROWSER_SOURCE_REFS


def process_interface(iface):
    """Update browser cells for one interface entry."""
    name = iface["name"]
    browser = iface["checklist"].get("browser")
    if not browser:
        return

    all_targets = (
        INTERFACE_IMPLEMENTED | DICT_IMPLEMENTED |
        INTERFACE_PARTIAL | DICT_PARTIAL
    )

    if name in INTERFACE_IMPLEMENTED or name in DICT_IMPLEMENTED:
        if browser["implementation"]["status"] in (
            "unreviewed", "partial", "not_wired"
        ):
            refs = resolve_source_refs(name)
            update_cell(
                browser["implementation"], "implemented",
                notes=["Verified via Playwright browser smoke and layered bench."],
                source_refs=refs,
            )
            if browser["correctness"]["status"] == "unreviewed":
                update_cell(
                    browser["correctness"], "integration",
                    notes=["Playwright smoke + layered bench pass in Doe mode."],
                    source_refs=refs,
                )
            if browser["performance"]["status"] == "unreviewed":
                perf_status = "diagnostic"
                if name in {"GPUObjectBase", "GPUObjectDescriptorBase",
                            "GPUColorDict", "GPUExtent3DDict"}:
                    perf_status = "not_meaningful"
                update_cell(
                    browser["performance"], perf_status,
                    notes=["Browser bench runs are diagnostic, not claimable."],
                    source_refs=refs,
                )
    elif name in INTERFACE_PARTIAL or name in DICT_PARTIAL:
        if browser["implementation"]["status"] in ("unreviewed", "not_wired"):
            refs = resolve_source_refs(name)
            update_cell(
                browser["implementation"], "partial",
                notes=["Runtime implements but browser test coverage is incomplete."],
                source_refs=refs,
            )
            if browser["correctness"]["status"] == "unreviewed":
                update_cell(
                    browser["correctness"], "integration",
                    notes=[], source_refs=refs,
                )

    # Member-level updates
    for member in iface.get("members", []):
        member_name = member["name"]
        mbrowser = member["checklist"].get("browser")
        if not mbrowser:
            continue

        key = (name, member_name)
        refs = resolve_source_refs(name, member_name)

        if key in MEMBER_IMPLEMENTED:
            if mbrowser["implementation"]["status"] in (
                "unreviewed", "partial", "not_wired"
            ):
                update_cell(
                    mbrowser["implementation"], "implemented",
                    notes=[], source_refs=refs,
                )
                if mbrowser["correctness"]["status"] == "unreviewed":
                    update_cell(
                        mbrowser["correctness"], "integration",
                        notes=[], source_refs=refs,
                    )
                if mbrowser["performance"]["status"] == "unreviewed":
                    update_cell(
                        mbrowser["performance"], "diagnostic",
                        notes=[], source_refs=refs,
                    )
        elif key in MEMBER_PARTIAL:
            if mbrowser["implementation"]["status"] in (
                "unreviewed", "not_wired"
            ):
                update_cell(
                    mbrowser["implementation"], "partial",
                    notes=["Runtime supports; browser test not yet exercised."],
                    source_refs=refs,
                )
                if mbrowser["correctness"]["status"] == "unreviewed":
                    update_cell(
                        mbrowser["correctness"], "unreviewed",
                        notes=[], source_refs=[],
                    )


def process_string_union(su):
    """Update browser cells for one string-union entry."""
    name = su["name"]
    browser = su["checklist"].get("browser")
    if not browser:
        return

    if name in STRING_UNION_IMPLEMENTED:
        if browser["implementation"]["status"] in (
            "unreviewed", "partial", "not_wired"
        ):
            update_cell(
                browser["implementation"], "implemented",
                notes=["Exercised in browser Playwright tests."],
                source_refs=BROWSER_SOURCE_REFS,
            )
            if browser["correctness"]["status"] == "unreviewed":
                update_cell(
                    browser["correctness"], "integration",
                    notes=[], source_refs=BROWSER_SOURCE_REFS,
                )
            if browser["performance"]["status"] == "unreviewed":
                update_cell(
                    browser["performance"], "not_meaningful",
                    notes=[], source_refs=[],
                )
    elif name in STRING_UNION_PARTIAL:
        if browser["implementation"]["status"] in ("unreviewed", "not_wired"):
            update_cell(
                browser["implementation"], "partial",
                notes=["Some values exercised in browser tests; full coverage pending."],
                source_refs=BROWSER_SOURCE_REFS,
            )
            if browser["correctness"]["status"] == "unreviewed":
                update_cell(
                    browser["correctness"], "integration",
                    notes=[], source_refs=BROWSER_SOURCE_REFS,
                )

    # Value-level updates
    for value_entry in su.get("values", []):
        value_name = value_entry["name"]
        vbrowser = value_entry["checklist"].get("browser")
        if not vbrowser:
            continue

        key = (name, value_name)
        if key in STRING_VALUE_IMPLEMENTED:
            if vbrowser["implementation"]["status"] in (
                "unreviewed", "partial", "not_wired"
            ):
                update_cell(
                    vbrowser["implementation"], "implemented",
                    notes=[], source_refs=BROWSER_SOURCE_REFS,
                )
                if vbrowser["correctness"]["status"] == "unreviewed":
                    update_cell(
                        vbrowser["correctness"], "integration",
                        notes=[], source_refs=BROWSER_SOURCE_REFS,
                    )
                if vbrowser["performance"]["status"] == "unreviewed":
                    update_cell(
                        vbrowser["performance"], "not_meaningful",
                        notes=[], source_refs=[],
                    )


def count_browser_statuses(data):
    """Count browser implementation statuses across interfaces and members."""
    counts = {}
    for iface in data.get("interfaces", []):
        browser = iface["checklist"].get("browser", {})
        impl = browser.get("implementation", {})
        s = impl.get("status", "unreviewed")
        counts[s] = counts.get(s, 0) + 1
        for member in iface.get("members", []):
            mbrowser = member["checklist"].get("browser", {})
            mimpl = mbrowser.get("implementation", {})
            ms = mimpl.get("status", "unreviewed")
            counts[ms] = counts.get(ms, 0) + 1
    for su in data.get("stringUnions", []):
        browser = su["checklist"].get("browser", {})
        impl = browser.get("implementation", {})
        s = impl.get("status", "unreviewed")
        counts[s] = counts.get(s, 0) + 1
        for val in su.get("values", []):
            vbrowser = val["checklist"].get("browser", {})
            vimpl = vbrowser.get("implementation", {})
            vs = vimpl.get("status", "unreviewed")
            counts[vs] = counts.get(vs, 0) + 1
    return counts


def main():
    with open(SPEC_INDEX_PATH, "r") as f:
        data = json.load(f)

    print("Before update:")
    before = count_browser_statuses(data)
    for s, c in sorted(before.items()):
        print(f"  {s}: {c}")

    for iface in data.get("interfaces", []):
        process_interface(iface)

    for su in data.get("stringUnions", []):
        process_string_union(su)

    data["lastUpdated"] = "2026-03-17"

    print("\nAfter update:")
    after = count_browser_statuses(data)
    for s, c in sorted(after.items()):
        print(f"  {s}: {c}")

    with open(SPEC_INDEX_PATH, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    print(f"\nBrowser spec index updated in {SPEC_INDEX_PATH}")


if __name__ == "__main__":
    main()

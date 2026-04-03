const model = @import("../../model_webgpu_types.zig");
const types = @import("../../core/abi/wgpu_types.zig");
const loader = @import("../../core/abi/wgpu_loader.zig");
const resources = @import("../../core/resource/wgpu_resources.zig");
const render_resource_mod = @import("wgpu_render_resources.zig");
const rc = @import("wgpu_render_constants.zig");
const ffi = @import("../../webgpu_backend.zig");
const Backend = ffi.WebGPUBackend;

pub const TempRenderTextureResult = struct {
    view: ?types.WGPUTextureView,
    needs_copy_back: bool,
};

/// Determines whether a temp render texture is needed for the given render
/// command and, if so, creates the temp texture and view. Formats affected
/// by the mip-level workaround are redirected through a scratch texture at
/// mip 0 so the render attachment requirement is satisfied.
pub fn setupTempRenderTexture(
    self: *Backend,
    render: model.RenderDrawCommand,
    target_format: types.WGPUTextureFormat,
    target_resource: model.CopyTextureResource,
) !TempRenderTextureResult {
    const needs_temp = render.uses_temporary_render_texture and
        rc.is_affected_render_format(target_format) and
        target_resource.mip_level >= render.temporary_render_texture_min_mip_level;

    if (!needs_temp) {
        return .{ .view = null, .needs_copy_back = false };
    }

    const temp_handle = render.target_handle +% rc.TEMP_RENDER_TEXTURE_OFFSET;
    const temp_resource = model.CopyTextureResource{
        .handle = temp_handle,
        .kind = .texture,
        .width = render.target_width,
        .height = render.target_height,
        .depth_or_array_layers = 1,
        .format = render.target_format,
        .usage = types.WGPUTextureUsage_RenderAttachment | types.WGPUTextureUsage_CopySrc | types.WGPUTextureUsage_CopyDst,
        .dimension = model.WGPUTextureDimension_2D,
        .view_dimension = model.WGPUTextureViewDimension_2D,
        .mip_level = 0,
        .sample_count = 1,
        .aspect = model.WGPUTextureAspect_All,
        .bytes_per_row = 0,
        .rows_per_image = 0,
        .offset = 0,
    };
    const temp_texture = try resources.getOrCreateTexture(
        self,
        temp_resource,
        types.WGPUTextureUsage_RenderAttachment | types.WGPUTextureUsage_CopySrc | types.WGPUTextureUsage_CopyDst,
    );
    const temp_view = render_resource_mod.getOrCreateCachedRenderTextureView(
        self,
        &self.full.render_target_view_cache,
        temp_handle,
        temp_texture,
        render.target_width,
        render.target_height,
        target_format,
        types.WGPUTextureUsage_RenderAttachment,
    ) catch {
        return error.TempRenderTextureViewFailed;
    };
    return .{ .view = temp_view, .needs_copy_back = true };
}

/// Copies the temp render texture back to the original target texture after
/// the render pass. The copy goes from mip 0 of the temp texture to the
/// original mip level of the target.
pub fn copyBackTempRenderTexture(
    self: *Backend,
    procs: anytype,
    encoder: anytype,
    render: model.RenderDrawCommand,
    target_texture: types.WGPUTexture,
    target_resource: model.CopyTextureResource,
) !void {
    const temp_handle = render.target_handle +% rc.TEMP_RENDER_TEXTURE_OFFSET;
    const temp_resource_src = model.CopyTextureResource{
        .handle = temp_handle,
        .kind = .texture,
        .width = render.target_width,
        .height = render.target_height,
        .depth_or_array_layers = 1,
        .format = render.target_format,
        .usage = types.WGPUTextureUsage_CopySrc,
        .dimension = model.WGPUTextureDimension_2D,
        .view_dimension = model.WGPUTextureViewDimension_2D,
        .mip_level = 0,
        .sample_count = 1,
        .aspect = model.WGPUTextureAspect_All,
        .bytes_per_row = 0,
        .rows_per_image = 0,
        .offset = 0,
    };
    const temp_src = try resources.getOrCreateTexture(self, temp_resource_src, types.WGPUTextureUsage_CopySrc);
    const copy_extent = types.WGPUExtent3D{
        .width = render.target_width,
        .height = render.target_height,
        .depthOrArrayLayers = 1,
    };
    procs.wgpuCommandEncoderCopyTextureToTexture(
        encoder,
        &types.WGPUTexelCopyTextureInfo{
            .texture = temp_src,
            .mipLevel = 0,
            .origin = .{ .x = 0, .y = 0, .z = 0 },
            .aspect = loader.normalizeTextureAspect(model.WGPUTextureAspect_All),
        },
        &types.WGPUTexelCopyTextureInfo{
            .texture = target_texture,
            .mipLevel = target_resource.mip_level,
            .origin = .{ .x = 0, .y = 0, .z = 0 },
            .aspect = loader.normalizeTextureAspect(model.WGPUTextureAspect_All),
        },
        &copy_extent,
    );
}

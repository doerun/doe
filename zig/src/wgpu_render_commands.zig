const std = @import("std");
const model = @import("model.zig");
const types = @import("wgpu_types.zig");
const loader = @import("wgpu_loader.zig");
const resources = @import("wgpu_resources.zig");
const async_procs_mod = @import("wgpu_async_procs.zig");
const render_assets = @import("wgpu_render_assets.zig");
const render_api_mod = @import("wgpu_render_api.zig");
const render_indexing = @import("wgpu_render_indexing.zig");
const render_p0_mod = @import("wgpu_render_p0.zig");
const render_resource_mod = @import("wgpu_render_resources.zig");
const render_types_mod = @import("wgpu_render_types.zig");
const ffi = @import("webgpu_ffi.zig");
const Backend = ffi.WebGPUBackend;

const RENDER_LOAD_OP_CLEAR: u32 = 0x00000002;
const RENDER_STORE_OP_STORE: u32 = 0x00000001;
const RENDER_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST: u32 = 0x00000004;
const RENDER_FRONT_FACE_CCW: u32 = 0x00000001;
const RENDER_CULL_MODE_NONE: u32 = 0x00000001;
const RENDER_COLOR_WRITE_MASK_ALL: u64 = 0x000000000000000F;
const RENDER_TARGET_DEPTH_SLICE_UNDEFINED: u32 = std.math.maxInt(u32);
const RENDER_MULTISAMPLE_MASK_ALL: u32 = 0xFFFF_FFFF;
const RENDER_DEPTH_STENCIL_FORMAT: types.WGPUTextureFormat = model.WGPUTextureFormat_Depth24PlusStencil8;
const RENDER_DEPTH_STENCIL_CLEAR_VALUE: f32 = 1.0;
const RENDER_STENCIL_CLEAR_VALUE: u32 = 0;
const RENDER_COMPARE_FUNCTION_ALWAYS: u32 = 0x00000008;
const RENDER_STENCIL_OPERATION_KEEP: u32 = 0x00000001;
const RENDER_OPTIONAL_BOOL_FALSE: u32 = 0x00000000;
const RENDER_STENCIL_MASK_DEFAULT: u32 = 0x000000FF;
const RENDER_DEPTH_ATTACHMENT_HANDLE_MASK: u64 = 0x8C9F_2400_0000_0000;
const RENDER_VERTEX_BUFFER_HANDLE: u64 = 0x8C9F_2500_0000_0000;
const RENDER_MULTI_DRAW_INDIRECT_BUFFER_HANDLE: u64 = 0x8C9F_2A00_0000_0000;
const RENDER_VERTEX_FORMAT_FLOAT32X4: u32 = 0x0000001F;
const RENDER_VERTEX_STEP_MODE_VERTEX: u32 = 0x00000001;
const RENDER_VERTEX_STRIDE_BYTES: u64 = 4 * @sizeOf(f32);
const RENDER_UNIFORM_BINDING_INDEX: u32 = render_resource_mod.RENDER_UNIFORM_BINDING_INDEX;
const RENDER_UNIFORM_DYNAMIC_STRIDE_BYTES: u64 = render_resource_mod.RENDER_UNIFORM_DYNAMIC_STRIDE_BYTES;
const RENDER_UNIFORM_MIN_BINDING_SIZE_BYTES: u64 = render_resource_mod.RENDER_UNIFORM_MIN_BINDING_SIZE_BYTES;
const RENDER_UNIFORM_TOTAL_BYTES: u64 = render_resource_mod.RENDER_UNIFORM_TOTAL_BYTES;

const RenderColor = render_types_mod.RenderColor;
const RenderBundleDescriptor = render_types_mod.RenderBundleDescriptor;
const RenderBundleEncoderDescriptor = render_types_mod.RenderBundleEncoderDescriptor;
const RenderPassColorAttachment = render_types_mod.RenderPassColorAttachment;
const RenderPassDescriptor = render_types_mod.RenderPassDescriptor;
const RenderPassDepthStencilAttachment = render_types_mod.RenderPassDepthStencilAttachment;
const RenderVertexAttribute = render_types_mod.RenderVertexAttribute;
const RenderVertexBufferLayout = render_types_mod.RenderVertexBufferLayout;
const RenderColorTargetState = render_types_mod.RenderColorTargetState;
const RenderFragmentState = render_types_mod.RenderFragmentState;
const RenderStencilFaceState = render_types_mod.RenderStencilFaceState;
const RenderDepthStencilState = render_types_mod.RenderDepthStencilState;
const RenderPipelineDescriptor = render_types_mod.RenderPipelineDescriptor;
const RenderUniformBindingResources = render_resource_mod.RenderUniformBindingResources;
pub fn executeRenderDraw(self: *Backend, render: model.RenderDrawCommand) !types.NativeExecutionResult {
    if (render.draw_count == 0) {
        return .{ .status = .unsupported, .status_message = "render_draw draw_count must be > 0" };
    }
    if (render.vertex_count == 0) {
        return .{ .status = .unsupported, .status_message = "render_draw vertex_count must be > 0" };
    }
    if (render.instance_count == 0) {
        return .{ .status = .unsupported, .status_message = "render_draw instance_count must be > 0" };
    }
    if (render.target_width == 0 or render.target_height == 0) {
        return .{ .status = .unsupported, .status_message = "render_draw target dimensions must be > 0" };
    }
    if (render.index_count != null and render.index_count.? == 0) {
        return .{ .status = .unsupported, .status_message = "render_draw index_count must be > 0 when provided" };
    }

    const procs = self.procs orelse return error.ProceduralNotReady;
    const render_api = render_api_mod.loadRenderApi(procs, self.dyn_lib) orelse {
        return .{ .status = .unsupported, .status_message = "render_draw requires full render api surface" };
    };

    const setup_start_ns = std.time.nanoTimestamp();
    const target_resource = model.CopyTextureResource{
        .handle = render.target_handle,
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
    const target_texture = try resources.getOrCreateTexture(
        self,
        target_resource,
        types.WGPUTextureUsage_RenderAttachment | types.WGPUTextureUsage_CopySrc | types.WGPUTextureUsage_CopyDst,
    );
    const render_vertex_bytes = std.mem.sliceAsBytes(render_assets.RENDER_DRAW_VERTEX_DATA[0..]);
    const render_vertex_usage = types.WGPUBufferUsage_Vertex | types.WGPUBufferUsage_CopyDst;
    const render_vertex_bytes_u64 = @as(u64, @intCast(render_vertex_bytes.len));
    const should_upload_vertex_data = blk: {
        if (self.buffers.get(RENDER_VERTEX_BUFFER_HANDLE)) |existing| {
            if (existing.size >= render_vertex_bytes_u64 and
                (existing.usage & render_vertex_usage) == render_vertex_usage)
            {
                break :blk false;
            }
        }
        break :blk true;
    };
    const render_vertex_buffer = try resources.getOrCreateBuffer(
        self,
        RENDER_VERTEX_BUFFER_HANDLE,
        render_vertex_bytes_u64,
        render_vertex_usage,
    );
    if (should_upload_vertex_data) {
        procs.wgpuQueueWriteBuffer(
            self.queue.?,
            render_vertex_buffer,
            0,
            render_vertex_bytes.ptr,
            render_vertex_bytes.len,
        );
    }
    const prepared_index = render_indexing.prepareIndexBuffer(self, render) catch |err| {
        return .{
            .status = if (err == error.InvalidIndexedDrawData) .unsupported else .@"error",
            .status_message = switch (err) {
                error.InvalidIndexedDrawData => "render_draw indexed mode requires valid index_data and bounds",
                else => "render_draw index buffer setup failed",
            },
        };
    };
    const indexed_draw = prepared_index != null;
    const viewport_width = render.viewport_width orelse @as(f32, @floatFromInt(render.target_width));
    const viewport_height = render.viewport_height orelse @as(f32, @floatFromInt(render.target_height));
    if (viewport_width <= 0 or viewport_height <= 0) {
        return .{ .status = .unsupported, .status_message = "render_draw viewport dimensions must be > 0" };
    }
    const scissor_width = render.scissor_width orelse render.target_width;
    const scissor_height = render.scissor_height orelse render.target_height;
    if (scissor_width == 0 or scissor_height == 0) {
        return .{ .status = .unsupported, .status_message = "render_draw scissor dimensions must be > 0" };
    }
    const requested_dynamic_offsets = render.bind_group_dynamic_offsets orelse &[_]u32{};
    if (requested_dynamic_offsets.len > 1) {
        return .{ .status = .unsupported, .status_message = "render_draw supports exactly one dynamic bind-group offset" };
    }
    var dynamic_offsets = [_]u32{0};
    if (requested_dynamic_offsets.len == 1) {
        dynamic_offsets[0] = requested_dynamic_offsets[0];
    }
    if (dynamic_offsets[0] % @as(u32, @intCast(RENDER_UNIFORM_DYNAMIC_STRIDE_BYTES)) != 0) {
        return .{ .status = .unsupported, .status_message = "render_draw dynamic offset must align to uniform stride" };
    }
    if (@as(u64, dynamic_offsets[0]) + RENDER_UNIFORM_MIN_BINDING_SIZE_BYTES > RENDER_UNIFORM_TOTAL_BYTES) {
        return .{ .status = .unsupported, .status_message = "render_draw dynamic offset exceeds uniform buffer bounds" };
    }

    const normalized_target_format = resources.normalizeTextureFormat(render.target_format);
    const target_format = if (normalized_target_format == types.WGPUTextureFormat_Undefined)
        model.WGPUTextureFormat_RGBA8Unorm
    else
        normalized_target_format;
    const depth_handle = render.target_handle ^ RENDER_DEPTH_ATTACHMENT_HANDLE_MASK;
    const depth_resource = model.CopyTextureResource{
        .handle = depth_handle,
        .kind = .texture,
        .width = render.target_width,
        .height = render.target_height,
        .depth_or_array_layers = 1,
        .format = RENDER_DEPTH_STENCIL_FORMAT,
        .usage = types.WGPUTextureUsage_RenderAttachment,
        .dimension = model.WGPUTextureDimension_2D,
        .view_dimension = model.WGPUTextureViewDimension_2D,
        .mip_level = 0,
        .sample_count = 1,
        .aspect = model.WGPUTextureAspect_All,
        .bytes_per_row = 0,
        .rows_per_image = 0,
        .offset = 0,
    };
    const depth_texture = try resources.getOrCreateTexture(
        self,
        depth_resource,
        types.WGPUTextureUsage_RenderAttachment,
    );
    const target_view = render_resource_mod.getOrCreateCachedRenderTextureView(
        self,
        &self.render_target_view_cache,
        render.target_handle,
        target_texture,
        render.target_width,
        render.target_height,
        target_format,
        types.WGPUTextureUsage_RenderAttachment,
    ) catch |err| {
        return .{
            .status = .@"error",
            .status_message = switch (err) {
                error.ProceduralNotReady => "backend not ready",
                error.TextureViewCreationFailed => "render_draw texture view creation failed",
                error.TextureViewCacheInsertFailed => "render_draw texture view cache insert failed",
            },
        };
    };
    const depth_view = render_resource_mod.getOrCreateCachedRenderTextureView(
        self,
        &self.render_depth_view_cache,
        depth_handle,
        depth_texture,
        render.target_width,
        render.target_height,
        RENDER_DEPTH_STENCIL_FORMAT,
        types.WGPUTextureUsage_RenderAttachment,
    ) catch |err| {
        return .{
            .status = .@"error",
            .status_message = switch (err) {
                error.ProceduralNotReady => "backend not ready",
                error.TextureViewCreationFailed => "render_draw depth view creation failed",
                error.TextureViewCacheInsertFailed => "render_draw depth view cache insert failed",
            },
        };
    };
    const render_uniform_resources = render_resource_mod.getOrCreateRenderUniformBindingResources(self) catch |err| {
        return .{
            .status = .@"error",
            .status_message = switch (err) {
                error.ProceduralNotReady => "backend not ready",
                error.BufferAllocationFailed => "render_draw uniform buffer allocation failed",
                error.BindGroupLayoutCreationFailed => "render_draw uniform bind group layout creation failed",
                error.BindGroupCreationFailed => "render_draw uniform bind group creation failed",
                error.TextureProcUnavailable => "render_draw texture proc surface unavailable",
                error.SamplerCreationFailed => "render_draw sampler creation failed",
                else => "render_draw uniform setup failed",
            },
        };
    };

    const render_pipeline = if (self.render_pipeline_cache.get(target_format)) |cached|
        cached.pipeline
    else blk: {
        const shader_module = resources.createShaderModule(self, render_assets.RENDER_DRAW_SHADER_SOURCE) catch |err| {
            return .{
                .status = .@"error",
                .status_message = switch (err) {
                    error.KernelModuleCreationFailed => "render_draw shader module creation failed",
                    error.ProceduralNotReady => "backend not ready",
                },
            };
        };

        var color_target = RenderColorTargetState{
            .nextInChain = null,
            .format = target_format,
            .blend = null,
            .writeMask = RENDER_COLOR_WRITE_MASK_ALL,
        };
        const vertex_attribute = RenderVertexAttribute{
            .nextInChain = null,
            .format = RENDER_VERTEX_FORMAT_FLOAT32X4,
            .offset = 0,
            .shaderLocation = 0,
        };
        const vertex_buffer_layout = RenderVertexBufferLayout{
            .nextInChain = null,
            .stepMode = RENDER_VERTEX_STEP_MODE_VERTEX,
            .arrayStride = RENDER_VERTEX_STRIDE_BYTES,
            .attributeCount = 1,
            .attributes = @ptrCast(&vertex_attribute),
        };
        var fragment_state = RenderFragmentState{
            .nextInChain = null,
            .module = shader_module,
            .entryPoint = loader.stringView("fs_main"),
            .constantCount = 0,
            .constants = null,
            .targetCount = 1,
            .targets = @ptrCast(&color_target),
        };
        const stencil_face_state = RenderStencilFaceState{
            .compare = RENDER_COMPARE_FUNCTION_ALWAYS,
            .failOp = RENDER_STENCIL_OPERATION_KEEP,
            .depthFailOp = RENDER_STENCIL_OPERATION_KEEP,
            .passOp = RENDER_STENCIL_OPERATION_KEEP,
        };
        const depth_stencil_state = RenderDepthStencilState{
            .nextInChain = null,
            .format = RENDER_DEPTH_STENCIL_FORMAT,
            .depthWriteEnabled = RENDER_OPTIONAL_BOOL_FALSE,
            .depthCompare = RENDER_COMPARE_FUNCTION_ALWAYS,
            .stencilFront = stencil_face_state,
            .stencilBack = stencil_face_state,
            .stencilReadMask = RENDER_STENCIL_MASK_DEFAULT,
            .stencilWriteMask = RENDER_STENCIL_MASK_DEFAULT,
            .depthBias = 0,
            .depthBiasSlopeScale = 0,
            .depthBiasClamp = 0,
        };
        const render_pipeline_layout = resources.createPipelineLayout(
            self,
            &[_]types.WGPUBindGroupLayout{render_uniform_resources.bind_group_layout},
        ) catch {
            procs.wgpuShaderModuleRelease(shader_module);
            return .{ .status = .@"error", .status_message = "render_draw pipeline layout creation failed" };
        };
        defer procs.wgpuPipelineLayoutRelease(render_pipeline_layout);
        const async_procs = async_procs_mod.loadAsyncProcs(self.dyn_lib) orelse {
            procs.wgpuShaderModuleRelease(shader_module);
            return .{ .status = .unsupported, .status_message = "render_draw requires async diagnostics api surface" };
        };

        const compilation_state = async_procs_mod.requestShaderCompilationInfoAndWait(
            async_procs,
            self.instance.?,
            procs,
            shader_module,
        ) catch {
            procs.wgpuShaderModuleRelease(shader_module);
            return .{ .status = .@"error", .status_message = "render_draw shader compilation info request failed" };
        };
        if (compilation_state.status != async_procs_mod.COMPILATION_INFO_STATUS_SUCCESS) {
            procs.wgpuShaderModuleRelease(shader_module);
            return .{ .status = .@"error", .status_message = "render_draw shader compilation info status not successful" };
        }

        async_procs_mod.pushErrorScope(async_procs, self.device.?, async_procs_mod.ERROR_FILTER_VALIDATION);
        async_procs_mod.pushErrorScope(async_procs, self.device.?, async_procs_mod.ERROR_FILTER_INTERNAL);
        async_procs_mod.pushErrorScope(async_procs, self.device.?, async_procs_mod.ERROR_FILTER_OUT_OF_MEMORY);

        const pipeline_desc = RenderPipelineDescriptor{
            .nextInChain = null,
            .label = loader.stringView("fawn.render_draw"),
            .layout = render_pipeline_layout,
            .vertex = .{
                .nextInChain = null,
                .module = shader_module,
                .entryPoint = loader.stringView("vs_main"),
                .constantCount = 0,
                .constants = null,
                .bufferCount = 1,
                .buffers = @ptrCast(&vertex_buffer_layout),
            },
            .primitive = .{
                .nextInChain = null,
                .topology = RENDER_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST,
                .stripIndexFormat = 0,
                .frontFace = RENDER_FRONT_FACE_CCW,
                .cullMode = RENDER_CULL_MODE_NONE,
                .unclippedDepth = types.WGPU_FALSE,
            },
            .depthStencil = &depth_stencil_state,
            .multisample = .{
                .nextInChain = null,
                .count = 1,
                .mask = RENDER_MULTISAMPLE_MASK_ALL,
                .alphaToCoverageEnabled = types.WGPU_FALSE,
            },
            .fragment = &fragment_state,
        };
        const pipeline = async_procs_mod.createRenderPipelineAsyncAndWait(
            async_procs,
            self.instance.?,
            procs,
            self.device.?,
            @ptrCast(&pipeline_desc),
        ) catch {
            _ = async_procs_mod.popErrorScopeAndWait(async_procs, self.instance.?, procs, self.device.?) catch {};
            _ = async_procs_mod.popErrorScopeAndWait(async_procs, self.instance.?, procs, self.device.?) catch {};
            _ = async_procs_mod.popErrorScopeAndWait(async_procs, self.instance.?, procs, self.device.?) catch {};
            procs.wgpuShaderModuleRelease(shader_module);
            return .{ .status = .@"error", .status_message = "render_draw async pipeline creation failed" };
        };

        const out_of_memory_scope = async_procs_mod.popErrorScopeAndWait(async_procs, self.instance.?, procs, self.device.?) catch {
            render_api.render_pipeline_release(pipeline);
            procs.wgpuShaderModuleRelease(shader_module);
            return .{ .status = .@"error", .status_message = "render_draw out-of-memory scope pop failed" };
        };
        const internal_scope = async_procs_mod.popErrorScopeAndWait(async_procs, self.instance.?, procs, self.device.?) catch {
            render_api.render_pipeline_release(pipeline);
            procs.wgpuShaderModuleRelease(shader_module);
            return .{ .status = .@"error", .status_message = "render_draw internal scope pop failed" };
        };
        const validation_scope = async_procs_mod.popErrorScopeAndWait(async_procs, self.instance.?, procs, self.device.?) catch {
            render_api.render_pipeline_release(pipeline);
            procs.wgpuShaderModuleRelease(shader_module);
            return .{ .status = .@"error", .status_message = "render_draw validation scope pop failed" };
        };
        const no_error = @as(u32, @intFromEnum(types.WGPUErrorType.noError));
        if (out_of_memory_scope.status != async_procs_mod.POP_ERROR_SCOPE_STATUS_SUCCESS or
            internal_scope.status != async_procs_mod.POP_ERROR_SCOPE_STATUS_SUCCESS or
            validation_scope.status != async_procs_mod.POP_ERROR_SCOPE_STATUS_SUCCESS or
            out_of_memory_scope.error_type != no_error or
            internal_scope.error_type != no_error or
            validation_scope.error_type != no_error)
        {
            render_api.render_pipeline_release(pipeline);
            procs.wgpuShaderModuleRelease(shader_module);
            return .{ .status = .@"error", .status_message = "render_draw error-scope validation failed" };
        }

        self.render_pipeline_cache.put(target_format, .{
            .shader_module = shader_module,
            .pipeline = pipeline,
        }) catch {
            render_api.render_pipeline_release(pipeline);
            procs.wgpuShaderModuleRelease(shader_module);
            return .{ .status = .@"error", .status_message = "render_draw pipeline cache insert failed" };
        };
        break :blk pipeline;
    };
    const p0_state = render_p0_mod.prepare(self, procs, render_api, indexed_draw, RENDER_MULTI_DRAW_INDIRECT_BUFFER_HANDLE);
    defer render_p0_mod.deinit(p0_state, procs);
    const command_encoder_write_buffer = p0_state.command_encoder_write_buffer;
    const occlusion_query_set = p0_state.occlusion_query_set;
    const render_indirect_buffer = p0_state.indirect_buffer;
    var prepared_render_bundle: render_api_mod.RenderBundle = null;
    defer if (prepared_render_bundle != null) {
        render_api.render_bundle_release(prepared_render_bundle);
    };
    if (render.encode_mode != .render_pass) {
        const bundle_color_formats = [_]types.WGPUTextureFormat{target_format};
        const render_bundle_encoder = render_api.device_create_render_bundle_encoder(
            self.device.?,
            &RenderBundleEncoderDescriptor{
                .nextInChain = null,
                .label = loader.stringView("fawn.render_bundle_encoder"),
                .colorFormatCount = 1,
                .colorFormats = bundle_color_formats[0..].ptr,
                .depthStencilFormat = RENDER_DEPTH_STENCIL_FORMAT,
                .sampleCount = 1,
                .depthReadOnly = types.WGPU_FALSE,
                .stencilReadOnly = types.WGPU_FALSE,
            },
        );
        if (render_bundle_encoder == null) {
            return .{ .status = .@"error", .status_message = "render_draw bundle encoder creation failed" };
        }
        defer render_api.render_bundle_encoder_release(render_bundle_encoder);

        if (render.pipeline_mode == .static) {
            render_api.render_bundle_encoder_set_pipeline(render_bundle_encoder, render_pipeline);
        }
        render_api.render_bundle_encoder_set_vertex_buffer(
            render_bundle_encoder,
            0,
            render_vertex_buffer,
            0,
            types.WGPU_WHOLE_SIZE,
        );
        if (indexed_draw) {
            render_api.render_bundle_encoder_set_index_buffer(
                render_bundle_encoder,
                prepared_index.?.buffer,
                prepared_index.?.format,
                0,
                types.WGPU_WHOLE_SIZE,
            );
        }
        if (render.bind_group_mode == .no_change) {
            render_api.render_bundle_encoder_set_bind_group(render_bundle_encoder, RENDER_UNIFORM_BINDING_INDEX, render_uniform_resources.bind_group, dynamic_offsets.len, dynamic_offsets[0..].ptr);
        }

        var bundle_draw_index: u32 = 0;
        if (indexed_draw) {
            while (bundle_draw_index < render.draw_count) : (bundle_draw_index += 1) {
                if (render.pipeline_mode == .redundant) {
                    render_api.render_bundle_encoder_set_pipeline(render_bundle_encoder, render_pipeline);
                }
                if (render.bind_group_mode == .redundant) {
                    render_api.render_bundle_encoder_set_bind_group(render_bundle_encoder, RENDER_UNIFORM_BINDING_INDEX, render_uniform_resources.bind_group, dynamic_offsets.len, dynamic_offsets[0..].ptr);
                }
                render_api.render_bundle_encoder_draw_indexed(
                    render_bundle_encoder,
                    render.index_count.?,
                    render.instance_count,
                    render.first_index,
                    render.base_vertex,
                    render.first_instance,
                );
            }
        } else {
            if (render.pipeline_mode != .redundant and render.bind_group_mode == .redundant) {
                while (bundle_draw_index < render.draw_count) : (bundle_draw_index += 1) {
                    render_api.render_bundle_encoder_set_bind_group(render_bundle_encoder, RENDER_UNIFORM_BINDING_INDEX, render_uniform_resources.bind_group, dynamic_offsets.len, dynamic_offsets[0..].ptr);
                    render_api.render_bundle_encoder_draw(
                        render_bundle_encoder,
                        render.vertex_count,
                        render.instance_count,
                        render.first_vertex,
                        render.first_instance,
                    );
                }
            } else {
                while (bundle_draw_index < render.draw_count) : (bundle_draw_index += 1) {
                    if (render.pipeline_mode == .redundant) {
                        render_api.render_bundle_encoder_set_pipeline(render_bundle_encoder, render_pipeline);
                    }
                    if (render.bind_group_mode == .redundant) {
                        render_api.render_bundle_encoder_set_bind_group(render_bundle_encoder, RENDER_UNIFORM_BINDING_INDEX, render_uniform_resources.bind_group, dynamic_offsets.len, dynamic_offsets[0..].ptr);
                    }
                    render_api.render_bundle_encoder_draw(
                        render_bundle_encoder,
                        render.vertex_count,
                        render.instance_count,
                        render.first_vertex,
                        render.first_instance,
                    );
                }
            }
        }

        prepared_render_bundle = render_api.render_bundle_encoder_finish(
            render_bundle_encoder,
            &RenderBundleDescriptor{
                .nextInChain = null,
                .label = loader.stringView("fawn.render_bundle"),
            },
        );
        if (prepared_render_bundle == null) {
            return .{ .status = .@"error", .status_message = "render_draw bundle finish failed" };
        }
    }
    const setup_end_ns = std.time.nanoTimestamp();

    const encode_start_ns = std.time.nanoTimestamp();
    const encoder = procs.wgpuDeviceCreateCommandEncoder(self.device.?, &types.WGPUCommandEncoderDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
    });
    if (encoder == null) {
        return .{ .status = .@"error", .status_message = "deviceCreateCommandEncoder returned null" };
    }
    defer procs.wgpuCommandEncoderRelease(encoder);
    const use_multi_draw_indexed = render.encode_mode == .render_pass and
        indexed_draw and
        render.pipeline_mode == .static and
        render.bind_group_mode == .no_change and
        render_indirect_buffer != null and
        command_encoder_write_buffer != null and
        render_api.render_pass_encoder_multi_draw_indexed_indirect != null;
    const use_multi_draw = render.encode_mode == .render_pass and
        !indexed_draw and
        render.pipeline_mode == .static and
        render.bind_group_mode == .no_change and
        render_indirect_buffer != null and
        command_encoder_write_buffer != null and
        render_api.render_pass_encoder_multi_draw_indirect != null;
    if (use_multi_draw_indexed) {
        const draw_args = render_types_mod.RenderDrawIndexedIndirectArgs{
            .index_count = render.index_count.?,
            .instance_count = render.instance_count,
            .first_index = render.first_index,
            .base_vertex = render.base_vertex,
            .first_instance = render.first_instance,
        };
        const draw_args_bytes = std.mem.asBytes(&draw_args);
        command_encoder_write_buffer.?(encoder, render_indirect_buffer, 0, draw_args_bytes.ptr, @as(u64, draw_args_bytes.len));
    } else if (use_multi_draw) {
        const draw_args = render_types_mod.RenderDrawIndirectArgs{
            .vertex_count = render.vertex_count,
            .instance_count = render.instance_count,
            .first_vertex = render.first_vertex,
            .first_instance = render.first_instance,
        };
        const draw_args_bytes = std.mem.asBytes(&draw_args);
        command_encoder_write_buffer.?(encoder, render_indirect_buffer, 0, draw_args_bytes.ptr, @as(u64, draw_args_bytes.len));
    }

    var color_attachment = RenderPassColorAttachment{
        .nextInChain = null,
        .view = target_view,
        .depthSlice = RENDER_TARGET_DEPTH_SLICE_UNDEFINED,
        .resolveTarget = null,
        .loadOp = RENDER_LOAD_OP_CLEAR,
        .storeOp = RENDER_STORE_OP_STORE,
        .clearValue = .{ .r = 0, .g = 0, .b = 0, .a = 1 },
    };
    const depth_stencil_attachment = RenderPassDepthStencilAttachment{
        .nextInChain = null,
        .view = depth_view,
        .depthLoadOp = RENDER_LOAD_OP_CLEAR,
        .depthStoreOp = RENDER_STORE_OP_STORE,
        .depthClearValue = RENDER_DEPTH_STENCIL_CLEAR_VALUE,
        .depthReadOnly = types.WGPU_FALSE,
        .stencilLoadOp = RENDER_LOAD_OP_CLEAR,
        .stencilStoreOp = RENDER_STORE_OP_STORE,
        .stencilClearValue = RENDER_STENCIL_CLEAR_VALUE,
        .stencilReadOnly = types.WGPU_FALSE,
    };
    const render_pass = render_api.command_encoder_begin_render_pass(encoder, &RenderPassDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
        .colorAttachmentCount = 1,
        .colorAttachments = @ptrCast(&color_attachment),
        .depthStencilAttachment = &depth_stencil_attachment,
        .occlusionQuerySet = occlusion_query_set,
        .timestampWrites = null,
    });
    if (render_pass == null) {
        return .{ .status = .@"error", .status_message = "render_draw begin render pass failed" };
    }
    defer render_api.render_pass_encoder_release(render_pass);
    render_p0_mod.beginPass(p0_state, render_api, render_pass);

    render_api.render_pass_encoder_set_viewport(
        render_pass,
        render.viewport_x,
        render.viewport_y,
        viewport_width,
        viewport_height,
        render.viewport_min_depth,
        render.viewport_max_depth,
    );
    render_api.render_pass_encoder_set_scissor_rect(
        render_pass,
        render.scissor_x,
        render.scissor_y,
        scissor_width,
        scissor_height,
    );
    const blend_constant = RenderColor{
        .r = render.blend_constant[0],
        .g = render.blend_constant[1],
        .b = render.blend_constant[2],
        .a = render.blend_constant[3],
    };
    render_api.render_pass_encoder_set_blend_constant(render_pass, &blend_constant);
    render_api.render_pass_encoder_set_stencil_reference(render_pass, render.stencil_reference);
    render_api.render_pass_encoder_set_vertex_buffer(
        render_pass,
        0,
        render_vertex_buffer,
        0,
        types.WGPU_WHOLE_SIZE,
    );
    if (indexed_draw) {
        render_api.render_pass_encoder_set_index_buffer(
            render_pass,
            prepared_index.?.buffer,
            prepared_index.?.format,
            0,
            types.WGPU_WHOLE_SIZE,
        );
    }
    if (render.encode_mode == .render_pass and render.pipeline_mode == .static) {
        render_api.render_pass_encoder_set_pipeline(render_pass, render_pipeline);
    }
    if (render.encode_mode == .render_pass and render.bind_group_mode == .no_change) {
        render_api.render_pass_encoder_set_bind_group(render_pass, RENDER_UNIFORM_BINDING_INDEX, render_uniform_resources.bind_group, dynamic_offsets.len, dynamic_offsets[0..].ptr);
    }

    if (render.encode_mode == .render_pass) {
        var draw_index: u32 = 0;
        if (indexed_draw) {
            if (use_multi_draw_indexed) {
                render_api.render_pass_encoder_multi_draw_indexed_indirect.?(
                    render_pass,
                    render_indirect_buffer,
                    0,
                    render.draw_count,
                    null,
                    0,
                );
            } else {
                while (draw_index < render.draw_count) : (draw_index += 1) {
                    if (render.pipeline_mode == .redundant) {
                        render_api.render_pass_encoder_set_pipeline(render_pass, render_pipeline);
                    }
                    if (render.bind_group_mode == .redundant) {
                        render_api.render_pass_encoder_set_bind_group(render_pass, RENDER_UNIFORM_BINDING_INDEX, render_uniform_resources.bind_group, dynamic_offsets.len, dynamic_offsets[0..].ptr);
                    }
                    render_api.render_pass_encoder_draw_indexed(
                        render_pass,
                        render.index_count.?,
                        render.instance_count,
                        render.first_index,
                        render.base_vertex,
                        render.first_instance,
                    );
                }
            }
        } else {
            if (use_multi_draw) {
                render_api.render_pass_encoder_multi_draw_indirect.?(
                    render_pass,
                    render_indirect_buffer,
                    0,
                    render.draw_count,
                    null,
                    0,
                );
            } else {
                while (draw_index < render.draw_count) : (draw_index += 1) {
                    if (render.pipeline_mode == .redundant) {
                        render_api.render_pass_encoder_set_pipeline(render_pass, render_pipeline);
                    }
                    if (render.bind_group_mode == .redundant) {
                        render_api.render_pass_encoder_set_bind_group(render_pass, RENDER_UNIFORM_BINDING_INDEX, render_uniform_resources.bind_group, dynamic_offsets.len, dynamic_offsets[0..].ptr);
                    }
                    render_api.render_pass_encoder_draw(
                        render_pass,
                        render.vertex_count,
                        render.instance_count,
                        render.first_vertex,
                        render.first_instance,
                    );
                }
            }
        }
    } else {
        if (prepared_render_bundle == null) {
            return .{ .status = .@"error", .status_message = "render_draw bundle setup missing prepared bundle" };
        }
        var bundles = [_]render_api_mod.RenderBundle{prepared_render_bundle};
        render_api.render_pass_encoder_execute_bundles(render_pass, bundles.len, bundles[0..].ptr);
    }
    render_p0_mod.endPass(p0_state, render_api, render_pass);
    render_api.render_pass_encoder_end(render_pass);

    const command_buffer = procs.wgpuCommandEncoderFinish(encoder, &types.WGPUCommandBufferDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
    });
    if (command_buffer == null) {
        return .{ .status = .@"error", .status_message = "commandEncoderFinish returned null" };
    }
    defer procs.wgpuCommandBufferRelease(command_buffer);
    const encode_end_ns = std.time.nanoTimestamp();

    var commands = [_]types.WGPUCommandBuffer{command_buffer};
    const submit_wait_start_ns = std.time.nanoTimestamp();
    procs.wgpuQueueSubmit(self.queue.?, commands.len, commands[0..].ptr);
    try self.syncAfterSubmit();
    const submit_wait_end_ns = std.time.nanoTimestamp();

    const setup_ns = if (setup_end_ns > setup_start_ns)
        @as(u64, @intCast(setup_end_ns - setup_start_ns))
    else
        0;
    const encode_ns = if (encode_end_ns > encode_start_ns)
        @as(u64, @intCast(encode_end_ns - encode_start_ns))
    else
        0;
    const submit_wait_ns = if (submit_wait_end_ns > submit_wait_start_ns)
        @as(u64, @intCast(submit_wait_end_ns - submit_wait_start_ns))
    else
        0;

    return .{
        .status = .ok,
        .status_message = "render_draw command submitted",
        .setup_ns = setup_ns,
        .encode_ns = encode_ns,
        .submit_wait_ns = submit_wait_ns,
        .dispatch_count = render.draw_count,
        .gpu_timestamp_ns = 0,
    };
}

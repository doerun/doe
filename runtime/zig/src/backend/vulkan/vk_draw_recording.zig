const std = @import("std");
const c = @import("vk_constants.zig");
const resources = @import("vk_resources.zig");
const model_render_types = @import("../../contracts/model/model_render_types.zig");
const model_gpu_types = @import("../../contracts/model/model_texture_value_types.zig");
const VK_NULL_U64 = c.VK_NULL_U64;
const VK_QUERY_CONTROL_NONE: u32 = 0;

pub const IndexBinding = struct {
    buffer: c.VkBuffer,
    offset: u64,
    format: u32,
    count: u32,
};

/// Borrows native handles and a read-only buffer registry only for recording.
/// Its caller owns allocation, image transitions, submission and retirement.
pub const DrawRecording = struct {
    command_buffer: c.VkCommandBuffer,
    buffers: *const std.AutoHashMapUnmanaged(u64, resources.ComputeBuffer),
    render_pass: c.VkRenderPass,
    framebuffer: c.VkFramebuffer,
    pipeline: c.VkPipeline,
    pipeline_layout: c.VkPipelineLayout,
    descriptor_set: c.VkDescriptorSet,
    has_depth_stencil: bool,

    fn resolve_buffer(self: *const DrawRecording, raw: ?*anyopaque) ?c.VkBuffer {
        const handle = raw orelse return null;
        const buffer = self.buffers.get(@intFromPtr(handle)) orelse return null;
        return buffer.buffer;
    }

    pub fn record(self: *const DrawRecording, cmd: model_render_types.RenderDrawCommand, index: ?IndexBinding, draw_count: u32, target_width: u32, target_height: u32) error{InvalidArgument}!void {
        var clear_values = [_]c.VkClearValue{
            .{
                .color = .{ .float32 = cmd.clear_color },
            },
            .{
                .depthStencil = .{ .depth = cmd.depth_clear_value, .stencil = cmd.stencil_clear_value },
            },
        };
        var render_pass_begin = c.VkRenderPassBeginInfo{
            .sType = c.VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO,
            .pNext = null,
            .renderPass = self.render_pass,
            .framebuffer = self.framebuffer,
            .renderArea = .{
                .offset = .{ .x = 0, .y = 0 },
                .extent = .{ .width = target_width, .height = target_height },
            },
            .clearValueCount = if (self.has_depth_stencil) 2 else 1,
            .pClearValues = clear_values[0..if (self.has_depth_stencil) 2 else 1].ptr,
        };
        if (cmd.occlusion_query_pool != 0) {
            if (cmd.occlusion_query_index) |query_index|
                c.vkCmdResetQueryPool(self.command_buffer, @intCast(cmd.occlusion_query_pool), query_index, 1);
        }
        c.vkCmdBeginRenderPass(self.command_buffer, &render_pass_begin, c.VK_SUBPASS_CONTENTS_INLINE);
        if (cmd.occlusion_query_pool != 0) {
            if (cmd.occlusion_query_index) |query_index| {
                const query_pool: c.VkQueryPool = @intCast(cmd.occlusion_query_pool);
                c.vkCmdBeginQuery(self.command_buffer, query_pool, query_index, VK_QUERY_CONTROL_NONE);
            }
        }

        if (cmd.vertex_bindings) |bs| {
            for (bs) |binding| {
                const vk_buffer = self.resolve_buffer(binding.handle) orelse continue;
                const buffers_arr = [1]c.VkBuffer{vk_buffer};
                const offsets_arr = [1]u64{binding.offset};
                c.vkCmdBindVertexBuffers(self.command_buffer, binding.slot, 1, &buffers_arr, &offsets_arr);
            }
        }
        const vp_width = cmd.viewport_width orelse @as(f32, @floatFromInt(target_width));
        const vp_height = cmd.viewport_height orelse @as(f32, @floatFromInt(target_height));
        var viewport = c.VkViewport{
            .x = cmd.viewport_x,
            .y = cmd.viewport_y,
            .width = vp_width,
            .height = vp_height,
            .minDepth = cmd.viewport_min_depth,
            .maxDepth = cmd.viewport_max_depth,
        };
        c.vkCmdSetViewport(self.command_buffer, 0, 1, @ptrCast(&viewport));
        const sc_width = cmd.scissor_width orelse target_width;
        const sc_height = cmd.scissor_height orelse target_height;
        var scissor = c.VkRect2D{
            .offset = .{
                .x = @intCast(cmd.scissor_x),
                .y = @intCast(cmd.scissor_y),
            },
            .extent = .{ .width = sc_width, .height = sc_height },
        };
        c.vkCmdSetScissor(self.command_buffer, 0, 1, @ptrCast(&scissor));

        if (cmd.depth_bias != 0 or cmd.depth_bias_slope_scale != 0 or cmd.depth_bias_clamp != 0) {
            c.vkCmdSetDepthBias(
                self.command_buffer,
                @floatFromInt(cmd.depth_bias),
                cmd.depth_bias_clamp,
                cmd.depth_bias_slope_scale,
            );
        }

        if (cmd.depth_stencil_format != model_gpu_types.WGPUTextureFormat_Undefined) {
            c.vkCmdSetStencilReference(
                self.command_buffer,
                c.VK_STENCIL_FACE_FRONT_AND_BACK,
                cmd.stencil_reference,
            );
        }

        c.vkCmdBindPipeline(self.command_buffer, c.VK_PIPELINE_BIND_POINT_GRAPHICS, self.pipeline);

        if (self.descriptor_set != VK_NULL_U64) {
            const sets = [1]u64{self.descriptor_set};
            c.vkCmdBindDescriptorSets(
                self.command_buffer,
                c.VK_PIPELINE_BIND_POINT_GRAPHICS,
                self.pipeline_layout,
                0,
                1,
                &sets,
                0,
                null,
            );
        }

        if (cmd.vertex_buffer_count > 0) {
            var vk_buffers: [model_render_types.MAX_VERTEX_BUFFERS]c.VkBuffer = [_]c.VkBuffer{VK_NULL_U64} ** model_render_types.MAX_VERTEX_BUFFERS;
            var vk_offsets: [model_render_types.MAX_VERTEX_BUFFERS]u64 = [_]u64{0} ** model_render_types.MAX_VERTEX_BUFFERS;
            var bound_count: u32 = 0;
            while (bound_count < cmd.vertex_buffer_count and bound_count < vk_buffers.len) : (bound_count += 1) {
                const handle = cmd.vertex_buffer_handles[bound_count];
                if (handle == 0) break;
                const compute_buffer = self.buffers.get(handle) orelse return error.InvalidArgument;
                vk_buffers[bound_count] = compute_buffer.buffer;
                vk_offsets[bound_count] = cmd.vertex_buffer_offsets[bound_count];
            }
            if (bound_count > 0) {
                c.vkCmdBindVertexBuffers(
                    self.command_buffer,
                    0,
                    bound_count,
                    vk_buffers[0..bound_count].ptr,
                    vk_offsets[0..bound_count].ptr,
                );
            }
        }

        if (index) |binding| c.vkCmdBindIndexBuffer(self.command_buffer, binding.buffer, binding.offset, binding.format);
        if (cmd.indirect_buffer_handle != 0) {
            const indirect = self.buffers.get(cmd.indirect_buffer_handle) orelse return error.InvalidArgument;
            if (index != null) {
                c.vkCmdDrawIndexedIndirect(self.command_buffer, indirect.buffer, cmd.indirect_offset, 1, c.VK_DRAW_INDEXED_INDIRECT_COMMAND_STRIDE);
            } else {
                c.vkCmdDrawIndirect(self.command_buffer, indirect.buffer, cmd.indirect_offset, 1, c.VK_DRAW_INDIRECT_COMMAND_STRIDE);
            }
        } else {
            for (0..draw_count) |_| {
                if (index) |binding| {
                    c.vkCmdDrawIndexed(self.command_buffer, binding.count, cmd.instance_count, cmd.first_index, cmd.base_vertex, cmd.first_instance);
                } else {
                    c.vkCmdDraw(self.command_buffer, cmd.vertex_count, cmd.instance_count, cmd.first_vertex, cmd.first_instance);
                }
            }
        }
        if (cmd.occlusion_query_pool != 0) {
            if (cmd.occlusion_query_index) |query_index| {
                const query_pool: c.VkQueryPool = @intCast(cmd.occlusion_query_pool);
                c.vkCmdEndQuery(self.command_buffer, query_pool, query_index);
            }
        }

        c.vkCmdEndRenderPass(self.command_buffer);
    }
};

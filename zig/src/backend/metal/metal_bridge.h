#pragma once
#include <stddef.h>
#include <stdint.h>

// Opaque handle: every returned handle is +1 retained; caller owns it.
// Call metal_bridge_release() to decrement when done.
typedef void* MetalHandle;

typedef struct {
    uint64_t array_stride;
    uint32_t step_mode;
    uint32_t buffer_index;
} MetalVertexBufferLayout;

typedef struct {
    uint32_t format;
    uint64_t offset;
    uint32_t shader_location;
    uint32_t buffer_index;
} MetalVertexAttributeDesc;

MetalHandle metal_bridge_create_default_device(void);
MetalHandle metal_bridge_create_surface_host(MetalHandle* layer_out);
void        metal_bridge_configure_surface_host(MetalHandle host, uint32_t width, uint32_t height);
void        metal_bridge_release(MetalHandle obj);

MetalHandle metal_bridge_device_new_command_queue(MetalHandle device);
MetalHandle metal_bridge_device_new_buffer_shared(MetalHandle device, size_t length);
MetalHandle metal_bridge_device_new_buffer_private(MetalHandle device, size_t length);
void*       metal_bridge_buffer_contents(MetalHandle buffer);

// Records a blit copy from src to dst and returns the committed command buffer
// (+1 retained). Call metal_bridge_command_buffer_wait_completed(), then
// metal_bridge_release() when done.
MetalHandle metal_bridge_encode_blit_copy(
    MetalHandle queue,
    MetalHandle src_buffer,
    MetalHandle dst_buffer,
    size_t      byte_count);

void metal_bridge_command_buffer_commit(MetalHandle cmd_buf);
void metal_bridge_command_buffer_wait_completed(MetalHandle cmd_buf);

// === Shared Event (lightweight GPU fence) ===

MetalHandle metal_bridge_device_new_shared_event(MetalHandle device);
uint64_t    metal_bridge_shared_event_signaled_value(MetalHandle event);
// Encode a signal on the command buffer; GPU sets event value after completion.
void metal_bridge_command_buffer_encode_signal_event(
    MetalHandle cmd_buf,
    MetalHandle event,
    uint64_t    value);
// Spin-wait until the event reaches the given value.
void metal_bridge_shared_event_wait(MetalHandle event, uint64_t value);

// Batch-encode multiple blit copies into a single command buffer.
// Returns the command buffer (+1 retained) ready for commit+wait.
MetalHandle metal_bridge_encode_blit_batch(
    MetalHandle  queue,
    MetalHandle* src_buffers,
    MetalHandle* dst_buffers,
    size_t*      byte_counts,
    uint32_t     count);

// === Streaming Blit Encoder ===

// Create a command buffer with a blit encoder ready for appending copies.
// Returns the command buffer (+1 retained). encoder_out receives the encoder.
MetalHandle metal_bridge_begin_blit_encoding(MetalHandle queue, MetalHandle* encoder_out);
// Append a copy to an open blit encoder.
void metal_bridge_blit_encoder_copy(
    MetalHandle encoder,
    MetalHandle src,
    MetalHandle dst,
    size_t      byte_count);
void metal_bridge_blit_encoder_copy_region(
    MetalHandle encoder,
    MetalHandle src,
    uint64_t    src_offset,
    MetalHandle dst,
    uint64_t    dst_offset,
    uint64_t    size);
void metal_bridge_blit_encoder_copy_buffer_to_texture(
    MetalHandle encoder,
    MetalHandle src,
    uint64_t    src_offset,
    uint32_t    src_bytes_per_row,
    uint32_t    src_rows_per_image,
    MetalHandle dst_texture,
    uint32_t    dst_mip_level,
    uint32_t    width,
    uint32_t    height,
    uint32_t    depth_or_array_layers);
void metal_bridge_blit_encoder_copy_texture_to_buffer(
    MetalHandle encoder,
    MetalHandle src_texture,
    uint32_t    src_mip_level,
    MetalHandle dst,
    uint64_t    dst_offset,
    uint32_t    dst_bytes_per_row,
    uint32_t    dst_rows_per_image,
    uint32_t    width,
    uint32_t    height,
    uint32_t    depth_or_array_layers);
void metal_bridge_blit_encoder_copy_texture_to_texture(
    MetalHandle encoder,
    MetalHandle src_texture,
    uint32_t    src_mip_level,
    MetalHandle dst_texture,
    uint32_t    dst_mip_level,
    uint32_t    width,
    uint32_t    height,
    uint32_t    depth_or_array_layers);
// End the current blit encoder. Call before commit or before starting a new encoder.
void metal_bridge_end_blit_encoding(MetalHandle encoder);

// === Streaming Command Buffer ===

// Create a command buffer without any encoder (+1 retained).
MetalHandle metal_bridge_create_command_buffer(MetalHandle queue);
// Open a blit encoder on an existing command buffer. Returns unretained encoder.
MetalHandle metal_bridge_cmd_buf_blit_encoder(MetalHandle cmd_buf);
// Encode a render pass on an existing command buffer (no commit).
void metal_bridge_cmd_buf_encode_render_pass(
    MetalHandle cmd_buf,
    MetalHandle pipeline,
    MetalHandle target,
    uint32_t    draw_count,
    uint32_t    vertex_count,
    uint32_t    instance_count,
    int         redundant_pipeline,
    int         redundant_bindgroup);
// Encode an ICB render pass on an existing command buffer (no commit).
void metal_bridge_cmd_buf_encode_icb_render_pass(
    MetalHandle cmd_buf,
    MetalHandle pipeline,
    MetalHandle icb,
    MetalHandle target,
    uint32_t    draw_count);
// Create render encoder on cmd_buf (unretained). Pipeline is set.
MetalHandle metal_bridge_cmd_buf_render_encoder(
    MetalHandle cmd_buf,
    MetalHandle pipeline,
    MetalHandle target,
    MetalHandle depth_target,
    int         use_depth_store);
void metal_bridge_render_encoder_set_bind_buffer(
    MetalHandle encoder,
    uint32_t    slot,
    MetalHandle buffer,
    uint64_t    offset);
void metal_bridge_render_encoder_set_bind_texture(
    MetalHandle encoder,
    uint32_t    slot,
    MetalHandle texture);
void metal_bridge_render_encoder_set_bind_sampler(
    MetalHandle encoder,
    uint32_t    slot,
    MetalHandle sampler);
void metal_bridge_render_encoder_set_vertex_buffer(
    MetalHandle encoder,
    uint32_t    slot,
    MetalHandle buffer,
    uint64_t    offset);
void metal_bridge_render_encoder_set_depth_stencil_state(
    MetalHandle encoder,
    MetalHandle depth_state);
void metal_bridge_render_encoder_set_depth_stencil_values(
    MetalHandle encoder,
    uint32_t    compare_fn,
    int         write_enabled);
void metal_bridge_render_encoder_set_depth_clip_mode(
    MetalHandle encoder,
    int         clamp);
void metal_bridge_render_encoder_set_front_facing(
    MetalHandle encoder,
    uint32_t    front_face);
void metal_bridge_render_encoder_set_cull_mode(
    MetalHandle encoder,
    uint32_t    cull_mode);
// Draw loop on an open render encoder.
void metal_bridge_render_encoder_draw(
    MetalHandle encoder,
    uint32_t    topology,
    uint32_t    draw_count,
    uint32_t    vertex_count,
    uint32_t    instance_count,
    uint32_t    first_vertex,
    uint32_t    first_instance,
    int         redundant_pipeline,
    MetalHandle pipeline);
void metal_bridge_render_encoder_draw_indexed(
    MetalHandle encoder,
    uint32_t    topology,
    uint32_t    draw_count,
    uint32_t    index_count,
    uint32_t    instance_count,
    MetalHandle index_buffer,
    uint64_t    index_offset,
    uint32_t    index_format,
    int32_t     base_vertex,
    uint32_t    first_instance);
// Execute ICB on an open render encoder.
void metal_bridge_render_encoder_execute_icb(
    MetalHandle encoder,
    MetalHandle icb,
    uint32_t    draw_count);
// End a render encoder.
void metal_bridge_render_encoder_end(MetalHandle encoder);

// === Compute Pipeline ===

// Compile MSL source into a MTLLibrary. On error writes a NUL-terminated
// message into error_buf (truncated to error_cap) and returns NULL.
MetalHandle metal_bridge_device_new_library_msl(
    MetalHandle device,
    const char* src,
    size_t      src_len,
    char*       error_buf,
    size_t      error_cap);

// Get a named function from a library.
MetalHandle metal_bridge_library_new_function(MetalHandle library, const char* name);

// Create compute pipeline from a function. Returns NULL on failure.
MetalHandle metal_bridge_device_new_compute_pipeline(
    MetalHandle device,
    MetalHandle function,
    char*       error_buf,
    size_t      error_cap);

// Encode and commit a compute dispatch. buffers[i] is the MTLBuffer for
// argument index i; buffers may be NULL (dispatch with no bindings). Returns
// the committed command buffer (+1 retained).
MetalHandle metal_bridge_encode_compute_dispatch(
    MetalHandle  queue,
    MetalHandle  pipeline,
    MetalHandle* buffers,
    uint32_t     buffer_count,
    uint32_t     x,
    uint32_t     y,
    uint32_t     z);

// Encode a blit copy into an existing command buffer (no commit).
void metal_bridge_cmd_buf_encode_blit_copy(
    MetalHandle cmd_buf,
    MetalHandle src,
    uint64_t    src_offset,
    MetalHandle dst,
    uint64_t    dst_offset,
    uint64_t    size);

// Encode a compute dispatch into an existing command buffer (no commit).
// Creates a compute encoder, dispatches, ends encoder.
// wg_x/wg_y/wg_z: shader workgroup size (0 = fallback to pipeline max).
void metal_bridge_cmd_buf_encode_compute_dispatch(
    MetalHandle  cmd_buf,
    MetalHandle  pipeline,
    MetalHandle* buffers,
    uint32_t     buffer_count,
    uint32_t     x,
    uint32_t     y,
    uint32_t     z,
    uint32_t     wg_x,
    uint32_t     wg_y,
    uint32_t     wg_z);

// Encode an indirect compute dispatch into an existing command buffer (no commit).
// indirect_buffer contains a MTLDispatchThreadgroupsIndirectArguments struct at offset.
// wg_x/wg_y/wg_z: shader workgroup size (0 = fallback to pipeline max).
void metal_bridge_cmd_buf_encode_compute_dispatch_indirect(
    MetalHandle  cmd_buf,
    MetalHandle  pipeline,
    MetalHandle* buffers,
    uint32_t     buffer_count,
    MetalHandle  indirect_buffer,
    uint64_t     indirect_offset,
    uint32_t     wg_x,
    uint32_t     wg_y,
    uint32_t     wg_z);

// === Texture ===

// pixel_format: WGPU texture format value (mapped internally to MTLPixelFormat).
// usage: WGPU texture usage flags.
MetalHandle metal_bridge_device_new_texture(
    MetalHandle device,
    uint32_t    width,
    uint32_t    height,
    uint32_t    mip_levels,
    uint32_t    pixel_format,
    uint32_t    usage);

// Write CPU data into a single mip level of a 2D texture. mip_level 0 = base.
void metal_bridge_texture_replace_region(
    MetalHandle  texture,
    uint32_t     width,
    uint32_t     height,
    const void*  data,
    uint32_t     bytes_per_row,
    uint32_t     mip_level);

uint32_t metal_bridge_texture_width(MetalHandle texture);
uint32_t metal_bridge_texture_height(MetalHandle texture);
uint32_t metal_bridge_texture_depth(MetalHandle texture);
uint32_t metal_bridge_texture_pixel_format(MetalHandle texture);
uint32_t metal_bridge_texture_mip_level_count(MetalHandle texture);
uint32_t metal_bridge_texture_sample_count(MetalHandle texture);

// === Sampler ===

// Filter values: 0=nearest, 1=linear.
// Address mode values: 0=clamp_to_edge, 1=mirror_clamp_to_edge, 2=repeat, 3=mirror_repeat.
MetalHandle metal_bridge_device_new_sampler(
    MetalHandle device,
    uint32_t    min_filter,
    uint32_t    mag_filter,
    uint32_t    mipmap_filter,
    uint32_t    addr_u,
    uint32_t    addr_v,
    uint32_t    addr_w,
    float       lod_min,
    float       lod_max,
    uint16_t    max_aniso);

// === Render Pipeline ===

// Create a render pipeline with built-in noop vertex/fragment shaders.
// pixel_format: WGPU texture format. support_icb: 1 to enable ICB use.
// Returns NULL on failure.
MetalHandle metal_bridge_device_new_render_pipeline(
    MetalHandle device,
    uint32_t    pixel_format,
    int         support_icb,
    char*       error_buf,
    size_t      error_cap);
MetalHandle metal_bridge_device_new_render_pipeline_functions(
    MetalHandle device,
    MetalHandle vertex_function,
    MetalHandle fragment_function,
    uint32_t    pixel_format,
    char*       error_buf,
    size_t      error_cap);
MetalHandle metal_bridge_device_new_render_pipeline_full(
    MetalHandle                     device,
    MetalHandle                     vertex_function,
    MetalHandle                     fragment_function,
    uint32_t                        pixel_format,
    uint32_t                        depth_format,
    const MetalVertexBufferLayout*  vertex_layouts,
    uint32_t                        vertex_layout_count,
    const MetalVertexAttributeDesc* vertex_attributes,
    uint32_t                        vertex_attribute_count,
    char*                           error_buf,
    size_t                          error_cap);
MetalHandle metal_bridge_device_new_depth_stencil_state(
    MetalHandle device,
    uint32_t    compare_fn,
    int         write_enabled,
    char*       error_buf,
    size_t      error_cap);

// Create an offscreen MTLTexture suitable as a render target.
MetalHandle metal_bridge_device_new_render_target(
    MetalHandle device,
    uint32_t    width,
    uint32_t    height,
    uint32_t    pixel_format);

// Encode a render pass with draw_count draw calls and commit. Returns the
// committed command buffer (+1 retained). redundant_pipeline: re-bind
// pipeline before each draw. redundant_bindgroup: no-op in Metal (documented
// deviation from WebGPU — Metal has no bind-group abstraction).
MetalHandle metal_bridge_encode_render_pass(
    MetalHandle queue,
    MetalHandle pipeline,
    MetalHandle target,
    uint32_t    draw_count,
    uint32_t    vertex_count,
    uint32_t    instance_count,
    int         redundant_pipeline,
    int         redundant_bindgroup);

// Create a Metal Indirect Command Buffer for render bundle emulation.
// command_count is the maximum number of draw commands.
MetalHandle metal_bridge_device_new_icb(
    MetalHandle device,
    MetalHandle pipeline,
    uint32_t    command_count,
    int         redundant_pipeline);

// Encode draw commands into an existing ICB. redundant_pipeline: call
// setRenderPipelineState per command (vs. inherit from encoder).
void metal_bridge_icb_encode_draws(
    MetalHandle icb,
    MetalHandle pipeline,
    uint32_t    draw_count,
    uint32_t    vertex_count,
    uint32_t    instance_count,
    int         redundant_pipeline);

// Encode a render pass that replays the ICB and commit. Returns the committed
// command buffer (+1 retained).
MetalHandle metal_bridge_encode_icb_render_pass(
    MetalHandle queue,
    MetalHandle pipeline,
    MetalHandle icb,
    MetalHandle target,
    uint32_t    draw_count);

// === GPU Timestamp Query (MTLCounterSampleBuffer) ===

// Check whether the device supports GPU timestamp counter sampling at stage boundaries.
int metal_bridge_supports_timestamp_query(MetalHandle device);

// Create a MTLCounterSampleBuffer for GPU timestamp queries.
// Returns NULL if counter sampling is unsupported or the timestamp counter set is absent.
MetalHandle metal_bridge_create_counter_sample_buffer(MetalHandle device, uint32_t count);

// Sample GPU timestamp on a blit encoder at the given query index.
// Creates a blit encoder on cmd_buf, samples, and ends encoding.
void metal_bridge_sample_timestamp(
    MetalHandle cmd_buf,
    MetalHandle counter_buffer,
    uint32_t    query_index);

// Resolve GPU timestamps from the counter sample buffer and copy to dest.
// dest_ptr must point to query_count * sizeof(uint64_t) bytes.
// Returns 1 on success, 0 on failure.
int metal_bridge_resolve_timestamps(
    MetalHandle counter_buffer,
    uint32_t    first_query,
    uint32_t    query_count,
    uint64_t*   dest_ptr);

// Release a counter sample buffer handle.
void metal_bridge_destroy_counter_sample_buffer(MetalHandle counter_buffer);

// === Semaphore-based completion (faster than waitUntilCompleted) ===

// Register a completion handler on cmd_buf that signals an internal semaphore.
// Must be called BEFORE commit. Only one pending wait is supported at a time.
void metal_bridge_command_buffer_setup_fast_wait(MetalHandle cmd_buf);
// Block until the completion handler fires. Call after commit.
void metal_bridge_command_buffer_wait_fast(void);

// === Device capability queries ===

// Feature bitmask positions returned by metal_bridge_query_device_features().
#define METAL_FEATURE_BIT_SHADER_F16               (1u << 0)
#define METAL_FEATURE_BIT_SUBGROUPS                (1u << 1)
#define METAL_FEATURE_BIT_TIMESTAMP_QUERY          (1u << 2)
#define METAL_FEATURE_BIT_INDIRECT_FIRST_INSTANCE  (1u << 3)
#define METAL_FEATURE_BIT_DEPTH_CLIP_CONTROL       (1u << 4)
#define METAL_FEATURE_BIT_DEPTH32FLOAT_STENCIL8    (1u << 5)
#define METAL_FEATURE_BIT_BGRA8UNORM_STORAGE       (1u << 6)
#define METAL_FEATURE_BIT_FLOAT32_FILTERABLE       (1u << 7)
#define METAL_FEATURE_BIT_FLOAT32_BLENDABLE        (1u << 8)
#define METAL_FEATURE_BIT_TEXTURE_COMPRESSION_ASTC (1u << 9)
#define METAL_FEATURE_BIT_TEXTURE_COMPRESSION_BC  (1u << 10)
#define METAL_FEATURE_BIT_TEXTURE_COMPRESSION_BC_SLICED_3D (1u << 11)
#define METAL_FEATURE_BIT_TEXTURE_COMPRESSION_ETC2 (1u << 12)
#define METAL_FEATURE_BIT_RG11B10UFLOAT_RENDERABLE (1u << 13)
#define METAL_FEATURE_BIT_SUBGROUPS_F16            (1u << 14)
#define METAL_FEATURE_BIT_TEXTURE_COMPRESSION_ASTC_SLICED_3D (1u << 15)
#define METAL_FEATURE_BIT_CLIP_DISTANCES           (1u << 16)
#define METAL_FEATURE_BIT_DUAL_SOURCE_BLENDING     (1u << 17)

// Query the default Metal device for supported features. Returns a bitmask
// of METAL_FEATURE_BIT_* flags. Result is cached after the first call.
// Returns 0 if no Metal device is available.
uint32_t metal_bridge_query_device_features(void);

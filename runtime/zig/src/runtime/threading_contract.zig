pub const ObjectThreadClass = enum {
    thread_safe,
    immutable_shareable,
    thread_confined,
};

pub const CallbackThreadClass = enum {
    caller_thread,
    worker_thread,
};

pub const ObjectKind = enum {
    instance,
    adapter,
    device,
    queue,
    buffer,
    texture,
    texture_view,
    sampler,
    bind_group,
    bind_group_layout,
    pipeline_layout,
    shader_module,
    compute_pipeline,
    render_pipeline,
    command_encoder,
    compute_pass_encoder,
    render_pass_encoder,
    render_bundle_encoder,
};

pub const QueueRole = enum {
    graphics,
    compute,
    transfer,
    readback,
};

pub fn object_thread_class(kind: ObjectKind) ObjectThreadClass {
    return switch (kind) {
        .instance,
        .adapter,
        .device,
        .queue,
        .buffer,
        .texture,
        .texture_view,
        .sampler,
        .bind_group,
        .bind_group_layout,
        .pipeline_layout,
        .shader_module,
        .compute_pipeline,
        .render_pipeline,
        => .thread_safe,

        .command_encoder,
        .compute_pass_encoder,
        .render_pass_encoder,
        .render_bundle_encoder,
        => .thread_confined,
    };
}

pub fn callback_thread_class() CallbackThreadClass {
    return .worker_thread;
}

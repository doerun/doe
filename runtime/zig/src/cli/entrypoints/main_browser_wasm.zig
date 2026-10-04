const compiler = @import("doe").compiler.wgsl_runtime.browserWasm();

export fn source_limit() u32 {
    return compiler.source_limit();
}

export fn reserve_source(length: u32) u32 {
    return compiler.reserve_source(length);
}

export fn compile(length: u32, enabled: u32) u32 {
    return compiler.compile(length, enabled);
}

export fn output_length() u32 {
    return compiler.output_length();
}

export fn release_job() void {
    compiler.release_job();
}

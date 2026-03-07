const build_options = @import("build_options");

pub export fn doeWgpuDropinBuildInfoSchemaVersion() callconv(.c) u32 {
    return 1;
}

pub export fn doeWgpuDropinLeanVerifiedBuild() callconv(.c) u32 {
    return if (build_options.lean_verified) 1 else 0;
}

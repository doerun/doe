pub const BackendKind = enum {
    native_vulkan,
    native_metal,
    native_d3d12,
    dawn_delegate,
    cost_model,

    pub fn name(self: BackendKind) []const u8 {
        return switch (self) {
            .native_vulkan => "native_vulkan",
            .native_metal => "native_metal",
            .native_d3d12 => "native_d3d12",
            .dawn_delegate => "dawn_delegate",
            .cost_model => "cost_model",
        };
    }

    pub fn is_native(self: BackendKind) bool {
        return switch (self) {
            .native_vulkan, .native_metal, .native_d3d12 => true,
            .dawn_delegate, .cost_model => false,
        };
    }

    pub fn is_claimable(self: BackendKind) bool {
        return self.is_native();
    }
};

pub const TimingSource = enum {
    gpu_timestamp,
    cpu_submit_wait,
    cpu_wall_clock,
    cost_model,

    pub fn name(self: TimingSource) []const u8 {
        return switch (self) {
            .gpu_timestamp => "gpu_timestamp",
            .cpu_submit_wait => "cpu_submit_wait",
            .cpu_wall_clock => "cpu_wall_clock",
            .cost_model => "cost_model",
        };
    }

    pub fn is_gpu_measured(self: TimingSource) bool {
        return self == .gpu_timestamp;
    }
};

pub const ComparabilityClass = enum {
    strict,
    directional,
    diagnostic,

    pub fn name(self: ComparabilityClass) []const u8 {
        return switch (self) {
            .strict => "strict",
            .directional => "directional",
            .diagnostic => "diagnostic",
        };
    }

    pub fn is_claimable(self: ComparabilityClass) bool {
        return self == .strict;
    }
};

pub const ArtifactMeta = struct {
    backend_kind: BackendKind,
    timing_source: TimingSource,
    comparability: ComparabilityClass,

    pub fn is_claimable(self: ArtifactMeta) bool {
        return self.backend_kind.is_claimable() and
            self.comparability.is_claimable() and
            self.timing_source != .cost_model;
    }
};

pub fn classify(
    backend_kind: BackendKind,
    gpu_timestamp_valid: bool,
    gpu_timestamp_attempted: bool,
) ArtifactMeta {
    const timing_source: TimingSource = if (backend_kind == .cost_model)
        .cost_model
    else if (gpu_timestamp_valid)
        .gpu_timestamp
    else if (gpu_timestamp_attempted)
        .cpu_submit_wait
    else
        .cpu_wall_clock;

    const comparability: ComparabilityClass = if (backend_kind == .cost_model)
        .diagnostic
    else if (gpu_timestamp_valid)
        .strict
    else if (backend_kind.is_native() or backend_kind == .dawn_delegate)
        .directional
    else
        .diagnostic;

    return .{
        .backend_kind = backend_kind,
        .timing_source = timing_source,
        .comparability = comparability,
    };
}

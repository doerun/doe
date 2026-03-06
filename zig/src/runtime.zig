// Re-export from quirk module for backwards compatibility.
// New code should import quirk/mod.zig instead.
const quirk_runtime = @import("quirk/runtime.zig");
pub const DispatchDecision = quirk_runtime.DispatchDecision;
pub const CommandDispatchBucket = quirk_runtime.CommandDispatchBucket;
pub const DispatchContext = quirk_runtime.DispatchContext;
pub const emptyDecision = quirk_runtime.emptyDecision;
pub const buildDispatchContext = quirk_runtime.buildDispatchContext;
pub const buildProfileDispatchContext = quirk_runtime.buildProfileDispatchContext;
pub const dispatch = quirk_runtime.dispatch;
pub const emptyContext = quirk_runtime.emptyContext;
pub const applyAction = quirk_runtime.applyAction;

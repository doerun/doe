// Re-export from quirk module for backwards compatibility.
// New code should import quirk/mod.zig instead.
const quirk_json = @import("quirk/quirk_json.zig");
pub const parseQuirks = quirk_json.parseQuirks;
pub const freeQuirks = quirk_json.freeQuirks;

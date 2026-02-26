pub const DropinDiagnostics = struct {
    symbol: []const u8,
    owner: []const u8,
    resolved: bool,
    fallback_used: bool,
};

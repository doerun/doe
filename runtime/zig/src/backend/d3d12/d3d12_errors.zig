// D3D12 HRESULT error mapping and diagnostic name lookup.
//
// Single source of truth for all HRESULT-to-Zig-error mapping in the
// D3D12 backend. Other modules should import check_hr / map_hresult
// from here instead of defining their own.
//
// Note: the current d3d12_bridge.c layer converts most HRESULTs into
// NULL-or-handle / 0-or-(-1) returns before they reach Zig. These
// HRESULT constants and check_hr are provided so that:
//   (a) bridge functions can be updated to propagate raw HRESULTs, and
//   (b) Zig-side code has a single, tested mapping ready for that day.

const std = @import("std");
const common_errors = @import("../common/errors.zig");

pub const D3D12Error = common_errors.BackendNativeError;

/// HRESULT is a 32-bit signed integer. Bit 31 set means failure.
pub const HRESULT = i32;

// --- Success codes ---
pub const S_OK: HRESULT = 0;
pub const S_FALSE: HRESULT = 1;

// --- Common COM / Win32 error codes ---
// Hex literals with bit 31 set are negative when stored as i32.
pub const E_FAIL: HRESULT = @bitCast(@as(u32, 0x80004005));
pub const E_INVALIDARG: HRESULT = @bitCast(@as(u32, 0x80070057));
pub const E_OUTOFMEMORY: HRESULT = @bitCast(@as(u32, 0x8007000E));
pub const E_NOTIMPL: HRESULT = @bitCast(@as(u32, 0x80004001));

// --- DXGI error codes ---
pub const DXGI_ERROR_DEVICE_REMOVED: HRESULT = @bitCast(@as(u32, 0x887A0005));
pub const DXGI_ERROR_DEVICE_HUNG: HRESULT = @bitCast(@as(u32, 0x887A0006));
pub const DXGI_ERROR_DEVICE_RESET: HRESULT = @bitCast(@as(u32, 0x887A0007));
pub const DXGI_ERROR_DRIVER_INTERNAL_ERROR: HRESULT = @bitCast(@as(u32, 0x887A0020));
pub const DXGI_ERROR_INVALID_CALL: HRESULT = @bitCast(@as(u32, 0x887A0001));
pub const DXGI_ERROR_WAS_STILL_DRAWING: HRESULT = @bitCast(@as(u32, 0x887A000A));

// --- D3D12-specific error codes ---
pub const D3D12_ERROR_ADAPTER_NOT_FOUND: HRESULT = @bitCast(@as(u32, 0x887E0001));
pub const D3D12_ERROR_DRIVER_VERSION_MISMATCH: HRESULT = @bitCast(@as(u32, 0x887E0002));

/// Check an HRESULT and return a Zig error on failure, or void on success.
/// HRESULT convention: non-negative values (bit 31 clear) are success.
pub fn check_hr(hr: HRESULT) D3D12Error!void {
    if (hr >= 0) return;
    return map_hresult(hr);
}

/// Map a raw HRESULT to a BackendNativeError. Called for failure codes only.
pub fn map_hresult(hr: HRESULT) D3D12Error {
    return switch (hr) {
        E_INVALIDARG => error.InvalidArgument,
        E_OUTOFMEMORY => error.InvalidState,
        E_NOTIMPL => error.UnsupportedFeature,
        DXGI_ERROR_DEVICE_REMOVED,
        DXGI_ERROR_DEVICE_HUNG,
        DXGI_ERROR_DEVICE_RESET,
        DXGI_ERROR_DRIVER_INTERNAL_ERROR,
        => error.InvalidState,
        DXGI_ERROR_INVALID_CALL => error.InvalidArgument,
        DXGI_ERROR_WAS_STILL_DRAWING => error.SyncUnavailable,
        D3D12_ERROR_ADAPTER_NOT_FOUND => error.UnsupportedFeature,
        D3D12_ERROR_DRIVER_VERSION_MISMATCH => error.UnsupportedFeature,
        E_FAIL => error.InvalidState,
        else => error.InvalidState,
    };
}

/// Return a human-readable name for common HRESULT codes.
/// Useful for structured log output without pulling in Windows headers.
pub fn hresultName(hr: HRESULT) []const u8 {
    return switch (hr) {
        S_OK => "S_OK",
        S_FALSE => "S_FALSE",
        E_FAIL => "E_FAIL",
        E_INVALIDARG => "E_INVALIDARG",
        E_OUTOFMEMORY => "E_OUTOFMEMORY",
        E_NOTIMPL => "E_NOTIMPL",
        DXGI_ERROR_DEVICE_REMOVED => "DXGI_ERROR_DEVICE_REMOVED",
        DXGI_ERROR_DEVICE_HUNG => "DXGI_ERROR_DEVICE_HUNG",
        DXGI_ERROR_DEVICE_RESET => "DXGI_ERROR_DEVICE_RESET",
        DXGI_ERROR_DRIVER_INTERNAL_ERROR => "DXGI_ERROR_DRIVER_INTERNAL_ERROR",
        DXGI_ERROR_INVALID_CALL => "DXGI_ERROR_INVALID_CALL",
        DXGI_ERROR_WAS_STILL_DRAWING => "DXGI_ERROR_WAS_STILL_DRAWING",
        D3D12_ERROR_ADAPTER_NOT_FOUND => "D3D12_ERROR_ADAPTER_NOT_FOUND",
        D3D12_ERROR_DRIVER_VERSION_MISMATCH => "D3D12_ERROR_DRIVER_VERSION_MISMATCH",
        else => "HRESULT_UNKNOWN",
    };
}

// --- Tests ---

test "check_hr succeeds on S_OK" {
    try check_hr(S_OK);
}

test "check_hr succeeds on S_FALSE" {
    try check_hr(S_FALSE);
}

test "check_hr succeeds on arbitrary positive value" {
    try check_hr(42);
}

test "check_hr returns error on E_FAIL" {
    const result = check_hr(E_FAIL);
    try std.testing.expectEqual(error.InvalidState, result);
}

test "map_hresult maps E_INVALIDARG to InvalidArgument" {
    try std.testing.expectEqual(error.InvalidArgument, map_hresult(E_INVALIDARG));
}

test "map_hresult maps E_OUTOFMEMORY to InvalidState" {
    try std.testing.expectEqual(error.InvalidState, map_hresult(E_OUTOFMEMORY));
}

test "map_hresult maps E_NOTIMPL to UnsupportedFeature" {
    try std.testing.expectEqual(error.UnsupportedFeature, map_hresult(E_NOTIMPL));
}

test "map_hresult maps DXGI_ERROR_DEVICE_REMOVED to InvalidState" {
    try std.testing.expectEqual(error.InvalidState, map_hresult(DXGI_ERROR_DEVICE_REMOVED));
}

test "map_hresult maps DXGI_ERROR_DEVICE_HUNG to InvalidState" {
    try std.testing.expectEqual(error.InvalidState, map_hresult(DXGI_ERROR_DEVICE_HUNG));
}

test "map_hresult maps DXGI_ERROR_DEVICE_RESET to InvalidState" {
    try std.testing.expectEqual(error.InvalidState, map_hresult(DXGI_ERROR_DEVICE_RESET));
}

test "map_hresult maps DXGI_ERROR_DRIVER_INTERNAL_ERROR to InvalidState" {
    try std.testing.expectEqual(error.InvalidState, map_hresult(DXGI_ERROR_DRIVER_INTERNAL_ERROR));
}

test "map_hresult maps DXGI_ERROR_INVALID_CALL to InvalidArgument" {
    try std.testing.expectEqual(error.InvalidArgument, map_hresult(DXGI_ERROR_INVALID_CALL));
}

test "map_hresult maps DXGI_ERROR_WAS_STILL_DRAWING to SyncUnavailable" {
    try std.testing.expectEqual(error.SyncUnavailable, map_hresult(DXGI_ERROR_WAS_STILL_DRAWING));
}

test "map_hresult maps D3D12_ERROR_ADAPTER_NOT_FOUND to UnsupportedFeature" {
    try std.testing.expectEqual(error.UnsupportedFeature, map_hresult(D3D12_ERROR_ADAPTER_NOT_FOUND));
}

test "map_hresult maps D3D12_ERROR_DRIVER_VERSION_MISMATCH to UnsupportedFeature" {
    try std.testing.expectEqual(error.UnsupportedFeature, map_hresult(D3D12_ERROR_DRIVER_VERSION_MISMATCH));
}

test "map_hresult falls back to InvalidState for unknown negative HRESULT" {
    // Arbitrary unknown failure code (bit 31 set)
    const unknown: HRESULT = @bitCast(@as(u32, 0x80040200));
    try std.testing.expectEqual(error.InvalidState, map_hresult(unknown));
}

test "hresultName returns known names" {
    try std.testing.expectEqualStrings("S_OK", hresultName(S_OK));
    try std.testing.expectEqualStrings("E_FAIL", hresultName(E_FAIL));
    try std.testing.expectEqualStrings("E_INVALIDARG", hresultName(E_INVALIDARG));
    try std.testing.expectEqualStrings("DXGI_ERROR_DEVICE_REMOVED", hresultName(DXGI_ERROR_DEVICE_REMOVED));
    try std.testing.expectEqualStrings("D3D12_ERROR_ADAPTER_NOT_FOUND", hresultName(D3D12_ERROR_ADAPTER_NOT_FOUND));
}

test "hresultName returns HRESULT_UNKNOWN for unrecognized code" {
    try std.testing.expectEqualStrings("HRESULT_UNKNOWN", hresultName(9999));
}

test "HRESULT constants have expected sign" {
    // Success codes are non-negative
    try std.testing.expect(S_OK >= 0);
    try std.testing.expect(S_FALSE >= 0);
    // Error codes are negative (bit 31 set)
    try std.testing.expect(E_FAIL < 0);
    try std.testing.expect(E_INVALIDARG < 0);
    try std.testing.expect(E_OUTOFMEMORY < 0);
    try std.testing.expect(E_NOTIMPL < 0);
    try std.testing.expect(DXGI_ERROR_DEVICE_REMOVED < 0);
    try std.testing.expect(DXGI_ERROR_DEVICE_HUNG < 0);
    try std.testing.expect(DXGI_ERROR_DEVICE_RESET < 0);
    try std.testing.expect(DXGI_ERROR_DRIVER_INTERNAL_ERROR < 0);
    try std.testing.expect(DXGI_ERROR_INVALID_CALL < 0);
    try std.testing.expect(DXGI_ERROR_WAS_STILL_DRAWING < 0);
    try std.testing.expect(D3D12_ERROR_ADAPTER_NOT_FOUND < 0);
    try std.testing.expect(D3D12_ERROR_DRIVER_VERSION_MISMATCH < 0);
}

// doe_shader_compilation_info_native.zig — GPUShaderModule.getCompilationInfo().
//
// Returns compilation diagnostics captured during shader module creation.
// When the module was created successfully (the common case) the message list
// is empty.  When the WGSL compiler recorded an error before returning null,
// the error details are extracted from the per-module error fields and returned
// as a single-entry JSON array so that callers receive actionable information.
//
// Output format (JSON array of message objects):
//   [{"message":"...","type":"error","lineNum":N,"linePos":N,"offset":0,"length":0}]
// An empty array ("[]") is returned when there are no diagnostics.
//
// The returned JSON is a NUL-terminated C string backed by a static buffer
// (single-threaded read; safe for synchronous N-API calls).  Callers must
// NOT free this pointer; it remains valid until the next call.

const std = @import("std");
const native = @import("doe_wgpu_native.zig");

const cast = native.cast;
const DoeShaderModule = native.DoeShaderModule;

// ============================================================
// Imports from the WGSL compiler — error metadata query
// ============================================================

const wgsl_compiler = @import("doe_wgsl/mod.zig");

// ============================================================
// Static output buffer
// ============================================================

// Sufficient for one error message with reasonable length.
// JSON schema: [{"message":"<msg>","type":"error","lineNum":<n>,"linePos":<n>,"offset":0,"length":0}]
const OUT_CAP: usize = 1024;
var out_buf: [OUT_CAP]u8 = undefined;

// Static NUL-terminated empty-array result.
const EMPTY_JSON: [*:0]const u8 = "[]";

// ============================================================
// Exported API
// ============================================================

// doeNativeShaderModuleGetCompilationInfo — retrieve compilation diagnostics
// for a previously created shader module.
//
// module_raw: opaque pointer to DoeShaderModule.
// Returns a pointer to a NUL-terminated JSON string.  The pointer remains
// valid until the next call to this function.  Callers must NOT free it.
//
// Behaviour:
//   - If the module handle is valid and the last WGSL compiler error is empty,
//     returns "[]" (no diagnostics — the module compiled cleanly).
//   - If the module handle is null (e.g. createShaderModule returned null and
//     the caller is querying diagnostics on a null handle), returns the last
//     recorded WGSL error as a single-entry error array.
//   - The message type is always "error" since Doe does not currently surface
//     warnings separately; extend when advisory messages are tracked.
pub export fn doeNativeShaderModuleGetCompilationInfo(
    module_raw: ?*anyopaque,
) callconv(.c) [*:0]const u8 {
    // A valid module means compilation succeeded — no errors to report.
    if (cast(DoeShaderModule, module_raw) != null) {
        return EMPTY_JSON;
    }

    // Module is null: the creation call failed.  Surface the last WGSL error.
    const msg = wgsl_compiler.lastErrorMessage();
    if (msg.len == 0) {
        return EMPTY_JSON;
    }

    const line = wgsl_compiler.lastErrorLine();
    const col = wgsl_compiler.lastErrorColumn();

    // Build escaped message: replace " with \", \ with \\, control chars with space.
    var escaped: [OUT_CAP]u8 = undefined;
    var ei: usize = 0;
    for (msg) |c| {
        if (ei + 2 >= escaped.len) break;
        if (c == '"') {
            escaped[ei] = '\\';
            ei += 1;
            escaped[ei] = '"';
            ei += 1;
        } else if (c == '\\') {
            escaped[ei] = '\\';
            ei += 1;
            escaped[ei] = '\\';
            ei += 1;
        } else if (c < 0x20) {
            escaped[ei] = ' ';
            ei += 1;
        } else {
            escaped[ei] = c;
            ei += 1;
        }
    }
    const escaped_msg = escaped[0..ei];

    const json = std.fmt.bufPrint(
        &out_buf,
        "[{{\"message\":\"{s}\",\"type\":\"error\",\"lineNum\":{d},\"linePos\":{d},\"offset\":0,\"length\":0}}]",
        .{ escaped_msg, line, col },
    ) catch {
        return EMPTY_JSON;
    };
    // Ensure NUL termination.
    if (json.len < out_buf.len) {
        out_buf[json.len] = 0;
    } else {
        out_buf[OUT_CAP - 1] = 0;
    }
    return @ptrCast(out_buf[0..].ptr);
}

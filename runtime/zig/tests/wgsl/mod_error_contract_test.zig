// mod_error_contract_test.zig — Public WGSL translation error-contract tests.

const std = @import("std");
const mod = @import("../../src/compiler/wgsl/mod.zig");
const analyzeToIr = mod.analyzeToIr;
const TranslateError = mod.TranslateError;
const CompilationStage = mod.CompilationStage;
const lastErrorStage = mod.lastErrorStage;
const lastErrorKind = mod.lastErrorKind;
const lastErrorContext = mod.lastErrorContext;
const lastErrorInfo = mod.lastErrorInfo;
const lastErrorMessage = mod.lastErrorMessage;

test "semantic type mismatch preserves stage kind and source context" {
    try std.testing.expectError(TranslateError.UnexpectedToken, analyzeToIr(std.testing.allocator, "fn main("));
    try std.testing.expectEqual(CompilationStage.parser, lastErrorStage());
    try std.testing.expectEqual(TranslateError.UnexpectedToken, lastErrorKind().?);
    try std.testing.expect(std.mem.startsWith(u8, lastErrorMessage(), "parser:"));

    const source =
        \\@compute @workgroup_size(1)
        \\fn main() {
        \\    let value: bool = 1u;
        \\}
    ;
    try std.testing.expectError(TranslateError.TypeMismatch, analyzeToIr(std.testing.allocator, source));
    const info = lastErrorInfo();
    try std.testing.expectEqual(CompilationStage.sema, info.stage);
    try std.testing.expectEqual(TranslateError.TypeMismatch, info.kind.?);
    try std.testing.expect(info.location != null);
    try std.testing.expect(std.mem.indexOf(u8, info.context, "let value: bool = 1u;") != null);
    try std.testing.expect(std.mem.startsWith(u8, lastErrorMessage(), "sema: TypeMismatch"));
}

test "semantic unsupported builtin preserves specific error contract" {
    const source =
        \\@compute @workgroup_size(1)
        \\fn main() {
        \\    let value = transpose(1.0);
        \\}
    ;

    try std.testing.expectError(TranslateError.UnsupportedBuiltin, analyzeToIr(std.testing.allocator, source));
    try std.testing.expectEqual(CompilationStage.sema, lastErrorStage());
    try std.testing.expectEqual(TranslateError.UnsupportedBuiltin, lastErrorKind().?);
    try std.testing.expect(std.mem.indexOf(u8, lastErrorContext(), "transpose(1.0)") != null);
    try std.testing.expect(std.mem.indexOf(u8, lastErrorMessage(), "UnsupportedBuiltin") != null);
}

test "ir builder unsupported construct preserves specific error contract" {
    const source =
        \\const FLAG: bool = !true;
        \\@compute @workgroup_size(1)
        \\fn main() {}
    ;

    try std.testing.expectError(TranslateError.UnsupportedConstruct, analyzeToIr(std.testing.allocator, source));
    try std.testing.expectEqual(CompilationStage.ir_builder, lastErrorStage());
    try std.testing.expectEqual(TranslateError.UnsupportedConstruct, lastErrorKind().?);
    try std.testing.expect(std.mem.indexOf(u8, lastErrorContext(), "const FLAG: bool = !true;") != null);
    try std.testing.expect(std.mem.startsWith(u8, lastErrorMessage(), "ir_builder: UnsupportedConstruct"));
}

const analysis = @import("../../src/compiler/wgsl/pipeline/analysis.zig");
const translate_msl = @import("../../src/compiler/wgsl/pipeline/translate_msl.zig");
const DiagnosticCase = struct { source: []const u8, stage: CompilationStage, kind: TranslateError, context: []const u8 };
const DIAGNOSTIC_CASES = [_]DiagnosticCase{
    .{ .source = "\nfn broken(", .stage = .parser, .kind = error.UnexpectedToken, .context = "broken" },
    .{ .source = "@compute @workgroup_size(1)\nfn main() { let value: bool = 1u; }", .stage = .sema, .kind = error.TypeMismatch, .context = "value" },
    .{ .source = "const FLAG: bool = !true;\n@compute @workgroup_size(1) fn main() {}", .stage = .ir_builder, .kind = error.UnsupportedConstruct, .context = "FLAG" },
};
const VALID_DIAGNOSTIC_SOURCE = "@compute @workgroup_size(1) fn main() {}";

fn checkOwnedDiagnostic(case: DiagnosticCase) !void {
    var diagnostic = analysis.Diagnostic{};
    try std.testing.expectError(case.kind, analysis.analyzeToIrWithDiagnostic(std.heap.page_allocator, case.source, &diagnostic));
    const snapshot = diagnostic;
    var success = analysis.Diagnostic{};
    var module = try analysis.analyzeToIrWithDiagnostic(std.heap.page_allocator, VALID_DIAGNOSTIC_SOURCE, &success);
    defer module.deinit();
    try std.testing.expectEqual(CompilationStage.none, success.lastErrorStage());
    for (0..32) |_| {
        var other = analysis.Diagnostic{};
        try std.testing.expectError(error.UnexpectedToken, analysis.analyzeToIrWithDiagnostic(std.heap.page_allocator, "fn other(", &other));
        const info = diagnostic.lastErrorInfo();
        try std.testing.expectEqual(case.kind, info.kind.?);
        try std.testing.expectEqual(case.stage, info.stage);
        try std.testing.expect(info.location != null);
        try std.testing.expect(std.mem.indexOf(u8, info.context, case.context) != null);
        try std.testing.expectEqualSlices(u8, snapshot.last_error_buf[0..snapshot.last_error_len], diagnostic.lastErrorMessage());
    }
}

const DiagnosticThread = struct {
    case: DiagnosticCase,
    failure: ?anyerror = null,
    fn run(self: *DiagnosticThread) void {
        checkOwnedDiagnostic(self.case) catch |err| {
            self.failure = err;
        };
    }
};

test "owned diagnostics survive concurrent parser sema builder and successful compilations" {
    var workers: [DIAGNOSTIC_CASES.len]DiagnosticThread = undefined;
    var threads: [DIAGNOSTIC_CASES.len]std.Thread = undefined;
    var started: usize = 0;
    defer for (threads[0..started]) |thread| thread.join();
    for (DIAGNOSTIC_CASES, 0..) |case, i| {
        workers[i] = .{ .case = case };
        threads[i] = try std.Thread.spawn(.{}, DiagnosticThread.run, .{&workers[i]});
        started += 1;
    }
    for (threads[0..started]) |thread| thread.join();
    started = 0;
    for (workers) |worker| if (worker.failure) |err| return err;
}

test "emission failures belong to the provided diagnostic" {
    var diagnostic = analysis.Diagnostic{};
    var output: [1]u8 = undefined;
    try std.testing.expectError(error.OutputTooLarge, translate_msl.translateToMslWithDiagnostic(std.testing.allocator, VALID_DIAGNOSTIC_SOURCE, &output, &diagnostic));
    try std.testing.expectEqual(CompilationStage.msl_emit, diagnostic.lastErrorStage());
    try std.testing.expectEqual(error.OutputTooLarge, diagnostic.lastErrorKind().?);
    _ = analyzeToIr(std.testing.allocator, "fn bad(") catch {};
    try std.testing.expectEqual(CompilationStage.msl_emit, diagnostic.lastErrorStage());
}

const REQUEST_SOURCE =
    \\override COUNT: u32 = 2u;
    \\@group(0) @binding(0) var<storage, read_write> data: array<u32>;
    \\@compute @workgroup_size(COUNT) fn main(@builtin(global_invocation_id) id: vec3<u32>) {
    \\  data[id.x] = COUNT;
    \\}
;

fn exerciseAnalysisRequest(allocator: std.mem.Allocator) !void {
    var diagnostic = analysis.Diagnostic{};
    var result = analysis.analyze(.{
        .allocator = allocator,
        .source = REQUEST_SOURCE,
        .robustness = analysis.default_translation_robustness_config(),
        .overrides = &.{.{ .key = "COUNT", .value = 4.0 }},
        .diagnostic = &diagnostic,
    }) catch |err| {
        try std.testing.expectEqual(error.OutOfMemory, err);
        try std.testing.expectEqual(error.OutOfMemory, diagnostic.lastErrorKind().?);
        return err;
    };
    defer result.module.deinit();
    try std.testing.expectEqual(@as(u32, 4), result.module.entry_points.items[0].workgroup_size[0]);
    try std.testing.expectEqual(CompilationStage.none, diagnostic.lastErrorStage());
}

test "analysis request owns rollback through every allocation failure" {
    try std.testing.checkAllAllocationFailures(std.testing.allocator, exerciseAnalysisRequest, .{});
}

test "analysis request preserves overrides robustness and compatibility diagnostics" {
    const overrides = [_]mod.ir.OverrideEntry{.{ .key = "COUNT", .value = 4.0 }};
    const config = analysis.default_translation_robustness_config();
    _ = analyzeToIr(std.testing.allocator, "fn broken(") catch {};
    var legacy_error = analysis.compatibilityDiagnostic().*;
    var diagnostic = analysis.Diagnostic{};
    var result = try analysis.analyze(.{
        .allocator = std.testing.allocator,
        .source = REQUEST_SOURCE,
        .robustness = config,
        .overrides = &overrides,
        .diagnostic = &diagnostic,
    });
    defer result.module.deinit();
    try std.testing.expectEqualStrings(legacy_error.lastErrorMessage(), lastErrorMessage());
    try std.testing.expectEqual(@as(u32, 4), result.module.entry_points.items[0].workgroup_size[0]);
    var legacy = try analysis.analyzeToIrWithConfigAndOverrides(std.testing.allocator, REQUEST_SOURCE, config, &overrides);
    defer legacy.deinit();
    try std.testing.expectEqual(mod.ir_digest.computeHex(&legacy), mod.ir_digest.computeHex(&result.module));
    try std.testing.expectEqual(CompilationStage.none, lastErrorStage());

    for (DIAGNOSTIC_CASES) |case| {
        try std.testing.expectError(case.kind, analysis.analyze(.{
            .allocator = std.testing.allocator,
            .source = case.source,
            .robustness = config,
            .diagnostic = &diagnostic,
        }));
        try std.testing.expectEqual(case.stage, diagnostic.lastErrorStage());
        try std.testing.expectError(case.kind, analyzeToIr(std.testing.allocator, case.source));
        try std.testing.expectEqualStrings(lastErrorMessage(), diagnostic.lastErrorMessage());
        try std.testing.expectEqualStrings(lastErrorContext(), diagnostic.lastErrorContext());
    }
}

test "analysis request preserves numeric parse overflow as invalid WGSL" {
    var diagnostic = analysis.Diagnostic{};
    try std.testing.expectError(error.InvalidWgsl, analysis.analyze(.{
        .allocator = std.testing.allocator,
        .source = "@group(4294967296) @binding(0) var<storage> data: array<u32>; @compute @workgroup_size(1) fn main() {}",
        .robustness = analysis.default_translation_robustness_config(),
        .diagnostic = &diagnostic,
    }));
    try std.testing.expectEqual(CompilationStage.sema, diagnostic.lastErrorStage());
}

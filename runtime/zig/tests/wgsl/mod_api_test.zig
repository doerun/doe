// mod_api_test.zig — Public WGSL translation API smoke and cross-backend baseline tests.

const translation_basics_test = @import("mod_api_translation_basics_test.zig");
const proof_preconditions_test = @import("mod_api_proof_preconditions_test.zig");
const stage_and_pointer_test = @import("mod_api_stage_and_pointer_test.zig");

comptime {
    _ = translation_basics_test;
    _ = proof_preconditions_test;
    _ = stage_and_pointer_test;
}

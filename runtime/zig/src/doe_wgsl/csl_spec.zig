// csl_spec.zig — Cerebras CSL target constants, limits, and enums.
//
// Reference: https://sdk.cerebras.net/csl/language_index (SDK 1.4.0)
// This file is the single source of truth for CSL target constraints
// used by the emit_csl_* backend modules.

/// Fabric routing directions available on each PE's router.
pub const Direction = enum {
    NORTH,
    SOUTH,
    EAST,
    WEST,
    RAMP,
};

/// WSE hardware generation. Affects color count, microthread model, and
/// queue initialization requirements.
pub const Arch = enum {
    wse2,
    wse3,
};

// ---------------------------------------------------------------------------
// Hardware limits
// ---------------------------------------------------------------------------

/// Maximum routable colors on WSE-2. WSE-3 may allow more but 24 is the
/// documented safe ceiling for SDK 1.4.0.
pub const MAX_COLORS: u8 = 24;

/// Colors reserved by the memcpy framework for host↔device transfers.
/// The PE program must not allocate these for application routing.
pub const MEMCPY_RESERVED_COLORS: u8 = 4;

/// Usable application colors after memcpy reservation.
pub const APP_COLORS: u8 = MAX_COLORS - MEMCPY_RESERVED_COLORS;

/// Per-PE SRAM on WSE-2 (bytes). WSE-3 is similar but not publicly documented
/// at a per-PE granularity; use this as the conservative floor.
pub const PE_SRAM_BYTES: usize = 48 * 1024;

/// Maximum PE grid dimension (width or height) for SDK rectangle programs.
/// The full WSE-2 mesh is ~750×1180 but practical SDK programs use smaller
/// rectangles to leave room for memcpy routing infrastructure.
pub const MAX_RECT_DIM: u16 = 512;

// ---------------------------------------------------------------------------
// Output format markers
// ---------------------------------------------------------------------------

/// Section separator emitted between layout.csl and pe_program.csl in the
/// combined output buffer. The host splits on this marker to extract files.
pub const SECTION_SEPARATOR: []const u8 = "\n//--- ";
pub const SECTION_SEPARATOR_END: []const u8 = " ---\n";

/// Standard file names for the two mandatory sections.
pub const LAYOUT_FILENAME: []const u8 = "layout.csl";
pub const PE_PROGRAM_FILENAME: []const u8 = "pe_program.csl";

// ---------------------------------------------------------------------------
// CSL scalar type names
// ---------------------------------------------------------------------------

pub fn scalarTypeName(scalar: @import("ir.zig").ScalarType) []const u8 {
    return switch (scalar) {
        .void => "void",
        .bool => "bool",
        .i32, .abstract_int => "i32",
        .u32 => "u32",
        .f32, .abstract_float => "f32",
        .f16 => "f16",
    };
}

// ---------------------------------------------------------------------------
// Fabric DSD type names
// ---------------------------------------------------------------------------

pub const FABIN_DSD: []const u8 = "fabin_dsd";
pub const FABOUT_DSD: []const u8 = "fabout_dsd";
pub const MEM1D_DSD: []const u8 = "mem1d_dsd";
pub const MEM4D_DSD: []const u8 = "mem4d_dsd";

enable f16;
struct State { a: array<u32, 2>, b: vec4f, c: mat2x2f }
var<private> a: State;
var<private> b: State;
var<private> flag: bool;
var<private> half: f16;
var<private> integer: i32;
@compute @workgroup_size(1) fn main() {}

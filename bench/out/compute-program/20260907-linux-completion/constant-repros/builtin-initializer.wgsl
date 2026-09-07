const VALUE: u32 = countOneBits(3u);
@group(0) @binding(0) var<storage, read_write> output: array<u32>;
@compute @workgroup_size(1) fn main() { output[0] = VALUE; }

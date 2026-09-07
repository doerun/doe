
    const COUNT: u32 = countOneBits(3u);
    const SIGNED: i32 = countOneBits(-1i);
    const COUNTS: vec2<u32> = countOneBits(vec2<u32>(0u, 0x55555555u));
    const ARRAY: array<u32, 3> = array<u32, 3>(5u, 7u, 11u);
    @group(0) @binding(0) var<storage, read_write> output: array<u32>;
    @compute @workgroup_size(1) fn main() {
      output[0] = COUNT; output[1] = u32(SIGNED);
      output[2] = COUNTS.x; output[3] = COUNTS.y;
      output[4] = COUNTS[output[0] - 1u]; output[5] = ARRAY[2];
    }
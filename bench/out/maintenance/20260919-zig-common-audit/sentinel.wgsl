@group(0) @binding(0) var<storage, read_write> data: array<u32>;
@compute @workgroup_size(1) fn main() {
  for (var i = 0u; i < arrayLength(&data); i += 1u) { data[i] = 0u; }
  data[0] = 7u;
}

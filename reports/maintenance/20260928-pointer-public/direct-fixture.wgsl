
@group(0) @binding(0) var<storage, read_write> data: array<u32>;
fn change(p: ptr<function, u32>) { *p += 5u; }
@compute @workgroup_size(1) fn main(@builtin(global_invocation_id) id: vec3u) {
  var x = id.x + 1u;
  data[id.x * 5u] = x + x;
  x += 3u;
  data[id.x * 5u + 1u] = x;
  change(&x);
  data[id.x * 5u + 2u] = x;
  if ((id.x % 2u) == 0u) { x += 10u; } else { x += 20u; }
  data[id.x * 5u + 3u] = x;
  for (var j = 0u; j < 3u; j++) { x += j; }
  data[id.x * 5u + 4u] = x;
}
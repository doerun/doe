@compute @workgroup_size(64, 1, 1)
fn main(@builtin(global_invocation_id) gid : vec3u) {
  var x : f32 = f32(gid.x + 1u);
  var y : f32 = 0.0;
  var i : u32 = 0u;

  loop {
    if (i >= 4096u) {
      break;
    }
    x = fract(sin(x * 1.6180339 + f32(i)) * 43758.5453);
    y = y + x;
    i = i + 1u;
  }

  if (y < -1.0) {
    x = y;
  }
  _ = x;
}

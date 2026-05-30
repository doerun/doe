@group(0) @binding(0) var src: texture_2d<f32>;
@group(0) @binding(1) var dst: texture_storage_2d<rgba8unorm, write>;

@compute @workgroup_size(8, 8)
fn main(@builtin(global_invocation_id) gid: vec3u) {
  let dims = textureDimensions(src);
  if (gid.x >= dims.x || gid.y >= dims.y) {
    return;
  }
  let pixel = textureLoad(src, vec2u(gid.xy), 0);
  textureStore(dst, vec2u(gid.xy), pixel);
}

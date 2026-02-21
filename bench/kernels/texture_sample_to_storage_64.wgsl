const kTextureSize : u32 = 64u;

@group(0) @binding(0) var srcTex : texture_2d<f32>;
@group(0) @binding(1) var dstTex : texture_storage_2d<rgba8unorm, write>;

@compute @workgroup_size(8, 8, 1)
fn main(@builtin(global_invocation_id) gid : vec3u) {
  if (gid.x >= kTextureSize || gid.y >= kTextureSize) {
    return;
  }

  let pixel = textureLoad(srcTex, vec2<i32>(i32(gid.x), i32(gid.y)), 0);
  let out = vec4<f32>(
    pixel.x * 0.5 + 0.25,
    pixel.y * 0.5 + 0.10,
    pixel.z * 0.5 + 0.05,
    1.0
  );
  textureStore(dstTex, vec2<i32>(i32(gid.x), i32(gid.y)), out);
}

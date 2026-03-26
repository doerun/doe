@vertex
fn main(@location(0) pos: vec4f) -> @builtin(position) vec4f {
    return pos;
}

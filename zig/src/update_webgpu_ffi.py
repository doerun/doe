import sys

with open("webgpu_ffi.zig", "r") as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    line_num = i + 1
    if 470 <= line_num <= 585:
        if line_num == 470:
            new_lines.append('    pub usingnamespace @import("wgpu_ffi_sync.zig");\n')
            new_lines.append('    pub usingnamespace @import("wgpu_ffi_surface.zig");\n')
        continue
    if 608 <= line_num <= 804:
        continue
    new_lines.append(line)

with open("webgpu_ffi.zig", "w") as f:
    f.writelines(new_lines)


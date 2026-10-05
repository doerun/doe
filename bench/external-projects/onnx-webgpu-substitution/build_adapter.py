"""Build a typed, pinned Dawn proc-table adapter without compiling GPU operators."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

DAWN_COMMIT = 'ec7b457e5bb1fcec6f59733c4f3dd84d2f885a38'
DOE_HEADER_HASH = '7691d76ceb67056f89e97b9ff0b62163eacf19a8e0e09a8fa7dbb32069b7978c'
GENERATOR_TREE_HASH = 'fdf72d6e9a85991849600945538556af6c41d6c20103599034c628b4beac65fa'
# These return/query language values whose identities differ between the pinned headers.
UNSUPPORTED_LANGUAGE_PROCS = frozenset({
    'instanceGetWGSLLanguageFeatures', 'instanceHasWGSLLanguageFeature',
    'supportedWGSLLanguageFeaturesFreeMembers',
})
EXPECTED_ENUM_DIFFERENCES = frozenset({
    'WGPUSType_ExternalTextureBindingLayout', 'WGPUSType_ExternalTextureBindingEntry',
    'WGPUSType_CompatibilityModeLimits', 'WGPUWGSLLanguageFeatureName_SubgroupUniformity',
    'WGPUWGSLLanguageFeatureName_ImmediateAddressSpace',
    'WGPUWGSLLanguageFeatureName_BufferView',
})
PROC_PATTERN = re.compile(r'WGPUProc(\w+)\s+(\w+);')
PROTO_PATTERN = re.compile(r'typedef\s+([\w \t*]+?)\s*\(\*WGPUProc(\w+)\)\((.*?)\)', re.S)


def identity(path: Path) -> dict[str, str]:
    return {'path': str(path.resolve()),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def generator_tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    inputs = [*root.joinpath('generator').rglob('*'), root / 'src/dawn/dawn.json']
    for path in sorted(inputs):
        if path.is_file() and '__pycache__' not in path.parts:
            digest.update(path.relative_to(root).as_posix().encode() + b'\0')
            digest.update(path.read_bytes() + b'\0')
    return digest.hexdigest()


def structs(header: str) -> dict[str, str]:
    return dict(re.findall(
        r'typedef struct (WGPU\w+) \{(.*?)\}\s*\1\s*\w*;',
        header, re.S))


def fields(body: str) -> list[str]:
    return re.findall(r'\b(\w+)\s*;', re.sub(r'/\*.*?\*/', '', body, flags=re.S))


def check_abi(output: Path, doe_header: Path, dawn_header: Path) -> dict:
    """Compile layout assertions; keep non-identical extension values explicit."""
    doe = doe_header.read_text(encoding='utf-8')
    dawn = dawn_header.read_text(encoding='utf-8')
    renamed = re.sub(r'\b(?:WGPU|wgpu)\w*', lambda match: 'Doe' + match[0], doe)
    renamed = renamed.replace('WEBGPU_H_', 'DOE_WEBGPU_H_')
    (output / 'doe_webgpu.h').write_text(renamed, encoding='utf-8')
    assertions = ['#include <stddef.h>', '#include "doe_webgpu.h"',
                  '#include "dawn/webgpu.h"']
    shared = []
    for name, body in structs(doe).items():
        other = structs(dawn).get(name)
        if other is None:
            continue
        if fields(body) != fields(other):
            raise ValueError(f'Unqualified member change: {name}')
        shared.append(name)
        assertions.append(f'static_assert(sizeof({name}) == sizeof(Doe{name}), "{name}");')
        for member in fields(body):
            assertions.append(
                f'static_assert(offsetof({name}, {member}) == '
                f'offsetof(Doe{name}, {member}), "{name}.{member}");')
    differences = []
    values = dict(re.findall(r'\b(WGPU\w+)\s*=\s*(0x[0-9A-Fa-f]+|\d+)', dawn))
    for name, value in re.findall(r'\b(WGPU\w+)\s*=\s*(0x[0-9A-Fa-f]+|\d+)', doe):
        if name not in values:
            continue
        if int(value, 0) != int(values[name], 0):
            differences.append(name)
        else:
            assertions.append(
                f'static_assert((unsigned){name} == (unsigned)Doe{name}, "{name}");')
    if frozenset(differences) != EXPECTED_ENUM_DIFFERENCES:
        raise ValueError(f'Unqualified enum changes: {differences}')
    functions = check_signatures(doe, dawn)
    assertions.append('int main() {return 0;}')
    audit = output / 'abi.cpp'
    audit.write_text('\n'.join(assertions) + '\n', encoding='utf-8')
    subprocess.run(['g++', '-Werror', '-I' + str(output),
                    '-I' + str(dawn_header.parent.parent), str(audit),
                    '-o', str(output / 'abi')], check=True)
    subprocess.run([str(output / 'abi')], check=True)
    return {'sharedStructures': shared, 'differentExtensionValues': differences,
            'auditSource': identity(audit), 'sharedFunctionSignatures': functions}


def check_signatures(doe: str, dawn: str) -> list[str]:
    def normalized(header: str) -> dict[str, tuple[str, tuple[str, ...]]]:
        result = {}
        for return_type, name, parameters in PROTO_PATTERN.findall(header):
            types = []
            for argument in parameters.split(','):
                argument = re.sub(r'\bWGPU_(?:NULLABLE|STRING_VIEW)\b', '', argument)
                argument = re.sub(r'\b\w+\s*$', '', argument.strip()) if argument.strip() != 'void' else 'void'
                types.append(re.sub(r'\s+', '', argument))
            result[name] = (re.sub(r'\s+', '', return_type), tuple(types))
        return result
    common = []
    other = normalized(dawn)
    for name, signature in normalized(doe).items():
        if name not in other:
            continue
        if signature != other[name]:
            raise ValueError(f'Unqualified proc signature: {name}')
        common.append(name)
    return common


def generate_wrappers(header: str, table: str, standard: str) -> tuple[str, list[str]]:
    """Emit signatures from C-imported types, preserving Dawn table order."""
    prototypes = {name: params for _, name, params in PROTO_PATTERN.findall(header)}
    lines = ['const bridge = @import("adapter.zig");', 'const c = bridge.c;']
    names = []
    standard_names = []
    for suffix, field in PROC_PATTERN.findall(table):
        names.append(field)
        proc = 'WGPUProc' + suffix
        args = prototypes[suffix]
        count = 0 if args.strip() == 'void' else len(args.split(','))
        lines.append(f'const F_{field} = @typeInfo(@typeInfo(c.{proc}).optional.child).pointer.child;')
        signature = ', '.join(
            f'a{i}: @typeInfo(F_{field}).@"fn".params[{i}].type.?'
            for i in range(count))
        arguments = ', '.join(f'a{i}' for i in range(count))
        lines.append(f'pub fn {field}({signature}) callconv(.c) bridge.Return("{field}") {{')
        lines.append(f'    return bridge.invoke("{field}", .{{{arguments}}});')
        lines.append('}')
        if (re.search(r'\b' + proc + r'\b', standard)
                and field not in UNSUPPORTED_LANGUAGE_PROCS):
            standard_names.append(field)
    lines.append('pub fn isStandard(comptime field: []const u8) bool {')
    lines.append('    const std = @import("std");')
    for field in standard_names:
        lines.append(f'    if (std.mem.eql(u8, field, "{field}")) return true;')
    lines.extend(['    return false;', '}'])
    return '\n'.join(lines) + '\n', names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dawn-source', type=Path, required=True,
                        help='Unmodified source archive of the pinned Dawn commit')
    parser.add_argument('--python', type=Path, required=True,
                        help='Python containing the pinned Jinja2 generator dependency')
    parser.add_argument('--out', type=Path, required=True,
                        help='New private build directory')
    args = parser.parse_args()
    args.out = args.out.resolve()
    args.dawn_source = args.dawn_source.resolve()
    args.python = args.python.resolve()
    if args.out.exists():
        parser.error(f'Refusing to replace build directory: {args.out}')
    repo = Path(__file__).resolve().parents[3]
    doe_header = repo / 'runtime/zig/vendor/webgpu-headers/webgpu.h'
    if identity(doe_header)['sha256'] != DOE_HEADER_HASH:
        raise ValueError('Doe header changed; requalify the adapter ABI first')
    if generator_tree_hash(args.dawn_source) != GENERATOR_TREE_HASH:
        raise ValueError('Dawn generator inputs differ from the pinned release ABI')
    subprocess.run([str(args.python), '-c',
                    'import importlib.metadata as m; assert m.version("Jinja2") == "3.1.6"'],
                   check=True)
    args.out.mkdir(parents=True)
    generated = args.out / 'generated'
    generator = args.dawn_source / 'generator/dawn_json_generator.py'
    source = args.dawn_source / 'src/dawn/dawn.json'
    subprocess.run([str(args.python), str(generator), '--dawn-json', str(source),
                    '--targets', 'headers', '--template-dir',
                    str(args.dawn_source / 'generator/templates'),
                    '--output-dir', str(generated)], check=True)
    dawn_header = generated / 'include/dawn/webgpu.h'
    table = generated / 'include/dawn/dawn_proc_table.h'
    abi = check_abi(args.out, doe_header, dawn_header)
    wrapper, names = generate_wrappers(dawn_header.read_text(encoding='utf-8'),
                                      table.read_text(encoding='utf-8'),
                                      doe_header.read_text(encoding='utf-8'))
    (args.out / 'proc_wrappers.zig').write_text(wrapper, encoding='utf-8')
    adapter = repo / 'runtime/bridge/dawn-proc-table/adapter.zig'
    shutil.copy2(adapter, args.out / 'adapter.zig')
    library = args.out / 'libdoe_dawn_bridge.so'
    subprocess.run(['zig', 'build-lib', str(args.out / 'adapter.zig'),
                    '-dynamic', '-lc', '-ldl', '-O', 'ReleaseSafe',
                    '-I' + str(generated / 'include'), '-femit-bin=' + str(library)],
                   check=True)
    context = repo / 'bench/external-projects/onnx-webgpu-substitution/external-context.c'
    subprocess.run(['cc', '-std=c11', '-Werror', '-Wall', '-Wextra', '-shared',
                    '-fPIC', '-pthread', '-I' + str(generated / 'include'), str(context),
                    '-o', str(args.out / 'libexternal_context.so')], check=True)
    manifest = {'schemaVersion': 1, 'dawnCommit': DAWN_COMMIT,
                'builder': identity(Path(__file__)),
                'generatorDependencies': {'Jinja2': '3.1.6'},
                'generatorTreeHash': GENERATOR_TREE_HASH,
                'generator': identity(generator), 'dawnJson': identity(source),
                'doeHeader': identity(doe_header), 'dawnHeader': identity(dawn_header),
                'procHeader': identity(table), 'adapterSource': identity(adapter),
                'wrapperSource': identity(args.out / 'proc_wrappers.zig'),
                'library': identity(library), 'contextSource': identity(context),
                'contextLibrary': identity(args.out / 'libexternal_context.so'),
                'procNames': names, 'abi': abi}
    (args.out / 'build.json').write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

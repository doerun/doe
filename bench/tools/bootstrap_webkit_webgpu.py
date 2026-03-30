#!/usr/bin/env python3
"""Bootstrap WebKit's standalone WebGPU library (Metal backend) for Apple comparison workflows.

WebKit's Source/WebGPU contains a standard C webgpu.h-backed framework.
This script fetches a WebKit checkout and builds the WebGPU framework target
using the upstream Xcode project so we can consume a native WebGPU sidecar.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


WEBKIT_REPO_URL = "git@github.com:WebKit/WebKit.git"
# Official Apple WebKit repo on GitHub (SSH, matches gh auth git protocol).

DEFAULT_SOURCE_DIR = "bench/vendor/webkit-webgpu"
DEFAULT_BUILD_DIR = "bench/vendor/webkit-webgpu/out/xcode"
DEFAULT_OUTPUT_STATE = "bench/fixtures/webkit_webgpu_runtime_state.json"
DEFAULT_BUILD_CONFIGURATION = "Release"
DEFAULT_XCODE_DERIVED_DATA = "/tmp/webkit-webgpu-xcode-derived-data"

WEBKIT_REQUIRED_PATHS = (
    ("Source/WebGPU", "dir"),
    ("Source/WebGPU/WebGPU.xcodeproj", "dir"),
    ("Source/WebGPU/WebGPU.xcodeproj/xcshareddata/xcschemes/WebGPU.xcscheme", "file"),
    ("Source/WebGPU/Configurations", "dir"),
    ("Source/WebGPU/WebGPU/WebGPU.h", "file"),
    ("Source/WTF", "dir"),
    ("Source/bmalloc", "dir"),
    ("Source/cmake", "dir"),
)

WEBKIT_OPTIONAL_PATHS = (
    ("Source/ThirdParty", "dir"),
    ("Source/JavaScriptCore", "dir"),
    ("Source/WebCore", "dir"),
    ("Source/WebKit", "dir"),
    ("Source/WebKitLegacy", "dir"),
)

WEBKIT_SPARSE_CHECKOUT_PATHS = [
    "/Source/WebGPU/",
    "/Source/WTF/",
    "/Source/bmalloc/",
    "/Source/cmake/",
    "/Source/CMakeLists.txt",
    "/CMakeLists.txt",
    "/cmake/",
    "/*.cmake",
    # Xcode configs referenced by ../../../Configurations/ from WebGPU project
    "/Configurations/",
    "/Tools/clangd/",
    "/Tools/Scripts/",
    "/WebKitLibraries/",
]


def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    merged_env = None
    if env:
        merged_env = {**os.environ, **env}
    proc = subprocess.run(
        cmd,
        cwd=None if cwd is None else str(cwd),
        env=merged_env,
        text=True,
        capture_output=capture,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed ({' '.join(cmd)})\n"
            f"cwd={cwd}\n"
            f"stdout={proc.stdout or ''}\n"
            f"stderr={proc.stderr or ''}"
        )
    return proc


def check_dependency(name: str) -> str:
    binary = shutil.which(name)
    if not binary:
        raise RuntimeError(f"required dependency missing: {name}")
    return binary


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_sparse_checkout(sparse_file: Path) -> None:
    sparse_file.parent.mkdir(parents=True, exist_ok=True)
    sparse_file.write_text("\n".join(WEBKIT_SPARSE_CHECKOUT_PATHS) + "\n", encoding="utf-8")


def ensure_repo(source_dir: Path, repo_url: str, branch: str, skip_fetch: bool) -> None:
    git_exe = check_dependency("git")
    if not source_dir.exists():
        print(f"Shallow-cloning WebKit into {source_dir} ...")
        print("(This may take several minutes — WebKit is large even with sparse checkout)")
        source_dir.mkdir(parents=True, exist_ok=True)
        run([git_exe, "init"], cwd=source_dir)
        run([git_exe, "remote", "add", "origin", repo_url], cwd=source_dir)
        run([git_exe, "config", "core.sparseCheckout", "true"], cwd=source_dir)
        write_sparse_checkout(source_dir / ".git" / "info" / "sparse-checkout")
        run([git_exe, "fetch", "--depth", "1", "origin", branch], cwd=source_dir)
        run([git_exe, "checkout", branch], cwd=source_dir)
        return

    if not (source_dir / ".git").exists():
        raise RuntimeError(f"{source_dir} exists but is not a git repo; remove it and rerun")

    run([git_exe, "config", "core.sparseCheckout", "true"], cwd=source_dir)
    write_sparse_checkout(source_dir / ".git" / "info" / "sparse-checkout")

    if skip_fetch:
        return

    run([git_exe, "fetch", "--depth", "1", "origin", branch], cwd=source_dir)
    run([git_exe, "checkout", branch], cwd=source_dir)


def check_path_exists(base: Path, relative: str, kind: str) -> bool:
    target = base / relative
    if kind == "dir":
        return target.is_dir()
    if kind == "file":
        return target.is_file()
    return target.exists()


def probe_webgpu_layout(source_dir: Path) -> dict[str, object]:
    webgpu_dir = source_dir / "Source" / "WebGPU"
    project_file = webgpu_dir / "WebGPU.xcodeproj" / "xcshareddata" / "xcschemes" / "WebGPU.xcscheme"

    return {
        "webgpu_dir_exists": webgpu_dir.is_dir(),
        "wtf_dir_exists": (source_dir / "Source" / "WTF").is_dir(),
        "bmalloc_dir_exists": (source_dir / "Source" / "bmalloc").is_dir(),
        "xcode_project_exists": (source_dir / "Source" / "WebGPU" / "WebGPU.xcodeproj").is_dir(),
        "xcscheme_exists": project_file.is_file(),
        "webgpu_source_cpp_count": len(list(webgpu_dir.rglob("*.cpp")) if webgpu_dir.is_dir() else []),
        "webgpu_source_header_count": len(list(webgpu_dir.rglob("*.h")) if webgpu_dir.is_dir() else []),
    }


def validate_webgpu_layout(source_dir: Path) -> dict[str, object]:
    required_status: dict[str, bool] = {}
    optional_status: dict[str, bool] = {}
    missing_required: list[str] = []
    missing_optional: list[str] = []

    for relative, kind in WEBKIT_REQUIRED_PATHS:
        ok = check_path_exists(source_dir, relative, kind)
        required_status[relative] = ok
        if not ok:
            missing_required.append(f"{relative} ({kind})")

    for relative, kind in WEBKIT_OPTIONAL_PATHS:
        ok = check_path_exists(source_dir, relative, kind)
        optional_status[relative] = ok
        if not ok:
            missing_optional.append(f"{relative} ({kind})")

    if missing_required:
        message = [
            "WebKit sparse checkout is missing required WebGPU inputs.",
            "Missing required paths:",
            *[f"  - {path}" for path in missing_required],
            "Suggested fix: include these in sparse-checkout and rerun with --rebuild.",
        ]
        raise RuntimeError("\n".join(message))

    if missing_optional:
        print("Warning: optional WebGPU inputs are absent:")
        for item in missing_optional:
            print(f"  - {item}")
        print(
            "The build can still proceed, but missing optional paths may cause unresolved "
            "dependencies depending on the checkout revision."
        )

    return {
        "required": required_status,
        "optional": optional_status,
        "missing_optional": missing_optional,
    }


def ensure_writable_dir(path: Path) -> None:
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
    probe = path / ".webkit_webgpu_build_probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise RuntimeError(
            f"unable to create files under {path}: {exc}. Set --xcode-derived-data or --build-dir to writable paths."
        )


def create_workspace(source_dir: Path) -> Path:
    """Create an Xcode workspace linking bmalloc, WTF, and WebGPU projects."""
    ws_dir = source_dir / "WebGPU.xcworkspace"
    ws_dir.mkdir(parents=True, exist_ok=True)
    contents = ws_dir / "contents.xcworkspacedata"
    contents.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Workspace version = "1.0">\n'
        '   <FileRef location = "group:Source/bmalloc/bmalloc.xcodeproj"/>\n'
        '   <FileRef location = "group:Source/WTF/WTF.xcodeproj"/>\n'
        '   <FileRef location = "group:Source/WebGPU/WebGPU.xcodeproj"/>\n'
        "</Workspace>\n",
        encoding="utf-8",
    )
    return ws_dir


def build_library(
    source_dir: Path,
    build_dir: Path,
    parallel: int,
    configuration: str,
    derived_data: Path,
) -> None:
    xcodebuild = check_dependency("xcodebuild")

    webgpu_project = source_dir / "Source" / "WebGPU" / "WebGPU.xcodeproj"
    if not webgpu_project.is_dir():
        raise RuntimeError(f"Xcode project missing: {webgpu_project}")

    ensure_writable_dir(build_dir)
    ensure_writable_dir(derived_data)

    ws_dir = create_workspace(source_dir)

    # Step 1: Build bmalloc + WTF via workspace (produces static libs).
    # Build each dependency individually to avoid the bmalloc↔WTF cycle
    # that xcodebuild detects when building the full workspace scheme.
    products_dir = derived_data / "Build" / "Products" / configuration
    if not (products_dir / "libWTF.a").exists():
        print("Step 1/2: Building bmalloc + WTF dependencies...")
        for scheme in ("bmalloc", "WTF"):
            print(f"  Building {scheme}...")
            dep_args = [
                xcodebuild,
                "-workspace", str(ws_dir),
                "-scheme", scheme,
                "-configuration", configuration,
                "ONLY_ACTIVE_ARCH=YES",
                "SDKROOT=macosx",
                "-derivedDataPath", str(derived_data),
                "-jobs", str(parallel),
            ]
            run(dep_args, cwd=source_dir, capture=False)
    else:
        print("Step 1/2: bmalloc + WTF already built, skipping.")

    # Step 2: Build WebGPU framework with explicit static lib linking.
    # WTF and bmalloc build as static libs, not frameworks, so WebGPU
    # needs explicit -lWTF -lbmalloc -lpas and system framework links.
    products_dir = derived_data / "Build" / "Products" / configuration
    print("Step 2/2: Building WebGPU.framework with static lib linking...")
    webgpu_args = [
        xcodebuild,
        "-project", str(webgpu_project),
        "-scheme", "WebGPU",
        "-configuration", configuration,
        "ONLY_ACTIVE_ARCH=YES",
        "SDKROOT=macosx",
        "-derivedDataPath", str(derived_data),
        "-jobs", str(parallel),
        f"LIBRARY_SEARCH_PATHS={products_dir}",
        f"HEADER_SEARCH_PATHS={products_dir}/usr/local/include $(inherited)",
        f"OTHER_LDFLAGS=$(inherited) -L{products_dir} -lWTF -lbmalloc -lpas"
        " -framework Security -framework Metal -framework IOKit"
        " -framework CoreFoundation",
        "SUPPORTS_TEXT_BASED_API=NO",
    ]
    run(webgpu_args, cwd=source_dir, capture=False)


def find_library(build_dir: Path, derived_data: Path, configuration: str) -> Path | None:
    candidates = [
        build_dir / configuration / "WebGPU.framework" / "WebGPU",
        build_dir / "Build" / "Products" / configuration / "WebGPU.framework" / "WebGPU",
        build_dir / "Products" / configuration / "WebGPU.framework" / "WebGPU",
        derived_data / "Build" / "Products" / configuration / "WebGPU.framework" / "WebGPU",
        build_dir / "libWebGPU.dylib",
        build_dir / "lib" / "WebGPU.dylib",
        build_dir / "Source" / "WebGPU" / "libWebGPU.dylib",
        build_dir / "libwebgpu.dylib",
    ]

    for path in candidates:
        if path.exists():
            return path

    # Framework/dylib fallbacks
    for path in build_dir.rglob("WebGPU.framework/WebGPU"):
        if path.is_file():
            return path

    for path in build_dir.rglob("*WebGPU*.dylib"):
        if path.is_file():
            return path

    for path in derived_data.rglob("WebGPU.framework/WebGPU"):
        if path.is_file():
            return path

    for path in derived_data.rglob("*webgpu*.dylib"):
        if path.is_file():
            return path

    return None


def build_shim(
    source_dir: Path,
    derived_data: Path,
    configuration: str,
) -> Path | None:
    """Build the C-linkage shim dylib that bridges WebKit's C++ API to Dawn's C ABI."""
    clangpp = shutil.which("clang++")
    if not clangpp:
        print("WARNING: clang++ not found, skipping shim build", file=sys.stderr)
        return None

    shim_src = Path(__file__).resolve().parent.parent / "drop-in" / "webkit_webgpu_c_shim.mm"
    if not shim_src.is_file():
        print(f"WARNING: shim source not found at {shim_src}, skipping", file=sys.stderr)
        return None

    products_dir = derived_data / "Build" / "Products" / configuration
    shim_dir = source_dir / "out" / "shim"
    shim_dir.mkdir(parents=True, exist_ok=True)
    shim_dylib = shim_dir / "libwebgpu_webkit_cshim.dylib"

    # The shim includes WebGPU.h from PrivateHeaders and needs WTF/bmalloc
    # source headers (the framework does not export them as a separate framework).
    private_headers = products_dir / "WebGPU.framework" / "PrivateHeaders"
    wtf_src = source_dir / "Source" / "WTF"
    bmalloc_src = source_dir / "Source" / "bmalloc"

    print("Building C-linkage shim (webkit_webgpu_c_shim.mm)...")
    run(
        [
            clangpp,
            "-shared",
            "-o", str(shim_dylib),
            str(shim_src),
            f"-F{products_dir}",
            "-framework", "WebGPU",
            "-framework", "Metal",
            "-framework", "IOKit",
            "-framework", "CoreFoundation",
            "-framework", "Security",
            f"-I{products_dir}/usr/local/include",
            f"-I{private_headers}",
            f"-I{wtf_src}",
            f"-I{bmalloc_src}",
            "-std=c++2b", "-ObjC++",
            "-install_name", "@rpath/libwebgpu_webkit_cshim.dylib",
            "-rpath", str(products_dir),
        ],
        capture=False,
    )

    install_name_tool = shutil.which("install_name_tool")
    codesign = shutil.which("codesign")
    cc = shutil.which("cc")

    # The built WebGPU.framework bakes /System/.../WebGPU as its install_name.
    # Redirect it to @rpath so the shim uses our built copy, not the system one.
    if install_name_tool:
        fw_binary = products_dir / "WebGPU.framework" / "WebGPU"
        system_fw = "/System/Library/PrivateFrameworks/WebGPU.framework/Versions/A/WebGPU"
        run(
            [install_name_tool, "-change", system_fw,
             "@rpath/WebGPU.framework/Versions/A/WebGPU", str(shim_dylib)],
        )

        # WebGPU.framework links against system JavaScriptCore, which has
        # duplicate WTF ObjC classes. Since no JSC symbols are used, redirect
        # the reference to a stub framework so it doesn't conflict.
        system_jsc = "/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/JavaScriptCore"
        stub_jsc_name = "@rpath/JavaScriptCore_unused.framework/Versions/A/JavaScriptCore"
        jsc_ref = run(
            ["otool", "-L", str(fw_binary)], capture=True,
        ).stdout
        if system_jsc in jsc_ref:
            run([install_name_tool, "-change", system_jsc, stub_jsc_name, str(fw_binary)])
            if codesign:
                run([codesign, "-f", "-s", "-", str(fw_binary)])

            # Create a minimal stub so the dynamic linker is satisfied.
            stub_dir = products_dir / "JavaScriptCore_unused.framework" / "Versions" / "A"
            stub_dir.mkdir(parents=True, exist_ok=True)
            stub_src = stub_dir / "stub.c"
            stub_src.write_text("/* empty stub */\n", encoding="utf-8")
            if cc:
                run(
                    [cc, "-shared", "-o", str(stub_dir / "JavaScriptCore"),
                     str(stub_src),
                     "-install_name", stub_jsc_name],
                )
                if codesign:
                    run([codesign, "-f", "-s", "-", str(stub_dir / "JavaScriptCore")])
                stub_src.unlink(missing_ok=True)

    # Create symlink so the Zig executor (which looks for libwebgpu_dawn.dylib) can load it.
    compat_link = shim_dir / "libwebgpu_dawn.dylib"
    if compat_link.is_symlink() or compat_link.exists():
        compat_link.unlink()
    compat_link.symlink_to("libwebgpu_webkit_cshim.dylib")

    return shim_dylib


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap WebKit WebGPU (Metal) for Apple comparison workflows."
    )
    parser.add_argument("--repo-url", default=WEBKIT_REPO_URL)
    parser.add_argument(
        "--source-dir",
        default=DEFAULT_SOURCE_DIR,
        help="Where to place the WebKit sparse checkout.",
    )
    parser.add_argument(
        "--build-dir",
        default=DEFAULT_BUILD_DIR,
        help="Build output root used by Xcode for SYMROOT/BUILD_DIR.",
    )
    parser.add_argument(
        "--xcode-derived-data",
        default=DEFAULT_XCODE_DERIVED_DATA,
        help="Xcode DerivedData directory (must be writable).",
    )
    parser.add_argument(
        "--build-configuration",
        default=DEFAULT_BUILD_CONFIGURATION,
        choices=("Debug", "Release"),
        help="Xcode build configuration.",
    )
    parser.add_argument(
        "--branch",
        default="main",
        help="Branch or tag to check out.",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=os.cpu_count() or 4,
        help="Build parallelism.",
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Do not fetch/update the WebKit repository.",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Do not build after checkout.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Delete build directory before building.",
    )
    parser.add_argument(
        "--probe-only",
        action="store_true",
        help="Clone and check source layout, don't build.",
    )
    parser.add_argument(
        "--output-state",
        default=DEFAULT_OUTPUT_STATE,
        help="Output path for build metadata.",
    )
    return parser.parse_args()


def main() -> int:
    if sys.platform != "darwin":
        print("ERROR: bootstrap_webkit_webgpu.py is macOS-only (Metal backend)", file=sys.stderr)
        return 1

    args = parse_args()
    source_dir = Path(args.source_dir).resolve()
    build_dir = Path(args.build_dir).resolve()
    derived_data = Path(args.xcode_derived_data).resolve()
    out_state = Path(args.output_state).resolve()

    check_dependency("git")

    # Step 1: Clone / update.
    if args.rebuild and build_dir.exists():
        shutil.rmtree(build_dir)

    ensure_repo(source_dir, args.repo_url, args.branch, args.skip_fetch)

    # Step 2: Probe and validate checkout.
    probe = probe_webgpu_layout(source_dir)
    layout = validate_webgpu_layout(source_dir)
    print(f"Source probe: {json.dumps(probe, indent=2)}")

    if args.probe_only:
        write_json(out_state, {"phase": "probe", "probe": probe, "layout": layout})
        return 0

    if not probe["webgpu_dir_exists"] or not probe["xcode_project_exists"]:
        print("ERROR: Source/WebGPU and/or WebGPU.xcodeproj not present after checkout", file=sys.stderr)
        write_json(out_state, {"phase": "probe_failed", "probe": probe, "layout": layout})
        return 1

    # Step 3: Build.
    if args.skip_build:
        write_json(
            out_state,
            {
                "phase": "configured",
                "probe": probe,
                "layout": layout,
                "buildDir": str(build_dir),
                "derivedData": str(derived_data),
                "configuration": args.build_configuration,
            },
        )
        return 0

    build_library(source_dir, build_dir, args.parallel, args.build_configuration, derived_data)

    # Step 4: Locate library.
    lib_path = find_library(build_dir, derived_data, args.build_configuration)
    if lib_path is None:
        print("WARNING: Build completed but WebGPU framework/binary not found.", file=sys.stderr)
        print("Listing build artifacts for diagnosis:")
        for item in sorted(build_dir.rglob("*.framework")):
            print(f"  {item}")
        for item in sorted(build_dir.rglob("*.dylib")):
            print(f"  {item}")
        write_json(
            out_state,
            {
                "phase": "build_complete_no_library",
                "probe": probe,
                "layout": layout,
                "buildDir": str(build_dir),
                "derivedData": str(derived_data),
                "configuration": args.build_configuration,
            },
        )
        return 1

    # Step 5: Build C-linkage shim.
    shim_path = build_shim(source_dir, derived_data, args.build_configuration)

    manifest = {
        "phase": "ready",
        "repo": str(source_dir),
        "buildDir": str(build_dir),
        "derivedData": str(derived_data),
        "buildSystem": "xcode",
        "configuration": args.build_configuration,
        "branch": args.branch,
        "library": str(lib_path),
        "libraryRelative": str(lib_path.relative_to(build_dir)) if lib_path.is_relative_to(build_dir) else str(lib_path),
        "shimLibrary": str(shim_path) if shim_path else None,
        "probe": probe,
        "layout": layout,
    }
    write_json(out_state, manifest)
    print(f"\nWebKit WebGPU library ready: {lib_path}")
    if shim_path:
        print(f"C-linkage shim ready: {shim_path}")
    print(f"State written to: {out_state}")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

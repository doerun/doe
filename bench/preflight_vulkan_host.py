#!/usr/bin/env python3
"""Host preflight checks for local Vulkan benchmark lanes."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def run_check(*command: str) -> bool:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    return completed.returncode == 0


def check_render_node(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, f"missing render node: {path}"
    readable = os.access(path, os.R_OK)
    writable = os.access(path, os.W_OK)
    if readable and writable:
        return True, "ok"
    return (
        False,
        f"insufficient permissions on {path} (read={readable}, write={writable})",
    )


def check_render_group() -> tuple[bool, str]:
    groups = set(os.getgroups())
    groups.add(os.getgid())
    groups.add(os.getegid())
    try:
        import grp

        render_gid = grp.getgrnam("render").gr_gid
    except Exception:
        return False, "unable to resolve render group"
    return render_gid in groups, "ok" if render_gid in groups else "user is not in render group"


def check_vulkaninfo() -> tuple[bool, str]:
    vulkaninfo = shutil.which("vulkaninfo")
    if vulkaninfo is None:
        return False, "missing vulkaninfo binary"
    if not run_check("vulkaninfo", "--summary"):
        return False, "vulkaninfo --summary failed"
    return True, "ok"


def main() -> int:
    if sys.platform != "linux":
        print("FAIL: Vulkan preflight requires Linux host")
        return 1

    checks: list[tuple[str, bool, str]] = []

    render_node = Path("/dev/dri/renderD128")
    render_node_ok, render_node_msg = check_render_node(render_node)
    checks.append(("renderNodeAccess", render_node_ok, render_node_msg))

    render_group_ok, render_group_msg = check_render_group()
    checks.append(("renderGroupMembership", render_group_ok, render_group_msg))

    vulkaninfo_ok, vulkaninfo_msg = check_vulkaninfo()
    checks.append(("vulkaninfo", vulkaninfo_ok, vulkaninfo_msg))

    if shutil.which("ldconfig") is not None:
        checks.append(("vulkanLoaderPresent", run_check("ldconfig", "-p"), "ok"))
    else:
        checks.append(("vulkanLoaderPresent", True, "ok"))

    failed = [name for name, ok, _ in checks if not ok]
    ok_overall = len(failed) == 0

    print(f"preflight ok={ok_overall}")
    for name, state, message in checks:
        print(f"[{'ok' if state else 'fail'}] {name}: {message}")

    return 0 if ok_overall else 2


if __name__ == "__main__":
    raise SystemExit(main())

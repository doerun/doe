"""Exercise production timestamp bridge bodies with recording COM methods."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[4]
    here = Path(__file__).resolve().parent
    bridge_dir = root / "runtime/zig/src/backend/d3d12"
    bridge_path = bridge_dir / "d3d12_bridge.c"
    source = bridge_path.read_text()
    begin = source.index("int d3d12_bridge_queue_get_timestamp_frequency_checked")
    end = source.index("/* --- Map/Unmap --- */", begin)
    bodies = source[begin:end]
    fixture = (here / "bridge-probe-prefix.c").read_text() + bodies + (here / "bridge-probe-main.c").read_text()
    zig = os.environ.get("ZIG", "zig")
    with tempfile.TemporaryDirectory(prefix="doe-d3d12-timestamps-") as temporary:
        probe = Path(temporary) / "probe.c"
        executable = Path(temporary) / "probe"
        probe.write_text(fixture)
        subprocess.run([zig, "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", str(bridge_dir), str(probe), "-o", str(executable)], check=True)
        subprocess.run([str(executable)], check=True, timeout=10)
    print(json.dumps({"bridgeSha256": hashlib.sha256(bridge_path.read_bytes()).hexdigest(), "timestampBodiesSha256": hashlib.sha256(bodies.encode()).hexdigest(), "scope": "production C control flow with recording COM methods; not Windows ABI or GPU execution"}, sort_keys=True))


if __name__ == "__main__":
    main()

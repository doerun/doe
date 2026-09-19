"""Compile a private source copy with one artifact decision removed."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
ZIG = Path('/home/x/.local/zig/zig-x86_64-linux-0.15.2/zig')
with tempfile.TemporaryDirectory(prefix='doe-artifact-coverage-') as temp:
    root = Path(temp)
    shutil.copytree(ROOT / 'runtime/zig/src', root / 'src')
    (root / 'probe.zig').write_text('test { _ = @import("src/backend/common/artifact_policy.zig"); }\n')
    path = root / 'src/backend/common/artifact_policy.zig'
    original = path.read_text()
    command = [str(ZIG), 'test', str(root / 'probe.zig'), '-I', str(ROOT / 'runtime/zig/vendor/webgpu-headers'), '-lc']
    accepted = subprocess.run(command, capture_output=True, text=True)
    (OUT / 'exhaustive-original.log').write_text(accepted.stdout + accepted.stderr)
    if accepted.returncode:
        raise SystemExit('unmodified source failed: see exhaustive-original.log')
    path.write_text(original.replace('        .map_async,\n', '', 1))
    rejected = subprocess.run(command, capture_output=True, text=True)
    (OUT / 'exhaustive-omission.log').write_text(rejected.stdout + rejected.stderr)
    if not rejected.returncode or 'switch must handle all possibilities' not in rejected.stderr:
        raise SystemExit('omitted decision was not rejected as expected')
    print('PASS: unmodified policy compiles; omitting map_async fails exhaustive switching')

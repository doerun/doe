"""Copy tracked build inputs, including working changes, into review scratch."""
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
SCRATCH = HERE / "build-scratch"


def main() -> None:
    if SCRATCH.exists():
        raise FileExistsError(SCRATCH)
    paths = subprocess.check_output(
        ["git", "ls-files", "-z", "--", "runtime/zig", "runtime/bridge",
         "config", "pipeline/lean", "assets"], cwd=REPO, text=True,
    ).split("\0")
    for name in filter(None, paths):
        source = REPO / name
        if source.is_file():
            target = SCRATCH / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


if __name__ == "__main__":
    main()

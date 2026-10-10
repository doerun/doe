"""Install, verify, or qualify the pinned Doe ONNX/Vulkan evaluation package."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.dont_write_bytecode = True

from distribution import install, verify


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    installation = commands.add_parser("install", help="Install a verified archive")
    installation.add_argument("archive", type=Path, help="Evaluation tar.gz")
    installation.add_argument("--sha256", required=True, help="Expected archive digest")
    installation.add_argument(
        "--prefix", type=Path, required=True, help="New installation directory"
    )
    commands.add_parser("verify", help="Verify every installed file")
    for name in ("run", "qualify"):
        sub = commands.add_parser(
            name,
            help=(
                "Run SqueezeNet"
                if name == "run"
                else "Run installation acceptance and negative controls"
            ),
        )
        sub.add_argument(
            "--out",
            type=Path,
            required=True,
            help="New results directory outside the installation",
        )
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    if args.command == "install":
        install(args.archive, args.sha256, args.prefix)
        print(f"Installed {args.prefix.resolve()}")
        return 0
    manifest = verify(root)
    if args.command == "verify":
        print(f"Verified Doe ONNX evaluation {manifest['version']}")
        return 0
    from qualification import execute

    return 0 if execute(root, args.out, args.command == "qualify")["passed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as error:
        print(f"Doe ONNX: {error}", file=sys.stderr)
        raise SystemExit(1)

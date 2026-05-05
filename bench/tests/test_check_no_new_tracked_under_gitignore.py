from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL = REPO_ROOT / "bench/tools/check_no_new_tracked_under_gitignore.py"


class CheckNoNewTrackedUnderGitignoreTest(unittest.TestCase):
    """The gate uses real git invocations so it has to run inside a git
    worktree to give meaningful results. Each test sets up a tempdir with
    its own .git + .gitignore, then runs the tool with explicit path args
    so we exercise the gate's match logic without needing staged changes
    in the parent repo."""

    def _run(self, repo: Path, paths: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(TOOL), *paths],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )

    def _init_repo(self, repo: Path, gitignore_body: str) -> None:
        subprocess.run(
            ["git", "init", "-q", "-b", "main", str(repo)], check=True
        )
        (repo / ".gitignore").write_text(gitignore_body, encoding="utf-8")
        # Ensure there's an initial commit so HEAD exists; not strictly
        # needed since the tool only consults the index/staging area, but
        # keeps the worktree state realistic.
        subprocess.run(
            ["git", "-C", str(repo), "add", ".gitignore"], check=True
        )
        subprocess.run(
            [
                "git", "-C", str(repo),
                "-c", "user.email=test@example.com",
                "-c", "user.name=test",
                "commit", "-q", "-m", "initial",
            ],
            check=True,
        )

    def test_returns_zero_when_path_not_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._init_repo(repo, "bench/out/\n")
            (repo / "src").mkdir()
            (repo / "src/foo.py").write_text("# foo\n", encoding="utf-8")
            r = self._run(repo, ["src/foo.py"])
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_returns_one_when_path_matches_gitignore(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._init_repo(repo, "bench/out/\n")
            (repo / "bench/out").mkdir(parents=True)
            (repo / "bench/out/leak.json").write_text("{}\n", encoding="utf-8")
            r = self._run(repo, ["bench/out/leak.json"])
            self.assertEqual(r.returncode, 1)
            self.assertIn("bench/out/leak.json", r.stderr)
            self.assertIn(".gitignore", r.stderr)

    def test_returns_zero_when_invoked_with_no_args_and_nothing_staged(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._init_repo(repo, "bench/out/\n")
            r = self._run(repo, [])
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_mixed_args_fails_only_on_ignored_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._init_repo(repo, "bench/out/\n")
            (repo / "src").mkdir()
            (repo / "src/foo.py").write_text("# foo\n", encoding="utf-8")
            (repo / "bench/out").mkdir(parents=True)
            (repo / "bench/out/leak.json").write_text("{}\n", encoding="utf-8")
            r = self._run(repo, ["src/foo.py", "bench/out/leak.json"])
            self.assertEqual(r.returncode, 1)
            # Only the ignored path should appear in the error list, not
            # the clean one.
            self.assertIn("bench/out/leak.json", r.stderr)
            self.assertNotIn("src/foo.py", r.stderr)


if __name__ == "__main__":
    unittest.main()

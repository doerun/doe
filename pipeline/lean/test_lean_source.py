"""Tests for Lean source files in pipeline/lean/Doe/.

Validates:
  - All .lean files exist and are non-empty
  - Import consistency (referenced modules have corresponding files)
  - Generated contract file exists
  - No circular imports in the top-level import DAG
  - Optional: Lean typecheck if toolchain is available
"""

import os
import re
import shutil
import subprocess
import unittest
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LEAN_DIR = REPO_ROOT / "pipeline" / "lean" / "Doe"


def _find_lean_files():
    """Return all .lean files under LEAN_DIR."""
    return sorted(LEAN_DIR.rglob("*.lean"))


def _file_to_module(lean_file):
    """Convert a .lean file path to its Lean module name.

    e.g. .../Doe/Core/Model.lean -> Doe.Core.Model
    """
    rel = lean_file.relative_to(LEAN_DIR.parent)
    parts = rel.with_suffix("").parts
    return ".".join(parts)


def _parse_imports(lean_file):
    """Extract import statements from a .lean file.

    Returns a list of module names (e.g. ['Doe.Core.Model']).
    """
    imports = []
    import_pattern = re.compile(r"^\s*import\s+([\w.]+)")
    with open(lean_file, encoding="utf-8") as f:
        for line in f:
            m = import_pattern.match(line)
            if m:
                imports.append(m.group(1))
    return imports


def _build_import_graph():
    """Build a directed graph: module -> list of imported modules.

    Only includes imports within the Doe namespace.
    """
    graph = defaultdict(list)
    for lean_file in _find_lean_files():
        module = _file_to_module(lean_file)
        for imp in _parse_imports(lean_file):
            if imp.startswith("Doe."):
                graph[module].append(imp)
    return graph


def _has_cycle(graph):
    """Detect cycles in a directed graph using iterative DFS.

    Returns (has_cycle, cycle_path) where cycle_path is a list of
    module names forming the cycle, or empty if no cycle.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color = defaultdict(int)

    all_nodes = set(graph.keys())
    for targets in graph.values():
        all_nodes.update(targets)

    for start in all_nodes:
        if color[start] != WHITE:
            continue
        # Iterative DFS with path tracking
        stack = [(start, iter(graph.get(start, [])))]
        path = [start]
        color[start] = GRAY
        while stack:
            node, children = stack[-1]
            try:
                child = next(children)
                if color[child] == GRAY:
                    # Found a cycle: extract the cycle from path
                    cycle_start = path.index(child)
                    return True, path[cycle_start:] + [child]
                if color[child] == WHITE:
                    color[child] = GRAY
                    path.append(child)
                    stack.append((child, iter(graph.get(child, []))))
            except StopIteration:
                color[node] = BLACK
                stack.pop()
                path.pop()

    return False, []


def _lean_toolchain_available():
    """Check if lean is available on PATH."""
    return shutil.which("lean") is not None


class TestLeanFilesExistAndNonEmpty(unittest.TestCase):
    """All .lean files exist and are non-empty."""

    def test_lean_files_found(self):
        files = _find_lean_files()
        self.assertGreater(
            len(files),
            0,
            f"No .lean files found under {LEAN_DIR}",
        )

    def test_all_lean_files_non_empty(self):
        empty = []
        for lean_file in _find_lean_files():
            if lean_file.stat().st_size == 0:
                empty.append(str(lean_file))
        self.assertFalse(
            empty,
            f"Empty .lean files: {empty}",
        )

    def test_all_lean_files_valid_utf8(self):
        failures = []
        for lean_file in _find_lean_files():
            try:
                lean_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                failures.append(str(lean_file))
        self.assertFalse(
            failures,
            f".lean files with invalid UTF-8: {failures}",
        )

    @unittest.skipUnless(_lean_toolchain_available(), "Lean toolchain not installed")
    def test_lean_typecheck(self):
        """If lean is available, typecheck each file."""
        check_script = REPO_ROOT / "pipeline" / "lean" / "check.sh"
        if not check_script.exists():
            self.skipTest("check.sh not found; cannot run typecheck")
        result = subprocess.run(
            [str(check_script)],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(REPO_ROOT),
        )
        self.assertEqual(
            result.returncode,
            0,
            f"Lean typecheck failed:\nstdout: {result.stdout[:2000]}\n"
            f"stderr: {result.stderr[:2000]}",
        )


class TestImportConsistency(unittest.TestCase):
    """Each .lean file's imports reference files that exist."""

    def test_all_imports_resolve_to_files(self):
        missing = []
        for lean_file in _find_lean_files():
            module = _file_to_module(lean_file)
            for imp in _parse_imports(lean_file):
                if not imp.startswith("Doe."):
                    # Skip non-project imports (e.g. Mathlib, Init)
                    continue
                imp_path = imp.replace(".", "/") + ".lean"
                full_path = LEAN_DIR.parent / imp_path
                if not full_path.exists():
                    missing.append((module, imp, str(full_path)))
        self.assertFalse(
            missing,
            "Imports reference non-existent .lean files:\n"
            + "\n".join(
                f"  {src} imports {target} (expected {path})"
                for src, target, path in missing
            ),
        )

    def test_no_self_imports(self):
        self_imports = []
        for lean_file in _find_lean_files():
            module = _file_to_module(lean_file)
            for imp in _parse_imports(lean_file):
                if imp == module:
                    self_imports.append(module)
        self.assertFalse(
            self_imports,
            f"Files that import themselves: {self_imports}",
        )


class TestGeneratedContractFile(unittest.TestCase):
    """Doe/Generated/ComparabilityContract.lean exists and is non-empty."""

    def test_file_exists(self):
        contract = LEAN_DIR / "Generated" / "ComparabilityContract.lean"
        self.assertTrue(
            contract.exists(),
            f"Generated contract file not found at {contract}",
        )

    def test_file_non_empty(self):
        contract = LEAN_DIR / "Generated" / "ComparabilityContract.lean"
        if not contract.exists():
            self.skipTest("Contract file does not exist")
        self.assertGreater(
            contract.stat().st_size,
            0,
            "Generated contract file is empty",
        )

    def test_file_contains_contract_hash(self):
        """The generated file should contain the comparability contract SHA."""
        contract = LEAN_DIR / "Generated" / "ComparabilityContract.lean"
        if not contract.exists():
            self.skipTest("Contract file does not exist")
        content = contract.read_text(encoding="utf-8")
        self.assertIn(
            "comparabilityContractSha256",
            content,
            "Generated contract file does not contain comparabilityContractSha256",
        )

    def test_file_defines_obligation_id(self):
        """The generated file should define ComparabilityObligationId."""
        contract = LEAN_DIR / "Generated" / "ComparabilityContract.lean"
        if not contract.exists():
            self.skipTest("Contract file does not exist")
        content = contract.read_text(encoding="utf-8")
        self.assertIn(
            "ComparabilityObligationId",
            content,
            "Generated contract file does not define ComparabilityObligationId",
        )


class TestNoCircularImports(unittest.TestCase):
    """Verify import DAG is acyclic."""

    def test_no_cycles_in_import_graph(self):
        graph = _build_import_graph()
        has_cycle, cycle_path = _has_cycle(graph)
        self.assertFalse(
            has_cycle,
            f"Circular import detected: {' -> '.join(cycle_path)}",
        )

    def test_import_graph_has_edges(self):
        """Sanity: the graph should have some edges (imports exist)."""
        graph = _build_import_graph()
        total_edges = sum(len(v) for v in graph.values())
        self.assertGreater(
            total_edges,
            0,
            "Import graph has no edges; import parsing may be broken",
        )


class TestModuleCoverage(unittest.TestCase):
    """Cross-check that key modules exist as files."""

    EXPECTED_MODULES = [
        "Doe.Core.Model",
        "Doe.Core.Runtime",
        "Doe.Core.Dispatch",
        "Doe.Core.Bridge",
        "Doe.Full.Comparability",
        "Doe.Full.ComparabilityFixtures",
        "Doe.Full.WorkloadGeometry",
        "Doe.Shader.ComputeBounds",
        "Doe.Generated.ComparabilityContract",
        "Doe.Extract",
    ]

    def test_expected_modules_exist(self):
        missing = []
        for module in self.EXPECTED_MODULES:
            rel_path = module.replace(".", "/") + ".lean"
            full_path = LEAN_DIR.parent / rel_path
            if not full_path.exists():
                missing.append(module)
        self.assertFalse(
            missing,
            f"Expected Lean modules missing: {missing}",
        )


if __name__ == "__main__":
    unittest.main()

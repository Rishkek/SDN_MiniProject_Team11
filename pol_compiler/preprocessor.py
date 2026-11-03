"""
Preprocessor for Prototype.pol files.
Resolves and inlines 'include' statements, loading .pollib libraries with cycle detection.
"""

import os
from typing import List, Set, Dict, Optional
from pol_compiler.lexer import Lexer
from pol_compiler.parser import Parser
from pol_compiler.ast_nodes import ProgramNode, IncludeNode, ASTNode


class PreprocessorError(ValueError):
    """Raised when an include file cannot be found or a circular dependency is detected."""
    pass


class Preprocessor:
    """Recursively resolves all includes in Prototype.pol source files."""

    def __init__(self, search_paths: Optional[List[str]] = None):
        self.search_paths = search_paths or ["lib", ".", "pol_src"]
        self.loaded_files: Set[str] = set()
        self.in_progress: Set[str] = set()

    def resolve_target_path(self, target: str, current_dir: str = ".") -> str:
        # 1. Check for standard library targets like 'lib.machine' -> 'lib/machine.pollib'
        if target.startswith("lib."):
            lib_sub = target[4:] + ".pollib"
            for p in self.search_paths:
                candidate = os.path.join(p, lib_sub)
                if os.path.isfile(candidate):
                    return os.path.abspath(candidate)
            # Try workspace root 'lib/'
            root_lib = os.path.join("lib", lib_sub)
            if os.path.isfile(root_lib):
                return os.path.abspath(root_lib)

        # 2. Check direct path relative to current_dir
        direct = os.path.join(current_dir, target)
        if os.path.isfile(direct):
            return os.path.abspath(direct)

        # 3. Check with .pollib extension if not provided
        if not target.endswith(".pollib") and not target.endswith(".pol"):
            cand_pollib = os.path.join(current_dir, target + ".pollib")
            if os.path.isfile(cand_pollib):
                return os.path.abspath(cand_pollib)

        # 4. Search in search_paths
        for p in self.search_paths:
            cand = os.path.join(p, target)
            if os.path.isfile(cand):
                return os.path.abspath(cand)
            if not target.endswith(".pollib"):
                cand2 = os.path.join(p, target + ".pollib")
                if os.path.isfile(cand2):
                    return os.path.abspath(cand2)

        raise PreprocessorError(f"Cannot resolve include target '{target}' from '{current_dir}'")

    def load_and_preprocess(self, filepath: str) -> ProgramNode:
        abs_path = os.path.abspath(filepath)
        if not os.path.isfile(abs_path):
            raise FileNotFoundError(f"Source file not found: {filepath}")

        if abs_path in self.in_progress:
            raise PreprocessorError(f"Circular include detected for: {abs_path}")

        if abs_path in self.loaded_files:
            return ProgramNode(statements=[])

        self.in_progress.add(abs_path)
        current_dir = os.path.dirname(abs_path)

        with open(abs_path, "r", encoding="utf-8") as f:
            source = f.read()

        lexer = Lexer(source, filepath=abs_path)
        tokens = lexer.tokenize()
        parser = Parser(tokens, filepath=abs_path)
        ast = parser.parse()

        merged_statements: List[ASTNode] = []

        for stmt in ast.statements:
            if isinstance(stmt, IncludeNode):
                included_path = self.resolve_target_path(stmt.target, current_dir=current_dir)
                if included_path not in self.loaded_files:
                    inc_ast = self.load_and_preprocess(included_path)
                    merged_statements.extend(inc_ast.statements)
            else:
                merged_statements.append(stmt)

        self.in_progress.remove(abs_path)
        self.loaded_files.add(abs_path)
        return ProgramNode(statements=merged_statements)

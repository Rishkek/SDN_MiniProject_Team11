"""
Prototype.pol Compiler Package (TopoNet Compiler).
Compiles .pol source files and .pollib libraries to .json topologies.
"""

from pol_compiler.ast_nodes import ProgramNode, ASTNode
from pol_compiler.lexer import Lexer, LexerError
from pol_compiler.parser import Parser, ParserError
from pol_compiler.preprocessor import Preprocessor, PreprocessorError
from pol_compiler.semantic import SemanticAnalyzer, SemanticError, TopologyIR
from pol_compiler.layout import compute_topology_layout
from pol_compiler.compiler import PolCompiler


def compile_pol_file(source_path: str, output_path: str = None, topology_type: str = "auto"):
    """Convenience helper to compile a .pol source file to .json."""
    compiler = PolCompiler()
    return compiler.compile_file(source_path, output_path=output_path, topology_type=topology_type)


__all__ = [
    "PolCompiler",
    "compile_pol_file",
    "Lexer",
    "LexerError",
    "Parser",
    "ParserError",
    "Preprocessor",
    "PreprocessorError",
    "SemanticAnalyzer",
    "SemanticError",
    "TopologyIR",
    "compute_topology_layout",
]

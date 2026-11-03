"""
Abstract Syntax Tree (AST) node definitions for the Prototype.pol language.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict, Tuple


@dataclass
class ASTNode:
    line: int = 1
    col: int = 1


@dataclass
class IncludeNode(ASTNode):
    target: str = ""


@dataclass
class DefineNode(ASTNode):
    symbol: str = ""
    target_type: str = ""
    is_unique: bool = False
    is_common: bool = False


@dataclass
class GridDirectiveNode(ASTNode):
    state: str = "OFF"  # 'ON' or 'OFF'


@dataclass
class UnitDefNode(ASTNode):
    unit_name: str = ""
    value_expr: Any = 1


@dataclass
class DataDeclNode(ASTNode):
    var_name: str = ""
    capacity_expr: Optional[Any] = None


@dataclass
class DataOpNode(ASTNode):
    op: str = "define"  # 'define', 'in', 'out', 'flow'
    var_name: str = ""
    value_expr: Any = None


@dataclass
class FieldAssignNode(ASTNode):
    target: str = ""
    field_name: str = ""
    arg: Optional[str] = None
    value_expr: Any = None


@dataclass
class MacroParam:
    type_name: str
    param_name: str


@dataclass
class MacroDefNode(ASTNode):
    return_type: str = ""
    name: str = ""
    params: List[MacroParam] = field(default_factory=list)
    body: List[ASTNode] = field(default_factory=list)


@dataclass
class MacroCallNode(ASTNode):
    name: str = ""
    args: List[Any] = field(default_factory=list)


@dataclass
class InstanceNode(ASTNode):
    name: str = ""


@dataclass
class DetailNode(ASTNode):
    target: str = ""
    body: List[ASTNode] = field(default_factory=list)
    instances: List[str] = field(default_factory=list)


@dataclass
class BundleDeclNode(ASTNode):
    element_type: str = "machine"
    name: str = "bundle"
    capacity: int = 16


@dataclass
class SpawnNode(ASTNode):
    type_name: str = ""
    count: Any = 1  # int or 'var'
    alias: str = ""


@dataclass
class SpawnsBlockNode(ASTNode):
    spawns: List[SpawnNode] = field(default_factory=list)
    bundle_target: Optional[str] = None
    padding: int = 0


@dataclass
class ConnectTupleNode(ASTNode):
    src: str = ""
    cable: str = ""
    dst: str = ""


@dataclass
class ConnectionsBlockNode(ASTNode):
    unpack_target: Optional[str] = None
    connections: List[ConnectTupleNode] = field(default_factory=list)


@dataclass
class DeployNode(ASTNode):
    layout_target: str = ""


@dataclass
class ProgramNode(ASTNode):
    statements: List[ASTNode] = field(default_factory=list)

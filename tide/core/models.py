"""Core stack data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class EdgeSource(StrEnum):
    PR = "pr"
    REMOTE = "remote"
    HEURISTIC = "heuristic"


@dataclass(frozen=True, slots=True)
class BranchNode:
    name: str
    local: bool = True
    remote: bool = False


@dataclass(frozen=True, slots=True)
class StackEdge:
    child: str
    parent: str
    source: EdgeSource


@dataclass(slots=True)
class StackGraph:
    nodes: dict[str, BranchNode] = field(default_factory=dict)
    parents: dict[str, StackEdge] = field(default_factory=dict)

    def add_node(self, node: BranchNode) -> None:
        self.nodes[node.name] = node

    def add_edge(self, edge: StackEdge) -> None:
        self.parents[edge.child] = edge

    def children(self) -> dict[str, list[StackEdge]]:
        out: dict[str, list[StackEdge]] = {}
        for edge in self.parents.values():
            out.setdefault(edge.parent, []).append(edge)
        for child_edges in out.values():
            child_edges.sort(key=lambda e: e.child)
        return out

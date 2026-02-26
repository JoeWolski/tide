"""Stack inference and deterministic rendering helpers."""

from __future__ import annotations

from dataclasses import dataclass

from tide.core.models import BranchNode, EdgeSource, StackEdge, StackGraph


@dataclass(slots=True)
class InferenceInput:
    branches: list[BranchNode]
    pr_edges: list[tuple[str, str]]
    remote_edges: list[tuple[str, str]]
    heuristic_edges: list[tuple[str, str]]


class StackInferer:
    """Infers a branch DAG with source-priority edge selection."""

    @staticmethod
    def infer(data: InferenceInput) -> StackGraph:
        graph = StackGraph()
        for branch in sorted(data.branches, key=lambda b: b.name):
            graph.add_node(branch)

        def apply(edges: list[tuple[str, str]], source: EdgeSource) -> None:
            for child, parent in sorted(edges):
                if child not in graph.nodes or parent not in graph.nodes:
                    continue
                if child in graph.parents:
                    continue
                if child == parent:
                    continue
                if StackInferer._introduces_cycle(graph, child=child, parent=parent):
                    continue
                graph.add_edge(StackEdge(child=child, parent=parent, source=source))

        apply(data.pr_edges, EdgeSource.PR)
        apply(data.remote_edges, EdgeSource.REMOTE)
        apply(data.heuristic_edges, EdgeSource.HEURISTIC)
        return graph

    @staticmethod
    def _introduces_cycle(graph: StackGraph, *, child: str, parent: str) -> bool:
        cur = parent
        seen: set[str] = set()
        while cur not in seen:
            if cur == child:
                return True
            seen.add(cur)
            edge = graph.parents.get(cur)
            if edge is None:
                return False
            cur = edge.parent
        return True


def path_to_root(graph: StackGraph, branch: str) -> list[str]:
    out: list[str] = []
    cur = branch
    seen: set[str] = set()
    while cur in graph.nodes and cur not in seen:
        out.append(cur)
        seen.add(cur)
        edge = graph.parents.get(cur)
        if edge is None:
            break
        cur = edge.parent
    return out

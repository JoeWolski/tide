"""Deterministic tree and status rendering."""

from __future__ import annotations

import json

from tide.core.models import EdgeSource, StackGraph


def render_tree(graph: StackGraph, trunk: str) -> str:
    children = graph.children()
    lines: list[str] = []

    def visit(node: str, prefix: str) -> None:
        lines.append(prefix + node)
        for edge in children.get(node, []):
            marker = "*" if edge.source == EdgeSource.HEURISTIC else ""
            visit(edge.child + marker, prefix + "  ")

    visit(trunk, "")
    return "\n".join(lines)


def render_json(graph: StackGraph) -> str:
    payload = {
        "nodes": sorted(graph.nodes),
        "edges": [
            {"child": edge.child, "parent": edge.parent, "source": edge.source.value}
            for edge in sorted(graph.parents.values(), key=lambda e: (e.parent, e.child))
        ],
    }
    return json.dumps(payload, sort_keys=True)


def render_status(branches: list[str]) -> str:
    return "\n".join(sorted(branches))

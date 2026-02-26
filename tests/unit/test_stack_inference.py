from tide.core.models import BranchNode, EdgeSource
from tide.core.stack import InferenceInput, StackInferer


def test_edge_priority_prefers_pr_then_remote_then_heuristic() -> None:
    branches = [BranchNode("main"), BranchNode("a"), BranchNode("b")]
    graph = StackInferer.infer(
        InferenceInput(
            branches=branches,
            pr_edges=[("a", "main")],
            remote_edges=[("a", "b"), ("b", "main")],
            heuristic_edges=[("a", "b")],
        )
    )

    assert graph.parents["a"].parent == "main"
    assert graph.parents["a"].source == EdgeSource.PR
    assert graph.parents["b"].parent == "main"
    assert graph.parents["b"].source == EdgeSource.REMOTE


def test_infer_skips_edges_that_would_create_cycles() -> None:
    branches = [BranchNode("main"), BranchNode("a"), BranchNode("b")]
    graph = StackInferer.infer(
        InferenceInput(
            branches=branches,
            pr_edges=[("a", "b"), ("b", "a")],
            remote_edges=[],
            heuristic_edges=[],
        )
    )

    assert graph.parents["a"].parent == "b"
    assert "b" not in graph.parents

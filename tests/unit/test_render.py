from tide.core.models import BranchNode
from tide.core.stack import InferenceInput, StackInferer
from tide.tui.render import render_tree


def test_tree_renderer_marks_heuristic_edges() -> None:
    graph = StackInferer.infer(
        InferenceInput(
            branches=[BranchNode("main"), BranchNode("a")],
            pr_edges=[],
            remote_edges=[],
            heuristic_edges=[("a", "main")],
        )
    )
    assert render_tree(graph, trunk="main") == "main\n  a*"

"""High-level deterministic stack operations."""

from __future__ import annotations

from dataclasses import dataclass

from tide.config.settings import TideConfig
from tide.core.errors import AmbiguityError, ConflictError, InputError
from tide.core.models import BranchNode, StackGraph
from tide.core.stack import InferenceInput, StackInferer, path_to_root
from tide.forge.base import PullRequest
from tide.forge.local import LocalForgeProvider
from tide.git.repo import GitRepo


@dataclass(slots=True)
class StackService:
    repo: GitRepo
    config: TideConfig
    forge: LocalForgeProvider

    def infer_graph(self) -> StackGraph:
        branches = [
            BranchNode(name=name, local=True, remote=False)
            for name in self.repo.list_local_branches()
        ]
        names = [branch.name for branch in branches]
        pr_edges: list[tuple[str, str]] = []
        remote_edges: list[tuple[str, str]] = []
        heuristic_edges: list[tuple[str, str]] = []

        prs = self.forge.list_prs_sync(names)
        for pr in prs:
            if pr.head in names and pr.base in names:
                pr_edges.append((pr.head, pr.base))

        for branch in names:
            hint = self.repo.branch_parent_hint(branch)
            if hint is not None and hint in names:
                remote_edges.append((branch, hint))

        trunk = self.config.trunk
        for branch in names:
            if branch == trunk:
                continue
            parent = self._best_ancestor_parent(branch, names)
            if parent is not None:
                heuristic_edges.append((branch, parent))

        return StackInferer.infer(
            InferenceInput(
                branches=branches,
                pr_edges=pr_edges,
                remote_edges=remote_edges,
                heuristic_edges=heuristic_edges,
            )
        )

    def _best_ancestor_parent(self, branch: str, names: list[str]) -> str | None:
        candidates: list[tuple[int, str]] = []
        for candidate in names:
            if candidate == branch:
                continue
            if not self.repo.is_ancestor(candidate, branch):
                continue
            distance = self.repo.rev_distance(candidate, branch)
            candidates.append((distance, candidate))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1]))
        return candidates[0][1]

    def parent_of(self, graph: StackGraph, branch: str) -> str | None:
        edge = graph.parents.get(branch)
        if edge is None:
            return None
        return edge.parent

    def children_of(self, graph: StackGraph, branch: str) -> list[str]:
        children = [edge.child for edge in graph.children().get(branch, [])]
        children.sort()
        return children

    def resolve_path_to_trunk(self, graph: StackGraph, start: str) -> list[str]:
        path = path_to_root(graph, start)
        trunk = self.config.trunk
        if trunk not in path:
            raise InputError(f"branch '{start}' has no path to trunk '{trunk}'")
        return path[: path.index(trunk) + 1]

    def resolve_scope(self, graph: StackGraph, selector: str, scope: str) -> list[str]:
        if selector not in graph.nodes:
            raise InputError(f"unknown branch selector: {selector}")
        if scope == "path":
            return self.resolve_path_to_trunk(graph, selector)
        if scope == "subtree":
            return self._subtree(graph, selector)
        if scope == "component":
            return self._component(graph, selector)
        raise InputError(f"unknown scope: {scope}")

    def _subtree(self, graph: StackGraph, root: str) -> list[str]:
        out: list[str] = []
        queue: list[str] = [root]
        while queue:
            node = queue.pop(0)
            out.append(node)
            queue.extend(self.children_of(graph, node))
        return sorted(set(out))

    def _component(self, graph: StackGraph, node: str) -> list[str]:
        undirected: dict[str, set[str]] = {name: set() for name in graph.nodes}
        for edge in graph.parents.values():
            undirected[edge.child].add(edge.parent)
            undirected[edge.parent].add(edge.child)

        out: set[str] = set()
        queue = [node]
        while queue:
            cur = queue.pop(0)
            if cur in out:
                continue
            out.add(cur)
            queue.extend(sorted(undirected[cur] - out))
        return sorted(out)

    def choose_single_child(self, graph: StackGraph, branch: str) -> str:
        children = self.children_of(graph, branch)
        if not children:
            raise InputError(f"no child branch from '{branch}'")
        if len(children) > 1:
            raise AmbiguityError(
                f"multiple child branches from '{branch}': {', '.join(children)}; use tide goto"
            )
        return children[0]

    def conflict_from_git_failure(
        self,
        *,
        operation: str,
        branches: list[str],
        fallback_files: list[str] | None = None,
    ) -> ConflictError:
        files = self.repo.conflicted_files()
        if not files:
            files = sorted(fallback_files or [])
        return ConflictError(operation=operation, branches=branches, files=files)

    def ensure_mergeable(self, branches: list[str]) -> None:
        prs = {pr.head: pr for pr in self.forge.list_prs_sync(branches)}
        bad: list[str] = []
        for branch in branches:
            pr = prs.get(branch)
            if pr is not None and pr.mergeable is False:
                bad.append(branch)
        if bad:
            raise InputError(f"non-mergeable PRs: {', '.join(sorted(bad))}")

    def missing_prs(self, branches: list[str]) -> list[str]:
        prs = {pr.head: pr for pr in self.forge.list_prs_sync(branches)}
        return sorted(branch for branch in branches if branch not in prs)

    def create_missing_prs(
        self,
        graph: StackGraph,
        branches: list[str],
        draft: bool = True,
    ) -> list[PullRequest]:
        created: list[PullRequest] = []
        existing = {pr.head: pr for pr in self.forge.list_prs_sync(branches)}
        for branch in sorted(branches):
            if branch == self.config.trunk or branch in existing:
                continue
            parent = self.parent_of(graph, branch)
            if parent is None:
                raise InputError(f"cannot create PR for '{branch}' without inferred base")
            created.append(
                self.forge.create_pr_sync(
                    head=branch,
                    base=parent,
                    title=f"{branch}",
                    body=f"Auto-generated by tide for branch {branch}",
                    draft=draft,
                )
            )
        return created

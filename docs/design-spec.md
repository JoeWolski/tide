# Tide — Design Specification

## Overview

Tide is a fast, deterministic, transaction-safe, extensible Python CLI tool for managing stacked feature branches and pull requests.

Core principles:

- **Git state is the source of truth.**
- **Every command is transactional and fully reversible locally.**
- **All commands support non-interactive execution.**
- **High performance, deterministic behavior.**
- **Extensible architecture (forge providers, transports, UI frontends, plugins).**
- **Comprehensive unit and integration test coverage.**

Tide must work even if all Tide-specific metadata is deleted. It must reconstruct stacks from local and remote Git state and forge metadata.

---

# 1. Core Architecture

## 1.1 Project Structure

```
tide/
cli/
core/
git/
forge/
tui/
config/
storage/
plugins/
tests/
unit/
integration/
golden/
```

## 1.2 Technology

- Python 3.11+
- Click for CLI
- asyncio for concurrent network operations
- pytest for testing
- ruff + black formatting
- mypy or pyright type checking
- TOML config
- platformdirs for config paths

---

# 2. Fundamental Principles

## 2.1 Git Is Source of Truth

Tide must infer stacks from:

1. PR metadata (primary source)
2. Remote branch relationships
3. Git ancestry heuristics (offline fallback)

Tide may cache data for speed but must never depend on cache correctness.

If Tide is deleted and reinstalled, users must resume immediately.

---

## 2.2 Transaction Safety

Every mutating command runs inside a transaction.

### Snapshot must include:

- Current HEAD state
- All local branch refs
- Index state
- Working tree changes
- Untracked files
- Worktrees
- Stashes
- Sparse checkout configuration
- Submodule states (including dirty state)

### Rollback Requirements

If any failure occurs:

- Repository state must be byte-for-byte identical to pre-command state.
- All created branches/worktrees must be removed.
- All modified refs restored.
- Submodules restored.
- Untracked files restored.

SIGINT/SIGTERM must trigger rollback.

---

# 3. Stack Model

## 3.1 Graph Representation

Stacks are represented as a DAG:

- Node = branch ref (local or remote)
- Edge = "A is based on B"

A stack is a connected component in this graph.

Supports:

- Linear stacks
- Trees with branching at any node
- Mixed local/remote-only branches

---

## 3.2 Edge Inference Priority

1. PR metadata (head → base)
2. Remote tracking configuration
3. Git ancestry heuristics

Heuristic edges must be marked as such in UI.

---

## 3.3 Branching Stacks

Stacks may branch at non-trunk nodes.

`tide show` must render full tree structure.

Landing operates on:

- Path from selected PR to trunk (default)
- Subtree (explicit)
- Full component (explicit)

---

# 4. Branch Naming

## 4.1 Template Configuration

Config key:

```
naming.branch_template = "$USER/$STACK/$FEATURE"
```

### Required Rule

Template must include `$FEATURE`.

Validation occurs on config load and set.

### Supported Tokens

- `$USER`
- `$STACK`
- `$FEATURE` (required)
- `$DATE`
- `$N`
- `$BASE`

Slugification must guarantee valid Git ref names.

Naming is ergonomic only — never authoritative.

---

# 5. Commands

## 5.1 Stack Manipulation

### tide add

Create new entry on current stack.

Supports:

- Automatic branch naming
- Dirty handling (`--dirty`)
- Non-interactive mode

---

### tide up / down / goto

Navigate stack entries.

Default dirty mode: `move`.

Options:

```
--dirty=fail|stash|move
--conflict=rollback|interactive|pause
```

---

### tide ripple

Propagate changes upward.

Default strategy: rebase.

Configurable:

```
stack.ripple.strategy = rebase|merge|cherry-pick
```

Default conflict mode: rollback.

---

### tide apply

Apply current changes to another entry.

Uses temporary worktrees.

Patch-based transfer.

Optional ripple.

---

## 5.2 PR Commands

### tide pr create

Automatically create missing PRs for stack path/subtree.

Example:

```
tide pr create --stack <selector> --scope path --head-pr <pr>
```

Configurable:

- Draft mode
- Title/body templates

---

### tide land

Land stacked PRs.

Landing modes:

- `squash-each` (default)
- `close-non-head`

Future:

- merge-queue bundle mode

---

### Land Validation

If missing PRs:

- Fail with non-zero exit
- List missing branches
- Print exact `tide pr create` command to fix

---

# 6. Conflict Handling

Default: rollback.

On conflict:

- Abort git operation
- Capture conflicted file list
- Rollback fully
- Print deterministic summary:
- operation
- branches involved
- conflicted files
- rerun command

Exit code: 4

JSON mode must include:

```
{
"error": "conflict",
"files": [...]
}
```

---

# 7. Landing Semantics

Landing operates on resolved path.

Before merging:

1. Resolve stack path.
2. Validate all PRs exist.
3. Validate mergeable state.
4. Perform merge/close sequence.

Tide does not enforce check policy.

Forge enforces branch protection.

---

# 8. Forge Layer

## 8.1 Provider Interface

```
ForgeProvider
ForgeTransport
```

### GitHub First

Supports:

- REST
- GraphQL

Config:

```
forge.provider = "github"
forge.github.transport = "graphql"
forge.github.auth = "gh"
```

Auth providers:

- gh CLI (default)
- Environment token
- Keyring
- Manual

Extensible for GitLab and Bitbucket.

---

# 9. Show / Status

## tide show

Tree view:

- Trunk at root
- Branch tree
- PR numbers
- Checks summary
- Review summary
- Local/remote markers
- Divergence indicators

Formats:

- tree (default)
- json

---

## tide status

Scriptable flat view.

---

# 10. Configuration

## Locations

- User config via platformdirs
- Repo override in `.git/tide/config.toml`

## Major Keys

```
repo.trunk
naming.branch_template
stack.ripple.strategy
dirty.default
conflict.mode
forge.provider
forge.github.transport
forge.github.auth
collab.mode
auto_update.channel
```

---

# 11. Collaboration

Default: fork model.

Config:

```
collab.mode = fork|direct
```

Commands:

- tide checkout
- tide push
- tide sync

Must support mixed local/remote stacks.

---

# 12. Auto Update

Bootstrap executable:

- Checks update channel:
- master
- release
- off

Config:

```
auto_update.channel = release|master|off
auto_update.ttl_seconds
```

Update must be atomic.

---

# 13. Worktrees and Submodules

Temporary worktrees used for destructive operations.

Transaction snapshot must include:

- Worktrees
- Submodules
- Sparse checkout
- Dirty states

Rollback must restore all.

---

# 14. Exit Codes

| Code | Meaning |
|------|--------|
| 0 | Success |
| 2 | Input/config error |
| 3 | Git failure |
| 4 | Conflict (rolled back) |
| 5 | Forge/auth/network failure |
| 6 | Ambiguity without flags |

---

# 15. Performance

- Single-pass repo scan
- Async parallel PR metadata retrieval
- No parallel git writes
- Cache invalidation keyed by commit ids

---

# 16. Testing Requirements

## Unit Tests

- Stack inference
- Naming validation
- Config precedence
- Renderer golden tests
- Transaction rollback

## Integration Tests

- Temp git repos
- Ripple conflict → full rollback
- Submodule rollback
- Missing PR detection

## Determinism Tests

- Same command twice → same output ordering

---

# 17. Non-Interactive Guarantees

Every command must:

- Support `--yes`
- Support `--json`
- Avoid blocking prompts
- Provide deterministic exit codes

---

# 18. Future Extensions

- Merge queue bundle mode
- Local verification of checks (`tide verify`)
- Smarter conflict resolution helpers
- Advanced PR batching strategies

---

# Summary

Tide is:

- Git-native
- Transaction-safe
- Forge-aware
- Stack-graph driven
- Fully reversible
- Deterministic
- Extensible
- Scriptable
- Thoroughly tested

This document defines the authoritative implementation specification.

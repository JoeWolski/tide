# tide

`tide` is a deterministic CLI for stacked branch and PR workflows.

This README is user-focused: every section is about running Tide in a concrete situation. It assumes your repository, remote, and forge auth are already set up.

## Mental Model

Tide infers your stack from real git/remote/PR state. It does not require Tide metadata to function.

- Local stack state: your local branches and HEAD.
- Remote stack state: remote-tracking branches and upstream relationships.
- Project/PR state: pull requests on your forge.

Inference priority:

1. PR metadata (head -> base)
2. Remote tracking relationships
3. Git ancestry heuristics (marked in UI)

## Default Behavior You Can Rely On

- Mutating commands are transactional.
- On conflict, default behavior is full rollback.
- Deterministic exit codes are used for scripting.
- `--json` and `--yes` are available for non-interactive automation.

Exit codes:

- `0`: success
- `2`: input/config error
- `3`: git failure
- `4`: conflict
- `5`: forge/auth/network failure
- `6`: ambiguous operation requiring explicit flags

## Situation: You Need To Understand The Current Stack

Assumed state:

- Local branches exist (`main`, feature branches).
- Some branches may only exist remotely.
- PRs may be partially created.

Run:

```bash
tide show
tide --json show
tide status
tide --json status
```

Use this when:

- You need the full tree view before rebasing or landing.
- You want scriptable flat output for CI or bots.
- You need to verify local/remote divergence and PR mapping.

## Situation: You Need A New Stack Entry From Current Branch

Assumed state:

- You are on a branch that belongs to a stack.
- You want a child branch for the next change.

Run:

```bash
tide add "feature-name"
```

Dirty working tree options:

```bash
tide add "feature-name" --dirty=fail
tide add "feature-name" --dirty=stash
tide add "feature-name" --dirty=move
```

Use this when:

- You want deterministic branch creation with configured naming.
- You need explicit dirty-state behavior instead of implicit stash habits.

## Situation: Your Branch Naming Must Follow Team Rules

Assumed state:

- Team branch naming conventions are enforced.

Configure template:

```toml
[naming]
branch_template = "$USER/$STACK/$FEATURE"
```

Supported tokens:

- `$USER`
- `$STACK`
- `$FEATURE` (required)
- `$DATE`
- `$N`
- `$BASE`

Use this when:

- You want predictable branch names across teammates and automation.

## Situation: You Need To Move Around A Stack Safely

Assumed state:

- You are on one stack entry and need to move to parent/child/explicit node.
- Your working tree may be dirty.

Run:

```bash
tide up
tide down
tide goto <branch>
```

With explicit behavior:

```bash
tide up --dirty=fail --conflict=rollback
tide down --dirty=stash --conflict=pause
tide goto <branch> --dirty=move --conflict=interactive
```

Use this when:

- You switch between stacked diffs frequently.
- You want predictable behavior if local changes exist.

## Situation: You Changed A Lower Branch And Need To Propagate Upward

Assumed state:

- You modified a lower stack entry.
- Child branches now need to be rebased/merged/cherry-picked.

Run:

```bash
tide ripple
```

Strategy selection:

```toml
[stack.ripple]
strategy = "rebase"   # or "merge" or "cherry-pick"
```

Conflict handling:

```bash
tide ripple --conflict=rollback
tide ripple --conflict=pause
tide ripple --conflict=interactive
```

Use this when:

- You want stack-wide propagation with one command.
- You need deterministic conflict behavior for local dev or CI.

## Situation: You Need To Apply Current Changes To Another Entry

Assumed state:

- You have local changes on the current entry.
- You want to transfer them to another stack entry.

Run:

```bash
tide apply <target-branch>
```

Use this when:

- You accidentally developed on the wrong stack entry.
- You want patch-based transfer using temporary worktrees.
- You may optionally follow with `tide ripple` if upstream propagation is needed.

## Situation: Your Stack Is A Tree (Not A Line)

Assumed state:

- A branch has multiple child branches.

Run:

```bash
tide show
```

Then choose operation scope intentionally:

- Path to trunk (default landing path behavior)
- Subtree (explicit)
- Full connected component (explicit)

Use this when:

- You need to land only one branch line without touching sibling branches.

## Situation: You Need PRs Created For Missing Stack Entries

Assumed state:

- Local and remote branches are ready.
- Some branches do not yet have PRs.

Run:

```bash
tide pr create --stack <selector> --scope path --head-pr <pr-number>
```

Use this when:

- You need Tide to create missing PRs in stack order.
- You want consistent draft/title/body behavior from config/templates.

## Situation: You Need To Land A Stack Deterministically

Assumed state:

- PRs exist for the path you intend to land.
- Forge permissions and branch protection are configured.

Run:

```bash
tide land
```

Landing modes:

- `squash-each` (default)
- `close-non-head`

What Tide validates before mutating:

1. Resolves the stack path.
2. Ensures required PRs exist.
3. Verifies mergeable state.
4. Executes merge/close sequence.

If PRs are missing, Tide fails with a non-zero exit and prints the exact `tide pr create` command to fix.

## Situation: A Conflict Happens And You Need Predictable Recovery

Assumed state:

- A mutating operation (`ripple`, `apply`, navigation with move/stash, landing path updates) hits a git conflict.

Default behavior (`rollback`):

- Operation aborts.
- Conflicted files are reported.
- Repository is restored to pre-command state.

For machine handling:

```bash
tide --json ripple
```

Conflict payload shape:

```json
{
  "error": "conflict",
  "files": ["path/one", "path/two"]
}
```

Use this when:

- CI or bots need stable conflict detection and retry logic.

## Situation: You Work In Fork And Direct Collaboration Modes

Assumed state:

- Some repos use fork-based contribution, others direct push.
- Mixed local/remote stack state exists.

Run:

```bash
tide checkout
tide push
tide sync
```

Set collaboration mode:

```toml
[collab]
mode = "fork"   # or "direct"
```

Use this when:

- You need the same stack workflow across internal and external repos.

## Situation: You Need Stable Non-Interactive CI Behavior

Assumed state:

- Command is run from automation.

Pattern:

```bash
tide --json --yes status
tide --json --yes show
tide --json --yes ripple
tide --json --yes land
```

Use this when:

- You need deterministic output and exit codes without prompts.

## Situation: You Need Repo-Specific Behavior Overrides

Assumed state:

- Team-level defaults exist, but one repo needs exceptions.

Config layers:

- User config (platformdirs location)
- Repo override: `.git/tide/config.toml`

Major keys:

```toml
[repo]
trunk = "main"

[naming]
branch_template = "$USER/$STACK/$FEATURE"

[stack.ripple]
strategy = "rebase"

[dirty]
default = "move"

[conflict]
mode = "rollback"

[forge]
provider = "github"

[forge.github]
transport = "graphql"
auth = "gh"

[collab]
mode = "fork"

[auto_update]
channel = "release"   # release | master | off
ttl_seconds = 86400
```

Use this when:

- You need deterministic team defaults while preserving per-repo flexibility.

## Situation: You Use Submodules, Sparse Checkout, Or Worktrees

Assumed state:

- Your repo has non-trivial git state (submodules/sparse/worktrees/untracked changes).

What Tide guarantees for mutating operations:

- Transaction snapshots include worktrees, submodules, sparse-checkout state, index, untracked files, and stashes.
- On rollback, these are restored.

Use this when:

- You need safety guarantees before using destructive graph operations.

## Situation: You Need Forge-Aware Behavior

Assumed state:

- You rely on PR metadata for accurate stack inference and landing.

Forge model:

- Provider abstraction (`ForgeProvider`, `ForgeTransport`)
- GitHub-first configuration with pluggable auth/transport
- Extensible to GitLab/Bitbucket

Use this when:

- You need predictable behavior across different forge backends.

## Situation: You Need To Debug Fast

Checklist:

1. Run `tide --json status` and verify parent/source edges.
2. Run `tide show` and confirm local/remote/PR expectations.
3. Re-run failed command with explicit `--conflict` and `--dirty`.
4. Inspect exit code (`2`/`3`/`4`/`5`/`6`) and branch accordingly in scripts.

## Scope Notes

- This README documents user operations aligned to the design spec, including branching stacks, collision handling modes, landing semantics, collaboration modes, config, non-interactive guarantees, and transactional safety expectations.
- Future extensions in the design spec (for example merge queue bundle mode or `tide verify`) are intentionally not documented as runnable commands here until they are productized.

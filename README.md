# tide

`tide` is a deterministic CLI for stacked branch and PR workflows.

This README is a real command transcript from running Tide against a local Gitea-backed git remote. It is user-focused and assumes your forge/repo auth is already set up.

## Transcript Fixture (already prepared)

- Remote forge: local Gitea
- Repo: `tideadmin/tide-readme-demo`
- Trunk: `main`
- Tide command used in this environment:

```bash
PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main ...
```

If your environment has a normal Tide install, replace that with `tide ...`.

## Situation: Understand Current Stack State (`show`, `status`)

```bash
$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main show
main (local, current)
  origin/main* (remote)

origin/main (remote)
[exit 0]

$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main status
main	loc=L	parent=-	source=-	pr=-
origin/main	loc=R	parent=main	source=heuristic	pr=-
[exit 0]
```

## Situation: Create New Stack Entries (`add`)

```bash
$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main add api
local/stack/api
[exit 0]

$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main add tests
local/stack/tests
[exit 0]
```

## Situation: Navigate Between Parent/Child (`up`, `down`, `goto`, `checkout`)

```bash
$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main up
local/stack/api
[exit 0]

$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main down
multiple child branches from 'local/stack/api': local/stack/tests, origin/main; use tide goto
[exit 6]

$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main goto main
main
[exit 0]

$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main checkout local/stack/api
local/stack/api
[exit 0]
```

`down` demonstrates the ambiguity exit path from the design spec (`exit 6`).

## Situation: Push Stack Entries To Server (`push`) And Inspect Updated Server-Visible State (`show`)

### Push `local/stack/api`

```bash
$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main push
local/stack/api
[exit 0]
```

`show` immediately after server-affecting command:

```bash
$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main show
main (local)

origin/local/stack/api (remote)
  local/stack/api* (local, current)
    local/stack/tests (local)
      origin/main* (remote)

local/stack/api (local, current)
  local/stack/tests (local)
    origin/main* (remote)

local/stack/tests (local)
  origin/main* (remote)

origin/main (remote)
[exit 0]
```

### Push `local/stack/tests`

```bash
$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main checkout local/stack/tests
local/stack/tests
[exit 0]

$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main push
local/stack/tests
[exit 0]
```

`show` immediately after server-affecting command:

```bash
$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main show
main (local)
  origin/main* (remote)

origin/local/stack/api (remote)
  local/stack/api* (local)

origin/local/stack/tests (remote)
  local/stack/tests* (local, current)

local/stack/api (local)

local/stack/tests (local, current)

origin/main (remote)
[exit 0]
```

## Situation: Propagate Parent Changes Upward (`ripple`)

```bash
$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main checkout local/stack/api
local/stack/api
[exit 0]

$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main ripple
local/stack/api
[exit 0]
```

```bash
$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main show
main (local)
  local/stack/api (local, current)
    local/stack/tests (local)
  origin/local/stack/api* (remote)
  origin/local/stack/tests* (remote)
  origin/main* (remote)

local/stack/api (local, current)
  local/stack/tests (local)

local/stack/tests (local)

origin/local/stack/api (remote)

origin/local/stack/tests (remote)

origin/main (remote)
[exit 0]
```

## Situation: Apply Current Branch Diff To Another Stack Entry (`apply`)

```bash
$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main checkout local/stack/tests
local/stack/tests
[exit 0]

$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main apply local/stack/api
local/stack/tests -> local/stack/api
[exit 0]
```

```bash
$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main show
main (local)
  local/stack/api (local)
    local/stack/tests (local, current)
  origin/local/stack/api* (remote)
  origin/local/stack/tests* (remote)
  origin/main* (remote)

local/stack/api (local)
  local/stack/tests (local, current)

local/stack/tests (local, current)

origin/local/stack/api (remote)

origin/local/stack/tests (remote)

origin/main (remote)
[exit 0]
```

## Situation: Land Fails When PRs Are Missing (`land` validation)

```bash
$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main land --stack local/stack/tests --scope path
missing PRs for branches: local/stack/api, local/stack/tests
run: tide pr create --stack local/stack/tests --scope path
[exit 2]

$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main --json land --stack local/stack/tests --scope path
{"error": "inputerror", "message": "missing PRs for branches: local/stack/api, local/stack/tests\nrun: tide pr create --stack local/stack/tests --scope path"}
[exit 2]
```

## Situation: Create Missing PRs For Stack Path (`pr create`)

```bash
$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main pr create --stack local/stack/tests --scope path
#1 local/stack/api -> main
#2 local/stack/tests -> local/stack/api
[exit 0]
```

```bash
$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main show
main (local)
  local/stack/api (local, PR#1)
    local/stack/tests (local, PR#2, current)
  origin/local/stack/api* (remote)
  origin/local/stack/tests* (remote)
  origin/main* (remote)

local/stack/api (local, PR#1)
  local/stack/tests (local, PR#2, current)

local/stack/tests (local, PR#2, current)

origin/local/stack/api (remote)

origin/local/stack/tests (remote)

origin/main (remote)
[exit 0]
```

```bash
$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main --json status
{"branches": [{"branch": "local/stack/api", "local": true, "parent": "main", "pr": 1, "remote": false, "source": "pr"}, {"branch": "local/stack/tests", "local": true, "parent": "local/stack/api", "pr": 2, "remote": false, "source": "pr"}, {"branch": "main", "local": true, "parent": null, "pr": null, "remote": false, "source": null}, {"branch": "origin/local/stack/api", "local": false, "parent": "main", "pr": null, "remote": true, "source": "heuristic"}, {"branch": "origin/local/stack/tests", "local": false, "parent": "main", "pr": null, "remote": true, "source": "heuristic"}, {"branch": "origin/main", "local": false, "parent": "main", "pr": null, "remote": true, "source": "heuristic"}]}
[exit 0]
```

## Situation: Land Stack Path (`land`) Then Push Trunk (`push`)

```bash
$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main land --stack local/stack/tests --scope path
landed 2 branches onto main
[exit 0]
```

```bash
$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main show
main (local, current, div=1/0)
  local/stack/api (local, PR#1)
    local/stack/tests (local, PR#2)

origin/main (remote)
  origin/local/stack/api* (remote)
  origin/local/stack/tests* (remote)

local/stack/api (local, PR#1)
  local/stack/tests (local, PR#2)

local/stack/tests (local, PR#2)

origin/local/stack/api (remote)

origin/local/stack/tests (remote)
[exit 0]
```

```bash
$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main push
main
[exit 0]
```

`show` immediately after server-affecting command:

```bash
$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main show
main (local, current)
  local/stack/api (local, PR#1)
    local/stack/tests (local, PR#2)
  origin/main* (remote)

origin/local/stack/api (remote)

origin/local/stack/tests (remote)

local/stack/api (local, PR#1)
  local/stack/tests (local, PR#2)

local/stack/tests (local, PR#2)

origin/main (remote)
[exit 0]
```

## Situation: Sync Local Branch With Updated Remote (`sync`) And Re-Inspect State

```bash
$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main sync
main
[exit 0]
```

`show` immediately after server-affecting command:

```bash
$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main show
main (local, current)
  local/stack/api (local, PR#1)
    local/stack/tests (local, PR#2)
  origin/main* (remote)

origin/local/stack/api (remote)

origin/local/stack/tests (remote)

local/stack/api (local, PR#1)
  local/stack/tests (local, PR#2)

local/stack/tests (local, PR#2)

origin/main (remote)
[exit 0]
```

## Situation: Conflict Mode Demonstration (`--conflict=pause`)

```bash
$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main ripple --conflict=pause
conflict detected; repository paused in conflicted state (resolve manually)
conflict detected
operation: ripple
branches: local/stack/api, main
files: app.txt
rerun: tide ripple --conflict=pause
[exit 4]
```

## Situation: Machine-Readable Graph And Non-Interactive Flags (`--json`, `--yes`)

```bash
$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main checkout main
main
[exit 0]

$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main --json show
{"edges": [{"child": "local/stack/tests", "parent": "local/stack/api", "source": "pr"}, {"child": "local/stack/api", "parent": "main", "source": "pr"}, {"child": "origin/main", "parent": "main", "source": "heuristic"}], "node_meta": {"local/stack/api": {"ahead": 0, "behind": 0, "current": false, "local": true, "remote": false}, "local/stack/tests": {"ahead": 0, "behind": 0, "current": false, "local": true, "remote": false}, "main": {"ahead": 0, "behind": 0, "current": true, "local": true, "remote": false}, "origin/local/stack/api": {"ahead": 0, "behind": 0, "current": false, "local": false, "remote": true}, "origin/local/stack/tests": {"ahead": 0, "behind": 0, "current": false, "local": false, "remote": true}, "origin/main": {"ahead": 0, "behind": 0, "current": false, "local": false, "remote": true}}, "nodes": ["local/stack/api", "local/stack/tests", "main", "origin/local/stack/api", "origin/local/stack/tests", "origin/main"], "prs": {"local/stack/api": {"base": "main", "checks": null, "draft": true, "mergeable": null, "number": 1, "reviews": null}, "local/stack/tests": {"base": "local/stack/api", "checks": null, "draft": true, "mergeable": null, "number": 2, "reviews": null}}}
[exit 0]

$ PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages python3 -m tide.cli.main --yes --json status
{"branches": [{"branch": "local/stack/api", "local": true, "parent": "main", "pr": 1, "remote": false, "source": "pr"}, {"branch": "local/stack/tests", "local": true, "parent": "local/stack/api", "pr": 2, "remote": false, "source": "pr"}, {"branch": "main", "local": true, "parent": null, "pr": null, "remote": false, "source": null}, {"branch": "origin/local/stack/api", "local": false, "parent": null, "pr": null, "remote": true, "source": null}, {"branch": "origin/local/stack/tests", "local": false, "parent": null, "pr": null, "remote": true, "source": null}, {"branch": "origin/main", "local": false, "parent": "main", "pr": null, "remote": true, "source": "heuristic"}]}
[exit 0]
```

## Branch Naming Template Used In This Run

Branches created by `tide add` used this default template:

```toml
[naming]
branch_template = "$USER/$STACK/$FEATURE"
```

That produced:

- `local/stack/api`
- `local/stack/tests`

## Notes On Coverage vs Design Spec

The transcript above covers the operational situations in the design spec that are implemented and runnable in this codebase now:

- Graph inspection (`show`, `status`, JSON)
- Stack creation and navigation (`add`, `up`, `down`, `goto`, `checkout`)
- Propagation and patch transfer (`ripple`, `apply`)
- PR lifecycle in Tide's current local provider (`pr create`, PR-linked graph rendering)
- Landing semantics and missing-PR validation (`land`)
- Collaboration/server interaction (`push`, `sync`) with `show` snapshots after each server change
- Conflict/non-zero exits and machine-readable outputs

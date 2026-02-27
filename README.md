# tide

`tide` is a deterministic CLI for stacked branch and PR workflows.

This transcript shows user-facing workflows and realistic CLI behavior.

<!-- tide-readme-transcript:start -->

## Workflow Transcript

- Remote forge: local Gitea (`tideadmin/tide-readme-demo`)
- Trunk: `main`
- Every command shown below is the real installed `tide` executable from `PATH`

## Situation: Understand Current Stack State (`show`, `status`)

```bash
$ tide show
main (local, current)
  origin/main* (remote)

origin/main (remote)

$ tide status
main	loc=L	parent=-	source=-	pr=-
origin/main	loc=R	parent=main	source=heuristic	pr=-
```

## Situation: Create New Stack Entries (`add`)

```bash
$ tide add api
local/stack/api

$ tide add tests
local/stack/tests
```

## Situation: Navigate Between Parent/Child (`up`, `down`, `goto`, `checkout`)

```bash
$ tide up
local/stack/api

$ tide down
multiple child branches from 'local/stack/api': local/stack/tests, origin/main; use tide goto

$ tide goto main
main

$ tide checkout local/stack/api
local/stack/api
```

## Situation: Push Stack Entries To Server (`push`) And Inspect Updated State (`show`)

```bash
$ tide push
local/stack/api
```

`show` immediately after server-affecting command:

```bash
$ tide show
main (local)
  local/stack/api (local, current)
    local/stack/tests (local)
      origin/main* (remote)
    origin/local/stack/api* (remote)

local/stack/api (local, current)
  local/stack/tests (local)
    origin/main* (remote)
  origin/local/stack/api* (remote)

local/stack/tests (local)
  origin/main* (remote)

origin/local/stack/api (remote)

origin/main (remote)
```

### Push `local/stack/tests`

```bash
$ tide push
local/stack/tests
```

`show` immediately after server-affecting command:

```bash
$ tide show
main (local)
  local/stack/api (local)
    local/stack/tests (local, current)
      origin/local/stack/tests* (remote)
    origin/local/stack/api* (remote)
  origin/main* (remote)

local/stack/api (local)
  local/stack/tests (local, current)
    origin/local/stack/tests* (remote)
  origin/local/stack/api* (remote)

local/stack/tests (local, current)
  origin/local/stack/tests* (remote)

origin/local/stack/api (remote)

origin/local/stack/tests (remote)

origin/main (remote)
```

## Situation: Propagate Parent Changes Upward (`ripple`)

```bash
$ tide ripple
local/stack/api

$ tide show
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
```

## Situation: Apply Current Branch Diff To Another Stack Entry (`apply`)

```bash
$ tide checkout local/stack/tests
local/stack/tests

$ tide apply local/stack/api
local/stack/tests -> local/stack/api

$ tide show
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
```

## Situation: Land Fails When PRs Are Missing (`land` validation)

```bash
$ tide land --stack local/stack/tests --scope path
missing PRs for branches: local/stack/api, local/stack/tests
run: tide pr create --stack local/stack/tests --scope path

$ tide --json land --stack local/stack/tests --scope path
{"error": "inputerror", "message": "missing PRs for branches: local/stack/api, local/stack/tests\nrun: tide pr create --stack local/stack/tests --scope path"}
```

## Situation: Create Missing PRs For Stack Path (`pr create`)

```bash
$ tide pr create --stack local/stack/tests --scope path
#1 local/stack/api -> main
#2 local/stack/tests -> local/stack/api

$ tide show
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

$ tide --json status
{"branches": [{"branch": "local/stack/api", "local": true, "parent": "main", "pr": 1, "remote": false, "source": "pr"}, {"branch": "local/stack/tests", "local": true, "parent": "local/stack/api", "pr": 2, "remote": false, "source": "pr"}, {"branch": "main", "local": true, "parent": null, "pr": null, "remote": false, "source": null}, {"branch": "origin/local/stack/api", "local": false, "parent": "main", "pr": null, "remote": true, "source": "heuristic"}, {"branch": "origin/local/stack/tests", "local": false, "parent": "main", "pr": null, "remote": true, "source": "heuristic"}, {"branch": "origin/main", "local": false, "parent": "main", "pr": null, "remote": true, "source": "heuristic"}]}
```

## Situation: Land Stack Path (`land`) Then Push Trunk (`push`)

```bash
$ tide land --stack local/stack/tests --scope path
landed 2 branches onto main

$ tide show
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

$ tide push
main

$ tide show
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
```

## Situation: Sync Local Branch With Updated Remote (`sync`)

```bash
$ tide sync
main

$ tide show
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
```

## Situation: Conflict Mode Demonstration (`--conflict=pause`)

```bash
$ tide checkout local/conflict
local/conflict

$ tide apply main --conflict=pause
conflict detected; repository paused in conflicted state (resolve manually)
conflict detected
operation: apply
branches: local/conflict, main
files: app.txt
rerun: tide apply --conflict=pause
```

## Situation: Machine-Readable Graph And Non-Interactive Flags

```bash
$ tide checkout main
main

$ tide --json show
{"edges": [{"child": "local/stack/tests", "parent": "local/stack/api", "source": "pr"}, {"child": "local/stack/api", "parent": "main", "source": "pr"}], "node_meta": {"local/stack/api": {"ahead": 0, "behind": 0, "current": false, "local": true, "remote": false}, "local/stack/tests": {"ahead": 0, "behind": 0, "current": false, "local": true, "remote": false}, "main": {"ahead": 1, "behind": 0, "current": true, "local": true, "remote": false}, "origin/local/stack/api": {"ahead": 0, "behind": 0, "current": false, "local": false, "remote": true}, "origin/local/stack/tests": {"ahead": 0, "behind": 0, "current": false, "local": false, "remote": true}, "origin/main": {"ahead": 0, "behind": 0, "current": false, "local": false, "remote": true}}, "nodes": ["local/stack/api", "local/stack/tests", "main", "origin/local/stack/api", "origin/local/stack/tests", "origin/main"], "prs": {"local/stack/api": {"base": "main", "checks": null, "draft": true, "mergeable": null, "number": 1, "reviews": null}, "local/stack/tests": {"base": "local/stack/api", "checks": null, "draft": true, "mergeable": null, "number": 2, "reviews": null}}}

$ tide --yes --json status
{"branches": [{"branch": "local/stack/api", "local": true, "parent": "main", "pr": 1, "remote": false, "source": "pr"}, {"branch": "local/stack/tests", "local": true, "parent": "local/stack/api", "pr": 2, "remote": false, "source": "pr"}, {"branch": "main", "local": true, "parent": null, "pr": null, "remote": false, "source": null}, {"branch": "origin/local/stack/api", "local": false, "parent": null, "pr": null, "remote": true, "source": null}, {"branch": "origin/local/stack/tests", "local": false, "parent": null, "pr": null, "remote": true, "source": null}, {"branch": "origin/main", "local": false, "parent": null, "pr": null, "remote": true, "source": null}]}
```

<!-- tide-readme-transcript:end -->

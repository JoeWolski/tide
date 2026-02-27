# tide

`tide` is a deterministic CLI for stacked branch and PR workflows.

This README is a practical, command-first walkthrough that uses a real local Gitea server in Docker and shows actual command output captured in this environment.

## What This README Demonstrates

- Spinning up a local forge (`gitea/gitea:1.22.6`) in Docker
- Creating an admin user and API token
- Creating a repository through the Gitea API
- Pushing a real stacked branch sequence with Git
- Creating stacked PRs through the Gitea API
- Querying PR state and common auth failure responses
- Running `tide show` / `tide --json status` against that repo

## Prerequisites

- Docker daemon reachable from your shell
- `git`, `curl`, `python3`
- This repository checked out at `/workspace/tide` (or adapt paths)

## 1) Start Local Gitea

Run:

```bash
docker rm -f tide-gitea-demo >/dev/null 2>&1 || true
mkdir -p /workspace/tmp/gitea-data
docker run -d --name tide-gitea-demo \
  -p 3001:3000 -p 2222:22 \
  -v /workspace/tmp/gitea-data:/data \
  -e USER_UID=1000 -e USER_GID=1000 \
  -e GITEA__security__INSTALL_LOCK=true \
  -e GITEA__service__DISABLE_REGISTRATION=true \
  -e GITEA__server__DOMAIN=localhost \
  -e GITEA__server__ROOT_URL=http://localhost:3001/ \
  gitea/gitea:1.22.6
```

Actual output (first run):

```text
Unable to find image 'gitea/gitea:1.22.6' locally
1.22.6: Pulling from gitea/gitea
...
Status: Downloaded newer image for gitea/gitea:1.22.6
09a4575ef0d34b4bb18a63548529b0ac4dea6c93808c644a0b0e8de0b4087ca9
```

Get the daemon-visible container IP and verify API health:

```bash
IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' tide-gitea-demo)
echo "$IP"
curl -sS "http://$IP:3000/api/v1/version" | python3 -m json.tool
```

Actual output:

```text
172.17.0.11
{
    "version": "1.22.6"
}
```

## 2) Create Admin User and API Token

Create admin user (idempotent note: reruns may report user already exists):

```bash
docker exec -u git tide-gitea-demo sh -c \
  "gitea admin user create \
    --username tideadmin \
    --password 'tidepass123' \
    --email tideadmin@example.com \
    --admin \
    --must-change-password=false"
```

Actual output:

```text
New user 'tideadmin' has been successfully created!
```

Generate a token for API calls:

```bash
TOKEN=$(docker exec -u git tide-gitea-demo sh -c \
  "gitea admin user generate-access-token \
    --username tideadmin \
    --token-name readme-demo \
    --scopes all \
    --raw")
echo "$TOKEN"
```

Actual output:

```text
1c9e47d3dc1e214b0deceb403b443467fefefbe2
```

## 3) Create a Repo Through Gitea API

```bash
curl -sS \
  -H "Content-Type: application/json" \
  -H "Authorization: token $TOKEN" \
  -d '{"name":"stack-demo","default_branch":"main","private":false}' \
  "http://$IP:3000/api/v1/user/repos" | \
python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps({"id":d["id"],"full_name":d["full_name"],"default_branch":d["default_branch"]}, indent=2))'
```

Actual output:

```json
{
  "id": 1,
  "full_name": "tideadmin/stack-demo",
  "default_branch": "main"
}
```

## 4) Push a Real Stacked Branch Sequence

```bash
rm -rf /workspace/tmp/stack-demo-local
mkdir -p /workspace/tmp/stack-demo-local
cd /workspace/tmp/stack-demo-local

git init -b main
git config user.name 'Tide Demo'
git config user.email 'tide-demo@example.com'
printf '# stack-demo\n' > README.md
git add README.md
git commit -m 'chore: initial commit'
git remote add origin "http://tideadmin:${TOKEN}@${IP}:3000/tideadmin/stack-demo.git"
git push -u origin main

git checkout -b feat/api
printf '\nAPI=v1\n' >> README.md
git add README.md
git commit -m 'feat: add API marker'
git push -u origin feat/api

git checkout -b feat/api-tests
mkdir -p tests
printf 'def test_api_marker():\n    assert True\n' > tests/test_api.py
git add tests/test_api.py
git commit -m 'test: add api smoke test'
git push -u origin feat/api-tests

git branch -vv
```

Actual output:

```text
Initialized empty Git repository in /workspace/tmp/stack-demo-local/.git/
[main (root-commit) 70ffebf] chore: initial commit
 1 file changed, 1 insertion(+)
 create mode 100644 README.md
remote: . Processing 1 references
remote: Processed 1 references in total
To http://172.17.0.11:3000/tideadmin/stack-demo.git
 * [new branch]      main -> main
branch 'main' set up to track 'origin/main'.
Switched to a new branch 'feat/api'
[feat/api f3e3b80] feat: add API marker
 1 file changed, 2 insertions(+)
remote: . Processing 1 references
remote: Processed 1 references in total
To http://172.17.0.11:3000/tideadmin/stack-demo.git
 * [new branch]      feat/api -> feat/api
branch 'feat/api' set up to track 'origin/feat/api'.
Switched to a new branch 'feat/api-tests'
[feat/api-tests 4f50cf2] test: add api smoke test
 1 file changed, 2 insertions(+)
 create mode 100644 tests/test_api.py
remote: . Processing 1 references
remote: Processed 1 references in total
To http://172.17.0.11:3000/tideadmin/stack-demo.git
 * [new branch]      feat/api-tests -> feat/api-tests
branch 'feat/api-tests' set up to track 'origin/feat/api-tests'.
  feat/api       f3e3b80 [origin/feat/api] feat: add API marker
* feat/api-tests 4f50cf2 [origin/feat/api-tests] test: add api smoke test
  main           70ffebf [origin/main] chore: initial commit
```

## 5) Create Stacked PRs Through Gitea API

```bash
curl -sS -H "Authorization: token $TOKEN" -H 'Content-Type: application/json' \
  -d '{"title":"feat/api -> main","head":"feat/api","base":"main","body":"First layer of the stack"}' \
  "http://$IP:3000/api/v1/repos/tideadmin/stack-demo/pulls"

curl -sS -H "Authorization: token $TOKEN" -H 'Content-Type: application/json' \
  -d '{"title":"feat/api-tests -> feat/api","head":"feat/api-tests","base":"feat/api","body":"Second layer of the stack"}' \
  "http://$IP:3000/api/v1/repos/tideadmin/stack-demo/pulls"
```

Actual output (trimmed to key fields):

```json
[
  {
    "number": 1,
    "title": "feat/api -> main",
    "head": "feat/api",
    "base": "main",
    "state": "open",
    "mergeable": true
  },
  {
    "number": 2,
    "title": "feat/api-tests -> feat/api",
    "head": "feat/api-tests",
    "base": "feat/api",
    "state": "open",
    "mergeable": true
  }
]
```

List open PRs:

```bash
curl -sS -H "Authorization: token $TOKEN" \
  "http://$IP:3000/api/v1/repos/tideadmin/stack-demo/pulls?state=open" | \
python3 -c 'import json,sys; arr=json.load(sys.stdin); out=[{"number":p["number"],"title":p["title"],"head":p["head"]["ref"],"base":p["base"]["ref"],"mergeable":p["mergeable"],"state":p["state"]} for p in arr]; print(json.dumps(out, indent=2))'
```

Actual output:

```json
[
  {
    "number": 2,
    "title": "feat/api-tests -> feat/api",
    "head": "feat/api-tests",
    "base": "feat/api",
    "mergeable": true,
    "state": "open"
  },
  {
    "number": 1,
    "title": "feat/api -> main",
    "head": "feat/api",
    "base": "main",
    "mergeable": true,
    "state": "open"
  }
]
```

## 6) Failure Path Example (Bad Token)

```bash
curl -sS -i -H 'Authorization: token not-a-real-token' "http://$IP:3000/api/v1/user" | sed -n '1,12p'
```

Actual output:

```text
HTTP/1.1 401 Unauthorized
Cache-Control: max-age=0, private, must-revalidate, no-transform
Content-Type: application/json;charset=utf-8
X-Content-Type-Options: nosniff
X-Frame-Options: SAMEORIGIN
Date: Fri, 27 Feb 2026 13:41:46 GMT
Content-Length: 93

{"message":"user does not exist [uid: 0, name: ]","url":"http://localhost:3001/api/swagger"}
```

## 7) Run Tide Against This Repo

This repo currently uses the local forge provider in code, so this step demonstrates stack inference against real local+remote git refs hosted on Gitea.

```bash
cd /workspace/tmp/stack-demo-local
PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages \
  python3 -m tide.cli.main show

PYTHONPATH=/workspace/tide:/workspace/tide/.pyuser/lib/python3.12/site-packages \
  python3 -m tide.cli.main --json status
```

Actual output:

```text
main (local)
  origin/main* (remote)

origin/feat/api (remote)
  feat/api* (local)

origin/feat/api-tests (remote)
  feat/api-tests* (local, current)

feat/api (local)

feat/api-tests (local, current)

origin/main (remote)
```

```json
{"branches": [{"branch": "feat/api", "local": true, "parent": "origin/feat/api", "pr": null, "remote": false, "source": "heuristic"}, {"branch": "feat/api-tests", "local": true, "parent": "origin/feat/api-tests", "pr": null, "remote": false, "source": "heuristic"}, {"branch": "main", "local": true, "parent": null, "pr": null, "remote": false, "source": null}, {"branch": "origin/feat/api", "local": false, "parent": null, "pr": null, "remote": true, "source": null}, {"branch": "origin/feat/api-tests", "local": false, "parent": null, "pr": null, "remote": true, "source": null}, {"branch": "origin/main", "local": false, "parent": "main", "pr": null, "remote": true, "source": "heuristic"}]}
```

## Practical Notes

- In this Docker environment, `localhost:3001` was not directly reachable from the host shell, but the bridge IP (`172.17.0.11`) was. If your host port mapping works, you can use `http://localhost:3001` instead.
- Token handling in examples is intentionally shell-variable based so you can rotate/revoke freely.
- Keep temporary demo repos under `/workspace/tmp` to avoid polluting your main checkout.

## Cleanup

```bash
docker rm -f tide-gitea-demo
rm -rf /workspace/tmp/gitea-data /workspace/tmp/stack-demo-local
```

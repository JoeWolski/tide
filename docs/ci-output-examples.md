# CI Output Examples

This document captures representative CI output for non-trivial failure and success paths.

## 1) Conflict Path: `tide --json apply main`

Example assertion from integration CI (`test_apply_conflict_returns_json_and_rolls_back`):

```json
{"error": "conflict", "files": ["f.txt"]}
```

Expected exit code: `4`

Why this is non-trivial:
- `apply` attempts patch transfer between diverged branches.
- command detects patch conflict deterministically.
- transaction restores branch/working tree after failure.

## 2) Landing Validation: Missing PRs

Example stderr from integration CI (`test_land_fails_with_missing_prs_and_fix_command`):

```text
missing PRs for branches: feat1, feat2
run: tide pr create --stack feat2 --scope path
```

Expected exit code: `2`

Why this is non-trivial:
- landing resolves stack path before mutating git.
- validates forge metadata completeness.
- prints exact deterministic remediation command.

## 3) Determinism Check: Repeated `status --json`

Validation from integration CI (`test_status_json_is_deterministic`):
- invoke `tide --json status` twice in same repo state
- assert byte-for-byte equality of output payload

Why this is non-trivial:
- branch traversal and graph rendering must be stable.
- output ordering is sorted and deterministic.

## Sample CI Pass Snippet

```text
$ python -m black --check tide tests
All done! ✨ 🍰 ✨

$ python -m ruff check tide tests
All checks passed!

$ python -m mypy tide
Success: no issues found in 24 source files

$ python -m pytest
..........                                                           [100%]
10 passed in 0.34s
```

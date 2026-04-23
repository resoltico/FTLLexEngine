---
afad: "3.5"
version: "0.163.0"
domain: RELEASE
updated: "2026-04-23"
route:
  keywords: [release, gh, github release, pypi, tag, assets, publish, verify, worktree, main]
  questions: ["how do I cut a release?", "how do I publish GitHub assets?", "how do I verify a release handoff?", "how do I rerun publish for an existing tag?"]
---

# Release Protocol

**Purpose**: Publish a tagged FTLLexEngine release through GitHub CLI and verify the GitHub Release and PyPI handoff.
**Prerequisites**: `gh` installed and authenticated, release version already set in `pyproject.toml`, and a checkout topology that can produce a clean release payload.

## Overview

The release flow is `gh`-first and branch-based. Do not push release commits directly to `main`.
Use a release branch, open a PR, merge it, verify the merged `main` commit is green, tag that
commit, and then verify the GitHub Release and published artifacts directly.

## Step 0: Verify GitHub CLI Readiness

Before doing anything else, run:

```bash
gh --version
gh auth status
```

If either command fails, stop immediately. Do not continue with release work until `gh` is both
installed and authenticated for the target repository.

## Step 1: Choose The Authoritative Checkout

Before any release build or branch creation, inspect the checkout that the user will keep using
after the release. Call it the primary checkout.

```bash
git rev-parse --show-toplevel
git branch --show-current
git status --short
git fetch origin --prune
git fetch origin --tags
git rev-list --left-right --count HEAD...origin/main
```

Rules:

- If the primary checkout is clean and current enough for release work, release from it directly.
- If the primary checkout is intentionally dirty, contains unrelated unpublished work, or should
  not be disturbed, create a clean release worktree from the same repository and do release work
  there.
- Do not run the release from a dirty checkout just because the intended payload currently lives
  there.
- If `git fetch origin --tags` fails with `would clobber existing tag`, stop and inspect the tag
  divergence before continuing. Compare the local and remote tag directly, delete only the stale
  local tag, and rerun the tag fetch:

```bash
TAG=v0.36.0
git rev-parse "$TAG"
git ls-remote --tags origin "refs/tags/$TAG" "refs/tags/$TAG^{}"
git tag -d "$TAG"
git fetch origin --tags
```

Recommended clean-worktree flow:

```bash
PRIMARY_CHECKOUT="$(git rev-parse --show-toplevel)"
git fetch origin --prune
git fetch origin --tags
RELEASE_WORKTREE="$(mktemp -d -t ftllexengine-release-XXXXXX)"
git worktree add --detach "$RELEASE_WORKTREE" origin/main
cd "$RELEASE_WORKTREE"
```

This flow intentionally keeps the worktree detached during pre-flight. Create
`release/X.Y.Z` only after Step 2 passes.

If the unpublished release payload exists only in the dirty primary checkout, move it explicitly
before running release gates in the clean worktree. Preferred: create a local bootstrap branch that
captures the payload, then add the release worktree from that branch. Acceptable: export one
explicit patch and apply it inside the release worktree.

Bootstrap-branch example:

```bash
git switch -c codex/release-bootstrap-X.Y.Z
git add -A
git commit -m "release: bootstrap X.Y.Z payload"
RELEASE_WORKTREE="$(mktemp -d -t ftllexengine-release-XXXXXX)"
git worktree add --detach "$RELEASE_WORKTREE" codex/release-bootstrap-X.Y.Z
cd "$RELEASE_WORKTREE"
```

## Step 2: Pre-flight And Release Readiness

Run the local gates first:

```bash
gh pr list --state open \
  --json number,title,url,headRefName,mergeStateStatus,isDraft,author,statusCheckRollup
bash -n scripts/*.sh
./check.sh
PY_VERSION=3.14 ./scripts/lint.sh
PY_VERSION=3.14 ./scripts/test.sh
uv run python scripts/validate_docs.py
uv run python scripts/validate_version.py
uv build
```

Also confirm:

- `CHANGELOG.md` contains the target release entry.
- `pyproject.toml` has the final target version.
- the release checkout is based on current `origin/main` or you explicitly understand the delta.

Do not cut the release branch or tag anything while any gate is red.

## Step 3: Release Branch And Staging Checkpoint

Create the release branch and treat staging as a scope-verification checkpoint:

```bash
git switch -c release/X.Y.Z
git add <release files>
git status --short
git diff --cached --name-status
git diff --cached --stat
git commit -m "release: bump version to X.Y.Z"
git push origin release/X.Y.Z
```

Requirements before continuing:

- `git status --short` shows no intended release file left unstaged or untracked.
- `git diff --cached --name-status` matches the expected file set.
- `git diff --cached --stat` confirms the staged payload is the release you intend to ship.

If the staged diff is incomplete or polluted, fix the branch before committing.

## Step 4: Pull Request And CI Checkpoint

Open the pull request:

```bash
gh pr create \
  --title "release: bump version to X.Y.Z" \
  --base main \
  --head release/X.Y.Z \
  --body "Release X.Y.Z"
```

Then verify scope and wait for checks:

```bash
gh pr diff <N> --name-only
gh pr view <N> --json number,state,mergeStateStatus,statusCheckRollup,url
gh pr checks <N>
```

Rules:

- `gh pr diff <N> --name-only` must still match the intended release file set.
- If `gh pr diff <N> --name-only` fails with HTTP 406 because the PR diff is too large, fall back
  to GitHub's paginated file list API and the local branch comparison:

```bash
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
gh api "repos/$REPO/pulls/<N>/files" --paginate --jq '.[].filename'
git diff --name-only origin/main...HEAD
```

- If you push another commit, reopen both the staging checkpoint and this PR diff checkpoint.
- Do not continue until the required PR checks are green.

## Step 5: Merge, Verify `main`, And Handle Partial Merge Failures

Merge the PR through GitHub, then verify the merged `main` commit itself before tagging:

```bash
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
gh pr merge <N> --repo "$REPO" --merge --delete-branch \
  --subject "release: bump version to X.Y.Z (#<N>)"
```

If `gh pr merge` exits non-zero, do not assume the merge failed. Inspect the PR directly:

```bash
gh pr view <N> --repo "$REPO" --json number,state,mergedAt,headRefName,baseRefName,url
```

If GitHub already reports `state` as `MERGED` and `mergedAt` is populated, treat that merged
state as authoritative and continue with the post-merge checks instead of retrying blindly.

Then fetch and verify the merged `main` handoff:

```bash
git fetch origin --prune
git fetch origin --tags
git switch --detach origin/main
MAIN_SHA="$(git rev-parse HEAD)"
gh run list --workflow=test.yml --branch=main --commit "$MAIN_SHA" --limit=20
gh run view <run-id> --log-failed
```

Do not create the tag until the exact merged `main` commit you intend to tag has a successful
`test.yml` run.

## Step 6: Tag, Publish Workflow, And Asset Convergence

Create and push the version tag only after Step 5 is green:

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

Verify the remote tag exists:

```bash
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
gh api "repos/$REPO/git/ref/tags/vX.Y.Z"
```

The tag push triggers `.github/workflows/publish.yml`. Monitor it directly:

```bash
TAG_SHA="$(git rev-list -n 1 vX.Y.Z)"
gh run list --workflow=publish.yml --event=push --commit "$TAG_SHA" --limit=20
gh run view <run-id> --log-failed
```

Publication invariant:

- PyPI-facing jobs may receive only uploadable distribution files (`.tar.gz` and `.whl`).
- The `ftllexengine-X.Y.Z.sha256` receipt is a GitHub Release asset, not a PyPI upload.
- If the workflow stages both distributions and the checksum receipt into the same artifact,
  treat that as a release-pipeline defect and fix the workflow before rerunning publication.

If you need to rerun publication for the existing tag, rerun the workflow against that tag. Do not
move or recreate the tag:

```bash
gh workflow run publish.yml -f release_tag=vX.Y.Z
gh workflow run publish.yml -f release_tag=vX.Y.Z -f publish_to_testpypi=true
```

If the tag push reaches a partial success state — for example, GitHub Release assets publish but
the PyPI job fails — repair the workflow on `main`, merge the fix, and then rerun
`workflow_dispatch` for the existing tag. Do not delete, move, or recreate the tag to retrigger
publication.

If GitHub Release assets need manual convergence after the workflow, use:

```bash
GH_TOKEN=... ./scripts/publish-github-release-assets.sh vX.Y.Z
GH_TOKEN=... ./scripts/verify-github-release.sh vX.Y.Z
```

## Step 7: Verify Public Release State

Do not treat workflow success alone as authoritative. Inspect the published release object:

```bash
gh release view vX.Y.Z --json tagName,isDraft,isPrerelease,publishedAt,url,assets
```

Required assets:

- `ftllexengine-X.Y.Z.tar.gz`
- `ftllexengine-X.Y.Z-py3-none-any.whl`
- `ftllexengine-X.Y.Z.sha256`

Then verify download, checksum, and installability:

```bash
TMP_DIR="$(mktemp -d)"
gh release download vX.Y.Z \
  -p 'ftllexengine-X.Y.Z-py3-none-any.whl' \
  -p 'ftllexengine-X.Y.Z.tar.gz' \
  -p 'ftllexengine-X.Y.Z.sha256' \
  -D "$TMP_DIR"

(
  cd "$TMP_DIR"
  shasum -a 256 -c "ftllexengine-X.Y.Z.sha256"
)

python3.13 -m venv "$TMP_DIR/py313"
"$TMP_DIR/py313/bin/pip" install --no-cache-dir "ftllexengine==X.Y.Z"
"$TMP_DIR/py313/bin/python" -c "import ftllexengine as pkg; print(pkg.__version__)"
rm -rf "$TMP_DIR"
```

The release is not complete until the release object, assets, and real install test all succeed.

## Step 8: Branch And Checkout Hygiene

Clean up the release branch topology and reconcile the primary checkout:

```bash
git remote prune origin
gh api "repos/$REPO/branches" --paginate --jq '.[].name'
```

Requirements:

- The remote `release/X.Y.Z` branch is gone.
- No stale historical `release/` branches remain locally or remotely.
- If a dedicated release worktree was used, the primary checkout is explicitly returned to a
  truthful `main`:

```bash
git -C "$PRIMARY_CHECKOUT" switch main
git -C "$PRIMARY_CHECKOUT" pull --ff-only
```

- Any still-needed unpublished local work from the old primary checkout is moved to a named branch
  or exported patch.
- Disposable release worktrees are removed after the release closes.

# Git Workflow Rules (All Mangrove Repos)

These rules apply to every repository under mangrove/. No exceptions.

## Feature Branch Workflow

1. **NEVER commit directly to `main` (or `master`).** All work must be done on a feature branch.
2. **Branch naming**: `feature/<short-description>`, `fix/<short-description>`, or `audit/<short-description>`. Keep it concise.
3. **Create the branch before making any changes.** If you realize you're on `main`, stash or create the branch immediately -- do not commit to `main`.

## Pull Requests

4. **Every merge to `main` goes through a pull request.** No direct merges, no fast-forward pushes.
5. **PRs require human approval.** Create the PR, post the URL, and wait. Do not merge without explicit user approval.
6. **Push the feature branch with `-u` on first push** to set upstream tracking.

## Post-Merge Verification

7. **After a PR is merged, watch the GitHub Actions CI/CD pipeline.** Run `gh run list --limit 5` or `gh run watch` to monitor the triggered workflow.
8. **NEVER declare a merge complete until CI passes and deployment is verified.** If the pipeline fails, investigate and fix immediately on a new branch.
9. **After successful deployment, delete the feature branch** both remotely (`gh pr view --json headRefName -q .headRefName` then `git push origin --delete <branch>`) and locally (`git branch -d <branch>`).
10. **Pull `main` to stay in sync with remote** after the branch is deleted: `git checkout main && git pull origin main`.

## Summary Checklist

```
[ ] Create feature branch from main
[ ] Do work, commit locally
[ ] Push feature branch, create PR
[ ] Wait for human approval
[ ] Merge PR (human or agent with explicit approval)
[ ] Watch GH Actions -- verify CI/CD passes
[ ] Verify deployment is working (health check, smoke test)
[ ] Delete feature branch (remote + local)
[ ] Pull main to sync with remote
```

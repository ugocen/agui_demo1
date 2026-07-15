# Collaboration protocol — pull, branch, PR, merge

Every change follows this workflow. Never commit directly to `main`; never
force-push `main`.

1. `git pull` on `main` first.
2. Create a new branch off `main`.
3. Commit your change on that branch.
4. Push the branch.
5. Open a PR.
6. Merge the PR — plain `gh pr merge`, never `--delete-branch`/`-d`.
7. `git pull` `main` again. The branch stays exactly where it is.

On push rejection: `git pull --rebase`.

## Branches are permanent — never delete one

Merging a PR does not retire its branch. Every branch stays after the merge,
local and remote, indefinitely. `main` keeps the *result* of a change; only the
branch keeps the *work* — the pre-squash commits, the review context, and a ref
to check out when a merged change has to be re-examined. That history is worth
more than a tidy branch list, and once a branch is gone it cannot be recovered
from here.

Never run any of these against this repo:

- `gh pr merge --delete-branch` / `gh pr merge -d`
- `git branch -d` / `git branch -D`
- `git push origin --delete <branch>` / `git push origin :<branch>`
- `/clean_gone` — it runs `git branch -D` over every `[gone]` branch and
  force-removes their worktrees.

Keep GitHub's auto-delete off as well: `gh repo view --json deleteBranchOnMerge`
must report `false`. Deleting a branch is the user's call, never yours — if one
truly has to go, ask first.

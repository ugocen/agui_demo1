# Collaboration protocol — pull, branch, PR, merge

Every change follows this workflow. Never commit directly to `main`; never
force-push `main`.

1. `git pull` on `main` first.
2. Create a new branch off `main`.
3. Commit your change on that branch.
4. Push the branch.
5. Open a PR.
6. Merge the PR.
7. `git pull` `main` again.

On push rejection: `git pull --rebase`.

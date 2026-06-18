# PR Policy

Editorial content is opinionated output. Prefer PR review over direct main pushes.

## Default Publication Path

1. Create a branch named `editorial/YYYY-MM-DD` or reuse an existing editorial branch for that date.
2. Commit generated artifacts and narrative revisions.
3. Push the branch.
4. Open a PR with:
   - covered match date
   - number of matches covered
   - Player of the Day names
   - hidden gem status
   - scoring version
   - audit warnings

## Direct Push Exception

Only push directly to `main` if the user explicitly asks for direct publication in the current conversation.

## PR Body Template

```md
## Editorial Picks

- Local match date:
- Matches covered:
- Scoring version:
- Player(s) of the Day:
- Hidden Gem:

## Audit

- Warnings:

## Verification

- [ ] `python -m pytest -q`
- [ ] examples SQL smoke test
- [ ] homepage/editorial page checked
```

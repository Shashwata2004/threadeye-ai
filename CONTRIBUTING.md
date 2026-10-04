# Contributing to ThreadEye AI

**Rule: nobody pushes to `main` except the repository owner (@Shashwata2004). Everyone else works on a
branch and opens a pull request; only the owner merges it.** GitHub enforces this with a ruleset
(`.github/rulesets/main-protection.json`, applied by `scripts/protect_main.sh`).

## Workflow / কাজের ধারা

```bash
git switch main && git pull                 # start from the latest main / সর্বশেষ main থেকে শুরু
git switch -c m2/live-screen                # one branch per task / প্রতি কাজে একটা ব্রাঞ্চ
# ... work, commit ...
make check                                  # run what CI runs before pushing / পুশের আগে পরীক্ষা
git push -u origin m2/live-screen
gh pr create --fill                         # open a pull request / PR খুলুন
```

1. **Branch names:** `<milestone>/<short-task>`, e.g. `m2/defect-cards`, `m2/sse-stream`, `fix/qr-label`.
2. **Pull request:** say what changed and how you tested it. CI (`backend`, `frontend`) must be green.
   The owner is asked for review automatically (`.github/CODEOWNERS`).
3. **Merge:** only the owner merges. If main moved on, update your branch first:
   `git fetch origin && git merge origin/main` (or rebase), then push again.
4. **After merge** the branch is deleted on GitHub; delete yours locally with `git branch -d <name>`.

বাংলায় সংক্ষেপে: `main`-এ সরাসরি পুশ শুধু মালিক করতে পারবেন। বাকিরা নিজের ব্রাঞ্চে কাজ করে PR খুলবেন,
CI সবুজ হতে হবে, আর মার্জ করবেন শুধু মালিক।

## House rules
- Never commit `.env`, `.env.cloud` or any password, token or key. `.env.example` and
  `.env.cloud.example` list every variable with placeholder values.
- Anything simulated must say SIMULATED; sample or fictional data must say SAMPLE DATA.
- New UI text goes into both `frontend/messages/en.json` and `bn.json` (`pnpm i18n:check`).
- API changes: run `make openapi` and commit `docs/api/openapi.json` with the generated TS types.
- Record prompts that shaped the code in `PROMPTS.md` and AI tools in `TOOLING.md` (competition rule).

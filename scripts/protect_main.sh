#!/usr/bin/env bash
# Apply (or update) the "only the owner pushes and merges main" ruleset.
#   scripts/protect_main.sh
# Needs: gh logged in as the repository owner; a PUBLIC repo, or GitHub Pro for a private one.
#
# What the ruleset does (only the Admin role, i.e. the owner, may bypass it):
#   update             nobody else can change main: no direct push, no merge
#   deletion           main cannot be deleted
#   non_fast_forward   no force-push to main
#   pull_request       a PR needs the code owner's approval (CODEOWNERS = the owner)
#   status checks      CI jobs "backend" and "frontend" must pass
set -euo pipefail
REPO="${REPO:-Shashwata2004/threadeye-ai}"
RULESET="$(dirname "$0")/../.github/rulesets/main-protection.json"
NAME="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["name"])' "$RULESET")"

existing=$(gh api "repos/$REPO/rulesets" --jq ".[] | select(.name == \"$NAME\") | .id" 2>/dev/null || true)
if [ -n "$existing" ]; then
  gh api -X PUT "repos/$REPO/rulesets/$existing" --input "$RULESET" >/dev/null
  echo "updated ruleset $existing on $REPO"
else
  id=$(gh api -X POST "repos/$REPO/rulesets" --input "$RULESET" --jq .id)
  echo "created ruleset $id on $REPO"
fi
gh api -X PATCH "repos/$REPO" -F delete_branch_on_merge=true >/dev/null
echo "merged branches are deleted automatically"

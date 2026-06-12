#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${STATIZ_REPO_DIR:-/home/ubuntu/statiz_code}"
REMOTE="${STATIZ_PUBLISH_REMOTE:-origin}"
BRANCH="${STATIZ_PUBLISH_BRANCH:-main}"
RESULTS_PATH="${STATIZ_PUBLIC_RESULTS_PATH:-web/public/results.json}"

cd "$REPO_DIR"

if git diff --quiet -- "$RESULTS_PATH"; then
  echo "statiz_publish_public_results: no public result changes"
  exit 0
fi

changed_paths="$(git diff --name-only)"
if [[ "$changed_paths" != "$RESULTS_PATH" ]]; then
  echo "statiz_publish_public_results: refusing to publish with unrelated tracked changes"
  git status --short
  exit 1
fi

git fetch "$REMOTE" "$BRANCH" --quiet
local_head="$(git rev-parse HEAD)"
remote_head="$(git rev-parse "$REMOTE/$BRANCH")"
if [[ "$local_head" != "$remote_head" ]]; then
  echo "statiz_publish_public_results: refusing to publish from stale checkout"
  echo "local=$local_head remote=$remote_head"
  exit 1
fi

if ! git config user.name >/dev/null; then
  git config user.name "statiz-server"
fi
if ! git config user.email >/dev/null; then
  git config user.email "statiz-server@users.noreply.github.com"
fi

git add "$RESULTS_PATH"
git commit -m "Publish public results $(TZ=Asia/Seoul date +%F)"
git push "$REMOTE" "HEAD:$BRANCH"
echo "statiz_publish_public_results: pushed $RESULTS_PATH to $REMOTE/$BRANCH"

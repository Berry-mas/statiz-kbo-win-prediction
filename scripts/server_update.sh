#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${STATIZ_REPO_DIR:-/home/ubuntu/statiz_code}"
REMOTE="${STATIZ_GIT_REMOTE:-origin}"
BRANCH="${STATIZ_GIT_BRANCH:-main}"
EXPECTED_COMMIT="${STATIZ_EXPECTED_COMMIT:-}"
RUN_TESTS="${STATIZ_UPDATE_RUN_TESTS:-0}"

cd "$REPO_DIR"

echo "statiz_update: repo=${REPO_DIR} remote=${REMOTE} branch=${BRANCH}"
git fetch "$REMOTE" "$BRANCH"

dirty_status="$(git status --porcelain --untracked-files=no)"
if [[ -n "$dirty_status" ]]; then
  echo "statiz_update: tracked local changes exist; refusing to update"
  echo "$dirty_status"
  echo "statiz_update: resolve tracked changes first, then rerun this script"
  exit 1
fi

git merge --ff-only "${REMOTE}/${BRANCH}"

if [[ -n "$EXPECTED_COMMIT" ]]; then
  actual_commit="$(git rev-parse --short=7 HEAD)"
  if [[ "$actual_commit" != "$EXPECTED_COMMIT" ]]; then
    echo "statiz_update: HEAD ${actual_commit} does not match expected ${EXPECTED_COMMIT}"
    exit 1
  fi
fi

uv sync --frozen
uv run python -m compileall -q src

if [[ "$RUN_TESTS" == "1" ]]; then
  uv run pytest
fi

echo "statiz_update: complete at $(git rev-parse --short=7 HEAD)"

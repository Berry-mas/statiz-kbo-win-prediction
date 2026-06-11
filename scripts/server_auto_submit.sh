#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${STATIZ_REPO_DIR:-/home/ubuntu/statiz_code}"
MODEL_VERSION="${STATIZ_MODEL_VERSION:-lgbm_v008}"
GAME_DATE="${STATIZ_GAME_DATE:-$(TZ=Asia/Seoul date +%F)}"
LOG_DIR="${STATIZ_LOG_DIR:-${REPO_DIR}/logs}"
DRY_RUN_ONLY="${STATIZ_DRY_RUN_ONLY:-1}"
EXECUTE_SUBMIT="${STATIZ_EXECUTE_SUBMIT:-0}"
IP_REGISTERED="${STATIZ_IP_REGISTERED:-0}"
MIN_LEAD_MINUTES="${STATIZ_MIN_LEAD_MINUTES:-35}"

mkdir -p "$LOG_DIR"
cd "$REPO_DIR"

cmd=(
  uv run python -m src.main auto-submit
  --date "$GAME_DATE"
  --model-version "$MODEL_VERSION"
)

if [[ "${STATIZ_SKIP_COLLECT:-0}" == "1" ]]; then
  cmd+=(--skip-collect)
fi

if [[ "${STATIZ_SKIP_FEATURES:-0}" == "1" ]]; then
  cmd+=(--skip-features)
fi

if [[ -n "${STATIZ_NOW:-}" ]]; then
  cmd+=(--now "$STATIZ_NOW")
fi

if [[ -n "$MIN_LEAD_MINUTES" ]]; then
  cmd+=(--min-lead-minutes "$MIN_LEAD_MINUTES")
fi

if [[ "$DRY_RUN_ONLY" == "0" && "$EXECUTE_SUBMIT" == "1" && "$IP_REGISTERED" == "1" ]]; then
  cmd+=(--execute-submit)
  echo "statiz_auto_submit: REAL SUBMIT enabled for ${GAME_DATE}"
else
  echo "statiz_auto_submit: dry-run only for ${GAME_DATE}"
  echo "statiz_auto_submit: set STATIZ_DRY_RUN_ONLY=0, STATIZ_EXECUTE_SUBMIT=1, and STATIZ_IP_REGISTERED=1 to allow real submission"
fi

exec "${cmd[@]}"

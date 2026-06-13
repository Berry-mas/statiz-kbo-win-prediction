#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${STATIZ_ENV_FILE:-/etc/statiz-auto-submit.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  set +a
fi

REPO_DIR="${STATIZ_REPO_DIR:-/home/ubuntu/statiz_code}"
UV_BIN="${STATIZ_UV_BIN:-/home/ubuntu/.local/bin/uv}"
MODEL_VERSION="${STATIZ_MODEL_VERSION:-lgbm_v008}"
GAME_DATE="${STATIZ_GAME_DATE:-$(TZ=Asia/Seoul date +%F)}"
LOG_DIR="${STATIZ_LOG_DIR:-${REPO_DIR}/logs}"
DRY_RUN_ONLY="${STATIZ_DRY_RUN_ONLY:-1}"
EXECUTE_SUBMIT="${STATIZ_EXECUTE_SUBMIT:-0}"
IP_REGISTERED="${STATIZ_IP_REGISTERED:-0}"

mkdir -p "$LOG_DIR"
cd "$REPO_DIR"

cmd=(
  "$UV_BIN" run python -m src.main auto-submit
  --date "$GAME_DATE"
  --model-version "$MODEL_VERSION"
  --submission-source manual
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

if [[ "$DRY_RUN_ONLY" == "0" && "$EXECUTE_SUBMIT" == "1" && "$IP_REGISTERED" == "1" ]]; then
  cmd+=(--execute-submit)
  echo "statiz_manual_submit: REAL SUBMIT enabled for ${GAME_DATE}"
else
  echo "statiz_manual_submit: dry-run only for ${GAME_DATE}"
  echo "statiz_manual_submit: set STATIZ_DRY_RUN_ONLY=0, STATIZ_EXECUTE_SUBMIT=1, and STATIZ_IP_REGISTERED=1 to allow real submission"
fi

set +e
"${cmd[@]}"
status=$?
set -e

if [[ "$status" -eq 0 && "${STATIZ_PUBLISH_PUBLIC_RESULTS:-0}" == "1" ]]; then
  ./scripts/publish_public_results.sh
fi

exit "$status"

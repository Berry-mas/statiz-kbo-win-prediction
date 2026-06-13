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
GAME_DATE="${STATIZ_GAME_DATE:-$(TZ=Asia/Seoul date +%F)}"
UPDATE_BEFORE_PUBLISH="${STATIZ_PUBLISH_UPDATE_BEFORE:-1}"

cd "$REPO_DIR"

if [[ "$UPDATE_BEFORE_PUBLISH" == "1" ]]; then
  ./scripts/server_update.sh
fi

YEAR="${GAME_DATE%%-*}"

echo "statiz_public_results: refreshing final game data for ${GAME_DATE}"
"$UV_BIN" run python -m src.main collect --year "$YEAR" --date "$GAME_DATE" --force-refresh
"$UV_BIN" run python -m src.main clean --year "$YEAR"

echo "statiz_public_results: exporting dashboard JSON"
"$UV_BIN" run python -c "from src.public_results import export_public_results; export_public_results()"

./scripts/publish_public_results.sh

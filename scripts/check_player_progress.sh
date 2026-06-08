#!/usr/bin/env bash
set -euo pipefail

year="${1:-2025}"
base_dir="data/raw/$year"

for dir in player_day player_season; do
  target_dir="$base_dir/$dir"
  if [[ -d "$target_dir" ]]; then
    count=$(find "$target_dir" -type f -name "*.json" 2>/dev/null | wc -l | tr -d ' ')
  else
    count=0
  fi
  echo "$dir: $count"
done

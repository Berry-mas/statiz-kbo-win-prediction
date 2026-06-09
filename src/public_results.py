"""
Build the public dashboard JSON from local logs and finalized game results.

Only finalized games are exported. Live, upcoming, cancelled, and unverified rows
are excluded so the public dashboard cannot reveal active prediction strategy.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from .constants import (
    GAMES_CSV,
    PREDICTION_LOG_CSV,
    PUBLIC_RESULTS_JSON,
    SUBMISSION_LOG_CSV,
    TEAM_CODES,
)


def export_public_results(
    output_path: str = PUBLIC_RESULTS_JSON,
    limit: int = 50,
) -> dict[str, Any]:
    """Export finalized submitted prediction results for the public dashboard.

    Args:
        output_path: Destination JSON path.
        limit: Maximum number of recent finalized games to include.

    Returns:
        The JSON-compatible payload written to disk.
    """
    games = _read_csv(GAMES_CSV)
    predictions = _read_csv(PREDICTION_LOG_CSV)
    submissions = _read_csv(SUBMISSION_LOG_CSV)

    rows: list[dict[str, Any]] = []
    if not games.empty and not predictions.empty and not submissions.empty:
        rows = _build_public_rows(games, predictions, submissions, limit)

    payload: dict[str, Any] = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "results": rows,
    }

    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info("Exported {} public result rows to {}", len(rows), dest)
    return payload


def _read_csv(path: str) -> pd.DataFrame:
    """Read a CSV path or return an empty DataFrame."""
    csv_path = Path(path)
    if not csv_path.exists():
        return pd.DataFrame()
    return pd.read_csv(csv_path, encoding="utf-8-sig")


def _build_public_rows(
    games: pd.DataFrame,
    predictions: pd.DataFrame,
    submissions: pd.DataFrame,
    limit: int,
) -> list[dict[str, Any]]:
    """Join logs with final scores and keep only public-safe rows."""
    finalized = games[
        (games["game_state"] == 3)
        & games["target_home_win"].notna()
        & games["home_score"].notna()
        & games["away_score"].notna()
    ].copy()
    if finalized.empty:
        return []

    submitted = submissions[submissions["submitted"].astype(str) == "True"].copy()
    if submitted.empty:
        return []

    latest_predictions = _latest_by_s_no(predictions, "predicted_at")
    latest_submissions = _latest_by_s_no(submitted, "submitted_at")

    merged = finalized.merge(latest_predictions, on="s_no", how="inner")
    merged = merged.merge(
        latest_submissions,
        on="s_no",
        how="inner",
        suffixes=("_prediction", "_submission"),
    )
    if merged.empty:
        return []

    merged = merged.sort_values(["game_date", "s_no"], ascending=False).head(limit)
    rows: list[dict[str, Any]] = []
    for _, row in merged.iterrows():
        probability = float(row["home_win_probability"])
        target = float(row["target_home_win"])
        predicted_home_win = probability > 50.0
        actual_home_win = target == 1.0
        rows.append(
            {
                "s_no": int(row["s_no"]),
                "game_date": str(row["game_date"]),
                "home_team": TEAM_CODES.get(int(row["home_team_code"]), "Unknown"),
                "away_team": TEAM_CODES.get(int(row["away_team_code"]), "Unknown"),
                "home_score": int(row["home_score"]),
                "away_score": int(row["away_score"]),
                "home_win_probability": round(probability, 2),
                "predicted_winner": "home" if predicted_home_win else "away",
                "actual_winner": "home" if actual_home_win else "away",
                "correct": predicted_home_win == actual_home_win,
                "model_version": str(row["model_version"]),
                "submitted_at": str(row["submitted_at"]),
            }
        )
    return rows


def _latest_by_s_no(df: pd.DataFrame, timestamp_col: str) -> pd.DataFrame:
    """Return the latest row per s_no using a timestamp column when present."""
    if timestamp_col in df.columns:
        df = df.sort_values(timestamp_col)
    return df.drop_duplicates(subset=["s_no"], keep="last")

"""
Build the public dashboard JSON from local logs and game results.

Submitted games include public submitted probabilities. Outcomes are only
published for finalized games, and raw strategy inputs are excluded.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
from loguru import logger

from .constants import (
    GAMES_CSV,
    PREDICTION_LOG_CSV,
    PUBLIC_RESULTS_JSON,
    SCHEDULER_RUN_LOG_CSV,
    SUBMISSION_LOG_CSV,
    TEAM_CODES,
)
from .submission_log import read_submission_log

SCHEMA_VERSION = 2
METRIC_WINDOW = 20
RECENT_SUBMISSION_LIMIT = 6
RECENT_GAME_LIMIT = 12
KST = ZoneInfo("Asia/Seoul")

TEAM_LOGO_KEYS: dict[int, str] = {
    1001: "samsung",
    2002: "kia",
    3001: "lotte",
    5002: "lg",
    6002: "doosan",
    7002: "hanwha",
    9002: "ssg",
    10001: "kiwoom",
    11001: "nc",
    12001: "kt",
}


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
    scheduler_runs = _read_csv(SCHEDULER_RUN_LOG_CSV)

    rows: list[dict[str, Any]] = []
    if not games.empty and not predictions.empty and not submissions.empty:
        rows = _build_public_rows(games, predictions, submissions, limit)

    latest_predictions = _latest_by_s_no(predictions, "predicted_at")
    latest_predictions = latest_predictions[
        [
            column
            for column in (
                "s_no",
                "home_win_probability",
                "model_version",
                "predicted_at",
            )
            if column in latest_predictions.columns
        ]
    ]
    latest_submissions = _latest_by_s_no(
        _successful_submissions(submissions), "submitted_at"
    )
    latest_scheduler = _latest_by_s_no(scheduler_runs, "checked_at")
    generated_at = datetime.now(tz=UTC)
    recent_games = _build_recent_games(
        games,
        latest_predictions,
        latest_submissions,
        latest_scheduler,
        RECENT_GAME_LIMIT,
        generated_at,
    )
    recent_submissions = _build_recent_submissions(
        latest_submissions,
        games,
        latest_predictions,
        RECENT_SUBMISSION_LIMIT,
        generated_at,
    )
    metrics = _build_model_metrics(rows, METRIC_WINDOW)
    latest_submission = recent_submissions[0] if recent_submissions else None
    latest_model_version = _latest_model_version(rows, recent_games, latest_predictions)

    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    existing_payload = _read_existing_payload(dest)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at.isoformat(),
        "publication_policy": {
            "scope": "Public dashboard data only",
            "probability_visibility": (
                "Submitted probabilities are published for submitted games; "
                "outcomes are published for finalized games only."
            ),
            "excluded": [
                "credentials",
                "raw API responses",
                "feature matrices",
                "unsubmitted live probabilities",
                "server addresses",
                "private file paths",
            ],
        },
        "model_version": latest_model_version,
        "summary": {
            "published_results": len(rows),
            "recent_submissions": len(recent_submissions),
            "recent_games": len(recent_games),
            "latest_submission_at": latest_submission["submitted_at"]
            if latest_submission
            else None,
            "metrics_window": metrics["window"],
        },
        "manual_workflow": _build_manual_workflow_summary(submissions),
        "latest_submission": latest_submission,
        "recent_submissions": recent_submissions,
        "recent_games": recent_games,
        "model_metrics": metrics,
        "results": rows,
    }
    if existing_payload is not None and _public_payload_without_time(
        existing_payload
    ) == _public_payload_without_time(payload):
        logger.info(
            "Public dashboard payload unchanged; leaving {} untouched with {} rows",
            dest,
            len(rows),
        )
        return existing_payload

    dest.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info("Exported {} public result rows to {}", len(rows), dest)
    return payload


def _read_existing_payload(path: Path) -> dict[str, Any] | None:
    """Read an existing public payload, returning None when invalid/missing."""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _public_payload_without_time(payload: dict[str, Any]) -> dict[str, Any]:
    comparable = dict(payload)
    comparable.pop("generated_at", None)
    return comparable


def _read_csv(path: str) -> pd.DataFrame:
    """Read a CSV path or return an empty DataFrame."""
    csv_path = Path(path)
    if not csv_path.exists():
        return pd.DataFrame()
    if str(csv_path) == SUBMISSION_LOG_CSV:
        return read_submission_log(csv_path)
    if str(csv_path) == SCHEDULER_RUN_LOG_CSV:
        return _read_optional_log_csv(csv_path)
    return pd.read_csv(csv_path, encoding="utf-8-sig")


def _read_optional_log_csv(csv_path: Path) -> pd.DataFrame:
    """Read non-critical operational logs without blocking public export."""
    try:
        return pd.read_csv(csv_path, encoding="utf-8-sig")
    except pd.errors.ParserError as exc:
        logger.warning(
            "Skipping malformed rows while reading optional public log {}: {}",
            csv_path,
            exc,
        )
        try:
            return pd.read_csv(
                csv_path,
                encoding="utf-8-sig",
                engine="python",
                on_bad_lines="skip",
            )
        except pd.errors.ParserError:
            logger.warning("Optional public log {} could not be parsed", csv_path)
            return pd.DataFrame()


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

    submitted = _successful_submissions(submissions)
    if submitted.empty:
        return []

    latest_predictions = _latest_by_s_no(predictions, "predicted_at")
    latest_predictions = latest_predictions[
        [
            column
            for column in (
                "s_no",
                "home_win_probability",
                "model_version",
                "predicted_at",
            )
            if column in latest_predictions.columns
        ]
    ]
    latest_submissions = _latest_by_s_no(submitted, "submitted_at").drop(
        columns=["game_date"],
        errors="ignore",
    )

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
    return [_public_result_row(row) for _, row in merged.iterrows()]


def _public_result_row(row: pd.Series) -> dict[str, Any]:
    probability = _optional_float(row.get("submitted_prob"))
    if probability is None:
        probability = float(row["home_win_probability"])
    predicted_home_win = probability > 50.0
    actual_home_win = float(row["target_home_win"]) == 1.0
    return {
        "s_no": int(row["s_no"]),
        "game_date": str(row["game_date"]),
        "game_time": _optional_string(row.get("game_time")),
        "home_team": _team_public(int(row["home_team_code"])),
        "away_team": _team_public(int(row["away_team_code"])),
        "home_score": int(row["home_score"]),
        "away_score": int(row["away_score"]),
        "home_win_probability": round(probability, 2),
        "predicted_winner": _winner_from_probability(probability),
        "actual_winner": "home" if actual_home_win else "away",
        "correct": predicted_home_win == actual_home_win,
        "model_version": str(row["model_version"]),
        "submitted_at": str(row["submitted_at"]),
        "submission_source": _optional_string(row.get("source")) or "auto",
    }


def _latest_by_s_no(df: pd.DataFrame, timestamp_col: str) -> pd.DataFrame:
    """Return the latest row per s_no using a timestamp column when present."""
    if df.empty or "s_no" not in df.columns:
        return df
    if timestamp_col in df.columns:
        df = df.sort_values(timestamp_col)
    return df.drop_duplicates(subset=["s_no"], keep="last")


def _successful_submissions(submissions: pd.DataFrame) -> pd.DataFrame:
    if submissions.empty or "submitted" not in submissions.columns:
        return pd.DataFrame()
    return submissions[_truthy_series(submissions["submitted"])].copy()


def _truthy_series(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin({"true", "1"})


def _build_recent_games(
    games: pd.DataFrame,
    predictions: pd.DataFrame,
    submissions: pd.DataFrame,
    scheduler_runs: pd.DataFrame,
    limit: int,
    as_of: datetime,
) -> list[dict[str, Any]]:
    if submissions.empty:
        return []

    merged = submissions.copy()
    if not games.empty:
        merged = merged.merge(games, on="s_no", how="left", suffixes=("", "_game"))
    if not predictions.empty:
        merged = merged.merge(
            predictions,
            on="s_no",
            how="left",
            suffixes=("", "_prediction"),
        )
    if not scheduler_runs.empty:
        safe_scheduler = scheduler_runs.drop(columns=["payload"], errors="ignore")
        merged = merged.merge(
            safe_scheduler,
            on="s_no",
            how="left",
            suffixes=("", "_scheduler"),
        )

    sort_columns = [
        column for column in ("submitted_at", "game_date") if column in merged
    ]
    if sort_columns:
        merged = merged.sort_values(sort_columns, ascending=False)
    merged = merged.head(limit)

    return [_recent_game_row(row, as_of) for _, row in merged.iterrows()]


def _recent_game_row(row: pd.Series, as_of: datetime) -> dict[str, Any]:
    home_probability = _optional_float(row.get("home_win_probability"))
    submitted_probability = _optional_float(row.get("submitted_prob"))
    display_probability = (
        submitted_probability if submitted_probability is not None else home_probability
    )
    home_sp_name = _optional_string(
        row.get("home_sp_name_scheduler", row.get("home_sp_name"))
    )
    away_sp_name = _optional_string(
        row.get("away_sp_name_scheduler", row.get("away_sp_name"))
    )
    is_final = _is_final_game(row)
    return {
        "s_no": _optional_int(row.get("s_no")),
        "game_date": _optional_string(row.get("game_date_game", row.get("game_date"))),
        "game_time": _optional_string(row.get("game_time")),
        "home_team": _team_public(_optional_int(row.get("home_team_code"))),
        "away_team": _team_public(_optional_int(row.get("away_team_code"))),
        "home_sp_name": home_sp_name,
        "away_sp_name": away_sp_name,
        "game_status": _public_game_status(row, as_of),
        "submitted_at": _optional_string(row.get("submitted_at")) or "",
        "submission_source": _optional_string(row.get("source")) or "auto",
        "model_version": _optional_string(row.get("model_version")) or "unknown",
        "probability_published": display_probability is not None,
        "home_win_probability": round(display_probability, 2)
        if display_probability is not None
        else None,
        "predicted_winner": _winner_from_probability(display_probability)
        if is_final
        else None,
        "scheduler": _scheduler_summary(row),
        **(
            _result_fields(row, display_probability)
            if is_final
            else _empty_result_fields()
        ),
    }


def _result_fields(row: pd.Series, probability: float | None) -> dict[str, Any]:
    actual_home_win = float(row["target_home_win"]) == 1.0
    predicted_home_win = bool(probability is not None and probability > 50.0)
    return {
        "home_score": _optional_int(row.get("home_score")),
        "away_score": _optional_int(row.get("away_score")),
        "actual_winner": "home" if actual_home_win else "away",
        "correct": predicted_home_win == actual_home_win,
    }


def _empty_result_fields() -> dict[str, Any]:
    return {
        "home_score": None,
        "away_score": None,
        "actual_winner": None,
        "correct": None,
    }


def _build_recent_submissions(
    submissions: pd.DataFrame,
    games: pd.DataFrame,
    predictions: pd.DataFrame,
    limit: int,
    as_of: datetime,
) -> list[dict[str, Any]]:
    if submissions.empty:
        return []

    enriched = submissions.copy()
    if not games.empty:
        enriched = enriched.merge(games, on="s_no", how="left", suffixes=("", "_game"))
    if not predictions.empty:
        enriched = enriched.merge(
            predictions[["s_no", "model_version"]],
            on="s_no",
            how="left",
        )

    game_date_col = "game_date_game" if "game_date_game" in enriched else "game_date"
    groups = (
        enriched.groupby([game_date_col, "source"], dropna=False)
        if "source" in enriched.columns
        else enriched.groupby([game_date_col], dropna=False)
    )
    batches: list[dict[str, Any]] = []
    for key, group in groups:
        if isinstance(key, tuple):
            game_date, source = key
        else:
            game_date, source = key, "auto"
        sorted_group = group.sort_values("submitted_at")
        model_versions = sorted(
            {
                str(value)
                for value in sorted_group.get("model_version", pd.Series(dtype=str))
                .dropna()
                .tolist()
            }
        )
        games_payload = [
            {
                "s_no": _optional_int(row.get("s_no")),
                "home_team": _team_public(_optional_int(row.get("home_team_code"))),
                "away_team": _team_public(_optional_int(row.get("away_team_code"))),
                "game_status": _public_game_status(row, as_of),
            }
            for _, row in sorted_group.iterrows()
        ]
        batches.append(
            {
                "game_date": str(game_date),
                "source": str(source or "auto"),
                "submitted_at": str(sorted_group["submitted_at"].max()),
                "submitted_games": int(len(sorted_group)),
                "model_version": model_versions[-1] if model_versions else "unknown",
                "games": games_payload,
            }
        )

    return sorted(batches, key=lambda row: row["submitted_at"], reverse=True)[:limit]


def _build_manual_workflow_summary(submissions: pd.DataFrame) -> dict[str, Any]:
    base = {
        "name": "Manual Statiz submit",
        "status": "unknown",
        "last_checked_at": None,
        "last_game_date": None,
        "submitted_games": 0,
        "source": "submission_log",
        "note": (
            "GitHub workflow run metadata is not published; this summarizes "
            "manual-source submission log rows only."
        ),
    }
    if submissions.empty or "source" not in submissions.columns:
        return base

    manual_rows = submissions[
        submissions["source"].fillna("auto").astype(str) == "manual"
    ]
    if manual_rows.empty:
        return base

    latest_at = str(manual_rows["submitted_at"].max())
    latest_rows = manual_rows[manual_rows["submitted_at"].astype(str) == latest_at]
    submitted_count = int(_truthy_series(latest_rows["submitted"]).sum())
    return {
        **base,
        "status": "success" if submitted_count > 0 else "failed",
        "last_checked_at": latest_at,
        "last_game_date": str(latest_rows["game_date"].iloc[0]),
        "submitted_games": submitted_count,
    }


def _build_model_metrics(
    finalized_rows: list[dict[str, Any]], window_size: int
) -> dict[str, Any]:
    rows = finalized_rows[:window_size]
    sample_size = len(rows)
    if sample_size == 0:
        return _empty_model_metrics(window_size)

    correct = sum(1 for row in rows if row["correct"])
    losses: list[float] = []
    briers: list[float] = []
    for row in rows:
        probability = max(
            min(float(row["home_win_probability"]) / 100, 1 - 1e-15), 1e-15
        )
        outcome = 1.0 if row["actual_winner"] == "home" else 0.0
        losses.append(
            -(
                outcome * math.log(probability)
                + (1 - outcome) * math.log(1 - probability)
            )
        )
        briers.append((probability - outcome) ** 2)

    return {
        "window": {
            "type": "recent_finalized_submitted_games",
            "requested": window_size,
            "sample_size": sample_size,
        },
        "accuracy": round(correct / sample_size, 4),
        "log_loss": round(sum(losses) / sample_size, 4),
        "brier": round(sum(briers) / sample_size, 4),
    }


def _empty_model_metrics(window_size: int) -> dict[str, Any]:
    return {
        "window": {
            "type": "recent_finalized_submitted_games",
            "requested": window_size,
            "sample_size": 0,
        },
        "accuracy": None,
        "log_loss": None,
        "brier": None,
    }


def _latest_model_version(
    finalized_rows: list[dict[str, Any]],
    recent_games: list[dict[str, Any]],
    predictions: pd.DataFrame,
) -> str | None:
    for collection in (recent_games, finalized_rows):
        for row in collection:
            value = row.get("model_version")
            if value and value != "unknown":
                return str(value)
    if not predictions.empty and "model_version" in predictions.columns:
        value = predictions.sort_values("predicted_at")["model_version"].dropna()
        if not value.empty:
            return str(value.iloc[-1])
    return None


def _team_public(code: int | None) -> dict[str, str]:
    if code is None:
        return {"name": "Unknown", "logo_key": "unknown"}
    return {
        "name": TEAM_CODES.get(code, "Unknown"),
        "logo_key": TEAM_LOGO_KEYS.get(code, "unknown"),
    }


def _public_game_status(row: pd.Series, as_of: datetime) -> str:
    state = _optional_int(row.get("game_state"))
    if state == 3:
        return "final"
    if state == 2:
        return "in_progress"
    if state in {4, 5}:
        return "cancelled"
    starts_at = _game_starts_at(row)
    if starts_at is not None and as_of.astimezone(KST) >= starts_at:
        return "in_progress"
    return "scheduled"


def _game_starts_at(row: pd.Series) -> datetime | None:
    game_date = _optional_string(row.get("game_date_game", row.get("game_date")))
    game_time = _optional_string(row.get("game_time"))
    if not game_date or not game_time:
        return None
    try:
        starts_at = datetime.fromisoformat(f"{game_date}T{game_time}")
    except ValueError:
        return None
    return starts_at.replace(tzinfo=KST)


def _is_final_game(row: pd.Series) -> bool:
    return (
        _optional_int(row.get("game_state")) == 3
        and _optional_float(row.get("target_home_win")) is not None
        and _optional_int(row.get("home_score")) is not None
        and _optional_int(row.get("away_score")) is not None
    )


def _winner_from_probability(probability: float | None) -> str | None:
    if probability is None:
        return None
    return "home" if probability > 50.0 else "away"


def _scheduler_summary(row: pd.Series) -> dict[str, Any] | None:
    status = _optional_string(row.get("status"))
    if status is None:
        return None
    return {
        "checked_at": _optional_string(row.get("checked_at")),
        "status": status,
        "reason": _optional_string(row.get("reason")),
        "would_submit": _optional_bool(row.get("would_submit")),
        "execute_submit": _optional_bool(row.get("execute_submit")),
        "starter_confirmed": _optional_bool(row.get("starter_confirmed")),
        "batting_lineup_missing": _optional_bool(row.get("batting_lineup_missing")),
        "starting_pitcher_count": _optional_int(row.get("starting_pitcher_count")),
        "starting_batter_count": _optional_int(row.get("starting_batter_count")),
        "home_sp_name": _optional_string(row.get("home_sp_name")),
        "away_sp_name": _optional_string(row.get("away_sp_name")),
    }


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    text = str(value).strip()
    return text if text else None


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    normalized = str(value).lower()
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    return None

"""
End-to-end dry-run automation for date/time based Statiz submissions.

The default mode is dry-run: it predicts and records what would be submitted but
does not call prediction/savePrediction unless execute_submit=True is passed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from .cleaner import DataCleaner
from .collector import DataCollector
from .constants import (
    GAMES_CSV,
    LINEUP_SNAPSHOT_CSV,
    SCHEDULER_RUN_LOG_CSV,
    SUBMISSION_LOG_CSV,
)
from .feature_builder import FeatureBuilder
from .notifications import DiscordNotifier
from .predictor import Predictor, normalize_prob
from .public_results import export_public_results
from .submitter import Submitter

KST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class AutomationConfig:
    """Runtime settings for one automated submission pass."""

    cutoff_minutes: int = 20
    hard_deadline_minutes: int = 15
    min_lead_minutes: int | None = None
    collect_data: bool = True
    build_features: bool = True
    execute_submit: bool = False
    now: datetime | None = None


def run_submission_automation(
    game_date: str,
    model_version: str | None = None,
    config: AutomationConfig | None = None,
    notifier: DiscordNotifier | None = None,
) -> list[dict[str, Any]]:
    """Run one date-scoped automation pass.

    Args:
        game_date: Date string in YYYY-MM-DD format.
        model_version: Optional model registry version.
        config: Runtime settings. Defaults to dry-run mode.
        notifier: Optional Discord notifier.

    Returns:
        Scheduler decision rows written to logs/scheduler_run_log.csv.
    """
    cfg = config or AutomationConfig()
    events = notifier or DiscordNotifier.from_env()

    _prepare_data(game_date, cfg)

    predictor = Predictor(model_version=model_version)
    predictions = predictor.predict_games(game_date)
    predictor.save_prediction_log(predictions, game_date)

    games = _load_games_for_date(game_date)
    lineups = _load_lineups()
    decisions = _build_decisions(
        game_date=game_date,
        games=games,
        predictions=predictions,
        lineups=lineups,
        model_version=predictor.model_version,
        config=cfg,
    )

    if cfg.execute_submit:
        _mark_already_submitted(decisions, game_date)
        _execute_real_submissions(decisions, game_date)

    _append_scheduler_log(decisions)
    public_payload = export_public_results()
    _notify_summary(events, decisions, public_count=len(public_payload["results"]))
    return decisions


def _prepare_data(game_date: str, config: AutomationConfig) -> None:
    """Collect, clean, and build feature data when enabled."""
    year, month, day = (int(part) for part in game_date.split("-"))

    if config.collect_data:
        DataCollector().collect_daily_all(year, month, day)
        DataCleaner().clean_all(year)

    if config.build_features:
        builder = FeatureBuilder()
        builder.load_clean_data()
        builder.build_features_for_year(year)


def _load_games_for_date(game_date: str) -> pd.DataFrame:
    """Load clean game rows for one date."""
    games_path = Path(GAMES_CSV)
    if not games_path.exists():
        return pd.DataFrame()
    games = pd.read_csv(games_path, encoding="utf-8-sig")
    return games[games["game_date"] == game_date].copy()


def _load_lineups() -> pd.DataFrame:
    """Load clean lineup rows."""
    lineups_path = Path(LINEUP_SNAPSHOT_CSV)
    if not lineups_path.exists():
        return pd.DataFrame()
    return pd.read_csv(lineups_path, encoding="utf-8-sig")


def _build_decisions(
    game_date: str,
    games: pd.DataFrame,
    predictions: list[dict[str, Any]],
    lineups: pd.DataFrame,
    model_version: str,
    config: AutomationConfig,
) -> list[dict[str, Any]]:
    """Build scheduler decisions for all predicted games."""
    checked_at = config.now or datetime.now(tz=KST)
    run_id = checked_at.strftime("%Y%m%d%H%M%S")
    predicted_by_s_no = {int(p["s_no"]): p for p in predictions}

    decisions: list[dict[str, Any]] = []
    for _, game in games.iterrows():
        s_no = int(game["s_no"])
        prediction = predicted_by_s_no.get(s_no)
        if prediction is None:
            decisions.append(
                _decision_row(
                    run_id,
                    checked_at,
                    game_date,
                    s_no,
                    model_version,
                    status="no_prediction",
                    reason="Feature row or model prediction not available",
                )
            )
            continue

        game_dt = _parse_game_datetime(game_date, str(game.get("game_time", "")))
        deadline_status = _deadline_status(checked_at, game_dt, config)
        lineup_missing = not _has_starting_lineup(lineups, s_no)
        status = deadline_status or (
            "lineup_missing_fallback" if lineup_missing else "ready"
        )
        would_submit = status in {"ready", "lineup_missing_fallback"}
        probability = normalize_prob(float(prediction["home_win_probability"]))

        decisions.append(
            _decision_row(
                run_id,
                checked_at,
                game_date,
                s_no,
                model_version,
                status=status,
                reason=_decision_reason(status),
                probability=probability,
                game_time=str(game.get("game_time", "")),
                lineup_missing=lineup_missing,
                would_submit=would_submit,
                execute_submit=config.execute_submit,
                payload={"s_no": s_no, "percent": probability},
            )
        )

    if games.empty:
        decisions.append(
            _decision_row(
                run_id,
                checked_at,
                game_date,
                0,
                model_version,
                status="no_games",
                reason="No clean game rows found for date",
            )
        )
    return decisions


def _decision_row(
    run_id: str,
    checked_at: datetime,
    game_date: str,
    s_no: int,
    model_version: str,
    status: str,
    reason: str,
    probability: float | None = None,
    game_time: str = "",
    lineup_missing: bool = False,
    would_submit: bool = False,
    execute_submit: bool = False,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one scheduler decision row."""
    return {
        "run_id": run_id,
        "checked_at": checked_at.isoformat(),
        "game_date": game_date,
        "s_no": s_no,
        "game_time": game_time,
        "model_version": model_version,
        "home_win_probability": probability,
        "lineup_missing": lineup_missing,
        "status": status,
        "reason": reason,
        "would_submit": would_submit,
        "execute_submit": execute_submit,
        "payload": payload or {},
    }


def parse_kst_datetime(value: str) -> datetime:
    """Parse an ISO timestamp for scheduler testing.

    Naive datetimes are interpreted as KST. Offset-aware datetimes are converted
    to KST so deadline comparisons stay consistent.
    """
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(
            "now must be an ISO timestamp like 2025-10-01T17:30:00+09:00"
        ) from exc

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)


def _parse_game_datetime(game_date: str, game_time: str) -> datetime | None:
    """Parse a KBO game datetime in KST."""
    if not game_time or game_time == "nan":
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(f"{game_date} {game_time}", fmt)
            return parsed.replace(tzinfo=KST)
        except ValueError:
            continue
    return None


def _deadline_status(
    now: datetime,
    game_dt: datetime | None,
    config: AutomationConfig,
) -> str | None:
    """Return a deadline-related status, or None when still submit-eligible."""
    if game_dt is None:
        return None
    hard_deadline = game_dt - timedelta(minutes=config.hard_deadline_minutes)
    safe_cutoff = game_dt - timedelta(minutes=config.cutoff_minutes)
    if now >= hard_deadline:
        return "past_hard_deadline"
    if now >= safe_cutoff:
        return "past_safe_cutoff"
    if config.min_lead_minutes is not None:
        earliest_submit = game_dt - timedelta(minutes=config.min_lead_minutes)
        if now < earliest_submit:
            return "too_early"
    return None


def _has_starting_lineup(lineups: pd.DataFrame, s_no: int) -> bool:
    """Return True when at least one starting lineup row exists for a game."""
    if lineups.empty or "s_no" not in lineups.columns:
        return False
    game_lineups = lineups[lineups["s_no"].astype(int) == s_no]
    if game_lineups.empty or "is_starter" not in game_lineups.columns:
        return False
    starters = game_lineups["is_starter"].astype(str).str.lower().isin({"true", "1"})
    return bool(starters.any())


def _decision_reason(status: str) -> str:
    """Map a scheduler status to a human-readable reason."""
    reasons = {
        "ready": "Lineup available and before safe cutoff",
        "lineup_missing_fallback": "Lineup missing before safe cutoff; fallback prediction allowed",
        "too_early": "Before configured submission window",
        "past_safe_cutoff": "Inside T-20 safety buffer; skip automated submission",
        "past_hard_deadline": "Inside official T-15 deadline; submission forbidden",
        "already_submitted": "Successful submission already recorded for this game",
    }
    return reasons.get(status, status)


def _mark_already_submitted(decisions: list[dict[str, Any]], game_date: str) -> None:
    """Disable duplicate submissions for games already submitted successfully."""
    already_submitted = _already_submitted_snos(game_date)
    if not already_submitted:
        return

    for row in decisions:
        if row["s_no"] in already_submitted and row["would_submit"]:
            row["status"] = "already_submitted"
            row["reason"] = _decision_reason("already_submitted")
            row["would_submit"] = False
            row["payload"] = {}


def _already_submitted_snos(game_date: str) -> set[int]:
    """Return game ids with successful submission rows for one date."""
    log_path = Path(SUBMISSION_LOG_CSV)
    if not log_path.exists():
        return set()

    try:
        submitted = pd.read_csv(log_path, encoding="utf-8-sig")
    except Exception as exc:
        logger.warning("Could not read submission log for duplicate guard: {}", exc)
        return set()

    required_columns = {"s_no", "game_date", "submitted"}
    if not required_columns.issubset(submitted.columns):
        return set()

    rows = submitted[
        (submitted["game_date"].astype(str) == game_date)
        & submitted["submitted"].astype(str).str.lower().isin({"true", "1"})
    ]
    return set(rows["s_no"].astype(int).tolist())


def _execute_real_submissions(decisions: list[dict[str, Any]], game_date: str) -> None:
    """Submit eligible decisions to the Statiz API."""
    submitter = Submitter()
    predictions = [
        {
            "s_no": row["s_no"],
            "home_win_probability": row["home_win_probability"],
        }
        for row in decisions
        if row["would_submit"]
    ]
    submitter.submit_all(predictions, game_date)


def _append_scheduler_log(decisions: list[dict[str, Any]]) -> None:
    """Append scheduler decisions to logs/scheduler_run_log.csv."""
    log_path = Path(SCHEDULER_RUN_LOG_CSV)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    rows = pd.DataFrame(
        [
            {
                **row,
                "payload": str(row["payload"]),
            }
            for row in decisions
        ]
    )
    rows.to_csv(
        log_path,
        mode="a",
        header=not log_path.exists(),
        index=False,
        encoding="utf-8-sig",
    )


def _notify_summary(
    notifier: DiscordNotifier,
    decisions: list[dict[str, Any]],
    public_count: int,
) -> None:
    """Send a compact Discord summary for one automation pass."""
    eligible = sum(1 for row in decisions if row["would_submit"])
    lineup_missing = sum(1 for row in decisions if row["lineup_missing"])
    skipped = len(decisions) - eligible
    try:
        notifier.send(
            title="Statiz dry-run automation complete",
            message="Submission automation pass finished.",
            fields={
                "eligible": eligible,
                "skipped": skipped,
                "lineup_missing": lineup_missing,
                "public_results": public_count,
                "execute_submit": any(row["execute_submit"] for row in decisions),
            },
        )
    except Exception as exc:
        logger.warning("Discord notification failed: {}", exc)

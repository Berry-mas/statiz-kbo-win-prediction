"""
Submitter: Submits predictions to the Statiz API with retry and validation.

Competition rules:
- 50.00% is invalid → normalize_prob() converts to 50.01
- Must submit at least 15 minutes before game start
- Retry up to 3 times with exponential backoff (0s, 10s, 30s)
- Log every submission attempt to logs/submission_log.csv
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from .api_client import StatizAPIClient
from .constants import GAMES_CSV, LOGS_DIR, SUBMISSION_LOG_CSV
from .predictor import normalize_prob

# KST = UTC+9
KST = timezone(timedelta(hours=9))

MAX_RETRIES = 3
RETRY_DELAYS = [0, 10, 30]  # seconds
DEADLINE_MINUTES = 15


class Submitter:
    """Submits win probability predictions to the Statiz API."""

    def __init__(self) -> None:
        self._client = StatizAPIClient()
        Path(LOGS_DIR).mkdir(parents=True, exist_ok=True)

    def _parse_game_datetime(self, game_date: str, game_time: str) -> datetime | None:
        """Parse 'YYYY-MM-DD' + 'HH:MM' into a KST-aware datetime."""
        try:
            dt_str = f"{game_date} {game_time}"
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
            return dt.replace(tzinfo=KST)
        except ValueError:
            logger.warning("Cannot parse game datetime: {} {}", game_date, game_time)
            return None

    def _is_past_deadline(self, game_date: str, game_time: str) -> bool:
        """Return True if it is too late to submit (within 15 min of game start)."""
        game_dt = self._parse_game_datetime(game_date, game_time)
        if game_dt is None:
            # Unknown start time — conservatively allow submission
            return False
        deadline = game_dt - timedelta(minutes=DEADLINE_MINUTES)
        now = datetime.now(tz=KST)
        return now >= deadline

    def validate_prediction(
        self,
        s_no: int,
        probability: float,
        game_date: str,
        game_time: str,
    ) -> tuple[bool, str]:
        """Validate a prediction before submission.

        Returns:
            (is_valid, reason_string)
        """
        if not (0.01 <= probability <= 99.99):
            return False, f"Probability {probability} out of range [0.01, 99.99]"
        if probability == 50.00:
            return False, "Probability 50.00 is invalid (must not equal exactly 50.00)"
        if self._is_past_deadline(game_date, game_time):
            return (
                False,
                f"Past 15-minute deadline for game {s_no} at {game_date} {game_time}",
            )
        return True, "OK"

    def submit_single(
        self,
        s_no: int,
        probability: float,
        game_date: str,
        game_time: str,
    ) -> dict[str, Any]:
        """Submit a single prediction with retry on failure.

        Returns:
            dict with keys: s_no, submitted, probability, attempts, response
        """
        probability = normalize_prob(probability)

        is_valid, reason = self.validate_prediction(
            s_no, probability, game_date, game_time
        )
        if not is_valid:
            logger.warning("Skipping submission s_no={}: {}", s_no, reason)
            self._log_submission(
                s_no,
                game_date,
                probability,
                submitted=False,
                attempts=0,
                response={},
                reason=reason,
            )
            return {
                "s_no": s_no,
                "submitted": False,
                "probability": probability,
                "attempts": 0,
                "response": {},
                "reason": reason,
            }

        last_exc: Exception | None = None
        for attempt, delay in enumerate(RETRY_DELAYS[:MAX_RETRIES], start=1):
            if delay > 0:
                logger.info(
                    "Retry attempt {} for s_no={} (waiting {}s)", attempt, s_no, delay
                )
                time.sleep(delay)

            try:
                response = self._client.save_prediction(s_no, probability)
                logger.info(
                    "Submitted s_no={} prob={:.2f}% attempt={} response={}",
                    s_no,
                    probability,
                    attempt,
                    response,
                )
                self._log_submission(
                    s_no,
                    game_date,
                    probability,
                    submitted=True,
                    attempts=attempt,
                    response=response,
                )
                return {
                    "s_no": s_no,
                    "submitted": True,
                    "probability": probability,
                    "attempts": attempt,
                    "response": response,
                    "reason": "OK",
                }
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Submission attempt {} failed for s_no={}: {}", attempt, s_no, exc
                )

        logger.error(
            "All {} attempts failed for s_no={}: {}", MAX_RETRIES, s_no, last_exc
        )
        self._log_submission(
            s_no,
            game_date,
            probability,
            submitted=False,
            attempts=MAX_RETRIES,
            response={},
            reason=str(last_exc),
        )
        return {
            "s_no": s_no,
            "submitted": False,
            "probability": probability,
            "attempts": MAX_RETRIES,
            "response": {},
            "reason": str(last_exc),
        }

    def submit_all(
        self,
        predictions: list[dict[str, Any]],
        game_date: str,
    ) -> list[dict[str, Any]]:
        """Submit predictions for all games on *game_date*.

        Args:
            predictions: list of {"s_no": int, "home_win_probability": float}
            game_date: "YYYY-MM-DD"

        Returns:
            list of submission result dicts
        """
        game_times: dict[int, str] = {}
        games_path = Path(GAMES_CSV)
        if games_path.exists():
            gdf = pd.read_csv(
                games_path, encoding="utf-8-sig", usecols=["s_no", "game_time"]
            )
            game_times = dict(
                zip(gdf["s_no"].astype(int), gdf["game_time"].astype(str), strict=True)
            )

        results: list[dict[str, Any]] = []
        for pred in predictions:
            s_no = int(pred["s_no"])
            prob = float(pred["home_win_probability"])
            game_time = game_times.get(s_no, "")
            result = self.submit_single(s_no, prob, game_date, game_time)
            results.append(result)

        submitted = sum(1 for r in results if r["submitted"])
        logger.info(
            "submit_all: {}/{} games submitted for {}",
            submitted,
            len(results),
            game_date,
        )
        return results

    def _log_submission(
        self,
        s_no: int,
        game_date: str,
        probability: float,
        submitted: bool,
        attempts: int,
        response: dict[str, Any],
        reason: str = "",
    ) -> None:
        """Append a row to submission_log.csv."""
        row = pd.DataFrame(
            [
                {
                    "s_no": s_no,
                    "game_date": game_date,
                    "submitted_prob": probability,
                    "submitted": submitted,
                    "attempts": attempts,
                    "submitted_at": datetime.now(tz=KST).isoformat(),
                    "response_status": response.get("cdoe", ""),
                    "response_message": response.get("result_msg", reason),
                }
            ]
        )

        log_path = Path(SUBMISSION_LOG_CSV)
        header = not log_path.exists()
        row.to_csv(
            log_path,
            mode="a",
            header=header,
            index=False,
            encoding="utf-8-sig",
        )

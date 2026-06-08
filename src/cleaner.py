"""
cleaner.py — DataCleaner

Reads raw JSON files from data/raw/ and writes/updates clean CSV files
under data/clean/. Each method appends new rows and deduplicates by key
columns so repeated runs are idempotent.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from .constants import (
    GAME_STATE_CANCELLED,
    GAME_STATE_FINISHED,
    GAMES_CSV,
    LINEUP_SNAPSHOT_CSV,
    RAW_DIR,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict[str, Any] | None:
    """Load a JSON file and return its contents, or None on failure."""
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        logger.warning("File not found: {}", path)
    except json.JSONDecodeError as exc:
        logger.warning("JSON decode error in {}: {}", path, exc)
    return None


def _read_csv_or_empty(csv_path: str, dtypes: dict | None = None) -> pd.DataFrame:
    """Read an existing CSV or return an empty DataFrame."""
    p = Path(csv_path)
    if p.exists():
        try:
            return pd.read_csv(p, dtype=dtypes, encoding="utf-8-sig")
        except Exception as exc:
            logger.warning("Could not read {}: {}", csv_path, exc)
    return pd.DataFrame()


def _save_csv(
    df: pd.DataFrame,
    csv_path: str,
    key_cols: list[str],
    sort_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Append df to existing CSV, deduplicate by key_cols, and save."""
    existing = _read_csv_or_empty(csv_path)
    combined = pd.concat([existing, df], ignore_index=True)
    combined = combined.drop_duplicates(subset=key_cols, keep="last")
    if sort_cols:
        combined = combined.sort_values(sort_cols).reset_index(drop=True)
    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(csv_path, index=False, encoding="utf-8-sig")
    return combined


def _s_no_to_date(s_no: int | str) -> str:
    """Derive game_date string 'YYYY-MM-DD' from an s_no like 2025041801."""
    s = str(s_no)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


# ---------------------------------------------------------------------------
# DataCleaner
# ---------------------------------------------------------------------------


class DataCleaner:
    """Transform raw JSON files into clean CSV files."""

    # ------------------------------------------------------------------
    # clean_games
    # ------------------------------------------------------------------

    def clean_games(self, year: int) -> pd.DataFrame:
        """Read all schedule JSON files for *year* and update games.csv."""
        schedule_dir = Path(RAW_DIR) / str(year) / "schedule"
        rows: list[dict[str, Any]] = []

        if not schedule_dir.exists():
            logger.warning("Schedule dir not found: {}", schedule_dir)
        else:
            for json_file in sorted(schedule_dir.glob("*.json")):
                data = _load_json(json_file)
                if data is None:
                    continue
                # API response key is MMDD (e.g. "0322") derived from filename "2025-03-22.json"
                stem = json_file.stem  # "2025-03-22"
                parts = stem.split("-")
                mmdd_key = parts[1] + parts[2] if len(parts) == 3 else ""
                games = data.get(mmdd_key, [])
                for g in games:
                    game_state = g.get("state")
                    is_cancelled = game_state == GAME_STATE_CANCELLED

                    home_score = g.get("homeScore")
                    away_score = g.get("awayScore")

                    if is_cancelled or game_state != GAME_STATE_FINISHED:
                        target = float("nan")
                    elif home_score is None or away_score is None:
                        target = float("nan")
                    elif home_score > away_score:
                        target = 1.0
                    elif home_score < away_score:
                        target = 0.0
                    else:
                        # draw
                        target = float("nan")

                    month_val = g.get("month")
                    day_val = g.get("day")
                    yr_val = int(g.get("year", year))
                    game_date = (
                        f"{yr_val:04d}-{int(month_val):02d}-{int(day_val):02d}"
                        if month_val and day_val
                        else ""
                    )

                    rows.append(
                        {
                            "s_no": g.get("s_no"),
                            "game_date": game_date,
                            "year": yr_val,
                            "month": month_val,
                            "day": day_val,
                            "game_time": g.get("hm"),
                            "stadium_code": g.get("s_code"),
                            "home_team_code": g.get("homeTeam"),
                            "away_team_code": g.get("awayTeam"),
                            "home_sp_no": g.get("homeSP"),
                            "away_sp_no": g.get("awaySP"),
                            "home_sp_name": g.get("homeSPName"),
                            "away_sp_name": g.get("awaySPName"),
                            "home_score": home_score,
                            "away_score": away_score,
                            "game_state": game_state,
                            "league_type": g.get("leagueType"),
                            "game_type": g.get("gameType"),
                            "is_cancelled": is_cancelled,
                            "target_home_win": target,
                        }
                    )

        if not rows:
            logger.warning("No schedule data found for year {}", year)
            return _read_csv_or_empty(GAMES_CSV)

        df = pd.DataFrame(rows)
        result = _save_csv(
            df, GAMES_CSV, key_cols=["s_no"], sort_cols=["game_date", "s_no"]
        )
        logger.info("clean_games: {} rows saved for year {}", len(result), year)
        return result

    # ------------------------------------------------------------------
    # clean_lineups
    # ------------------------------------------------------------------

    def clean_lineups(self, year: int) -> pd.DataFrame:
        """Read all lineup JSON files for *year* and update lineup_snapshot.csv."""
        lineup_dir = Path(RAW_DIR) / str(year) / "lineup"
        rows: list[dict[str, Any]] = []

        if not lineup_dir.exists():
            logger.warning("Lineup dir not found: {}", lineup_dir)
        else:
            for json_file in sorted(lineup_dir.glob("*.json")):
                data = _load_json(json_file)
                if data is None:
                    continue
                # Lineup response keys are team codes as strings (e.g. "3001", "5002")
                players: list[dict[str, Any]] = []
                for key, val in data.items():
                    if key.isdigit() and isinstance(val, list):
                        players.extend(val)
                for p in players:
                    s_no = p.get("s_no")
                    position_code = p.get("position")
                    rows.append(
                        {
                            "s_no": s_no,
                            "game_date": _s_no_to_date(s_no) if s_no else "",
                            "team_code": p.get("t_code"),
                            "p_no": p.get("p_no"),
                            "batting_order": p.get("battingOrder"),
                            "position_code": position_code,
                            "is_starter": p.get("starting") == "Y",
                            "p_name": p.get("p_name"),
                            "p_bat": p.get("p_bat"),
                            "p_throw": p.get("p_throw"),
                            "is_pitcher": position_code == 1,
                        }
                    )

        if not rows:
            logger.warning("No lineup data found for year {}", year)
            return _read_csv_or_empty(LINEUP_SNAPSHOT_CSV)

        df = pd.DataFrame(rows)
        result = _save_csv(
            df,
            LINEUP_SNAPSHOT_CSV,
            key_cols=["s_no", "team_code", "p_no"],
            sort_cols=["game_date", "s_no", "team_code", "batting_order"],
        )
        logger.info("clean_lineups: {} rows saved for year {}", len(result), year)
        return result

    # ------------------------------------------------------------------
    # clean_all
    # ------------------------------------------------------------------

    def clean_all(self, year: int, biz_date: str | None = None) -> None:
        """Run leakage-safe cleaning steps for a given year.

        The baseline feature builder computes as-of team, starter, and bullpen
        features directly from games and raw playerDay files. It intentionally
        avoids creating single-date season snapshots that can be misused for
        historical training rows.
        """
        if biz_date is None:
            biz_date = datetime.now().strftime("%Y-%m-%d")

        logger.info("Starting clean_all for year={} biz_date={}", year, biz_date)

        self.clean_games(year)
        self.clean_lineups(year)
        logger.info("clean_all completed for year={} biz_date={}", year, biz_date)

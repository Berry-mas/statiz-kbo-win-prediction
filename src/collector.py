"""
DataCollector: Fetches raw data from Statiz API and persists each response as
a JSON file under data/raw/{year}/{type}/.  Collection is idempotent by default;
target files are reused unless a method is called with force=True.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from loguru import logger

from .api_client import StatizAPIClient
from .constants import (
    GAME_STATE_CANCELLED,
    LEAGUE_TYPE_REGULAR,
    PERIOD_APRIL,
    PERIOD_AUGUST,
    PERIOD_JULY,
    PERIOD_JUNE,
    PERIOD_MARCH,
    PERIOD_MAY,
    PERIOD_OCTOBER,
    PERIOD_SEPTEMBER,
    RAW_DIR,
    ROSTER_CODE_1ST_TEAM,
    TEAM_RECORD_BATTING,
    TEAM_RECORD_PITCHING,
)

# All monthly period codes for collect_team_season_stats
_MONTH_PERIODS: list[str] = [
    PERIOD_MARCH,
    PERIOD_APRIL,
    PERIOD_MAY,
    PERIOD_JUNE,
    PERIOD_JULY,
    PERIOD_AUGUST,
    PERIOD_SEPTEMBER,
    PERIOD_OCTOBER,
]


def _raw_path(*parts: str | int) -> Path:
    """Return a Path under RAW_DIR for the given path segments."""
    return Path(RAW_DIR, *[str(p) for p in parts])


def _save_json(path: Path, data: dict[str, Any]) -> None:
    """Create parent directories and write *data* as formatted JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data["_collected_at"] = datetime.now().isoformat()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.debug("Saved {}", path)


def _pe_label(pe: str) -> str:
    """Convert period parameter to a safe filename segment."""
    return pe if pe else "all"


def _player_season_exists(p_no: int, year: int) -> bool:
    """Return whether a player's season file already exists for year."""
    return _raw_path(year, "player_season", f"{p_no}.json").exists()


class DataCollector:
    """Collects raw data from Statiz API and stores responses as JSON files."""

    def __init__(self) -> None:
        self._client = StatizAPIClient()

    def collect_schedule(
        self, year: int, month: int, day: int, force: bool = False
    ) -> dict[str, Any]:
        """Fetch game schedule for *year/month/day* and save to disk.

        The file is only written when at least one regular-season game exists
        in the response.  Returns the full API response dict.
        """
        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        dest = _raw_path(year, "schedule", f"{date_str}.json")

        if dest.exists() and not force:
            logger.debug("Schedule already exists, skipping: {}", dest)
            return json.loads(dest.read_text(encoding="utf-8"))

        data = self._client.get(
            "/prediction/gameSchedule",
            params={"year": year, "month": month, "day": day},
        )

        # API response key is MMDD (e.g. "0322"), not "date"
        mmdd_key = f"{month:02d}{day:02d}"
        games: list[dict[str, Any]] = data.get(mmdd_key) or []
        regular_games = [g for g in games if g.get("leagueType") == LEAGUE_TYPE_REGULAR]

        if not regular_games:
            logger.debug("No regular-season games on {}, skipping save", date_str)
            return data

        _save_json(dest, data)
        logger.info(
            "Collected schedule for {}: {} regular games", date_str, len(regular_games)
        )
        return data

    def collect_boxscore(
        self, s_no: int, year: int, force: bool = False
    ) -> dict[str, Any]:
        """Fetch boxscore for *s_no* and save to disk."""
        dest = _raw_path(year, "boxscore", f"{s_no}.json")

        if dest.exists() and not force:
            logger.debug("Boxscore already exists, skipping: {}", dest)
            return json.loads(dest.read_text(encoding="utf-8"))

        data = self._client.get("/prediction/gameBoxscore", params={"s_no": s_no})
        _save_json(dest, data)
        logger.info("Collected boxscore s_no={}", s_no)
        return data

    def collect_lineup(
        self, s_no: int, year: int, force: bool = False
    ) -> dict[str, Any]:
        """Fetch lineup for *s_no* and save to disk."""
        dest = _raw_path(year, "lineup", f"{s_no}.json")

        if dest.exists() and not force:
            logger.debug("Lineup already exists, skipping: {}", dest)
            return json.loads(dest.read_text(encoding="utf-8"))

        data = self._client.get("/prediction/gameLineup", params={"s_no": s_no})
        _save_json(dest, data)
        logger.info("Collected lineup s_no={}", s_no)
        return data

    def collect_team_stats(self, year: int, pe: str = "") -> dict[str, Any]:
        """Fetch batting **and** pitching team stats for the given period.

        Files:
            data/raw/{year}/team_stats/{year}_{pe_label}_batting.json
            data/raw/{year}/team_stats/{year}_{pe_label}_pitching.json

        Returns ``{"batting": {...}, "pitching": {...}}``.
        """
        label = _pe_label(pe)
        results: dict[str, Any] = {}

        for m2 in (TEAM_RECORD_BATTING, TEAM_RECORD_PITCHING):
            dest = _raw_path(year, "team_stats", f"{year}_{label}_{m2}.json")

            if dest.exists():
                logger.debug("Team stats already exists, skipping: {}", dest)
                results[m2] = json.loads(dest.read_text(encoding="utf-8"))
                continue

            data = self._client.get(
                "/prediction/teamRecord",
                params={"m2": m2, "year": year, "pe": pe, "we": "", "ii": ""},
            )
            _save_json(dest, data)
            logger.info("Collected team stats year={} pe='{}' m2={}", year, pe, m2)
            results[m2] = data

        return results

    def collect_player_day(self, p_no: int, year: int) -> dict[str, Any]:
        """Fetch per-game stats for *p_no* in *year* and save to disk."""
        dest = _raw_path(year, "player_day", f"{p_no}_{year}.json")

        if dest.exists():
            logger.debug("Player day already exists, skipping: {}", dest)
            return json.loads(dest.read_text(encoding="utf-8"))

        data = self._client.get(
            "/prediction/playerDay", params={"p_no": p_no, "year": year}
        )
        _save_json(dest, data)
        logger.info("Collected player day p_no={} year={}", p_no, year)
        return data

    def collect_player_season(self, p_no: int) -> dict[str, Any]:
        """Fetch multi-year season stats for *p_no* and save per-year files.

        The API response contains a list of season records, one per year.
        Each record is saved under ``data/raw/{year}/player_season/{p_no}.json``.
        Returns the full API response dict.
        """
        data = self._client.get("/prediction/playerSeason", params={"p_no": p_no})

        season_list: list[dict[str, Any]] = (data.get("basic") or {}).get("list") or []

        if not season_list:
            logger.warning("No season data returned for p_no={}", p_no)
            return data

        for entry in season_list:
            entry_year_raw = entry.get("year")
            if entry_year_raw is None:
                logger.warning("Season entry missing 'year' field for p_no={}", p_no)
                continue
            entry_year = int(entry_year_raw)

            dest = _raw_path(entry_year, "player_season", f"{p_no}.json")
            if dest.exists():
                logger.debug("Player season already exists, skipping: {}", dest)
                continue

            _save_json(dest, data)
            logger.info("Collected player season p_no={} year={}", p_no, entry_year)

        return data

    def collect_player_situation(
        self, p_no: int, year: int, si: int = 2
    ) -> dict[str, Any]:
        """Fetch situational stats (e.g. stadium splits) for *p_no*."""
        dest = _raw_path(year, "player_situation", f"{p_no}_{year}_{si}.json")

        if dest.exists():
            logger.debug("Player situation already exists, skipping: {}", dest)
            return json.loads(dest.read_text(encoding="utf-8"))

        data = self._client.get(
            "/prediction/playerSituation",
            params={"p_no": p_no, "year": year, "si": si},
        )
        _save_json(dest, data)
        logger.info("Collected player situation p_no={} year={} si={}", p_no, year, si)
        return data

    def collect_roster(self, date_str: str, t_code: int) -> list[dict[str, Any]]:
        """Fetch 1-gun roster for *t_code* on *date_str* (YYYY-MM-DD).

        Saves to ``data/raw/{year}/roster/{date_str}_{t_code}.json``.
        Returns the ``players`` list from the API response.
        """
        year = int(date_str[:4])
        dest = _raw_path(year, "roster", f"{date_str}_{t_code}.json")

        if dest.exists():
            logger.debug("Roster already exists, skipping: {}", dest)
            stored = json.loads(dest.read_text(encoding="utf-8"))
            return stored.get("players") or []

        data = self._client.get(
            "/prediction/playerRoster",
            params={"date": date_str, "code": ROSTER_CODE_1ST_TEAM, "t_code": t_code},
        )
        _save_json(dest, data)
        logger.info(
            "Collected roster date={} t_code={} ({} players)",
            date_str,
            t_code,
            len(data.get("players") or []),
        )
        return data.get("players") or []

    def collect_daily_all(
        self, year: int, month: int, day: int, force: bool = False
    ) -> None:
        """Collect all data for a single calendar date.

        Steps:
            1. Collect schedule and find regular-season games.
            2. For each game collect boxscore + lineup (errors are logged, not raised).
            3. Collect playerDay/playerSeason for starting pitchers only.
        """
        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        logger.info("collect_daily_all: {}", date_str)

        try:
            schedule_data = self.collect_schedule(year, month, day, force=force)
        except Exception:
            logger.exception("Failed to collect schedule for {}", date_str)
            return

        # API response key is MMDD (e.g. "0322"), not "date"
        mmdd_key = f"{month:02d}{day:02d}"
        games: list[dict[str, Any]] = schedule_data.get(mmdd_key) or []
        regular_games = [
            g
            for g in games
            if g.get("leagueType") == LEAGUE_TYPE_REGULAR
            and g.get("state") != GAME_STATE_CANCELLED
        ]
        if not regular_games:
            return

        for game in regular_games:
            s_no: int | None = game.get("s_no")
            if s_no is None:
                logger.warning("Game entry missing s_no on {}", date_str)
                continue

            try:
                self.collect_boxscore(s_no, year, force=force)
            except Exception:
                logger.exception("Failed to collect boxscore s_no={}", s_no)

            try:
                self.collect_lineup(s_no, year, force=force)
            except Exception:
                logger.exception("Failed to collect lineup s_no={}", s_no)

        starter_pnos: set[int] = set()
        for game in regular_games:
            s_no = game.get("s_no")
            if s_no is None:
                continue
            lineup_path = _raw_path(year, "lineup", f"{s_no}.json")
            if not lineup_path.exists():
                continue
            lineup_data = json.loads(lineup_path.read_text(encoding="utf-8"))
            for key, players in lineup_data.items():
                if not key.isdigit() or not isinstance(players, list):
                    continue
                for p in players:
                    if p.get("position") == 1 and p.get("starting") == "Y":
                        p_no = p.get("p_no")
                        if p_no:
                            starter_pnos.add(int(p_no))

        for p_no in starter_pnos:
            try:
                self.collect_player_day(p_no, year)
            except Exception:
                logger.exception("Failed to collect player_day p_no={}", p_no)
            if _player_season_exists(p_no, year):
                logger.debug(
                    "Player season exists, skipping API: p_no={} year={}", p_no, year
                )
                continue
            try:
                self.collect_player_season(p_no)
            except Exception:
                logger.exception("Failed to collect player_season p_no={}", p_no)

    def collect_season_bulk(self, year: int) -> None:
        """Collect all daily data for an entire season (March 1 – November 30).

        Errors on individual dates are logged and skipped.  Progress is logged
        every 10 days.
        """
        logger.info("collect_season_bulk: year={}", year)

        start = date(year, 3, 1)
        end = date(year, 11, 30)
        current = start
        day_count = 0

        while current <= end:
            day_count += 1
            if day_count % 10 == 0:
                logger.info(
                    "Season bulk progress: {} / {} (day {} of {})",
                    current,
                    end,
                    day_count,
                    (end - start).days + 1,
                )

            try:
                self.collect_daily_all(current.year, current.month, current.day)
            except Exception:
                logger.exception("collect_daily_all failed for {}, skipping", current)

            time.sleep(0.3)  # avoid hitting API rate limit
            current += timedelta(days=1)

        logger.info("collect_season_bulk complete for year={}", year)

    def collect_team_season_stats(self, year: int) -> None:
        """Collect team stats for the full season and each monthly period.

        Periods: '' (all season), M3, M4, M5, M6, M7, M8, M9, M10.
        Both batting and pitching are collected via collect_team_stats.
        Errors are logged and skipped.
        """
        logger.info("collect_team_season_stats: year={}", year)

        periods = ["", *_MONTH_PERIODS]
        for pe in periods:
            label = _pe_label(pe)
            logger.debug("Collecting team stats year={} pe='{}'", year, label)
            try:
                self.collect_team_stats(year, pe)
            except Exception:
                logger.exception(
                    "Failed to collect team stats year={} pe='{}'", year, label
                )

        logger.info("collect_team_season_stats complete for year={}", year)

"""Build leakage-safe pre-match features from clean games and raw player data."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger
from pandas.errors import EmptyDataError

from .constants import (
    GAME_STATE_FINISHED,
    GAMES_CSV,
    LEAGUE_TYPE_REGULAR,
    LINEUP_SNAPSHOT_CSV,
    RAW_DIR,
    feature_csv_path,
)

_NAN = float("nan")


def _read_csv_safe(path: str) -> pd.DataFrame:
    """Read a CSV file, returning an empty frame when it does not exist."""
    csv_path = Path(path)
    if not csv_path.exists():
        logger.warning("CSV not found: {}", path)
        return pd.DataFrame()
    try:
        return pd.read_csv(csv_path, encoding="utf-8-sig")
    except EmptyDataError:
        return pd.DataFrame()


def _to_float(value: Any, default: float = _NAN) -> float:
    """Convert API scalar values to float."""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    """Convert API scalar values to int."""
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _ip_to_float(value: Any) -> float:
    """Convert baseball IP notation like 7.1 into decimal innings."""
    ip_value = _to_float(value, default=0.0)
    full_innings = int(ip_value)
    outs = round((ip_value - full_innings) * 10)
    if outs not in (0, 1, 2):
        return ip_value
    return full_innings + outs / 3.0


def _safe_div(numerator: float, denominator: float) -> float:
    """Return numerator / denominator, or NaN when denominator is zero."""
    if denominator == 0:
        return _NAN
    return numerator / denominator


def _safe_subtract(left: Any, right: Any) -> float:
    """Return left - right, preserving NaN when either side is missing."""
    left_value = _to_float(left)
    right_value = _to_float(right)
    if pd.isna(left_value) or pd.isna(right_value):
        return _NAN
    return left_value - right_value


def _missing_flag(value: Any) -> float:
    """Return a numeric missing-value indicator."""
    return 1.0 if pd.isna(_to_float(value)) else 0.0


def _win_rate_ratio(home_rate: Any, away_rate: Any) -> float:
    """Return home_rate / (home_rate + away_rate), using neutral defaults."""
    home_value = _to_float(home_rate, default=0.5)
    away_value = _to_float(away_rate, default=0.5)
    if pd.isna(home_value):
        home_value = 0.5
    if pd.isna(away_value):
        away_value = 0.5
    return _safe_div(home_value, home_value + away_value)


def _game_date_from_row(row: pd.Series) -> date:
    """Parse a game row's date."""
    return pd.to_datetime(row["game_date"]).date()


class FeatureBuilder:
    """Build one leakage-safe feature row per regular-season game."""

    def __init__(self) -> None:
        self.games_df: pd.DataFrame | None = None
        self.lineups_df: pd.DataFrame | None = None
        self._pitcher_cache: dict[tuple[int, int], list[dict[str, Any]]] = {}
        self._batter_season_cache: dict[tuple[int, int], dict[str, float] | None] = {}
        self._lineup_cache: dict[tuple[int, int], list[dict[str, Any]]] = {}

    def load_clean_data(self) -> None:
        """Load clean game and lineup rows."""
        games_df = _read_csv_safe(GAMES_CSV)
        if not games_df.empty:
            games_df["game_date"] = pd.to_datetime(
                games_df["game_date"], errors="coerce"
            )
            games_df = games_df.sort_values(["game_date", "s_no"]).reset_index(
                drop=True
            )
        self.games_df = games_df
        logger.info("Loaded games: {}", len(games_df))

        lineups_df = _read_csv_safe(LINEUP_SNAPSHOT_CSV)
        if not lineups_df.empty:
            lineups_df["s_no"] = pd.to_numeric(lineups_df["s_no"], errors="coerce")
            lineups_df["team_code"] = pd.to_numeric(
                lineups_df["team_code"], errors="coerce"
            )
            lineups_df["p_no"] = pd.to_numeric(lineups_df["p_no"], errors="coerce")
            lineups_df = lineups_df.dropna(
                subset=["s_no", "team_code", "p_no"]
            ).reset_index(drop=True)
            lineups_df["s_no"] = lineups_df["s_no"].astype(int)
            lineups_df["team_code"] = lineups_df["team_code"].astype(int)
            lineups_df["p_no"] = lineups_df["p_no"].astype(int)
        self.lineups_df = lineups_df
        self._lineup_cache = self._build_lineup_cache(lineups_df)
        logger.info("Loaded lineup rows: {}", len(lineups_df))

    @staticmethod
    def _build_lineup_cache(
        lineups_df: pd.DataFrame,
    ) -> dict[tuple[int, int], list[dict[str, Any]]]:
        """Index starting batters by game and team."""
        required_cols = {"s_no", "team_code", "p_no", "is_starter", "is_pitcher"}
        if lineups_df.empty or not required_cols.issubset(lineups_df.columns):
            return {}

        batter_lineups = lineups_df[
            lineups_df["is_starter"].fillna(False).astype(bool)
            & ~lineups_df["is_pitcher"].fillna(False).astype(bool)
        ].copy()
        if batter_lineups.empty:
            return {}

        batter_lineups["batting_order_int"] = pd.to_numeric(
            batter_lineups["batting_order"], errors="coerce"
        )
        batter_lineups = batter_lineups.sort_values(
            ["s_no", "team_code", "batting_order_int"], na_position="last"
        )

        cache: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for (s_no, team_code), group in batter_lineups.groupby(
            ["s_no", "team_code"], sort=False
        ):
            cache[(int(s_no), int(team_code))] = group.to_dict(orient="records")
        return cache

    def _lineup_rows_for_team(self, team_code: int, s_no: int) -> list[dict[str, Any]]:
        """Return cached starting-batter lineup rows for a team game."""
        if self.lineups_df is None or self.lineups_df.empty:
            return []
        if not self._lineup_cache:
            self._lineup_cache = self._build_lineup_cache(self.lineups_df)
        return self._lineup_cache.get((s_no, team_code), [])

    def _finished_games_before(
        self, team_code: int, game_date: date, year: int
    ) -> pd.DataFrame:
        """Return completed same-season games for a team before game_date."""
        if self.games_df is None or self.games_df.empty:
            return pd.DataFrame()

        df = self.games_df
        mask = (
            (df["year"] == year)
            & (df["league_type"] == LEAGUE_TYPE_REGULAR)
            & (df["game_state"] == GAME_STATE_FINISHED)
            & (pd.to_datetime(df["game_date"]).dt.date < game_date)
            & (~df["target_home_win"].isna())
            & (
                (df["home_team_code"] == team_code)
                | (df["away_team_code"] == team_code)
            )
        )
        return df[mask].sort_values(["game_date", "s_no"])

    def _team_outcome(self, row: pd.Series, team_code: int) -> dict[str, float]:
        """Return runs and win outcome from a game row for team_code."""
        is_home = row["home_team_code"] == team_code
        runs_for = _to_float(
            row["home_score" if is_home else "away_score"], default=0.0
        )
        runs_against = _to_float(
            row["away_score" if is_home else "home_score"], default=0.0
        )
        win = 1.0 if runs_for > runs_against else 0.0
        return {"runs_for": runs_for, "runs_against": runs_against, "win": win}

    def _team_features(
        self, team_code: int, game_date: date, year: int
    ) -> dict[str, float]:
        """Compute season-to-date and recent form features for a team."""
        past = self._finished_games_before(team_code, game_date, year)
        outcomes = [self._team_outcome(row, team_code) for _, row in past.iterrows()]
        recent = outcomes[-5:]

        return {
            "games_played": float(len(outcomes)),
            "win_rate": self._mean(outcomes, "win"),
            "runs_for_pg": self._mean(outcomes, "runs_for"),
            "runs_against_pg": self._mean(outcomes, "runs_against"),
            "run_diff_pg": self._mean_diff(outcomes),
            "win_rate_last_5": self._mean(recent, "win"),
            "runs_for_last_5": self._mean(recent, "runs_for"),
            "runs_against_last_5": self._mean(recent, "runs_against"),
            "run_diff_last_5": self._mean_diff(recent),
        }

    @staticmethod
    def _mean(rows: list[dict[str, float]], key: str) -> float:
        """Return the mean of key across rows."""
        if not rows:
            return _NAN
        return sum(row[key] for row in rows) / len(rows)

    @staticmethod
    def _mean_diff(rows: list[dict[str, float]]) -> float:
        """Return mean run differential."""
        if not rows:
            return _NAN
        total = sum(row["runs_for"] - row["runs_against"] for row in rows)
        return total / len(rows)

    def _load_pitcher_games(self, p_no: int, year: int) -> list[dict[str, Any]]:
        """Load raw playerDay games for a pitcher and season."""
        cache_key = (p_no, year)
        if cache_key in self._pitcher_cache:
            return self._pitcher_cache[cache_key]

        path = Path(RAW_DIR) / str(year) / "player_day" / f"{p_no}_{year}.json"
        if not path.exists():
            self._pitcher_cache[cache_key] = []
            return []

        data = json.loads(path.read_text(encoding="utf-8"))
        games: list[dict[str, Any]] = []
        for s_no, record in data.items():
            if not isinstance(record, dict):
                continue
            game_date = self._pitcher_game_date(s_no, record, year)
            if game_date is None:
                continue
            games.append({**record, "_game_date": game_date, "_s_no": _to_int(s_no)})

        games.sort(key=lambda item: (item["_game_date"], item["_s_no"]))
        self._pitcher_cache[cache_key] = games
        return games

    @staticmethod
    def _pitcher_game_date(s_no: str, record: dict[str, Any], year: int) -> date | None:
        """Infer a date for a playerDay row."""
        raw_game_date = record.get("gameDate")
        if isinstance(raw_game_date, str) and "-" in raw_game_date:
            try:
                return datetime.strptime(f"{year}-{raw_game_date}", "%Y-%m-%d").date()
            except ValueError:
                return None
        if len(str(s_no)) >= 8 and str(s_no)[:4].isdigit():
            try:
                return datetime.strptime(str(s_no)[:8], "%Y%m%d").date()
            except ValueError:
                return None
        return None

    def _starter_features(
        self, p_no: int | None, game_date: date, year: int
    ) -> dict[str, float]:
        """Compute starter as-of features from playerDay only."""
        if p_no is None:
            return self._empty_starter_features()

        games = [
            game
            for game in self._load_pitcher_games(p_no, year)
            if game["_game_date"] < game_date and _ip_to_float(game.get("IP")) > 0
        ]
        starts = [game for game in games if _to_int(game.get("GS")) == 1]
        recent_starts = starts[-3:]
        last_game = games[-1] if games else None

        return {
            "starter_games": float(len(games)),
            "starter_starts": float(len(starts)),
            "starter_era": self._pitcher_era(games),
            "starter_whip": self._pitcher_whip(games),
            "starter_fip_proxy": self._pitcher_fip_proxy(games),
            "starter_era_last_3": self._pitcher_era(recent_starts),
            "starter_fip_proxy_last_3": self._pitcher_fip_proxy(recent_starts),
            "starter_days_rest": (
                float((game_date - last_game["_game_date"]).days) if last_game else _NAN
            ),
            "starter_np_last_game": _to_float(last_game.get("NP"))
            if last_game
            else _NAN,
        }

    @staticmethod
    def _empty_starter_features() -> dict[str, float]:
        """Return NaN starter features."""
        return {
            "starter_games": _NAN,
            "starter_starts": _NAN,
            "starter_era": _NAN,
            "starter_whip": _NAN,
            "starter_fip_proxy": _NAN,
            "starter_era_last_3": _NAN,
            "starter_fip_proxy_last_3": _NAN,
            "starter_days_rest": _NAN,
            "starter_np_last_game": _NAN,
        }

    @staticmethod
    def _pitcher_era(games: list[dict[str, Any]]) -> float:
        """Compute ERA from raw pitcher game rows."""
        innings = sum(_ip_to_float(game.get("IP")) for game in games)
        earned_runs = sum(_to_float(game.get("ER"), default=0.0) for game in games)
        return _safe_div(earned_runs * 9.0, innings)

    @staticmethod
    def _pitcher_whip(games: list[dict[str, Any]]) -> float:
        """Compute WHIP from raw pitcher game rows."""
        innings = sum(_ip_to_float(game.get("IP")) for game in games)
        walks_hits = sum(
            _to_float(game.get("BB"), default=0.0)
            + _to_float(game.get("H"), default=0.0)
            for game in games
        )
        return _safe_div(walks_hits, innings)

    @staticmethod
    def _pitcher_fip_proxy(games: list[dict[str, Any]]) -> float:
        """Compute a constant-free FIP proxy from raw pitcher game rows."""
        innings = sum(_ip_to_float(game.get("IP")) for game in games)
        home_runs = sum(_to_float(game.get("HR"), default=0.0) for game in games)
        walks = sum(_to_float(game.get("BB"), default=0.0) for game in games)
        hit_by_pitch = sum(_to_float(game.get("HP"), default=0.0) for game in games)
        strikeouts = sum(_to_float(game.get("SO"), default=0.0) for game in games)
        numerator = 13.0 * home_runs + 3.0 * (walks + hit_by_pitch) - 2.0 * strikeouts
        return _safe_div(numerator, innings)

    def _bullpen_features(
        self, team_code: int, game_date: date, year: int
    ) -> dict[str, float]:
        """Compute last-3-day bullpen proxy from available playerDay rows."""
        player_day_dir = Path(RAW_DIR) / str(year) / "player_day"
        if not player_day_dir.exists():
            return {"bullpen_ip_last_3": _NAN, "bullpen_era_last_3": _NAN}

        start_date = game_date - timedelta(days=3)
        bullpen_games: list[dict[str, Any]] = []
        for day_file in player_day_dir.glob(f"*_{year}.json"):
            p_no = _to_int(day_file.stem.split("_")[0])
            for game in self._load_pitcher_games(p_no, year):
                if not (start_date <= game["_game_date"] < game_date):
                    continue
                if _to_int(game.get("t_code")) != team_code:
                    continue
                if _to_int(game.get("GS")) == 1:
                    continue
                if _ip_to_float(game.get("IP")) > 0:
                    bullpen_games.append(game)

        return {
            "bullpen_ip_last_3": sum(
                _ip_to_float(game.get("IP")) for game in bullpen_games
            ),
            "bullpen_era_last_3": self._pitcher_era(bullpen_games),
        }

    def _load_batter_previous_season_stats(
        self, p_no: int, year: int
    ) -> dict[str, float] | None:
        """Load a batter's previous-season aggregate stats."""
        stats_year = year - 1
        cache_key = (p_no, stats_year)
        if cache_key in self._batter_season_cache:
            return self._batter_season_cache[cache_key]

        path = Path(RAW_DIR) / str(stats_year) / "player_season" / f"{p_no}.json"
        if not path.exists():
            self._batter_season_cache[cache_key] = None
            return None

        data = json.loads(path.read_text(encoding="utf-8"))
        basic_rows = data.get("basic", {}).get("list", [])
        deepen_rows = data.get("deepen", {}).get("list", [])
        if not isinstance(basic_rows, list):
            self._batter_season_cache[cache_key] = None
            return None

        for index, basic in enumerate(basic_rows):
            if not isinstance(basic, dict):
                continue
            if _to_int(basic.get("year")) != stats_year:
                continue

            deepen = deepen_rows[index] if index < len(deepen_rows) else {}
            if not isinstance(deepen, dict):
                deepen = {}

            stats = {
                "pa": _to_float(basic.get("PA"), default=0.0),
                "ops": _to_float(basic.get("OPS")),
                "woba": _to_float(deepen.get("wOBA")),
                "wrcplus": _to_float(basic.get("wRCplus")),
                "war": _to_float(basic.get("WAR"), default=0.0),
                "hr": _to_float(basic.get("HR"), default=0.0),
                "sb": _to_float(basic.get("SB"), default=0.0),
            }
            self._batter_season_cache[cache_key] = stats
            return stats

        self._batter_season_cache[cache_key] = None
        return None

    def _lineup_features(
        self, team_code: int, s_no: int, year: int
    ) -> dict[str, float]:
        """Aggregate starting-batter features from previous-season stats."""
        lineup = self._lineup_rows_for_team(team_code, s_no)
        if not lineup:
            return self._empty_lineup_features()

        player_rows: list[dict[str, float]] = []
        top_order_rows: list[dict[str, float]] = []
        for player in lineup:
            stats = self._load_batter_previous_season_stats(
                _to_int(player["p_no"]), year
            )
            if stats is None or stats["pa"] <= 0:
                continue
            player_rows.append(stats)
            batting_order = _to_float(player.get("batting_order_int"))
            if not pd.isna(batting_order) and batting_order <= 4:
                top_order_rows.append(stats)

        batter_count = float(len(lineup))
        covered_count = float(len(player_rows))
        bat_sides = [player.get("p_bat") for player in lineup]
        left_count = float(sum(_to_int(value) == 2 for value in bat_sides))
        switch_count = float(sum(_to_int(value) == 3 for value in bat_sides))

        return {
            "lineup_batter_count": batter_count,
            "lineup_prev_stats_coverage": _safe_div(covered_count, batter_count),
            "lineup_left_batter_count": left_count,
            "lineup_left_batter_ratio": _safe_div(left_count, batter_count),
            "lineup_switch_batter_count": switch_count,
            "lineup_prev_pa_sum": self._sum_player_stat(player_rows, "pa"),
            "lineup_prev_ops_pa_weighted": self._weighted_player_stat(
                player_rows, "ops"
            ),
            "lineup_prev_woba_pa_weighted": self._weighted_player_stat(
                player_rows, "woba"
            ),
            "lineup_prev_wrcplus_pa_weighted": self._weighted_player_stat(
                player_rows, "wrcplus"
            ),
            "lineup_prev_war_sum": self._sum_player_stat(player_rows, "war"),
            "lineup_prev_war_avg": self._mean_player_stat(player_rows, "war"),
            "lineup_prev_hr_sum": self._sum_player_stat(player_rows, "hr"),
            "lineup_prev_sb_sum": self._sum_player_stat(player_rows, "sb"),
            "lineup_top4_prev_ops_pa_weighted": self._weighted_player_stat(
                top_order_rows, "ops"
            ),
            "lineup_top4_prev_wrcplus_pa_weighted": self._weighted_player_stat(
                top_order_rows, "wrcplus"
            ),
        }

    @staticmethod
    def _empty_lineup_features() -> dict[str, float]:
        """Return empty lineup features."""
        return {
            "lineup_batter_count": 0.0,
            "lineup_prev_stats_coverage": _NAN,
            "lineup_left_batter_count": _NAN,
            "lineup_left_batter_ratio": _NAN,
            "lineup_switch_batter_count": _NAN,
            "lineup_prev_pa_sum": _NAN,
            "lineup_prev_ops_pa_weighted": _NAN,
            "lineup_prev_woba_pa_weighted": _NAN,
            "lineup_prev_wrcplus_pa_weighted": _NAN,
            "lineup_prev_war_sum": _NAN,
            "lineup_prev_war_avg": _NAN,
            "lineup_prev_hr_sum": _NAN,
            "lineup_prev_sb_sum": _NAN,
            "lineup_top4_prev_ops_pa_weighted": _NAN,
            "lineup_top4_prev_wrcplus_pa_weighted": _NAN,
        }

    @staticmethod
    def _sum_player_stat(rows: list[dict[str, float]], key: str) -> float:
        """Return a sum over player rows."""
        values = [row[key] for row in rows if not pd.isna(row[key])]
        if not values:
            return _NAN
        return float(sum(values))

    @staticmethod
    def _mean_player_stat(rows: list[dict[str, float]], key: str) -> float:
        """Return an unweighted mean over player rows."""
        values = [row[key] for row in rows if not pd.isna(row[key])]
        if not values:
            return _NAN
        return float(sum(values) / len(values))

    @staticmethod
    def _weighted_player_stat(rows: list[dict[str, float]], key: str) -> float:
        """Return a PA-weighted mean over player rows."""
        numerator = 0.0
        denominator = 0.0
        for row in rows:
            value = row[key]
            weight = row["pa"]
            if pd.isna(value) or pd.isna(weight) or weight <= 0:
                continue
            numerator += value * weight
            denominator += weight
        return _safe_div(numerator, denominator)

    def _prefixed(self, prefix: str, features: dict[str, float]) -> dict[str, float]:
        """Prefix a feature dictionary."""
        return {f"{prefix}_{key}": value for key, value in features.items()}

    def _matchup_features(self, row: dict[str, Any]) -> dict[str, float]:
        """Build home-vs-away comparison features from an assembled row."""
        diff_feature_names = [
            "games_played",
            "win_rate",
            "runs_for_pg",
            "runs_against_pg",
            "run_diff_pg",
            "win_rate_last_5",
            "runs_for_last_5",
            "runs_against_last_5",
            "run_diff_last_5",
            "starter_games",
            "starter_starts",
            "starter_era",
            "starter_whip",
            "starter_fip_proxy",
            "starter_era_last_3",
            "starter_fip_proxy_last_3",
            "starter_days_rest",
            "starter_np_last_game",
            "bullpen_ip_last_3",
            "bullpen_era_last_3",
            "lineup_batter_count",
            "lineup_prev_stats_coverage",
            "lineup_left_batter_count",
            "lineup_left_batter_ratio",
            "lineup_switch_batter_count",
            "lineup_prev_pa_sum",
            "lineup_prev_ops_pa_weighted",
            "lineup_prev_woba_pa_weighted",
            "lineup_prev_wrcplus_pa_weighted",
            "lineup_prev_war_sum",
            "lineup_prev_war_avg",
            "lineup_prev_hr_sum",
            "lineup_prev_sb_sum",
            "lineup_top4_prev_ops_pa_weighted",
            "lineup_top4_prev_wrcplus_pa_weighted",
        ]

        features = {
            f"home_minus_away_{name}": _safe_subtract(
                row.get(f"home_{name}"), row.get(f"away_{name}")
            )
            for name in diff_feature_names
        }
        features.update(
            {
                "team_win_rate_ratio": _win_rate_ratio(
                    row.get("home_win_rate"), row.get("away_win_rate")
                ),
                "team_recent_win_rate_ratio": _win_rate_ratio(
                    row.get("home_win_rate_last_5"),
                    row.get("away_win_rate_last_5"),
                ),
                "home_starter_missing": _missing_flag(row.get("home_starter_era")),
                "away_starter_missing": _missing_flag(row.get("away_starter_era")),
                "home_bullpen_missing": _missing_flag(
                    row.get("home_bullpen_era_last_3")
                ),
                "away_bullpen_missing": _missing_flag(
                    row.get("away_bullpen_era_last_3")
                ),
            }
        )
        return features

    def _build_row(self, game_row: pd.Series) -> dict[str, Any]:
        """Build a single feature row."""
        game_date = _game_date_from_row(game_row)
        year = _to_int(game_row["year"])
        home_code = _to_int(game_row["home_team_code"])
        away_code = _to_int(game_row["away_team_code"])
        home_sp_no = _to_int(game_row.get("home_sp_no")) or None
        away_sp_no = _to_int(game_row.get("away_sp_no")) or None

        row: dict[str, Any] = {
            "s_no": _to_int(game_row["s_no"]),
            "game_date": game_date.isoformat(),
            "year": year,
            "home_team_code": home_code,
            "away_team_code": away_code,
            "stadium_code": _to_int(game_row.get("stadium_code")),
            "game_time": game_row.get("game_time"),
            "home_starter_p_no": home_sp_no,
            "away_starter_p_no": away_sp_no,
            "day_of_week": game_date.weekday(),
            "month": game_date.month,
            "is_doubleheader": game_row.get("game_type") in (2, 3),
            "target_home_win": game_row.get("target_home_win"),
        }
        row.update(
            self._prefixed("home", self._team_features(home_code, game_date, year))
        )
        row.update(
            self._prefixed("away", self._team_features(away_code, game_date, year))
        )
        row.update(
            self._prefixed("home", self._starter_features(home_sp_no, game_date, year))
        )
        row.update(
            self._prefixed("away", self._starter_features(away_sp_no, game_date, year))
        )
        row.update(
            self._prefixed("home", self._bullpen_features(home_code, game_date, year))
        )
        row.update(
            self._prefixed("away", self._bullpen_features(away_code, game_date, year))
        )
        row.update(
            self._prefixed("home", self._lineup_features(home_code, row["s_no"], year))
        )
        row.update(
            self._prefixed("away", self._lineup_features(away_code, row["s_no"], year))
        )
        row.update(self._matchup_features(row))
        return row

    def build_features_for_year(self, year: int) -> pd.DataFrame:
        """Build and save feature rows for all regular-season games in year."""
        if self.games_df is None:
            self.load_clean_data()

        if self.games_df is None or self.games_df.empty:
            logger.warning("No clean games loaded")
            return pd.DataFrame()

        mask = (
            (self.games_df["year"] == year)
            & (self.games_df["league_type"] == LEAGUE_TYPE_REGULAR)
            & (self.games_df["game_state"] == GAME_STATE_FINISHED)
            & (~self.games_df["target_home_win"].isna())
        )
        games = (
            self.games_df[mask]
            .sort_values(["game_date", "s_no"])
            .reset_index(drop=True)
        )
        rows = [self._build_row(game_row) for _, game_row in games.iterrows()]
        features = pd.DataFrame(rows)

        out_path = Path(feature_csv_path(year))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        features.to_csv(out_path, index=False, encoding="utf-8-sig")
        logger.info("Saved {} feature rows to {}", len(features), out_path)
        return features

    def build_features_for_date(self, game_date: str) -> pd.DataFrame:
        """Build and upsert feature rows for regular-season games on one date."""
        if self.games_df is None:
            self.load_clean_data()

        if self.games_df is None or self.games_df.empty:
            logger.warning("No clean games loaded")
            return pd.DataFrame()

        target_date = pd.to_datetime(game_date).date()
        year = target_date.year
        dates = pd.to_datetime(self.games_df["game_date"], errors="coerce").dt.date
        mask = (
            (self.games_df["year"] == year)
            & (self.games_df["league_type"] == LEAGUE_TYPE_REGULAR)
            & (dates == target_date)
        )
        games = (
            self.games_df[mask]
            .sort_values(["game_date", "s_no"])
            .reset_index(drop=True)
        )
        rows = [self._build_row(game_row) for _, game_row in games.iterrows()]
        features = pd.DataFrame(rows)

        out_path = Path(feature_csv_path(year))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        existing = _read_csv_safe(str(out_path))
        if features.empty:
            combined = existing
        elif existing.empty:
            combined = features
        else:
            existing = existing[~existing["s_no"].isin(features["s_no"])]
            combined = pd.concat([existing, features], ignore_index=True)

        if not combined.empty:
            combined = combined.sort_values(["game_date", "s_no"]).reset_index(
                drop=True
            )
        combined.to_csv(out_path, index=False, encoding="utf-8-sig")
        logger.info(
            "Upserted {} feature rows for date={} into {}",
            len(features),
            game_date,
            out_path,
        )
        return features

    def build_features_for_game(self, s_no: int) -> pd.Series:
        """Build one feature row for a known game number."""
        if self.games_df is None:
            self.load_clean_data()
        if self.games_df is None or self.games_df.empty:
            return pd.Series({"error": "No clean games loaded"})

        matches = self.games_df[self.games_df["s_no"] == s_no]
        if matches.empty:
            return pd.Series({"error": f"Game s_no={s_no} not found"})
        return pd.Series(self._build_row(matches.iloc[0]))

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.feature_builder import FeatureBuilder


def test_build_features_for_date_upserts_unfinished_prediction_game(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Date-scoped prediction features should include pre-game rows."""
    games_path = tmp_path / "clean" / "games.csv"
    lineup_path = tmp_path / "clean" / "lineup_snapshot.csv"
    features_dir = tmp_path / "features"
    raw_dir = tmp_path / "raw"
    games_path.parent.mkdir(parents=True, exist_ok=True)
    lineup_path.parent.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir()

    pd.DataFrame(
        [
            {
                "s_no": 20260001,
                "game_date": "2026-06-10",
                "year": 2026,
                "league_type": 10100,
                "game_state": 3,
                "target_home_win": 1.0,
                "home_team_code": 1001,
                "away_team_code": 2002,
                "home_score": 5,
                "away_score": 3,
                "stadium_code": 7003,
                "game_time": "18:30",
                "game_type": 1,
                "home_sp_no": None,
                "away_sp_no": None,
            },
            {
                "s_no": 20260002,
                "game_date": "2026-06-11",
                "year": 2026,
                "league_type": 10100,
                "game_state": 1,
                "target_home_win": None,
                "home_team_code": 5002,
                "away_team_code": 7002,
                "home_score": None,
                "away_score": None,
                "stadium_code": 1001,
                "game_time": "18:30",
                "game_type": 1,
                "home_sp_no": None,
                "away_sp_no": None,
            },
        ]
    ).to_csv(games_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(
        columns=[
            "s_no",
            "team_code",
            "p_no",
            "batting_order",
            "is_starter",
            "is_pitcher",
            "p_bat",
        ]
    ).to_csv(lineup_path, index=False, encoding="utf-8-sig")

    monkeypatch.setattr("src.feature_builder.GAMES_CSV", str(games_path))
    monkeypatch.setattr("src.feature_builder.LINEUP_SNAPSHOT_CSV", str(lineup_path))
    monkeypatch.setattr("src.feature_builder.RAW_DIR", str(raw_dir))
    monkeypatch.setattr(
        "src.feature_builder.feature_csv_path",
        lambda year: str(features_dir / f"feature_game_pre_match_{year}.csv"),
    )

    builder = FeatureBuilder()
    builder.load_clean_data()

    year_features = builder.build_features_for_year(2026)
    date_features = builder.build_features_for_date("2026-06-11")
    saved = pd.read_csv(
        features_dir / "feature_game_pre_match_2026.csv", encoding="utf-8-sig"
    )

    assert year_features["s_no"].tolist() == [20260001]
    assert date_features["s_no"].tolist() == [20260002]
    assert saved["s_no"].tolist() == [20260001, 20260002]
    assert saved.loc[saved["s_no"] == 20260002, "game_date"].item() == "2026-06-11"


def test_build_features_for_date_handles_empty_year_feature_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prediction feature upsert should work when the yearly CSV has no rows."""
    games_path = tmp_path / "clean" / "games.csv"
    lineup_path = tmp_path / "clean" / "lineup_snapshot.csv"
    features_dir = tmp_path / "features"
    raw_dir = tmp_path / "raw"
    games_path.parent.mkdir(parents=True)
    raw_dir.mkdir()

    pd.DataFrame(
        [
            {
                "s_no": 20260002,
                "game_date": "2026-06-11",
                "year": 2026,
                "league_type": 10100,
                "game_state": 1,
                "target_home_win": None,
                "home_team_code": 5002,
                "away_team_code": 7002,
                "home_score": None,
                "away_score": None,
                "stadium_code": 1001,
                "game_time": "18:30",
                "game_type": 1,
                "home_sp_no": None,
                "away_sp_no": None,
            }
        ]
    ).to_csv(games_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(
        columns=[
            "s_no",
            "team_code",
            "p_no",
            "batting_order",
            "is_starter",
            "is_pitcher",
            "p_bat",
        ]
    ).to_csv(lineup_path, index=False, encoding="utf-8-sig")

    monkeypatch.setattr("src.feature_builder.GAMES_CSV", str(games_path))
    monkeypatch.setattr("src.feature_builder.LINEUP_SNAPSHOT_CSV", str(lineup_path))
    monkeypatch.setattr("src.feature_builder.RAW_DIR", str(raw_dir))
    monkeypatch.setattr(
        "src.feature_builder.feature_csv_path",
        lambda year: str(features_dir / f"feature_game_pre_match_{year}.csv"),
    )

    builder = FeatureBuilder()
    builder.load_clean_data()

    assert builder.build_features_for_year(2026).empty
    date_features = builder.build_features_for_date("2026-06-11")
    saved = pd.read_csv(
        features_dir / "feature_game_pre_match_2026.csv", encoding="utf-8-sig"
    )

    assert date_features["s_no"].tolist() == [20260002]
    assert saved["s_no"].tolist() == [20260002]


def test_lineup_features_use_previous_season_batter_stats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lineup features should use only the previous season's playerSeason row."""
    raw_dir = tmp_path / "raw"
    player_dir = raw_dir / "2024" / "player_season"
    player_dir.mkdir(parents=True)
    monkeypatch.setattr("src.feature_builder.RAW_DIR", str(raw_dir))

    (player_dir / "11.json").write_text(
        json.dumps(
            {
                "basic": {
                    "list": [
                        {
                            "p_no": 11,
                            "year": "2024",
                            "PA": "100",
                            "OPS": 0.8,
                            "wRCplus": 120.0,
                            "WAR": 2.0,
                            "HR": "10",
                            "SB": "3",
                        },
                        {
                            "p_no": 11,
                            "year": "2025",
                            "PA": "100",
                            "OPS": 2.0,
                            "wRCplus": 300.0,
                            "WAR": 9.0,
                            "HR": "40",
                            "SB": "20",
                        },
                    ]
                },
                "deepen": {"list": [{"wOBA": 0.36}, {"wOBA": 0.8}]},
            }
        ),
        encoding="utf-8",
    )
    (player_dir / "22.json").write_text(
        json.dumps(
            {
                "basic": {
                    "list": [
                        {
                            "p_no": 22,
                            "year": "2024",
                            "PA": "50",
                            "OPS": 1.0,
                            "wRCplus": 150.0,
                            "WAR": 1.0,
                            "HR": "5",
                            "SB": "1",
                        }
                    ]
                },
                "deepen": {"list": [{"wOBA": 0.4}]},
            }
        ),
        encoding="utf-8",
    )

    builder = FeatureBuilder()
    builder.lineups_df = pd.DataFrame(
        [
            {
                "s_no": 20250001,
                "team_code": 1001,
                "p_no": 11,
                "batting_order": "1",
                "is_starter": True,
                "is_pitcher": False,
                "p_bat": 2,
            },
            {
                "s_no": 20250001,
                "team_code": 1001,
                "p_no": 22,
                "batting_order": "2",
                "is_starter": True,
                "is_pitcher": False,
                "p_bat": 1,
            },
            {
                "s_no": 20250001,
                "team_code": 1001,
                "p_no": 99,
                "batting_order": "P",
                "is_starter": True,
                "is_pitcher": True,
                "p_bat": 1,
            },
        ]
    )

    features = builder._lineup_features(1001, 20250001, 2025)

    assert features["lineup_batter_count"] == 2.0
    assert features["lineup_prev_stats_coverage"] == 1.0
    assert features["lineup_prev_pa_sum"] == 150.0
    assert features["lineup_prev_ops_pa_weighted"] == pytest.approx(
        (0.8 * 100 + 1.0 * 50) / 150
    )
    assert features["lineup_prev_woba_pa_weighted"] == pytest.approx(
        (0.36 * 100 + 0.4 * 50) / 150
    )
    assert features["lineup_prev_wrcplus_pa_weighted"] == pytest.approx(130.0)
    assert features["lineup_prev_war_sum"] == 3.0
    assert features["lineup_prev_hr_sum"] == 15.0

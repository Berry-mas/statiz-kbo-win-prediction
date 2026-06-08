from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.feature_builder import FeatureBuilder


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

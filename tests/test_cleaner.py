from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src import cleaner as cleaner_module
from src.cleaner import DataCleaner
from src.constants import GAME_STATE_FINISHED, GAME_STATE_RAINOUT_COLD


def test_clean_games_treats_rain_shortened_game_as_final(
    tmp_path: Path, monkeypatch
) -> None:
    raw_dir = tmp_path / "raw"
    schedule_dir = raw_dir / "2026" / "schedule"
    schedule_dir.mkdir(parents=True)
    games_csv = tmp_path / "games.csv"
    schedule = {
        "0619": [
            {
                "s_no": 20260360,
                "year": 2026,
                "month": 6,
                "day": 19,
                "state": GAME_STATE_RAINOUT_COLD,
                "homeScore": 9,
                "awayScore": 3,
            },
            {
                "s_no": 20260359,
                "year": 2026,
                "month": 6,
                "day": 19,
                "state": GAME_STATE_FINISHED,
                "homeScore": 3,
                "awayScore": 3,
            },
        ]
    }
    (schedule_dir / "2026-06-19.json").write_text(
        json.dumps(schedule), encoding="utf-8"
    )
    monkeypatch.setattr(cleaner_module, "RAW_DIR", str(raw_dir))
    monkeypatch.setattr(cleaner_module, "GAMES_CSV", str(games_csv))

    cleaned = DataCleaner().clean_games(2026).set_index("s_no")

    assert cleaned.loc[20260360, "target_home_win"] == 1.0
    assert bool(cleaned.loc[20260360, "is_cancelled"]) is False
    assert pd.isna(cleaned.loc[20260359, "target_home_win"])

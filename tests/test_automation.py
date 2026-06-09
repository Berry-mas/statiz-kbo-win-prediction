from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from src.automation import (
    KST,
    AutomationConfig,
    _build_decisions,
    _deadline_status,
    _parse_game_datetime,
    parse_kst_datetime,
)


def test_build_decisions_marks_lineup_missing_fallback() -> None:
    now_game_time = (datetime.now(tz=KST) + timedelta(hours=2)).strftime("%H:%M")
    games = pd.DataFrame(
        [
            {
                "s_no": 20260001,
                "game_date": "2026-06-09",
                "game_time": now_game_time,
            }
        ]
    )
    predictions = [
        {
            "s_no": 20260001,
            "home_win_probability": 52.346,
            "model_version": "lgbm_test",
        }
    ]

    decisions = _build_decisions(
        game_date="2026-06-09",
        games=games,
        predictions=predictions,
        lineups=pd.DataFrame(),
        model_version="lgbm_test",
        config=AutomationConfig(),
    )

    assert decisions[0]["status"] == "lineup_missing_fallback"
    assert decisions[0]["lineup_missing"] is True
    assert decisions[0]["would_submit"] is True
    assert decisions[0]["payload"] == {"s_no": 20260001, "percent": 52.35}


def test_deadline_status_forbids_after_hard_deadline() -> None:
    now = datetime(2026, 6, 9, 18, 50, tzinfo=KST)
    game_dt = datetime(2026, 6, 9, 19, 0, tzinfo=KST)

    status = _deadline_status(now, game_dt, AutomationConfig())

    assert status == "past_hard_deadline"


def test_parse_game_datetime_accepts_seconds() -> None:
    parsed = _parse_game_datetime("2025-10-01", "18:30:00")

    assert parsed is not None
    assert parsed.hour == 18
    assert parsed.minute == 30
    assert parsed.tzinfo == KST


def test_build_decisions_uses_injected_now_for_deadline() -> None:
    games = pd.DataFrame(
        [
            {
                "s_no": 20260001,
                "game_date": "2026-06-09",
                "game_time": "18:30:00",
            }
        ]
    )
    predictions = [
        {
            "s_no": 20260001,
            "home_win_probability": 51.0,
            "model_version": "lgbm_test",
        }
    ]
    lineups = pd.DataFrame(
        [
            {
                "s_no": 20260001,
                "is_starter": True,
            }
        ]
    )

    decisions = _build_decisions(
        game_date="2026-06-09",
        games=games,
        predictions=predictions,
        lineups=lineups,
        model_version="lgbm_test",
        config=AutomationConfig(now=parse_kst_datetime("2026-06-09T17:30:00+09:00")),
    )

    assert decisions[0]["checked_at"] == "2026-06-09T17:30:00+09:00"
    assert decisions[0]["status"] == "ready"
    assert decisions[0]["would_submit"] is True


def test_parse_kst_datetime_converts_utc_z_suffix() -> None:
    parsed = parse_kst_datetime("2026-06-09T08:30:00Z")

    assert parsed.isoformat() == "2026-06-09T17:30:00+09:00"

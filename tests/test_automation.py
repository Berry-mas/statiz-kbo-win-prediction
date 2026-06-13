from __future__ import annotations

from datetime import datetime

import pandas as pd

from src.automation import (
    KST,
    AutomationConfig,
    _already_submitted_snos,
    _build_decisions,
    _deadline_status,
    _mark_already_submitted,
    _notify_successful_submissions,
    _parse_game_datetime,
    _submission_message,
    parse_kst_datetime,
)


def test_build_decisions_marks_lineup_missing_fallback() -> None:
    now = datetime(2026, 6, 9, 16, 0, tzinfo=KST)
    game_date = "2026-06-09"
    now_game_time = "18:30"
    games = pd.DataFrame(
        [
            {
                "s_no": 20260001,
                "game_date": game_date,
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
        game_date=game_date,
        games=games,
        predictions=predictions,
        lineups=pd.DataFrame(),
        model_version="lgbm_test",
        config=AutomationConfig(now=now),
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


def test_deadline_status_marks_too_early_when_min_lead_is_set() -> None:
    now = datetime(2026, 6, 9, 17, 30, tzinfo=KST)
    game_dt = datetime(2026, 6, 9, 18, 30, tzinfo=KST)

    status = _deadline_status(now, game_dt, AutomationConfig(min_lead_minutes=35))

    assert status == "too_early"


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


def test_mark_already_submitted_disables_duplicate_submission(
    tmp_path, monkeypatch
) -> None:
    log_path = tmp_path / "submission_log.csv"
    pd.DataFrame(
        [
            {
                "s_no": 20260001,
                "game_date": "2026-06-09",
                "submitted": True,
            }
        ]
    ).to_csv(log_path, index=False, encoding="utf-8-sig")
    monkeypatch.setattr("src.automation.SUBMISSION_LOG_CSV", str(log_path))
    decisions = [
        {
            "s_no": 20260001,
            "status": "ready",
            "reason": "Lineup available and before safe cutoff",
            "would_submit": True,
            "payload": {"s_no": 20260001, "percent": 51.0},
        }
    ]

    assert _already_submitted_snos("2026-06-09") == {20260001}

    _mark_already_submitted(decisions, "2026-06-09")

    assert decisions[0]["status"] == "already_submitted"
    assert decisions[0]["would_submit"] is False
    assert decisions[0]["payload"] == {}


def test_manual_submission_does_not_block_later_auto_submission(
    tmp_path, monkeypatch
) -> None:
    log_path = tmp_path / "submission_log.csv"
    pd.DataFrame(
        [
            {
                "s_no": 20260001,
                "game_date": "2026-06-09",
                "submitted": True,
                "source": "manual",
            },
            {
                "s_no": 20260002,
                "game_date": "2026-06-09",
                "submitted": True,
                "source": "auto",
            },
        ]
    ).to_csv(log_path, index=False, encoding="utf-8-sig")
    monkeypatch.setattr("src.automation.SUBMISSION_LOG_CSV", str(log_path))
    decisions = [
        {
            "s_no": 20260001,
            "status": "ready",
            "reason": "Lineup available and before safe cutoff",
            "would_submit": True,
            "payload": {"s_no": 20260001, "percent": 51.0},
        },
        {
            "s_no": 20260002,
            "status": "ready",
            "reason": "Lineup available and before safe cutoff",
            "would_submit": True,
            "payload": {"s_no": 20260002, "percent": 52.0},
        },
    ]

    assert _already_submitted_snos("2026-06-09", source="auto") == {20260002}
    assert _already_submitted_snos("2026-06-09", source="manual") == {20260001}

    _mark_already_submitted(decisions, "2026-06-09", source="auto")

    assert decisions[0]["status"] == "ready"
    assert decisions[0]["would_submit"] is True
    assert decisions[1]["status"] == "already_submitted"
    assert decisions[1]["would_submit"] is False


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send(self, title, message, fields=None):
        self.sent.append({"title": title, "message": message, "fields": fields or {}})
        return True


def test_notify_successful_submissions_skips_when_no_success() -> None:
    notifier = FakeNotifier()
    decisions = [
        {
            "s_no": 20260001,
            "game_time": "18:30",
            "home_team_code": 5002,
            "away_team_code": 2002,
            "home_win_probability": 57.12,
        }
    ]

    _notify_successful_submissions(
        notifier,
        decisions,
        submission_results=[{"s_no": 20260001, "submitted": False}],
        public_count=0,
    )

    assert notifier.sent == []


def test_notify_successful_submissions_includes_matchup_and_prediction() -> None:
    notifier = FakeNotifier()
    decisions = [
        {
            "s_no": 20260001,
            "game_time": "18:30",
            "home_team_code": 5002,
            "away_team_code": 2002,
            "home_win_probability": 57.12,
        },
        {
            "s_no": 20260002,
            "game_time": "18:30",
            "home_team_code": 1001,
            "away_team_code": 7002,
            "home_win_probability": 44.4,
        },
    ]

    _notify_successful_submissions(
        notifier,
        decisions,
        submission_results=[{"s_no": 20260001, "submitted": True}],
        public_count=0,
    )

    assert len(notifier.sent) == 1
    assert notifier.sent[0]["title"] == "Statiz submission succeeded"
    assert "18:30 KIA vs LG: LG 승률 57.12%" in notifier.sent[0]["message"]
    assert "한화" not in notifier.sent[0]["message"]


def test_submission_message_uses_away_team_when_home_probability_below_half() -> None:
    message = _submission_message(
        {
            "game_time": "17:00",
            "home_team_code": 1001,
            "away_team_code": 7002,
            "home_win_probability": 44.4,
        }
    )

    assert message == "- 17:00 한화 vs 삼성: 한화 승률 55.60% (제출 홈팀 승률 44.40%)"

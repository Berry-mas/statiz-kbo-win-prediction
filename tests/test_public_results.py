from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from src import public_results
from src.submission_log import read_submission_log


def test_export_public_results_includes_only_finalized_submitted_games(
    tmp_path: Path, monkeypatch
) -> None:
    games_csv = tmp_path / "games.csv"
    prediction_log = tmp_path / "prediction_log.csv"
    submission_log = tmp_path / "submission_log.csv"
    output_json = tmp_path / "results.json"
    scheduler_log = tmp_path / "scheduler_run_log.csv"

    pd.DataFrame(
        [
            {
                "s_no": 20260001,
                "game_date": "2026-06-09",
                "home_team_code": 1001,
                "away_team_code": 2002,
                "home_score": 5,
                "away_score": 3,
                "game_state": 3,
                "target_home_win": 1.0,
            },
            {
                "s_no": 20260002,
                "game_date": "2026-06-09",
                "home_team_code": 3001,
                "away_team_code": 5002,
                "home_score": None,
                "away_score": None,
                "game_state": 2,
                "target_home_win": None,
            },
        ]
    ).to_csv(games_csv, index=False, encoding="utf-8-sig")
    pd.DataFrame(
        [
            {
                "s_no": 20260001,
                "game_date": "2026-06-09",
                "home_win_probability": 42.0,
                "model_version": "lgbm_test",
                "predicted_at": "2026-06-09T09:00:00+00:00",
            },
            {
                "s_no": 20260002,
                "game_date": "2026-06-09",
                "home_win_probability": 41.2,
                "model_version": "lgbm_test",
                "predicted_at": "2026-06-09T09:00:00+00:00",
            },
        ]
    ).to_csv(prediction_log, index=False, encoding="utf-8-sig")
    pd.DataFrame(
        [
            {
                "s_no": 20260001,
                "game_date": "2026-06-09",
                "submitted_prob": 57.12,
                "submitted": True,
                "source": "manual",
                "attempts": 1,
                "submitted_at": "2026-06-09T17:30:00+09:00",
                "response_status": 0,
                "response_message": "ok",
            },
            {
                "s_no": 20260002,
                "game_date": "2026-06-09",
                "submitted_prob": 41.2,
                "submitted": True,
                "source": "auto",
                "attempts": 1,
                "submitted_at": "2026-06-09T17:10:00+09:00",
                "response_status": 0,
                "response_message": "ok",
            },
        ]
    ).to_csv(submission_log, index=False, encoding="utf-8-sig")
    pd.DataFrame(
        [
            {
                "run_id": "run-public-test",
                "checked_at": "2026-06-09T17:20:00+09:00",
                "game_date": "2026-06-09",
                "s_no": 20260001,
                "game_time": "18:30",
                "home_team_code": 1001,
                "away_team_code": 2002,
                "home_sp_name": "홈선발",
                "away_sp_name": "원정선발",
                "model_version": "lgbm_test",
                "home_win_probability": 57.12,
                "starter_confirmed": True,
                "starting_pitcher_count": 2,
                "starting_batter_count": 0,
                "batting_lineup_missing": True,
                "status": "lineup_missing_fallback",
                "reason": "Batting lineup missing before safe cutoff; fallback prediction allowed",
                "would_submit": True,
                "execute_submit": True,
                "payload": "{'internal_payload': 'private-row-detail'}",
            },
        ]
    ).to_csv(scheduler_log, index=False, encoding="utf-8-sig")

    monkeypatch.setattr(public_results, "GAMES_CSV", str(games_csv))
    monkeypatch.setattr(public_results, "PREDICTION_LOG_CSV", str(prediction_log))
    monkeypatch.setattr(public_results, "SUBMISSION_LOG_CSV", str(submission_log))
    monkeypatch.setattr(public_results, "SCHEDULER_RUN_LOG_CSV", str(scheduler_log))

    payload = public_results.export_public_results(str(output_json))

    assert payload["schema_version"] == 3
    assert payload["model_version"] == "lgbm_test"
    assert len(payload["results"]) == 1
    assert payload["results"][0]["s_no"] == 20260001
    assert payload["results"][0]["home_team"] == {
        "name": "삼성",
        "logo_key": "samsung",
    }
    assert payload["results"][0]["home_win_probability"] == 57.12
    assert payload["results"][0]["predicted_winner"] == "home"
    assert payload["results"][0]["correct"] is True
    assert payload["manual_workflow"]["status"] == "success"
    assert payload["manual_workflow"]["submitted_games"] == 1
    assert payload["latest_submission"]["source"] == "manual"
    assert payload["model_metrics"]["window"]["sample_size"] == 1
    assert payload["model_metrics"]["window"]["type"] == (
        "all_finalized_submitted_games"
    )
    assert payload["model_metrics"]["window"]["requested"] is None
    assert payload["model_metrics"]["accuracy"] == 1.0
    assert payload["recent_games"][0]["probability_published"] is True
    assert payload["recent_games"][0]["home_win_probability"] == 57.12
    assert payload["recent_games"][0]["predicted_winner"] == "home"
    assert payload["recent_games"][0]["correct"] is True
    assert (
        payload["recent_games"][0]["scheduler"]["status"] == "lineup_missing_fallback"
    )
    assert payload["recent_games"][0]["scheduler"]["home_sp_name"] == "홈선발"
    assert payload["recent_games"][0]["scheduler"]["away_sp_name"] == "원정선발"
    assert payload["recent_games"][0]["home_sp_name"] == "홈선발"
    assert payload["recent_games"][0]["away_sp_name"] == "원정선발"
    unfinalized_row = next(
        row for row in payload["recent_games"] if row["s_no"] == 20260002
    )
    assert unfinalized_row["probability_published"] is True
    assert unfinalized_row["home_win_probability"] == 41.2
    assert unfinalized_row["predicted_winner"] is None
    assert unfinalized_row["correct"] is None
    assert "payload" not in payload["recent_games"][0]["scheduler"]
    assert "internal_payload" not in output_json.read_text(encoding="utf-8")
    assert output_json.exists()


def test_submission_log_reader_accepts_mixed_legacy_and_source_rows(
    tmp_path: Path,
) -> None:
    submission_log = tmp_path / "submission_log.csv"
    submission_log.write_text(
        "\ufeff"
        "s_no,game_date,submitted_prob,submitted,attempts,submitted_at,response_status,response_message\n"
        "20260330,2026-06-12,52.73,False,3,2026-06-12T18:03:50+09:00,,old failure\n"
        "20260331,2026-06-13,59.28,False,manual,3,2026-06-13T14:45:14+09:00,400,"
        "\"{'result_cd': 400, 'result_msg': '필수 값이 누락되었습니다.', 'update_time': None}\"\n",
        encoding="utf-8",
    )

    parsed = read_submission_log(submission_log)

    assert parsed["source"].tolist() == ["auto", "manual"]
    assert parsed["attempts"].tolist() == [3, 3]


def test_scheduler_log_reader_skips_malformed_optional_rows(
    tmp_path: Path, monkeypatch
) -> None:
    scheduler_log = tmp_path / "scheduler_run_log.csv"
    scheduler_log.write_text(
        "s_no,checked_at,status\n"
        "2026061301,2026-06-13T18:00:00+09:00,lineup_missing_fallback\n"
        "2026061302,2026-06-13T18:10:00+09:00,submitted,extra,fields\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(public_results, "SCHEDULER_RUN_LOG_CSV", str(scheduler_log))

    parsed = public_results._read_csv(str(scheduler_log))

    assert parsed["s_no"].tolist() == [2026061301]
    assert parsed["status"].tolist() == ["lineup_missing_fallback"]


def test_public_game_status_uses_game_time_when_schedule_state_is_stale() -> None:
    row = pd.Series(
        {
            "game_state": 1,
            "game_date": "2026-06-14",
            "game_time": "14:00:00",
        }
    )

    assert (
        public_results._public_game_status(
            row,
            datetime(2026, 6, 14, 4, 55, tzinfo=UTC),
        )
        == "scheduled"
    )
    assert (
        public_results._public_game_status(
            row,
            datetime(2026, 6, 14, 5, 0, tzinfo=UTC),
        )
        == "in_progress"
    )


def test_rain_shortened_game_is_final_and_graded() -> None:
    row = pd.Series(
        {
            "s_no": 20260360,
            "game_date": "2026-06-19",
            "game_state": 5,
            "home_team_code": 11001,
            "away_team_code": 9002,
            "home_score": 9,
            "away_score": 3,
            "target_home_win": 1.0,
            "home_win_probability": 48.36,
        }
    )

    result = public_results._recent_game_row(row, datetime.now(tz=UTC))

    assert result["game_status"] == "final"
    assert result["home_score"] == 9
    assert result["away_score"] == 3
    assert result["predicted_winner"] == "away"
    assert result["actual_winner"] == "home"
    assert result["correct"] is False


def test_draw_publishes_score_without_model_grade() -> None:
    row = pd.Series(
        {
            "s_no": 20260359,
            "game_date": "2026-06-19",
            "game_state": 3,
            "home_team_code": 7002,
            "away_team_code": 1001,
            "home_score": 3,
            "away_score": 3,
            "target_home_win": float("nan"),
            "home_win_probability": 48.89,
        }
    )

    result = public_results._recent_game_row(row, datetime.now(tz=UTC))

    assert result["game_status"] == "final"
    assert result["home_score"] == 3
    assert result["away_score"] == 3
    assert result["predicted_winner"] == "away"
    assert result["actual_winner"] is None
    assert result["correct"] is None


def test_recent_game_date_limit_keeps_whole_dates() -> None:
    merged = pd.DataFrame(
        [
            {"s_no": 1, "game_date": "2026-06-16"},
            {"s_no": 2, "game_date": "2026-06-16"},
            {"s_no": 3, "game_date": "2026-06-15"},
            {"s_no": 4, "game_date": "2026-06-15"},
            {"s_no": 5, "game_date": "2026-06-14"},
        ]
    )

    limited = public_results._limit_recent_game_dates(merged, 2)

    assert limited["s_no"].tolist() == [1, 2, 3, 4]


def test_model_metrics_use_all_finalized_submitted_games() -> None:
    rows = [
        {
            "home_win_probability": 60.0,
            "actual_winner": "home" if index < 13 else "away",
            "correct": index < 13,
        }
        for index in range(25)
    ]

    metrics = public_results._build_model_metrics(rows)

    assert metrics["window"] == {
        "type": "all_finalized_submitted_games",
        "requested": None,
        "sample_size": 25,
    }
    assert metrics["accuracy"] == 0.52

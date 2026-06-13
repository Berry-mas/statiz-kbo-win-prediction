from __future__ import annotations

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
                "home_win_probability": 57.12,
                "model_version": "lgbm_test",
                "predicted_at": "2026-06-09T09:00:00+00:00",
            },
            {
                "s_no": 20260002,
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
                "run_id": "run-secret-ish",
                "checked_at": "2026-06-09T17:20:00+09:00",
                "game_date": "2026-06-09",
                "s_no": 20260001,
                "game_time": "18:30",
                "home_team_code": 1001,
                "away_team_code": 2002,
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
                "payload": "{'secret_strategy': 'do-not-publish'}",
            },
        ]
    ).to_csv(scheduler_log, index=False, encoding="utf-8-sig")

    monkeypatch.setattr(public_results, "GAMES_CSV", str(games_csv))
    monkeypatch.setattr(public_results, "PREDICTION_LOG_CSV", str(prediction_log))
    monkeypatch.setattr(public_results, "SUBMISSION_LOG_CSV", str(submission_log))
    monkeypatch.setattr(public_results, "SCHEDULER_RUN_LOG_CSV", str(scheduler_log))

    payload = public_results.export_public_results(str(output_json))

    assert payload["schema_version"] == 2
    assert payload["model_version"] == "lgbm_test"
    assert len(payload["results"]) == 1
    assert payload["results"][0]["s_no"] == 20260001
    assert payload["results"][0]["home_team"] == {
        "name": "삼성",
        "logo_key": "samsung",
    }
    assert payload["manual_workflow"]["status"] == "success"
    assert payload["manual_workflow"]["submitted_games"] == 1
    assert payload["latest_submission"]["source"] == "manual"
    assert payload["model_metrics"]["window"]["sample_size"] == 1
    assert payload["model_metrics"]["accuracy"] == 1.0
    assert payload["recent_games"][0]["probability_published"] is True
    assert payload["recent_games"][0]["scheduler"]["status"] == "lineup_missing_fallback"
    assert "payload" not in payload["recent_games"][0]["scheduler"]
    assert "secret_strategy" not in output_json.read_text(encoding="utf-8")
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

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src import public_results


def test_export_public_results_includes_only_finalized_submitted_games(
    tmp_path: Path, monkeypatch
) -> None:
    games_csv = tmp_path / "games.csv"
    prediction_log = tmp_path / "prediction_log.csv"
    submission_log = tmp_path / "submission_log.csv"
    output_json = tmp_path / "results.json"

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
                "submitted": True,
                "submitted_at": "2026-06-09T17:30:00+09:00",
            },
            {
                "s_no": 20260002,
                "submitted": True,
                "submitted_at": "2026-06-09T17:30:00+09:00",
            },
        ]
    ).to_csv(submission_log, index=False, encoding="utf-8-sig")

    monkeypatch.setattr(public_results, "GAMES_CSV", str(games_csv))
    monkeypatch.setattr(public_results, "PREDICTION_LOG_CSV", str(prediction_log))
    monkeypatch.setattr(public_results, "SUBMISSION_LOG_CSV", str(submission_log))

    payload = public_results.export_public_results(str(output_json))

    assert len(payload["results"]) == 1
    assert payload["results"][0]["s_no"] == 20260001
    assert payload["results"][0]["home_team"] == "삼성"
    assert output_json.exists()

from __future__ import annotations

from src import predictor
from src.predictor import Predictor


def test_predict_games_returns_empty_for_empty_feature_csv(tmp_path, monkeypatch):
    feature_csv = tmp_path / "feature_game_pre_match_2026.csv"
    feature_csv.write_text("", encoding="utf-8-sig")
    monkeypatch.setattr(predictor, "feature_csv_path", lambda year: str(feature_csv))

    instance = Predictor.__new__(Predictor)

    assert instance.predict_games("2026-06-11") == []


def test_predict_games_returns_empty_for_missing_feature_csv(tmp_path, monkeypatch):
    feature_csv = tmp_path / "missing.csv"
    monkeypatch.setattr(predictor, "feature_csv_path", lambda year: str(feature_csv))

    instance = Predictor.__new__(Predictor)

    assert instance.predict_games("2026-06-11") == []

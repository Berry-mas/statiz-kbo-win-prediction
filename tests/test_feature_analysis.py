from __future__ import annotations

import importlib.util
import json

import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest

from src.feature_analysis import (
    publish_feature_analysis_to_web,
    visualize_lgbm_feature_effects,
)


@pytest.mark.skipif(
    importlib.util.find_spec("matplotlib") is None
    or importlib.util.find_spec("shap") is None,
    reason="feature analysis plotting dependencies are not installed",
)
def test_visualize_lgbm_feature_effects_writes_artifacts(tmp_path):
    rng = np.random.default_rng(42)
    x1 = rng.normal(size=80)
    x2 = rng.normal(size=80)
    X = pd.DataFrame(
        {
            "team_win_rate_ratio": x1,
            "starter_era_diff": x2,
            "home_team_code": rng.integers(0, 4, size=80),
        }
    )
    game_metadata = pd.DataFrame(
        {
            "s_no": np.arange(20250001, 20250081),
            "game_date": ["2025-09-01"] * 80,
            "home_team_code": [1001] * 80,
            "away_team_code": [2002] * 80,
        }
    )
    y = ((x1 - 0.4 * x2) > 0).astype(int)
    dataset = lgb.Dataset(X, label=y)
    model = lgb.train(
        {
            "objective": "binary",
            "metric": "binary_logloss",
            "verbose": -1,
            "seed": 42,
        },
        dataset,
        num_boost_round=8,
    )

    manifest = visualize_lgbm_feature_effects(
        model,
        X,
        y_valid=y,
        game_metadata=game_metadata,
        output_dir=tmp_path / "analysis",
        top_n=2,
        dependence_features=["team_win_rate_ratio", "missing_feature"],
        model_version="test_model",
    )

    analysis_dir = tmp_path / "analysis"
    assert manifest["model_version"] == "test_model"
    assert (analysis_dir / "manifest.json").exists()
    assert (analysis_dir / "lgbm_feature_importance.csv").exists()
    assert (analysis_dir / "shap_importance.csv").exists()
    assert (analysis_dir / "permutation_importance.csv").exists()
    assert (analysis_dir / "lgbm_gain_top2.png").exists()
    assert (analysis_dir / "shap_summary.png").exists()
    assert (analysis_dir / "dependence_team_win_rate_ratio.png").exists()
    assert (analysis_dir / "feature_signal_network.json").exists()
    assert (analysis_dir / "feature_agreement.json").exists()
    assert (analysis_dir / "feature_family_summary.json").exists()
    assert (analysis_dir / "feature_game_explanations.json").exists()
    assert "missing_feature" not in manifest["dependence_images"]
    assert manifest["network_path"] == "feature_signal_network.json"
    assert manifest["agreement_path"] == "feature_agreement.json"
    assert manifest["family_summary_path"] == "feature_family_summary.json"
    assert manifest["game_explanations_path"] == "feature_game_explanations.json"

    game_explanations = json.loads(
        (analysis_dir / "feature_game_explanations.json").read_text(encoding="utf-8")
    )
    assert game_explanations["schema_version"] == 1
    assert game_explanations["display_count"] > 0
    assert game_explanations["games"][0]["home_team"]["name"] == "삼성"


def test_publish_feature_analysis_to_web_rewrites_manifest_paths(tmp_path):
    analysis_dir = tmp_path / "analysis"
    analysis_dir.mkdir()
    (analysis_dir / "chart.png").write_bytes(b"image")
    (analysis_dir / "importance.csv").write_text(
        "feature,value\nx,1\n", encoding="utf-8"
    )
    (analysis_dir / "feature_signal_network.json").write_text(
        '{"schema_version": 1, "nodes": [], "edges": []}', encoding="utf-8"
    )
    (analysis_dir / "feature_agreement.json").write_text(
        '{"schema_version": 1, "methods": [], "rows": []}', encoding="utf-8"
    )
    (analysis_dir / "feature_family_summary.json").write_text(
        '{"schema_version": 1, "families": []}', encoding="utf-8"
    )
    (analysis_dir / "feature_game_explanations.json").write_text(
        '{"schema_version": 1, "games": []}', encoding="utf-8"
    )
    (analysis_dir / "manifest.json").write_text(
        """
        {
          "schema_version": 1,
          "source_model_dir": "artifacts/model_registry/test_model",
          "sections": [
            {
              "id": "gain",
              "title": "Gain",
              "description": "Gain chart",
              "image_path": "chart.png",
              "csv_path": "importance.csv"
            }
          ],
          "csv_paths": {"gain": "importance.csv"},
          "dependence_images": {"x": "chart.png"},
          "network_path": "feature_signal_network.json",
          "agreement_path": "feature_agreement.json",
          "family_summary_path": "feature_family_summary.json",
          "game_explanations_path": "feature_game_explanations.json"
        }
        """,
        encoding="utf-8",
    )

    manifest_path = publish_feature_analysis_to_web(
        analysis_dir,
        public_dir=tmp_path / "public" / "feature-analysis",
    )

    manifest = manifest_path.read_text(encoding="utf-8")
    assert "/feature-analysis/chart.png" in manifest
    assert "/feature-analysis/importance.csv" in manifest
    assert "/feature-analysis/feature_signal_network.json" in manifest
    assert "/feature-analysis/feature_agreement.json" in manifest
    assert "/feature-analysis/feature_family_summary.json" in manifest
    assert "/feature-analysis/feature_game_explanations.json" in manifest
    assert "source_model_dir" not in manifest
    assert (tmp_path / "public" / "feature-analysis" / "chart.png").exists()
    assert (
        tmp_path / "public" / "feature-analysis" / "feature_signal_network.json"
    ).exists()
    assert (
        tmp_path / "public" / "feature-analysis" / "feature_agreement.json"
    ).exists()
    assert (
        tmp_path / "public" / "feature-analysis" / "feature_family_summary.json"
    ).exists()
    assert (
        tmp_path / "public" / "feature-analysis" / "feature_game_explanations.json"
    ).exists()

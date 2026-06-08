"""
Predictor: Load LightGBM ensemble and produce home win probabilities.

Loads all seed models from a model registry version directory and averages
predictions to generate calibrated home team win probabilities.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from loguru import logger

from .constants import MODEL_REGISTRY_DIR, PREDICTION_LOG_CSV, feature_csv_path
from .feature_matrix import prepare_model_matrix


def normalize_prob(p: float) -> float:
    """Normalize probability to valid submission range.

    Rules:
    - Clamp to [0.01, 99.99]
    - Round to 2 decimal places
    - 50.00 is invalid -> convert to 50.01
    """
    p = max(0.01, min(99.99, p))
    p = round(p, 2)
    if p == 50.00:
        p = 50.01
    return p


class Predictor:
    def __init__(self, model_version: str | None = None) -> None:
        self.registry_dir = Path(MODEL_REGISTRY_DIR)

        if model_version is None:
            self.model_version = self._load_latest_model_version()
        else:
            self.model_version = model_version

        self.models: list[lgb.Booster] = []
        self.feature_list: list[str] = []
        self.categorical_features: list[str] = []

        self.load_model(self.model_version)

    # ------------------------------------------------------------------
    # Version discovery
    # ------------------------------------------------------------------

    def _load_latest_model_version(self) -> str:
        """Find latest lgbm_v* directory by version number."""
        if not self.registry_dir.exists():
            raise FileNotFoundError(
                f"Model registry directory not found: {self.registry_dir}"
            )

        prefix = "lgbm_v"
        candidates = [
            d.name
            for d in self.registry_dir.iterdir()
            if d.is_dir() and d.name.startswith(prefix)
        ]

        if not candidates:
            raise FileNotFoundError(f"No model versions found in {self.registry_dir}")

        # Sort by version number (numeric suffix)
        def _version_num(name: str) -> int:
            try:
                return int(name.replace(prefix, ""))
            except ValueError:
                return -1

        latest = sorted(candidates, key=_version_num)[-1]
        logger.info("Auto-detected latest model version: {}", latest)
        return latest

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def load_model(self, version: str) -> None:
        """Load all seed models from artifacts/model_registry/{version}/."""
        version_dir = self.registry_dir / version
        if not version_dir.exists():
            raise FileNotFoundError(f"Model version directory not found: {version_dir}")

        # Load seed models
        model_files = sorted(version_dir.glob("model_seed*.txt"))
        if not model_files:
            raise FileNotFoundError(f"No model_seed*.txt files found in {version_dir}")

        self.models = []
        for model_file in model_files:
            booster = lgb.Booster(model_file=str(model_file))
            self.models.append(booster)
            logger.debug("Loaded model: {}", model_file.name)

        logger.info("Loaded {} seed models from version={}", len(self.models), version)

        # Load feature list
        feature_list_path = version_dir / "feature_list.json"
        if feature_list_path.exists():
            self.feature_list = json.loads(
                feature_list_path.read_text(encoding="utf-8")
            )
        else:
            logger.warning("feature_list.json not found in {}", version_dir)
            self.feature_list = []

        # Load categorical features
        cat_path = version_dir / "categorical_features.json"
        if cat_path.exists():
            self.categorical_features = json.loads(cat_path.read_text(encoding="utf-8"))
        else:
            logger.warning("categorical_features.json not found in {}", version_dir)
            self.categorical_features = []

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def predict_from_features(self, features: pd.DataFrame) -> list[float]:
        """Average predictions across all seed models and apply normalize_prob.

        Args:
            features: DataFrame with columns matching self.feature_list

        Returns:
            List of home_win_probability values (normalized, 2 decimal places)
        """
        if not self.models:
            raise RuntimeError("No models loaded. Call load_model() first.")

        available_cols = [c for c in self.feature_list if c in features.columns]
        available_categoricals = [
            col for col in self.categorical_features if col in available_cols
        ]
        X = prepare_model_matrix(features, available_cols, available_categoricals)

        X_values = X.values

        seed_preds: list[np.ndarray] = []
        for booster in self.models:
            preds = booster.predict(X_values)
            seed_preds.append(preds)

        avg_preds = np.mean(seed_preds, axis=0)

        # Convert raw probability [0,1] to percentage [0,100] and normalize
        results = [normalize_prob(float(p) * 100.0) for p in avg_preds]
        return results

    def predict_games(self, game_date: str) -> list[dict]:
        """Predict home win probabilities for all games on a given date.

        Args:
            game_date: Date string in "YYYY-MM-DD" format

        Returns:
            List of {"s_no": int, "home_win_probability": float, "model_version": str}
        """
        year = int(game_date[:4])
        feature_csv = Path(feature_csv_path(year))

        if not feature_csv.exists():
            logger.warning("Feature CSV not found: {}", feature_csv)
            return []

        df = pd.read_csv(feature_csv, encoding="utf-8-sig")
        day_df = df[df["game_date"] == game_date].copy()

        if day_df.empty:
            logger.info("No games found for date={}", game_date)
            return []

        logger.info(
            "Predicting {} games for date={} using version={}",
            len(day_df),
            game_date,
            self.model_version,
        )

        probs = self.predict_from_features(day_df)

        results: list[dict] = []
        for i, (_, row) in enumerate(day_df.iterrows()):
            results.append(
                {
                    "s_no": int(row["s_no"]),
                    "home_win_probability": probs[i],
                    "model_version": self.model_version,
                }
            )

        logger.info("Predictions generated for {} games", len(results))
        return results

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def save_prediction_log(self, predictions: list[dict], game_date: str) -> None:
        """Append prediction results to logs/prediction_log.csv.

        Schema: s_no, game_date, home_win_probability, model_version, predicted_at
        """
        if not predictions:
            logger.debug("No predictions to log for date={}", game_date)
            return

        log_path = Path(PREDICTION_LOG_CSV)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        predicted_at = datetime.now(tz=UTC).isoformat()

        rows = [
            {
                "s_no": p["s_no"],
                "game_date": game_date,
                "home_win_probability": p["home_win_probability"],
                "model_version": p["model_version"],
                "predicted_at": predicted_at,
            }
            for p in predictions
        ]

        new_df = pd.DataFrame(rows)
        header = not log_path.exists()
        new_df.to_csv(
            log_path,
            mode="a",
            header=header,
            index=False,
            encoding="utf-8-sig",
        )
        logger.info("Appended {} rows to prediction log: {}", len(rows), log_path)

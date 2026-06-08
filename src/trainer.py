"""
ModelTrainer: LightGBM training pipeline with time-based cross-validation.

Trains ensemble of 5 seed models for KBO baseball win prediction.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
import yaml
from loguru import logger
from sklearn.metrics import brier_score_loss, log_loss

from .constants import MODEL_REGISTRY_DIR, feature_csv_path
from .feature_matrix import prepare_model_matrix

_NON_FEATURE_COLS = {
    "s_no",
    "game_date",
    "year",
    "game_time",
    "home_starter_p_no",
    "away_starter_p_no",
    "target_home_win",
}

CATEGORICAL_FEATURES = [
    "home_team_code",
    "away_team_code",
    "stadium_code",
    "day_of_week",
    "month",
    "is_doubleheader",
]

MIN_CV_VAL_SAMPLES = 20
_NAN = float("nan")

LGBM_BASE_PARAMS: dict = {
    "objective": "binary",
    "metric": "binary_logloss",
    "num_leaves": 31,
    "learning_rate": 0.05,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "min_child_samples": 20,
    "verbose": -1,
}


class ModelTrainer:
    MODEL_VERSION_PREFIX = "lgbm_v"
    SEEDS = [42, 123, 456, 789, 1337]

    def __init__(self, model_version: str | None = None) -> None:
        self.registry_dir = Path(MODEL_REGISTRY_DIR)
        self.registry_dir.mkdir(parents=True, exist_ok=True)

        if model_version is not None:
            self.model_version = model_version
        else:
            self.model_version = self._next_version()

        logger.info("ModelTrainer initialized with version={}", self.model_version)

    def _next_version(self) -> str:
        """Auto-increment version: lgbm_v001, lgbm_v002, ..."""
        existing = sorted(
            [
                d.name
                for d in self.registry_dir.iterdir()
                if d.is_dir() and d.name.startswith(self.MODEL_VERSION_PREFIX)
            ]
        )
        if not existing:
            return f"{self.MODEL_VERSION_PREFIX}001"

        last = existing[-1]
        try:
            num = int(last.replace(self.MODEL_VERSION_PREFIX, ""))
        except ValueError:
            num = 0
        return f"{self.MODEL_VERSION_PREFIX}{num + 1:03d}"

    def load_features(self, years: list[int]) -> pd.DataFrame:
        """Load and concatenate feature CSVs for given years.

        Drops rows where target_home_win is NaN and sorts by game_date ascending.
        """
        dfs: list[pd.DataFrame] = []
        for year in years:
            path = Path(feature_csv_path(year))
            if not path.exists():
                logger.warning("Feature CSV not found for year={}: {}", year, path)
                continue
            df = pd.read_csv(path, encoding="utf-8-sig")
            logger.info("Loaded feature CSV year={}: {} rows", year, len(df))
            dfs.append(df)

        if not dfs:
            raise FileNotFoundError(f"No feature CSVs found for years: {years}")

        combined = pd.concat(dfs, ignore_index=True)
        before = len(combined)
        combined = combined.dropna(subset=["target_home_win"])
        after = len(combined)
        if before != after:
            logger.info("Dropped {} rows with NaN target_home_win", before - after)

        combined = combined.sort_values("game_date", ascending=True).reset_index(
            drop=True
        )
        logger.info("Total feature rows after merge & clean: {}", len(combined))
        return combined

    def _get_feature_columns(self, df: pd.DataFrame) -> list[str]:
        """Return numeric feature columns (excluding meta and target columns)."""
        return [c for c in df.columns if c not in _NON_FEATURE_COLS]

    def _get_categorical_features(self, feature_cols: list[str]) -> list[str]:
        """Return categorical feature columns present in feature_cols."""
        return [c for c in CATEGORICAL_FEATURES if c in feature_cols]

    def time_based_cv(self, df: pd.DataFrame) -> list[tuple[np.ndarray, np.ndarray]]:
        """Create chronological monthly expanding-window folds."""
        df = df.copy()
        df["_game_date"] = pd.to_datetime(df["game_date"])
        df["_year_month"] = df["_game_date"].dt.to_period("M")

        folds: list[tuple[np.ndarray, np.ndarray]] = []
        for val_period in sorted(df["_year_month"].dropna().unique()):
            val_start = val_period.to_timestamp()
            train_mask = df["_game_date"] < val_start
            val_mask = df["_year_month"] == val_period

            train_idx = df.index[train_mask].to_numpy()
            val_idx = df.index[val_mask].to_numpy()

            if len(train_idx) < 50:
                logger.debug(
                    "Skipping fold val_period={}: only {} train samples",
                    val_period,
                    len(train_idx),
                )
                continue
            if len(val_idx) == 0:
                logger.debug(
                    "Skipping fold val_period={}: no validation samples", val_period
                )
                continue
            if len(val_idx) < MIN_CV_VAL_SAMPLES:
                logger.debug(
                    "Skipping fold val_period={}: only {} validation samples",
                    val_period,
                    len(val_idx),
                )
                continue
            if df.loc[val_idx, "target_home_win"].nunique() < 2:
                logger.debug(
                    "Skipping fold val_period={}: validation has one target class",
                    val_period,
                )
                continue

            folds.append((train_idx, val_idx))
            logger.debug(
                "CV fold: val_period={} | train={} val={}",
                val_period,
                len(train_idx),
                len(val_idx),
            )

        logger.info("Created {} CV folds", len(folds))
        return folds

    def train_single_seed(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
        seed: int,
        categorical_features: list[str],
    ) -> lgb.Booster:
        """Train a single LightGBM model with a given seed."""
        params = {**LGBM_BASE_PARAMS, "seed": seed}

        train_set = lgb.Dataset(
            X_train,
            label=y_train,
            categorical_feature=categorical_features,
            free_raw_data=False,
        )
        val_set = lgb.Dataset(
            X_val,
            label=y_val,
            categorical_feature=categorical_features,
            reference=train_set,
            free_raw_data=False,
        )

        callbacks = [
            lgb.early_stopping(stopping_rounds=50, verbose=False),
            lgb.log_evaluation(period=-1),
        ]

        booster = lgb.train(
            params=params,
            train_set=train_set,
            num_boost_round=500,
            valid_sets=[val_set],
            callbacks=callbacks,
        )

        logger.debug("Trained seed={} best_iteration={}", seed, booster.best_iteration)
        return booster

    def train_with_cv(self, df: pd.DataFrame) -> dict:
        """Run time-based CV and return fold metrics.

        For each fold: train 5 seeds, average predictions.
        Returns {"fold_metrics": [...], "mean_logloss": float, "mean_brier": float}
        """
        feature_cols = self._get_feature_columns(df)
        categorical_features = self._get_categorical_features(feature_cols)
        folds = self.time_based_cv(df)

        fold_metrics: list[dict] = []

        for fold_idx, (train_idx, val_idx) in enumerate(folds):
            train_df = df.loc[train_idx]
            val_df = df.loc[val_idx]

            X_train = prepare_model_matrix(train_df, feature_cols, categorical_features)
            y_train = train_df["target_home_win"].astype(float)
            X_val = prepare_model_matrix(val_df, feature_cols, categorical_features)
            y_val = val_df["target_home_win"].astype(float)

            seed_preds: list[np.ndarray] = []
            seed_best_iterations: list[int] = []
            for seed in self.SEEDS:
                booster = self.train_single_seed(
                    X_train, y_train, X_val, y_val, seed, categorical_features
                )
                preds = booster.predict(X_val.values)
                seed_preds.append(preds)
                seed_best_iterations.append(int(booster.best_iteration))

            avg_preds = np.mean(seed_preds, axis=0)
            fold_logloss = float(log_loss(y_val, avg_preds, labels=[0.0, 1.0]))
            fold_brier = float(brier_score_loss(y_val, avg_preds))

            fold_metrics.append(
                {
                    "fold": fold_idx,
                    "train_size": len(train_idx),
                    "val_size": len(val_idx),
                    "log_loss": fold_logloss,
                    "brier_score": fold_brier,
                    "best_iterations": seed_best_iterations,
                    "best_iteration_mean": float(np.mean(seed_best_iterations)),
                    "best_iteration_median": float(np.median(seed_best_iterations)),
                }
            )
            logger.info(
                "Fold {}: log_loss={:.4f} brier={:.4f} (train={} val={})",
                fold_idx,
                fold_logloss,
                fold_brier,
                len(train_idx),
                len(val_idx),
            )

        mean_logloss = float(np.mean([m["log_loss"] for m in fold_metrics]))
        mean_brier = float(np.mean([m["brier_score"] for m in fold_metrics]))
        weighted_mean_logloss = self._weighted_metric(fold_metrics, "log_loss")
        weighted_mean_brier = self._weighted_metric(fold_metrics, "brier_score")
        final_num_boost_round = self._recommended_num_boost_round(fold_metrics)

        logger.info(
            "CV complete: mean_logloss={:.4f} mean_brier={:.4f}",
            mean_logloss,
            mean_brier,
        )

        return {
            "fold_metrics": fold_metrics,
            "mean_logloss": mean_logloss,
            "mean_brier": mean_brier,
            "weighted_mean_logloss": weighted_mean_logloss,
            "weighted_mean_brier": weighted_mean_brier,
            "recommended_num_boost_round": final_num_boost_round,
        }

    @staticmethod
    def _weighted_metric(fold_metrics: list[dict[str, Any]], metric: str) -> float:
        """Return validation-size weighted mean for a fold metric."""
        total_val_size = sum(int(row["val_size"]) for row in fold_metrics)
        if total_val_size == 0:
            return _NAN
        weighted_sum = sum(
            float(row[metric]) * int(row["val_size"]) for row in fold_metrics
        )
        return weighted_sum / total_val_size

    @staticmethod
    def _recommended_num_boost_round(fold_metrics: list[dict[str, Any]]) -> int:
        """Return a robust final boosting round count from CV early stopping."""
        best_iterations = [
            int(value)
            for row in fold_metrics
            for value in row.get("best_iterations", [])
            if int(value) > 0
        ]
        if not best_iterations:
            return 500
        return max(1, int(np.median(best_iterations)))

    def _predict_with_seed_ensemble(
        self,
        train_df: pd.DataFrame,
        val_df: pd.DataFrame,
        feature_cols: list[str],
        categorical_features: list[str],
    ) -> np.ndarray:
        """Train the seed ensemble and return averaged validation predictions."""
        X_train = prepare_model_matrix(train_df, feature_cols, categorical_features)
        y_train = train_df["target_home_win"].astype(float)
        X_val = prepare_model_matrix(val_df, feature_cols, categorical_features)
        y_val = val_df["target_home_win"].astype(float)

        seed_preds: list[np.ndarray] = []
        for seed in self.SEEDS:
            booster = self.train_single_seed(
                X_train, y_train, X_val, y_val, seed, categorical_features
            )
            seed_preds.append(booster.predict(X_val.values))

        return np.mean(seed_preds, axis=0)

    def evaluate_late_2025_holdout(self, df: pd.DataFrame) -> dict:
        """Evaluate a 2025 September-and-later holdout when available."""
        feature_cols = self._get_feature_columns(df)
        categorical_features = self._get_categorical_features(feature_cols)

        eval_df = df.copy()
        eval_df["_game_date"] = pd.to_datetime(eval_df["game_date"])
        holdout_start = pd.Timestamp("2025-09-01")

        train_df = eval_df[eval_df["_game_date"] < holdout_start].copy()
        val_df = eval_df[eval_df["_game_date"] >= holdout_start].copy()
        val_df = val_df[val_df["year"] == 2025].copy()

        if len(train_df) < 50 or val_df.empty:
            logger.warning(
                "Skipping late-2025 holdout: train={} val={}",
                len(train_df),
                len(val_df),
            )
            return {
                "enabled": False,
                "reason": "Need at least 50 train rows and non-empty 2025 late-season rows",
                "train_size": len(train_df),
                "val_size": len(val_df),
            }

        preds = self._predict_with_seed_ensemble(
            train_df=train_df,
            val_df=val_df,
            feature_cols=feature_cols,
            categorical_features=categorical_features,
        )
        y_val = val_df["target_home_win"].astype(float)
        metrics = {
            "enabled": True,
            "holdout_start": holdout_start.date().isoformat(),
            "train_size": len(train_df),
            "val_size": len(val_df),
            "log_loss": float(log_loss(y_val, preds, labels=[0.0, 1.0])),
            "brier_score": float(brier_score_loss(y_val, preds)),
        }
        logger.info(
            "Late-2025 holdout: log_loss={:.4f} brier={:.4f} train={} val={}",
            metrics["log_loss"],
            metrics["brier_score"],
            metrics["train_size"],
            metrics["val_size"],
        )
        return metrics

    def train_final_model(
        self, df: pd.DataFrame, num_boost_round: int = 500
    ) -> list[lgb.Booster]:
        """Train on ALL data (no validation split). Returns 5 models (one per seed)."""
        feature_cols = self._get_feature_columns(df)
        categorical_features = self._get_categorical_features(feature_cols)

        X = prepare_model_matrix(df, feature_cols, categorical_features)
        y = df["target_home_win"].astype(float)

        models: list[lgb.Booster] = []
        for seed in self.SEEDS:
            params = {**LGBM_BASE_PARAMS, "seed": seed}
            train_set = lgb.Dataset(
                X,
                label=y,
                categorical_feature=categorical_features,
                free_raw_data=False,
            )
            booster = lgb.train(
                params=params,
                train_set=train_set,
                num_boost_round=num_boost_round,
                callbacks=[lgb.log_evaluation(period=-1)],
            )
            models.append(booster)
            logger.info(
                "Final model seed={} trained ({} iterations)", seed, booster.num_trees()
            )

        logger.info("Final training complete: {} seed models", len(models))
        return models

    def save_model(
        self,
        models: list[lgb.Booster],
        feature_list: list[str],
        categorical_features: list[str],
        cv_metrics: dict,
        train_years: list[int],
        final_num_boost_round: int,
    ) -> Path:
        """Save model artifacts to artifacts/model_registry/{version}/.

        Files:
            model_seed{i}.txt         - LightGBM text format
            feature_list.json         - ordered feature names
            categorical_features.json - categorical feature names
            metrics.json              - CV metrics
            train_config.yaml         - training configuration
        """
        version_dir = self.registry_dir / self.model_version
        version_dir.mkdir(parents=True, exist_ok=True)

        for i, booster in enumerate(models):
            model_path = version_dir / f"model_seed{i}.txt"
            booster.save_model(str(model_path))
            logger.info("Saved model_seed{}.txt", i)

        (version_dir / "feature_list.json").write_text(
            json.dumps(feature_list, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        (version_dir / "categorical_features.json").write_text(
            json.dumps(categorical_features, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        (version_dir / "metrics.json").write_text(
            json.dumps(cv_metrics, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        train_config = {
            "model_version": self.model_version,
            "train_years": train_years,
            "seeds": self.SEEDS,
            "lgbm_params": LGBM_BASE_PARAMS,
            "final_num_boost_round": final_num_boost_round,
        }
        (version_dir / "train_config.yaml").write_text(
            yaml.dump(train_config, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

        logger.info("Artifacts saved to {}", version_dir)
        return version_dir

    def run(self, train_years: list[int], val_years: list[int] | None = None) -> Path:
        """Main training pipeline.

        1. Load features for train_years
        2. Run time-based CV
        3. Optionally evaluate on val_years
        4. Train final models on train_years
        5. Save artifacts
        6. Return model directory path
        """
        logger.info(
            "Starting training pipeline: train_years={} val_years={}",
            train_years,
            val_years,
        )

        df = self.load_features(train_years)
        feature_cols = self._get_feature_columns(df)
        categorical_features = self._get_categorical_features(feature_cols)

        logger.info(
            "Features: {} total | {} categorical",
            len(feature_cols),
            len(categorical_features),
        )

        cv_metrics = self.train_with_cv(df)

        cv_metrics["late_2025_holdout"] = self.evaluate_late_2025_holdout(df)

        if val_years:
            val_df = self.load_features(val_years)
            logger.info("Val years {} loaded: {} rows", val_years, len(val_df))
            cv_metrics["val_years"] = val_years

        final_num_boost_round = int(cv_metrics.get("recommended_num_boost_round", 500))
        final_models = self.train_final_model(df, num_boost_round=final_num_boost_round)

        model_dir = self.save_model(
            models=final_models,
            feature_list=feature_cols,
            categorical_features=categorical_features,
            cv_metrics=cv_metrics,
            train_years=train_years,
            final_num_boost_round=final_num_boost_round,
        )

        logger.info(
            "Training pipeline complete: version={} path={}",
            self.model_version,
            model_dir,
        )
        return model_dir

"""Offline model evaluation utilities for saved LightGBM artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss

from .trainer import ModelTrainer


def parse_years(value: str) -> list[int]:
    """Parse comma-separated years."""
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def safe_probability(values: np.ndarray) -> np.ndarray:
    """Clip probabilities to a numerically safe interval."""
    return np.clip(values.astype(float), 1e-6, 1 - 1e-6)


def team_win_rate_ratio(df: pd.DataFrame) -> np.ndarray:
    """Estimate home win probability from pre-game home/away win rates."""
    home = df["home_win_rate"].astype(float).fillna(0.5).to_numpy()
    away = df["away_win_rate"].astype(float).fillna(0.5).to_numpy()
    denominator = home + away
    ratio = np.divide(
        home, denominator, out=np.full_like(home, 0.5), where=denominator > 0
    )
    return safe_probability(ratio)


def baseline_predictions(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
) -> dict[str, np.ndarray]:
    """Return baseline predictions for a validation frame."""
    train_prior = float(train_df["target_home_win"].astype(float).mean())
    return {
        "constant_0_5": np.full(len(val_df), 0.5, dtype=float),
        "train_home_win_prior": np.full(len(val_df), train_prior, dtype=float),
        "team_win_rate_ratio": team_win_rate_ratio(val_df),
    }


def score_predictions(y_true: pd.Series, y_pred: np.ndarray) -> dict[str, float]:
    """Compute binary probabilistic scores."""
    safe_pred = safe_probability(y_pred)
    y = y_true.astype(float)
    return {
        "log_loss": float(log_loss(y, safe_pred, labels=[0.0, 1.0])),
        "brier_score": float(brier_score_loss(y, safe_pred)),
    }


def evaluate_cv_baselines(df: pd.DataFrame) -> pd.DataFrame:
    """Evaluate baselines on the trainer's chronological CV folds."""
    trainer = ModelTrainer(model_version="evaluation_only")
    folds = trainer.time_based_cv(df)
    rows: list[dict[str, Any]] = []

    for fold_index, (train_idx, val_idx) in enumerate(folds):
        train_df = df.loc[train_idx]
        val_df = df.loc[val_idx]
        y_val = val_df["target_home_win"]

        for baseline_name, preds in baseline_predictions(train_df, val_df).items():
            rows.append(
                {
                    "evaluation": "monthly_expanding_cv",
                    "fold": fold_index,
                    "baseline": baseline_name,
                    "train_size": len(train_df),
                    "val_size": len(val_df),
                    **score_predictions(y_val, preds),
                }
            )

    return pd.DataFrame(rows)


def evaluate_late_holdout_baselines(df: pd.DataFrame) -> pd.DataFrame:
    """Evaluate baselines on the same late-2025 holdout used by training."""
    eval_df = df.copy()
    eval_df["_game_date"] = pd.to_datetime(eval_df["game_date"])
    holdout_start = pd.Timestamp("2025-09-01")
    train_df = eval_df[eval_df["_game_date"] < holdout_start].copy()
    val_df = eval_df[
        (eval_df["_game_date"] >= holdout_start) & (eval_df["year"] == 2025)
    ].copy()

    rows: list[dict[str, Any]] = []
    for baseline_name, preds in baseline_predictions(train_df, val_df).items():
        rows.append(
            {
                "evaluation": "late_2025_holdout",
                "fold": "holdout",
                "baseline": baseline_name,
                "train_size": len(train_df),
                "val_size": len(val_df),
                **score_predictions(val_df["target_home_win"], preds),
            }
        )

    return pd.DataFrame(rows)


def summarize_baselines(baseline_rows: pd.DataFrame) -> pd.DataFrame:
    """Aggregate baseline scores by evaluation and baseline."""
    return (
        baseline_rows.groupby(["evaluation", "baseline"], as_index=False)
        .agg(
            mean_log_loss=("log_loss", "mean"),
            mean_brier_score=("brier_score", "mean"),
            total_val_size=("val_size", "sum"),
        )
        .sort_values(["evaluation", "mean_log_loss"])
    )


def load_metrics(model_dir: Path) -> dict[str, Any]:
    """Load saved model metrics."""
    return json.loads((model_dir / "metrics.json").read_text(encoding="utf-8"))


def model_metric_rows(metrics: dict[str, Any]) -> pd.DataFrame:
    """Convert saved model metrics into rows comparable to baseline summaries."""
    rows = [
        {
            "evaluation": "monthly_expanding_cv",
            "model": "saved_cv_ensemble",
            "log_loss": metrics["mean_logloss"],
            "brier_score": metrics["mean_brier"],
        }
    ]
    holdout = metrics.get("late_2025_holdout", {})
    if holdout.get("enabled"):
        rows.append(
            {
                "evaluation": "late_2025_holdout",
                "model": "saved_holdout_ensemble",
                "log_loss": holdout["log_loss"],
                "brier_score": holdout["brier_score"],
            }
        )
    return pd.DataFrame(rows)


def load_feature_names(model_dir: Path) -> list[str]:
    """Load the feature order used by the model."""
    return json.loads((model_dir / "feature_list.json").read_text(encoding="utf-8"))


def feature_importance(model_dir: Path) -> pd.DataFrame:
    """Average feature importance across all saved seed models."""
    feature_names = load_feature_names(model_dir)
    rows: list[pd.DataFrame] = []

    for model_path in sorted(model_dir.glob("model_seed*.txt")):
        booster = lgb.Booster(model_file=str(model_path))
        rows.append(
            pd.DataFrame(
                {
                    "feature": feature_names,
                    "gain": booster.feature_importance(importance_type="gain"),
                    "split": booster.feature_importance(importance_type="split"),
                    "model_file": model_path.name,
                }
            )
        )

    combined = pd.concat(rows, ignore_index=True)
    summary = (
        combined.groupby("feature", as_index=False)
        .agg(mean_gain=("gain", "mean"), mean_split=("split", "mean"))
        .sort_values("mean_gain", ascending=False)
        .reset_index(drop=True)
    )
    total_gain = float(summary["mean_gain"].sum())
    summary["gain_share"] = summary["mean_gain"] / total_gain if total_gain > 0 else 0.0
    return summary


def run_evaluation(model_version: str, years: list[int]) -> Path:
    """Run baseline comparison and feature importance export."""
    model_dir = Path("artifacts/model_registry") / model_version
    if not model_dir.exists():
        raise FileNotFoundError(f"Model directory not found: {model_dir}")

    trainer = ModelTrainer(model_version="evaluation_only")
    df = trainer.load_features(years)

    baseline_rows = pd.concat(
        [evaluate_cv_baselines(df), evaluate_late_holdout_baselines(df)],
        ignore_index=True,
    )
    baseline_summary = summarize_baselines(baseline_rows)
    model_metrics = model_metric_rows(load_metrics(model_dir))
    importance = feature_importance(model_dir)

    output_dir = model_dir / "evaluation"
    output_dir.mkdir(parents=True, exist_ok=True)
    baseline_rows.to_csv(output_dir / "baseline_fold_scores.csv", index=False)
    baseline_summary.to_csv(output_dir / "baseline_summary.csv", index=False)
    model_metrics.to_csv(output_dir / "model_metrics.csv", index=False)
    importance.to_csv(output_dir / "feature_importance.csv", index=False)

    summary_payload = {
        "model_version": model_version,
        "years": years,
        "model_metrics": model_metrics.to_dict(orient="records"),
        "baseline_summary": baseline_summary.to_dict(orient="records"),
        "top_features_by_gain": importance.head(20).to_dict(orient="records"),
    }
    (output_dir / "evaluation_summary.json").write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_dir

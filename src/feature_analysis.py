"""Feature analysis utilities for saved LightGBM prediction models."""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
from loguru import logger
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.inspection import permutation_importance

from .constants import MODEL_REGISTRY_DIR, TEAM_CODES
from .feature_matrix import prepare_model_matrix
from .trainer import ModelTrainer

INTERPRETATION_NOTES = [
    "Feature importance and SHAP importance are not causal evidence.",
    "Read these charts as signals the model used strongly for prediction, not as proof that a feature caused the outcome.",
    "LightGBM gain/split importance and SHAP values describe different views of model behavior.",
]

FEATURE_FAMILY_META = {
    "starter": {"label": "Starter quality", "color": "#2e607d"},
    "lineup": {"label": "Lineup strength", "color": "#0d7a5f"},
    "bullpen": {"label": "Bullpen load", "color": "#6d4c8d"},
    "recent_form": {"label": "Recent form", "color": "#b57a16"},
    "team_context": {"label": "Team context", "color": "#a33b32"},
    "schedule": {"label": "Schedule", "color": "#65716b"},
    "other": {"label": "Other signals", "color": "#151716"},
}


class _LGBMEnsembleEstimator(ClassifierMixin, BaseEstimator):
    def __init__(self, models: list[Any], task_type: str) -> None:
        self.models = models
        self.task_type = task_type
        self.classes_ = np.array([0, 1])

    def fit(self, X: pd.DataFrame, y: pd.Series) -> _LGBMEnsembleEstimator:
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        probabilities = _predict_probability(self.models, X)
        return np.column_stack([1 - probabilities, probabilities])

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.task_type == "classification":
            return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)
        return _predict_probability(self.models, X)


def visualize_lgbm_feature_effects(
    model: Any,
    X_valid: pd.DataFrame,
    y_valid: pd.Series | np.ndarray | None = None,
    game_metadata: pd.DataFrame | None = None,
    output_dir: str | Path = "feature_analysis",
    top_n: int = 30,
    task_type: str = "classification",
    scoring: str | None = None,
    dependence_features: list[str] | None = None,
    random_state: int = 42,
    model_version: str | None = None,
    manifest_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate LightGBM importance, SHAP, and permutation analysis artifacts.

    Binary classification SHAP outputs are normalized to the positive class.
    Multi-class SHAP outputs raise a clear error because this project serves a
    binary home-win probability model.
    """
    if not isinstance(X_valid, pd.DataFrame):
        raise TypeError("X_valid must be a pandas DataFrame with feature names.")
    if X_valid.empty:
        raise ValueError("X_valid must contain at least one row.")
    if top_n < 1:
        raise ValueError("top_n must be >= 1.")
    if task_type not in {"classification", "regression"}:
        raise ValueError("task_type must be 'classification' or 'regression'.")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    models = _normalize_models(model)
    feature_names = list(X_valid.columns)

    lgbm_importance = _lightgbm_importance(models, feature_names)
    lgbm_csv = output_path / "lgbm_feature_importance.csv"
    lgbm_importance.to_csv(lgbm_csv, index=False)
    gain_plot = output_path / f"lgbm_gain_top{top_n}.png"
    split_plot = output_path / f"lgbm_split_top{top_n}.png"
    _plot_bar(
        lgbm_importance,
        value_column="mean_gain",
        title=f"LightGBM gain importance top {top_n}",
        output_path=gain_plot,
        top_n=top_n,
    )
    _plot_bar(
        lgbm_importance,
        value_column="mean_split",
        title=f"LightGBM split importance top {top_n}",
        output_path=split_plot,
        top_n=top_n,
    )

    shap_values = _mean_positive_class_shap(models, X_valid)
    shap_importance = pd.DataFrame(
        {
            "feature": feature_names,
            "mean_abs_shap": np.abs(shap_values).mean(axis=0),
        }
    ).sort_values("mean_abs_shap", ascending=False, ignore_index=True)
    shap_csv = output_path / "shap_importance.csv"
    shap_importance.to_csv(shap_csv, index=False)
    shap_summary_plot = output_path / "shap_summary.png"
    shap_bar_plot = output_path / f"shap_bar_top{top_n}.png"
    _plot_shap_summary(shap_values, X_valid, shap_summary_plot)
    _plot_shap_bar(shap_importance, shap_bar_plot, top_n)

    dependence_images: dict[str, str] = {}
    for feature in dependence_features or []:
        if feature not in X_valid.columns:
            logger.warning("Dependence feature not found, skipping: {}", feature)
            continue
        output_file = output_path / f"dependence_{_safe_filename(feature)}.png"
        _plot_shap_dependence(shap_values, X_valid, feature, output_file)
        dependence_images[feature] = output_file.name

    permutation_csv: Path | None = None
    permutation_plot: Path | None = None
    permutation_df = pd.DataFrame()
    if y_valid is None:
        logger.warning(
            "Skipping permutation importance because y_valid was not provided."
        )
    else:
        permutation_df = _permutation_importance(
            models=models,
            X_valid=X_valid,
            y_valid=y_valid,
            task_type=task_type,
            scoring=scoring,
            random_state=random_state,
        )
        permutation_csv = output_path / "permutation_importance.csv"
        permutation_df.to_csv(permutation_csv, index=False)
        permutation_plot = output_path / f"permutation_importance_top{top_n}.png"
        _plot_bar(
            permutation_df.rename(columns={"importance_mean": "value"}),
            value_column="value",
            title=f"Permutation importance top {top_n}",
            output_path=permutation_plot,
            top_n=top_n,
        )

    top_features = {
        "gain": _top_feature_records(lgbm_importance, "mean_gain", top_n),
        "split": _top_feature_records(lgbm_importance, "mean_split", top_n),
        "shap": _top_feature_records(shap_importance, "mean_abs_shap", top_n),
        "permutation": _top_feature_records(permutation_df, "importance_mean", top_n)
        if not permutation_df.empty
        else [],
    }
    feature_network = _build_feature_signal_network(top_features, top_n)
    network_path = output_path / "feature_signal_network.json"
    network_path.write_text(
        json.dumps(feature_network, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    feature_agreement = _build_importance_agreement(top_features, top_n)
    agreement_path = output_path / "feature_agreement.json"
    agreement_path.write_text(
        json.dumps(feature_agreement, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    family_summary = _build_feature_family_summary(top_features, top_n)
    family_summary_path = output_path / "feature_family_summary.json"
    family_summary_path.write_text(
        json.dumps(family_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    game_explanations = _build_game_explanations(
        shap_values=shap_values,
        X_valid=X_valid,
        models=models,
        y_valid=y_valid,
        game_metadata=game_metadata,
    )
    game_explanations_path = output_path / "feature_game_explanations.json"
    game_explanations_path.write_text(
        json.dumps(game_explanations, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "model_version": model_version,
        "task_type": task_type,
        "sample_size": int(len(X_valid)),
        "top_n": int(top_n),
        "interpretation_notes": INTERPRETATION_NOTES,
        "sections": [
            {
                "id": "lgbm_gain",
                "title": "LightGBM gain importance",
                "description": "Total loss reduction attributed to each feature across trees.",
                "image_path": gain_plot.name,
                "csv_path": lgbm_csv.name,
            },
            {
                "id": "lgbm_split",
                "title": "LightGBM split importance",
                "description": "How often each feature is used for a tree split.",
                "image_path": split_plot.name,
                "csv_path": lgbm_csv.name,
            },
            {
                "id": "shap_summary",
                "title": "SHAP summary",
                "description": "Per-game contribution distribution for the positive home-win class.",
                "image_path": shap_summary_plot.name,
                "csv_path": shap_csv.name,
            },
            {
                "id": "shap_bar",
                "title": "SHAP mean absolute impact",
                "description": "Average absolute SHAP contribution by feature.",
                "image_path": shap_bar_plot.name,
                "csv_path": shap_csv.name,
            },
        ],
        "csv_paths": {
            "lgbm_feature_importance": lgbm_csv.name,
            "shap_importance": shap_csv.name,
            "permutation_importance": permutation_csv.name if permutation_csv else None,
        },
        "dependence_images": dependence_images,
        "top_features": top_features,
        "network_path": network_path.name,
        "agreement_path": agreement_path.name,
        "family_summary_path": family_summary_path.name,
        "game_explanations_path": game_explanations_path.name,
    }
    if permutation_plot is not None:
        manifest["sections"].append(
            {
                "id": "permutation",
                "title": "Permutation importance",
                "description": "Prediction score drop after shuffling one feature at a time.",
                "image_path": permutation_plot.name,
                "csv_path": permutation_csv.name if permutation_csv else None,
            }
        )
    if manifest_extra:
        manifest.update(manifest_extra)

    manifest_path = output_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def run_saved_model_feature_analysis(
    model_version: str,
    years: list[int],
    output_dir: str | Path = "outputs/feature_analysis",
    top_n: int = 30,
    scoring: str | None = None,
    dependence_features: list[str] | None = None,
    random_state: int = 42,
) -> Path:
    """Run feature analysis for a saved model registry version."""
    model_dir = Path(MODEL_REGISTRY_DIR) / model_version
    if not model_dir.exists():
        raise FileNotFoundError(f"Model directory not found: {model_dir}")

    models = [
        lgb.Booster(model_file=str(path))
        for path in sorted(model_dir.glob("model_seed*.txt"))
    ]
    if not models:
        raise FileNotFoundError(f"No model_seed*.txt files found in {model_dir}")

    feature_list = json.loads(
        (model_dir / "feature_list.json").read_text(encoding="utf-8")
    )
    categorical_features = json.loads(
        (model_dir / "categorical_features.json").read_text(encoding="utf-8")
    )

    trainer = ModelTrainer(model_version="feature_analysis_only")
    df = trainer.load_features(years)
    analysis_df, analysis_window = _select_analysis_frame(df)
    X_valid = prepare_model_matrix(analysis_df, feature_list, categorical_features)
    y_valid = analysis_df["target_home_win"].astype(int)

    version_output_dir = Path(output_dir) / model_version
    visualize_lgbm_feature_effects(
        model=models,
        X_valid=X_valid,
        y_valid=y_valid,
        game_metadata=analysis_df,
        output_dir=version_output_dir,
        top_n=top_n,
        task_type="classification",
        scoring=scoring,
        dependence_features=dependence_features,
        random_state=random_state,
        model_version=model_version,
        manifest_extra={
            "years": years,
            "analysis_window": analysis_window,
            "source_model_dir": str(model_dir),
        },
    )
    return version_output_dir


def publish_feature_analysis_to_web(
    output_dir: str | Path,
    public_dir: str | Path = "web/public/feature-analysis",
    public_path_prefix: str = "/feature-analysis",
) -> Path:
    """Copy generated analysis files to Next.js public assets and rewrite paths."""
    source_dir = Path(output_dir)
    manifest_path = source_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Feature analysis manifest not found: {manifest_path}")

    target_dir = Path(public_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for file_path in source_dir.iterdir():
        if file_path.is_file() and file_path.name != "manifest.json":
            shutil.copy2(file_path, target_dir / file_path.name)

    web_manifest = _manifest_with_public_paths(manifest, public_path_prefix)
    target_manifest = target_dir / "manifest.json"
    target_manifest.write_text(
        json.dumps(web_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target_manifest


def _normalize_models(model: Any) -> list[Any]:
    if isinstance(model, list | tuple):
        models = list(model)
    else:
        models = [model]
    if not models:
        raise ValueError("model must contain at least one LightGBM model.")
    return models


def _predict_probability(models: list[Any], X: pd.DataFrame) -> np.ndarray:
    predictions: list[np.ndarray] = []
    for model in models:
        if hasattr(model, "predict_proba"):
            proba = model.predict_proba(X)
            values = np.asarray(proba)
            if values.ndim == 2 and values.shape[1] == 2:
                predictions.append(values[:, 1].astype(float))
            else:
                predictions.append(values.astype(float).reshape(-1))
            continue
        predictions.append(np.asarray(model.predict(X), dtype=float).reshape(-1))
    return np.mean(predictions, axis=0)


def _lightgbm_importance(models: list[Any], feature_names: list[str]) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for index, model in enumerate(models):
        booster = _as_booster(model)
        gain = booster.feature_importance(importance_type="gain")
        split = booster.feature_importance(importance_type="split")
        if len(gain) != len(feature_names):
            raise ValueError(
                f"Feature count mismatch: model has {len(gain)} features, X_valid has {len(feature_names)}."
            )
        rows.append(
            pd.DataFrame(
                {
                    "feature": feature_names,
                    "gain": gain,
                    "split": split,
                    "model_index": index,
                }
            )
        )
    combined = pd.concat(rows, ignore_index=True)
    summary = (
        combined.groupby("feature", as_index=False)
        .agg(mean_gain=("gain", "mean"), mean_split=("split", "mean"))
        .sort_values("mean_gain", ascending=False, ignore_index=True)
    )
    total_gain = float(summary["mean_gain"].sum())
    total_split = float(summary["mean_split"].sum())
    summary["gain_share"] = summary["mean_gain"] / total_gain if total_gain > 0 else 0.0
    summary["split_share"] = (
        summary["mean_split"] / total_split if total_split > 0 else 0.0
    )
    return summary


def _as_booster(model: Any) -> lgb.Booster:
    if isinstance(model, lgb.Booster):
        return model
    booster = getattr(model, "booster_", None)
    if isinstance(booster, lgb.Booster):
        return booster
    raise TypeError("model must be a lightgbm.Booster or fitted LightGBM estimator.")


def _mean_positive_class_shap(models: list[Any], X_valid: pd.DataFrame) -> np.ndarray:
    shap = _import_shap()
    values: list[np.ndarray] = []
    for model in models:
        explainer = shap.TreeExplainer(_as_booster(model))
        shap_output = explainer.shap_values(X_valid)
        values.append(_positive_class_shap_array(shap_output, len(X_valid)))
    return np.mean(values, axis=0)


def _positive_class_shap_array(shap_output: Any, sample_size: int) -> np.ndarray:
    if isinstance(shap_output, list):
        if len(shap_output) == 2:
            return np.asarray(shap_output[1], dtype=float)
        if len(shap_output) == 1:
            return np.asarray(shap_output[0], dtype=float)
        raise ValueError("Multi-class SHAP output is not supported.")

    arr = np.asarray(shap_output, dtype=float)
    if arr.ndim == 2:
        return arr
    if arr.ndim == 3 and arr.shape[-1] == 2:
        return arr[:, :, 1]
    if arr.ndim == 3 and arr.shape[0] == 2 and arr.shape[1] == sample_size:
        return arr[1, :, :]
    raise ValueError(
        "Unsupported SHAP output shape; multi-class models are not supported."
    )


def _permutation_importance(
    models: list[Any],
    X_valid: pd.DataFrame,
    y_valid: pd.Series | np.ndarray,
    task_type: str,
    scoring: str | None,
    random_state: int,
) -> pd.DataFrame:
    estimator = _LGBMEnsembleEstimator(models=models, task_type=task_type)
    if task_type == "classification":
        effective_scoring = scoring or "accuracy"
    else:
        effective_scoring = scoring or "neg_mean_squared_error"

    result = permutation_importance(
        estimator,
        X_valid,
        y_valid,
        scoring=effective_scoring,
        n_repeats=10,
        random_state=random_state,
        n_jobs=1,
    )
    return pd.DataFrame(
        {
            "feature": list(X_valid.columns),
            "importance_mean": result.importances_mean,
            "importance_std": result.importances_std,
            "scoring": effective_scoring,
        }
    ).sort_values("importance_mean", ascending=False, ignore_index=True)


def _plot_bar(
    df: pd.DataFrame,
    value_column: str,
    title: str,
    output_path: Path,
    top_n: int,
) -> None:
    plt = _import_matplotlib()
    plot_df = df.nlargest(top_n, value_column).sort_values(value_column)
    fig_height = max(4.8, 0.32 * len(plot_df) + 1.5)
    fig, ax = plt.subplots(figsize=(9.5, fig_height))
    ax.barh(plot_df["feature"], plot_df[value_column], color="#0d7a5f")
    ax.set_title(title)
    ax.set_xlabel(value_column)
    ax.grid(axis="x", alpha=0.18)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def _plot_shap_summary(
    shap_values: np.ndarray, X_valid: pd.DataFrame, output_path: Path
) -> None:
    shap = _import_shap()
    plt = _import_matplotlib()
    shap.summary_plot(shap_values, X_valid, show=False)
    fig = plt.gcf()
    fig.tight_layout()
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def _plot_shap_bar(
    shap_importance: pd.DataFrame, output_path: Path, top_n: int
) -> None:
    _plot_bar(
        shap_importance.rename(columns={"mean_abs_shap": "value"}),
        value_column="value",
        title=f"SHAP mean absolute impact top {top_n}",
        output_path=output_path,
        top_n=top_n,
    )


def _plot_shap_dependence(
    shap_values: np.ndarray,
    X_valid: pd.DataFrame,
    feature: str,
    output_path: Path,
) -> None:
    shap = _import_shap()
    plt = _import_matplotlib()
    shap.dependence_plot(feature, shap_values, X_valid, show=False)
    fig = plt.gcf()
    fig.tight_layout()
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def _import_matplotlib() -> Any:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "matplotlib is required for feature analysis plots. Install project dependencies."
        ) from exc
    return plt


def _import_shap() -> Any:
    try:
        import shap
    except ImportError as exc:
        raise RuntimeError(
            "shap is required for SHAP feature analysis. Install project dependencies."
        ) from exc
    return shap


def _top_feature_records(
    df: pd.DataFrame, value_column: str, top_n: int
) -> list[dict[str, Any]]:
    if df.empty:
        return []
    rows = df.nlargest(top_n, value_column)[["feature", value_column]]
    return [
        {"feature": str(row["feature"]), "value": float(row[value_column])}
        for row in rows.to_dict(orient="records")
    ]


def _select_analysis_frame(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    analysis_df = df.copy()
    analysis_df["_game_date"] = pd.to_datetime(analysis_df["game_date"])
    holdout_start = pd.Timestamp("2025-09-01")
    holdout = analysis_df[
        (analysis_df["_game_date"] >= holdout_start) & (analysis_df["year"] == 2025)
    ].copy()
    if not holdout.empty and holdout["target_home_win"].nunique() >= 2:
        return holdout, {
            "type": "late_2025_analysis_sample",
            "start_date": holdout_start.date().isoformat(),
            "sample_size": int(len(holdout)),
        }
    return analysis_df, {
        "type": "all_loaded_feature_rows",
        "sample_size": int(len(analysis_df)),
    }


def _safe_filename(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return safe.strip("._") or "feature"


def _manifest_with_public_paths(
    manifest: dict[str, Any],
    public_path_prefix: str,
) -> dict[str, Any]:
    prefix = public_path_prefix.rstrip("/")
    web_manifest = json.loads(json.dumps(manifest, ensure_ascii=False))
    web_manifest.pop("source_model_dir", None)

    def public_path(value: str | None) -> str | None:
        if not value:
            return value
        if value.startswith("/"):
            return value
        return f"{prefix}/{value}"

    for section in web_manifest.get("sections", []):
        section["image_path"] = public_path(section.get("image_path"))
        section["csv_path"] = public_path(section.get("csv_path"))
    for key, value in list(web_manifest.get("csv_paths", {}).items()):
        web_manifest["csv_paths"][key] = public_path(value)
    for key, value in list(web_manifest.get("dependence_images", {}).items()):
        web_manifest["dependence_images"][key] = public_path(value)
    web_manifest["network_path"] = public_path(web_manifest.get("network_path"))
    web_manifest["agreement_path"] = public_path(web_manifest.get("agreement_path"))
    web_manifest["family_summary_path"] = public_path(
        web_manifest.get("family_summary_path")
    )
    web_manifest["game_explanations_path"] = public_path(
        web_manifest.get("game_explanations_path")
    )
    return web_manifest


def _build_feature_family_summary(
    top_features: dict[str, list[dict[str, Any]]],
    top_n: int,
) -> dict[str, Any]:
    methods = [
        {"id": "gain", "label": "Gain"},
        {"id": "split", "label": "Split"},
        {"id": "shap", "label": "SHAP"},
        {"id": "permutation", "label": "Permutation"},
    ]
    family_rows: dict[str, dict[str, Any]] = {}

    for method in methods:
        method_id = method["id"]
        for rank, row in enumerate(top_features.get(method_id, [])[:top_n], start=1):
            feature = str(row.get("feature", "")).strip()
            if not feature:
                continue
            family = _feature_family(feature)
            family_meta = FEATURE_FAMILY_META[family]
            score = (top_n - rank + 1) / top_n
            family_record = family_rows.setdefault(
                family,
                {
                    "id": family,
                    "label": family_meta["label"],
                    "color": family_meta["color"],
                    "score": 0.0,
                    "method_scores": {},
                    "features": {},
                },
            )
            family_record["score"] += score
            family_record["method_scores"][method_id] = (
                family_record["method_scores"].get(method_id, 0.0) + score
            )
            feature_record = family_record["features"].setdefault(
                feature,
                {
                    "feature": feature,
                    "label": _feature_node_label(feature),
                    "side": _feature_side(feature),
                    "score": 0.0,
                    "ranks": {},
                },
            )
            feature_record["score"] += score
            feature_record["ranks"][method_id] = rank

    total_score = sum(float(row["score"]) for row in family_rows.values())
    families: list[dict[str, Any]] = []
    for family_record in family_rows.values():
        feature_records = sorted(
            family_record["features"].values(),
            key=lambda row: (-float(row["score"]), str(row["feature"])),
        )
        method_scores = {
            method["id"]: round(
                float(family_record["method_scores"].get(method["id"], 0.0)),
                6,
            )
            for method in methods
        }
        primary_method = max(
            method_scores.items(),
            key=lambda item: (float(item[1]), item[0]),
        )[0]
        impact_share = (
            float(family_record["score"]) / total_score if total_score > 0 else 0.0
        )
        families.append(
            {
                "id": family_record["id"],
                "label": family_record["label"],
                "color": family_record["color"],
                "impact_score": round(float(family_record["score"]), 6),
                "impact_share": round(impact_share, 6),
                "method_coverage": sum(1 for score in method_scores.values() if score > 0),
                "primary_method": primary_method,
                "feature_count": len(feature_records),
                "top_features": [
                    {
                        "feature": str(feature["feature"]),
                        "label": str(feature["label"]),
                        "side": str(feature["side"]),
                        "score": round(float(feature["score"]), 6),
                        "ranks": feature["ranks"],
                    }
                    for feature in feature_records[:5]
                ],
                "method_scores": method_scores,
            }
        )

    families.sort(
        key=lambda row: (
            -float(row["impact_share"]),
            _feature_family_sort_index(str(row["id"])),
        )
    )
    return {
        "schema_version": 1,
        "title": "Feature family summary",
        "description": "Aggregated model interpretation signal by baseball feature family.",
        "methods": methods,
        "top_n": top_n,
        "families": families,
    }


def _build_importance_agreement(
    top_features: dict[str, list[dict[str, Any]]],
    top_n: int,
) -> dict[str, Any]:
    methods = [
        {"id": "gain", "label": "Gain"},
        {"id": "split", "label": "Split"},
        {"id": "shap", "label": "SHAP"},
        {"id": "permutation", "label": "Permutation"},
    ]
    feature_rows: dict[str, dict[str, Any]] = {}
    for method in methods:
        method_id = method["id"]
        for rank, row in enumerate(top_features.get(method_id, [])[:top_n], start=1):
            feature = str(row.get("feature", "")).strip()
            if not feature:
                continue
            record = feature_rows.setdefault(
                feature,
                {
                    "feature": feature,
                    "family": _feature_family(feature),
                    "family_label": FEATURE_FAMILY_META[_feature_family(feature)][
                        "label"
                    ],
                    "side": _feature_side(feature),
                    "ranks": {},
                    "values": {},
                },
            )
            record["ranks"][method_id] = rank
            record["values"][method_id] = float(row.get("value", 0.0))

    rows: list[dict[str, Any]] = []
    for record in feature_rows.values():
        ranks = record["ranks"]
        method_count = len(ranks)
        rank_score = sum((top_n - int(rank) + 1) / top_n for rank in ranks.values())
        consensus_score = rank_score / len(methods)
        average_rank = sum(int(rank) for rank in ranks.values()) / method_count
        missing_methods = [method["id"] for method in methods if method["id"] not in ranks]
        rows.append(
            {
                **record,
                "method_count": method_count,
                "average_rank": round(average_rank, 3),
                "consensus_score": round(consensus_score, 6),
                "missing_methods": missing_methods,
            }
        )

    rows.sort(
        key=lambda row: (
            -int(row["method_count"]),
            -float(row["consensus_score"]),
            float(row["average_rank"]),
            str(row["feature"]),
        )
    )

    return {
        "schema_version": 1,
        "title": "Importance agreement matrix",
        "description": "Feature ranks compared across LightGBM gain, split, SHAP, and permutation importance.",
        "methods": methods,
        "top_n": top_n,
        "rows": rows[: min(top_n, 30)],
    }


def _build_feature_signal_network(
    top_features: dict[str, list[dict[str, Any]]],
    top_n: int,
) -> dict[str, Any]:
    feature_scores: dict[str, dict[str, Any]] = {}
    metric_names = ["gain", "split", "shap", "permutation"]

    for metric in metric_names:
        for rank, row in enumerate(top_features.get(metric, [])[:top_n], start=1):
            feature = str(row.get("feature", "")).strip()
            if not feature:
                continue
            record = feature_scores.setdefault(
                feature,
                {"score": 0.0, "metrics": {}, "rank_total": 0},
            )
            value = float(row.get("value", 0.0))
            record["score"] += (top_n - rank + 1) / top_n
            record["rank_total"] += rank
            record["metrics"][metric] = {"rank": rank, "value": value}

    if not feature_scores:
        return {
            "schema_version": 1,
            "title": "Feature signal network",
            "description": "Feature-family graph derived from published model interpretation rankings.",
            "nodes": [],
            "edges": [],
            "families": FEATURE_FAMILY_META,
        }

    max_score = max(float(record["score"]) for record in feature_scores.values())
    feature_items = sorted(
        feature_scores.items(),
        key=lambda item: (
            -float(item[1]["score"]),
            int(item[1]["rank_total"]),
            item[0],
        ),
    )[: min(top_n, 24)]
    selected_features = {feature for feature, _ in feature_items}

    nodes: list[dict[str, Any]] = [
        {
            "id": "model_signal",
            "kind": "model",
            "label": "Home-win model",
            "score": 1.0,
        }
    ]
    edges: list[dict[str, Any]] = []
    family_scores: dict[str, float] = {}

    for feature, record in feature_items:
        family = _feature_family(feature)
        side = _feature_side(feature)
        score = float(record["score"]) / max_score if max_score > 0 else 0.0
        family_scores[family] = family_scores.get(family, 0.0) + score
        nodes.append(
            {
                "id": f"feature:{feature}",
                "kind": "feature",
                "label": _feature_node_label(feature),
                "feature": feature,
                "family": family,
                "family_label": FEATURE_FAMILY_META[family]["label"],
                "side": side,
                "score": round(score, 6),
                "metrics": record["metrics"],
            }
        )
        edges.append(
            {
                "source": f"family:{family}",
                "target": f"feature:{feature}",
                "kind": "family_membership",
                "weight": round(score, 6),
                "label": FEATURE_FAMILY_META[family]["label"],
            }
        )

    max_family_score = max(family_scores.values()) if family_scores else 1.0
    family_nodes = []
    for family, score in sorted(family_scores.items()):
        normalized_score = score / max_family_score if max_family_score > 0 else 0.0
        family_nodes.append(
            {
                "id": f"family:{family}",
                "kind": "family",
                "label": FEATURE_FAMILY_META[family]["label"],
                "family": family,
                "color": FEATURE_FAMILY_META[family]["color"],
                "score": round(normalized_score, 6),
            }
        )
        edges.append(
            {
                "source": "model_signal",
                "target": f"family:{family}",
                "kind": "family_signal",
                "weight": round(normalized_score, 6),
                "label": FEATURE_FAMILY_META[family]["label"],
            }
        )
    nodes[1:1] = family_nodes

    related_edges = _related_feature_edges(selected_features, feature_scores, max_score)
    edges.extend(related_edges)

    return {
        "schema_version": 1,
        "title": "Feature signal network",
        "description": "Feature-family graph derived from published model interpretation rankings.",
        "nodes": nodes,
        "edges": edges,
        "families": FEATURE_FAMILY_META,
    }


def _feature_family(feature: str) -> str:
    value = feature.lower()
    if "starter" in value:
        return "starter"
    if "lineup" in value or any(
        token in value for token in ["ops", "wrcplus", "war_", "pa_sum", "sb_sum"]
    ):
        return "lineup"
    if "bullpen" in value:
        return "bullpen"
    if "last_5" in value or "recent" in value:
        return "recent_form"
    if any(
        token in value
        for token in ["run_diff", "runs_for", "runs_against", "win_rate", "team_code"]
    ):
        return "team_context"
    if "day_of_week" in value:
        return "schedule"
    return "other"


def _feature_family_sort_index(family: str) -> int:
    order = [
        "starter",
        "lineup",
        "recent_form",
        "bullpen",
        "team_context",
        "schedule",
        "other",
    ]
    try:
        return order.index(family)
    except ValueError:
        return len(order)


def _feature_side(feature: str) -> str:
    if feature.startswith("home_minus_away_"):
        return "comparison"
    if feature.startswith("home_"):
        return "home"
    if feature.startswith("away_"):
        return "away"
    return "neutral"


def _feature_node_label(feature: str) -> str:
    value = feature
    for prefix in ["home_minus_away_", "home_", "away_"]:
        if value.startswith(prefix):
            value = value.removeprefix(prefix)
            break
    return value.replace("_", " ")


def _related_feature_edges(
    selected_features: set[str],
    feature_scores: dict[str, dict[str, Any]],
    max_score: float,
) -> list[dict[str, Any]]:
    feature_groups: dict[str, list[str]] = {}
    for feature in selected_features:
        key = _feature_relation_key(feature)
        feature_groups.setdefault(key, []).append(feature)

    edges: list[dict[str, Any]] = []
    for features in feature_groups.values():
        if len(features) < 2:
            continue
        sorted_features = sorted(features)
        for source, target in zip(sorted_features, sorted_features[1:], strict=False):
            source_score = float(feature_scores[source]["score"])
            target_score = float(feature_scores[target]["score"])
            normalized_score = (
                min(source_score, target_score) / max_score if max_score > 0 else 0.0
            )
            edges.append(
                {
                    "source": f"feature:{source}",
                    "target": f"feature:{target}",
                    "kind": "home_away_relation",
                    "weight": round(normalized_score, 6),
                    "label": "Home/away related signal",
                }
            )
    return edges


def _feature_relation_key(feature: str) -> str:
    for prefix in ["home_minus_away_", "home_", "away_"]:
        if feature.startswith(prefix):
            return feature.removeprefix(prefix)
    return feature


def _build_game_explanations(
    shap_values: np.ndarray,
    X_valid: pd.DataFrame,
    models: list[Any],
    y_valid: pd.Series | np.ndarray | None,
    game_metadata: pd.DataFrame | None,
    max_games: int = 12,
    factors_per_side: int = 4,
) -> dict[str, Any]:
    probabilities = _predict_probability(models, X_valid)
    explanation_strength = np.abs(shap_values).sum(axis=1)
    selected_indices = np.argsort(-explanation_strength)[: min(max_games, len(X_valid))]
    metadata = _aligned_game_metadata(game_metadata, X_valid)
    labels = (
        pd.Series(y_valid).reset_index(drop=True)
        if y_valid is not None
        else pd.Series([None] * len(X_valid))
    )

    games: list[dict[str, Any]] = []
    for row_position in selected_indices:
        position = int(row_position)
        probability = float(probabilities[position])
        home_factors, away_factors = _game_factor_groups(
            shap_row=shap_values[position],
            feature_row=X_valid.iloc[position],
            factors_per_side=factors_per_side,
        )
        games.append(
            {
                **_game_metadata_record(metadata.iloc[position], position),
                "home_win_probability": round(probability, 6),
                "predicted_side": "home" if probability >= 0.5 else "away",
                "actual_home_win": _optional_binary_label(labels.iloc[position]),
                "confidence": round(abs(probability - 0.5) * 2, 6),
                "explanation_strength": round(float(explanation_strength[position]), 6),
                "top_home_factors": home_factors,
                "top_away_factors": away_factors,
            }
        )

    return {
        "schema_version": 1,
        "title": "Game explanation view",
        "description": "Per-game SHAP factors that pushed the model toward home or away.",
        "sample_size": int(len(X_valid)),
        "display_count": len(games),
        "class_label": "home_win",
        "games": games,
    }


def _aligned_game_metadata(
    game_metadata: pd.DataFrame | None,
    X_valid: pd.DataFrame,
) -> pd.DataFrame:
    if game_metadata is None:
        return pd.DataFrame(index=range(len(X_valid)))
    return game_metadata.reset_index(drop=True).reindex(range(len(X_valid))).copy()


def _game_factor_groups(
    shap_row: np.ndarray,
    feature_row: pd.Series,
    factors_per_side: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    feature_names = list(feature_row.index)
    ranked_indices = np.argsort(-np.abs(shap_row))
    home_factors: list[dict[str, Any]] = []
    away_factors: list[dict[str, Any]] = []

    for feature_index in ranked_indices:
        contribution = float(shap_row[int(feature_index)])
        if contribution == 0:
            continue
        factor = _game_factor_record(
            feature=feature_names[int(feature_index)],
            contribution=contribution,
            feature_value=feature_row.iloc[int(feature_index)],
        )
        if contribution > 0 and len(home_factors) < factors_per_side:
            home_factors.append(factor)
        elif contribution < 0 and len(away_factors) < factors_per_side:
            away_factors.append(factor)
        if (
            len(home_factors) >= factors_per_side
            and len(away_factors) >= factors_per_side
        ):
            break
    return home_factors, away_factors


def _game_factor_record(
    feature: str,
    contribution: float,
    feature_value: Any,
) -> dict[str, Any]:
    family = _feature_family(feature)
    return {
        "feature": feature,
        "label": _feature_node_label(feature),
        "family": family,
        "family_label": FEATURE_FAMILY_META[family]["label"],
        "side": _feature_side(feature),
        "contribution": round(contribution, 6),
        "abs_contribution": round(abs(contribution), 6),
        "feature_value": _json_scalar(feature_value),
    }


def _game_metadata_record(row: pd.Series, row_position: int) -> dict[str, Any]:
    home_code = _optional_int_value(row.get("home_team_code"))
    away_code = _optional_int_value(row.get("away_team_code"))
    s_no = _optional_int_value(row.get("s_no"))
    return {
        "id": str(s_no) if s_no is not None else f"row_{row_position}",
        "row_index": row_position,
        "s_no": s_no,
        "game_date": _optional_string_value(row.get("game_date")),
        "home_team": _team_record(home_code),
        "away_team": _team_record(away_code),
    }


def _team_record(code: int | None) -> dict[str, Any]:
    return {
        "code": code,
        "name": TEAM_CODES.get(code, "Unknown") if code is not None else "Unknown",
    }


def _optional_binary_label(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    return int(value)


def _optional_int_value(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    return int(value)


def _optional_string_value(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return str(value)


def _json_scalar(value: Any) -> float | int | str | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, int | float | str):
        return value
    return str(value)

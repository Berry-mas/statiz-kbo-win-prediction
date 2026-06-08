"""Utilities for converting feature rows into LightGBM input matrices."""

from __future__ import annotations

import pandas as pd

from .constants import STADIUM_CODES, TEAM_CODES

_CATEGORY_VALUE_MAPS: dict[str, dict[int, int]] = {
    "home_team_code": {value: idx for idx, value in enumerate(sorted(TEAM_CODES))},
    "away_team_code": {value: idx for idx, value in enumerate(sorted(TEAM_CODES))},
    "stadium_code": {value: idx for idx, value in enumerate(sorted(STADIUM_CODES))},
    "day_of_week": {value: value for value in range(7)},
    "month": {value: value - 1 for value in range(1, 13)},
    "is_doubleheader": {0: 0, 1: 1},
}


def _encode_categorical(series: pd.Series, feature_name: str) -> pd.Series:
    """Encode a categorical column with a stable project-level mapping."""
    numeric = pd.to_numeric(series, errors="coerce")
    if feature_name == "is_doubleheader":
        numeric = numeric.astype("boolean").astype("Int64")

    mapping = _CATEGORY_VALUE_MAPS.get(feature_name)
    if mapping is None:
        return numeric.fillna(-1).astype("int32")
    return numeric.map(mapping).fillna(-1).astype("int32")


def prepare_model_matrix(
    df: pd.DataFrame,
    feature_cols: list[str],
    categorical_features: list[str],
) -> pd.DataFrame:
    """Return a model input matrix with stable categorical integer values.

    Statiz team, stadium, month, and day codes are already stable numeric codes.
    Keeping those original codes avoids fold-specific category remapping from
    ``pandas.Categorical.cat.codes``.
    """
    X = df[feature_cols].copy()
    for col in categorical_features:
        if col not in X.columns:
            continue
        X[col] = _encode_categorical(X[col], col)
    return X

"""Helpers for reading and migrating submission_log.csv."""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
from loguru import logger

SUBMISSION_LOG_COLUMNS = [
    "s_no",
    "game_date",
    "submitted_prob",
    "submitted",
    "source",
    "attempts",
    "submitted_at",
    "response_status",
    "response_message",
]

LEGACY_SUBMISSION_LOG_COLUMNS = [
    "s_no",
    "game_date",
    "submitted_prob",
    "submitted",
    "attempts",
    "submitted_at",
    "response_status",
    "response_message",
]

SOURCE_INDEX = SUBMISSION_LOG_COLUMNS.index("source")


def read_submission_log(path: str | Path) -> pd.DataFrame:
    """Read submission_log.csv, accepting both legacy and current schemas."""
    csv_path = Path(path)
    if not csv_path.exists():
        return pd.DataFrame()

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file_obj:
        rows = list(csv.reader(file_obj))
    if not rows:
        return pd.DataFrame()

    header = rows[0]
    if header == SUBMISSION_LOG_COLUMNS:
        return _coerce_types(pd.DataFrame(rows[1:], columns=SUBMISSION_LOG_COLUMNS))
    if header == LEGACY_SUBMISSION_LOG_COLUMNS:
        normalized = _normalize_legacy_rows(rows[1:], csv_path)
        return _coerce_types(pd.DataFrame(normalized, columns=SUBMISSION_LOG_COLUMNS))
    if {"s_no", "game_date", "submitted"}.issubset(header):
        partial = pd.DataFrame(rows[1:], columns=header)
        if "source" not in partial.columns:
            partial["source"] = "auto"
        for column in SUBMISSION_LOG_COLUMNS:
            if column not in partial.columns:
                partial[column] = pd.NA
        return _coerce_types(partial[SUBMISSION_LOG_COLUMNS])

    logger.warning("Unknown submission log schema in {}: {}", csv_path, header)
    return pd.DataFrame()


def _coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    """Restore basic dtypes after csv.reader normalization."""
    for column in ("s_no", "submitted_prob", "attempts", "response_status"):
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def ensure_submission_log_schema(path: str | Path) -> None:
    """Rewrite a legacy submission log with the current source column."""
    csv_path = Path(path)
    if not csv_path.exists():
        return

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file_obj:
        rows = list(csv.reader(file_obj))
    if not rows:
        return

    header = rows[0]
    if header == SUBMISSION_LOG_COLUMNS:
        return
    if header != LEGACY_SUBMISSION_LOG_COLUMNS:
        logger.warning("Cannot migrate unknown submission log schema: {}", csv_path)
        return

    normalized = _normalize_legacy_rows(rows[1:], csv_path)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.writer(file_obj)
        writer.writerow(SUBMISSION_LOG_COLUMNS)
        writer.writerows(normalized)
    logger.info("Migrated submission log schema: {}", csv_path)


def _normalize_legacy_rows(rows: list[list[str]], csv_path: Path) -> list[list[str]]:
    """Insert source=auto into legacy rows while preserving already-new rows."""
    normalized: list[list[str]] = []
    for index, row in enumerate(rows, start=2):
        if len(row) == len(LEGACY_SUBMISSION_LOG_COLUMNS):
            normalized.append([*row[:SOURCE_INDEX], "auto", *row[SOURCE_INDEX:]])
        elif len(row) == len(SUBMISSION_LOG_COLUMNS):
            normalized.append(row)
        elif not any(cell.strip() for cell in row):
            continue
        else:
            logger.warning(
                "Skipping malformed submission log row {} in {}: {}",
                index,
                csv_path,
                row,
            )
    return normalized

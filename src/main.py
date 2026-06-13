"""
CLI entry point for the Statiz KBO prediction system.

Commands:
  collect  --year YEAR [--date YYYY-MM-DD] [--include-team-stats]
                                               Collect raw data
  clean    --year YEAR                        Transform raw JSON → clean CSV
  features --year YEAR                        Build feature_game_pre_match CSV
  train    --years 2023,2024 [--val-years 2025]  Train LightGBM models
  predict  --date YYYY-MM-DD [--model-version lgbm_v001]  Generate predictions
  submit   --date YYYY-MM-DD [--model-version lgbm_v001] [--dry-run]  Predict + submit
  auto-submit --date YYYY-MM-DD [--model-version lgbm_v001]  Scheduled automation
  run-daily [--date YYYY-MM-DD] [--model-version lgbm_v001] [--dry-run]  Daily pipeline
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from loguru import logger


def _setup_logging() -> None:
    Path("logs").mkdir(exist_ok=True)
    logger.add(
        "logs/statiz_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="14 days",
        level="INFO",
        encoding="utf-8",
    )


def cmd_collect(args: argparse.Namespace) -> None:
    from .collector import DataCollector

    collector = DataCollector()

    if args.date:
        from datetime import datetime

        d = datetime.strptime(args.date, "%Y-%m-%d").date()
        logger.info("Collecting single day: {}", args.date)
        collector.collect_daily_all(d.year, d.month, d.day)
        if args.include_team_stats:
            collector.collect_team_season_stats(d.year)
    else:
        logger.info("Collecting full season for year={}", args.year)
        collector.collect_season_bulk(args.year)
        if args.include_team_stats:
            collector.collect_team_season_stats(args.year)


def cmd_clean(args: argparse.Namespace) -> None:
    from .cleaner import DataCleaner

    cleaner = DataCleaner()
    cleaner.clean_all(args.year)


def cmd_features(args: argparse.Namespace) -> None:
    from .feature_builder import FeatureBuilder

    builder = FeatureBuilder()
    builder.load_clean_data()
    df = builder.build_features_for_year(args.year)
    logger.info("Built {} feature rows for year={}", len(df), args.year)


def cmd_train(args: argparse.Namespace) -> None:
    from .trainer import ModelTrainer

    train_years = [int(y.strip()) for y in args.years.split(",")]
    val_years = (
        [int(y.strip()) for y in args.val_years.split(",")] if args.val_years else None
    )

    logger.info("Training on years={} val_years={}", train_years, val_years)
    trainer = ModelTrainer()
    model_path = trainer.run(train_years=train_years, val_years=val_years)
    logger.info("Model saved to {}", model_path)


def cmd_predict(args: argparse.Namespace) -> None:
    from .predictor import Predictor

    predictor = Predictor(model_version=args.model_version)
    predictions = predictor.predict_games(args.date)
    predictor.save_prediction_log(predictions, args.date)
    logger.info("Predicted {} games for {}", len(predictions), args.date)
    for p in predictions:
        logger.info("  s_no={} home_win={:.2f}%", p["s_no"], p["home_win_probability"])


def cmd_submit(args: argparse.Namespace) -> None:
    from .predictor import Predictor
    from .submitter import Submitter

    predictor = Predictor(model_version=args.model_version)
    predictions = predictor.predict_games(args.date)
    predictor.save_prediction_log(predictions, args.date)

    if args.dry_run:
        logger.info(
            "[DRY RUN] Would submit {} predictions for {}", len(predictions), args.date
        )
        for p in predictions:
            logger.info(
                "  [DRY RUN] s_no={} prob={:.2f}%", p["s_no"], p["home_win_probability"]
            )
        return

    submitter = Submitter()
    results = submitter.submit_all(predictions, args.date)
    submitted = sum(1 for r in results if r["submitted"])
    logger.info(
        "Submitted {}/{} predictions for {}", submitted, len(results), args.date
    )


def cmd_run_daily(args: argparse.Namespace) -> None:
    target_date = args.date or date.today().strftime("%Y-%m-%d")
    logger.info("run-daily for date={}", target_date)

    from .collector import DataCollector

    d_parts = target_date.split("-")
    collector = DataCollector()
    collector.collect_daily_all(int(d_parts[0]), int(d_parts[1]), int(d_parts[2]))

    from .cleaner import DataCleaner

    DataCleaner().clean_all(int(d_parts[0]))

    args.date = target_date
    cmd_submit(args)


def cmd_auto_submit(args: argparse.Namespace) -> None:
    from .automation import (
        AutomationConfig,
        parse_kst_datetime,
        run_submission_automation,
    )

    target_date = args.date or date.today().strftime("%Y-%m-%d")
    config = AutomationConfig(
        min_lead_minutes=args.min_lead_minutes,
        collect_data=not args.skip_collect,
        build_features=not args.skip_features,
        execute_submit=args.execute_submit,
        submission_source=args.submission_source,
        now=parse_kst_datetime(args.now) if args.now else None,
    )
    decisions = run_submission_automation(
        game_date=target_date,
        model_version=args.model_version,
        config=config,
    )
    eligible = sum(1 for row in decisions if row["would_submit"])
    logger.info(
        "auto-submit finished for {}: eligible={} total={} execute_submit={}",
        target_date,
        eligible,
        len(decisions),
        args.execute_submit,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Statiz KBO baseball win prediction system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p = subparsers.add_parser("collect", help="Collect raw data from API")
    p.add_argument("--year", type=int, required=True)
    p.add_argument(
        "--date", type=str, help="YYYY-MM-DD (single day; default: full season)"
    )
    p.add_argument(
        "--include-team-stats",
        action="store_true",
        help="Also collect teamRecord API files after baseline raw data",
    )

    p = subparsers.add_parser("clean", help="Transform raw JSON → clean CSV")
    p.add_argument("--year", type=int, required=True)

    p = subparsers.add_parser("features", help="Build feature CSV from clean data")
    p.add_argument("--year", type=int, required=True)

    p = subparsers.add_parser("train", help="Train LightGBM model")
    p.add_argument(
        "--years", type=str, required=True, help="Comma-separated: 2023,2024"
    )
    p.add_argument("--val-years", type=str, help="Validation years: 2025")

    p = subparsers.add_parser("predict", help="Generate predictions for a date")
    p.add_argument("--date", type=str, required=True, help="YYYY-MM-DD")
    p.add_argument("--model-version", type=str, default=None)

    p = subparsers.add_parser("submit", help="Predict and submit to API")
    p.add_argument("--date", type=str, required=True, help="YYYY-MM-DD")
    p.add_argument("--model-version", type=str, default=None)
    p.add_argument("--dry-run", action="store_true", help="Predict but do not submit")

    p = subparsers.add_parser(
        "auto-submit",
        help="Run date/time based automation for one date",
    )
    p.add_argument("--date", type=str, default=None, help="YYYY-MM-DD (default: today)")
    p.add_argument("--model-version", type=str, default=None)
    p.add_argument(
        "--execute-submit",
        action="store_true",
        help="Actually call prediction/savePrediction for eligible games",
    )
    p.add_argument(
        "--skip-collect",
        action="store_true",
        help="Use existing local data instead of calling collection APIs",
    )
    p.add_argument(
        "--skip-features",
        action="store_true",
        help="Use existing feature CSV instead of rebuilding features",
    )
    p.add_argument(
        "--now",
        type=str,
        default=None,
        help="Override scheduler current time for dry-run tests, e.g. 2025-10-01T17:30:00+09:00",
    )
    p.add_argument(
        "--min-lead-minutes",
        type=int,
        default=None,
        help="Skip games until they are within this many minutes before start time",
    )
    p.add_argument(
        "--submission-source",
        type=str,
        choices=("auto", "manual"),
        default="auto",
        help="Label successful submission logs so manual submits do not block a later auto pass",
    )

    p = subparsers.add_parser(
        "run-daily", help="Full daily pipeline: collect → predict → submit"
    )
    p.add_argument("--date", type=str, default=None, help="YYYY-MM-DD (default: today)")
    p.add_argument("--model-version", type=str, default=None)
    p.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    _setup_logging()

    dispatch = {
        "collect": cmd_collect,
        "clean": cmd_clean,
        "features": cmd_features,
        "train": cmd_train,
        "predict": cmd_predict,
        "submit": cmd_submit,
        "auto-submit": cmd_auto_submit,
        "run-daily": cmd_run_daily,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()

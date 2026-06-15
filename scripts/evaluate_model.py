"""CLI wrapper for offline model evaluation."""

from __future__ import annotations

import argparse

from src.feature_analysis import (
    publish_feature_analysis_to_web,
    run_saved_model_feature_analysis,
)
from src.model_evaluation import parse_years, run_evaluation


def main() -> None:
    """Run saved model evaluation and write artifacts."""
    parser = argparse.ArgumentParser(
        description="Evaluate saved Statiz model artifacts."
    )
    parser.add_argument("--model-version", default="lgbm_v005")
    parser.add_argument("--years", default="2023,2024,2025")
    parser.add_argument(
        "--feature-analysis",
        action="store_true",
        help="Generate feature importance, SHAP, and permutation analysis artifacts.",
    )
    parser.add_argument(
        "--feature-analysis-output-dir",
        default="outputs/feature_analysis",
        help="Directory for local feature analysis artifacts.",
    )
    parser.add_argument(
        "--publish-web",
        action="store_true",
        help="Copy feature analysis artifacts to web/public/feature-analysis.",
    )
    parser.add_argument("--top-n", type=int, default=30)
    parser.add_argument(
        "--dependence-features",
        default="",
        help="Comma-separated feature names for SHAP dependence plots.",
    )
    parser.add_argument(
        "--scoring",
        default=None,
        help="Optional sklearn scoring name for permutation importance.",
    )
    args = parser.parse_args()
    years = parse_years(args.years)

    output_dir = run_evaluation(
        model_version=args.model_version,
        years=years,
    )
    print(f"Saved evaluation artifacts to {output_dir}")

    if args.feature_analysis:
        dependence_features = [
            item.strip() for item in args.dependence_features.split(",") if item.strip()
        ]
        analysis_dir = run_saved_model_feature_analysis(
            model_version=args.model_version,
            years=years,
            output_dir=args.feature_analysis_output_dir,
            top_n=args.top_n,
            scoring=args.scoring,
            dependence_features=dependence_features,
        )
        print(f"Saved feature analysis artifacts to {analysis_dir}")

        if args.publish_web:
            manifest_path = publish_feature_analysis_to_web(analysis_dir)
            print(f"Published feature analysis manifest to {manifest_path}")


if __name__ == "__main__":
    main()

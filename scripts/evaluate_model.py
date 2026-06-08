"""CLI wrapper for offline model evaluation."""

from __future__ import annotations

import argparse

from src.model_evaluation import parse_years, run_evaluation


def main() -> None:
    """Run saved model evaluation and write artifacts."""
    parser = argparse.ArgumentParser(
        description="Evaluate saved Statiz model artifacts."
    )
    parser.add_argument("--model-version", default="lgbm_v005")
    parser.add_argument("--years", default="2023,2024,2025")
    args = parser.parse_args()

    output_dir = run_evaluation(
        model_version=args.model_version,
        years=parse_years(args.years),
    )
    print(f"Saved evaluation artifacts to {output_dir}")


if __name__ == "__main__":
    main()

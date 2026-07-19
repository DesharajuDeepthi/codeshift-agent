"""
Entry point for the UpgradePilot evaluation harness.

Usage:
    uv run python -m evals.run --suite detection --backend local
    uv run python -m evals.run --suite smoke --backend local
    uv run python -m evals.run --suite all --backend local
    uv run python -m evals.run --suite regression --backend langsmith
"""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="UpgradePilot evaluation harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--suite", choices=["smoke", "detection", "all", "regression"], required=True
    )
    parser.add_argument(
        "--backend",
        choices=["local", "langsmith"],
        default="local",
        help="Evaluation backend (default: local)",
    )
    args = parser.parse_args()

    if args.backend == "langsmith":
        if args.suite != "regression":
            parser.error("LangSmith backend currently supports --suite regression")
        from evals.langsmith_backend import run_langsmith_regression

        result = run_langsmith_regression()
    else:
        from evals.suites.local import run_local_suite

        result = run_local_suite(args.suite)
    result.print_report()

    sys.exit(0 if result.passed else 1)


if __name__ == "__main__":
    main()

"""Sync versioned local evaluation datasets to LangSmith."""

from __future__ import annotations

import sys

from evals.langsmith_backend import sync_langsmith_datasets


def main() -> None:
    result = sync_langsmith_datasets()
    result.print_report()
    sys.exit(0 if result.passed else 1)


if __name__ == "__main__":
    main()

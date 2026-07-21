"""
Benchmark dataset for UpgradePilot LLM evals.

Each example is a (input, expected_output) pair:
  input:  repository_url + ref — what we feed the pipeline
  output: what we expect the pipeline to produce

Run once to create/update the dataset in LangSmith:
  python evals/dataset.py
"""

from __future__ import annotations

import os
from typing import Any

from langsmith import Client

DATASET_NAME = "upgradepilot-benchmark-v1"

# ---------------------------------------------------------------------------
# Benchmark examples
# Each "output" defines the MINIMUM we expect — scorers check these.
# ---------------------------------------------------------------------------
EXAMPLES: list[dict[str, Any]] = [
    {
        "input": {
            "repository_url": "https://github.com/nsidnev/fastapi-realworld-example-app",
            "ref": "master",
            "migration_pack": "pydantic-v1-to-v2",
            "analysis_mode": "standard",
        },
        "output": {
            # Minimum findings we expect for this repo
            "min_finding_count": 5,
            # Applicability — this repo uses Pydantic v1
            "expected_applicability": "SUPPORTED",
            # Risk score should be non-trivial (repo has real v1 usage)
            "min_risk_score": 0.3,
            # The migration plan must mention key v2 migration topics
            "plan_must_mention": ["model_validator", "field_validator", "BaseModel"],
            # Interpretation must be present for at least one finding
            "min_interpreted_findings": 1,
        },
    },
    {
        "input": {
            "repository_url": "https://github.com/pydantic/pydantic",
            "ref": "main",
            "migration_pack": "pydantic-v1-to-v2",
            "analysis_mode": "standard",
        },
        "output": {
            # pydantic itself is already v2 — should be NOT_APPLICABLE or UNSUPPORTED
            "expected_applicability": "UNSUPPORTED",
            "min_finding_count": 0,
            "min_risk_score": 0.0,
            "plan_must_mention": [],
            "min_interpreted_findings": 0,
        },
    },
]


def create_or_update_dataset() -> str:
    """Push benchmark examples to LangSmith. Returns the dataset ID."""
    api_key = os.environ.get("LANGSMITH_API_KEY")
    if not api_key:
        raise RuntimeError("LANGSMITH_API_KEY env var must be set")

    client = Client(api_key=api_key)

    # Get or create dataset
    existing = [d for d in client.list_datasets() if d.name == DATASET_NAME]
    if existing:
        dataset = existing[0]
        print(f"Using existing dataset: {DATASET_NAME} ({dataset.id})")
        # Clear old examples so we can repopulate
        for ex in client.list_examples(dataset_id=dataset.id):
            client.delete_example(ex.id)
    else:
        dataset = client.create_dataset(
            DATASET_NAME,
            description=(
                "Fixed benchmark repos for UpgradePilot LLM eval. "
                "Each example has expected finding counts, applicability, "
                "risk scores, and required plan keywords."
            ),
        )
        print(f"Created dataset: {DATASET_NAME} ({dataset.id})")

    for ex in EXAMPLES:
        client.create_example(
            inputs=ex["input"],
            outputs=ex["output"],
            dataset_id=dataset.id,
        )
    print(f"Uploaded {len(EXAMPLES)} examples.")
    return str(dataset.id)


if __name__ == "__main__":
    dataset_id = create_or_update_dataset()
    print(f"\nDataset ready. View at: https://smith.langchain.com/datasets/{dataset_id}")

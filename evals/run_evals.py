"""
Run UpgradePilot LLM evals.

Usage:
  python evals/run_evals.py                  # run all benchmark examples
  python evals/run_evals.py --fail-under 0.7 # exit 1 if avg score < 0.7 (CI)

What it does:
  1. Runs the full UpgradePilot pipeline in fixture mode (fast, no LLM calls)
  2. Scores each output with deterministic scorers (scorers.py)
  3. Pushes scores to LangSmith if LANGSMITH_API_KEY is set
  4. Prints a summary table and exits 1 if below threshold
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from typing import Any

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_root, "src"))
sys.path.insert(0, _root)  # so `evals` package is importable

from evals.scorers import ALL_SCORERS

# ---------------------------------------------------------------------------
# Inline benchmark examples (no LangSmith dependency to pull them)
# ---------------------------------------------------------------------------
from upgradepilot.graph.state import FIXTURE_SUPPORTED, FIXTURE_UNSUPPORTED  # noqa: E402

BENCHMARK_EXAMPLES = [
    {
        "inputs": {
            "repository_url": "https://github.com/nsidnev/fastapi-realworld-example-app",
            "ref": "master",
            "fixture_scenario": FIXTURE_SUPPORTED,
        },
        "outputs": {
            "min_finding_count": 1,
            "expected_applicability": "SUPPORTED",
            "min_risk_score": 0.0,
            "plan_must_mention": [],
            "min_interpreted_findings": 0,
        },
    },
    {
        "inputs": {
            "repository_url": "https://github.com/pydantic/pydantic",
            "ref": "main",
            "fixture_scenario": FIXTURE_UNSUPPORTED,
        },
        "outputs": {
            "expected_applicability": "UNSUPPORTED",
            "min_finding_count": 0,
            "min_risk_score": 0.0,
            "plan_must_mention": [],
            "min_interpreted_findings": 0,
        },
    },
]


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------


async def _run_pipeline(inputs: dict[str, Any]) -> dict[str, Any]:
    from upgradepilot.graph.build import build_graph
    from upgradepilot.graph.state import make_initial_state

    request_data = {
        "repository_url": inputs["repository_url"],
        "ref": inputs.get("ref", "main"),
        "migration_pack": "pydantic-v1-to-v2",
        "analysis_mode": "fixture",
    }
    state = make_initial_state(
        analysis_id=f"eval-{int(time.time())}",
        request_data=request_data,
        fixture_scenario=inputs.get("fixture_scenario", FIXTURE_SUPPORTED),
    )
    graph = build_graph()
    config = {"configurable": {"thread_id": state["analysis_id"]}}
    final: dict[str, Any] = {}
    async for chunk in graph.astream(state, config=config, stream_mode="values"):  # type: ignore[attr-defined]
        final = dict(chunk)
    return final


# ---------------------------------------------------------------------------
# LangSmith result upload (optional — skipped if no API key)
# ---------------------------------------------------------------------------


def _push_to_langsmith(
    repo: str,
    scores: dict[str, tuple[float, str]],
    experiment_prefix: str,
) -> None:
    api_key = os.environ.get("LANGSMITH_API_KEY")
    if not api_key:
        return
    try:
        from langsmith import Client

        from evals.dataset import DATASET_NAME

        client = Client(api_key=api_key)
        datasets = [d for d in client.list_datasets() if d.name == DATASET_NAME]
        if not datasets:
            return
        dataset_id = datasets[0].id
        examples = [
            e
            for e in client.list_examples(dataset_id=dataset_id)
            if repo in str(e.inputs.get("repository_url", ""))
        ]
        if not examples:
            return
        example_id = examples[0].id
        run_id = str(__import__("uuid").uuid4())
        client.create_run(
            name=f"{experiment_prefix}/{repo}",
            run_type="chain",
            inputs={"repository": repo},
            id=run_id,
            project_name=os.environ.get("LANGSMITH_PROJECT", "upgradepilot-eval"),
        )
        for key, (score, comment) in scores.items():
            client.create_feedback(
                run_id=run_id,
                key=key,
                score=score,
                comment=comment,
                source_info={"example_id": str(example_id)},
            )
        client.update_run(run_id, end_time=__import__("datetime").datetime.utcnow())
    except Exception as exc:
        print(f"  [LangSmith upload skipped: {exc}]")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail-under", type=float, default=0.0)
    parser.add_argument("--experiment-prefix", type=str, default="upgradepilot-eval")
    args = parser.parse_args()

    all_scores: list[float] = []

    for example in BENCHMARK_EXAMPLES:
        inputs = example["inputs"]
        expected = example["outputs"]
        repo = inputs["repository_url"].split("/")[-1]

        print(f"\nRunning: {repo}...")
        t0 = time.time()
        output = asyncio.run(_run_pipeline(inputs))
        elapsed = round(time.time() - t0, 1)

        results: dict[str, tuple[float, str]] = {}
        for scorer in ALL_SCORERS:
            r = scorer(output, expected)
            results[r["key"]] = (float(r["score"]), r.get("comment", ""))

        print(
            f"  Applicability: {output.get('applicability_status')} | "
            f"Status: {output.get('status')} | {elapsed}s"
        )
        print(f"  {'Scorer':<28} {'Score':>6}   Detail")
        print(f"  {'-' * 62}")
        for key, (score, comment) in results.items():
            bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
            status = "PASS" if score >= 0.8 else "WARN" if score >= 0.5 else "FAIL"
            print(f"  {key:<28} {score:>6.3f}  [{bar}] {status}  {comment}")

        avg = sum(s for s, _ in results.values()) / len(results)
        print(f"  {'─' * 62}")
        print(f"  {'Example average':<28} {avg:>6.3f}")
        all_scores.extend(s for s, _ in results.values())

        _push_to_langsmith(repo, results, args.experiment_prefix)

    overall = sum(all_scores) / len(all_scores) if all_scores else 0.0
    print(f"\n{'=' * 64}")
    print(f"OVERALL AVERAGE SCORE: {overall:.3f}")
    ci_status = "PASS" if overall >= args.fail_under else "FAIL"
    print(f"CI THRESHOLD ({args.fail_under:.2f}):    {ci_status}")
    print(f"{'=' * 64}")

    if overall < args.fail_under:
        sys.exit(1)


if __name__ == "__main__":
    main()

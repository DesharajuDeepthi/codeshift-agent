"""Verify LangGraph PostgreSQL checkpoint persistence and resume.

This script uses fixture-mode analysis data, so it never downloads or executes a
repository. It requires DATABASE_URL to point at a reachable PostgreSQL service.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any, cast

from upgradepilot.graph.build import build_graph
from upgradepilot.graph.checkpointer import get_postgres_checkpointer
from upgradepilot.graph.state import FIXTURE_SUPPORTED, AnalysisStatus, make_initial_state


async def main() -> None:
    database_url = os.environ["DATABASE_URL"]
    thread_id = f"checkpoint-audit-{uuid.uuid4()}"
    analysis_id = str(uuid.uuid4())
    state = make_initial_state(
        analysis_id=analysis_id,
        request_data={
            "repository_url": "https://github.com/pydantic/pydantic",
            "ref": "main",
            "migration_pack": "pydantic-v1-to-v2",
            "analysis_mode": "fixture",
            "request_id": "checkpoint-audit",
            "github_owner": "pydantic",
            "github_repo": "pydantic",
        },
        fixture_scenario=FIXTURE_SUPPORTED,
    )
    config = {"configurable": {"thread_id": thread_id}}

    async with get_postgres_checkpointer(database_url) as checkpointer:
        await checkpointer.setup()
        graph = build_graph(checkpointer=checkpointer)
        result = await cast(Any, graph).ainvoke(state, config=config)
        if result["status"] != AnalysisStatus.COMPLETED:
            raise RuntimeError(f"expected completed analysis, got {result['status']!r}")

        checkpoint = await checkpointer.aget_tuple(config)
        if checkpoint is None:
            raise RuntimeError("no persisted checkpoint found")

        rebuilt_graph = build_graph(checkpointer=checkpointer)
        resumed_state = await cast(Any, rebuilt_graph).aget_state(config)
        if resumed_state.values.get("analysis_id") != analysis_id:
            raise RuntimeError("resumed state did not match persisted analysis")

    print(f"postgres_checkpoint_resume=pass thread_id={thread_id} analysis_id={analysis_id}")


if __name__ == "__main__":
    asyncio.run(main())

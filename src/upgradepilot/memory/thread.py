"""
Stable thread_id derivation for LangGraph checkpointer.

Same user + same repo always produces the same thread_id, allowing
LangGraph to resume from the previous checkpoint on re-analysis.
This is the foundation for cross-run delta detection.
"""

from __future__ import annotations

import hashlib
import uuid


def make_thread_id(user_id: uuid.UUID, repo_url: str) -> str:
    """
    Derive a stable LangGraph thread_id from user + repo.

    Collisions are impossible within a tenant: user_id is a UUID,
    repo_url is a canonical GitHub URL normalised to lowercase.
    """
    canonical = repo_url.strip().lower().rstrip("/")
    raw = f"{user_id}:{canonical}"
    return hashlib.sha256(raw.encode()).hexdigest()

"""
Agent config loader — reads agent.yaml once (LRU-cached) and exposes
typed helpers consumed by graph.py and nodes/pipeline.py.

agent.yaml is the single source of truth for:
  - LLM settings      (model, temperature, max_tokens)
  - Entry point       (which node the graph starts at)
  - Agent tools       (which tools the LLM can call — drives bind_tools + ToolNode)
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

import yaml


@lru_cache(maxsize=1)
def load_agent_config() -> dict:
    path = Path(__file__).parent / "agent.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _pipeline() -> dict:
    return load_agent_config()["agent"]["langgraph"]["pipeline"]


def get_entry_point() -> str:
    """Return the graph entry-point node id (e.g. 'agent')."""
    return _pipeline()["entry_point"]


def get_agent_tool_names() -> List[str]:
    """Return the list of tool names the LLM agent can call, as declared in agent.yaml."""
    return _pipeline()["agent_tools"]


def get_llm_config() -> dict:
    """Return the LLM block (model, temperature, max_tokens, etc.)."""
    return load_agent_config()["agent"]["llm"]


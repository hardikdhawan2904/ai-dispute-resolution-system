"""
Agent config loader — reads agent.yaml.
"""
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
    """Return the graph entry-point node id."""
    return _pipeline()["entry_point"]


def get_agent_tool_names() -> List[str]:
    """Return the list of tool names the LLM agent can call."""
    return _pipeline()["agent_tools"]


def get_llm_config() -> dict:
    """Return the LLM block."""
    return load_agent_config()["agent"]["llm"]

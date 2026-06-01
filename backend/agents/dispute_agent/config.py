"""
Agent config loader — reads agent.yaml once (cached) and exposes
typed helpers used by pipeline.py and graph.py.

All pipeline structure (nodes, edges, tools, entry point) is
sourced exclusively from agent.yaml. Nothing is hardcoded here.
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
    return _pipeline()["entry_point"]


def get_pipeline_nodes() -> List[dict]:
    return _pipeline()["nodes"]


def get_pipeline_edges() -> List[dict]:
    return _pipeline()["edges"]


def get_node_tools(node_id: str) -> List[str]:
    """Return all tool names declared for a node in agent.yaml."""
    for node in get_pipeline_nodes():
        if node["id"] == node_id:
            if "tools" in node:
                return node["tools"]
            if "tool" in node:
                return [node["tool"]]
    raise KeyError(f"Node '{node_id}' not found in agent.yaml pipeline")


def get_llm_config() -> dict:
    return load_agent_config()["agent"]["llm"]


def is_llm_node(node_id: str) -> bool:
    for node in get_pipeline_nodes():
        if node["id"] == node_id:
            return bool(node.get("llm_call", False))
    return False

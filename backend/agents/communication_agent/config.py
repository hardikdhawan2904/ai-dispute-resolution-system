from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml


@lru_cache(maxsize=1)
def load_agent_config() -> dict:
    path = Path(__file__).parent / "agent.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_llm_config() -> dict:
    return load_agent_config()["agent"]["llm"]

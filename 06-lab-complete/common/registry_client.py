"""Registry client helpers.

Provides `discover(task)` to look up an agent endpoint from the registry,
and `register(agent_info)` for agents to self-register on startup.
"""

import os

import httpx

REGISTRY_URL = os.getenv("REGISTRY_URL", "http://localhost:10000")


async def discover(task: str) -> str:
    """Return the endpoint URL of the agent that handles the given task.

    Args:
        task: The task identifier (e.g. "legal_question", "tax_question").

    Returns:
        The HTTP endpoint base URL of the matching agent.

    Raises:
        httpx.HTTPStatusError: If no agent is found or the registry is unreachable.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{REGISTRY_URL}/discover/{task}")
        resp.raise_for_status()
        return resp.json()["endpoint"]


async def register(agent_info: dict) -> None:
    """Register an agent with the registry.

    Args:
        agent_info: Dict with keys: agent_name, version, description,
                    tasks, endpoint, tags.

    Raises:
        httpx.HTTPStatusError: If registration fails.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{REGISTRY_URL}/register", json=agent_info)
        resp.raise_for_status()
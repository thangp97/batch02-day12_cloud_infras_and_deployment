"""Registry Service — port 10000.

A lightweight FastAPI service that allows agents to self-register and
clients to discover agent endpoints by task name.

Endpoints:
  POST /register          — register an agent
  GET  /discover/{task}   — find an agent that handles the given task
  GET  /agents            — list all registered agents
  GET  /health            — health check
"""

from __future__ import annotations

import json
import logging
import os
import signal
from datetime import datetime, timezone
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

PORT = int(os.getenv("REGISTRY_PORT", "10000"))


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "time": self.formatTime(record),
            "level": record.levelname,
            "agent": "registry",
            "msg": record.getMessage(),
        })


def _setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    logging.root.handlers = [handler]
    logging.root.setLevel(logging.INFO)


_setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="A2A Registry", version="1.0.0")

agents: dict[str, dict[str, Any]] = {}


class AgentRegistration(BaseModel):
    agent_name: str
    version: str = "1.0"
    description: str = ""
    tasks: list[str] = []
    endpoint: str
    tags: list[str] = []


@app.post("/register", status_code=200)
async def register(registration: AgentRegistration) -> dict:
    entry = registration.model_dump()
    entry["registered_at"] = datetime.now(timezone.utc).isoformat()
    agents[registration.agent_name] = entry
    logger.info(
        "Registered agent '%s' at %s (tasks=%s)",
        registration.agent_name,
        registration.endpoint,
        registration.tasks,
    )
    return {"status": "ok", "agent_name": registration.agent_name}


@app.get("/discover/{task}")
async def discover(task: str) -> dict:
    for agent in agents.values():
        if task in agent.get("tasks", []):
            logger.info("Discovered agent '%s' for task '%s'", agent["agent_name"], task)
            return {
                "agent_name": agent["agent_name"],
                "endpoint": agent["endpoint"],
                "description": agent.get("description", ""),
            }
    raise HTTPException(status_code=404, detail=f"No agent found for task '{task}'")


@app.get("/agents")
async def list_agents() -> dict:
    return {"agents": list(agents.values())}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "agent_count": len(agents)}


if __name__ == "__main__":
    logger.info("Starting Registry on port %d", PORT)
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info"))

    def _handle_sigterm(*_):
        logger.info("SIGTERM received — initiating graceful shutdown")
        server.should_exit = True

    signal.signal(signal.SIGTERM, _handle_sigterm)
    import asyncio
    asyncio.run(server.serve())

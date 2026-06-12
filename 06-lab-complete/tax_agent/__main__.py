"""Tax Agent server entry point — port 10102."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi.responses import JSONResponse

load_dotenv()

from a2a.server.apps import A2AFastAPIApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from common.registry_client import register
from tax_agent.agent_executor import TaxAgentExecutor


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "time": self.formatTime(record),
            "level": record.levelname,
            "agent": "tax_agent",
            "msg": record.getMessage(),
        })


def _setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    logging.root.handlers = [handler]
    logging.root.setLevel(logging.INFO)


_setup_logging()
logger = logging.getLogger(__name__)

PORT = int(os.getenv("TAX_AGENT_PORT", "10102"))
HOST = os.getenv("AGENT_HOST", "localhost")
REGISTRY_URL = os.getenv("REGISTRY_URL", "http://localhost:10000")
AGENT_ENDPOINT = f"http://{HOST}:{PORT}"
_START_TIME = time.time()


async def _register_with_retry(max_attempts: int = 10, delay: float = 2.0) -> None:
    info = {
        "agent_name": "tax-agent",
        "version": "1.0",
        "description": "Specialist tax attorney and CPA agent for tax law questions",
        "tasks": ["tax_question"],
        "endpoint": AGENT_ENDPOINT,
        "tags": ["tax", "irs", "tax-evasion", "penalties"],
    }
    for attempt in range(1, max_attempts + 1):
        try:
            await register(info)
            logger.info("Registered with registry (attempt %d)", attempt)
            return
        except Exception as exc:
            logger.warning(
                "Registry not ready (attempt %d/%d): %s — retrying in %.0fs",
                attempt, max_attempts, exc, delay,
            )
            await asyncio.sleep(delay)
    logger.error("Failed to register after %d attempts", max_attempts)


async def main() -> None:
    await _register_with_retry()

    agent_card = AgentCard(
        name="Tax Agent",
        description="Specialist tax attorney and CPA for tax law and compliance questions",
        url=AGENT_ENDPOINT,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[
            AgentSkill(
                id="tax_question",
                name="Tax Question",
                description=(
                    "Answer questions about tax law, tax evasion consequences, "
                    "IRS penalties, corporate tax liability, and related topics."
                ),
                tags=["tax", "irs", "penalties", "compliance"],
            )
        ],
    )

    executor = TaxAgentExecutor()
    task_store = InMemoryTaskStore()
    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=task_store,
    )
    app_builder = A2AFastAPIApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )
    app = app_builder.build()

    @app.get("/health")
    async def health():
        return {"status": "ok", "agent": "tax_agent",
                "uptime_seconds": round(time.time() - _START_TIME)}

    @app.get("/ready")
    async def ready():
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                await client.get(f"{REGISTRY_URL}/health")
            return {"ready": True}
        except Exception:
            return JSONResponse(status_code=503, content={"ready": False})

    config = uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info")
    server = uvicorn.Server(config)

    def _handle_sigterm(*_):
        logger.info("SIGTERM received — initiating graceful shutdown")
        server.should_exit = True

    signal.signal(signal.SIGTERM, _handle_sigterm)

    logger.info("Tax Agent listening on port %d", PORT)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())

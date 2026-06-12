"""Customer Agent server entry point — port 10100."""

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
from customer_agent.agent_executor import CustomerAgentExecutor
from customer_agent.middleware import auth_rate_cost_middleware


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "time": self.formatTime(record),
            "level": record.levelname,
            "agent": "customer_agent",
            "msg": record.getMessage(),
        })


def _setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    logging.root.handlers = [handler]
    logging.root.setLevel(logging.INFO)


_setup_logging()
logger = logging.getLogger(__name__)

# Railway inject PORT tự động; fallback về CUSTOMER_AGENT_PORT cho Docker
PORT = int(os.getenv("PORT", os.getenv("CUSTOMER_AGENT_PORT", "10100")))
HOST = os.getenv("AGENT_HOST", "localhost")
REGISTRY_URL = os.getenv("REGISTRY_URL", "http://localhost:10000")
AGENT_ENDPOINT = f"http://{HOST}:{PORT}"
_START_TIME = time.time()


async def _register_with_retry(max_attempts: int = 10, delay: float = 2.0) -> None:
    info = {
        "agent_name": "customer-agent",
        "version": "1.0",
        "description": "Entry-point legal assistant; routes user questions to the Law Agent",
        "tasks": [],
        "endpoint": AGENT_ENDPOINT,
        "tags": ["customer", "entry-point", "legal-assistant"],
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
        name="Customer Agent",
        description=(
            "Your legal assistant. Ask any legal question — I will route it through "
            "our network of specialist legal, tax, and compliance agents."
        ),
        url=AGENT_ENDPOINT,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[
            AgentSkill(
                id="legal_assistant",
                name="Legal Assistant",
                description=(
                    "Answer legal questions by routing them to specialist agents "
                    "covering contract law, tax, and regulatory compliance."
                ),
                tags=["legal", "assistant", "multi-agent"],
            )
        ],
    )

    executor = CustomerAgentExecutor()
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

    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])
    app.middleware("http")(auth_rate_cost_middleware)

    @app.get("/health")
    async def health():
        return {"status": "ok", "agent": "customer_agent",
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

    logger.info("Customer Agent listening on port %d", PORT)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())

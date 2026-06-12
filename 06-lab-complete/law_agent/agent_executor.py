"""Law Agent — AgentExecutor bridge between A2A SDK and LangGraph StateGraph."""

from __future__ import annotations

import logging
from uuid import uuid4

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, TextPart

from law_agent.graph import create_graph

logger = logging.getLogger(__name__)

# Build graph once at module load
_graph = create_graph()


class LawAgentExecutor(AgentExecutor):
    """Bridges A2A RequestContext to the Law StateGraph agent."""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        question = self._extract_question(context)
        context_id = context.context_id or str(uuid4())
        task_id = context.task_id or str(uuid4())
        metadata = context.message.metadata or {} if context.message else {}
        trace_id = metadata.get("trace_id", str(uuid4()))
        depth = int(metadata.get("delegation_depth", 0))

        logger.info(
            "LawAgent executing | task=%s context=%s trace=%s depth=%d",
            task_id, context_id, trace_id, depth,
        )

        updater = TaskUpdater(event_queue, task_id, context_id)
        await updater.submit()
        await updater.start_work()

        try:
            result = await _graph.ainvoke(
                {
                    "question": question,
                    "context_id": context_id,
                    "trace_id": trace_id,
                    "delegation_depth": depth,
                    "law_analysis": "",
                    "needs_tax": False,
                    "needs_compliance": False,
                    "tax_result": "",
                    "compliance_result": "",
                    "final_answer": "",
                },
                config={"configurable": {"thread_id": context_id}},
            )

            answer = result.get("final_answer", "")
            if not answer:
                # Fallback: use law_analysis if aggregation didn't produce output
                answer = result.get("law_analysis", "")
            if not answer:
                answer = "I was unable to generate a legal analysis at this time."

            await updater.add_artifact(
                parts=[Part(root=TextPart(text=answer))],
                name="legal_analysis",
            )
            await updater.complete()

        except Exception as exc:
            logger.exception("LawAgent execution error: %s", exc)
            await updater.failed(
                updater.new_agent_message(
                    parts=[Part(root=TextPart(text=f"Legal analysis failed: {exc}"))]
                )
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id or str(uuid4())
        context_id = context.context_id or str(uuid4())
        updater = TaskUpdater(event_queue, task_id, context_id)
        await updater.cancel()

    @staticmethod
    def _extract_question(context: RequestContext) -> str:
        if context.message and context.message.parts:
            parts = []
            for part in context.message.parts:
                inner = getattr(part, "root", part)
                text = getattr(inner, "text", None)
                if text:
                    parts.append(text)
            return "\n".join(parts)
        return ""
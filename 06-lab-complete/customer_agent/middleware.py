"""Auth, rate limiting, cost guard cho Customer Agent."""
from __future__ import annotations

import collections
import datetime
import os
import time

from fastapi import Request
from fastapi.responses import JSONResponse

AGENT_API_KEY = os.getenv("AGENT_API_KEY", "change-me")
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MIN", "10"))
MONTHLY_BUDGET_USD = float(os.getenv("MONTHLY_BUDGET_USD", "10.0"))
COST_PER_REQUEST = float(os.getenv("COST_PER_REQUEST_USD", "0.01"))

_SKIP_PATHS = {"/health", "/ready", "/.well-known/agent.json"}

# In-memory stores — OK for single-instance Railway deploy
_request_times: dict[str, collections.deque] = {}
_monthly_cost: dict[str, float] = {}
_current_month: dict[str, str] = {}


def _month_key() -> str:
    return datetime.date.today().strftime("%Y-%m")


async def auth_rate_cost_middleware(request: Request, call_next):
    if request.url.path in _SKIP_PATHS:
        return await call_next(request)

    # 1. API Key auth
    api_key = request.headers.get("X-API-Key", "")
    if api_key != AGENT_API_KEY:
        return JSONResponse(status_code=401, content={"error": "Invalid API key"})

    user_id = api_key[:8]

    # 2. Rate limiting — sliding window 1 phút
    now = time.time()
    window = _request_times.setdefault(user_id, collections.deque())
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= RATE_LIMIT:
        return JSONResponse(
            status_code=429,
            content={"error": f"Rate limit exceeded: {RATE_LIMIT} req/min"},
        )
    window.append(now)

    # 3. Cost guard — monthly budget
    month = _month_key()
    if _current_month.get(user_id) != month:
        _current_month[user_id] = month
        _monthly_cost[user_id] = 0.0
    if _monthly_cost[user_id] + COST_PER_REQUEST > MONTHLY_BUDGET_USD:
        return JSONResponse(
            status_code=402,
            content={"error": f"Monthly budget ${MONTHLY_BUDGET_USD} exceeded"},
        )
    _monthly_cost[user_id] += COST_PER_REQUEST

    return await call_next(request)

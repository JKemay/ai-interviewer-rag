"""Liveness and readiness probes.

These are different questions and conflating them causes outages:

  /healthz  — "is this process alive?" If it fails, the orchestrator restarts
              the container. It must NOT check dependencies: a database blip
              would otherwise trigger a restart storm across every replica,
              turning a recoverable dependency failure into an outage.

  /readyz   — "should this instance receive traffic?" If it fails, the load
              balancer stops routing here but leaves the process running. This
              is where dependency checks belong.
"""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    status: Literal["ready", "degraded"]
    checks: dict[str, bool]


@router.get("/healthz", summary="Liveness probe")
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/readyz", summary="Readiness probe")
async def readyz() -> ReadinessResponse:
    # No dependencies yet. Phase 1 adds a database round-trip here, and Phase 3
    # object storage. Each check reports independently so a partial outage is
    # visible rather than collapsed into one boolean.
    checks: dict[str, bool] = {}
    healthy = all(checks.values())
    return ReadinessResponse(status="ready" if healthy else "degraded", checks=checks)

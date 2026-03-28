"""
aurolab/services/execution_service/api/execution_router.py

POST /api/v1/execute   — Submit a GeneratedProtocol for simulation + plan creation
GET  /api/v1/plans/{plan_id}  — Retrieve an execution plan
GET  /api/v1/plans/           — List all plans
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..core.orchestrator import execute_protocol
from ..core.isaac_sim_bridge import SimMode
from ..core.robot_commands import ExecutionPlan, ExecutionStatus

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["Execution"])


class ExecuteRequest(BaseModel):
    protocol: dict = Field(description="GeneratedProtocol JSON from /api/v1/generate")
    sim_mode: str = Field(default="mock", pattern=r"^(mock|live)$")
    auto_correct: bool = Field(default=True)


class ExecutionSummaryResponse(BaseModel):
    plan_id: str
    protocol_id: str
    protocol_title: str
    status: str
    command_count: int
    command_breakdown: dict
    estimated_mins: float
    validation_errors: int
    sim_passed: bool | None
    is_executable: bool
    collision_description: str | None = None


def _plan_to_summary(plan: ExecutionPlan) -> ExecutionSummaryResponse:
    s = plan.summary()
    return ExecutionSummaryResponse(
        **s,
        collision_description=(
            plan.simulation_result.collision_description
            if plan.simulation_result and not plan.simulation_result.passed
            else None
        ),
    )


@router.post(
    "/execute",
    response_model=ExecutionSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Simulate and validate a protocol for robotic execution",
)
async def execute(body: ExecuteRequest, request: Request) -> ExecutionSummaryResponse:
    plan_store: dict = request.app.state.execution_plan_store

    mode = SimMode.LIVE if body.sim_mode == "live" else SimMode.MOCK

    try:
        plan = execute_protocol(
            protocol=body.protocol,
            sim_mode=mode,
            auto_correct=body.auto_correct,
        )
    except Exception as exc:
        log.error("execute_failed", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Execution pipeline failed: {exc}",
        ) from exc

    plan_store[plan.plan_id] = plan
    return _plan_to_summary(plan)


@router.get(
    "/plans/{plan_id}",
    summary="Retrieve an execution plan by ID",
)
async def get_plan(plan_id: str, request: Request) -> dict:
    store: dict = request.app.state.execution_plan_store
    plan = store.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan.model_dump(mode="json")


@router.get(
    "/plans/",
    response_model=list[ExecutionSummaryResponse],
    summary="List all execution plans",
)
async def list_plans(request: Request) -> list[ExecutionSummaryResponse]:
    store: dict = request.app.state.execution_plan_store
    return [_plan_to_summary(p) for p in store.values()]
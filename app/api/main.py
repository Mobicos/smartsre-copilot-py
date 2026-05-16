"""API router composition."""

from fastapi import APIRouter

from app.api.routes import (
    agent_metrics,
    aiops,
    chat,
    contracts,
    file,
    native_agent,
    scenario_regression,
)

api_router = APIRouter()
api_router.include_router(chat.router, tags=["Chat"])
api_router.include_router(file.router, tags=["Files"])
api_router.include_router(aiops.router, tags=["AIOps"])
api_router.include_router(native_agent.router, tags=["NativeAgent"])
api_router.include_router(scenario_regression.router, tags=["ScenarioRegression"])
api_router.include_router(agent_metrics.router, tags=["AgentMetrics"])
api_router.include_router(contracts.router, tags=["Contracts"])

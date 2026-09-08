from __future__ import annotations

from fastapi import APIRouter

from web_api.routes import clients, health, intel, reports, scene, settings, tools, trackers, stream, assistant, maintenance, banking, application


def build_router() -> APIRouter:
    router = APIRouter()
    router.include_router(health.router)
    router.include_router(trackers.router)
    router.include_router(clients.router)
    router.include_router(reports.router)
    router.include_router(settings.router)
    router.include_router(tools.router)
    router.include_router(intel.router)
    router.include_router(scene.router)
    router.include_router(stream.router)
    router.include_router(assistant.router)
    router.include_router(maintenance.router)
    router.include_router(banking.router)
    router.include_router(application.router)
    return router

from fastapi import FastAPI

from app.api.routers import (
    auth,
    candidates,
    catalogue_details,
    chat,
    health,
    institutions,
    programs,
    staff,
    visitors,
)


def create_app() -> FastAPI:
    app = FastAPI(
        title="SmartCampus AI — Backend API",
        version="0.5.0",
        description=(
            "Backend API for IIT/ISB university orientation. "
            "Public catalogue exposes only published programmes and independently verified details. "
            "Staff and candidate identities use separate bearer sessions and role permissions. "
            "Anonymous visitor chat remains available without an account. "
            "Full RAG, voice and official admission decisions are not yet implemented."
        ),
    )
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(institutions.router, prefix="/api/v1")
    app.include_router(programs.router, prefix="/api/v1")
    app.include_router(programs.admin_router, prefix="/api/v1")
    app.include_router(visitors.router, prefix="/api/v1")
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(staff.router, prefix="/api/v1")
    app.include_router(catalogue_details.public, prefix="/api/v1")
    app.include_router(catalogue_details.admin, prefix="/api/v1")
    app.include_router(candidates.router, prefix="/api/v1")
    return app


app = create_app()

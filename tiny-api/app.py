"""FastAPI application wiring for the HappyRobot carrier demo API."""
from __future__ import annotations

from fastapi import FastAPI

from database import initialize_database
from logging_utils import get_uvicorn_logger
from routers.dashboard import router as dashboard_router
from routers.loads import router as loads_router
from routers.negotiations import router as negotiations_router


logger = get_uvicorn_logger("app")

app = FastAPI(title="HappyRobot Carrier Demo API")


@app.on_event("startup")
def _ensure_database() -> None:
    """Initialize the SQLite database before serving requests."""

    logger.info("Starting application startup")
    initialize_database()
    logger.info("Database initialized and application startup complete")


app.include_router(loads_router)
app.include_router(negotiations_router)
app.include_router(dashboard_router)

"""FastAPI application that returns example loads for carriers."""
from __future__ import annotations

import os
import random
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from database import (
    fetch_all_loads,
    fetch_negotiation_events,
    initialize_database,
    record_negotiation_event,
)

app = FastAPI(title="HappyRobot Carrier Demo API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _ensure_database() -> None:
    """Initialize the SQLite database before serving requests."""
    initialize_database()

API_KEY_HEADER_NAME = "X-API-Key"
DEFAULT_API_KEY = "local-dev-api-key"
api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)


def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    """Ensure the caller supplied the expected API key."""
    expected_key = os.getenv("DEMO_API_KEY", DEFAULT_API_KEY)
    if not api_key or api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key


class CarrierRequest(BaseModel):
    """Incoming request describing the carrier's location and equipment."""

    origin: str = Field(..., description="Carrier origin in 'City, ST' format")
    equipment_type: str = Field(..., description="Requested equipment type")


class NegotiationEventRequest(BaseModel):
    """Payload describing a single negotiation interaction."""

    load_accepted: str | bool = Field(
        ..., description="Whether the load was accepted (expected 'true' or 'false')."
    )
    posted_price: str | float | int = Field(
        ..., description="Initial price shown to the carrier."
    )
    final_price: str | float | int = Field(
        ..., description="Final agreed price after negotiation."
    )
    total_negotiations: str | int = Field(
        ..., description="How many negotiation rounds occurred (stringified number)."
    )
    call_sentiment: str = Field(..., description="Overall sentiment from the call transcript.")
    commodity: str = Field(..., description="Commodity associated with the load.")


class NegotiationEvent(BaseModel):
    """Normalized negotiation event returned to dashboard clients."""

    load_accepted: bool
    posted_price: float
    final_price: float
    total_negotiations: int
    call_sentiment: str
    commodity: str
    created_at: str


class LoadResponse(BaseModel):
    """Response payload describing a single load."""

    load_id: str
    origin: str
    destination: str
    pickup_datetime: str
    delivery_datetime: str
    equipment_type: str
    loadboard_rate: float
    notes: Optional[str] = None
    weight: int
    commodity_type: str
    num_of_pieces: int
    miles: int
    dimensions: str


def _extract_state(location: str) -> str:
    """Return the upper-cased state component of a `City, ST` string."""
    parts = [segment.strip() for segment in location.split(",") if segment.strip()]
    if not parts:
        return ""
    return parts[-1].upper()


def _normalize_equipment(equipment: str) -> str:
    return equipment.strip().lower()


def _select_load(
    loads: List[Dict[str, Any]], origin_state: str, equipment: str
) -> Optional[Dict[str, Any]]:
    """Choose an appropriate load based on state and equipment preferences."""
    if not origin_state:
        return None

    state_matches = [load for load in loads if _extract_state(load["origin"]) == origin_state]
    if not state_matches:
        return None

    equipment_matches = [
        load
        for load in state_matches
        if _normalize_equipment(load["equipment_type"]) == _normalize_equipment(equipment)
    ]

    candidates = equipment_matches or state_matches
    return random.choice(candidates)


@app.post("/loads/match", response_model=LoadResponse)
def match_load(request: CarrierRequest, api_key: str = Depends(verify_api_key)) -> LoadResponse:
    """Return a sample load that best matches the carrier request."""
    origin_state = _extract_state(request.origin)
    loads = [dict(row) for row in fetch_all_loads()]

    load = _select_load(loads, origin_state, request.equipment_type)
    if load is None:
        raise HTTPException(status_code=404, detail="No loads available for the provided origin")

    return LoadResponse(**load)


@app.post(
    "/loads/negotiations",
    status_code=status.HTTP_201_CREATED,
    summary="Record negotiation insights for dashboard analytics.",
)
def log_negotiation_event(
    payload: NegotiationEventRequest,
    api_key: str = Depends(verify_api_key),
) -> Dict[str, str]:
    """Persist a negotiation event so it can later power a dashboard."""

    normalized = {}
    for key, value in payload.model_dump().items():
        if isinstance(value, str):
            normalized[key] = value.strip()
        elif isinstance(value, bool):
            normalized[key] = "true" if value else "false"
        else:
            normalized[key] = str(value)

    normalized["load_accepted"] = normalized["load_accepted"].lower()
    normalized["created_at"] = datetime.now(timezone.utc).isoformat()

    record_negotiation_event(normalized)

    return {"message": "Negotiation event recorded."}


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes", "y"}


def _as_float(value: str) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: str) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@app.get("/loads/negotiations", response_model=List[NegotiationEvent])
def list_negotiation_events(
    api_key: str = Depends(verify_api_key),
) -> List[NegotiationEvent]:
    """Return the negotiation history with normalized types."""

    events: List[NegotiationEvent] = []
    for row in fetch_negotiation_events():
        posted_price = _as_float(row["posted_price"])
        final_price = _as_float(row["final_price"])
        total_negotiations = _as_int(row["total_negotiations"])

        if posted_price is None or final_price is None or total_negotiations is None:
            # Skip rows that cannot be safely represented in the response schema.
            continue

        events.append(
            NegotiationEvent(
                load_accepted=_as_bool(row["load_accepted"]),
                posted_price=posted_price,
                final_price=final_price,
                total_negotiations=total_negotiations,
                call_sentiment=row["call_sentiment"],
                commodity=row["commodity"],
                created_at=row["created_at"],
            )
        )

    return events


BASE_DIR = Path(__file__).resolve().parent


@lru_cache()
def _dashboard_html() -> str:
    dashboard_path = BASE_DIR / "static" / "dashboard.html"
    return dashboard_path.read_text(encoding="utf-8")


@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard() -> HTMLResponse:
    """Serve the lightweight negotiation analytics dashboard."""

    return HTMLResponse(content=_dashboard_html())

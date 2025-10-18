"""FastAPI application that returns example loads for carriers."""
from __future__ import annotations

import os
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from database import fetch_all_loads, initialize_database, record_negotiation_event

app = FastAPI(title="HappyRobot Carrier Demo API")


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

    load_accepted: str = Field(
        ..., description="Whether the load was accepted (expected 'true' or 'false')."
    )
    posted_price: str = Field(..., description="Initial price shown to the carrier.")
    final_price: str = Field(..., description="Final agreed price after negotiation.")
    total_negotiations: str = Field(
        ..., description="How many negotiation rounds occurred (stringified number)."
    )
    call_sentiment: str = Field(..., description="Overall sentiment from the call transcript.")
    commodity: str = Field(..., description="Commodity associated with the load.")


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

    normalized = {
        key: value.strip()
        for key, value in payload.model_dump().items()
    }
    normalized["load_accepted"] = normalized["load_accepted"].lower()
    normalized["created_at"] = datetime.now(timezone.utc).isoformat()

    record_negotiation_event(normalized)

    return {"message": "Negotiation event recorded."}

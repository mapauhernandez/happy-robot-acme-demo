"""Endpoints for matching available loads to carriers."""
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from database import fetch_all_loads
from schemas import CarrierRequest, LoadResponse
from security import verify_api_key

router = APIRouter(prefix="/loads", tags=["loads"])


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


@router.post("/match", response_model=LoadResponse)
def match_load(
    request: CarrierRequest, api_key: str = Depends(verify_api_key)
) -> LoadResponse:
    """Return a sample load that best matches the carrier request."""
    origin_state = _extract_state(request.origin)
    loads = [dict(row) for row in fetch_all_loads()]

    load = _select_load(loads, origin_state, request.equipment_type)
    if load is None:
        raise HTTPException(status_code=404, detail="No loads available for the provided origin")

    return LoadResponse(**load)

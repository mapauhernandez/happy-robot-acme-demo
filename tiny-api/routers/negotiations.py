"""Endpoints for recording and retrieving negotiation outcomes."""
from __future__ import annotations

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, status

from database import fetch_all_negotiations, insert_negotiation
from schemas import NegotiationRecord, NegotiationRequest
from security import verify_api_key

router = APIRouter(prefix="/negotiations", tags=["negotiations"])


@router.post("", response_model=NegotiationRecord, status_code=status.HTTP_201_CREATED)
def create_negotiation(
    request: NegotiationRequest, api_key: str = Depends(verify_api_key)
) -> NegotiationRecord:
    """Persist a negotiation outcome supplied by the caller."""

    created_at = datetime.utcnow().replace(microsecond=0)
    row_id = insert_negotiation(
        {
            "load_accepted": 1 if request.load_accepted else 0,
            "posted_price": request.posted_price,
            "final_price": request.final_price,
            "total_negotiations": request.total_negotiations,
            "call_sentiment": request.call_sentiment,
            "commodity": request.commodity,
            "created_at": created_at.isoformat(),
        }
    )

    return NegotiationRecord(id=row_id, created_at=created_at, **request.model_dump())


@router.get("", response_model=List[NegotiationRecord])
def list_negotiations(api_key: str = Depends(verify_api_key)) -> List[NegotiationRecord]:
    """Return all recorded negotiation outcomes."""

    records: List[NegotiationRecord] = []
    for row in fetch_all_negotiations():
        created_at = datetime.fromisoformat(row["created_at"])
        records.append(
            NegotiationRecord(
                id=row["id"],
                created_at=created_at,
                load_accepted=bool(row["load_accepted"]),
                posted_price=row["posted_price"],
                final_price=row["final_price"],
                total_negotiations=row["total_negotiations"],
                call_sentiment=row["call_sentiment"],
                commodity=row["commodity"],
            )
        )
    return records

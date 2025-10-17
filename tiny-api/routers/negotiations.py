"""Endpoints for recording and retrieving negotiation outcomes."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from database import fetch_all_negotiations, insert_negotiation
from schemas import NegotiationRecord, NegotiationRequest
from security import verify_api_key

router = APIRouter(prefix="/negotiations", tags=["negotiations"])


def _get_logger() -> logging.Logger:
    """Return a logger wired to uvicorn's console handler."""

    base_logger = logging.getLogger("uvicorn.error")
    # Fallback to the root logger if uvicorn hasn't set up logging yet.
    if not base_logger.handlers:
        base_logger = logging.getLogger()
    child = base_logger.getChild("negotiations")
    child.setLevel(logging.INFO)
    return child


logger = _get_logger()


@router.post("", response_model=NegotiationRecord, status_code=status.HTTP_201_CREATED)
def create_negotiation(
    request: NegotiationRequest, api_key: str = Depends(verify_api_key)
) -> NegotiationRecord:
    """Persist a negotiation outcome supplied by the caller."""

    payload = request.model_dump()
    logger.info("Received negotiation submission", extra={"payload": payload})

    created_at = datetime.utcnow().replace(microsecond=0)
    try:
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
    except Exception as exc:  # pragma: no cover - diagnostic path
        logger.exception("Negotiation insert failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record negotiation: {exc}",
        ) from exc

    logger.info(
        "Negotiation stored",
        extra={
            "row_id": row_id,
            "created_at": created_at.isoformat(),
            "load_accepted": payload["load_accepted"],
            "final_price": payload["final_price"],
        },
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

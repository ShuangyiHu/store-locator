from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.rate_limiter import public_rate_limit
from app.database import get_db
from app.schemas.store import SearchRequest, SearchResponse
from app.services import store_service

router = APIRouter()


@router.post(
    "/search",
    response_model=SearchResponse,
    dependencies=[Depends(public_rate_limit)],
)
def search_stores(
    payload: SearchRequest,
    db: Session = Depends(get_db),
) -> SearchResponse:
    try:
        return store_service.search_stores(db, payload)
    except store_service.LocationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

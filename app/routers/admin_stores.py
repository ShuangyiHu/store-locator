from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.database import get_db
from app.models.role import Permissions
from app.models.store import StoreStatus
from app.models.user import User
from app.schemas.common import CSVImportReport, PaginatedResponse
from app.schemas.store import StoreCreate, StoreResponse, StoreUpdate
from app.services import csv_service, store_service

router = APIRouter()


@router.post(
    "",
    response_model=StoreResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_store(
    payload: StoreCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission(Permissions.STORE_CREATE)),
) -> StoreResponse:
    try:
        store = store_service.create_store(db, payload)
    except store_service.DuplicateStoreError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except store_service.LocationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return StoreResponse.from_store(store)


@router.get("", response_model=PaginatedResponse[StoreResponse])
def list_stores(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission(Permissions.STORE_READ)),
) -> PaginatedResponse[StoreResponse]:
    parsed_status: StoreStatus | None = None
    if status_filter is not None:
        try:
            parsed_status = StoreStatus(status_filter)
        except ValueError:
            valid = sorted(s.value for s in StoreStatus)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"status must be one of {valid}",
            )

    items, total = store_service.list_stores(db, page, page_size, parsed_status)
    return PaginatedResponse[StoreResponse](
        page=page,
        page_size=page_size,
        total=total,
        items=[StoreResponse.from_store(s) for s in items],
    )


@router.get("/{store_id}", response_model=StoreResponse)
def get_store(
    store_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission(Permissions.STORE_READ)),
) -> StoreResponse:
    store = store_service.get_store(db, store_id)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Store {store_id} not found",
        )
    return StoreResponse.from_store(store)


@router.patch("/{store_id}", response_model=StoreResponse)
def update_store(
    store_id: str,
    payload: StoreUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission(Permissions.STORE_UPDATE)),
) -> StoreResponse:
    store = store_service.partial_update_store(db, store_id, payload)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Store {store_id} not found",
        )
    return StoreResponse.from_store(store)


@router.delete("/{store_id}")
def deactivate_store(
    store_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission(Permissions.STORE_DELETE)),
) -> Response:
    if not store_service.soft_delete_store(db, store_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Store {store_id} not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/import", response_model=CSVImportReport)
async def import_stores_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission(Permissions.STORE_IMPORT)),
) -> CSVImportReport:
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a .csv",
        )
    content = await file.read()
    try:
        return csv_service.import_stores_from_csv(db, content)
    except csv_service.CSVStructureError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.database import get_db
from app.models.role import Permissions
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.services import user_service

router = APIRouter()


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _actor: User = Depends(require_permission(Permissions.USER_MANAGE)),
) -> UserResponse:
    try:
        user = user_service.create_user(db, payload)
    except user_service.DuplicateEmailError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email {exc} already exists",
        )
    except user_service.InvalidRoleError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return UserResponse.model_validate(user)


@router.get("", response_model=PaginatedResponse[UserResponse])
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _actor: User = Depends(require_permission(Permissions.USER_MANAGE)),
) -> PaginatedResponse[UserResponse]:
    items, total = user_service.list_users(db, page, page_size)
    return PaginatedResponse[UserResponse](
        page=page,
        page_size=page_size,
        total=total,
        items=[UserResponse.model_validate(u) for u in items],
    )


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _actor: User = Depends(require_permission(Permissions.USER_MANAGE)),
) -> UserResponse:
    user = user_service.get_user(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )
    return UserResponse.model_validate(user)


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permissions.USER_MANAGE)),
) -> UserResponse:
    try:
        user = user_service.update_user(db, user_id, payload, actor)
    except user_service.InvalidRoleError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except user_service.CannotModifySelfError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )
    return UserResponse.model_validate(user)


@router.delete("/{user_id}")
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permissions.USER_MANAGE)),
) -> Response:
    try:
        ok = user_service.soft_delete_user(db, user_id, actor)
    except user_service.CannotModifySelfError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

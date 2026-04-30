from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshRequest,
)
from app.schemas.user import UserResponse
from app.services import auth_service

router = APIRouter()

@router.post("/login/swagger", include_in_schema=False)
def login_swagger(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> LoginResponse:
    """Swagger Authorize button compatibility — same logic, form-encoded input."""
    settings = get_settings()
    try:
        user, access_token, refresh_token = auth_service.login(
            db, form_data.username, form_data.password
        )
    except auth_service.InvalidCredentialsError:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    except auth_service.InactiveUserError:
        raise HTTPException(status_code=401, detail="Account is inactive")

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserResponse.model_validate(user),
    )
    
@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    settings = get_settings()
    try:
        user, access_token, refresh_token = auth_service.login(
            db, str(payload.email), payload.password
        )
    except auth_service.InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    except auth_service.InactiveUserError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is inactive",
        )

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserResponse.model_validate(user),
    )


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> AccessTokenResponse:
    settings = get_settings()
    try:
        _user, access_token = auth_service.refresh_access_token(db, payload.refresh_token)
    except auth_service.InvalidRefreshTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    return AccessTokenResponse(
        access_token=access_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/logout")
def logout(payload: LogoutRequest, db: Session = Depends(get_db)) -> Response:
    auth_service.logout(db, payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

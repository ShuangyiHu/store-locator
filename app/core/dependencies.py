from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core import security
from app.database import get_db
from app.models.user import User, UserStatus

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login/swagger")

_CREDENTIALS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = security.decode_access_token(token)
    except jwt.InvalidTokenError:
        raise _CREDENTIALS_EXC

    sub = payload.get("sub")
    if sub is None:
        raise _CREDENTIALS_EXC

    user = db.get(User, int(sub))
    if user is None or user.status != UserStatus.ACTIVE:
        raise _CREDENTIALS_EXC

    return user

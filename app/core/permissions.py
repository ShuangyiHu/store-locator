from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from app.core.dependencies import get_current_user
from app.models.user import User


def require_permission(permission: str) -> Callable[[User], User]:
    """Build a FastAPI dependency that ensures the current user has `permission`.

    Usage:
        @router.post("/", dependencies=[Depends(require_permission(Permissions.STORE_CREATE))])

    Or to inject the user:
        def handler(user: User = Depends(require_permission("store:create"))):
    """

    def dependency(user: User = Depends(get_current_user)) -> User:
        granted = {p.name for p in user.role.permissions}
        if permission not in granted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission}",
            )
        return user

    return dependency

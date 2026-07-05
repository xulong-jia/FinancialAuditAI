from collections.abc import Callable

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.services import auth_service


def current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    user_id = auth_service.parse_access_token(authorization.split(" ", 1)[1].strip())
    return auth_service.get_user(db, user_id)


def require_permission(permission: str) -> Callable:
    def dependency(user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
        permissions = auth_service.user_permissions(db, user)
        if "*" in permissions or permission in permissions:
            return user
        raise HTTPException(status_code=403, detail="Permission denied")

    return dependency


RequireRead = Depends(require_permission("read"))

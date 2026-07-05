from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, RoleCreate, RoleRead, RoleUpdate, TokenRead, UserCreate, UserRead, UserUpdate
from app.schemas.review import AuditLogRead
from app.services import auth_service

router = APIRouter(tags=["auth"])


def _first_user_or_admin(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    if db.scalar(select(User.id).limit(1)) is None:
        return None
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    user_id = auth_service.parse_access_token(authorization.split(" ", 1)[1].strip())
    user = auth_service.get_user(db, user_id)
    permissions = auth_service.user_permissions(db, user)
    if "*" not in permissions and "user:manage" not in permissions:
        raise HTTPException(status_code=403, detail="Permission denied")
    return user


@router.post("/auth/login", response_model=TokenRead)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    _, token = auth_service.authenticate(db, payload.email, payload.password)
    return TokenRead(access_token=token)


@router.get("/auth/me", response_model=UserRead)
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return auth_service.user_read(user, db)


@router.post("/auth/logout")
def logout() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/users", response_model=list[UserRead], dependencies=[Depends(require_permission("user:manage"))])
def list_users(db: Session = Depends(get_db)):
    return auth_service.list_users(db)


@router.post("/users", response_model=UserRead)
def create_user(payload: UserCreate, db: Session = Depends(get_db), user: User | None = Depends(_first_user_or_admin)):
    created = auth_service.create_user(db, payload)
    return auth_service.user_read(created, db)


@router.patch("/users/{user_id}", response_model=UserRead, dependencies=[Depends(require_permission("user:manage"))])
def update_user(user_id: UUID, payload: UserUpdate, db: Session = Depends(get_db)):
    updated = auth_service.update_user(db, user_id, payload)
    return auth_service.user_read(updated, db)


@router.get("/roles", response_model=list[RoleRead], dependencies=[Depends(require_permission("user:manage"))])
def list_roles(db: Session = Depends(get_db)):
    return auth_service.list_roles(db)


@router.post("/roles", response_model=RoleRead, dependencies=[Depends(require_permission("user:manage"))])
def create_role(payload: RoleCreate, db: Session = Depends(get_db)):
    return auth_service.create_role(db, payload)


@router.patch("/roles/{role_id}", response_model=RoleRead, dependencies=[Depends(require_permission("user:manage"))])
def update_role(role_id: UUID, payload: RoleUpdate, db: Session = Depends(get_db)):
    return auth_service.update_role(db, role_id, payload)


@router.get("/audit-logs", response_model=list[AuditLogRead], dependencies=[Depends(require_permission("audit_log:read"))])
def list_audit_logs(limit: int = 200, db: Session = Depends(get_db)):
    return auth_service.list_audit_logs(db, limit)

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from secrets import token_bytes
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import redact
from app.models.audit_log import AuditLog
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole
from app.schemas.auth import RoleCreate, RoleUpdate, UserCreate, UserUpdate

ROLE_SEEDS: dict[str, tuple[str, list[str]]] = {
    "viewer": ("Viewer", ["read"]),
    "analyst": ("Analyst", ["read", "task:create", "task:update", "document:upload", "document:process", "audit:run", "agent:run"]),
    "reviewer": ("Reviewer", ["read", "review:write", "audit:run"]),
    "manager": ("Manager", ["read", "report:generate", "evaluation:read", "audit_log:read"]),
    "admin": ("Admin", ["*"]),
}
ITERATIONS = 120_000


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_default_roles(db: Session) -> None:
    existing = {role.code for role in db.scalars(select(Role))}
    for code, (name, permissions) in ROLE_SEEDS.items():
        if code in existing:
            continue
        db.add(Role(code=code, name=name, description=f"Default {name.lower()} role", permissions=permissions))
    db.commit()


def authenticate(db: Session, email: str, password: str) -> tuple[User, str]:
    ensure_default_roles(db)
    user = db.scalar(select(User).where(User.email == email.casefold()))
    if user is None or user.status != "active" or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user.last_login_at = utc_now()
    db.commit()
    return user, create_access_token(user)


def create_user(db: Session, payload: UserCreate) -> User:
    ensure_default_roles(db)
    if "@" not in payload.email:
        raise HTTPException(status_code=400, detail="Invalid email")
    email = payload.email.casefold()
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(status_code=400, detail="User already exists")
    first_user = db.scalar(select(User.id).limit(1)) is None
    role_codes = payload.role_codes or (["admin"] if first_user else ["viewer"])
    roles = _roles_by_code(db, role_codes)
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        organization=payload.organization,
        title=payload.title,
        status=payload.status,
    )
    db.add(user)
    db.flush()
    for role in roles:
        db.add(UserRole(user_id=user.id, role_id=role.id))
    _add_log(db, "system", "user_created", "user", user.id, None, {"email": user.email, "role_codes": role_codes})
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user_id: UUID, payload: UserUpdate) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    before = user_read(user, db)
    values = payload.model_dump(exclude_unset=True)
    if "password" in values and values["password"] is not None:
        user.password_hash = hash_password(values.pop("password"))
    for key in ("full_name", "organization", "title", "status"):
        if key in values:
            setattr(user, key, values[key])
    if payload.role_codes is not None:
        db.query(UserRole).filter(UserRole.user_id == user.id).delete()
        for role in _roles_by_code(db, payload.role_codes):
            db.add(UserRole(user_id=user.id, role_id=role.id))
    user.updated_at = utc_now()
    db.flush()
    after = user_read(user, db)
    _add_log(db, "system", "user_updated", "user", user.id, before, after)
    db.commit()
    db.refresh(user)
    return user


def list_users(db: Session) -> list[dict]:
    ensure_default_roles(db)
    return [user_read(user, db) for user in db.scalars(select(User).order_by(User.email.asc()))]


def get_user(db: Session, user_id: UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="User is disabled")
    return user


def user_read(user: User, db: Session) -> dict:
    roles = user_roles(db, user.id)
    permissions = sorted({permission for role in roles for permission in (role.permissions or [])})
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "organization": user.organization,
        "title": user.title,
        "status": user.status,
        "role_codes": [role.code for role in roles],
        "permissions": permissions,
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def user_permissions(db: Session, user: User) -> set[str]:
    return {permission for role in user_roles(db, user.id) for permission in (role.permissions or [])}


def user_roles(db: Session, user_id: UUID) -> list[Role]:
    return list(
        db.scalars(
            select(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
            .order_by(Role.code.asc())
        )
    )


def list_roles(db: Session) -> list[Role]:
    ensure_default_roles(db)
    return list(db.scalars(select(Role).order_by(Role.code.asc())))


def create_role(db: Session, payload: RoleCreate) -> Role:
    ensure_default_roles(db)
    if db.scalar(select(Role).where(Role.code == payload.code)) is not None:
        raise HTTPException(status_code=400, detail="Role already exists")
    role = Role(**payload.model_dump())
    db.add(role)
    db.flush()
    _add_log(db, "system", "role_created", "role", role.id, None, _role_snapshot(role))
    db.commit()
    db.refresh(role)
    return role


def update_role(db: Session, role_id: UUID, payload: RoleUpdate) -> Role:
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    before = _role_snapshot(role)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(role, key, value)
    role.updated_at = utc_now()
    after = _role_snapshot(role)
    _add_log(db, "system", "role_updated", "role", role.id, before, after)
    db.commit()
    db.refresh(role)
    return role


def list_audit_logs(db: Session, limit: int = 200) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500))))


def hash_password(password: str) -> str:
    salt = token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        ITERATIONS,
        base64.urlsafe_b64encode(salt).decode(),
        base64.urlsafe_b64encode(digest).decode(),
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, iterations, salt_b64, digest_b64 = password_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(digest_b64.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def create_access_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "exp": int((utc_now() + timedelta(minutes=settings.access_token_minutes)).timestamp()),
    }
    payload_part = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = _sign(payload_part)
    return f"{payload_part}.{signature}"


def parse_access_token(token: str) -> UUID:
    try:
        payload_part, signature = token.split(".", 1)
        if not hmac.compare_digest(_sign(payload_part), signature):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(_pad(payload_part)).decode())
        if int(payload["exp"]) < int(utc_now().timestamp()):
            raise HTTPException(status_code=401, detail="Token expired")
        return UUID(str(payload["sub"]))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


def _roles_by_code(db: Session, role_codes: list[str]) -> list[Role]:
    ensure_default_roles(db)
    roles = list(db.scalars(select(Role).where(Role.code.in_(role_codes))))
    found = {role.code for role in roles}
    missing = set(role_codes) - found
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown role: {sorted(missing)[0]}")
    return roles


def _role_snapshot(role: Role) -> dict:
    return {
        "id": str(role.id),
        "code": role.code,
        "name": role.name,
        "description": role.description,
        "permissions": role.permissions or [],
    }


def _add_log(
    db: Session,
    actor_name: str | None,
    action: str,
    target_type: str,
    target_id: UUID | None,
    before_value: dict | None,
    after_value: dict | None,
) -> None:
    db.add(
        AuditLog(
            actor_name=actor_name,
            task_id=None,
            action=action,
            target_type=target_type,
            target_id=target_id,
            before_value=redact(before_value),
            after_value=redact(after_value),
        )
    )


def _sign(payload_part: str) -> str:
    digest = hmac.new(settings.auth_secret_key.encode(), payload_part.encode(), hashlib.sha256).digest()
    return _b64(digest)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _pad(value: str) -> bytes:
    return (value + "=" * (-len(value) % 4)).encode()

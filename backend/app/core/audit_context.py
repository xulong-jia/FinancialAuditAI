from contextvars import ContextVar, Token
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class AuditContext:
    user_id: UUID | None = None
    ip_address: str | None = None
    user_agent: str | None = None


_context: ContextVar[AuditContext] = ContextVar("audit_context", default=AuditContext())


def get_audit_context() -> AuditContext:
    return _context.get()


def set_audit_context(
    *, user_id: UUID | None = None, ip_address: str | None = None, user_agent: str | None = None
) -> Token[AuditContext]:
    return _context.set(AuditContext(user_id=user_id, ip_address=ip_address, user_agent=user_agent))


def set_audit_user(user_id: UUID) -> None:
    current = _context.get()
    _context.set(AuditContext(user_id=user_id, ip_address=current.ip_address, user_agent=current.user_agent))


def reset_audit_context(token: Token[AuditContext]) -> None:
    _context.reset(token)

from __future__ import annotations

from datetime import datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from color_rush.config import Settings
from color_rush.domain.enums import AdminRole
from color_rush.domain.errors import AuthError, ConflictError, ForbiddenError, NotFoundError
from color_rush.infrastructure.persistence.models import AdminAction, AdminSession, AdminUser
from color_rush.infrastructure.security import (
    create_access_token,
    hash_password,
    hash_secret,
    new_token,
    verify_password,
)

WRITE_ROLES = {
    "sessions.write": {AdminRole.OWNER, AdminRole.ADMIN},
    "rounds.write": {AdminRole.OWNER, AdminRole.ADMIN},
    "pause": {AdminRole.OWNER, AdminRole.ADMIN, AdminRole.MODERATOR},
    "moderation": {AdminRole.OWNER, AdminRole.ADMIN, AdminRole.MODERATOR},
    "settings": {AdminRole.OWNER},
    "seasons": {AdminRole.OWNER},
    "users": {AdminRole.OWNER},
    "delete": {AdminRole.OWNER},
    "youtube": {AdminRole.OWNER, AdminRole.ADMIN},
    "overlay": {AdminRole.OWNER, AdminRole.ADMIN},
    "audit.read": {AdminRole.OWNER, AdminRole.ADMIN, AdminRole.MODERATOR, AdminRole.OBSERVER},
}


def require_role(role: AdminRole, permission: str) -> None:
    allowed = WRITE_ROLES.get(permission)
    if allowed is None or role not in allowed:
        raise ForbiddenError("insufficient role")


def bootstrap_owner(session: Session, settings: Settings, now: datetime) -> AdminUser:
    existing = session.scalar(select(AdminUser))
    if existing is not None:
        return cast(AdminUser, existing)
    user = AdminUser(
        id=uuid4(),
        username=settings.bootstrap_owner_username,
        password_hash=hash_password(settings.bootstrap_owner_password),
        role=AdminRole.OWNER.value,
        created_at=now,
        revoked_at=None,
    )
    session.add(user)
    session.flush()
    return user


def login(
    session: Session,
    settings: Settings,
    *,
    username: str,
    password: str,
    now: datetime,
) -> tuple[str, str, AdminUser]:
    user = session.scalar(select(AdminUser).where(AdminUser.username == username))
    if user is None or user.revoked_at is not None or not verify_password(password, user.password_hash):
        raise AuthError("invalid credentials")
    refresh = new_token()
    row = AdminSession(
        id=uuid4(),
        user_id=user.id,
        refresh_token_hash=hash_secret(refresh),
        expires_at=now + timedelta(seconds=settings.jwt_refresh_ttl_seconds),
        revoked_at=None,
        created_at=now,
    )
    session.add(row)
    access = create_access_token(
        secret_key=settings.secret_key,
        user_id=user.id,
        role=AdminRole(user.role),
        ttl_seconds=settings.jwt_access_ttl_seconds,
        now=now,
    )
    return access, refresh, user


def refresh_tokens(
    session: Session,
    settings: Settings,
    refresh_token: str,
    now: datetime,
) -> tuple[str, str, AdminUser]:
    hashed = hash_secret(refresh_token)
    row = session.scalar(select(AdminSession).where(AdminSession.refresh_token_hash == hashed))
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        raise AuthError("refresh token expired or revoked")
    user = session.get(AdminUser, row.user_id)
    if user is None or user.revoked_at is not None:
        raise AuthError("account revoked")
    row.revoked_at = now
    return _issue(session, settings, user, now)


def _issue(session: Session, settings: Settings, user: AdminUser, now: datetime) -> tuple[str, str, AdminUser]:
    refresh = new_token()
    session.add(
        AdminSession(
            id=uuid4(),
            user_id=user.id,
            refresh_token_hash=hash_secret(refresh),
            expires_at=now + timedelta(seconds=settings.jwt_refresh_ttl_seconds),
            revoked_at=None,
            created_at=now,
        )
    )
    access = create_access_token(
        secret_key=settings.secret_key,
        user_id=user.id,
        role=AdminRole(user.role),
        ttl_seconds=settings.jwt_access_ttl_seconds,
        now=now,
    )
    return access, refresh, user


def logout(session: Session, refresh_token: str, now: datetime) -> None:
    hashed = hash_secret(refresh_token)
    row = session.scalar(select(AdminSession).where(AdminSession.refresh_token_hash == hashed))
    if row is not None:
        row.revoked_at = now


def record_admin_action(
    session: Session,
    *,
    actor_id: UUID,
    action: str,
    request_id: str | None,
    reason: str | None,
    before: dict[str, object] | None,
    after: dict[str, object] | None,
    now: datetime,
) -> None:
    if request_id:
        existing = session.scalar(select(AdminAction).where(AdminAction.request_id == request_id))
        if existing is not None:
            raise ConflictError("duplicate request_id")
    session.add(
        AdminAction(
            id=uuid4(),
            actor_id=actor_id,
            request_id=request_id,
            action=action,
            reason=reason,
            before_state=before,
            after_state=after,
            created_at=now,
        )
    )


def get_user(session: Session, user_id: UUID) -> AdminUser:
    user = session.get(AdminUser, user_id)
    if user is None or user.revoked_at is not None:
        raise NotFoundError("user not found")
    return user


def list_admin_users(session: Session) -> list[AdminUser]:
    return list(session.scalars(select(AdminUser).order_by(AdminUser.created_at.asc())))


def create_admin_user(
    session: Session,
    *,
    username: str,
    password: str,
    role: AdminRole,
    actor_id: UUID,
    now: datetime,
    request_id: str | None = None,
) -> AdminUser:
    existing = session.scalar(select(AdminUser).where(AdminUser.username == username))
    if existing is not None:
        raise ConflictError("username already exists")
    user = AdminUser(
        id=uuid4(),
        username=username,
        password_hash=hash_password(password),
        role=role.value,
        created_at=now,
        revoked_at=None,
    )
    session.add(user)
    record_admin_action(
        session,
        actor_id=actor_id,
        action="users.create",
        request_id=request_id,
        reason=None,
        before=None,
        after={"username": username, "role": role.value},
        now=now,
    )
    session.flush()
    return user

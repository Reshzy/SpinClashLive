from __future__ import annotations

WRITE_ROLES: dict[str, frozenset[str]] = {
    "sessions.write": frozenset({"owner", "admin"}),
    "rounds.write": frozenset({"owner", "admin"}),
    "pause": frozenset({"owner", "admin", "moderator"}),
    "moderation": frozenset({"owner", "admin", "moderator"}),
    "settings": frozenset({"owner"}),
    "seasons": frozenset({"owner"}),
    "users": frozenset({"owner"}),
    "delete": frozenset({"owner"}),
    "youtube": frozenset({"owner", "admin"}),
    "overlay": frozenset({"owner", "admin"}),
    "audit.read": frozenset({"owner", "admin", "moderator", "observer"}),
}


def can(role: str, permission: str) -> bool:
    allowed = WRITE_ROLES.get(permission)
    if allowed is None:
        return False
    return role in allowed

from __future__ import annotations

from typing import Any

from color_rush_desktop.api_client.errors import ApiError, TokenBundle
from color_rush_desktop.config import DesktopConfig


class KeyringStore:
    def __init__(self, config: DesktopConfig) -> None:
        self._service = config.keyring_service

    def save(self, bundle: TokenBundle, api_base: str) -> None:
        try:
            import keyring

            keyring.set_password(self._service, "refresh_token", bundle.refresh_token)
            keyring.set_password(self._service, "role", bundle.role)
            keyring.set_password(self._service, "user_id", bundle.user_id)
            keyring.set_password(self._service, "api_base", api_base)
        except Exception:
            return

    def load(self) -> dict[str, str] | None:
        try:
            import keyring

            refresh = keyring.get_password(self._service, "refresh_token")
        except Exception:
            return None
        if not refresh:
            return None
        try:
            import keyring

            return {
                "refresh_token": refresh,
                "role": keyring.get_password(self._service, "role") or "",
                "user_id": keyring.get_password(self._service, "user_id") or "",
                "api_base": keyring.get_password(self._service, "api_base") or "",
            }
        except Exception:
            return {"refresh_token": refresh, "role": "", "user_id": "", "api_base": ""}

    def clear(self) -> None:
        try:
            import keyring

            for key in ("refresh_token", "role", "user_id", "api_base"):
                try:
                    keyring.delete_password(self._service, key)
                except Exception:
                    continue
        except Exception:
            return


def redacted(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}…{value[-2:]}"


def safe_log_payload(payload: dict[str, Any]) -> dict[str, Any]:
    blocked = {"access_token", "refresh_token", "secret", "password", "authorization"}
    return {key: "***" if key.lower() in blocked else value for key, value in payload.items()}


def require_bundle(data: dict[str, Any]) -> TokenBundle:
    try:
        return TokenBundle(
            access_token=str(data["access_token"]),
            refresh_token=str(data["refresh_token"]),
            role=str(data["role"]),
            user_id=str(data["user_id"]),
            token_type=str(data.get("token_type") or "bearer"),
        )
    except KeyError as exc:
        raise ApiError("token response missing fields", code="auth_error") from exc

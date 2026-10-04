from __future__ import annotations

from contextlib import suppress
from typing import Any
from uuid import uuid4

import httpx

from color_rush_desktop.api_client.errors import ApiError, HttpJob, TokenBundle
from color_rush_desktop.api_client.keyring_store import require_bundle
from color_rush_desktop.config import DesktopConfig


class RestClient:
    def __init__(self, config: DesktopConfig, transport: httpx.BaseTransport | None = None) -> None:
        self.config = config
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self._transport = transport
        self._client = self._make_client()

    def _make_client(self) -> httpx.Client:
        if self._transport is not None:
            return httpx.Client(
                base_url=self.config.api_base,
                timeout=self.config.request_timeout_s,
                transport=self._transport,
            )
        return httpx.Client(base_url=self.config.api_base, timeout=self.config.request_timeout_s)

    def close(self) -> None:
        self._client.close()
        self._client = self._make_client()

    def set_tokens(self, bundle: TokenBundle) -> None:
        self.access_token = bundle.access_token
        self.refresh_token = bundle.refresh_token

    def clear_tokens(self) -> None:
        self.access_token = None
        self.refresh_token = None

    def login(self, username: str, password: str) -> TokenBundle:
        payload = self._send("POST", "/api/v1/auth/login", json_body={"username": username, "password": password})
        bundle = require_bundle(payload)
        self.set_tokens(bundle)
        return bundle

    def refresh(self) -> TokenBundle:
        if not self.refresh_token:
            raise ApiError("no refresh token", code="auth_error", status=401)
        payload = self._send("POST", "/api/v1/auth/refresh", json_body={"refresh_token": self.refresh_token})
        bundle = require_bundle(payload)
        self.set_tokens(bundle)
        return bundle

    def logout(self) -> None:
        if self.refresh_token:
            with suppress(ApiError):
                self._send("POST", "/api/v1/auth/logout", json_body={"refresh_token": self.refresh_token})
        self.clear_tokens()

    def execute(self, job: HttpJob) -> Any:
        body = dict(job.json_body or {})
        if job.expected_revision is not None and "expected_revision" not in body:
            body["expected_revision"] = job.expected_revision
        headers: dict[str, str] = {}
        if job.admin_write:
            headers["Idempotency-Key"] = str(uuid4())
        return self._send(
            job.method,
            job.path,
            json_body=body or None,
            params=job.params,
            headers=headers,
            auth=job.auth,
        )

    def _send(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        auth: bool = True,
        _retried: bool = False,
    ) -> Any:
        request_headers = dict(headers or {})
        if auth and self.access_token:
            request_headers["Authorization"] = f"Bearer {self.access_token}"
        try:
            response = self._client.request(method, path, json=json_body, params=params, headers=request_headers)
        except httpx.HTTPError as exc:
            raise ApiError(f"network error: {exc}", code="network_error", retry=True) from exc
        if response.status_code == 401 and auth and self.refresh_token and not _retried:
            self.refresh()
            return self._send(
                method,
                path,
                json_body=json_body,
                params=params,
                headers=headers,
                auth=auth,
                _retried=True,
            )
        if response.status_code >= 400:
            try:
                body: Any = response.json()
            except ValueError:
                body = {"message": response.text[:300]}
            raise ApiError.from_body(response.status_code, body)
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {"text": response.text}

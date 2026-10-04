from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from color_rush.application.youtube_oauth import sign_oauth_state, start_oauth, verify_oauth_state
from color_rush.config import Settings
from color_rush.domain.errors import ConfigurationError, InvalidCommandError


def test_oauth_state_roundtrip() -> None:
    now = datetime.now(tz=UTC)
    game_id = uuid4()
    user_id = uuid4()
    state = sign_oauth_state("secret-key", game_id=game_id, user_id=user_id, now=now)
    got_game, got_user = verify_oauth_state("secret-key", state, now)
    assert got_game == game_id
    assert got_user == user_id


def test_oauth_state_rejects_tampering_and_expiry() -> None:
    now = datetime.now(tz=UTC)
    state = sign_oauth_state("secret-key", game_id=uuid4(), user_id=uuid4(), now=now)
    with pytest.raises(InvalidCommandError):
        verify_oauth_state("other-secret", state, now)
    with pytest.raises(InvalidCommandError):
        verify_oauth_state("secret-key", state, now + timedelta(hours=2))
    with pytest.raises(InvalidCommandError):
        verify_oauth_state("secret-key", "not-a-state", now)


def test_oauth_start_requires_backend_client() -> None:
    settings = Settings(google_oauth_client_id="", google_oauth_client_secret="")
    with pytest.raises(ConfigurationError):
        start_oauth(settings, game_id=uuid4(), user_id=uuid4(), now=datetime.now(tz=UTC))


def test_oauth_start_builds_readonly_url() -> None:
    settings = Settings(
        google_oauth_client_id="client-id",
        google_oauth_client_secret="client-secret",
        google_oauth_redirect_uri="http://127.0.0.1:8000/api/v1/admin/youtube/oauth/callback",
    )
    payload = start_oauth(settings, game_id=uuid4(), user_id=uuid4(), now=datetime.now(tz=UTC))
    assert payload["authorization_url"].startswith("https://accounts.google.com/o/oauth2/v2/auth")
    assert "youtube.readonly" in payload["authorization_url"]
    assert "client-id" in payload["authorization_url"]
    assert payload["state"]

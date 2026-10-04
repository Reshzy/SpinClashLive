from datetime import UTC, datetime
from uuid import uuid4

import pytest

from color_rush.domain.enums import AdminRole
from color_rush.domain.errors import AuthError
from color_rush.infrastructure.redis.projections import decoded_score, encoded_score, sanitize_name
from color_rush.infrastructure.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_and_jwt_roundtrip() -> None:
    stored = hash_password("secret-pass")
    assert verify_password("secret-pass", stored)
    assert not verify_password("nope", stored)
    token = create_access_token(
        secret_key="k" * 32,
        user_id=uuid4(),
        role=AdminRole.OWNER,
        ttl_seconds=60,
        now=datetime.now(tz=UTC),
    )
    payload = decode_access_token("k" * 32, token)
    assert payload["role"] == "owner"
    with pytest.raises(AuthError):
        decode_access_token("other" * 8, token)


def test_tie_encoding_and_safe_names() -> None:
    assert encoded_score(14) == -14
    assert decoded_score(-14) == 14
    assert encoded_score(0) == 0
    assert sanitize_name("<script>Ada") == "scriptAda"
    assert len(sanitize_name("x" * 80)) == 24

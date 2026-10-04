"""Milestone 2 auth, overlay tickets, source health, and deletion fields.

Revision ID: 0002_m2_auth_source
Revises: 0001_initial
Create Date: 2026-10-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_m2_auth_source"
down_revision: str | None = "0001_initial"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE game_sessions
            ADD COLUMN last_help_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE source_checkpoints
            ADD COLUMN session_id UUID REFERENCES game_sessions(id),
            ADD COLUMN resync_required BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN error_class VARCHAR(32),
            ADD COLUMN lag_ms INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE players
            ADD COLUMN last_lookup_at TIMESTAMP WITH TIME ZONE,
            ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE,
            ADD COLUMN anonymized_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE leaderboard_scores
            ADD COLUMN score_version INTEGER NOT NULL DEFAULT 0
        """
    )
    op.execute(
        """
        CREATE TABLE overlay_tickets (
            id UUID NOT NULL,
            game_id UUID NOT NULL REFERENCES games(id),
            session_id UUID REFERENCES game_sessions(id),
            secret_hash VARCHAR(256) NOT NULL,
            label VARCHAR(80) NOT NULL DEFAULT 'overlay',
            revoked_at TIMESTAMP WITH TIME ZONE,
            expires_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE google_credentials (
            id UUID NOT NULL,
            game_id UUID NOT NULL REFERENCES games(id),
            auth_mode VARCHAR(16) NOT NULL,
            encrypted_payload TEXT NOT NULL,
            scopes VARCHAR(256) NOT NULL DEFAULT 'https://www.googleapis.com/auth/youtube.readonly',
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            revoked_at TIMESTAMP WITH TIME ZONE,
            PRIMARY KEY (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE idempotency_keys (
            key VARCHAR(128) NOT NULL,
            actor_id UUID NOT NULL REFERENCES admin_users(id),
            request_hash VARCHAR(64) NOT NULL,
            status_code INTEGER NOT NULL,
            response_json JSONB NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (key)
        )
        """
    )
    op.execute("CREATE INDEX ix_idempotency_expires ON idempotency_keys (expires_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS idempotency_keys")
    op.execute("DROP TABLE IF EXISTS google_credentials")
    op.execute("DROP TABLE IF EXISTS overlay_tickets")
    op.execute("ALTER TABLE leaderboard_scores DROP COLUMN IF EXISTS score_version")
    op.execute("ALTER TABLE players DROP COLUMN IF EXISTS last_lookup_at")
    op.execute("ALTER TABLE players DROP COLUMN IF EXISTS deleted_at")
    op.execute("ALTER TABLE players DROP COLUMN IF EXISTS anonymized_at")
    op.execute("ALTER TABLE source_checkpoints DROP COLUMN IF EXISTS session_id")
    op.execute("ALTER TABLE source_checkpoints DROP COLUMN IF EXISTS resync_required")
    op.execute("ALTER TABLE source_checkpoints DROP COLUMN IF EXISTS error_class")
    op.execute("ALTER TABLE source_checkpoints DROP COLUMN IF EXISTS lag_ms")
    op.execute("ALTER TABLE game_sessions DROP COLUMN IF EXISTS last_help_at")

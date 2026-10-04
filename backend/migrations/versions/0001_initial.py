"""Initial Color Rush Live schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE EXTENSION IF NOT EXISTS btree_gist
        """
    )
    op.execute(
        """
        CREATE TABLE admin_users (
        	id UUID NOT NULL, 
        	username VARCHAR(64) NOT NULL, 
        	password_hash VARCHAR(256) NOT NULL, 
        	role VARCHAR(32) NOT NULL, 
        	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	revoked_at TIMESTAMP WITH TIME ZONE, 
        	PRIMARY KEY (id), 
        	UNIQUE (username)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE games (
        	id UUID NOT NULL, 
        	name VARCHAR(120) NOT NULL, 
        	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	PRIMARY KEY (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE outbox_events (
        	id UUID NOT NULL, 
        	event_id UUID NOT NULL, 
        	aggregate_type VARCHAR(64) NOT NULL, 
        	aggregate_id UUID NOT NULL, 
        	aggregate_revision INTEGER NOT NULL, 
        	event_type VARCHAR(64) NOT NULL, 
        	schema_version INTEGER NOT NULL, 
        	payload JSONB NOT NULL, 
        	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	published_at TIMESTAMP WITH TIME ZONE, 
        	PRIMARY KEY (id), 
        	CONSTRAINT uq_outbox_event_id UNIQUE (event_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_outbox_pending ON outbox_events (published_at) WHERE published_at IS NULL
        """
    )
    op.execute(
        """
        CREATE TABLE players (
        	id UUID NOT NULL, 
        	provider VARCHAR(32) NOT NULL, 
        	provider_channel_id VARCHAR(128) NOT NULL, 
        	display_name VARCHAR(128) NOT NULL, 
        	avatar_ref VARCHAR(512), 
        	profile_refreshed_at TIMESTAMP WITH TIME ZONE, 
        	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	PRIMARY KEY (id), 
        	CONSTRAINT uq_players_provider_channel UNIQUE (provider, provider_channel_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE projection_jobs (
        	id UUID NOT NULL, 
        	job_key VARCHAR(160) NOT NULL, 
        	status VARCHAR(16) NOT NULL, 
        	attempts INTEGER NOT NULL, 
        	completed_watermark BIGINT NOT NULL, 
        	payload JSONB NOT NULL, 
        	PRIMARY KEY (id), 
        	CONSTRAINT uq_projection_job_key UNIQUE (job_key)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_projection_pending ON projection_jobs (status)
        """
    )
    op.execute(
        """
        CREATE TABLE source_checkpoints (
        	broadcast_id VARCHAR(128) NOT NULL, 
        	next_page_token VARCHAR(512), 
        	source_mode VARCHAR(32) NOT NULL, 
        	last_success_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	ownership_token VARCHAR(128) NOT NULL, 
        	PRIMARY KEY (broadcast_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE admin_actions (
        	id UUID NOT NULL, 
        	actor_id UUID NOT NULL, 
        	request_id VARCHAR(80), 
        	action VARCHAR(64) NOT NULL, 
        	reason TEXT, 
        	before_state JSONB, 
        	after_state JSONB, 
        	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	PRIMARY KEY (id), 
        	CONSTRAINT uq_admin_actions_request UNIQUE (request_id), 
        	FOREIGN KEY(actor_id) REFERENCES admin_users (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE admin_sessions (
        	id UUID NOT NULL, 
        	user_id UUID NOT NULL, 
        	refresh_token_hash VARCHAR(256) NOT NULL, 
        	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	revoked_at TIMESTAMP WITH TIME ZONE, 
        	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(user_id) REFERENCES admin_users (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE configuration_versions (
        	id UUID NOT NULL, 
        	game_id UUID NOT NULL, 
        	version INTEGER NOT NULL, 
        	configuration JSONB NOT NULL, 
        	activation_boundary VARCHAR(32) NOT NULL, 
        	actor_id UUID, 
        	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	PRIMARY KEY (id), 
        	CONSTRAINT uq_config_game_version UNIQUE (game_id, version), 
        	FOREIGN KEY(game_id) REFERENCES games (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE game_sessions (
        	id UUID NOT NULL, 
        	game_id UUID NOT NULL, 
        	broadcast_ref VARCHAR(128), 
        	live_chat_ref VARCHAR(128), 
        	mode VARCHAR(16) NOT NULL, 
        	paused BOOLEAN NOT NULL, 
        	config_version INTEGER NOT NULL, 
        	timezone_version VARCHAR(64) NOT NULL, 
        	active_round_id UUID, 
        	revision INTEGER NOT NULL, 
        	next_inbox_sequence BIGINT NOT NULL, 
        	next_round_bonus VARCHAR(32) NOT NULL, 
        	next_round_gold_bonus_reward INTEGER NOT NULL, 
        	source_mode VARCHAR(32) NOT NULL, 
        	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(game_id) REFERENCES games (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE player_moderation (
        	id UUID NOT NULL, 
        	player_id UUID NOT NULL, 
        	scope_key VARCHAR(160) NOT NULL, 
        	blocked BOOLEAN NOT NULL, 
        	reason TEXT, 
        	actor_id UUID, 
        	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	PRIMARY KEY (id), 
        	CONSTRAINT uq_moderation_player_scope UNIQUE (player_id, scope_key), 
        	FOREIGN KEY(player_id) REFERENCES players (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_moderation_scope_player ON player_moderation (scope_key, player_id)
        """
    )
    op.execute(
        """
        CREATE TABLE player_statistics (
        	id UUID NOT NULL, 
        	player_id UUID NOT NULL, 
        	game_id UUID NOT NULL, 
        	lifetime_points BIGINT NOT NULL, 
        	wins INTEGER NOT NULL, 
        	rounds_played INTEGER NOT NULL, 
        	current_streak INTEGER NOT NULL, 
        	best_streak INTEGER NOT NULL, 
        	gold_wins INTEGER NOT NULL, 
        	PRIMARY KEY (id), 
        	CONSTRAINT uq_stats_player_game UNIQUE (player_id, game_id), 
        	FOREIGN KEY(player_id) REFERENCES players (id), 
        	FOREIGN KEY(game_id) REFERENCES games (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE seasons (
        	id UUID NOT NULL, 
        	game_id UUID NOT NULL, 
        	name VARCHAR(120) NOT NULL, 
        	starts_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	ends_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	status VARCHAR(16) NOT NULL, 
        	during TSTZRANGE GENERATED ALWAYS AS (tstzrange(starts_at, ends_at, '[)')) STORED NOT NULL, 
        	PRIMARY KEY (id), 
        	CONSTRAINT ck_seasons_interval CHECK (ends_at > starts_at), 
        	CONSTRAINT ex_seasons_no_overlap EXCLUDE USING gist (game_id WITH =, during WITH &&), 
        	FOREIGN KEY(game_id) REFERENCES games (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_seasons_game_status ON seasons (game_id, status)
        """
    )
    op.execute(
        """
        CREATE TABLE coordinator_leases (
        	session_id UUID NOT NULL, 
        	owner_id VARCHAR(128) NOT NULL, 
        	fencing_token BIGINT NOT NULL, 
        	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	PRIMARY KEY (session_id), 
        	FOREIGN KEY(session_id) REFERENCES game_sessions (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE leaderboard_periods (
        	id UUID NOT NULL, 
        	game_id UUID NOT NULL, 
        	period_type VARCHAR(16) NOT NULL, 
        	starts_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	ends_at TIMESTAMP WITH TIME ZONE, 
        	timezone_version VARCHAR(64) NOT NULL, 
        	season_id UUID, 
        	status VARCHAR(16) NOT NULL, 
        	local_identity VARCHAR(64) NOT NULL, 
        	finalized_at TIMESTAMP WITH TIME ZONE, 
        	PRIMARY KEY (id), 
        	CONSTRAINT uq_period_logical_identity UNIQUE (game_id, period_type, local_identity, timezone_version), 
        	FOREIGN KEY(game_id) REFERENCES games (id), 
        	FOREIGN KEY(season_id) REFERENCES seasons (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_periods_game_type_status ON leaderboard_periods (game_id, period_type, status)
        """
    )
    op.execute(
        """
        CREATE TABLE rounds (
        	id UUID NOT NULL, 
        	session_id UUID NOT NULL, 
        	number INTEGER NOT NULL, 
        	state VARCHAR(16) NOT NULL, 
        	revision INTEGER NOT NULL, 
        	rules_snapshot JSONB NOT NULL, 
        	opened_at TIMESTAMP WITH TIME ZONE, 
        	scheduled_closes_at TIMESTAMP WITH TIME ZONE, 
        	closed_at TIMESTAMP WITH TIME ZONE, 
        	score_effective_at TIMESTAMP WITH TIME ZONE, 
        	cutoff_sequence BIGINT, 
        	result VARCHAR(16), 
        	result_draw INTEGER, 
        	presentation_plan JSONB, 
        	cancel_reason TEXT, 
        	drain_deadline_at TIMESTAMP WITH TIME ZONE, 
        	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	PRIMARY KEY (id), 
        	CONSTRAINT uq_rounds_session_number UNIQUE (session_id, number), 
        	FOREIGN KEY(session_id) REFERENCES game_sessions (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_rounds_session_state ON rounds (session_id, state)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_rounds_session_nonterminal ON rounds (session_id) WHERE state IN ('open','draining','locked','spinning','result','settling','settled')
        """
    )
    op.execute(
        """
        CREATE TABLE champion_awards (
        	id UUID NOT NULL, 
        	period_id UUID NOT NULL, 
        	award_type VARCHAR(32) NOT NULL, 
        	player_id UUID NOT NULL, 
        	display_title VARCHAR(160) NOT NULL, 
        	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	PRIMARY KEY (id), 
        	CONSTRAINT uq_champion_period_type UNIQUE (period_id, award_type), 
        	FOREIGN KEY(period_id) REFERENCES leaderboard_periods (id), 
        	FOREIGN KEY(player_id) REFERENCES players (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE command_inbox (
        	id UUID NOT NULL, 
        	session_id UUID NOT NULL, 
        	sequence BIGINT NOT NULL, 
        	provider VARCHAR(32) NOT NULL, 
        	provider_message_id VARCHAR(160) NOT NULL, 
        	broadcast_id VARCHAR(128) NOT NULL, 
        	candidate_round_id UUID, 
        	player_id UUID NOT NULL, 
        	command VARCHAR(16) NOT NULL, 
        	published_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	received_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	processing_status VARCHAR(16) NOT NULL, 
        	decision_reason VARCHAR(64) NOT NULL, 
        	PRIMARY KEY (id), 
        	CONSTRAINT uq_inbox_session_sequence UNIQUE (session_id, sequence), 
        	CONSTRAINT uq_inbox_provider_message UNIQUE (provider, broadcast_id, provider_message_id), 
        	CONSTRAINT ck_inbox_sequence_positive CHECK (sequence > 0), 
        	FOREIGN KEY(session_id) REFERENCES game_sessions (id), 
        	FOREIGN KEY(candidate_round_id) REFERENCES rounds (id), 
        	FOREIGN KEY(player_id) REFERENCES players (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_inbox_eligible ON command_inbox (session_id, processing_status, sequence)
        """
    )
    op.execute(
        """
        CREATE TABLE leaderboard_archives (
        	id UUID NOT NULL, 
        	period_id UUID NOT NULL, 
        	player_id UUID NOT NULL, 
        	final_rank INTEGER NOT NULL, 
        	points BIGINT NOT NULL, 
        	correct_picks INTEGER NOT NULL, 
        	rounds_played INTEGER NOT NULL, 
        	gold_wins INTEGER NOT NULL, 
        	best_streak INTEGER NOT NULL, 
        	PRIMARY KEY (id), 
        	CONSTRAINT uq_archive_period_player UNIQUE (period_id, player_id), 
        	FOREIGN KEY(period_id) REFERENCES leaderboard_periods (id), 
        	FOREIGN KEY(player_id) REFERENCES players (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE leaderboard_scores (
        	id UUID NOT NULL, 
        	period_id UUID NOT NULL, 
        	player_id UUID NOT NULL, 
        	points BIGINT NOT NULL, 
        	correct_picks INTEGER NOT NULL, 
        	rounds_played INTEGER NOT NULL, 
        	gold_wins INTEGER NOT NULL, 
        	best_streak INTEGER NOT NULL, 
        	PRIMARY KEY (id), 
        	CONSTRAINT uq_lb_score_period_player UNIQUE (period_id, player_id), 
        	FOREIGN KEY(period_id) REFERENCES leaderboard_periods (id), 
        	FOREIGN KEY(player_id) REFERENCES players (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_lb_scores_period_points_player ON leaderboard_scores (period_id, points, player_id)
        """
    )
    op.execute(
        """
        CREATE TABLE picks (
        	id UUID NOT NULL, 
        	round_id UUID NOT NULL, 
        	player_id UUID NOT NULL, 
        	choice VARCHAR(16) NOT NULL, 
        	last_sequence BIGINT NOT NULL, 
        	change_count INTEGER NOT NULL, 
        	first_received_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	PRIMARY KEY (id), 
        	CONSTRAINT uq_picks_round_player UNIQUE (round_id, player_id), 
        	FOREIGN KEY(round_id) REFERENCES rounds (id), 
        	FOREIGN KEY(player_id) REFERENCES players (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_picks_round_color ON picks (round_id, choice)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_picks_round_player ON picks (round_id, player_id)
        """
    )
    op.execute(
        """
        CREATE TABLE round_periods (
        	id UUID NOT NULL, 
        	round_id UUID NOT NULL, 
        	period_type VARCHAR(16) NOT NULL, 
        	period_id UUID NOT NULL, 
        	PRIMARY KEY (id), 
        	CONSTRAINT uq_round_period_type UNIQUE (round_id, period_type), 
        	FOREIGN KEY(round_id) REFERENCES rounds (id), 
        	FOREIGN KEY(period_id) REFERENCES leaderboard_periods (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE score_ledger (
        	id UUID NOT NULL, 
        	round_id UUID NOT NULL, 
        	player_id UUID NOT NULL, 
        	correct BOOLEAN NOT NULL, 
        	points_delta BIGINT NOT NULL, 
        	effective_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	rules_version INTEGER NOT NULL, 
        	PRIMARY KEY (id), 
        	CONSTRAINT uq_ledger_round_player UNIQUE (round_id, player_id), 
        	CONSTRAINT ck_ledger_points_nonnegative CHECK (points_delta >= 0), 
        	FOREIGN KEY(round_id) REFERENCES rounds (id), 
        	FOREIGN KEY(player_id) REFERENCES players (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_ledger_round_player_effective ON score_ledger (round_id, player_id, effective_at)
        """
    )
    op.execute(
        """
        CREATE TABLE settlement_jobs (
        	id UUID NOT NULL, 
        	round_id UUID NOT NULL, 
        	partition INTEGER NOT NULL, 
        	status VARCHAR(16) NOT NULL, 
        	cursor BIGINT NOT NULL, 
        	attempts INTEGER NOT NULL, 
        	errors TEXT, 
        	PRIMARY KEY (id), 
        	CONSTRAINT uq_settlement_round_partition UNIQUE (round_id, partition), 
        	FOREIGN KEY(round_id) REFERENCES rounds (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_settlement_pending ON settlement_jobs (status)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS settlement_jobs CASCADE
        """
    )
    op.execute(
        """
        DROP TABLE IF EXISTS score_ledger CASCADE
        """
    )
    op.execute(
        """
        DROP TABLE IF EXISTS round_periods CASCADE
        """
    )
    op.execute(
        """
        DROP TABLE IF EXISTS picks CASCADE
        """
    )
    op.execute(
        """
        DROP TABLE IF EXISTS leaderboard_scores CASCADE
        """
    )
    op.execute(
        """
        DROP TABLE IF EXISTS leaderboard_archives CASCADE
        """
    )
    op.execute(
        """
        DROP TABLE IF EXISTS command_inbox CASCADE
        """
    )
    op.execute(
        """
        DROP TABLE IF EXISTS champion_awards CASCADE
        """
    )
    op.execute(
        """
        DROP TABLE IF EXISTS rounds CASCADE
        """
    )
    op.execute(
        """
        DROP TABLE IF EXISTS leaderboard_periods CASCADE
        """
    )
    op.execute(
        """
        DROP TABLE IF EXISTS coordinator_leases CASCADE
        """
    )
    op.execute(
        """
        DROP TABLE IF EXISTS seasons CASCADE
        """
    )
    op.execute(
        """
        DROP TABLE IF EXISTS player_statistics CASCADE
        """
    )
    op.execute(
        """
        DROP TABLE IF EXISTS player_moderation CASCADE
        """
    )
    op.execute(
        """
        DROP TABLE IF EXISTS game_sessions CASCADE
        """
    )
    op.execute(
        """
        DROP TABLE IF EXISTS configuration_versions CASCADE
        """
    )
    op.execute(
        """
        DROP TABLE IF EXISTS admin_sessions CASCADE
        """
    )
    op.execute(
        """
        DROP TABLE IF EXISTS admin_actions CASCADE
        """
    )
    op.execute(
        """
        DROP TABLE IF EXISTS source_checkpoints CASCADE
        """
    )
    op.execute(
        """
        DROP TABLE IF EXISTS projection_jobs CASCADE
        """
    )
    op.execute(
        """
        DROP TABLE IF EXISTS players CASCADE
        """
    )
    op.execute(
        """
        DROP TABLE IF EXISTS outbox_events CASCADE
        """
    )
    op.execute(
        """
        DROP TABLE IF EXISTS games CASCADE
        """
    )
    op.execute(
        """
        DROP TABLE IF EXISTS admin_users CASCADE
        """
    )
    op.execute(
        """
        DROP EXTENSION IF EXISTS btree_gist
        """
    )

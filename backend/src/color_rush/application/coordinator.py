from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from color_rush.application.ingest import process_eligible_inbox
from color_rush.application.periods import (
    assign_round_periods,
    ensure_covering_season,
    ensure_periods_for,
)
from color_rush.application.ports import Clock, Rng
from color_rush.application.settlement import all_partitions_complete
from color_rush.domain.enums import (
    OCCUPYING_ROUND_STATES,
    BonusType,
    Color,
    RoundState,
    SessionMode,
)
from color_rush.domain.errors import (
    DrainFailedError,
    FencingError,
    IllegalTransitionError,
    RoundBusyError,
    SettlementError,
)
from color_rush.domain.presentation import build_presentation_plan
from color_rush.domain.rng import select_result
from color_rush.domain.rules import RoundRules
from color_rush.domain.states import cancel_allowed, require_transition
from color_rush.infrastructure.persistence.db import acquire_session_lock, database_clock
from color_rush.infrastructure.persistence.models import (
    ConfigurationVersion,
    CoordinatorLease,
    Game,
    GameSession,
    OutboxEvent,
    Round,
    SettlementJob,
)


class Coordinator:
    def __init__(
        self,
        session: Session,
        *,
        clock: Clock,
        rng: Rng,
        owner_id: str,
        lease_ttl_seconds: int = 15,
        partition_count: int = 8,
    ) -> None:
        self.session = session
        self.clock = clock
        self.rng = rng
        self.owner_id = owner_id
        self.lease_ttl_seconds = lease_ttl_seconds
        self.partition_count = partition_count

    def create_game(self, name: str = "Color Rush Live") -> Game:
        now = self.clock.now()
        game = Game(id=uuid4(), name=name, created_at=now)
        self.session.add(game)
        self.session.flush()
        self.session.add(
            ConfigurationVersion(
                id=uuid4(),
                game_id=game.id,
                version=1,
                configuration=RoundRules().to_snapshot(),
                activation_boundary="next_round",
                actor_id=None,
                created_at=now,
            )
        )
        self.session.flush()
        return game

    def create_session(
        self,
        game_id: UUID,
        *,
        mode: SessionMode = SessionMode.MANUAL,
        timezone: str = "Asia/Manila",
        source_mode: str = "simulation",
        broadcast_ref: str | None = None,
    ) -> GameSession:
        now = self.clock.now()
        row = GameSession(
            id=uuid4(),
            game_id=game_id,
            broadcast_ref=broadcast_ref,
            live_chat_ref=None,
            mode=mode.value,
            paused=False,
            config_version=1,
            timezone_version=timezone,
            active_round_id=None,
            revision=1,
            next_inbox_sequence=1,
            next_round_bonus=BonusType.NONE.value,
            next_round_gold_bonus_reward=28,
            source_mode=source_mode,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        self.session.flush()
        ensure_covering_season(self.session, game_id, now, timezone)
        ensure_periods_for(self.session, game_id, now, timezone)
        self.claim_lease(row.id)
        return row

    def claim_lease(self, session_id: UUID) -> CoordinatorLease:
        now = self.clock.now()
        expires = now + timedelta(seconds=self.lease_ttl_seconds)
        lease = self.session.get(CoordinatorLease, session_id)
        if lease is None:
            lease = CoordinatorLease(
                session_id=session_id,
                owner_id=self.owner_id,
                fencing_token=1,
                expires_at=expires,
            )
            self.session.add(lease)
        else:
            lease.owner_id = self.owner_id
            lease.fencing_token += 1
            lease.expires_at = expires
        self.session.flush()
        return lease

    def require_fence(self, session_id: UUID, token: int) -> CoordinatorLease:
        lease = self.session.get(CoordinatorLease, session_id)
        now = self.clock.now()
        if lease is None or lease.fencing_token != token or lease.owner_id != self.owner_id:
            raise FencingError("stale coordinator fence")
        if lease.expires_at <= now:
            raise FencingError("coordinator lease expired")
        return lease

    def _load_session(self, session_id: UUID) -> GameSession:
        row = self.session.get(GameSession, session_id)
        if row is None:
            raise ValueError("unknown session")
        return row

    def _rules_for_open(self, game_session: GameSession) -> RoundRules:
        config = self.session.scalar(
            select(ConfigurationVersion).where(
                ConfigurationVersion.game_id == game_session.game_id,
                ConfigurationVersion.version == game_session.config_version,
            )
        )
        if config is not None:
            data = dict(config.configuration)
            data["bonus"] = game_session.next_round_bonus
            data["gold_bonus_reward"] = game_session.next_round_gold_bonus_reward
            data["timezone"] = game_session.timezone_version
            data["version"] = game_session.config_version
            return RoundRules.from_snapshot(data)
        return RoundRules(
            bonus=BonusType(game_session.next_round_bonus),
            gold_bonus_reward=game_session.next_round_gold_bonus_reward,
            timezone=game_session.timezone_version,
            version=game_session.config_version,
        )

    def set_next_bonus(
        self, session_id: UUID, token: int, bonus: BonusType, gold_reward: int = 28
    ) -> None:
        self.require_fence(session_id, token)
        game_session = self._load_session(session_id)
        game_session.next_round_bonus = bonus.value
        game_session.next_round_gold_bonus_reward = gold_reward
        game_session.revision += 1
        game_session.updated_at = self.clock.now()

    def pause(self, session_id: UUID, token: int) -> None:
        self.require_fence(session_id, token)
        game_session = self._load_session(session_id)
        game_session.paused = True
        game_session.revision += 1
        game_session.updated_at = self.clock.now()

    def resume(self, session_id: UUID, token: int) -> None:
        self.require_fence(session_id, token)
        game_session = self._load_session(session_id)
        game_session.paused = False
        game_session.revision += 1
        game_session.updated_at = self.clock.now()

    def set_mode(self, session_id: UUID, token: int, mode: SessionMode) -> None:
        self.require_fence(session_id, token)
        game_session = self._load_session(session_id)
        game_session.mode = mode.value
        game_session.revision += 1
        game_session.updated_at = self.clock.now()

    def start_round(self, session_id: UUID, token: int, rules: RoundRules | None = None) -> Round:
        self.require_fence(session_id, token)
        acquire_session_lock(self.session, session_id)
        now = database_clock(self.session)
        game_session = self._load_session(session_id)
        if game_session.paused:
            raise RoundBusyError("session is paused")
        from color_rush.application.source_health import source_blocks_new_rounds
        from color_rush.config import get_settings

        settings = get_settings()
        if source_blocks_new_rounds(
            self.session,
            game_session,
            lag_pause_ms=settings.source_lag_pause_ms,
            backlog_pause=settings.source_backlog_pause,
        ):
            raise RoundBusyError("source is unhealthy")
        occupying = self.session.scalar(
            select(Round).where(
                Round.session_id == session_id,
                Round.state.in_([state.value for state in OCCUPYING_ROUND_STATES]),
            )
        )
        if occupying is not None:
            raise RoundBusyError("session already has an occupying round")
        last_number = self.session.scalar(
            select(func.max(Round.number)).where(Round.session_id == session_id)
        )
        snapshot_rules = rules or self._rules_for_open(game_session)
        snapshot_rules.validate()
        ensure_covering_season(self.session, game_session.game_id, now, game_session.timezone_version)
        rnd = Round(
            id=uuid4(),
            session_id=session_id,
            number=(last_number or 0) + 1,
            state=RoundState.OPEN.value,
            revision=1,
            rules_snapshot=snapshot_rules.to_snapshot(),
            opened_at=now,
            scheduled_closes_at=now + timedelta(seconds=snapshot_rules.prediction_window_s),
            closed_at=None,
            score_effective_at=None,
            cutoff_sequence=None,
            result=None,
            result_draw=None,
            presentation_plan=None,
            cancel_reason=None,
            drain_deadline_at=None,
            created_at=now,
            updated_at=now,
        )
        self.session.add(rnd)
        game_session.active_round_id = rnd.id
        game_session.next_round_bonus = BonusType.NONE.value
        game_session.revision += 1
        game_session.updated_at = now
        self._outbox("round", rnd.id, rnd.revision, "round.opened", {"round_id": str(rnd.id)})
        self.session.flush()
        return rnd

    def close_ingress(
        self,
        session_id: UUID,
        token: int,
        *,
        early: bool = False,
        now_override: object | None = None,
    ) -> Round:
        self.require_fence(session_id, token)
        acquire_session_lock(self.session, session_id)
        now = database_clock(self.session)
        game_session = self._load_session(session_id)
        if game_session.active_round_id is None:
            raise IllegalTransitionError("no active round")
        rnd = self.session.get(Round, game_session.active_round_id)
        if rnd is None:
            raise IllegalTransitionError("active round missing")
        require_transition(RoundState(rnd.state), RoundState.DRAINING)
        if rnd.scheduled_closes_at is None:
            raise IllegalTransitionError("round has no deadline")
        if not early and now < rnd.scheduled_closes_at:
            raise IllegalTransitionError("deadline has not been reached")
        rules = RoundRules.from_snapshot(rnd.rules_snapshot)
        cutoff = max(game_session.next_inbox_sequence - 1, 0)
        rnd.state = RoundState.DRAINING.value
        rnd.closed_at = now
        rnd.score_effective_at = now if early else rnd.scheduled_closes_at
        rnd.cutoff_sequence = cutoff
        rnd.drain_deadline_at = now + timedelta(seconds=rules.drain_bound_s)
        rnd.revision += 1
        rnd.updated_at = now
        assign_round_periods(
            self.session,
            game_id=game_session.game_id,
            round_id=rnd.id,
            effective_at=rnd.score_effective_at,
            timezone=game_session.timezone_version,
        )
        self._outbox("round", rnd.id, rnd.revision, "round.draining", {"cutoff": cutoff})
        self.session.flush()
        return rnd

    def complete_drain(self, session_id: UUID, token: int) -> Round:
        self.require_fence(session_id, token)
        acquire_session_lock(self.session, session_id)
        now = database_clock(self.session)
        game_session = self._load_session(session_id)
        rnd = self.session.get(Round, game_session.active_round_id)
        if rnd is None:
            raise IllegalTransitionError("no active round")
        if RoundState(rnd.state) is not RoundState.DRAINING:
            raise IllegalTransitionError("round is not draining")
        if rnd.drain_deadline_at is not None and now > rnd.drain_deadline_at:
            return self._cancel_locked(rnd, now, "drain_timeout")
        process_eligible_inbox(self.session, rnd.id)
        now_after = database_clock(self.session)
        if rnd.drain_deadline_at is not None and now_after > rnd.drain_deadline_at:
            return self._cancel_locked(rnd, now_after, "drain_timeout")
        require_transition(RoundState.DRAINING, RoundState.LOCKED)
        rnd.state = RoundState.LOCKED.value
        rnd.revision += 1
        rnd.updated_at = now_after
        self._outbox("round", rnd.id, rnd.revision, "round.locked", {})
        self.session.flush()
        return rnd

    def fail_drain(self, session_id: UUID, token: int) -> Round:
        self.require_fence(session_id, token)
        acquire_session_lock(self.session, session_id)
        now = database_clock(self.session)
        game_session = self._load_session(session_id)
        rnd = self.session.get(Round, game_session.active_round_id)
        if rnd is None:
            raise DrainFailedError("no active round")
        return self._cancel_locked(rnd, now, "drain_timeout")

    def cancel(self, session_id: UUID, token: int, reason: str) -> Round:
        self.require_fence(session_id, token)
        acquire_session_lock(self.session, session_id)
        now = database_clock(self.session)
        game_session = self._load_session(session_id)
        rnd = self.session.get(Round, game_session.active_round_id)
        if rnd is None:
            raise IllegalTransitionError("no active round")
        if not cancel_allowed(RoundState(rnd.state)):
            raise IllegalTransitionError("cancel is not available after outcome commitment")
        return self._cancel_locked(rnd, now, reason)

    def _cancel_locked(self, rnd: Round, now: object, reason: str) -> Round:
        require_transition(RoundState(rnd.state), RoundState.CANCELLED)
        rnd.state = RoundState.CANCELLED.value
        rnd.cancel_reason = reason
        rnd.revision += 1
        rnd.updated_at = now  # type: ignore[assignment]
        game_session = self._load_session(rnd.session_id)
        game_session.active_round_id = None
        game_session.revision += 1
        game_session.updated_at = now  # type: ignore[assignment]
        self._outbox("round", rnd.id, rnd.revision, "round.cancelled", {"reason": reason})
        self.session.flush()
        return rnd

    def spin(self, session_id: UUID, token: int, *, forced: Color | None = None) -> Round:
        self.require_fence(session_id, token)
        game_session = self._load_session(session_id)
        rnd = self.session.get(Round, game_session.active_round_id)
        if rnd is None:
            raise IllegalTransitionError("no active round")
        if rnd.result is not None and RoundState(rnd.state) is RoundState.SPINNING:
            return rnd
        require_transition(RoundState(rnd.state), RoundState.SPINNING)
        rules = RoundRules.from_snapshot(rnd.rules_snapshot)
        if forced is not None:
            if game_session.source_mode != "simulation":
                raise IllegalTransitionError("forced outcomes are simulation-only")
            color, draw = forced, -1
        else:
            color, draw = select_result(self.rng.below, rules)
        now = self.clock.now()
        plan = build_presentation_plan(result=color, started_at=now, rules=rules)
        rnd.result = color.value
        rnd.result_draw = draw
        rnd.presentation_plan = plan.to_snapshot()
        rnd.state = RoundState.SPINNING.value
        rnd.revision += 1
        rnd.updated_at = now
        self._outbox(
            "round",
            rnd.id,
            rnd.revision,
            "round.spinning",
            {"result": color.value, "plan": plan.to_snapshot()},
        )
        self.session.flush()
        return rnd

    def advance_after_spin(self, session_id: UUID, token: int) -> Round:
        self.require_fence(session_id, token)
        game_session = self._load_session(session_id)
        rnd = self.session.get(Round, game_session.active_round_id)
        if rnd is None:
            raise IllegalTransitionError("no active round")
        now = self.clock.now()
        state = RoundState(rnd.state)
        if state is RoundState.SPINNING:
            require_transition(state, RoundState.RESULT)
            rnd.state = RoundState.RESULT.value
        elif state is RoundState.RESULT:
            require_transition(state, RoundState.SETTLING)
            rnd.state = RoundState.SETTLING.value
            self._create_settlement_jobs(rnd.id)
        else:
            raise IllegalTransitionError(f"cannot advance from {state}")
        rnd.revision += 1
        rnd.updated_at = now
        self.session.flush()
        return rnd

    def mark_settled(self, session_id: UUID, token: int) -> Round:
        self.require_fence(session_id, token)
        game_session = self._load_session(session_id)
        rnd = self.session.get(Round, game_session.active_round_id)
        if rnd is None:
            raise IllegalTransitionError("no active round")
        require_transition(RoundState(rnd.state), RoundState.SETTLED)
        if not all_partitions_complete(self.session, rnd.id):
            raise SettlementError("settlement partitions incomplete")
        now = self.clock.now()
        rnd.state = RoundState.SETTLED.value
        rnd.revision += 1
        rnd.updated_at = now
        self._outbox("round", rnd.id, rnd.revision, "round.settled", {})
        self.session.flush()
        return rnd

    def enter_cooldown(self, session_id: UUID, token: int) -> Round:
        self.require_fence(session_id, token)
        game_session = self._load_session(session_id)
        rnd = self.session.get(Round, game_session.active_round_id)
        if rnd is None:
            raise IllegalTransitionError("no active round")
        require_transition(RoundState(rnd.state), RoundState.COOLDOWN)
        now = self.clock.now()
        rnd.state = RoundState.COOLDOWN.value
        rnd.revision += 1
        rnd.updated_at = now
        game_session.active_round_id = None
        game_session.updated_at = now
        self.session.flush()
        return rnd

    def maybe_close_due_rounds(self, session_id: UUID, token: int) -> Round | None:
        game_session = self._load_session(session_id)
        if game_session.active_round_id is None:
            return None
        rnd = self.session.get(Round, game_session.active_round_id)
        if rnd is None or RoundState(rnd.state) is not RoundState.OPEN:
            return None
        acquire_session_lock(self.session, session_id)
        now = database_clock(self.session)
        if rnd.scheduled_closes_at is not None and now >= rnd.scheduled_closes_at:
            return self.close_ingress(session_id, token, early=False)
        return None

    def _create_settlement_jobs(self, round_id: UUID) -> None:
        existing = self.session.scalars(select(SettlementJob).where(SettlementJob.round_id == round_id)).all()
        if existing:
            return
        for partition in range(self.partition_count):
            self.session.add(
                SettlementJob(
                    id=uuid4(),
                    round_id=round_id,
                    partition=partition,
                    status="pending",
                    cursor=0,
                    attempts=0,
                    errors=None,
                )
            )

    def _outbox(
        self,
        aggregate_type: str,
        aggregate_id: UUID,
        revision: int,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        self.session.add(
            OutboxEvent(
                id=uuid4(),
                event_id=uuid4(),
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                aggregate_revision=revision,
                event_type=event_type,
                schema_version=1,
                payload=payload,
                created_at=self.clock.now(),
                published_at=None,
            )
        )

from enum import StrEnum


class Color(StrEnum):
    RED = "red"
    GOLD = "gold"
    GREEN = "green"


class CommandType(StrEnum):
    RED = "red"
    GOLD = "gold"
    GREEN = "green"
    SCORE = "score"
    RANK = "rank"
    HELP = "help"


class BonusType(StrEnum):
    NONE = "none"
    DOUBLE_POINTS = "double_points"
    GOLD_BONUS = "gold_bonus"


class RoundState(StrEnum):
    WAITING = "waiting"
    OPEN = "open"
    DRAINING = "draining"
    LOCKED = "locked"
    SPINNING = "spinning"
    RESULT = "result"
    SETTLING = "settling"
    SETTLED = "settled"
    COOLDOWN = "cooldown"
    CANCELLED = "cancelled"


class SessionMode(StrEnum):
    MANUAL = "manual"
    AUTOMATIC = "automatic"


class PeriodType(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    SEASON = "season"
    ALL_TIME = "all_time"


class PeriodStatus(StrEnum):
    OPEN = "open"
    CLOSING = "closing"
    FINALIZED = "finalized"


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    IGNORED = "ignored"


class DecisionReason(StrEnum):
    ACCEPTED_NEW = "accepted_new"
    ACCEPTED_CHANGE = "accepted_change"
    ACCEPTED_REPEAT = "accepted_repeat"
    REJECTED_OLD_SEQUENCE = "rejected_old_sequence"
    REJECTED_CHANGE_LIMIT = "rejected_change_limit"
    REJECTED_NOT_OPEN = "rejected_not_open"
    REJECTED_LATE_RECEIPT = "rejected_late_receipt"
    REJECTED_HISTORICAL = "rejected_historical"
    REJECTED_AFTER_CUTOFF = "rejected_after_cutoff"
    REJECTED_BLOCKED = "rejected_blocked"
    REJECTED_UNKNOWN_COMMAND = "rejected_unknown_command"
    IGNORED_LOOKUP = "ignored_lookup"
    IGNORED_HELP = "ignored_help"
    IGNORED_INVALID = "ignored_invalid"
    THROTTLED_LOOKUP = "throttled_lookup"
    HELP_COOLDOWN = "help_cooldown"


class SettlementJobStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    FAILED = "failed"


class ChampionAwardType(StrEnum):
    CHAMPION = "champion"


class AdminRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MODERATOR = "moderator"
    OBSERVER = "observer"


class SourceHealth(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    RESYNC = "resync"
    DISABLED = "disabled"
    ENDED = "ended"
    QUOTA = "quota"
    PERMISSION = "permission"
    TRANSIENT = "transient"


class WorkerRole(StrEnum):
    COORDINATOR = "coordinator"
    INGEST = "ingest"
    SETTLEMENT = "settlement"
    OUTBOX = "outbox"
    PROJECTION = "projection"
    GATEWAY = "gateway"
    RETENTION = "retention"
    ALL = "all"


PICK_COMMANDS: frozenset[CommandType] = frozenset(
    {CommandType.RED, CommandType.GOLD, CommandType.GREEN}
)

COLOR_BY_COMMAND: dict[CommandType, Color] = {
    CommandType.RED: Color.RED,
    CommandType.GOLD: Color.GOLD,
    CommandType.GREEN: Color.GREEN,
}

OCCUPYING_ROUND_STATES: frozenset[RoundState] = frozenset(
    {
        RoundState.OPEN,
        RoundState.DRAINING,
        RoundState.LOCKED,
        RoundState.SPINNING,
        RoundState.RESULT,
        RoundState.SETTLING,
        RoundState.SETTLED,
    }
)

CANCELABLE_STATES: frozenset[RoundState] = frozenset(
    {RoundState.OPEN, RoundState.DRAINING, RoundState.LOCKED}
)

PRE_SPIN_STATES: frozenset[RoundState] = frozenset(
    {RoundState.OPEN, RoundState.DRAINING, RoundState.LOCKED}
)

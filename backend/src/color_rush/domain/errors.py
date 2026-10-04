class DomainError(Exception):
    """Base class for rule violations."""


class InvalidCommandError(DomainError):
    pass


class InvalidRulesError(DomainError):
    pass


class IllegalTransitionError(DomainError):
    pass


class EligibilityError(DomainError):
    pass


class FencingError(DomainError):
    pass


class RoundBusyError(DomainError):
    pass


class DrainFailedError(DomainError):
    pass


class SettlementError(DomainError):
    pass


class ConfigurationError(DomainError):
    pass


class ConflictError(DomainError):
    pass


class AuthError(DomainError):
    pass


class ForbiddenError(DomainError):
    pass


class NotFoundError(DomainError):
    pass

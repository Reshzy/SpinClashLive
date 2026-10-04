import secrets

from color_rush.domain.rng import RngDraw


def secrets_randbelow(upper: int) -> int:
    return secrets.randbelow(upper)


production_rng: RngDraw = secrets_randbelow

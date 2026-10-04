from color_rush.domain.enums import CommandType

_COMMANDS: dict[str, CommandType] = {
    "!red": CommandType.RED,
    "!gold": CommandType.GOLD,
    "!green": CommandType.GREEN,
    "!score": CommandType.SCORE,
    "!rank": CommandType.RANK,
    "!help": CommandType.HELP,
}


def parse_command(text: str) -> CommandType | None:
    """Return a command only when the entire trimmed token is an exact command."""
    token = text.strip().casefold()
    return _COMMANDS.get(token)

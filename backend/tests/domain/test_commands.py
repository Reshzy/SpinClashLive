import pytest

from color_rush.domain.commands import parse_command
from color_rush.domain.enums import CommandType


@pytest.mark.domain
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("!red", CommandType.RED),
        ("  !GOLD  ", CommandType.GOLD),
        ("!Green", CommandType.GREEN),
        ("!score", CommandType.SCORE),
        ("!RANK", CommandType.RANK),
        ("!help", CommandType.HELP),
    ],
)
def test_exact_commands(text: str, expected: CommandType) -> None:
    assert parse_command(text) is expected


@pytest.mark.domain
@pytest.mark.parametrize(
    "text",
    [
        "please !red",
        "!red please",
        "!!red",
        "red",
        "!red!",
        "!reds",
        "go !gold now",
        "",
        "   ",
    ],
)
def test_non_exact_rejected(text: str) -> None:
    assert parse_command(text) is None

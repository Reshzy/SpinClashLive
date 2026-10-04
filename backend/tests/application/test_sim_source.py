from datetime import UTC, datetime

from color_rush.application.ports import FrozenClock
from color_rush.domain.commands import parse_command
from color_rush.infrastructure.simulation.source import SimulationChatSource


def test_simulation_source_covers_required_shapes() -> None:
    clock = FrozenClock(datetime(2026, 10, 4, 8, 0, tzinfo=UTC))
    source = SimulationChatSource(clock=clock, broadcast_id="sim-1", seed=7)
    source.insert_gap(1)
    batches = list(source.iter_batches())
    texts = [item.command_text for batch in batches for item in batch.commands]
    ids = [item.provider_message_id for batch in batches for item in batch.commands]
    assert any(text == "!red" for text in texts)
    assert "go red please" in texts
    assert ids.count("dup-same") == 2
    historical = [
        item
        for batch in batches
        for item in batch.commands
        if item.provider_message_id.startswith("hist") or item.published_at.hour < 8
    ]
    assert historical
    assert any(parse_command(text) is None for text in texts)
    assert source.forced_outcome() is None
    from color_rush.domain.enums import Color

    source.force_outcome(Color.GOLD)
    assert source.forced_outcome() is Color.GOLD

"""Deterministic development source. Uses the durable application pipeline."""

from color_rush.infrastructure.simulation.pipeline import inject_chat
from color_rush.infrastructure.simulation.source import SimulationChatSource

__all__ = ["SimulationChatSource", "inject_chat"]

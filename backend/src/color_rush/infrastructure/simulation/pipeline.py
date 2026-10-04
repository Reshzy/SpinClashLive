"""Compatibility wrapper. Prefer SimulationChatSource for new work."""

from color_rush.infrastructure.simulation.source import inject_chat

__all__ = ["inject_chat"]

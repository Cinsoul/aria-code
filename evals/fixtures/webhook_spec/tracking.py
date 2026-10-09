"""SwiftLine tracking webhooks. Implement to docs/WEBHOOKS.md."""

from __future__ import annotations


def verify(body: bytes, signature: str, timestamp: int, now: int, secret: bytes) -> bool:
    """True when a request is authentic (docs/WEBHOOKS.md, section 1)."""
    raise NotImplementedError


class Tracker:
    """Current status per shipment, built from events (docs/WEBHOOKS.md, sections 2-3)."""

    def handle(self, event: dict) -> str:
        """Process one event; return "applied", "duplicate", "ignored" or "stale"."""
        raise NotImplementedError

    def status(self, shipment_id: str) -> str | None:
        """The shipment's current status, or None if no event has been applied."""
        raise NotImplementedError

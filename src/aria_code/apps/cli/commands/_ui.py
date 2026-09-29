"""Rendering helpers for the command mixins.

Two different things used to come from aria_cli's module globals, and only one
of them was ever state:

* ``console`` / ``HAS_RICH`` are per-session state. They belong on
  ``self.context`` — which 40f23c8 started and this package is finishing.
* ``rich_box`` and ``Panel`` are not state at all. They are ``rich.box`` and
  ``rich.panel.Panel``, sitting behind aria_cli's guarded import purely because
  that is where the try/except happened to live. Reaching into a 7000-line
  module for them bought nothing, so they are resolved here instead.

``print_error`` takes the context explicitly rather than reading a global, so a
mixin can render without knowing anything about aria_cli.
"""

from __future__ import annotations

from typing import Any

__all__ = ["Panel", "print_error", "rich_box", "has_rich"]

try:  # Optional: the CLI degrades to plain print when rich is absent.
    from rich import box as rich_box
    from rich.panel import Panel
except ImportError:  # pragma: no cover - exercised only without rich installed
    rich_box = None  # type: ignore[assignment]
    Panel = None  # type: ignore[assignment]


def has_rich() -> bool:
    """Whether rich is importable.

    For module-level helpers that have no ``self`` and so cannot read
    ``self.context.has_rich``. Anything with a context should use that instead —
    a session can be configured without a console even where rich is installed.
    """
    return rich_box is not None


def print_error(context: Any, msg: str, hint: str = "") -> None:
    """Render an error through the context's console.

    ``context`` is an AriaContext, or anything exposing ``console`` and
    ``has_rich``; the renderer already falls back to plain print when console is
    None, so a context built without one still works.
    """
    from aria_code.ui.render.output import print_error as _render

    _render(
        msg,
        hint,
        console=getattr(context, "console", None),
        has_rich=bool(getattr(context, "has_rich", False)),
        rich_box=rich_box,
    )

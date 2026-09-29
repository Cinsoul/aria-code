"""Rendering helpers that take an AriaContext instead of borrowing aria_cli's.

Command mixins used to call ``_print_error`` as a bare name, resolved out of
aria_cli's module globals — which is why 20 call sites across this package had
to reach back into a 7000-line module holding live console state just to print
a line of red text.

aria_cli's own ``_print_error`` is a three-line wrapper that injects
``console`` / ``HAS_RICH`` / ``rich_box`` into ui.render.output.print_error.
The mixins already carry all three on ``self.context``, so they can call the
renderer directly and the detour disappears.
"""

from __future__ import annotations

from typing import Any

__all__ = ["print_error", "rich_box"]


def rich_box() -> Any:
    """``rich.box`` when rich is installed, else None — what print_error expects."""
    try:
        from rich import box

        return box
    except ImportError:
        return None


def print_error(context: Any, msg: str, hint: str = "") -> None:
    """Render an error through the context's console.

    ``context`` is an AriaContext (or anything exposing ``console`` and
    ``has_rich``); print_error already handles console=None by falling back to
    plain print, so a context built without one still works.
    """
    from aria_code.ui.render.output import print_error as _render

    _render(
        msg,
        hint,
        console=getattr(context, "console", None),
        has_rich=bool(getattr(context, "has_rich", False)),
        rich_box=rich_box(),
    )

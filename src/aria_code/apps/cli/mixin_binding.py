"""Bind a block of ArtheraTerminal methods, kept in their own module, to aria_cli's names.

Parts of ArtheraTerminal move out of aria_cli.py unchanged: their bodies still
use aria_cli's module-level names (console, LOCAL_TOOLS, _PROJECT_CONTEXT, …).
bind_mixin() returns a copy of a mixin whose functions resolve bare names in
the namespace given, and ArtheraTerminal inherits the copy.

A copy per call, never a rebind of the mixin itself: aria_cli loads as two
module objects (aria_cli and aria_code.aria_cli), and rebinding one shared
class would leave both terminals on whichever module loaded last.
"""

from __future__ import annotations

import types


def bind_mixin(mixin: type, namespace: dict, owner: str = "ArtheraTerminal") -> type:
    """A copy of ``mixin`` whose methods look up globals in ``namespace``."""
    methods = {}
    for name, attr in vars(mixin).items():
        if isinstance(attr, types.FunctionType):
            bound = types.FunctionType(attr.__code__, namespace, attr.__name__,
                                       attr.__defaults__, attr.__closure__)
            bound.__kwdefaults__ = attr.__kwdefaults__
            bound.__doc__ = attr.__doc__
            bound.__qualname__ = f"{owner}.{attr.__name__}"
            methods[name] = bound
    return type(mixin.__name__, (), {"__doc__": mixin.__doc__, "__module__": mixin.__module__, **methods})


__all__ = ["bind_mixin"]

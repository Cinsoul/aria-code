"""Aria Code.

This package is importable under two roots by design, and has been since the
src/ restructure: ``aria_code.X`` and a bare ``X``. The tree uses both — 399
modules import each other bare (``from market_data_client import get_mdc``)
while others use the package path, and the tests patch whichever root the code
under test actually uses. tests/test_single_import_root.py exists to keep a
single *file* from mixing the two.

In development both roots resolve because pyproject's
``pythonpath = [".", "src", "src/aria_code"]`` and tests/conftest.py put them
there. An installed wheel has neither, so only ``aria_code`` resolved and the
console script died immediately:

    $ aria-code --version
    ModuleNotFoundError: No module named 'aria_cli'

4.4.1 did not hit this because its wheel predates the restructure — it shipped
``aria_cli.py`` and 56 other modules at top level, so the bare root *was* the
package. After the move, nothing put the inner directory on the path.

Adding it here rather than shipping a .pth file keeps it inside the package, so
it applies to `pip install`, `pip install -e .`, a zipapp and a PyInstaller
bundle alike, and it is visible to anyone reading the package rather than hidden
in site-packages.

This is a bridge, not the destination. One root is the goal — v4.4.2 converted
the tree to ``aria_code.*`` throughout — but converting it means moving every
test's patch target with it, and doing that silently under a release is how the
bare-root bugs in this history were introduced.
"""

import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path:
    # Appended, not inserted: a module that legitimately shadows one of these
    # names in the user's own project must keep winning.
    _sys.path.append(_HERE)

del _os, _sys, _HERE

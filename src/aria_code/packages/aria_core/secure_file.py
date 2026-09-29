"""Write files that hold secrets with owner-only permissions.

Three files in this tree hold credentials and every one of them was written
with the process umask — typically 0644, i.e. readable by every other account
on the machine:

  ~/.arthera/brokers.json    brokerage passwords, api_secret, access_token
  ~/.arthera/providers.json  LLM provider API keys
  <config_dir>/config.json   auth_token and refresh_token from /login

The repo already knew to do better: model_cmds.py chmods a generated .env to
0600. The file holding the credentials that can move money was the one without
it.

chmod after create still leaves a window where the file exists with the default
mode, so this opens with O_CREAT|O_EXCL at 0600 where it can, and falls back to
write-then-chmod on an existing file. Permissions are a no-op on Windows, where
the ACL inherited from the user profile directory governs instead — that is
why failure to chmod is not fatal here.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

__all__ = ["write_secret_text", "write_secret_json", "harden_existing"]

_OWNER_ONLY = stat.S_IRUSR | stat.S_IWUSR  # 0o600


def harden_existing(path: Path) -> None:
    """Restrict an existing file to the owner. Never raises."""
    try:
        os.chmod(path, _OWNER_ONLY)
    except (OSError, NotImplementedError):  # pragma: no cover - platform dependent
        pass


def write_secret_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Write *text* to *path* with 0600, creating the parent directory."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Create at the right mode rather than fixing it afterwards, so the content
    # is never briefly world-readable.
    if not path.exists():
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, _OWNER_ONLY)
        except FileExistsError:
            pass  # raced with someone else; fall through to the normal path
        else:
            with os.fdopen(fd, "w", encoding=encoding) as handle:
                handle.write(text)
            return

    path.write_text(text, encoding=encoding)
    harden_existing(path)


def write_secret_json(path: Path, payload: Any, **dumps_kwargs: Any) -> None:
    """json.dump *payload* to *path* with 0600."""
    dumps_kwargs.setdefault("indent", 2)
    dumps_kwargs.setdefault("ensure_ascii", False)
    write_secret_text(Path(path), json.dumps(payload, **dumps_kwargs))

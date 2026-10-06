"""One search behind "@": files, folders, market assets and saved resources.

"@" opened on a list of kinds — file:, folder:, asset:, portfolio: … — and a
file only appeared once a path character was typed, so attaching src/fx.py
took "@", "file:", then the path. Codex's "@" goes straight to results across
files, folders and plugins. Here "@fx" lists fx.py, test_fx.py and any asset,
strategy or report that matches, each labelled with its kind; "@file:" and the
other kind prefixes still narrow the list to one kind.

The inserted text is the canonical reference (@file:src/fx.py, @asset:AAPL),
so references.py resolves it unchanged. Nothing here imports prompt_toolkit.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from aria_code.packages.aria_services.references import reference_search_roots

# Directories a walk never enters when the workspace is not a git repository.
_SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".tox", "dist", "build", ".next", ".idea", ".vscode", "target",
})
MAX_INDEXED_FILES = 20000
INDEX_TTL_SECONDS = 30.0
RESOURCE_KINDS = ("portfolio", "strategy", "dataset", "run", "report")
# Within one match quality, this order breaks ties. A saved strategy or report
# is named on purpose, so it ranks above the file behind it; an asset ranks
# first only when the query is typed like a ticker ("@FX", not "@fx").
_KIND_ORDER = {"strategy": 1, "portfolio": 2, "report": 3, "dataset": 4, "run": 5, "file": 6, "folder": 7}


@dataclass(frozen=True)
class Mention:
    kind: str
    value: str                 # what follows "kind:" — a path, a symbol, a name
    score: int                 # lower is better
    matched: tuple[int, ...] = ()   # positions in `label` to highlight

    @property
    def label(self) -> str:
        return self.value + ("/" if self.kind == "folder" else "")

    @property
    def insert_text(self) -> str:
        value = f'"{self.value}"' if any(ch.isspace() for ch in self.value) else self.value
        return f"{self.kind}:{value}"


def _match(query: str, text: str) -> tuple[int, tuple[int, ...]] | None:
    """(score, positions) of query in text, or None. Case-insensitive."""
    if not query:
        return 50, ()
    q, t = query.lower(), text.lower()
    if t == q:
        return 0, tuple(range(len(text)))
    if t.startswith(q):
        return 10, tuple(range(len(query)))
    at = t.find(q)
    if at >= 0:
        return 20 + min(at, 9), tuple(range(at, at + len(query)))
    positions, i = [], 0
    for index, ch in enumerate(t):
        if i < len(q) and ch == q[i]:
            positions.append(index)
            i += 1
    if i == len(q):
        spread = positions[-1] - positions[0]
        return 40 + min(spread, 29), tuple(positions)
    return None


def _match_path(query: str, path: str) -> tuple[int, tuple[int, ...]] | None:
    """Prefer the file name; fall back to the whole relative path."""
    name_start = path.rfind("/") + 1
    name_hit = _match(query, path[name_start:])
    if name_hit is not None:
        score, positions = name_hit
        return score, tuple(name_start + p for p in positions)
    path_hit = _match(query, path)
    if path_hit is not None:
        return path_hit[0] + 5, path_hit[1]
    return None


class MentionIndex:
    """Searches everything "@" can attach, for one workspace."""

    def __init__(self, workspace: Path | str, *, output_root: Path | str | None = None,
                 symbols: Iterable[str] = ()):
        self.workspace = Path(workspace).expanduser().resolve()
        self.output_root = Path(output_root).expanduser().resolve() if output_root else None
        self.symbols = sorted({str(s).upper() for s in symbols if str(s).strip()})
        self._files: list[str] = []
        self._indexed_at = 0.0

    # ── the file list ────────────────────────────────────────────────────────
    def files(self) -> list[str]:
        """Workspace-relative file paths, .gitignore respected when in a repository."""
        if not self._files or time.monotonic() - self._indexed_at > INDEX_TTL_SECONDS:
            self._files = self._git_files() or self._walk_files()
            self._indexed_at = time.monotonic()
        return self._files

    def _git_files(self) -> list[str]:
        try:
            done = subprocess.run(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                cwd=self.workspace, capture_output=True, text=True, timeout=3,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        if done.returncode != 0:
            return []
        return [line for line in done.stdout.splitlines() if line][:MAX_INDEXED_FILES]

    def _walk_files(self) -> list[str]:
        found: list[str] = []
        for root, dirs, names in os.walk(self.workspace):
            dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS and not d.startswith("."))
            rel_root = os.path.relpath(root, self.workspace)
            for name in sorted(names):
                if name.startswith("."):
                    continue
                found.append(name if rel_root == "." else f"{rel_root}/{name}".replace(os.sep, "/"))
                if len(found) >= MAX_INDEXED_FILES:
                    return found
        return found

    def folders(self) -> list[str]:
        seen: dict[str, None] = {}
        for path in self.files():
            parts = path.split("/")[:-1]
            for depth in range(1, len(parts) + 1):
                seen["/".join(parts[:depth])] = None
        return list(seen)

    def recent_files(self, limit: int = 5) -> list[str]:
        stamped = []
        for path in self.files()[:MAX_INDEXED_FILES]:
            try:
                stamped.append((os.stat(self.workspace / path).st_mtime, path))
            except OSError:
                continue
        return [path for _, path in sorted(stamped, reverse=True)[:limit]]

    def resources(self, kind: str) -> list[str]:
        names: dict[str, None] = {}
        for root in reference_search_roots(kind, self.workspace, self.output_root):
            if not root.is_dir():
                continue
            try:
                for path in root.rglob("*"):
                    if path.is_file() and not any(p.startswith(".") for p in path.relative_to(root).parts):
                        names[path.stem] = None
                    if len(names) >= 200:
                        break
            except OSError:
                continue
        return list(names)

    # ── search ───────────────────────────────────────────────────────────────
    def search(self, query: str, *, kind: str | None = None, limit: int = 30) -> list[Mention]:
        """Matches for `query`, best first; only `kind` when one is given."""
        found: list[Mention] = []

        def add(k: str, values: Iterable[str], matcher) -> None:
            if kind and k != kind:
                return
            for value in values:
                hit = matcher(query, value)
                if hit is not None:
                    found.append(Mention(k, value, hit[0], hit[1]))

        add("file", self.files(), _match_path)
        add("folder", self.folders(), _match_path)
        # Tickers by exact, prefix or substring only: "fx" scattered through
        # NFLX is not a way anyone looks for Netflix.
        add("asset", self.symbols, lambda q, v: (h if (h := _match(q, v)) and h[0] < 40 else None))
        if query and _looks_like_symbol(query) and query.upper() not in self.symbols and kind in (None, "asset"):
            found.append(Mention("asset", query.upper(), 30, tuple(range(len(query)))))
        for resource in RESOURCE_KINDS:
            add(resource, self.resources(resource), _match)
        asset_rank = 0 if _looks_like_symbol(query) else 8
        found.sort(key=lambda m: (m.score, asset_rank if m.kind == "asset" else _KIND_ORDER.get(m.kind, 9),
                                  len(m.value), m.value))
        # Letters scattered through a long path ("AAP" in providers/llm/ollama.py)
        # are noise once there is a popup's worth of closer matches.
        if sum(1 for m in found if m.score < 40) >= 8:
            found = [m for m in found if m.score < 40]
        return found[:limit]


def _looks_like_symbol(text: str) -> bool:
    """A ticker someone is typing: "AAPL", "0700.HK", "BTC-USD" — not "fx" or "readme"."""
    raw = text.strip()
    return 1 <= len(raw) <= 12 and raw.upper() == raw and any(ch.isalnum() for ch in raw) and " " not in raw


__all__ = ["Mention", "MentionIndex"]

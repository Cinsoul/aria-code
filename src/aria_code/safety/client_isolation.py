"""Keep one client's document free of other clients' data.

A 3PL's stock file, a fund's holdings export or a merchant ledger often holds
several clients side by side. A document written *for one of them* (named for
it: ``report_BETA.md``, ``statement-acme.csv``) must not carry another
client's name, id or item codes. The prompt says so, and in an eval run the
agent still copied two notes from Beta's own rows that named Acme and Gamma
SKUs into Beta's report.

This is the check behind that rule, the way a liquid handler's checker
tracks what each tip has touched rather than trusting the protocol's
comments: before a client document is written, its text is scanned for the
identifiers of every *other* client found in the workspace's data files, and
the write is refused with a list of what leaked.

Clients are found in CSV files near the document that have an owner column
(``owner_id``, ``shipper``, ``client``, ``customer``…). A document is a
client's when its file name names exactly one of them. Code is not checked:
a script that processes every client legitimately names them all, and so
does an internal report whose name does not single one out.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

OWNER_COLUMNS = ("owner_id", "owner", "shipper_id", "shipper", "client_id", "client",
                 "customer_id", "customer", "account_id", "货主", "客户")
NAME_COLUMNS = ("owner_name", "shipper_name", "client_name", "customer_name", "account_name",
                "货主名称", "客户名称")
ITEM_COLUMNS = ("sku", "item", "item_id", "item_code", "product_id", "product_code", "sku_id")
DOCUMENT_SUFFIXES = {".md", ".markdown", ".txt", ".csv", ".tsv", ".json", ".html", ".htm",
                     ".xml", ".yaml", ".yml", ".rst", ".eml"}
MIN_TERM = 3                       # "A" or "AB" as an owner id would match everywhere
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_FILES = 25


@dataclass
class Client:
    id: str
    names: set[str] = field(default_factory=set)
    items: set[str] = field(default_factory=set)

    def terms(self) -> list[str]:
        return sorted({t for t in {self.id, *self.names, *self.items} if len(t) >= MIN_TERM}, key=len, reverse=True)


_CACHE: dict[tuple[str, float, int], dict[str, Client]] = {}


def _column(header: Iterable[str], wanted: tuple[str, ...]) -> str | None:
    lowered = {h.strip().lower(): h for h in header if h}
    for name in wanted:
        if name in lowered:
            return lowered[name]
    return None


def _clients_in(path: Path) -> dict[str, Client]:
    try:
        stat = path.stat()
    except OSError:
        return {}
    if stat.st_size > MAX_FILE_BYTES:
        return {}
    key = (str(path), stat.st_mtime, stat.st_size)
    if key in _CACHE:
        return _CACHE[key]
    found: dict[str, Client] = {}
    try:
        with path.open(newline="", encoding="utf-8-sig", errors="replace") as fh:
            reader = csv.DictReader(fh)
            header = reader.fieldnames or []
            owner = _column(header, OWNER_COLUMNS)
            if owner:
                name = _column(header, NAME_COLUMNS)
                item = _column(header, ITEM_COLUMNS)
                for row in reader:
                    cid = (row.get(owner) or "").strip()
                    if not cid:
                        continue
                    client = found.setdefault(cid, Client(cid))
                    if name and (row.get(name) or "").strip():
                        client.names.add(row[name].strip())
                    if item and (row.get(item) or "").strip():
                        client.items.add(row[item].strip())
    except (OSError, csv.Error, UnicodeError):
        found = {}
    _CACHE[key] = found
    return found


def client_index(roots: Iterable[Path]) -> dict[str, Client]:
    """Every client named in the CSV data files in *roots* and their immediate subfolders."""
    index: dict[str, Client] = {}
    seen = 0
    for root in dict.fromkeys(Path(r) for r in roots):
        if not root.is_dir():
            continue
        candidates = sorted(root.glob("*.csv")) + sorted(root.glob("*/*.csv"))
        for path in candidates:
            if seen >= MAX_FILES:
                return index
            seen += 1
            for cid, client in _clients_in(path).items():
                merged = index.setdefault(cid, Client(cid))
                merged.names |= client.names
                merged.items |= client.items
    return index if len(index) > 1 else {}


def _words(text: str) -> set[str]:
    return {w.lower() for w in re.split(r"[^0-9A-Za-z一-鿿]+", text) if w}


def target_client(path: Path, index: dict[str, Client]) -> str | None:
    """The one client a document's file name singles out, if it singles out exactly one."""
    words = _words(Path(path).stem)
    compact = re.sub(r"[^0-9a-z一-鿿]", "", Path(path).stem.lower())
    hits = set()
    for cid, client in index.items():
        if cid.lower() in words:
            hits.add(cid)
            continue
        for name in client.names:
            squashed = re.sub(r"[^0-9a-z一-鿿]", "", name.lower())
            if len(squashed) >= MIN_TERM and squashed in compact:
                hits.add(cid)
    return next(iter(hits)) if len(hits) == 1 else None


def _mentions(text: str, term: str) -> bool:
    if re.search(r"[一-鿿]", term):
        return term in text
    return re.search(rf"(?<![0-9A-Za-z]){re.escape(term)}(?![0-9A-Za-z])", text, re.IGNORECASE) is not None


def foreign_mentions(text: str, target: str, index: dict[str, Client]) -> dict[str, list[str]]:
    """Other clients' identifiers that appear in *text*, by client."""
    own = {t.lower() for t in index[target].terms()} if target in index else set()
    leaks: dict[str, list[str]] = {}
    for cid, client in sorted(index.items()):
        if cid == target:
            continue
        hits = [t for t in client.terms() if t.lower() not in own and _mentions(text, t)]
        if hits:
            leaks[cid] = hits[:4]
    return leaks


def check_write(path: Path | str, content: str, roots: Iterable[Path | str] = ()) -> str | None:
    """Why this write must be refused, or None when it may go ahead."""
    path = Path(path)
    if path.suffix.lower() not in DOCUMENT_SUFFIXES:
        return None
    search = [path.parent, *(Path(r) for r in roots)]
    index = client_index(search)
    if not index:
        return None
    target = target_client(path, index)
    if target is None:
        return None
    leaks = foreign_mentions(content, target, index)
    if not leaks:
        return None
    listed = "; ".join(f"{cid} ({', '.join(terms)})" for cid, terms in leaks.items())
    return (f"Not written: {path.name} is for client {target}, but it contains other clients' data: {listed}. "
            f"A client's document holds only that client's data. Remove these, including any that came "
            f"from notes or comments in {target}'s own rows, and write it again. If this is meant to be an "
            f"internal cross-client document, name it without singling out one client.")


__all__ = ["Client", "check_write", "client_index", "foreign_mentions", "target_client"]

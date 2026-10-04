"""Where the relay keeps what it must not forget.

Bindings (which Feishu user reaches which machine), each machine's
credentials, the chats a client may post to, and which client posted which
card. All of it used to live in a SQLite file inside the container — and a
Cloud Run container's filesystem is discarded on every deploy and restart, so
every merge to main unbound every user and reset every machine's credentials
to "first use". `RELAY_STORE=firestore` keeps it in Firestore instead.

SQLite stays the default: right for local development and for a self-hosted
relay with a persistent disk.

Both stores implement the same small contract, and tests/test_relay_store.py
runs one set of tests against both. The one operation that must be atomic is
claim_credentials: the first registration of a client_id wins, and two
connections racing for the same id cannot both. SQLite gets that from the
primary key, Firestore from create(), which fails if the document exists.

Firestore layout — every read is by document id, never a query:
    relay_bindings/{feishu_user_id}        {client_id, bound_at}
    relay_clients/{client_id}              {token_hash, bind_code_hash, created_at}
    relay_bind_codes/{bind_code_hash}      {client_id}
    relay_client_chats/{sha256(client:chat)} {client_id, chat_id, last_seen}
    relay_card_origins/{message_id}        {client_id, created_at}
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import time
from typing import Optional


class SqliteStore:
    kind = "sqlite"

    def __init__(self, path: str) -> None:
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS bindings (
                feishu_user_id TEXT PRIMARY KEY, client_id TEXT NOT NULL, bound_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS client_credentials (
                client_id TEXT PRIMARY KEY, token_hash TEXT NOT NULL,
                bind_code_hash TEXT NOT NULL, created_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS client_chats (
                client_id TEXT NOT NULL, chat_id TEXT NOT NULL, last_seen REAL NOT NULL,
                PRIMARY KEY (client_id, chat_id));
            CREATE TABLE IF NOT EXISTS card_origins (
                message_id TEXT PRIMARY KEY, client_id TEXT NOT NULL, created_at REAL NOT NULL);
        """)
        self.db.commit()

    def client_for_user(self, feishu_user_id: str) -> Optional[str]:
        row = self.db.execute("SELECT client_id FROM bindings WHERE feishu_user_id = ?",
                              (feishu_user_id,)).fetchone()
        return row["client_id"] if row else None

    def bind_user(self, feishu_user_id: str, client_id: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO bindings VALUES (?, ?, ?)",
                        (feishu_user_id, client_id, time.time()))
        self.db.commit()

    def binding_count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM bindings").fetchone()[0]

    def credentials(self, client_id: str) -> Optional[dict]:
        row = self.db.execute("SELECT token_hash, bind_code_hash FROM client_credentials "
                              "WHERE client_id = ?", (client_id,)).fetchone()
        return dict(row) if row else None

    def claim_credentials(self, client_id: str, token_hash: str, bind_code_hash: str) -> bool:
        try:
            self.db.execute("INSERT INTO client_credentials VALUES (?, ?, ?, ?)",
                            (client_id, token_hash, bind_code_hash, time.time()))
            self.db.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def set_bind_code(self, client_id: str, bind_code_hash: str) -> None:
        self.db.execute("UPDATE client_credentials SET bind_code_hash = ? WHERE client_id = ?",
                        (bind_code_hash, client_id))
        self.db.commit()

    def client_for_bind_code(self, bind_code_hash: str) -> Optional[str]:
        row = self.db.execute("SELECT client_id FROM client_credentials WHERE bind_code_hash = ?",
                              (bind_code_hash,)).fetchone()
        return row["client_id"] if row else None

    def remember_chat(self, client_id: str, chat_id: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO client_chats VALUES (?, ?, ?)",
                        (client_id, chat_id, time.time()))
        self.db.commit()

    def has_chat(self, client_id: str, chat_id: str) -> bool:
        return self.db.execute("SELECT 1 FROM client_chats WHERE client_id = ? AND chat_id = ?",
                               (client_id, chat_id)).fetchone() is not None

    def remember_card(self, message_id: str, client_id: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO card_origins VALUES (?, ?, ?)",
                        (message_id, client_id, time.time()))
        self.db.commit()

    def card_origin(self, message_id: str) -> Optional[str]:
        row = self.db.execute("SELECT client_id FROM card_origins WHERE message_id = ?",
                              (message_id,)).fetchone()
        return row["client_id"] if row else None


class FirestoreStore:
    kind = "firestore"

    def __init__(self, client, already_exists: type = Exception) -> None:
        self.client = client
        self._already_exists = already_exists

    def _doc(self, collection: str, doc_id: str):
        return self.client.collection(collection).document(doc_id)

    def _get(self, collection: str, doc_id: str) -> Optional[dict]:
        if not doc_id:
            return None
        snapshot = self._doc(collection, doc_id).get()
        return snapshot.to_dict() if snapshot.exists else None

    @staticmethod
    def _chat_key(client_id: str, chat_id: str) -> str:
        return hashlib.sha256(f"{client_id}\0{chat_id}".encode("utf-8")).hexdigest()

    def client_for_user(self, feishu_user_id: str) -> Optional[str]:
        return (self._get("relay_bindings", feishu_user_id) or {}).get("client_id")

    def bind_user(self, feishu_user_id: str, client_id: str) -> None:
        self._doc("relay_bindings", feishu_user_id).set({"client_id": client_id, "bound_at": time.time()})

    def binding_count(self) -> int:
        # Fine at a relay's scale; an aggregation query would need an index.
        return sum(1 for _ in self.client.collection("relay_bindings").list_documents())

    def credentials(self, client_id: str) -> Optional[dict]:
        data = self._get("relay_clients", client_id)
        return {"token_hash": data["token_hash"], "bind_code_hash": data["bind_code_hash"]} if data else None

    def claim_credentials(self, client_id: str, token_hash: str, bind_code_hash: str) -> bool:
        try:
            self._doc("relay_clients", client_id).create(
                {"token_hash": token_hash, "bind_code_hash": bind_code_hash, "created_at": time.time()})
        except self._already_exists:
            return False
        self._doc("relay_bind_codes", bind_code_hash).set({"client_id": client_id})
        return True

    def set_bind_code(self, client_id: str, bind_code_hash: str) -> None:
        old = (self._get("relay_clients", client_id) or {}).get("bind_code_hash")
        if old and old != bind_code_hash:
            self._doc("relay_bind_codes", old).delete()
        self._doc("relay_bind_codes", bind_code_hash).set({"client_id": client_id})
        self._doc("relay_clients", client_id).set({"bind_code_hash": bind_code_hash}, merge=True)

    def client_for_bind_code(self, bind_code_hash: str) -> Optional[str]:
        return (self._get("relay_bind_codes", bind_code_hash) or {}).get("client_id")

    def remember_chat(self, client_id: str, chat_id: str) -> None:
        self._doc("relay_client_chats", self._chat_key(client_id, chat_id)).set(
            {"client_id": client_id, "chat_id": chat_id, "last_seen": time.time()})

    def has_chat(self, client_id: str, chat_id: str) -> bool:
        return self._get("relay_client_chats", self._chat_key(client_id, chat_id)) is not None

    def remember_card(self, message_id: str, client_id: str) -> None:
        self._doc("relay_card_origins", message_id).set({"client_id": client_id, "created_at": time.time()})

    def card_origin(self, message_id: str) -> Optional[str]:
        return (self._get("relay_card_origins", message_id) or {}).get("client_id")


def open_store():
    """The store RELAY_STORE names: "sqlite" (default, DB_PATH) or "firestore"."""
    kind = os.environ.get("RELAY_STORE", "sqlite").strip().lower()
    if kind == "firestore":
        from google.api_core.exceptions import AlreadyExists
        from google.cloud import firestore

        client = firestore.Client(
            project=os.environ.get("RELAY_FIRESTORE_PROJECT") or None,
            database=os.environ.get("RELAY_FIRESTORE_DATABASE") or "(default)",
        )
        return FirestoreStore(client, already_exists=AlreadyExists)
    if kind != "sqlite":
        raise ValueError(f"RELAY_STORE must be sqlite or firestore, not {kind!r}")
    return SqliteStore(os.environ.get("DB_PATH", "./relay.db"))

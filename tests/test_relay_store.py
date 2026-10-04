"""The relay's state must survive a redeploy, and both stores must agree.

On Cloud Run the relay kept bindings and machine credentials in a SQLite file
inside the container, which is discarded on every deploy: each merge to main
unbound every user. relay_store.py adds a Firestore store. One contract runs
against both stores here, so they cannot drift apart, and a relay "redeploy"
(a module reload) is shown to keep a binding when the store persists.
"""

from __future__ import annotations

import importlib
import json
import os

import pytest

from aria_code.relay_store import FirestoreStore, SqliteStore, open_store


class AlreadyExists(Exception):
    pass


class _Snapshot:
    def __init__(self, data):
        self.exists = data is not None
        self._data = data

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _Doc:
    def __init__(self, table, doc_id):
        self.table, self.id = table, doc_id

    def get(self):
        return _Snapshot(self.table.get(self.id))

    def set(self, data, merge=False):
        self.table[self.id] = {**self.table.get(self.id, {}), **data} if merge else dict(data)

    def create(self, data):
        if self.id in self.table:
            raise AlreadyExists(self.id)
        self.table[self.id] = dict(data)

    def delete(self):
        self.table.pop(self.id, None)


class _Collection:
    def __init__(self, table):
        self.table = table

    def document(self, doc_id):
        assert doc_id and "/" not in doc_id, f"invalid Firestore document id {doc_id!r}"
        return _Doc(self.table, doc_id)

    def list_documents(self):
        return [_Doc(self.table, k) for k in list(self.table)]


class FakeFirestore:
    """The subset of google.cloud.firestore.Client the store uses — by id only."""

    def __init__(self):
        self.tables = {}

    def collection(self, name):
        return _Collection(self.tables.setdefault(name, {}))


@pytest.fixture(params=["sqlite", "firestore"])
def store(request, tmp_path):
    if request.param == "sqlite":
        return SqliteStore(str(tmp_path / "relay.db"))
    return FirestoreStore(FakeFirestore(), already_exists=AlreadyExists)


class TestContract:
    def test_bindings(self, store):
        assert store.client_for_user("ou_a") is None and store.binding_count() == 0
        store.bind_user("ou_a", "aria-1")
        store.bind_user("ou_a", "aria-2")          # rebinding replaces
        assert store.client_for_user("ou_a") == "aria-2" and store.binding_count() == 1

    def test_the_first_claim_wins_and_a_second_cannot(self, store):
        assert store.claim_credentials("aria-1", "tok-a", "code-a")
        assert not store.claim_credentials("aria-1", "tok-b", "code-b")
        assert store.credentials("aria-1") == {"token_hash": "tok-a", "bind_code_hash": "code-a"}
        assert store.client_for_bind_code("code-b") is None

    def test_bind_codes_resolve_and_rotate(self, store):
        store.claim_credentials("aria-1", "tok", "code-a")
        assert store.client_for_bind_code("code-a") == "aria-1"
        store.set_bind_code("aria-1", "code-b")
        assert store.client_for_bind_code("code-a") is None
        assert store.client_for_bind_code("code-b") == "aria-1"
        assert store.credentials("aria-1")["bind_code_hash"] == "code-b"

    def test_chats_are_per_client(self, store):
        store.remember_chat("aria-1", "oc_x/with:odd chars")
        assert store.has_chat("aria-1", "oc_x/with:odd chars")
        assert not store.has_chat("aria-2", "oc_x/with:odd chars")

    def test_card_origins(self, store):
        assert store.card_origin("om_1") is None
        store.remember_card("om_1", "aria-1")
        assert store.card_origin("om_1") == "aria-1"


class TestChoosingAStore:
    def test_sqlite_is_the_default(self, monkeypatch, tmp_path):
        monkeypatch.delenv("RELAY_STORE", raising=False)
        monkeypatch.setenv("DB_PATH", str(tmp_path / "r.db"))
        assert open_store().kind == "sqlite"

    def test_an_unknown_store_is_an_error_not_a_silent_default(self, monkeypatch):
        monkeypatch.setenv("RELAY_STORE", "redis")
        with pytest.raises(ValueError):
            open_store()


# ── The relay on top of it ───────────────────────────────────────────────────

fastapi_testclient = pytest.importorskip("fastapi.testclient", reason="relay server dependency")
if os.environ.get("GITHUB_ACTIONS"):
    import fastapi  # noqa: F401,E402 — CI must run these, not skip them


def _load_relay(monkeypatch, tmp_path, store=None):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "relay.db"))
    monkeypatch.setenv("FEISHU_VERIFICATION_TOKEN", "tok")
    for key in ("FEISHU_ENCRYPT_KEY", "RELAY_ALLOW_UNVERIFIED_EVENTS", "RELAY_SECRET", "K_SERVICE"):
        monkeypatch.delenv(key, raising=False)
    import aria_relay_server
    relay = importlib.reload(aria_relay_server)
    if store is not None:
        relay._store_instance = store
    return relay


def _register(relay, client_id="aria-1", token="t" * 43, code="ABCDEFGHJKLM"):
    with fastapi_testclient.TestClient(relay.app).websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "register", "client_id": client_id,
                                 "token": token, "bind_code": code}))
        return json.loads(ws.receive_text())


class TestRelayAcrossARedeploy:
    def test_a_binding_and_credentials_survive_a_redeploy_with_a_persistent_store(self, monkeypatch, tmp_path):
        shared = FirestoreStore(FakeFirestore(), already_exists=AlreadyExists)
        relay = _load_relay(monkeypatch, tmp_path, shared)
        assert _register(relay)["ok"]
        relay._bind("ou_owner", relay._client_for_bind_code("ABCD-EFGH-JKLM"))

        redeployed = _load_relay(monkeypatch, tmp_path, shared)   # a fresh process, same store
        assert redeployed._lookup_client("ou_owner") == "aria-1"
        assert not _register(redeployed, token="x" * 43)["ok"], "credentials were forgotten"
        assert _register(redeployed)["ok"]

    def test_status_names_the_store_and_warns_on_cloud_run_with_sqlite(self, monkeypatch, tmp_path):
        relay = _load_relay(monkeypatch, tmp_path)
        body = fastapi_testclient.TestClient(relay.app).get("/status").json()
        assert body["store"] == "sqlite" and "store_warning" not in body
        monkeypatch.setenv("K_SERVICE", "aria-code")
        body = fastapi_testclient.TestClient(relay.app).get("/status").json()
        assert "firestore" in body["store_warning"]

    def test_no_warning_with_firestore_on_cloud_run(self, monkeypatch, tmp_path):
        relay = _load_relay(monkeypatch, tmp_path,
                            FirestoreStore(FakeFirestore(), already_exists=AlreadyExists))
        monkeypatch.setenv("K_SERVICE", "aria-code")
        body = fastapi_testclient.TestClient(relay.app).get("/status").json()
        assert body["store"] == "firestore" and "store_warning" not in body

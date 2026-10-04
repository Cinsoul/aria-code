"""Knowing a client_id must not let anyone impersonate or bind that machine.

Before 2026-10-04 the client_id was a relay client's only identity and also
its bind code. Two consequences, both closed here:

  1. Registering with someone's client_id replaced their connection, and their
     Feishu messages went to the newcomer.
  2. Sending "/bind ARIA-BIND-<their client_id>" from your own, properly signed
     Feishu account bound you to their machine, so your messages ran there —
     on their model quota, against their local data.

Now each machine registers a token (trust on first use) and a bind code it
generated and shows only on its own screen; the relay stores hashes of both.
"""

from __future__ import annotations

import importlib
import json
import os
from unittest import mock

import pytest

if os.environ.get("GITHUB_ACTIONS"):
    import fastapi  # noqa: F401  — CI must run these, not skip them

fastapi_testclient = pytest.importorskip("fastapi.testclient", reason="relay server dependency")
TestClient = fastapi_testclient.TestClient

TOKEN_A, TOKEN_B = "a" * 43, "b" * 43
CODE_A, CODE_B = "ABCDEFGHJKLM", "NPQRSTUVWXYZ"


@pytest.fixture
def relay(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "relay.db"))
    for key in ("FEISHU_ENCRYPT_KEY", "RELAY_ALLOW_UNVERIFIED_EVENTS", "RELAY_SECRET"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("FEISHU_VERIFICATION_TOKEN", "tok")
    import aria_relay_server
    return importlib.reload(aria_relay_server)


def _register(relay, client_id="aria-victim", token=TOKEN_A, code=CODE_A, **extra):
    with TestClient(relay.app).websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "register", "client_id": client_id,
                                 "token": token, "bind_code": code, **extra}))
        return json.loads(ws.receive_text())


class TestRegistration:
    def test_the_first_registration_is_accepted(self, relay):
        assert _register(relay)["ok"]

    def test_only_hashes_are_stored(self, relay):
        _register(relay)
        row = relay.get_db().execute("SELECT * FROM client_credentials").fetchone()
        assert TOKEN_A not in tuple(row) and CODE_A not in tuple(row)

    def test_the_same_machine_reconnects(self, relay):
        _register(relay)
        assert _register(relay)["ok"]

    def test_someone_else_with_the_client_id_is_refused(self, relay):
        _register(relay)
        answer = _register(relay, token=TOKEN_B)
        assert not answer["ok"] and "another installation" in answer["reason"]

    def test_a_client_without_credentials_is_told_to_upgrade(self, relay):
        with TestClient(relay.app).websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"type": "register", "client_id": "aria-old"}))
            answer = json.loads(ws.receive_text())
        assert not answer["ok"] and "upgrade" in answer["reason"]

    def test_the_deployment_secret_still_gates_registration(self, relay, monkeypatch):
        monkeypatch.setattr(relay, "_RELAY_SECRET", "s3cret")
        assert not _register(relay, secret="wrong")["ok"]
        assert _register(relay, client_id="aria-other", secret="s3cret")["ok"]


def _bind_event(open_id, text):
    return {"token": "tok", "header": {"event_type": "im.message.receive_v1"}, "event": {
        "sender": {"sender_id": {"open_id": open_id}},
        "message": {"message_id": "om_1", "chat_id": "oc_dm", "message_type": "text",
                    "content": json.dumps({"text": text})}}}


class TestBinding:
    def _post(self, relay, open_id, text):
        sent = []

        async def send_text(to, text):
            sent.append(text)

        with mock.patch.object(relay, "_send_feishu_text", send_text):
            TestClient(relay.app).post("/feishu/event", json=_bind_event(open_id, text))
        return sent

    def test_the_machines_own_code_binds_it(self, relay):
        _register(relay)
        replies = self._post(relay, "ou_owner", "/bind ARIA-BIND-ABCD-EFGH-JKLM")
        assert "绑定成功" in replies[0]
        assert relay._lookup_client("ou_owner") == "aria-victim"

    def test_the_client_id_no_longer_binds(self, relay):
        _register(relay)
        replies = self._post(relay, "ou_attacker", "/bind ARIA-BIND-ARIA-VICTIM")
        assert "无效" in replies[0]
        assert relay._lookup_client("ou_attacker") is None

    def test_a_guessed_code_does_not_bind(self, relay):
        _register(relay)
        self._post(relay, "ou_attacker", f"/bind ARIA-BIND-{CODE_B}")
        assert relay._lookup_client("ou_attacker") is None

    def test_a_rotated_code_replaces_the_old_one(self, relay):
        _register(relay)
        _register(relay, code=CODE_B)
        self._post(relay, "ou_x", f"/bind {CODE_A}")
        assert relay._lookup_client("ou_x") is None
        self._post(relay, "ou_owner", f"/bind {CODE_B}")
        assert relay._lookup_client("ou_owner") == "aria-victim"

    def test_a_rotation_needs_the_token(self, relay):
        _register(relay)
        _register(relay, token=TOKEN_B, code=CODE_B)   # refused, so nothing changes
        self._post(relay, "ou_attacker", f"/bind {CODE_B}")
        assert relay._lookup_client("ou_attacker") is None


# ── The client side ──────────────────────────────────────────────────────────

from aria_code.clients import aria_relay_client as client  # noqa: E402


class TestClientCredentials:
    def test_created_once_saved_privately_and_reused(self, tmp_path, monkeypatch):
        # setenv (not delenv) so monkeypatch restores whatever
        # ensure_credentials writes into os.environ.
        monkeypatch.setenv("ARIA_RELAY_CLIENT_TOKEN", "")
        monkeypatch.setenv("ARIA_RELAY_BIND_CODE", "")
        env_file = tmp_path / ".aria" / ".env"
        first = client.ensure_credentials(env_file)
        assert oct(env_file.stat().st_mode & 0o777) == "0o600"
        assert len(first[0]) >= 32 and len(first[1]) == 12
        assert client.ensure_credentials(env_file) == first
        assert env_file.read_text().count("ARIA_RELAY_CLIENT_TOKEN=") == 1

    def test_bind_codes_avoid_characters_people_misread(self):
        codes = "".join(client.new_bind_code() for _ in range(200))
        assert not set(codes) & set("0O1I")

    def test_the_bind_code_is_typed_in_groups(self):
        assert client.format_bind_code("abcdefghjklm") == "ARIA-BIND-ABCD-EFGH-JKLM"

    def test_the_register_frame_carries_the_credentials(self, monkeypatch):
        monkeypatch.setenv("ARIA_RELAY_SECRET", "s3cret")
        frame = client.register_frame("aria-a", TOKEN_A, CODE_A)
        assert frame == {"type": "register", "client_id": "aria-a", "token": TOKEN_A,
                         "bind_code": CODE_A, "secret": "s3cret"}

"""The relay client must only ever connect where the user chose — never to a default it does not own.

The client, the setup wizard and docker-compose all defaulted to
wss://relay.aria.ai. aria.ai belongs to an unrelated party; the subdomain does
not resolve today, but its owner could create it, and every client left on
the default would send its machine token, bind code and Feishu traffic there.
"""

from __future__ import annotations

import asyncio
import pathlib
from unittest import mock

import pytest

from aria_code.clients import aria_relay_client as client

ROOT = pathlib.Path(__file__).resolve().parents[1]


class TestWhereTheClientMayConnect:
    @pytest.mark.parametrize("url", [
        client.OFFICIAL_RELAY_URL,
        "wss://relay.example.com/ws",       # a self-hosted relay
        "ws://localhost:8765/ws",           # local development
        "ws://127.0.0.1:8765/ws",
    ])
    def test_allowed(self, url):
        assert client.relay_url_problem(url) == ""

    @pytest.mark.parametrize("url, why", [
        ("", "not set"),
        ("wss://relay.aria.ai", "not run by Arthera"),
        ("wss://anything.aria.ai/ws", "not run by Arthera"),
        ("ws://relay.example.com/ws", "wss://"),      # the token would travel in clear
        ("https://relay.example.com/ws", "wss://"),
    ])
    def test_refused(self, url, why):
        assert why in client.relay_url_problem(url)

    def test_the_client_refuses_before_opening_a_connection(self, monkeypatch):
        monkeypatch.setattr(client, "_RELAY_URL", "wss://relay.aria.ai")
        monkeypatch.setattr(client, "_CLIENT_ID", "aria-x")
        connect = mock.Mock(side_effect=AssertionError("must not connect"))
        with mock.patch("websockets.connect", connect), pytest.raises(SystemExit):
            asyncio.run(client._connect_and_serve(once=True))
        connect.assert_not_called()


class TestWhatTheWizardOffers:
    def test_a_fresh_setup_is_offered_the_official_relay(self):
        assert client.default_relay_url("") == client.OFFICIAL_RELAY_URL

    def test_a_saved_foreign_default_is_replaced(self):
        assert client.default_relay_url("wss://relay.aria.ai") == client.OFFICIAL_RELAY_URL

    def test_a_saved_self_hosted_relay_is_kept(self):
        assert client.default_relay_url("wss://relay.example.com/ws") == "wss://relay.example.com/ws"


def test_nothing_still_defaults_to_the_foreign_domain():
    """The domain may appear only in explanations and the refusal list."""
    files = [ROOT / "docker-compose.yml", ROOT / ".env.daemon.template",
             *sorted((ROOT / "src" / "aria_code").rglob("*.py"))]
    offending = []
    for path in files:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "aria.ai" not in line:
                continue
            stripped = line.strip()
            if stripped.startswith("#") or "_UNOWNED_RELAY_HOSTS" in line or "endswith(\".aria.ai\")" in line:
                continue
            offending.append(f"{path.relative_to(ROOT)}:{number}: {stripped}")
    assert not offending, "\n".join(offending)

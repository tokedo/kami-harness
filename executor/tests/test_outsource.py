"""Offline tests for the OUTSOURCE class (2.0.0-dev, H2).

Covers the operator-key storage tool (kamibots_enable_strategies): the
exact request body, the owner-key hard line, and the address echo
check; start_strategy's missing-key error naming the missing step
(status mapping resolved live 2026-07-23: HTTP 403, body "No active
operator key..."); and the class-level degradation mapping
(OUTSOURCE_UNAVAILABLE on connection failure and 5xx for every
strategy-service tool). No network, keys, or chain access.
"""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

import server


@pytest.fixture()
def kb_accounts(accounts):
    """Fabricated accounts with Kamibots credentials attached."""
    for a in accounts.values():
        a.api_key = "kamibots_testkey"
        a.privy_id = "did:privy:test"
    return accounts


class FakeAsyncClient:
    """httpx.AsyncClient stand-in driven by a handler(method, url, kw)."""

    def __init__(self, handler):
        self._handler = handler

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def request(self, method, url, **kw):
        return self._handler(method, url, kw)

    async def post(self, url, **kw):
        return self._handler("POST", url, kw)


def _install(monkeypatch, handler, calls=None):
    def factory(timeout=None):
        def wrapped(method, url, kw):
            if calls is not None:
                calls.append({"method": method, "url": url, **kw})
            return handler(method, url, kw)

        return FakeAsyncClient(wrapped)

    monkeypatch.setattr(server.httpx, "AsyncClient", factory)


def _resp(status, body):
    text = json.dumps(body) if isinstance(body, dict) else str(body)
    return SimpleNamespace(
        status_code=status, text=text,
        json=lambda: body if isinstance(body, dict) else json.loads(text),
    )


class TestEnableStrategies:
    def test_posts_operator_key_exactly(self, kb_accounts, monkeypatch):
        acct = kb_accounts["testa"]
        calls = []
        _install(
            monkeypatch,
            lambda m, u, kw: _resp(
                200, {"success": True, "operatorAddress": acct.operator_addr}
            ),
            calls,
        )
        r = asyncio.run(server.kamibots_enable_strategies(account="testa"))
        assert r == {
            "account": "testa",
            "operator_address": acct.operator_addr,
            "stored": True,
        }
        call = calls[0]
        assert call["method"] == "POST"
        assert call["url"].endswith("/api/agent/operator-key")
        assert call["json"] == {"operatorKey": acct.operator_key}
        assert call["headers"] == {"X-Agent-Key": "kamibots_testkey"}

    def test_owner_key_never_in_request(self, kb_accounts, monkeypatch):
        # A split account: operator and owner are DIFFERENT keys, so the
        # assertion below cannot pass by key coincidence.
        from conftest import KEY_A, KEY_B

        split = server._Account("split", KEY_A, KEY_B)
        split.api_key = "kamibots_testkey"
        monkeypatch.setitem(server._accounts, "split", split)
        calls = []
        _install(
            monkeypatch,
            lambda m, u, kw: _resp(
                200, {"success": True, "operatorAddress": split.operator_addr}
            ),
            calls,
        )
        asyncio.run(server.kamibots_enable_strategies(account="split"))
        blob = json.dumps(calls)
        assert split.operator_key in blob
        # The hard line: no owner private key crosses the wire, ever.
        assert split.owner_key not in blob
        assert split.owner_key != split.operator_key

    def test_address_echo_mismatch_raises(self, kb_accounts, monkeypatch):
        _install(
            monkeypatch,
            lambda m, u, kw: _resp(
                200, {"success": True, "operatorAddress": "0x" + "99" * 20}
            ),
        )
        with pytest.raises(ValueError, match="expects"):
            asyncio.run(server.kamibots_enable_strategies(account="testa"))

    def test_owner_only_account_refuses(self, kb_accounts, monkeypatch):
        # An account without an operator wallet has nothing to store —
        # the operator-key property raises before any request is built.
        owner_only = server._Account("bare", None, kb_accounts["testa"].owner_key)
        owner_only.api_key = "kamibots_testkey"
        monkeypatch.setitem(server._accounts, "bare", owner_only)
        called = []
        _install(monkeypatch, lambda m, u, kw: _resp(200, {}), called)
        with pytest.raises(ValueError, match="no operator wallet"):
            asyncio.run(server.kamibots_enable_strategies(account="bare"))
        assert called == []


class TestStartStrategyMissingKey:
    def test_missing_key_error_names_the_step(self, kb_accounts, monkeypatch):
        _install(
            monkeypatch,
            lambda m, u, kw: _resp(
                403,
                {"error": "No active operator key. Set one up before "
                          "starting strategies."},
            ),
        )
        with pytest.raises(ValueError) as ei:
            asyncio.run(
                server.start_strategy("harvestAndRest", 45, 86, {},
                                      account="testa")
            )
        msg = str(ei.value)
        assert "403" in msg
        assert "No active operator key" in msg
        assert "kamibots_enable_strategies" in msg
        assert "register_kamibots" in msg  # full onboarding order named

    def test_other_403_passes_through_unembellished(
        self, kb_accounts, monkeypatch
    ):
        _install(
            monkeypatch,
            lambda m, u, kw: _resp(403, {"error": "insufficient tier slots"}),
        )
        with pytest.raises(server.StrategyServiceError) as ei:
            asyncio.run(
                server.start_strategy("harvestAndRest", 45, 86, {},
                                      account="testa")
            )
        assert "kamibots_enable_strategies" not in str(ei.value)

    def test_success_passes_through(self, kb_accounts, monkeypatch):
        body = {"id": "x", "containerId": "c", "status": "RUNNING"}
        _install(monkeypatch, lambda m, u, kw: _resp(200, body))
        r = asyncio.run(
            server.start_strategy("harvestAndRest", 45, 86, {},
                                  account="testa")
        )
        assert r == body


class TestOutsourceDegradation:
    """OUTSOURCE is never silently dead: connection failures and 5xx
    raise the distinct OUTSOURCE_UNAVAILABLE error on every
    strategy-service tool."""

    def _tool_calls(self):
        return {
            "get_tier": lambda: server.get_tier(account="testa"),
            "get_all_strategies": lambda: server.get_all_strategies(
                account="testa"),
            "get_all_strategy_statuses":
                lambda: server.get_all_strategy_statuses(account="testa"),
            "get_strategy_status": lambda: server.get_strategy_status(
                45, account="testa"),
            "get_strategy_logs": lambda: server.get_strategy_logs(
                "c1", account="testa"),
            "start_strategy": lambda: server.start_strategy(
                "harvestAndRest", 45, 86, {}, account="testa"),
            "stop_strategy": lambda: server.stop_strategy(
                "45", account="testa"),
            "kamibots_enable_strategies":
                lambda: server.kamibots_enable_strategies(account="testa"),
        }

    def test_connection_failure_raises_unavailable(
        self, kb_accounts, monkeypatch
    ):
        def boom(m, u, kw):
            raise httpx.ConnectError("connection refused")

        _install(monkeypatch, boom)
        for name, call in self._tool_calls().items():
            with pytest.raises(server.OutsourceUnavailableError) as ei:
                asyncio.run(call())
            assert "OUTSOURCE_UNAVAILABLE" in str(ei.value), name

    def test_5xx_raises_unavailable_with_status(
        self, kb_accounts, monkeypatch
    ):
        _install(monkeypatch, lambda m, u, kw: _resp(503, {"error": "down"}))
        with pytest.raises(server.OutsourceUnavailableError) as ei:
            asyncio.run(server.get_tier(account="testa"))
        assert "upstream status 503" in str(ei.value)

    def test_register_kamibots_connection_failure(
        self, kb_accounts, monkeypatch
    ):
        def boom(m, u, kw):
            raise httpx.ConnectError("connection refused")

        _install(monkeypatch, boom)
        with pytest.raises(server.OutsourceUnavailableError):
            asyncio.run(server.register_kamibots(account="testa"))

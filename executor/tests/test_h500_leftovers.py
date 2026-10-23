"""5.0.0 (G) — the transport-vs-chain-fact leftovers of 4.7.0.

G1  The pre-send checks seven tools worded themselves go through the
    shared dry-run gate: a system redeployed between two calls is
    re-resolved and the call lands at the new address (the case where
    every item transfer was refused against the cached old address and
    the re-resolve never ran); a transport failure is retried once and
    otherwise "not performed", never "dry-run reverted".
G2  A deposit's other outcomes after its approve landed — it lands and
    reverts, it is unconfirmed, the node refuses its broadcast outside
    validation — keep their own type and words, and say first that the
    approve landed, with its hash in `landed`.
G3  Transport failures are classified by their CLASS before any text:
    the dry-run gate and the quest probe (an HTTP 4xx included), and a
    broadcast (a transport error whose text happens to carry a refusal
    word is never the node's verdict).
G4  Two of 4.5.0's "known, not changed": a hop refused before signing
    adds no `txs` row; the ledger's own check failing between receipt
    waits is unconfirmed, never an untyped error.

The hermetic node (fakenode.py); synthetic fixtures only.
"""

from __future__ import annotations

import asyncio

import eth_abi
import pytest
import requests
import web3._utils.threads as web3_threads
import web3.exceptions as web3_exceptions

import server
from conftest import KEY_A, KEY_B
from fakenode import FakeNode, Result, VirtualClock, addr_for, make_w3
from test_400_surface import ONYX_TOKEN, portal_env  # noqa: F401
from test_h400_lane import _travel_env
from test_h400_send_path import chain_env  # noqa: F401

OTHER = "0x00000000000000000000000000000000000b0b00"
QUIET = "the transport failed"          # matches no text marker


# ---------------------------------------------------------------------------
# G1 — a system that moves between two calls
# ---------------------------------------------------------------------------

@pytest.fixture()
def moved(monkeypatch):
    node = FakeNode(server.CHAIN_ID)
    w3 = server._install_read_retry(make_w3(node))
    clock = VirtualClock()
    node.clock = clock
    t0, b0 = clock.now, node.block
    clock.on_sleep.append(lambda now: setattr(
        node, "block", max(node.block, b0 + int(now - t0))))
    monkeypatch.setattr(server, "w3", w3)
    monkeypatch.setattr(server, "time", clock)
    monkeypatch.setattr(web3_threads, "time", clock)
    monkeypatch.setattr(server, "_resolve_component", addr_for)
    acct = server._Account("main", KEY_B, KEY_A)
    monkeypatch.setattr(server, "_accounts", {"main": acct})
    aid = int(acct.owner_addr, 16)
    monkeypatch.setattr(server, "_account_id_for_operator", lambda a: aid)
    monkeypatch.setattr(server, "_require_registered_owner", lambda a: aid)
    monkeypatch.setattr(server, "_kami_owner_id", lambda k: aid)
    monkeypatch.setattr(server, "_kami_state", lambda k: "RESTING")
    for comp, sig, typ, val in (
        ("component.name", "safeGet(uint256)", "string", "someone"),
        ("component.state", "safeGet(uint256)", "string", "RESTING"),
        ("component.id.kami.owns", "safeGet(uint256)", "uint256", aid),
        ("component.value", "safeGet(uint256)", "uint256", 0),
        ("component.index.item", "safeGet(uint256)", "uint32", 0),
    ):
        node.handle(addr_for(comp), sig, lambda n, c, a, k, t=typ, v=val:
                    Result(output=eth_abi.encode([t], [v])))
    cache: dict[str, str] = {}
    monkeypatch.setattr(server, "_system_cache", cache)
    monkeypatch.setattr(server, "_resolve_system", lambda sid: (
        cache.setdefault(sid, addr_for(sid))))

    def move(system_id: str, signature: str):
        """The cache holds the system's OLD address, which refuses
        everything (the redeployed system's predecessor)."""
        old = addr_for(system_id + ".OLD")
        cache[system_id] = old
        node.handle(old, signature, lambda n, c, a, k: Result(
            status=0, revert="System: not authorized"))
        return old

    return node, move, cache


MOVED = [
    ("transfer_items", "system.item.transfer",
     "executeTyped(uint32[],uint256[],uint256)",
     lambda: server.transfer_items([11301], [2], to_address=OTHER,
                                   account="main")),
    ("transfer_kami", "system.kami.send", "executeTyped(uint32[],address)",
     lambda: server.transfer_kami([5], to_address=OTHER, account="main")),
    ("sacrifice_kami", "system.kami.sacrifice.commit", "executeTyped(uint32)",
     lambda: server.sacrifice_kami(5, account="main")),
    ("sacrifice_kami_batch", "system.kami.sacrifice.commit",
     "executeTyped(uint32)",
     lambda: server.sacrifice_kami_batch([5], account="main",
                                         delay_seconds=0)),
    ("register_account", "system.account.register",
     "executeTyped(address,string)",
     lambda: server.register_account("walker", account="main")),
    ("equip_all_batch", "system.kami.equip", "executeTyped(uint256,uint32)",
     lambda: server.equip_all_batch([{"kami_id": 5, "item_index": 30001}],
                                    account="main", delay_seconds=0)),
    ("unequip_all_batch", "system.kami.unequip",
     "executeTyped(uint256,string)",
     lambda: server.unequip_all_batch([5], account="main", delay_seconds=0)),
]


@pytest.mark.parametrize("name,system,sig,call", MOVED,
                         ids=[m[0] for m in MOVED])
def test_a_system_that_moved_is_re_resolved_and_the_call_lands(
    moved, name, system, sig, call,
):
    node, move, cache = moved
    old = move(system, sig)
    call()
    landed_at = [t.to for t in node.executed]
    assert landed_at == [addr_for(system).lower()], (name, landed_at)
    assert old.lower() not in landed_at
    assert cache[system] == addr_for(system)


def _flaky(node, system_id, exc, times):
    """The next `times` eth_calls to the system raise `exc` at the
    transport, before the node."""
    provider = server.w3.provider
    inner = provider.make_request
    left = {"n": times}
    to = addr_for(system_id).lower()

    def make_request(method, params):
        if (method == "eth_call" and left["n"] > 0
                and str(params[0].get("to", "")).lower() == to):
            left["n"] -= 1
            raise exc
        return inner(method, params)

    provider.make_request = make_request


def test_a_transport_failure_on_a_pre_send_check_is_retried(moved):
    node, move, cache = moved
    _flaky(node, "system.kami.send",
           requests.exceptions.ChunkedEncodingError(QUIET), 1)
    out = server.transfer_kami([5], to_address=OTHER, account="main")
    assert out["status"] == "success"


def test_a_pre_send_check_that_never_ran_is_not_performed(moved):
    node, move, cache = moved
    _flaky(node, "system.kami.send",
           requests.exceptions.ChunkedEncodingError(QUIET), 2)
    with pytest.raises(server.PreTxValidationError) as ei:
        server.transfer_kami([5], to_address=OTHER, account="main")
    assert "transaction dry-run not performed" in str(ei.value)
    assert "dry-run reverted" not in str(ei.value)
    assert node.executed == []


# ---------------------------------------------------------------------------
# G2 — a deposit's outcomes after its approve landed
# ---------------------------------------------------------------------------

def _onyx_deposit(portal_env, handler=None):  # noqa: F811
    node, game, clock, portal, split = portal_env
    portal.token_bal[(ONYX_TOKEN.lower(), split.owner_addr.lower())] = 10 ** 20
    if handler is not None:
        node.handle(addr_for("system.erc20.portal"),
                    "deposit(uint32,uint256)", handler)
    return node, portal, split


def _says_the_approve_landed(ei, node, portal):
    approve_hash = node.sends[0][2]
    assert len(portal.approvals) == 1
    msg = str(ei.value)
    assert msg.startswith(f"the approve {approve_hash} landed"), msg
    assert getattr(ei.value, "landed", None) == [approve_hash]
    return msg


def test_a_deposit_that_lands_and_reverts_names_the_approve(
    portal_env,  # noqa: F811
):
    node, game, clock, portal, split = portal_env
    plain = portal._deposit
    _onyx_deposit(portal_env, lambda n, c, a, k: (
        Result(status=0, revert="Token Portal: disabled") if k
        else plain(n, c, a, k)))
    with pytest.raises(server.OnChainRevertError) as ei:
        server.portal_deposit(100, 1_000, account="split")
    msg = _says_the_approve_landed(ei, node, portal)
    assert "REVERTED" in msg and ei.value.tx_hash in msg


def test_an_unconfirmed_deposit_names_the_approve(
    portal_env,  # noqa: F811
):
    node, game, clock, portal, split = portal_env
    plain = portal._deposit

    def deposit(n, c, a, k):
        if portal.approvals:
            n.hold_mining = True         # the deposit is held, never mined
        return plain(n, c, a, k)

    _onyx_deposit(portal_env, deposit)
    with pytest.raises(server.TxUnconfirmedError) as ei:
        server.portal_deposit(100, 1_000, account="split")
    msg = _says_the_approve_landed(ei, node, portal)
    assert "UNCONFIRMED" in msg


def test_a_deposit_broadcast_the_node_refuses_names_the_approve(
    portal_env,  # noqa: F811
):
    node, game, clock, portal, split = portal_env
    _onyx_deposit(portal_env)
    node.fail("eth_sendRawTransaction", times=10, error={
        "code": -32000, "message": "insufficient funds for gas * price"},
        when=lambda p: bool(portal.approvals))
    with pytest.raises(Exception) as ei:
        server.portal_deposit(100, 1_000, account="split")
    assert not isinstance(ei.value, server.PreTxValidationError)
    msg = _says_the_approve_landed(ei, node, portal)
    assert "insufficient funds" in msg


# ---------------------------------------------------------------------------
# G3 — classified by class before text
# ---------------------------------------------------------------------------

def _quiet_transport_errors():
    return [
        requests.exceptions.HTTPError(
            "400 Client Error: Bad Request for url: https://rpc.example/"),
        requests.exceptions.HTTPError(QUIET),
        requests.exceptions.ChunkedEncodingError(QUIET),
        requests.exceptions.ConnectionError(QUIET),
        requests.exceptions.Timeout(QUIET),
        web3_exceptions.ProviderConnectionError(QUIET),
        web3_exceptions.RequestTimedOut(QUIET),
        ConnectionError(QUIET),
        TimeoutError(QUIET),
        OSError(QUIET),
    ]


@pytest.mark.parametrize("exc", _quiet_transport_errors(),
                         ids=lambda e: f"{type(e).__name__}:{str(e)[:12]}")
def test_the_dry_run_gate_reads_a_transport_class_as_not_performed(
    monkeypatch, exc,
):
    calls = []

    class Fn:
        args = [1]

        def call(self, params=None, block_identifier=None):
            calls.append(1)
            raise exc

    monkeypatch.setattr(server.time, "sleep", lambda s: None)
    with pytest.raises(server.PreTxValidationError) as ei:
        server._dry_run(Fn(), "0x" + "ab" * 20)
    assert len(calls) == 2                       # retried once
    assert getattr(ei.value, "infrastructure", False) is True
    assert "dry-run reverted" not in str(ei.value)


def test_the_quest_probe_reads_a_transport_class_as_no_revert(
    chain_env,  # noqa: F811
):
    node, game, clock, op = chain_env
    acc_id = server._account_entity_id("testa")
    node.handle(addr_for("component.id.quest.owns"), "safeGet(uint256)",
                lambda n, c, a, k: Result(
                    output=eth_abi.encode(["uint256"], [acc_id])))
    node.handle(addr_for("component.is.complete"), "has(uint256)",
                lambda n, c, a, k: Result(
                    output=eth_abi.encode(["bool"], [False])))
    quest_sys = addr_for("system.quest.complete").lower()
    provider = server.w3.provider
    inner = provider.make_request

    def make_request(method, params):
        if method == "eth_call" and str(
                params[0].get("to", "")).lower() == quest_sys:
            raise requests.exceptions.HTTPError(
                "404 Client Error: Not Found for url: https://rpc.example/")
        return inner(method, params)

    provider.make_request = make_request
    r = server.quest_state(48, account="testa")
    assert r["revert_reason"] is None, r


def test_a_transport_error_is_never_the_nodes_broadcast_verdict():
    exc = requests.exceptions.ConnectionError(
        "Max retries exceeded (NameResolutionError: host does not exist)")
    assert server._classify_send_error(str(exc), exc) == "ambiguous"
    # the node's own JSON-RPC words are still read
    assert server._classify_send_error(
        "nonce too low", ValueError("nonce too low")) == "stale"
    assert server._classify_send_error(
        "insufficient funds for gas", ValueError("x")) == "definitive"


def test_a_broadcast_lost_in_transport_is_re_offered_and_lands(
    chain_env, monkeypatch,  # noqa: F811
):
    """The first broadcast never reaches the node and its transport text
    carries "does not exist": not a definitive refusal (an unfunded
    wallet), so the same bytes are re-offered and land."""
    node, game, clock, op = chain_env
    game.inv[11301] = 5
    provider = server.w3.provider
    inner = provider.make_request
    left = {"n": 1}

    def make_request(method, params):
        if method == "eth_sendRawTransaction" and left["n"]:
            left["n"] -= 1
            raise requests.exceptions.ConnectionError(
                "Max retries exceeded (NameResolutionError: host does not "
                "exist)")
        return inner(method, params)

    provider.make_request = make_request
    out = server.feed_kami(7, 11301, account="testa")
    assert out["status"] == "success"
    assert game.inv[11301] == 4


# ---------------------------------------------------------------------------
# G4 — two of 4.5.0's "known, not changed"
# ---------------------------------------------------------------------------

def test_a_hop_refused_before_signing_adds_no_row(accounts, monkeypatch):
    _travel_env(monkeypatch, 100, [1, 2, 3, 4])
    calls = []

    def send(account, system_id, abi, args, gas_limit=None, **kw):
        calls.append(args)
        if len(calls) == 2:
            raise server.PreTxValidationError("dry-run reverted: nope")
        return {"tx_hash": f"0x{len(calls):02x}", "status": "success",
                "block": 9, "gas_used": 1_000, "fee_wei": "1"}

    monkeypatch.setattr(server, "_send_tx_retry", send)
    r = asyncio.run(server.travel_to_room(4, account="testa",
                                          allow_partial=True))
    assert len(calls) == 2
    assert [t.get("tx_hash") for t in r["txs"]] == ["0x01"]
    assert "nope" in r["error"]


def test_a_failing_ledger_check_between_waits_is_unconfirmed(
    chain_env, monkeypatch,  # noqa: F811
):
    node, game, clock, op = chain_env
    game.inv[11301] = 5
    node.hold_mining = True

    def broken(tx_hash):
        raise KeyError("ledger entry vanished")

    monkeypatch.setattr(server, "_check_inflight", broken)
    with pytest.raises(server.TxUnconfirmedError) as ei:
        server.feed_kami(7, 11301, account="testa")
    assert "the check between receipt waits failed" in ei.value.reason
    assert "ledger entry vanished" in ei.value.reason

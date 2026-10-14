"""4.7.0 — three truths.

1  A transport failure never stands in for a chain fact. The landed-revert
   replay (`_replay_once`) reads a transport failure — by class (requests'
   RequestException, web3's provider and connection errors,
   ConnectionError, TimeoutError, OSError) or by text (an HTTP error
   status line, "max retries", "http error") — as a replay that did not
   run; revert data the error carries still decodes first. A reverted
   `act_sequence` row whose replay could not say why carries `reason`
   "revert reason unavailable (replay inconclusive)" — present, never
   absent, never the transport's text. The text markers are the list the
   dry-run gate and the quest probe share, so a dry-run hit by such a
   failure is "dry-run not performed ... (infrastructure, not a game
   revert)" after its one retry, never "dry-run reverted: 503 ...", and
   `quest_state`'s `revert_reason` is None. Found 2026-10-13: a reverted
   liquidate inside a sequence carried the RPC's 503 text as its reason.
2  A roster label matches in any case on every tool that takes one —
   writes, `lens_receipts`, `get_gas_balance`, a transfer's `to_account`
   (the lens reads have since 4.4.0). A label no roster entry has fails
   with the 4.6.1 message, byte for byte.
3  A deposit refused after its approve landed says so first. Every
   refusal between the approve's landing and the deposit's signing
   raises `RefusedAfterLandedError` (a PreTxValidationError), whose
   message begins "the approve <hash> landed ..." and never says no
   transaction was sent; a deposit refused before any approve keeps the
   4.6.1 text.

Hermetic: the fake node of the 4.0.0 tests (a real Web3 over a simulated
JSON-RPC node, on a virtual clock) and the doubles of the earlier suites.
"""

from __future__ import annotations

import json
import traceback
from types import SimpleNamespace

import eth_abi
import pytest
import requests
import web3.exceptions as web3_exceptions

import server
from conftest import FakeContract
from fakenode import Result, addr_for
from test_400_surface import ETH_TOKEN, ONYX_TOKEN, portal_env  # noqa: F401
from test_gas_wallet import gas_env  # noqa: F401
from test_h400_send_path import chain_env  # noqa: F401
from test_h420_families import PRICE, WEI, ITEMS, APPROVE_BOUND, _fund
from test_transfers import _kami_chain

# What requests' raise_for_status() says for an HTTP 503 from the public
# endpoint: the text the 2026-10-13 row carried as its "reason".
PROD_503 = ("503 Server Error: Service Unavailable for url: "
            "https://jsonrpc-yominet-1.anvil.asia-southeast.initia.xyz/")
KILLER, VICTIM = 31, 41
LIQ = {"op": "liquidate", "kami_id": KILLER, "victim_kami_id": VICTIM}


# ---------------------------------------------------------------------------
# 1 — a transport failure never stands in for a chain fact
# ---------------------------------------------------------------------------

def _replay_w3(monkeypatch, exc):
    """A client whose eth_call raises `exc`; its head is far ahead."""
    def call(*a, **k):
        raise exc
    monkeypatch.setattr(server, "w3", SimpleNamespace(
        eth=SimpleNamespace(call=call, block_number=10 ** 9)))


def _transport_errors():
    """Every transport class the replay must read as not having run,
    each with a text that matches no marker: the class alone decides."""
    text = "the transport failed"
    return [
        requests.exceptions.HTTPError(text),
        requests.exceptions.ConnectionError(text),
        requests.exceptions.Timeout(text),
        requests.exceptions.RequestException(text),
        web3_exceptions.ProviderConnectionError(text),
        web3_exceptions.PersistentConnectionError(text),
        web3_exceptions.RequestTimedOut(text),
        ConnectionError(text),
        TimeoutError(text),
        OSError(text),
    ]


def test_a_503_on_the_replay_is_a_replay_that_did_not_run(monkeypatch):
    """(a) The production failure: the HTTP-503 class with its own text."""
    _replay_w3(monkeypatch, requests.exceptions.HTTPError(PROD_503))
    assert server._replay_once({"to": "0x" + "22" * 20}, 1001) == (None, False)


@pytest.mark.parametrize("exc", _transport_errors(),
                         ids=lambda e: type(e).__name__)
def test_every_transport_class_is_a_replay_that_did_not_run(monkeypatch, exc):
    _replay_w3(monkeypatch, exc)
    assert server._replay_once({"to": "0x" + "22" * 20}, 1001) == (None, False)


@pytest.mark.parametrize("text", [
    PROD_503,
    "502 Server Error: Bad Gateway for url: https://rpc.example/",
    "504 Server Error: Gateway Timeout for url: https://rpc.example/",
    "Service Unavailable",
    "HTTPSConnectionPool(host='rpc.example', port=443): Max retries "
    "exceeded with url: /",
    "HTTP Error 500",
])
def test_a_transport_text_is_an_infrastructure_text(text):
    """By text too, in the list the replay, the dry-run gate and the
    quest probe share; a revert's own text is still not one."""
    assert server._is_replay_infra_error(text)
    assert not server._is_replay_infra_error(
        "execution reverted: objs not met")


def test_revert_data_still_decodes_first(monkeypatch):
    """(c) A replay that returns real revert data yields the decoded
    reason — even when the error that carries it is a transport class."""
    payload = "0x08c379a0" + eth_abi.encode(
        ["string"], ["not enough MUSU"]).hex()
    err = {"code": 3, "message": "execution reverted: not enough MUSU",
           "data": payload}
    _replay_w3(monkeypatch, ValueError(err))
    assert server._replay_once({"to": "0x" + "22" * 20}, 7) == (
        "not enough MUSU", True)
    _replay_w3(monkeypatch, requests.exceptions.HTTPError(err))
    assert server._replay_once({"to": "0x" + "22" * 20}, 7) == (
        "not enough MUSU", True)


def test_a_single_send_revert_says_unavailable_never_the_503(monkeypatch):
    """The single-send error renders `reason or REPLAY_UNAVAILABLE`; the
    exception's own `reason` stays None when nothing was recovered."""
    _replay_w3(monkeypatch, requests.exceptions.HTTPError(PROD_503))
    receipt = SimpleNamespace(status=0, blockNumber=1001, gasUsed=120_000,
                              transactionHash=bytes.fromhex("ab" * 32))
    built = {"from": "0x" + "11" * 20, "to": "0x" + "22" * 20,
             "data": "0x12345678", "gas": 500_000}
    with pytest.raises(server.OnChainRevertError) as ei:
        server._receipt_outcome(receipt, built)
    assert ei.value.reason is None
    msg = str(ei.value)
    assert server.REPLAY_UNAVAILABLE in msg
    assert "503" not in msg and "Server Error" not in msg


def _reverting_liquidate(node):
    """The liquidate passes its dry-run and reverts when it lands."""
    def run(n, caller, args, commit):
        if commit:
            return Result(status=0, revert="target not liquidatable",
                          gas_used=120_000)
        return Result(gas_used=900_000)
    node.handle(addr_for("system.harvest.liquidate"),
                "executeTyped(uint256,uint256)", run)


def _replay_raises(exc):
    """Every eth_call at a numbered block — the replay of a landed
    transaction; the gates call at `latest` — raises `exc` in the
    transport, before the node, as requests does for an HTTP 503."""
    provider = server.w3.provider
    inner = provider.make_request
    seen = []

    def make_request(method, params):
        if (method == "eth_call" and len(params) > 1
                and str(params[1]).startswith("0x")):
            seen.append(params[1])
            raise exc
        return inner(method, params)

    provider.make_request = make_request
    return seen


def _texts(out: dict) -> list[str]:
    """Every string the call returns except hashes: the row's fields and
    the notice."""
    row = out["steps"][0]
    return [v for k, v in row.items()
            if isinstance(v, str) and k != "tx_hash"] + [out.get("notice", "")]


@pytest.mark.parametrize("receipts", ["batched", "one-by-one"])
def test_a_reverted_row_whose_replay_met_a_503_says_unavailable(
    chain_env, monkeypatch, receipts,  # noqa: F811
):
    """(b) The 2026-10-13 row, on both receipt paths: `reverted`, `reason`
    REPLAY_UNAVAILABLE, and the 503 nowhere in the row or the notice."""
    node, game, clock, op = chain_env
    _reverting_liquidate(node)
    if receipts == "one-by-one":
        monkeypatch.setattr(server, "_batch_receipts", lambda hashes: None)
    seen = _replay_raises(requests.exceptions.HTTPError(PROD_503))

    out = server.act_sequence([LIQ], account="testa")

    assert seen, "the replay never ran"
    row = out["steps"][0]
    assert row["status"] == "reverted", row
    assert row["reason"] == server.REPLAY_UNAVAILABLE, row
    assert all("503" not in t for t in _texts(out)), out
    assert "Server Error" not in json.dumps(out), out
    assert out["landed"] == 0 and out["sent"] == 1


@pytest.mark.parametrize("receipts", ["batched", "one-by-one"])
def test_a_reverted_row_always_carries_a_reason(
    chain_env, monkeypatch, receipts,  # noqa: F811
):
    """The replay ran clean at the block and its neighbours: nothing was
    recovered, and the row says so instead of omitting `reason`."""
    node, game, clock, op = chain_env
    _reverting_liquidate(node)
    if receipts == "one-by-one":
        monkeypatch.setattr(server, "_batch_receipts", lambda hashes: None)
    out = server.act_sequence([LIQ], account="testa")
    row = out["steps"][0]
    assert row["status"] == "reverted", row
    assert row["reason"] == server.REPLAY_UNAVAILABLE, row


def test_a_recovered_reason_still_reaches_the_row(chain_env):  # noqa: F811
    """(c) on the sequence: a replay that reverts with a reason puts that
    reason on the row, as before."""
    node, game, clock, op = chain_env

    def run(n, caller, args, commit):
        return Result(status=0, revert="target not liquidatable",
                      gas_used=120_000) if (commit or node.executed) else (
            Result(gas_used=900_000))
    node.handle(addr_for("system.harvest.liquidate"),
                "executeTyped(uint256,uint256)", run)
    out = server.act_sequence([LIQ], account="testa")
    row = out["steps"][0]
    assert row["status"] == "reverted", row
    assert row["reason"] == "target not liquidatable", row


def test_a_dry_run_hit_by_a_503_is_not_performed_never_reverted(monkeypatch):
    """(ii) The gate retries once, then says the node did not run it."""
    calls = []

    class Fn:
        args = [1]

        def call(self, params=None):
            calls.append(1)
            raise requests.exceptions.HTTPError(PROD_503)

    monkeypatch.setattr(server.time, "sleep", lambda s: None)
    with pytest.raises(server.PreTxValidationError) as ei:
        server._dry_run(Fn(), "0xabc")
    msg = str(ei.value)
    assert len(calls) == 2
    assert getattr(ei.value, "infrastructure", False) is True
    assert "transaction dry-run not performed" in msg
    assert "infrastructure, not a game revert" in msg
    assert "dry-run reverted" not in msg


def test_a_quest_probe_hit_by_a_503_names_no_revert(chain_env):  # noqa: F811
    """(iii) quest_state: an owned, incomplete quest whose completion
    probe met the transport's 503 states no revert reason."""
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
            raise requests.exceptions.HTTPError(PROD_503)
        return inner(method, params)

    provider.make_request = make_request
    r = server.quest_state(48, account="testa")
    assert r["owned"] is True and r["completed"] is False
    assert r["revert_reason"] is None, r
    assert r["state"] == "active_blocked"


# ---------------------------------------------------------------------------
# 2 — a roster label matches in any case on every tool
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("label", ["TESTA", "TestA", "testa"])
def test_get_account_matches_a_label_in_any_case(accounts, label):
    assert server._get_account(label) is accounts["testa"]


def test_a_label_no_roster_entry_has_fails_as_before(accounts):
    for label in ("TESTX", "testx", " testa"):
        with pytest.raises(ValueError) as ei:
            server._get_account(label)
        assert str(ei.value) == (
            f"Account '{label}' not found. Available: testa, testb, noown")


def test_a_write_with_an_upper_case_label_signs_with_that_account(
    chain_env,  # noqa: F811
):
    node, game, clock, op = chain_env
    game.xp[server._kami_entity_id(5)] = 1_000
    assert server.level_up_kami(5, account="TESTA")["status"] == "success"
    game.xp[server._kami_entity_id(5)] = 1_000
    assert server.level_up_kami(5, account="testa")["status"] == "success"
    senders = [s for s, _n, _h in node.sends]
    assert senders == [op.lower(), op.lower()], senders


def test_lens_receipts_with_an_upper_case_label_reads_that_account(
    accounts, monkeypatch,
):
    asked = []
    monkeypatch.setattr(server, "_lens_request",
                        lambda q, args, **kw: asked.append((q, args)) or {})
    server.lens_receipts("TESTA")
    server.lens_receipts("testa")
    assert asked == [("receipts", [accounts["testa"].owner_addr])] * 2


def test_gas_balance_with_an_upper_case_label_is_that_account(gas_env):  # noqa: F811
    upper = server.get_gas_balance(account="SOLO")
    lower = server.get_gas_balance(account="solo")
    assert list(upper["balances"]) == ["solo"]
    assert upper == lower


def test_a_transfer_to_an_upper_case_label_goes_to_that_account(
    accounts, chain, sent,
):
    _kami_chain(chain, owner_eid=server._account_entity_id("testa"))
    r = server.transfer_kami([5], to_account="TESTB", account="TESTA")
    assert r["status"] == "success"
    assert r["destination_operator"] == accounts["testb"].operator_addr
    assert r["per_kami"][0]["owned_by_source"] is True


def test_the_lens_label_match_and_the_write_match_are_one_rule(accounts):
    for label in ("TESTA", "TestA", "testa"):
        assert server._roster_label(label) is server._get_account(label)


# ---------------------------------------------------------------------------
# 3 — a deposit refused after its approve landed says so first
# ---------------------------------------------------------------------------

def _deposit_refused_after_the_approve(node, portal):
    """The deposit's dry-run passes until the approve has landed, then
    reverts (the portal was disabled in between)."""
    plain = portal._deposit
    node.handle(addr_for("system.erc20.portal"), "deposit(uint32,uint256)",
                lambda n, c, a, k: (
                    Result(status=0, revert="Token Portal: disabled")
                    if portal.approvals else plain(n, c, a, k)))


def _raised_through(ei) -> list[str]:
    """The functions the refusal passed through: the raise, and the
    refusal it wraps (its __cause__), if any."""
    names = [e.name for e in ei.traceback]
    cause = ei.value.__cause__
    if cause is not None:
        names += [f.name for f in traceback.extract_tb(cause.__traceback__)]
    return names


def _assert_says_the_approve_landed(ei, node, portal):
    assert len(node.sends) == 1 and len(portal.approvals) == 1
    approve_hash = node.sends[0][2]
    msg = str(ei.value)
    assert msg.startswith(f"the approve {approve_hash} landed"), msg
    assert "no transaction sent" not in msg, msg
    assert getattr(ei.value, "landed", None) == [approve_hash]
    return msg


@pytest.mark.parametrize("item, token, items", [
    (100, ONYX_TOKEN, 1_000),      # not the gas token: _portal_send's dry-run
    (103, ETH_TOKEN, 50_000),      # the gas token: the deposit's own estimate
], ids=["onyx", "gas-token"])
def test_a_deposit_refused_after_its_approve_says_the_approve_landed(
    portal_env, item, token, items,  # noqa: F811
):
    node, game, clock, portal, split = portal_env
    portal.token_bal[(token.lower(), split.owner_addr.lower())] = 10 ** 20
    _deposit_refused_after_the_approve(node, portal)
    with pytest.raises(server.PreTxValidationError) as ei:
        server.portal_deposit(item, items, account="split")
    msg = _assert_says_the_approve_landed(ei, node, portal)
    assert msg.endswith("Token Portal: disabled', '0x08c379a0"
                        + eth_abi.encode(["string"],
                                         ["Token Portal: disabled"]).hex()
                        + "')"), msg


def test_the_gas_token_gate_after_the_approve_says_the_approve_landed(
    portal_env,  # noqa: F811
):
    """The deposit's own fee bound, checked once its allowance exists
    (4.2.0's lead), now with no prefix in front of it."""
    node, game, clock, portal, split = portal_env
    plain = portal._deposit

    def heavy_deposit(n, caller, args, commit):
        res = plain(n, caller, args, commit)
        return Result(status=res.status, gas_used=1_300_000, logs=res.logs,
                      revert=res.revert, output=res.output)

    node.handle(addr_for("system.erc20.portal"), "deposit(uint32,uint256)",
                heavy_deposit)
    est_bound = server._DEPOSIT_GAS_ESTIMATE * PRICE + 1
    _fund(portal, split, WEI + APPROVE_BOUND + est_bound, allowance=0)
    with pytest.raises(server.PreTxValidationError) as ei:
        server.portal_deposit(103, ITEMS, account="split")
    msg = _assert_says_the_approve_landed(ei, node, portal)
    assert msg.count("the approve ") == 1, msg
    assert "gas token" in msg


def test_a_deposit_refused_by_its_revalidation_says_the_approve_landed(
    portal_env, monkeypatch,  # noqa: F811
):
    """The third route: the deposit's send drained an earlier call's armed
    tail, so the lane re-ran the deposit's dry-run just before signing."""
    node, game, clock, portal, split = portal_env
    portal.token_bal[(ONYX_TOKEN.lower(), split.owner_addr.lower())] = 10 ** 20
    state = {"refuse": False}
    plain = portal._deposit
    node.handle(addr_for("system.erc20.portal"), "deposit(uint32,uint256)",
                lambda n, c, a, k: (
                    Result(status=0, revert="Token Portal: disabled")
                    if state["refuse"] else plain(n, c, a, k)))
    prepared = []
    real = server._lane_prepare

    def prepare(lane, addr, key, ctl):
        prepared.append(addr)
        drained = real(lane, addr, key, ctl)
        if len(prepared) == 2:          # the deposit's send
            state["refuse"] = True
            return True
        return drained

    monkeypatch.setattr(server, "_lane_prepare", prepare)
    with pytest.raises(server.PreTxValidationError) as ei:
        server.portal_deposit(100, 1_000, account="split")
    assert len(prepared) == 2
    assert "_lane_send" in _raised_through(ei)
    _assert_says_the_approve_landed(ei, node, portal)


def test_a_deposit_refused_before_any_approve_keeps_the_4_6_1_text(
    portal_env,  # noqa: F811
):
    node, game, clock, portal, split = portal_env
    owner = split.owner_addr.lower()
    portal.token_bal[(ONYX_TOKEN.lower(), owner)] = 10 ** 20
    portal.allowance[(ONYX_TOKEN.lower(), owner)] = 10 ** 20
    node.handle(addr_for("system.erc20.portal"), "deposit(uint32,uint256)",
                lambda n, c, a, k: Result(status=0,
                                          revert="Token Portal: disabled"))
    with pytest.raises(server.PreTxValidationError) as ei:
        server.portal_deposit(100, 1_000, account="split")
    assert type(ei.value) is server.PreTxValidationError
    assert not node.sends
    data = "0x08c379a0" + eth_abi.encode(
        ["string"], ["Token Portal: disabled"]).hex()
    assert str(ei.value) == (
        "validation failed; no transaction sent: transaction dry-run "
        f"reverted: ('execution reverted: Token Portal: disabled', '{data}')")


def test_the_refusal_after_a_landing_keeps_the_refusal_it_wraps():
    """The class: a PreTxValidationError (every handler that catches one
    still does), the lead in place of the prefix, the refusal's own
    detail, mechanics and infrastructure flag, and what landed."""
    first = server.PreTxValidationError("transaction dry-run not performed")
    first.mechanics = " [mechanics] x"
    first.infrastructure = True
    lead = server._approve_landed_lead("0x" + "ab" * 32)
    e = server.RefusedAfterLandedError(first, lead, ["0x" + "ab" * 32])
    assert isinstance(e, server.PreTxValidationError)
    assert str(e) == lead + "transaction dry-run not performed [mechanics] x"
    assert e.detail == first.detail and e.mechanics == first.mechanics
    assert e.infrastructure is True
    assert e.landed == ["0x" + "ab" * 32]
    assert lead == (
        f"the approve {'0x' + 'ab' * 32} landed (its allowance stays, so a "
        f"later deposit sends no approve); the deposit itself is refused "
        f"before signing it: ")
    assert server.PreTxValidationError.PREFIX == (
        "validation failed; no transaction sent: ")

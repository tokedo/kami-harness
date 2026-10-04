"""4.3.0 — the last release before the freeze (part 1).

J1  `dry_run` on portal_deposit, portal_claim and portal_cancel
J2  a fee total wherever a result sums gas; gas fields on gap-fill rows
J3  the two lane texts 4.2.0 left behind; fund_operator states the
    prepayment

All hermetic: the fake portal and fake node of the 4.0.0 / 4.2.0 tests.
"""

from __future__ import annotations

import asyncio

import pytest

import server
from fakenode import READINESS_ERROR
from test_400_surface import ETH_TOKEN, ONYX_TOKEN, portal_env  # noqa: F401
from test_h400_lane import _travel_env
from test_h400_send_path import _feeds, _refuse_nonce
from test_h400_send_path import chain_env  # noqa: F401  (fixture)

PRICE = 2_500_000                     # the flat price, wei per gas
# The fake portal's estimates x 1.5 (the limits the portal sends with),
# and the prepayment bound _gas_fee_bound states for each (+ 1 wei).
DEPOSIT_BOUND = 750_000 * PRICE + 1   # deposit: 500,000 -> 750,000
APPROVE_BOUND = 90_000 * PRICE + 1    # approve:  60,000 ->  90,000
SETTLE_BOUND = 450_000 * PRICE + 1    # claim / cancel: 300,000 -> 450,000
ITEMS = 5                             # Ether Shard 103, scale 5
WEI = ITEMS * 10 ** 13


def _fund(portal, split, held, allowance, token=ETH_TOKEN):
    owner, t = split.owner_addr.lower(), token.lower()
    portal.token_bal[(t, owner)] = held
    portal.allowance[(t, owner)] = allowance


def _no_terminal_state(out):
    """A dry run has no terminal state (SPEC P4): no status, no hash."""
    assert out["dry_run"] is True
    for k in ("status", "tx_hash", "block", "gas_used", "fee_wei", "txs"):
        assert k not in out, (k, out)


# ---------------------------------------------------------------------------
# J1 — dry_run on the three portal tools that lacked it
# ---------------------------------------------------------------------------

def test_a_deposit_dry_run_quotes_and_signs_nothing(portal_env):  # noqa: F811
    """Allowance covering: the token amount, no approve, the deposit's fee
    bound, the gas-token rule's verdict — and not one transaction."""
    node, game, clock, portal, split = portal_env
    _fund(portal, split, WEI + DEPOSIT_BOUND, allowance=WEI)
    out = server.portal_deposit(103, ITEMS, account="split", dry_run=True)
    _no_terminal_state(out)
    assert not node.sends
    assert out["token"]["amount_wei"] == str(WEI)
    assert out["credited"] == ITEMS - 1                  # tax 1
    assert out["approve_needed"] is False
    assert out["approve_fee_bound_wei"] is None
    assert out["deposit_fee_bound_wei"] == str(DEPOSIT_BOUND)
    assert out["gas_token"] is True and out["gas_token_rule"] == "passes"
    assert game.inv[103] == 200_000                      # nothing deposited


def test_a_deposit_dry_run_refuses_as_the_real_call_does(portal_env):  # noqa: F811
    """The gas-token rule's refusal, with zero transactions: the same
    PreTxValidationError a real call raises."""
    node, game, clock, portal, split = portal_env
    _fund(portal, split, WEI + DEPOSIT_BOUND - 1, allowance=WEI)
    with pytest.raises(server.PreTxValidationError) as dry:
        server.portal_deposit(103, ITEMS, account="split", dry_run=True)
    with pytest.raises(server.PreTxValidationError) as real:
        server.portal_deposit(103, ITEMS, account="split")
    assert str(dry.value) == str(real.value)
    assert "1 wei short" in str(dry.value)
    assert not node.sends


def test_a_deposit_dry_run_with_a_short_allowance_signs_no_approve(
    portal_env,  # noqa: F811
):
    """The approve would be needed: the dry run says so, states its bound,
    and signs nothing — not even the approve. The deposit cannot be
    estimated before its allowance exists, so its bound is null and the
    verdict says what was checked."""
    node, game, clock, portal, split = portal_env
    _fund(portal, split, WEI + APPROVE_BOUND, allowance=0)
    out = server.portal_deposit(103, ITEMS, account="split", dry_run=True)
    _no_terminal_state(out)
    assert not node.sends and not portal.approvals
    assert out["approve_needed"] is True
    assert out["approve_fee_bound_wei"] == str(APPROVE_BOUND)
    assert out["deposit_fee_bound_wei"] is None
    assert out["gas_token_rule"].startswith("approve stage passes")

    _fund(portal, split, WEI + APPROVE_BOUND - 1, allowance=0)
    with pytest.raises(server.PreTxValidationError, match="1 wei short"):
        server.portal_deposit(103, ITEMS, account="split", dry_run=True)
    assert not node.sends and not portal.approvals


def test_a_deposit_dry_run_of_a_token_that_is_not_the_gas_token(portal_env):  # noqa: F811
    node, game, clock, portal, split = portal_env
    wei = 1_000 * 10 ** 16
    _fund(portal, split, wei, allowance=wei, token=ONYX_TOKEN)
    out = server.portal_deposit(100, 1_000, account="split", dry_run=True)
    _no_terminal_state(out)
    assert not node.sends
    assert out["gas_token"] is False
    assert out["gas_token_rule"] == "not the gas token"
    assert out["deposit_fee_bound_wei"] == str(DEPOSIT_BOUND)


def _receipt_at(portal_env, to="operator", wait=True):  # noqa: F811
    node, game, clock, portal, split = portal_env
    rid = server.portal_withdraw(103, 100_000, to=to,
                                 account="split")["receipt_id"]
    if wait:
        clock.sleep(43_201)
    return rid


def test_a_claim_dry_run_states_payee_route_amount_and_signs_nothing(
    portal_env,  # noqa: F811
):
    node, game, clock, portal, split = portal_env
    rid = _receipt_at(portal_env)
    sent = len(node.sends)
    out = server.portal_claim(rid, account="split", dry_run=True)
    _no_terminal_state(out)
    assert len(node.sends) == sent
    assert int(rid, 16) in portal.receipts               # still pending
    assert out["receipt_id"] == rid and out["route"] == "operator"
    assert out["payee"].lower() == split.operator_addr.lower()
    assert out["amount_wei"] == str(99_499 * 10 ** 13)
    assert out["amount"] == "0.99499"
    assert out["claimable_now"] is True
    assert out["fee_bound_wei"] == str(SETTLE_BOUND)


def test_a_claim_dry_run_before_the_delay_refuses_as_the_real_call_does(
    portal_env,  # noqa: F811
):
    node, game, clock, portal, split = portal_env
    rid = _receipt_at(portal_env, wait=False)
    sent = len(node.sends)
    with pytest.raises(server.PreTxValidationError) as dry:
        server.portal_claim(rid, account="split", dry_run=True)
    with pytest.raises(server.PreTxValidationError) as real:
        server.portal_claim(rid, account="split")
    assert str(dry.value) == str(real.value)
    assert "claimable at" in str(dry.value)
    assert len(node.sends) == sent


def test_a_claim_dry_run_names_a_payee_that_is_not_this_server(portal_env):  # noqa: F811
    node, game, clock, portal, split = portal_env
    rid = _receipt_at(portal_env)
    portal.operator = ("0x" + "ab" * 20)
    out = server.portal_claim(rid, account="split", dry_run=True)
    assert next(iter(out)) == "notice" and "as of this claim" in out["notice"]
    assert out["payee"].lower() == "0x" + "ab" * 20


def test_a_cancel_dry_run_states_items_and_tax_and_signs_nothing(
    portal_env,  # noqa: F811
):
    node, game, clock, portal, split = portal_env
    rid = _receipt_at(portal_env, to="owner", wait=False)
    sent, inv = len(node.sends), game.inv[103]
    out = server.portal_cancel(rid, account="split", dry_run=True)
    _no_terminal_state(out)
    assert len(node.sends) == sent and game.inv[103] == inv
    assert int(rid, 16) in portal.receipts
    assert out["receipt_id"] == rid
    assert out["items_refunded"] == 99_499 and out["tax_not_refunded"] == 501
    assert out["fee_bound_wei"] == str(SETTLE_BOUND)


def test_the_three_portal_tools_take_an_optional_dry_run():
    tools = {t.name: t for t in server.mcp._tool_manager.list_tools()}
    for name in ("portal_deposit", "portal_claim", "portal_cancel"):
        props = tools[name].parameters["properties"]
        assert props.get("dry_run", {}).get("default") is False, name
        assert "dry_run" not in tools[name].parameters.get("required", [])
        assert "dry_run" in tools[name].description, name


# ---------------------------------------------------------------------------
# J2 — a fee total where a tool sums gas; gas fields on gap-fill rows
# ---------------------------------------------------------------------------

def _hops(monkeypatch, outcomes):
    """travel's hop sender: each outcome is a fee string, None (a landed
    hop whose fee legs were not identified), "revert" or "refuse"."""
    calls = []

    def send(account, system_id, abi, args, gas_limit=None, **kw):
        calls.append(args)
        o = outcomes[len(calls) - 1]
        if o == "revert":
            raise server.OnChainRevertError(f"0x{len(calls):02x}", 9,
                                            70_000, "AccMove: nope")
        if o == "refuse":
            raise server.PreTxValidationError("dry-run reverted: nope")
        return {"tx_hash": f"0x{len(calls):02x}", "status": "success",
                "block": 9, "gas_used": 1_000, "fee_wei": o}

    monkeypatch.setattr(server, "_send_tx_retry", send)


def _travel(**kw):
    return asyncio.run(server.travel_to_room(4, account="testa", **kw))


def test_travel_states_the_fee_total_of_its_hops(accounts, monkeypatch):
    _travel_env(monkeypatch, 100, [1, 2, 3, 4])
    _hops(monkeypatch, ["100", "250", "1"])
    r = _travel()
    assert r["gas_used"] == 3_000
    assert r.get("fee_wei") == "351", r


def test_travel_fee_total_is_null_when_a_hop_that_spent_gas_states_none(
    accounts, monkeypatch,
):
    """A reverted hop spent gas its receipt cannot show (no logs), and a
    landed hop may have unidentified legs: either makes any sum an
    understatement, so the total is null — never an estimate."""
    _travel_env(monkeypatch, 100, [1, 2, 3, 4])
    _hops(monkeypatch, ["100", "revert"])
    r = _travel(allow_partial=True)
    assert [t["status"] for t in r["txs"]] == ["success", "reverted"]
    assert "fee_wei" in r and r["fee_wei"] is None, r

    _hops(monkeypatch, ["100", None, "5"])
    r = _travel()
    assert "fee_wei" in r and r["fee_wei"] is None, r


def test_travel_fee_total_counts_nothing_for_a_hop_never_sent(
    accounts, monkeypatch,
):
    """A refused hop (nothing signed) cost nothing: the total is the
    landed hops' sum."""
    _travel_env(monkeypatch, 100, [1, 2, 3, 4])
    _hops(monkeypatch, ["100", "refuse"])
    r = _travel(allow_partial=True)
    assert r["txs"][-1]["status"] == "error"
    assert r.get("fee_wei") == "100", r


def _gas_legged_fills(node):
    """Every plain (empty-calldata) transaction the fake node mines gets
    the chain's two gas-token legs: prepayment at log 0, refund last."""
    fee_collector = "0x" + "fc" * 20
    original = node._execute

    def execute(tx):
        original(tx)
        if tx.data:
            return
        rec = node.receipts[tx.hash]
        prepay = tx.gas * PRICE + 1
        refund = prepay - 300_000_000_000          # a fee of 3e11 wei
        word = lambda a: "0x" + "00" * 12 + a.lower().removeprefix("0x")
        leg = lambda src, dst, v, i: {
            "address": ETH_TOKEN.lower(),
            "topics": ["0x" + server._TRANSFER_TOPIC, word(src), word(dst)],
            "data": "0x" + v.to_bytes(32, "big").hex(),
            "blockNumber": rec["blockNumber"], "blockHash": rec["blockHash"],
            "transactionHash": tx.hash, "transactionIndex": "0x0",
            "logIndex": hex(i), "removed": False}
        rec["logs"] = [leg(tx.sender, fee_collector, prepay, 0),
                       leg(fee_collector, tx.sender, refund, 1)]

    node._execute = execute


@pytest.mark.parametrize("batched", [True, False])
def test_a_gap_fill_row_carries_its_gas_fields(chain_env, monkeypatch,  # noqa: F811
                                               batched):
    """A gap fill is a real transaction that cost gas: its `filled` row
    carries block, gas_used and fee_wei from its own receipt — on the
    batched receipt path and on the one-by-one fallback."""
    node, game, clock, op = chain_env
    game.inv[11301] = 50
    _gas_legged_fills(node)
    if not batched:
        monkeypatch.setattr(server, "_batch_receipts", lambda hashes: None)
    for _ in range(4):                                   # outlast re-offers
        _refuse_nonce(node, 502, READINESS_ERROR)
    out = server.act_sequence(_feeds(6), account="testa")
    (fill,) = out["filled"]
    rec = node.receipts[fill["tx_hash"].lower()]
    assert fill["status"] == "success", fill
    assert fill.get("block") == int(rec["blockNumber"], 16), fill
    assert fill.get("gas_used") == int(rec["gasUsed"], 16), fill
    assert fill.get("fee_wei") == "300000000000", fill


# ---------------------------------------------------------------------------
# J3 — the texts 4.2.0 left behind
# ---------------------------------------------------------------------------

THIS = "an earlier call of this server"
ANOTHER = "another process using this key"


def _call_of(whose: str) -> str:
    return (server._CallControl("act_sequence").id if whose == "this"
            else "act_sequence#0123456789ab")       # another process's


@pytest.mark.parametrize("whose", ["this", "other"])
def test_the_lane_blocked_error_says_who_signed_the_armed_tail(
    chain_env, monkeypatch, whose,  # noqa: F811
):
    from test_h400_lane import _nonce_of
    from test_h420_families import _ledger
    node, game, clock, op = chain_env
    game.xp[server._kami_entity_id(5)] = 1_000
    armed = _ledger(node, op, [501, 502], _call_of(whose))
    monkeypatch.setattr(server, "_LANES", {})
    node.fail("eth_sendRawTransaction", times=5, error={
        "code": -32000, "message": "insufficient funds for gas * price"},
        when=lambda p: _nonce_of(p[0]) == 500)
    with pytest.raises(server.LaneBlockedError) as ei:
        server.level_up_kami(5, account="testa")
    text = str(ei.value)
    assert "lane blocked behind nonce 500" in text
    assert all(h in text for h in armed)
    assert "Nothing was sent by this call" in text
    assert "by this harness" not in text, text
    if whose == "this":
        assert THIS in text and ANOTHER not in text, text
    else:
        assert ANOTHER in text and THIS not in text, text
        assert "lane directory" in text, text


@pytest.mark.parametrize("whose", ["this", "other"])
def test_the_late_mined_notice_says_who_signed_it(chain_env, whose):  # noqa: F811
    from test_h400_lane import _sign_feed
    node, game, clock, op = chain_env
    game.xp[server._kami_entity_id(5)] = 1_000
    lane = server._lane(op)
    raw = _sign_feed(500)
    h = "0x" + server.Web3.keccak(raw).hex().removeprefix("0x")
    with lane.critical():
        e = lane.add(500, h, raw, _call_of(whose), "use_item_batch", 2)
        lane.release(e, "proven absent")
    game.inv[11301] = 1
    node.rpc({"jsonrpc": "2.0", "id": 1, "method": "eth_sendRawTransaction",
              "params": ["0x" + raw.hex()]})            # it mines anyway
    note = server.run_tool("level_up_kami", kami_id=5,
                           account="testa")["notice"]
    assert f"had released, {h} (use_item_batch step 2" in note
    assert "mined late at nonce 500" in note
    assert "this harness had released" not in note, note
    if whose == "this":
        assert THIS in note and ANOTHER not in note, note
    else:
        assert ANOTHER in note and THIS not in note, note


def test_fund_operator_describes_the_prepayment():
    tools = {t.name: t for t in server.mcp._tool_manager.list_tools()}
    d = tools["fund_operator"].description
    assert "250k gas at the flat price + 1 wei" in d, d

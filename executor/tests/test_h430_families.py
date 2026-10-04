"""4.3.0 — the last release before the freeze (part 1).

J1  `dry_run` on portal_deposit, portal_claim and portal_cancel
J2  a fee total wherever a result sums gas; gas fields on gap-fill rows
J3  the two lane texts 4.2.0 left behind; fund_operator states the
    prepayment

All hermetic: the fake portal and fake node of the 4.0.0 / 4.2.0 tests.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import server
from fakenode import READINESS_ERROR
from test_400_surface import ETH_TOKEN, ONYX_TOKEN, portal_env  # noqa: F401
from test_gas_wallet import gas_env  # noqa: F401  (fixture)
from test_h350_families import FakeChain, seq_env  # noqa: F401  (fixture)
from test_h420_families import _batch_of_the_two_872_stops
from test_h420_families import landed  # noqa: F401  (fixture)
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
    estimated before its allowance exists, so its bound is the J8
    estimate, marked as one, and the verdict says so."""
    node, game, clock, portal, split = portal_env
    est = server._DEPOSIT_GAS_ESTIMATE * PRICE + 1
    _fund(portal, split, WEI + APPROVE_BOUND + est, allowance=0)
    out = server.portal_deposit(103, ITEMS, account="split", dry_run=True)
    _no_terminal_state(out)
    assert not node.sends and not portal.approvals
    assert out["approve_needed"] is True
    assert out["approve_fee_bound_wei"] == str(APPROVE_BOUND)
    assert out["deposit_fee_bound_wei"] == str(est)
    assert out["deposit_fee_bound_estimated"] is True
    assert out["gas_token_rule"].startswith("passes, the deposit's bound "
                                            "an estimate")

    _fund(portal, split, WEI + APPROVE_BOUND + est - 1, allowance=0)
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


# ===========================================================================
# Part 2 — the second live round's last-call list
# ===========================================================================

FIX = Path(__file__).parent / "fixtures" / "receipts_20261004"
_REAL_KAMI_EID = server._kami_entity_id


def _receipt(name_or_raw):
    raw = (json.loads((FIX / name_or_raw).read_text())
           if isinstance(name_or_raw, str) else name_or_raw)
    return server._format_receipt(raw)


START = "system_harvest_start_34030997_988a9650.json"      # kamis 6058, 6245
STOP = "system_harvest_stop_34031314_ee431877.json"        # kami 6058
COLLECT = "system_harvest_collect_34031082_94415aa2.json"  # kami 6058


@pytest.fixture()
def starts(landed, monkeypatch):  # noqa: F811
    """harvest_start on its real send path too (landed covers stop and
    collect): ownership passes, the chain answers with a recorded receipt."""
    monkeypatch.setattr(server, "_require_kamis_owned", lambda *a: None)
    return landed


# ---------------------------------------------------------------------------
# J4 — get_gas_balance states exact wei, and the block it read at
# ---------------------------------------------------------------------------

def test_gas_balance_states_every_balance_in_exact_wei(gas_env):  # noqa: F811
    odd = 123_456_789_012_345_678_901                   # 21 digits
    gas_env.balances[gas_env.solo.operator_addr] = odd
    gas_env.balances[gas_env.solo.owner_addr] = 1
    gas_env.mainnet[gas_env.solo.owner_addr] = odd + 7
    solo = server.get_gas_balance(account="solo")["balances"]["solo"]
    assert solo.get("operator_wei") == str(odd), solo
    assert solo.get("owner_wei") == "1", solo
    assert solo.get("owner_mainnet_wei") == str(odd + 7), solo
    assert solo["operator_eth"] == "123.456789012345678901"   # unchanged
    gas_env.mainnet.clear()
    solo = server.get_gas_balance(account="solo")["balances"]["solo"]
    assert solo["owner_mainnet_eth"] == "unavailable"
    assert "owner_mainnet_wei" in solo and solo["owner_mainnet_wei"] is None


def test_gas_balance_states_the_block_it_read_at(gas_env, monkeypatch):  # noqa: F811
    """Every Yominet balance of the call is read at ONE stated block."""
    reads = []

    def get_balance(addr, block_identifier="latest"):
        reads.append(block_identifier)
        return gas_env.balances.get(addr, 0)

    monkeypatch.setattr(server.w3.eth, "block_number", 34_100_000,
                        raising=False)
    monkeypatch.setattr(server.w3.eth, "get_balance", get_balance)
    r = server.get_gas_balance()
    assert r.get("block") == 34_100_000, r
    assert reads and set(reads) == {34_100_000}, reads


# ---------------------------------------------------------------------------
# J5 — one tool, one result shape on its single and batch paths
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tool, name", [
    ("harvest_start", START), ("harvest_stop", STOP),
    ("harvest_collect", COLLECT),
])
def test_single_and_batch_paths_return_the_same_keys(starts, tool, name):
    """One receipt answers both calls: the key sets must match."""
    call = getattr(server, tool)
    args = (lambda ks: (ks, 73)) if tool == "harvest_start" else (
        lambda ks: (ks,))
    starts.append(_receipt(name))
    single = call(*args([6058]), account="testa")
    starts.append(_receipt(name))
    batch = call(*args([6058, 6245]), account="testa")
    assert set(single) == set(batch), (
        f"{tool}: single-only {set(single) - set(batch)}, "
        f"batch-only {set(batch) - set(single)}")
    assert batch["account"] == "testa"


# ---------------------------------------------------------------------------
# J6 — a start / stop / collect says when each kami may act next
# ---------------------------------------------------------------------------

def test_a_batch_start_states_each_kamis_cooldown(starts):
    """The 2-kami start (34030997): each kami's component.Time.Next write
    — LibCooldown.set, block timestamp + cooldown — the unit the kill
    rows use."""
    starts.append(_receipt(START))
    out = server.harvest_start([6245, 6058], 73, account="testa")
    assert out.get("cooldowns") == [
        {"kami_id": 6245, "cooldown_until": 1791101278},
        {"kami_id": 6058, "cooldown_until": 1791101278}], out


@pytest.mark.parametrize("tool, name, kamis, want", [
    ("harvest_stop", STOP, [6058], {6058: 1791101909}),
    ("harvest_collect", COLLECT, [6058], {6058: 1791101541}),
])
def test_a_stop_or_collect_states_the_cooldown_it_started(starts, tool, name,
                                                          kamis, want):
    starts.append(_receipt(name))
    out = getattr(server, tool)(kamis, account="testa")
    assert out.get("cooldowns") == [
        {"kami_id": k, "cooldown_until": want[k]} for k in kamis], out


def test_a_batch_stop_states_each_kamis_own_cooldown(starts):
    starts.append(_receipt(_batch_of_the_two_872_stops()))
    out = server.harvest_stop([11224, 12649], account="testa")
    assert out.get("cooldowns") == [
        {"kami_id": 11224, "cooldown_until": 1791103093},
        {"kami_id": 12649, "cooldown_until": 1791103093}], out


def test_a_cooldown_the_receipt_does_not_carry_is_null_never_a_guess(starts):
    """No Time.Next write for the kami, and the read at the receipt's
    block fails (the offline node): null plus a decode_error."""
    raw = json.loads((FIX / STOP).read_text())
    tn = "0x" + server._TIME_NEXT_COMPONENT_ID.to_bytes(32, "big").hex()
    raw = {**raw, "logs": [lg for lg in raw["logs"]
                           if lg["topics"][1:2] != [tn]]}
    starts.append(_receipt(raw))
    (row,) = server.harvest_stop([6058], account="testa")["cooldowns"]
    assert row["kami_id"] == 6058 and row["cooldown_until"] is None, row
    assert "cooldown" in row.get("decode_error", ""), row


def test_sequence_start_and_stop_rows_carry_cooldowns(seq_env):  # noqa: F811
    seq_env.setattr(server, "_kami_entity_id", _REAL_KAMI_EID)
    names = [START, STOP]
    seq_env.setattr(server, "w3", FakeChain(["ok", "ok"]))
    seq_env.setattr(server, "_await_receipt",
                    lambda h, built, timeout, account=None, ceiling_key=None:
                    _receipt(names[int(h[-2:], 16)]))
    out = server.act_sequence([
        {"op": "harvest_start", "kami_ids": [6058, 6245], "node_index": 73},
        {"op": "harvest_stop", "kami_ids": [6058]},
    ], account="testa")
    start, stop = out["steps"]
    assert start.get("cooldowns") == [
        {"kami_id": 6058, "cooldown_until": 1791101278},
        {"kami_id": 6245, "cooldown_until": 1791101278}], start
    assert stop.get("cooldowns") == [
        {"kami_id": 6058, "cooldown_until": 1791101909}], stop


# ---------------------------------------------------------------------------
# J7 — the single-action tools say how to get one block
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["feed_kami", "liquidate_kami",
                                  "harvest_start", "harvest_stop"])
def test_the_actions_act_sequence_batches_say_how_to_land_together(name):
    d = {t.name: t for t in server.mcp._tool_manager.list_tools()}[
        name].description
    assert "Calls on one key run in turn" in d, d
    assert "act_sequence" in d, d


# ===========================================================================
# Review amendment — A, B, C (J8)
# ===========================================================================

# --- A: the LAST cooldown write wins ----------------------------------------

@pytest.mark.parametrize("later", [1_791_101_999, 1_791_100_000])
def test_the_last_cooldown_write_in_the_receipt_wins(starts, later):
    """The 34031314 stop with its component.Time.Next write on kami 6058
    (1791101909) followed by a second write of another value: the later
    WRITE is the cooldown — larger or smaller, never the first, never the
    max."""
    raw = json.loads((FIX / STOP).read_text())
    tn = "0x" + server._TIME_NEXT_COMPONENT_ID.to_bytes(32, "big").hex()
    kami = "0x" + server._kami_entity_id(6058).to_bytes(32, "big").hex()
    logs = list(raw["logs"])
    i = next(i for i, lg in enumerate(logs)
             if lg["topics"][1:2] == [tn] and lg["topics"][3:4] == [kami])
    second = dict(logs[i])
    second["data"] = logs[i]["data"][:-64] + later.to_bytes(32, "big").hex()
    logs.insert(i + 1, second)
    starts.append(_receipt({**raw, "logs": logs}))
    (row,) = server.harvest_stop([6058], account="testa")["cooldowns"]
    assert row == {"kami_id": 6058, "cooldown_until": later}, row


# --- B: the dry runs run the gas gate -----------------------------------------

def _poor(node, address, wei=10 ** 9):
    """The fake node answers `wei` for this address's native balance."""
    rich = node._eth_getBalance
    node._eth_getBalance = lambda addr, block="latest": (
        hex(wei) if addr.lower() == address.lower() else rich(addr, block))


@pytest.mark.parametrize("tool", ["portal_claim", "portal_cancel"])
def test_a_settle_dry_run_refuses_a_signer_short_of_gas_as_the_real_call_does(
    portal_env, tool,  # noqa: F811
):
    node, game, clock, portal, split = portal_env
    rid = _receipt_at(portal_env)                 # operator lane: operator signs
    _poor(node, split.operator_addr)
    sent = len(node.sends)
    call = getattr(server, tool)
    with pytest.raises(server.PreTxValidationError) as dry:
        call(rid, account="split", dry_run=True)
    with pytest.raises(server.PreTxValidationError) as real:
        call(rid, account="split")
    assert str(dry.value) == str(real.value)
    assert "operator wallet" in str(dry.value), str(dry.value)
    assert f"gas limit {SETTLE_BOUND // PRICE}" in str(dry.value)
    assert len(node.sends) == sent
    assert int(rid, 16) in portal.receipts


def test_a_deposit_dry_run_refuses_an_owner_short_of_gas_as_the_real_call_does(
    portal_env,  # noqa: F811
):
    node, game, clock, portal, split = portal_env
    wei = 1_000 * 10 ** 16
    _fund(portal, split, wei, allowance=wei, token=ONYX_TOKEN)
    _poor(node, split.owner_addr)
    with pytest.raises(server.PreTxValidationError) as dry:
        server.portal_deposit(100, 1_000, account="split", dry_run=True)
    with pytest.raises(server.PreTxValidationError) as real:
        server.portal_deposit(100, 1_000, account="split")
    assert str(dry.value) == str(real.value)
    assert "owner wallet" in str(dry.value), str(dry.value)
    assert not node.sends


# --- C (J8): a gas-token deposit that cannot leave the deposit's fee is
# refused BEFORE the approve, on an estimated deposit bound ----------------

# The gas limit the recorded live deposit (fixtures/receipts_20261004,
# system_erc20_portal_34031247: 5 Ether Shards) was SENT with — the
# node's estimate x 1.5, read from its prepayment — the deposit's gas
# limit before its allowance exists (review ruling: at least as strict as
# the exact check it stands in for).
DEPOSIT_GAS_ESTIMATE = 1_712_649
EST_BOUND = DEPOSIT_GAS_ESTIMATE * PRICE + 1     # 4,281,622,500,001 wei


def test_the_deposit_gas_estimate_is_the_limit_the_recorded_deposit_was_sent_with():
    """prepayment = gas limit x price + 1 wei (log 0, the sender to the
    fee collector); the node's estimate ran ~1.42x the gas used."""
    raw = json.loads((FIX / "system_erc20_portal_34031247_f8ba5d86.json")
                     .read_text())
    prepay = int(raw["logs"][0]["data"], 16)
    assert (prepay - 1) % PRICE == 0
    limit = (prepay - 1) // PRICE
    assert server._DEPOSIT_GAS_ESTIMATE == limit == 1_712_649
    used = int(raw["gasUsed"], 16)
    assert used == 803_569 and round(limit / 1.5 / used, 2) == 1.42


def test_a_short_allowance_deposit_that_cannot_leave_the_deposit_fee_signs_nothing(
    portal_env,  # noqa: F811
):
    """One wei below amount + the approve's bound + the ESTIMATED deposit
    bound: refused before the approve, naming the four numbers and that
    the deposit's bound is an estimate. No transaction is sent."""
    node, game, clock, portal, split = portal_env
    held = WEI + APPROVE_BOUND + EST_BOUND - 1
    _fund(portal, split, held, allowance=0)
    with pytest.raises(server.PreTxValidationError) as ei:
        server.portal_deposit(103, ITEMS, account="split")
    assert not node.sends and not portal.approvals
    msg = str(ei.value)
    for number in (held, WEI, APPROVE_BOUND, EST_BOUND):
        assert str(number) in msg, (number, msg)
    assert "estimate" in msg and "1 wei short" in msg, msg


def test_a_short_allowance_deposit_at_the_estimated_boundary_proceeds(
    portal_env,  # noqa: F811
):
    """Exactly amount + the approve's bound + the estimated deposit bound:
    the approve is signed, and the exact deposit check after it (the fake
    deposit's own bound is below the estimate) lets the deposit go."""
    node, game, clock, portal, split = portal_env
    _fund(portal, split, WEI + APPROVE_BOUND + EST_BOUND, allowance=0)
    out = server.portal_deposit(103, ITEMS, account="split")
    assert [t["step"] for t in out["txs"]] == ["approve", "deposit"]


def test_a_short_allowance_dry_run_states_the_estimated_deposit_bound(
    portal_env,  # noqa: F811
):
    node, game, clock, portal, split = portal_env
    _fund(portal, split, WEI + APPROVE_BOUND + EST_BOUND, allowance=0)
    out = server.portal_deposit(103, ITEMS, account="split", dry_run=True)
    assert not node.sends and not portal.approvals
    assert out["approve_needed"] is True
    assert out["deposit_fee_bound_wei"] == str(EST_BOUND)
    assert out.get("deposit_fee_bound_estimated") is True, out
    assert "estimate" in out["gas_token_rule"], out
    _fund(portal, split, WEI + APPROVE_BOUND + EST_BOUND - 1, allowance=0)
    with pytest.raises(server.PreTxValidationError, match="1 wei short"):
        server.portal_deposit(103, ITEMS, account="split", dry_run=True)
    assert not node.sends and not portal.approvals


def test_a_deposit_with_its_allowance_is_checked_exactly_as_before(portal_env):  # noqa: F811
    """Allowance covering: no estimate anywhere — the deposit's own bound,
    estimated by the node, exactly as in 4.2.0."""
    node, game, clock, portal, split = portal_env
    _fund(portal, split, WEI + DEPOSIT_BOUND, allowance=WEI)
    out = server.portal_deposit(103, ITEMS, account="split", dry_run=True)
    assert out["deposit_fee_bound_wei"] == str(DEPOSIT_BOUND)
    assert out.get("deposit_fee_bound_estimated") is False, out
    assert server.portal_deposit(103, ITEMS, account="split")["status"] == (
        "success")
    _fund(portal, split, WEI + DEPOSIT_BOUND - 1, allowance=WEI)
    with pytest.raises(server.PreTxValidationError, match="1 wei short"):
        server.portal_deposit(103, ITEMS, account="split")

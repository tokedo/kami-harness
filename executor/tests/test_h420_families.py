"""4.2.0 — what the live stage of 2026-10-04 showed missing or misleading.

H1  a harvest stop / collect says what it paid (item and amount, per kami)
H2  every write result says what it actually cost (`fee_wei`)
H3  a deposit of the gas token must leave the fee
H4  the two-process notice says whose transaction it was
H5  two descriptions that misled a careful agent

The receipts are REAL (tests/fixtures/receipts_20261004, recorded on the
public test account; index.json states the chain truth each one is
checked against, and which two are another account's with synthetic
identifiers).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import lanes
import server
from test_400_surface import ETH_TOKEN, portal_env  # noqa: F401  (fixture)
from test_h350_families import FakeChain, seq_env  # noqa: F401  (fixture)
from test_h400_lane import _sign_feed
from test_h400_send_path import chain_env  # noqa: F401  (fixture)

FIX = Path(__file__).parent / "fixtures" / "receipts_20261004"
INDEX = json.loads((FIX / "index.json").read_text())
PAYOUTS = INDEX["harvest_payouts"]
TEST_ACCOUNT_ID = 0xB6278E6C4D6F67E721F104DB07CCBF1F4E9CFC47
# seq_env replaces _kami_entity_id with a stand-in; the decode under test
# maps the receipt's real kami entities, so it needs the real derivation.
_REAL_KAMI_EID = server._kami_entity_id


def _raw(name: str) -> dict:
    return json.loads((FIX / name).read_text())


def _receipt(name_or_raw):
    raw = _raw(name_or_raw) if isinstance(name_or_raw, str) else name_or_raw
    return server._format_receipt(raw)


@pytest.fixture()
def landed(monkeypatch, accounts):
    """harvest_stop / harvest_collect run their REAL send path (_send_tx,
    _send_batch_tx); only the signing + broadcast + receipt wait is
    replaced, and it answers with the next recorded receipt queued."""
    monkeypatch.setattr(server, "_validate_active_harvests", lambda *a: None)
    monkeypatch.setattr(server, "_require_registered_operator",
                        lambda a: TEST_ACCOUNT_ID)
    monkeypatch.setattr(server, "_require_gas_balance", lambda *a, **k: None)
    monkeypatch.setattr(server, "_validated_fn", lambda *a, **k: object())
    queue: list = []
    monkeypatch.setattr(server, "_signed_send", lambda *a, **k: queue.pop(0))
    return queue


# ---------------------------------------------------------------------------
# H1 — a harvest stop / collect says what it paid
# ---------------------------------------------------------------------------

STOPS = [n for n in PAYOUTS if n.startswith("system_harvest_stop_")]


@pytest.mark.parametrize("name", STOPS)
def test_a_stop_states_the_item_and_amount_it_paid(landed, name):
    """2, 2, 2, 622, 630 of item 2 (VIPP) — the chain's balance deltas."""
    fact = PAYOUTS[name]
    landed.append(_receipt(name))
    out = server.harvest_stop([fact["kami"]], account="testa")
    assert out.get("payouts") == [{
        "kami_id": fact["kami"], "item": 2, "item_name": "VIPP",
        "amount": fact["amount"],
    }], f"{name}: {out}"


def test_a_collect_that_paid_nothing_says_zero_of_its_item(landed):
    name = "system_harvest_collect_34031082_94415aa2.json"
    landed.append(_receipt(name))
    out = server.harvest_collect([6058], account="testa")
    assert out.get("payouts") == [
        {"kami_id": 6058, "item": 2, "item_name": "VIPP", "amount": 0}], out


@pytest.mark.parametrize("name", list(PAYOUTS))
def test_the_item_is_the_inventory_the_receipt_writes(name):
    """The item is not in the event: it is the account's inventory entity
    the receipt writes, and its written value IS the balance the chain
    reported after the action (index.json)."""
    fact = PAYOUTS[name]
    writes = server._component_value_writes(_receipt(name))
    inv = server._inventory_entity_id(TEST_ACCOUNT_ID, fact["item"])
    assert writes[inv] == [fact["item_balance_after"]]


def _batch_of_the_two_872_stops() -> dict:
    """One receipt holding both 34031872 stops, as a 2-kami batch lands:
    the first stop's prepayment and game logs, then the second's game logs
    and refund — each kami's claim runs and emits before the next one."""
    a = _raw("system_harvest_stop_34031872_1ae21191.json")
    b = _raw("system_harvest_stop_34031872_2f07ff6c.json")
    return {**a, "logs": a["logs"][:-1] + b["logs"][1:]}


def test_a_batch_attributes_each_payout_to_its_own_kami(landed):
    """Asked in the opposite order to the receipt's: attribution is by the
    event's kami, never by position."""
    landed.append(_receipt(_batch_of_the_two_872_stops()))
    out = server.harvest_stop([11224, 12649], account="testa")
    assert out["kamis"] == [11224, 12649]
    assert out.get("payouts") == [
        {"kami_id": 11224, "item": 2, "item_name": "VIPP", "amount": 630},
        {"kami_id": 12649, "item": 2, "item_name": "VIPP", "amount": 622},
    ], out


def test_a_payout_that_cannot_be_decoded_is_a_decode_error_never_a_guess(
    landed,
):
    """No HARVEST_STOP event for the kami: no item, no amount."""
    raw = _raw("system_harvest_stop_34031314_ee431877.json")
    landed.append(_receipt(raw))
    out = server.harvest_stop([6245], account="testa")   # not the kami paid
    (row,) = out["payouts"]
    assert row["kami_id"] == 6245
    assert row["item"] is None and row["amount"] is None
    assert "no HARVEST_STOP event for kami #6245" in row["decode_error"]

    # The event without the inventory write that names its item: the
    # amount is the game's own number, the item is not stated.
    inv = server._inventory_entity_id(TEST_ACCOUNT_ID, 2)
    word = "0x" + inv.to_bytes(32, "big").hex()
    raw2 = {**raw, "logs": [lg for lg in raw["logs"]
                            if word not in lg["topics"]]}
    landed.append(_receipt(raw2))
    (row,) = server.harvest_stop([6058], account="testa")["payouts"]
    assert row["amount"] == 2 and row["item"] is None
    assert "item is not stated" in row["decode_error"]


def test_a_sequence_stop_row_carries_its_payouts(seq_env):  # noqa: F811
    """act_sequence's harvest_stop rows, from the step's own receipt."""
    seq_env.setattr(server, "_kami_entity_id", _REAL_KAMI_EID)
    names = ["system_harvest_stop_34031872_1ae21191.json",
             "system_harvest_stop_34031872_2f07ff6c.json"]
    chain = FakeChain(["ok", "ok"])
    seq_env.setattr(server, "w3", chain)
    seq_env.setattr(server, "_await_receipt",
                    lambda h, built, timeout, account=None, ceiling_key=None:
                    _receipt(names[int(h[-2:], 16)]))
    out = server.act_sequence([
        {"op": "harvest_stop", "kami_ids": [12649]},
        {"op": "harvest_stop", "kami_ids": [11224]},
    ], account="testa")
    rows = out["steps"]
    assert [r["status"] for r in rows] == ["success", "success"]
    assert rows[0].get("payouts") == [
        {"kami_id": 12649, "item": 2, "item_name": "VIPP", "amount": 622}]
    assert rows[1].get("payouts") == [
        {"kami_id": 11224, "item": 2, "item_name": "VIPP", "amount": 630}]


# ---------------------------------------------------------------------------
# H2 — every write result says what it actually cost
# ---------------------------------------------------------------------------

FEES = INDEX["fees_wei"]
LANDED = sorted(n for n, fee in FEES.items() if fee is not None)
GAS_TOKEN = "0xe1ff7038eaaaf027031688e1535a055b2bac2546"
TRANSFER = "0x" + server._TRANSFER_TOPIC


def _word(addr: str) -> str:
    return "0x" + "00" * 12 + addr.lower().removeprefix("0x")


def _gas_leg(src: str, dst: str, value: int, token: str = GAS_TOKEN) -> dict:
    return {"address": token, "topics": [TRANSFER, _word(src), _word(dst)],
            "data": "0x" + value.to_bytes(32, "big").hex(),
            "logIndex": "0x0", "blockNumber": "0x1", "blockHash": "0x" + "00" * 32,
            "transactionHash": "0x" + "00" * 32, "transactionIndex": "0x0",
            "removed": False}


@pytest.mark.parametrize("name", LANDED)
def test_fee_wei_is_the_prepayment_minus_the_refund(name):
    """All 23 landed receipts (21 of the test session, the claim and the
    other account's item transfer): fee_wei is the gas token's log-0
    Transfer minus its last-log Transfer, as computed by hand in
    index.json — 1.05x to 1.18x of gas_used x effectiveGasPrice."""
    r = _receipt(name)
    fields = server._tx_fields(r)
    assert fields.get("fee_wei") == FEES[name], f"{name}: {fields}"
    ratio = int(FEES[name]) / (r.gasUsed * r.effectiveGasPrice)
    assert 1.04 < ratio < 1.18


@pytest.mark.parametrize("name", [
    "system_erc20_portal_34031247_f8ba5d86.json",      # deposit: sender -> holder
    "system_erc20_portal_claim_synthetic.json",         # claim: holder -> signer
    "token_eth_34031245_f8fa7ad1.json",                 # approve on the gas token
])
def test_a_transaction_that_moves_the_gas_token_itself_is_not_misread(name):
    """The deposit pulls 50,000,000,000,000 wei from the sender at log 1;
    the claim pays 90,000,000,000,000 wei to the signer at log 9; the
    approve is a call on the gas token. Neither is a leg."""
    assert server._tx_fields(_receipt(name)).get("fee_wei") == FEES[name]


def test_the_legs_are_identified_by_counterparty_not_by_position():
    """Position alone would misread each of these; the rule states null."""
    claim = _raw("system_erc20_portal_claim_synthetic.json")
    logs = claim["logs"]
    payout = next(lg for lg in logs[1:-1] if lg["topics"][0] == TRANSFER
                  and lg["address"] == GAS_TOKEN)
    # No refund leg, and the claim's payout (holder -> signer) last: its
    # sender is not the prepayment's recipient.
    no_refund = {**claim, "logs": [lg for lg in logs[:-1] if lg is not payout]
                 + [payout]}
    assert server._tx_fields(_receipt(no_refund))["fee_wei"] is None

    dep = _raw("system_erc20_portal_34031247_f8ba5d86.json")
    # No prepayment: the first log is the deposit's own pull (sender ->
    # the token holder), whose recipient is not the refund's sender.
    no_prepay = {**dep, "logs": dep["logs"][1:]}
    assert server._tx_fields(_receipt(no_prepay))["fee_wei"] is None

    # Legs of another sender, or on another token: not this fee.
    other = "0x" + "77" * 20
    stop = _raw("system_harvest_stop_34031314_ee431877.json")
    assert server._tx_fields(_receipt({**stop, "from": other}))[
        "fee_wei"] is None
    swapped = [_gas_leg(stop["from"], "0x" + "fc" * 20, 10, token=other)]
    assert server._tx_fields(_receipt(
        {**stop, "logs": swapped + stop["logs"][1:]}))["fee_wei"] is None


def test_a_reverted_transaction_has_a_null_fee():
    """A reverted receipt carries no logs: null, never an estimate."""
    name = "system_kami_use_item_reverted_34031837_885eac81.json"
    r = _receipt(name)
    assert r.status == 0 and not r.logs
    assert server._tx_fields(r).get("fee_wei", "absent") is None
    e = server.OnChainRevertError(server._hex_hash(r.transactionHash),
                                  r.blockNumber, r.gasUsed, "reverted")
    assert server._failed_tx_fields(e).get("fee_wei", "absent") is None


def test_every_send_path_reports_fee_wei(monkeypatch, accounts):
    """The five success shapes: _send_tx, _send_batch_tx, _send_tx_owner,
    _send_eth and _tx_fields (portal tools) — and a leg keeps it."""
    name = "system_harvest_stop_34031872_1ae21191.json"
    monkeypatch.setattr(server, "_require_registered_operator", lambda a: 1)
    monkeypatch.setattr(server, "_require_registered_owner", lambda a: 1)
    monkeypatch.setattr(server, "_require_gas_balance", lambda *a, **k: None)
    monkeypatch.setattr(server, "_validated_fn", lambda *a, **k: object())
    monkeypatch.setattr(server, "_signed_send", lambda *a, **k: _receipt(name))
    outs = [
        server._send_tx("testa", "system.harvest.stop", [], [1]),
        server._send_batch_tx("testa", "system.harvest.stop", [],
                              "executeBatched", [[1]], 1),
        server._send_tx_owner("testa", "system.trade.create", [], [1]),
        server._send_eth("0x01", "0x" + "11" * 20, "0x" + "22" * 20, 0),
        server._tx_fields(_receipt(name)),
    ]
    for out in outs:
        assert out.get("fee_wei") == FEES[name], out
    assert server._receipt_fields(outs[0]).get("fee_wei") == FEES[name]


def test_sequence_rows_report_fee_wei_and_null_for_a_revert(seq_env):  # noqa: F811
    """act_sequence: a landed row's fee from its own receipt; a reverted
    row's is null."""
    seq_env.setattr(server, "_kami_entity_id", _REAL_KAMI_EID)
    name = "system_harvest_stop_34031872_1ae21191.json"
    seq_env.setattr(server, "w3", FakeChain(["ok", "revert"]))

    def await_receipt(h, built, timeout, account=None, ceiling_key=None):
        if int(h[-2:], 16) == 0:
            return _receipt(name)
        raise server.OnChainRevertError(h, 900, 358_803, "kami starving..")

    seq_env.setattr(server, "_await_receipt", await_receipt)
    out = server.act_sequence([
        {"op": "harvest_stop", "kami_ids": [12649]},
        {"op": "feed", "kami_id": 12649, "item_id": 11301},
    ], account="testa")
    ok, bad = out["steps"]
    assert ok["status"] == "success" and ok.get("fee_wei") == FEES[name]
    assert bad["status"] == "reverted"
    assert bad.get("fee_wei", "absent") is None


# ---------------------------------------------------------------------------
# H3 — a deposit of the gas token must leave the fee
# ---------------------------------------------------------------------------

PRICE = 2_500_000                      # the flat price, wei per gas
# The fake portal's estimates (fakenode Result.gas_used) x 1.5, the gas
# limit the portal send provisions: deposit 500,000 -> 750,000; approve
# 60,000 -> 90,000. The gas gate's fee bound is gas limit x the price.
DEPOSIT_BOUND = 750_000 * PRICE        # 1,875,000,000,000 wei
APPROVE_BOUND = 90_000 * PRICE         #   225,000,000,000 wei
ITEMS = 5                              # Ether Shard 103, scale 5
WEI = ITEMS * 10 ** 13                 # 50,000,000,000,000 wei


def _fund(portal, split, held, allowance):
    owner, t = split.owner_addr.lower(), ETH_TOKEN.lower()
    portal.token_bal[(t, owner)] = held
    portal.allowance[(t, owner)] = allowance


def test_a_gas_token_deposit_that_would_leave_less_than_its_fee_is_refused(
    portal_env,  # noqa: F811
):
    """The live failure: the token balance covers the deposit and the gas
    gate passes on its own, but both come out of ONE balance. One wei
    short of amount + fee bound: refused before signing, with the three
    numbers."""
    node, game, clock, portal, split = portal_env
    held = WEI + DEPOSIT_BOUND - 1
    _fund(portal, split, held, allowance=WEI)
    with pytest.raises(server.PreTxValidationError) as ei:
        server.portal_deposit(103, ITEMS, account="split")
    msg = str(ei.value)
    assert not node.sends
    for number in (held, WEI, DEPOSIT_BOUND):
        assert str(number) in msg, msg
    assert "gas token" in msg


def test_a_gas_token_deposit_that_leaves_exactly_the_fee_is_sent(
    portal_env,  # noqa: F811
):
    node, game, clock, portal, split = portal_env
    _fund(portal, split, WEI + DEPOSIT_BOUND, allowance=WEI)
    out = server.portal_deposit(103, ITEMS, account="split")
    assert [t["step"] for t in out["txs"]] == ["deposit"]
    assert game.inv[103] == 200_000 + ITEMS - 1        # tax 1


def test_a_short_wallet_signs_no_approve_either(portal_env):  # noqa: F811
    """Allowance short: the approve's own fee comes out of the same token.
    Holding less than amount + the approve's fee bound refuses before
    the approve is signed."""
    node, game, clock, portal, split = portal_env
    held = WEI + APPROVE_BOUND - 1
    _fund(portal, split, held, allowance=0)
    with pytest.raises(server.PreTxValidationError) as ei:
        server.portal_deposit(103, ITEMS, account="split")
    assert not node.sends and not portal.approvals
    msg = str(ei.value)
    for number in (held, WEI, APPROVE_BOUND):
        assert str(number) in msg, msg


def test_after_the_approve_the_deposit_is_checked_against_its_own_fee(
    portal_env,  # noqa: F811
):
    """The deposit cannot be estimated before its allowance exists, so its
    own bound is checked once the approve has landed — and the deposit is
    refused before IT is signed, saying the approve landed."""
    node, game, clock, portal, split = portal_env
    held = WEI + APPROVE_BOUND          # covers the approve, not the deposit
    _fund(portal, split, held, allowance=0)
    with pytest.raises(server.PreTxValidationError) as ei:
        server.portal_deposit(103, ITEMS, account="split")
    assert len(node.sends) == 1 and len(portal.approvals) == 1
    msg = str(ei.value)
    approve_hash = node.sends[0][2]
    assert approve_hash in msg and "approve" in msg
    for number in (held, WEI, DEPOSIT_BOUND):
        assert str(number) in msg, msg


def test_a_deposit_of_a_token_that_is_not_the_gas_token_needs_only_its_amount(
    portal_env,  # noqa: F811
):
    """Onyx Shard (100) is not the gas token: the balance covering the
    amount exactly is enough, as before."""
    node, game, clock, portal, split = portal_env
    owner, t = split.owner_addr.lower(), "0x4badfb501ab304ff11217c44702bb9e9732e7cf4"
    wei = 1_000 * 10 ** 16
    portal.token_bal[(t, owner)] = wei
    portal.allowance[(t, owner)] = wei
    out = server.portal_deposit(100, 1_000, account="split")
    assert out["status"] == "success"


# ---------------------------------------------------------------------------
# H4 — the two-process notice says whose transaction it was
# ---------------------------------------------------------------------------

ANOTHER = "another process using this key"
THIS = "an earlier call of this server"


def _ledger(node, op, nonces, call, broadcast=True):
    """Entries in the key's lane file, written by the call `call` — of
    THIS process when `call` is one of its own call ids, else of another
    process sharing the lane directory (a second server on the key)."""
    lane = lanes.Lane(server.CHAIN_ID, server.Web3.to_checksum_address(op),
                      lanes.default_dir())
    hashes = []
    for step, n in enumerate(nonces, start=1):
        raw = _sign_feed(n)
        if broadcast:
            h = node.rpc({"jsonrpc": "2.0", "id": 1,
                          "method": "eth_sendRawTransaction",
                          "params": ["0x" + raw.hex()]})["result"]
        else:
            h = "0x" + server.Web3.keccak(raw).hex().removeprefix("0x")
        lane.offered(lane.add(n, h, raw, call, "act_sequence", step))
        hashes.append(h)
    lane.save()
    return hashes


def _this_servers_call() -> str:
    return server._CallControl("act_sequence").id


def _other_process_call() -> str:
    return "act_sequence#0123456789ab"       # the 4.1.0 call-id shape


@pytest.mark.parametrize("whose", ["this", "other"])
def test_a_mined_entry_is_attributed_to_its_signer(chain_env, monkeypatch,  # noqa: F811
                                                    whose):
    node, game, clock, op = chain_env
    game.inv[11301] = 10
    game.xp[server._kami_entity_id(5)] = 1_000
    call = _this_servers_call() if whose == "this" else _other_process_call()
    (h,) = _ledger(node, op, [500], call)            # contiguous: it mines
    monkeypatch.setattr(server, "_LANES", {})
    out = server.run_tool("level_up_kami", kami_id=5, account="testa")
    note = out["notice"]
    assert f"{h} (act_sequence step 1" in note
    assert "has since mined at nonce 500" in note
    if whose == "this":
        assert THIS in note and ANOTHER not in note, note
    else:
        assert ANOTHER in note and THIS not in note, note
        assert "lane directory" in note
        assert str(lanes.default_dir()) in note, note


@pytest.mark.parametrize("whose", ["this", "other"])
def test_a_drained_tail_is_attributed_to_its_signer(chain_env, monkeypatch,  # noqa: F811
                                                    whose):
    node, game, clock, op = chain_env
    game.inv[11301] = 10
    game.xp[server._kami_entity_id(5)] = 1_000
    call = _this_servers_call() if whose == "this" else _other_process_call()
    armed = _ledger(node, op, [501, 502], call)      # behind a gap at 500
    monkeypatch.setattr(server, "_LANES", {})
    out = server.run_tool("level_up_kami", kami_id=5, account="testa")
    note = out["notice"]
    assert "released 2 transaction(s) left armed behind nonce 500" in note
    assert all(h in note for h in armed)
    if whose == "this":
        assert THIS in note and ANOTHER not in note, note
    else:
        assert ANOTHER in note and THIS not in note, note
        assert str(lanes.default_dir()) in note, note


def test_a_consumed_entry_of_another_process_says_so(chain_env, monkeypatch):  # noqa: F811
    """Signed by another process at nonce 500, never broadcast, and the
    nonce is used by something else: NOT executed — and whose it was."""
    node, game, clock, op = chain_env
    game.xp[server._kami_entity_id(5)] = 1_000
    (h,) = _ledger(node, op, [500], _other_process_call(), broadcast=False)
    node.set_nonce(op, 501)                          # 500 consumed elsewhere
    monkeypatch.setattr(server, "_LANES", {})
    out = server.run_tool("level_up_kami", kami_id=5, account="testa")
    note = out["notice"]
    assert f"{h} (act_sequence step 1" in note and "NOT executed" in note
    assert ANOTHER in note and THIS not in note, note

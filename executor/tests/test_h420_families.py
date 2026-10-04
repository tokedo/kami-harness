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
from test_gas_wallet import gas_env  # noqa: F401  (fixture)
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


# --- H1, the attribution pinned (review amendment A) -------------------------
#
# The window rule against upstream at the pin: HarvestStopSystem /
# HarvestCollectSystem write an inventory in exactly two places, both in
# LibHarvest.claim — the harvest's tax recipients (LibInventory.incFor on
# THEIR holder ids, the node's item) and the account (incFor(toID, item,
# amtLeft)). Every other write of the action — LibScavenge.incFor,
# LibScore.incFor, LibData.inc, LibExperience, the bonuses — is on its own
# entity, never on keccak256("inventory.instance", account, item). So no
# real stop or collect puts a second item of the account's inside its
# window; the two rewrites below construct one to prove what happens.

INV_ITEM_2 = server._inventory_entity_id(TEST_ACCOUNT_ID, 2)    # VIPP
INV_ITEM_1 = server._inventory_entity_id(TEST_ACCOUNT_ID, 1)    # MUSU


def _topic(entity: int) -> str:
    return "0x" + entity.to_bytes(32, "big").hex()


def _onto(log: dict, entity: int) -> dict:
    """The same log, written on another entity (topic 3)."""
    return {**log, "topics": log["topics"][:3] + [_topic(entity)]}


def _two_items_batch() -> dict:
    """The 2-kami batch of the two 34031872 stops (_batch_of_the_two_872_
    stops: the first's prepayment and game logs, the second's game logs
    and refund), with every log of the SECOND stop's segment written on
    the account's item-2 inventory entity rewritten onto its item-1 (MUSU)
    inventory entity: kami 11224's claim now credits MUSU, kami 12649's
    still credits VIPP. Nothing else changes."""
    raw = _batch_of_the_two_872_stops()
    a_len = len(_raw("system_harvest_stop_34031872_1ae21191.json")["logs"]) - 1
    logs = list(raw["logs"])
    rewritten = 0
    for i in range(a_len, len(logs)):
        if logs[i]["topics"][3:4] == [_topic(INV_ITEM_2)]:
            logs[i] = _onto(logs[i], INV_ITEM_1)
            rewritten += 1
    assert rewritten == 1          # the second stop's one inventory write
    return {**raw, "logs": logs}


@pytest.mark.parametrize("ask", [[12649, 11224], [11224, 12649]])
def test_a_batch_paying_two_different_items_states_each_kamis_own(landed, ask):
    """Each payout's item is the inventory written in ITS window — after
    the previous kami's event — not any item written earlier."""
    landed.append(_receipt(_two_items_batch()))
    rows = {r["kami_id"]: r for r in
            server.harvest_stop(ask, account="testa")["payouts"]}
    assert rows[12649] == {"kami_id": 12649, "item": 2, "item_name": "VIPP",
                           "amount": 622}, rows
    assert rows[11224] == {"kami_id": 11224, "item": 1, "item_name": "MUSU",
                           "amount": 630}, rows


def test_two_items_written_before_one_event_state_the_amount_not_the_item(
    landed,
):
    """The 34031314 stop with its inventory write duplicated onto the
    item-1 inventory entity, right after the original: two catalogued
    items in one window. The event's amount stands; the item is not
    guessed."""
    raw = _raw("system_harvest_stop_34031314_ee431877.json")
    logs = list(raw["logs"])
    i = next(i for i, lg in enumerate(logs)
             if lg["topics"][3:4] == [_topic(INV_ITEM_2)])
    logs.insert(i + 1, _onto(logs[i], INV_ITEM_1))
    landed.append(_receipt({**raw, "logs": logs}))
    (row,) = server.harvest_stop([6058], account="testa")["payouts"]
    assert row["amount"] == 2, row
    assert row["item"] is None and row["item_name"] is None, row
    assert "inventory writes of items [1, 2]" in row["decode_error"], row


def test_two_events_for_one_kami_state_no_amount(landed):
    """The 34031314 stop with its HARVEST_STOP event duplicated right after
    itself: two events for kami 6058. Neither is taken."""
    raw = _raw("system_harvest_stop_34031314_ee431877.json")
    stop = "0x" + server.Web3.keccak(text="HARVEST_STOP").hex().removeprefix("0x")
    logs = list(raw["logs"])
    i = next(i for i, lg in enumerate(logs) if lg["topics"][1:2] == [stop])
    logs.insert(i + 1, dict(logs[i]))
    landed.append(_receipt({**raw, "logs": logs}))
    (row,) = server.harvest_stop([6058], account="testa")["payouts"]
    assert row["amount"] is None and row["item"] is None, row
    assert "2 HARVEST_STOP events for kami #6058" in row["decode_error"], row


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
# 60,000 -> 90,000. The gas gate's fee bound is what the chain prepays:
# gas limit x the price + 1 wei (every fixture receipt's log 0).
DEPOSIT_BOUND = 750_000 * PRICE + 1    # 1,875,000,000,001 wei
APPROVE_BOUND = 90_000 * PRICE + 1     #   225,000,000,001 wei
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


def test_the_bound_includes_the_wei_the_chain_prepays(portal_env):  # noqa: F811
    """Review ruling (4.2.0): every measured prepayment is gas limit x
    price + 1 wei, so a wallet holding exactly amount + gas limit x price
    is one wei short when the deposit's transferFrom runs: refused. One
    wei more is sent."""
    node, game, clock, portal, split = portal_env
    held = WEI + 750_000 * PRICE
    _fund(portal, split, held, allowance=WEI)
    with pytest.raises(server.PreTxValidationError) as ei:
        server.portal_deposit(103, ITEMS, account="split")
    assert not node.sends
    msg = str(ei.value)
    assert f"fee bound is {750_000 * PRICE + 1} wei" in msg, msg
    assert "1 wei short" in msg, msg
    _fund(portal, split, held + 1, allowance=WEI)
    assert server.portal_deposit(103, ITEMS, account="split")["status"] == (
        "success")


@pytest.mark.parametrize("value", [0, 7 * 10 ** 15])
def test_the_gas_gate_moves_by_the_same_wei(monkeypatch, value):
    """_require_gas_balance, the gate every send passes: a balance of
    exactly gas limit x price (+ value) is refused, one wei more passes."""
    from web3 import Web3
    gas = 3_000_000
    balance = {"wei": gas * PRICE + value}
    monkeypatch.setattr(server, "w3", type("W", (), {
        "eth": type("E", (), {"get_balance": staticmethod(
            lambda a: balance["wei"])}),
        "from_wei": staticmethod(Web3.from_wei)}))
    with pytest.raises(server.PreTxValidationError) as ei:
        server._require_gas_balance("0x" + "11" * 20, gas, value, "operator")
    assert "gas limit 3000000 at the flat price" in str(ei.value)
    balance["wei"] += 1
    server._require_gas_balance("0x" + "11" * 20, gas, value, "operator")


# The three balance checks that computed their own provision (review
# ruling, second round): each refuses exactly gas limit x price + value
# and passes one wei more, and its own refusal states the wei.

def test_fund_operator_needs_the_prepayment_wei(gas_env):  # noqa: F811
    """fund_operator: a plain transfer at _PLAIN_TRANSFER_GAS."""
    owner = gas_env.solo.owner_addr
    gas_env.balances[owner] = 10 ** 17 + server._PLAIN_TRANSFER_GAS * PRICE
    with pytest.raises(ValueError) as ei:
        server.fund_operator("0.1", account="solo")
    assert "+ 1 wei" in str(ei.value), str(ei.value)
    assert gas_env.sends == []
    gas_env.balances[owner] += 1
    assert server.fund_operator("0.1", account="solo")["operator_eth"] == "0.1"


def test_buy_kami_needs_the_prepayment_wei(accounts, monkeypatch, sent):
    from types import SimpleNamespace
    from web3 import Web3
    price = 10 ** 18
    monkeypatch.setattr(server, "get_kami_market_listings", lambda **kw: {
        "count": 1, "listings": [{
            "kami_index": 5, "price_eth": 1.0, "price_wei": price,
            "order_id_hex": hex(11), "seller_account_id": "999",
            "expiry": 0, "created_at": 60}]})
    gas = server._batch_gas(server._GAS_CEILINGS["buy_kami_base"],
                            server._GAS_CEILINGS["buy_kami_per_item"], 1,
                            "kami purchases")
    balance = {"wei": price + gas * PRICE}
    monkeypatch.setattr(server, "w3", SimpleNamespace(
        eth=SimpleNamespace(get_balance=lambda a: balance["wei"]),
        from_wei=Web3.from_wei))
    with pytest.raises(server.PreTxValidationError) as ei:
        server.buy_kami([5], "2.0", account="testa")
    msg = str(ei.value)
    assert "gas provision" in msg and "+ 1 wei" in msg, msg
    assert sent == []
    balance["wei"] += 1
    server.buy_kami([5], "2.0", account="testa")
    assert sent[-1]["system"] == "system.kamimarket.buy"
    assert sent[-1]["value_wei"] == price


def test_newbie_vendor_buy_needs_the_prepayment_wei(accounts, monkeypatch,
                                                    sent):
    from types import SimpleNamespace
    from conftest import FakeContract
    price = 6 * 10 ** 15
    balance = {"wei": price + server._GAS_CEILINGS["newbie_vendor_buy"] * PRICE}
    vendor = FakeContract({"calcPrice": lambda: price})
    monkeypatch.setattr(server, "w3", SimpleNamespace(
        eth=SimpleNamespace(contract=lambda address=None, abi=None: vendor,
                            get_balance=lambda a: balance["wei"]),
        from_wei=server.Web3.from_wei, to_wei=server.Web3.to_wei))
    monkeypatch.setattr(server, "_resolve_system", lambda sid: sid)
    monkeypatch.setattr(server, "_require_registered_owner", lambda a: 0x7777)
    with pytest.raises(server.PreTxValidationError) as ei:
        server.newbie_vendor_buy(1234, "0.01", account="testa")
    msg = str(ei.value)
    assert "gas provision" in msg and "+ 1 wei" in msg, msg
    assert sent == []
    balance["wei"] += 1
    server.newbie_vendor_buy(1234, "0.01", account="testa")
    assert sent[-1]["system"] == "system.newbievendor.buy"
    assert sent[-1]["value_wei"] == price


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


# ---------------------------------------------------------------------------
# H5 — two descriptions that misled a careful agent
# ---------------------------------------------------------------------------

def _description(name: str) -> str:
    return {t.name: t for t in server.mcp._tool_manager.list_tools()}[
        name].description


def test_lens_portal_says_open_withdrawals_are_every_other_accounts():
    """The lens filters the asked account's own rows out of
    openWithdrawals (the game client's panel); its own are in `receipts`
    (pending: lens_receipts). An agent looked for its receipts there."""
    d = _description("lens_portal")
    assert "openWithdrawals" in d and "OTHER" in d, d
    assert "`receipts`" in d and "lens_receipts" in d, d


def test_lens_room_says_exits_are_not_de_duplicated():
    """Special exits, then geometric neighbours, verbatim: a room can be
    listed twice."""
    d = _description("lens_room")
    assert "special exits" in d and "neighbours" in d, d
    assert "not de-duplicated" in d and "twice" in d, d

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

import server
from test_h350_families import FakeChain, seq_env  # noqa: F401  (fixture)

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

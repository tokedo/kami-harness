"""5.0.0 (B.2, B.3) — patch 0.4.5's two new chain rules, before signing.

T1  an item transfer's target must be an ACCOUNT (upstream 04cb25f8,
    ItemTransferSystem: require(isAccount(targetID), "ItemTransfer: target
    is not an account")). Through 4.7.0 nothing checked it here, and before
    the patch the chain credited any id — items sent to a non-account were
    lost. An unregistered target is refused before any dry-run, naming the
    chain's rule; a registered one goes on to the dry-run and lands.
T2  a soulbound kami (the newcomer vendor binds one for 3 days; the only
    binder at the pin) cannot be sent, rerolled or sacrificed: the expiry
    is read from chain (component.value at keccak256(abi.encode(kamiID,
    "SOULBOUND"))) and the four tools refuse with the end time. An expired
    bind passes. A bind the read did not see, refused by the dry-run with
    the chain's "kami is soulbound", reads the same.

Everything runs on the hermetic node (fakenode.py); all fixtures are
synthetic.
"""

from __future__ import annotations

import time as real_time

import eth_abi
import pytest
import web3._utils.threads as web3_threads

import server
from conftest import KEY_A, KEY_B
from fakenode import FakeNode, Result, VirtualClock, addr_for, make_w3

UNREGISTERED = "0x00000000000000000000000000000000000a11ce"
REGISTERED = "0x00000000000000000000000000000000000b0b00"
KAMI = 45


def _uint(v: int) -> Result:
    return Result(output=eth_abi.encode(["uint256"], [v]))


def _arg(a: bytes) -> int:
    return eth_abi.decode(["uint256"], a[:32])[0]


@pytest.fixture()
def env(monkeypatch):
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
    monkeypatch.setattr(server, "_resolve_system", addr_for)
    monkeypatch.setattr(server, "_resolve_component", addr_for)
    acct = server._Account("main", KEY_B, KEY_A)
    friend = server._Account("friend", KEY_A, KEY_B)
    monkeypatch.setattr(server, "_accounts", {"main": acct, "friend": friend})
    aid = int(acct.owner_addr, 16)
    monkeypatch.setattr(server, "_account_id_for_operator",
                        lambda addr: aid if addr == acct.operator_addr else 7)
    monkeypatch.setattr(server, "_require_registered_owner", lambda a: aid)
    monkeypatch.setattr(server, "_kami_owner_id", lambda k: aid)
    monkeypatch.setattr(server, "_kami_state", lambda k: "RESTING")
    monkeypatch.setattr(server, "_inventory_balance", lambda h, i: 10**9)
    monkeypatch.setattr(
        server, "_gacha_commit_and_reveal",
        lambda account, commit, tool: {"commit": commit, "reveal": None,
                                       "commit_ids": []})
    st = {"bound_until": {}, "names": {aid: "main",
                                       int(REGISTERED, 16): "bob"}}

    def value(n, c, a, commit):
        eid = _arg(a)
        for k, until in st["bound_until"].items():
            if eid == server._soulbound_entity_id(k):
                return _uint(until)
        return _uint(0)

    node.handle(addr_for("component.value"), "safeGet(uint256)", value)
    node.handle(addr_for("component.name"), "safeGet(uint256)",
                lambda n, c, a, k: Result(output=eth_abi.encode(
                    ["string"], [st["names"].get(_arg(a), "")])))
    node.handle(addr_for("component.state"), "safeGet(uint256)",
                lambda n, c, a, k: Result(output=eth_abi.encode(
                    ["string"], ["RESTING"])))
    node.handle(addr_for("component.id.kami.owns"), "safeGet(uint256)",
                lambda n, c, a, k: _uint(aid))
    return node, clock, acct, st


def _calls_to(node, system_id) -> int:
    to = addr_for(system_id).lower()
    return sum(1 for m, p in node.requests
               if m in ("eth_call", "eth_estimateGas")
               and (p[0].get("to") or "").lower() == to)


def _landed(node, system_id) -> int:
    to = addr_for(system_id).lower()
    return sum(1 for t in node.executed if (t.to or "").lower() == to)


# ---------------------------------------------------------------------------
# T1 — the item-transfer target must be an account
# ---------------------------------------------------------------------------

def test_an_unregistered_target_is_refused_before_the_dry_run(env):
    node, clock, acct, st = env
    with pytest.raises(server.PreTxValidationError) as ei:
        server.transfer_items([11301], [3], to_address=UNREGISTERED,
                              account="main")
    target = server.Web3.to_checksum_address(UNREGISTERED)
    assert str(ei.value) == (
        "validation failed; no transaction sent: target "
        f"{target} is not a registered account; items can only be sent to "
        "an account (the chain refuses with 'ItemTransfer: target is not an "
        "account')")
    assert _calls_to(node, "system.item.transfer") == 0
    assert node.executed == []


def test_an_unregistered_roster_label_is_named(env, monkeypatch):
    node, clock, acct, st = env
    st["names"].clear()
    with pytest.raises(server.PreTxValidationError,
                       match="target 'friend' is not a registered account"):
        server.transfer_items([11301], [3], to_account="friend",
                              account="main")
    assert node.executed == []


def test_a_registered_target_goes_on_to_the_dry_run_and_lands(env):
    node, clock, acct, st = env
    out = server.transfer_items([11301], [3], to_address=REGISTERED,
                                account="main")
    assert out["status"] == "success"
    assert _calls_to(node, "system.item.transfer") >= 1
    assert _landed(node, "system.item.transfer") == 1


# ---------------------------------------------------------------------------
# T2 — soulbound kamis
# ---------------------------------------------------------------------------

def _bound_text(clock, seconds_left: int) -> str:
    now = int(clock.now)
    iso = real_time.strftime("%Y-%m-%dT%H:%M:%SZ",
                             real_time.gmtime(now + seconds_left))
    return (f"kami {KAMI} is soulbound until {iso} "
            f"({seconds_left / 3600:.1f} h left); the chain refuses send / "
            f"reroll / sacrifice / listing / offers / unstaking until then")


FOUR = [
    ("transfer_kami", lambda: server.transfer_kami(
        [KAMI], to_address=REGISTERED, account="main"), "system.kami.send"),
    ("gacha_reroll", lambda: server.gacha_reroll([KAMI], account="main"),
     "system.kami.gacha.reroll"),
    ("sacrifice_kami", lambda: server.sacrifice_kami(KAMI, account="main"),
     "system.kami.sacrifice.commit"),
]


@pytest.mark.parametrize("name,call,system", FOUR, ids=[f[0] for f in FOUR])
def test_a_bound_kami_is_refused_with_its_end_time(env, name, call, system):
    node, clock, acct, st = env
    st["bound_until"][KAMI] = int(clock.now) + 1000
    with pytest.raises(server.PreTxValidationError) as ei:
        call()
    assert _bound_text(clock, 1000) in str(ei.value)
    assert _calls_to(node, system) == 0, "a dry-run ran for a bound kami"
    assert node.executed == []


def test_the_batch_skips_a_bound_kami_with_its_end_time(env):
    node, clock, acct, st = env
    st["bound_until"][KAMI] = int(clock.now) + 1000
    out = server.sacrifice_kami_batch([KAMI, 46], account="main",
                                      delay_seconds=0)
    rows = {r["kami_id"]: r for r in out["results"]}
    assert rows[KAMI]["status"] == "skipped"
    assert rows[KAMI]["reason"] == _bound_text(clock, 1000)
    assert rows[46]["status"] == "success"
    assert _landed(node, "system.kami.sacrifice.commit") == 1


@pytest.mark.parametrize("name,call,system", FOUR, ids=[f[0] for f in FOUR])
def test_an_expired_bind_passes(env, name, call, system):
    node, clock, acct, st = env
    st["bound_until"][KAMI] = int(clock.now) - 1
    out = call()
    assert out.get("status") == "success" or out.get("commit", {}).get(
        "status") == "success"
    assert _landed(node, system) == 1


def test_a_bind_the_read_missed_reads_the_same_from_the_dry_run(env):
    """The race: the pre-send read sees no bind, the chain's dry-run
    refuses "kami is soulbound" — the refusal is the fact message."""
    node, clock, acct, st = env
    until = int(clock.now) + 7200

    def send(n, c, a, commit):
        st["bound_until"][KAMI] = until        # bound in between
        return Result(status=0, revert="kami is soulbound")

    node.handle(addr_for("system.kami.send"),
                "executeTyped(uint32[],address)", send)
    with pytest.raises(server.PreTxValidationError) as ei:
        server.transfer_kami([KAMI], to_address=REGISTERED, account="main")
    assert _bound_text(clock, 7200) in str(ei.value)
    assert node.executed == []


def test_the_vendor_names_what_the_bind_blocks():
    d = {t.name: t for t in server.mcp._tool_manager.list_tools()}[
        "newbie_vendor_buy"].description
    assert ("listing, offer acceptance, unstaking, sending, rerolling or "
            "sacrificing") in " ".join(d.split())


def test_the_soulbind_entity_is_abi_encoded_not_packed():
    """LibSoulbound._entity = keccak256(abi.encode(kamiID, "SOULBOUND")):
    the string is a dynamic tail (offset, length, padded bytes)."""
    from eth_utils import keccak
    kid = server._kami_entity_id(KAMI)
    encoded = (kid.to_bytes(32, "big") + (64).to_bytes(32, "big")
               + (9).to_bytes(32, "big") + b"SOULBOUND".ljust(32, b"\0"))
    assert server._soulbound_entity_id(KAMI) == int.from_bytes(
        keccak(encoded), "big")
    packed = keccak(kid.to_bytes(32, "big") + b"SOULBOUND")
    assert server._soulbound_entity_id(KAMI) != int.from_bytes(packed, "big")

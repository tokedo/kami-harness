"""4.0.0 leg A — the lane and the loops, asserted as invariants.

test_h400_send_path.py holds the reproductions of the defects; this file
pins the behaviour that replaced them: where the lane's state lives and
what it may contain, how a restarted process treats transactions an
earlier one left armed, how the call reports a gap it filled, how
receipts are collected, how concurrent calls interleave, and the A4
items (travel, a moved system, equipment, scavenge).
"""

from __future__ import annotations

import asyncio
import json
import os
import stat
import threading
import time
from types import SimpleNamespace

import anyio
import eth_abi
import pytest
from eth_account import Account
from mcp.shared.memory import create_connected_server_and_client_session

import lanes
import server
from conftest import KEY_A, KEY_B
from fakenode import READINESS_ERROR, Result, addr_for, make_w3
from test_h400_send_path import (  # noqa: F401  (fixtures)
    AID,
    Game,
    _Hold,
    _feeds,
    _nonce_of,
    _refuse_nonce,
    chain_env,
    scav_env,
    wall_env,
)


def _sign_feed(nonce: int, kami: int = 21, item: int = 11301) -> bytes:
    """A feed signed by an EARLIER process on the same operator key."""
    data = bytes.fromhex(server.Web3.keccak(
        text="executeTyped(uint256,uint32)")[:4].hex()) + eth_abi.encode(
        ["uint256", "uint32"], [server._kami_entity_id(kami), item])
    return bytes(Account.sign_transaction({
        "to": addr_for("system.kami.use.item"), "data": data, "value": 0,
        "gas": 3_500_000, "nonce": nonce, "chainId": server.CHAIN_ID,
        "maxFeePerGas": 2_500_000, "maxPriorityFeePerGas": 0,
    }, KEY_A).raw_transaction)


def _arm_earlier_tail(node, op, nonces):
    """An earlier process signed and broadcast `nonces`, and the node
    queued them behind a gap; its lane file says so."""
    lane = lanes.Lane(server.CHAIN_ID, server.Web3.to_checksum_address(op),
                      lanes.default_dir())
    hashes = []
    for step, n in enumerate(nonces, start=1):
        raw = _sign_feed(n)
        resp = node.rpc({"jsonrpc": "2.0", "id": 1,
                         "method": "eth_sendRawTransaction",
                         "params": ["0x" + raw.hex()]})
        h = resp["result"]
        e = lane.add(n, h, raw, "act_sequence#earlier", "act_sequence", step)
        lane.offered(e)
        hashes.append(h)
    lane.save()
    return hashes


# ---------------------------------------------------------------------------
# The lane's state file
# ---------------------------------------------------------------------------

def test_the_lane_directory_is_independent_of_the_secret_store(
    monkeypatch, tmp_path,
):
    monkeypatch.delenv("KAMI_LANE_DIR", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("KAMI_KEYS_FILE", str(tmp_path / "does-not-exist.env"))
    assert lanes.default_dir() == tmp_path / ".kami-harness" / "lanes"
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert lanes.default_dir() == tmp_path / "state" / "kami-harness" / "lanes"
    monkeypatch.setenv("KAMI_LANE_DIR", str(tmp_path / "explicit"))
    assert lanes.default_dir() == tmp_path / "explicit"


def test_the_ledger_holds_no_key_and_no_raw_bytes_once_resolved(chain_env):
    node, game, clock, op = chain_env
    game.xp[server._kami_entity_id(5)] = 1_000
    server.level_up_kami(5, account="testa")
    # A definitive refusal leaves a tombstone, never the signed bytes.
    node.fail("eth_sendRawTransaction", times=1, error={
        "code": -32000, "message": "insufficient funds for gas * price"})
    with pytest.raises(Exception):
        server.level_up_kami(5, account="testa")
    lane = server._lane(op)
    path = lane.path
    data = json.loads(path.read_text())
    assert stat.S_IMODE(os.stat(path.parent).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    text = path.read_text()
    assert KEY_A[2:].lower() not in text.lower()
    assert data["floor"] == 501 and data["mined_top"] == 500
    assert [e["state"] for e in data["entries"]] == ["released"]
    assert all(e["raw"] is None for e in data["entries"])


def test_a_repeated_hash_is_refused_by_the_ledger():
    lane = lanes.Lane(1, "0x" + "11" * 20, lanes.default_dir())
    lane.add(7, "0xaa", b"\x01", "c", "t")
    with pytest.raises(ValueError):
        lane.add(7, "0xaa", b"\x01", "c2", "t")


# ---------------------------------------------------------------------------
# A restarted process and an armed tail (C2/C3/C4)
# ---------------------------------------------------------------------------

def test_a_later_call_drains_an_earlier_calls_armed_tail_and_says_so(
    chain_env, monkeypatch,
):
    node, game, clock, op = chain_env
    game.inv[11301] = 10
    eid = server._kami_entity_id(5)
    game.xp[eid] = 1_000
    armed = _arm_earlier_tail(node, op, [501, 502, 503])
    assert node.queued(op) == [501, 502, 503]       # armed behind 500
    monkeypatch.setattr(server, "_LANES", {})       # a restarted process
    dry_runs = []
    real = server._dry_run
    monkeypatch.setattr(server, "_dry_run",
                        lambda *a, **k: dry_runs.append(1) or real(*a, **k))

    out = server.run_tool("level_up_kami", kami_id=5, account="testa")

    assert list(out)[0] == "notice"
    note = out["notice"]
    for h in armed:
        assert f"{h} (act_sequence step" in note and "-> success" in note
    assert "Gap filled with a zero-value self-transfer: nonce 500" in note
    fill = next(t for t in node.executed if t.nonce == 500)
    assert fill.to == op.lower() and fill.value == 0 and fill.data == b""
    assert game.inv[11301] == 7                     # the tail ran, now
    mine = next(t for t in node.executed if t.hash == out["tx_hash"])
    assert mine.nonce == 504                        # after the tail
    assert len(dry_runs) == 2                       # validation re-ran


def test_a_tail_that_cannot_be_filled_blocks_the_lane(chain_env, monkeypatch):
    node, game, clock, op = chain_env
    game.xp[server._kami_entity_id(5)] = 1_000
    armed = _arm_earlier_tail(node, op, [501, 502])
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
    assert game.level[server._kami_entity_id(5)] == 0
    assert node.queued(op) == [501, 502]


def test_a_released_transaction_that_mines_late_is_attributed(chain_env):
    node, game, clock, op = chain_env
    game.xp[server._kami_entity_id(5)] = 1_000
    lane = server._lane(op)
    raw = _sign_feed(500)
    h = "0x" + server.Web3.keccak(raw).hex().removeprefix("0x")
    with lane.critical():
        e = lane.add(500, h, raw, "x#1", "use_item_batch", 2)
        lane.release(e, "proven absent")
    game.inv[11301] = 1
    node.rpc({"jsonrpc": "2.0", "id": 1, "method": "eth_sendRawTransaction",
              "params": ["0x" + raw.hex()]})            # it mines anyway
    out = server.run_tool("level_up_kami", kami_id=5, account="testa")
    assert f"had released, {h} (use_item_batch step 2" in out["notice"]
    assert "mined late at nonce 500" in out["notice"]


# ---------------------------------------------------------------------------
# act_sequence: the first line, and receipts in batches
# ---------------------------------------------------------------------------

def test_a_filled_gap_is_the_first_line_of_the_sequence_result(chain_env):
    node, game, clock, op = chain_env
    game.inv[11301] = 50
    _refuse_nonce(node, 502, READINESS_ERROR)
    for _ in range(3):                                  # outlast re-offers
        _refuse_nonce(node, 502, READINESS_ERROR)
    out = server.act_sequence(_feeds(6), account="testa")
    assert list(out)[0] == "notice"
    row = out["steps"][2]
    assert row["status"] == "not_sent"
    fill = row["nonce_filled_by"]
    assert out["notice"].startswith("step 2 (feed) was dropped: jsonrpc "
                                    "readiness error")
    assert f"nonce 502 was filled by a zero-value self-transfer {fill}" in (
        out["notice"])
    assert "steps 3-5 ran after it" in out["notice"]
    assert [r["status"] for r in out["steps"]] == [
        "success", "success", "not_sent", "success", "success", "success"]
    assert out["filled"] == [{"nonce": 502, "tx_hash": fill, "for_step": 2,
                              "status": "success"}]
    assert node.queued(op) == []


def test_sequence_receipts_are_collected_in_batches(chain_env):
    node, game, clock, op = chain_env
    game.inv[11301] = 50
    server.act_sequence(_feeds(6), account="testa")
    receipt_batches = [b for b in server.w3.provider.batches
                       if b and set(b) == {"eth_getTransactionReceipt"}]
    assert receipt_batches and len(receipt_batches[0]) == 6
    singles = [m for m, _p in node.requests
               if m == "eth_getTransactionReceipt"]
    assert len(singles) == 6        # the batch's own items, nothing more


# ---------------------------------------------------------------------------
# Lanes are per signer address
# ---------------------------------------------------------------------------

def test_owner_and_operator_are_separate_lanes_and_one_address_is_one(
    chain_env, monkeypatch,
):
    node, game, clock, op = chain_env
    split = server._Account("split", KEY_B, KEY_A)     # operator B, owner A
    monkeypatch.setitem(server._accounts, "split", split)
    node.set_nonce(split.operator_addr, 40)
    game.xp[server._kami_entity_id(5)] = 1_000
    server._send_tx("split", "system.kami.level", server._ABI_LEVEL,
                    [server._kami_entity_id(5)])
    server._send_tx_owner("split", "system.trade.create",
                          server._ABI_TRADE_CREATE, [[1], [1], [2], [1], 0])
    keys = {a for _c, a in server._LANES}
    assert keys == {split.operator_addr, split.owner_addr}
    assert server._lane(split.operator_addr).floor == 41
    assert server._lane(split.owner_addr).floor == 501
    # testa's owner and operator are ONE address, so ONE nonce lane.
    assert accounts_one_lane(monkeypatch)


def accounts_one_lane(monkeypatch) -> bool:
    a = server._get_account("testa")
    return a.owner_addr == a.operator_addr and (
        server._lane(a.owner_addr) is server._lane(a.operator_addr))


# ---------------------------------------------------------------------------
# Concurrency: signers in parallel, one signer interleaved, progress, cancel
# ---------------------------------------------------------------------------

class _HoldReceipt:
    """Holds the first receipt poll of the Nth broadcast until released."""

    def __init__(self, node, nth=1, watchdog_s=3.0):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.released_by_watchdog = False
        sends = []
        original = node.rpc

        def rpc(request):
            resp = original(request)
            if request["method"] == "eth_sendRawTransaction" and "result" in resp:
                sends.append(resp["result"])
            if (request["method"] == "eth_getTransactionReceipt"
                    and len(sends) >= nth and request["params"]
                    and request["params"][0] == sends[nth - 1]
                    and not self.release.is_set()):
                self.entered.set()
                if not self.release.wait(watchdog_s):
                    self.released_by_watchdog = True
            return resp

        node.rpc = rpc


def _mcp(coro_fn, **session_kw):
    async def main():
        async with create_connected_server_and_client_session(
            server.mcp._mcp_server, **session_kw
        ) as client:
            await coro_fn(client)
    anyio.run(main)


def test_writes_on_different_signers_run_concurrently(wall_env, monkeypatch):
    node, game = wall_env
    hold = _Hold(node, nth=1, watchdog_s=3.0)       # holds testa's send
    marks = {}

    async def body(client):
        async with anyio.create_task_group() as tg:
            async def slow():
                await client.call_tool("use_item_batch", {
                    "kami_id": 21, "item_id": 11301, "count": 1,
                    "account": "testa"})
            tg.start_soon(slow)
            while not hold.entered.is_set():
                await anyio.sleep(0.01)
            r = await client.call_tool("use_item_batch", {
                "kami_id": 22, "item_id": 11301, "count": 1,
                "account": "testb"})
            marks["b_error"] = r.isError
            marks["b_done_while_a_held"] = not hold.release.is_set()
            hold.release.set()

    _mcp(body)
    assert marks["b_error"] is False
    assert marks["b_done_while_a_held"] and not hold.released_by_watchdog
    assert game.inv[11301] == 8


def test_one_signer_interleaves_at_step_boundaries(wall_env):
    """The lane lock covers the send critical section, not the receipt
    wait: an emergency write on the SAME signer goes out while a loop on
    that signer is waiting for its receipt."""
    node, game = wall_env
    hold = _HoldReceipt(node, nth=1, watchdog_s=3.0)
    game.xp[server._kami_entity_id(5)] = 1_000
    marks = {}

    async def body(client):
        async with anyio.create_task_group() as tg:
            async def loop():
                await client.call_tool("use_item_batch", {
                    "kami_id": 21, "item_id": 11301, "count": 2,
                    "account": "testa"})
            tg.start_soon(loop)
            while not hold.entered.is_set():
                await anyio.sleep(0.01)
            r = await client.call_tool("level_up_kami", {
                "kami_id": 5, "account": "testa"})
            marks["error"] = r.isError
            marks["while_held"] = not hold.release.is_set()
            hold.release.set()

    _mcp(body)
    assert marks["error"] is False and marks["while_held"]
    nonces = sorted(t.nonce for t in node.executed)
    assert nonces == list(range(nonces[0], nonces[0] + 3))   # no gap, no dup


def test_progress_is_reported_per_landed_transaction(wall_env):
    node, game = wall_env
    seen = []

    async def body(client):
        async def on_progress(progress, total, message):
            seen.append(message)
        await client.call_tool("use_item_batch", {
            "kami_id": 21, "item_id": 11301, "count": 3, "account": "testa"},
            progress_callback=on_progress)

    _mcp(body)
    assert len(seen) == 3
    assert all("use_item_batch: transaction" in m and "success 0x" in m
               for m in seen)


def test_a_cancel_logs_the_partial_outcome(wall_env):
    node, game = wall_env
    hold = _Hold(node, nth=1, watchdog_s=3.0)
    logs = []

    async def on_log(params):
        logs.append(str(params.data))

    async def body(client):
        async with anyio.create_task_group() as tg:
            rid = client._request_id

            async def write():
                try:
                    await client.call_tool("use_item_batch", {
                        "kami_id": 21, "item_id": 11301, "count": 4,
                        "account": "testa"})
                except Exception:
                    pass
            tg.start_soon(write)
            while not hold.entered.is_set():
                await anyio.sleep(0.01)
            from mcp import types as t
            await client.send_notification(t.ClientNotification(
                t.CancelledNotification(params=t.CancelledNotificationParams(
                    requestId=rid))))
            await anyio.sleep(0.2)
            hold.release.set()
            await anyio.sleep(0.5)

    _mcp(body, logging_callback=on_log)
    assert len(logs) == 1
    assert "use_item_batch was cancelled; partial outcome" in logs[0]
    assert "cancelled by the client" in logs[0]
    assert "0x" in logs[0]                       # the use that landed


# ---------------------------------------------------------------------------
# A4 — travel on one stamina unit
# ---------------------------------------------------------------------------

def _travel_env(monkeypatch, stamina, path, sp=()):
    monkeypatch.setattr(server, "_require_registered_operator", lambda a: AID)
    view = {"index": 1, "name": "t", "stamina": stamina, "room": path[0]}
    monkeypatch.setattr(server, "_read_account_view",
                        lambda aid: (dict(view), ""))
    monkeypatch.setattr(server, "_sp_item_balances", lambda aid: [
        {"itemIndex": i, "balance": n, "name": "sp"} for i, n in sp])
    monkeypatch.setattr(server, "rooms_graph", SimpleNamespace(
        shortest_path=lambda a, b, blocked=None: list(path),
        move_cost=lambda p: 5 * (len(p) - 1),
        gates_on=lambda a, b: [],
    ))
    return view


def test_travel_plans_on_the_clamped_stamina(accounts, monkeypatch):
    """A getter value above the cap (6,360 observed against a real 100)
    no longer makes a 23-hop walk look feasible without items."""
    _travel_env(monkeypatch, 6360, list(range(1, 25)))
    r = asyncio.run(server.travel_to_room(24, account="testa", dry_run=True))
    assert r["stamina_have"] == 100
    assert r["stamina_needed"] == 115
    assert r["feasible"] is False


def test_an_out_of_stamina_hop_uses_an_item_and_is_retried(
    accounts, monkeypatch,
):
    view = _travel_env(monkeypatch, 100, [1, 2, 3], sp=[(21201, 2)])
    sent = []

    def send(account, system_id, abi, args, gas_limit=None, **kw):
        sent.append((system_id, list(args)))
        if system_id == "system.account.move" and args == [3] and not any(
            s == "system.account.use.item" for s, _a in sent
        ):
            raise server.PreTxValidationError(
                "transaction dry-run reverted: Account: insufficient stamina")
        return {"tx_hash": f"0x{len(sent):02x}", "status": "success",
                "block": 1, "gas_used": 1}

    monkeypatch.setattr(server, "_send_tx_retry", send)
    r = asyncio.run(server.travel_to_room(3, account="testa", use_items=True))
    assert r["reached_target"] is True
    assert [s for s, _a in sent] == [
        "system.account.move", "system.account.move",
        "system.account.use.item", "system.account.move"]
    assert r["items_used"] == [{"item_id": 21201, "count": 1}]
    assert r["stamina_remaining"] == 100            # read back, clamped
    view["stamina"] = 0


def test_an_unplannable_route_is_an_error_not_a_result(accounts, monkeypatch):
    _travel_env(monkeypatch, 100, [1, 2])

    def no_route(a, b, aid):
        raise ValueError("room 99 is not in the room graph")

    monkeypatch.setattr(server, "_plan_gates", no_route)
    with pytest.raises(server.PreTxValidationError) as ei:
        asyncio.run(server.travel_to_room(99, account="testa"))
    assert "room 99 is not in the room graph (current room 1" in str(ei.value)


# ---------------------------------------------------------------------------
# A4 — a system that moved
# ---------------------------------------------------------------------------

def test_a_dry_run_revert_re_resolves_a_moved_system_once(
    chain_env, monkeypatch,
):
    node, game, clock, op = chain_env
    old = addr_for("system.kami.level.OLD")
    new = addr_for("system.kami.level")
    monkeypatch.setattr(server, "_system_cache",
                        {"system.kami.level": old})
    resolved = []
    monkeypatch.setattr(server, "_resolve_system", lambda sid: (
        resolved.append(sid) or server._system_cache.setdefault(sid, new)))
    node.handle(old, "executeTyped(uint256)", lambda n, c, a, commit: Result(
        status=0, revert="System: not authorized"))
    game.xp[server._kami_entity_id(5)] = 1_000
    r = server.level_up_kami(5, account="testa")
    assert r["status"] == "success"
    assert server._system_cache["system.kami.level"] == new
    assert game.level[server._kami_entity_id(5)] == 1


def test_an_unchanged_system_address_keeps_the_original_refusal(
    chain_env, monkeypatch,
):
    node, game, clock, op = chain_env
    addr = addr_for("system.kami.level")
    monkeypatch.setattr(server, "_system_cache", {"system.kami.level": addr})
    monkeypatch.setattr(server, "_resolve_system", lambda sid: (
        server._system_cache.setdefault(sid, addr)))
    with pytest.raises(server.PreTxValidationError) as ei:
        server.level_up_kami(5, account="testa")      # no XP
    assert "need more experience" in str(ei.value)


# ---------------------------------------------------------------------------
# A4 — equipment: an occupied slot is skipped, never swapped
# ---------------------------------------------------------------------------

def _equip_env(node, occupant: dict):
    def index_item(n, c, args, commit):
        (eid,) = eth_abi.decode(["uint256"], args[:32])
        for kami, item in occupant.items():
            if eid == server._equipment_instance_id(kami):
                return Result(output=eth_abi.encode(["uint32"], [item]))
        return Result(output=eth_abi.encode(["uint32"], [0]))

    node.handle(addr_for("component.index.item"), "safeGet(uint256)",
                index_item)


def test_an_occupied_slot_is_skipped_and_its_item_named(chain_env):
    node, game, clock, op = chain_env
    _equip_env(node, {1: 30001})
    out = server.equip_all_batch(
        [{"kami_id": 1, "item_index": 30002},
         {"kami_id": 2, "item_index": 30002}],
        account="testa", delay_seconds=0)
    rows = {r["kami_id"]: r for r in out["results"]}
    assert rows[1]["status"] == "skipped"
    assert rows[1]["equipped_item"] == 30001
    assert "occupied by item 30001" in rows[1]["reason"]
    assert rows[2]["status"] == "success"
    assert out["equipped"] == 1 and out["skipped"] == 1


def test_equip_item_refuses_an_occupied_slot(chain_env):
    node, game, clock, op = chain_env
    game.inv[30002] = 1
    _equip_env(node, {1: 30001})
    with pytest.raises(server.PreTxValidationError) as ei:
        server.equip_item(1, 30002, account="testa")
    assert "occupied by item 30001" in str(ei.value)
    assert not node.sends


# ---------------------------------------------------------------------------
# A4 — scavenge: a commit drained between the read and the reveal
# ---------------------------------------------------------------------------

def test_a_reveal_that_reveals_nothing_is_flagged(scav_env, monkeypatch):
    """The commit is drained elsewhere AFTER this call read its rolls,
    so the reveal is sent, succeeds, and carries no droptable event."""
    node, game, clock, op = scav_env
    real = server._send_reveal_tx

    def drained_first(account, ids):
        for c in ids:
            if c in game.commits:
                game.drain(c, game.commits[c])
        return real(account, ids)

    monkeypatch.setattr(server, "_send_reveal_tx", drained_first)
    out = server.scavenge_claim_and_reveal(53, account="testa")
    assert out["revealed_items"] == [] and out["already_revealed"] is True
    assert out["reveals"] == 1
    assert "revealed nothing" in out["notice"]


def test_droptable_reveal_reports_the_rolls_left(scav_env):
    node, game, clock, op = scav_env
    claim = server.scavenge_claim(53, account="testa")
    clock.sleep(2)
    out = server.droptable_reveal(claim["commit_ids"], account="testa")
    assert out["rolls_remaining"] == {str(Game.COMMIT_ID): 7_000}
    assert "7000 rolls are still unrevealed" in out["notice"]

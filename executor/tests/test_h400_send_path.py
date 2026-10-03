"""4.0.0 leg A — the send path and concurrency.

Every test here drives the PRODUCTION send path end to end against the
hermetic node in `fakenode.py`: a real `web3.Web3` over a simulated
JSON-RPC node, real local signing with the public local-dev keys, real
receipt polling (on a virtual clock). Nothing above the wire is mocked
except the read-only state gates the existing suite already fakes.

Each reproduction states the mechanism it isolates. They were written
against the 3.7.0 code (`a2c22c1`) and FAIL there for the stated
reason; that failure is the bite of the regression test.
"""

from __future__ import annotations

import asyncio
import inspect
import threading
import time
from collections import defaultdict

import anyio
import eth_abi
import pytest
import web3._utils.threads as web3_threads
from mcp import types as mcp_types
from mcp.shared.memory import create_connected_server_and_client_session

import server
from fakenode import (
    READINESS_ERROR,
    FakeNode,
    Result,
    VirtualClock,
    addr_for,
    make_w3,
)

AID = 0x4242


def _nonce_of(raw_hex: str) -> int:
    from eth_account.typed_transactions import TypedTransaction
    from hexbytes import HexBytes
    tx = TypedTransaction.from_bytes(HexBytes(raw_hex))
    return int(tx.as_dict()["nonce"])


def _uint(v: int) -> Result:
    return Result(output=eth_abi.encode(["uint256"], [v]))


class Game:
    """The slice of game state these loops touch, as contract handlers."""

    def __init__(self, node: FakeNode):
        self.node = node
        self.level: dict[int, int] = defaultdict(int)
        self.xp: dict[int, int] = defaultdict(int)
        self.inv: dict[int, int] = defaultdict(int)
        self.skills: dict[tuple[int, int], int] = defaultdict(int)
        self.commits: dict[int, int] = {}     # commit id -> remaining rolls
        self.loot: dict[int, int] = defaultdict(int)
        self.after_commit = []                # hooks(system, sender)
        h = node.handle
        h(addr_for("system.kami.level"), "executeTyped(uint256)", self._level)
        h(addr_for("system.kami.use.item"), "executeTyped(uint256,uint32)",
          self._feed)
        h(addr_for("system.skill.upgrade"), "executeTyped(uint256,uint32)",
          self._skill)
        h(addr_for("component.level"), "safeGet(uint256)",
          lambda n, c, a, commit: _uint(self.level[_eid(a)]))
        h(addr_for("component.experience"), "safeGet(uint256)",
          lambda n, c, a, commit: _uint(self.xp[_eid(a)]))
        h(addr_for("system.scavenge.claim"), "executeTyped(uint256)",
          self._claim)
        h(addr_for("system.droptable.item.reveal"), "executeTyped(uint256[])",
          self._reveal)
        h(addr_for("component.value"), "safeGet(uint256)", self._value)

    def _value(self, node, caller, args, commit):
        """component.value: a commit's remaining rolls, or an inventory
        balance of the test account (inventory.instance entity)."""
        eid = _eid(args)
        if eid in self.commits:
            return _uint(self.commits[eid])
        if eid == self.COMMIT_ID:
            return _uint(0)       # safeGet of a removed value reads 0
        for item, count in list(self.inv.items()):
            if eid == server._inventory_entity_id(AID, item):
                return _uint(count)
        return Result(status=0, revert="component not modelled")

    def _done(self, system, caller, commit):
        if commit:
            for hook in list(self.after_commit):
                hook(system, caller.sender)

    def _level(self, node, caller, args, commit):
        eid = _eid(args)
        if self.xp[eid] < 100:
            return Result(status=0, revert="KamiLevel: need more experience")
        if commit:
            self.level[eid] += 1
            self.xp[eid] -= 100
        self._done("level", caller, commit)
        return Result(gas_used=600_000)

    def _feed(self, node, caller, args, commit):
        eid, item = eth_abi.decode(["uint256", "uint32"], args)
        if self.inv[item] < 1:
            return Result(status=0, revert="Inventory: insufficient balance")
        if commit:
            self.inv[item] -= 1
            self.xp[eid] += 100
        self._done("feed", caller, commit)
        return Result(gas_used=1_300_000)

    def _skill(self, node, caller, args, commit):
        eid, skill = eth_abi.decode(["uint256", "uint32"], args)
        if commit:
            self.skills[(eid, skill)] += 1
        self._done("skill", caller, commit)
        return Result(gas_used=700_000)

    # --- scavenge: the upstream chunked reveal (LibDroptable,
    # MAX_ROLLS_PER_REVEAL = 5000 per transaction across all commits; a
    # drained commit is filtered to 0 and skipped without a revert).

    CLAIM_ROLLS = 12_000
    COMMIT_ID = 2 ** 200 + 77
    KEYS = (1005, 11302)
    MAX_ROLLS = 5_000
    TOPIC = "0x" + server._DROPTABLE_EVENT_TOPIC

    def _claim(self, node, caller, args, commit):
        if commit:
            self.commits[self.COMMIT_ID] = self.CLAIM_ROLLS
        data = eth_abi.encode(
            ["uint256"] * 4, [7, 3, 1, self.COMMIT_ID])
        self._done("claim", caller, commit)
        return Result(gas_used=900_000, logs=[(addr_for("world"), [self.TOPIC], data)])

    def drain(self, cid, rolls):
        """Reveal `rolls` of commit `cid` (the chain's own chunk rule)."""
        remaining = self.commits.get(cid, 0)
        chunk = min(remaining, rolls)
        a = chunk // 2
        amounts = [a, chunk - a]
        if chunk == remaining:
            self.commits.pop(cid, None)
        else:
            self.commits[cid] = remaining - chunk
        for k, amt in zip(self.KEYS, amounts):
            self.loot[k] += amt
        return chunk, amounts

    def _reveal(self, node, caller, args, commit):
        (ids,) = eth_abi.decode(["uint256[]"], args)
        logs = []
        budget = self.MAX_ROLLS
        snapshot = dict(self.commits), dict(self.loot)
        for cid in ids:
            if budget == 0:
                break
            if cid not in self.commits:      # filterInvalid: drained -> 0
                continue
            chunk, amounts = self.drain(cid, budget)
            budget -= chunk
            n = len(self.KEYS)
            data = eth_abi.encode(
                ["uint256"] * (2 * n + 2 + 2),
                [cid, 1, n, *self.KEYS, n, *amounts],
            )
            logs.append((addr_for("world"), [self.TOPIC], data))
        if not commit:
            self.commits, self.loot = snapshot[0], defaultdict(int, snapshot[1])
        self._done("reveal", caller, commit)
        return Result(gas_used=200_000 + 1_130 * (self.MAX_ROLLS - budget),
                      logs=logs)


def _eid(args: bytes) -> int:
    return eth_abi.decode(["uint256"], args[:32])[0]


def _call(fn, **kw):
    """Call a tool body whether it is `def` or `async def`."""
    out = fn(**kw)
    if inspect.isawaitable(out):
        out = asyncio.run(out)
    return out


@pytest.fixture()
def chain_env(monkeypatch, accounts):
    """A real Web3 over the fake node; the read-only gates pass."""
    node = FakeNode(server.CHAIN_ID)
    game = Game(node)
    # The production client construction (servers before 4.0.0 lack it).
    w3 = getattr(server, "_install_read_retry", lambda w: w)(make_w3(node))
    clock = VirtualClock()
    # One block per virtual second, never backwards.
    t0, b0 = clock.now, node.block
    clock.on_sleep.append(lambda now: setattr(
        node, "block", max(node.block, b0 + int(now - t0))))
    monkeypatch.setattr(server, "w3", w3)
    monkeypatch.setattr(server, "time", clock)
    monkeypatch.setattr(web3_threads, "time", clock)
    monkeypatch.setattr(server, "_resolve_system", addr_for)
    monkeypatch.setattr(server, "_resolve_component", addr_for)
    monkeypatch.setattr(server, "_require_registered_operator", lambda a: AID)
    monkeypatch.setattr(server, "_require_registered_owner", lambda a: AID)
    monkeypatch.setattr(server, "_kami_owner_id", lambda k: AID)
    monkeypatch.setattr(server, "_kami_state", lambda k: "RESTING")
    monkeypatch.setattr(server, "_harvest_state", lambda k: "ACTIVE")
    monkeypatch.setattr(server, "_killer_bounty", lambda k: 0)
    monkeypatch.setattr(server, "_inventory_balance",
                        lambda holder, item: game.inv[item])
    op = accounts["testa"].operator_addr
    node.set_nonce(op, 500)
    return node, game, clock, op


def _hashes(rows) -> list[str]:
    return [r["tx_hash"] for r in rows if r.get("tx_hash")]


# ---------------------------------------------------------------------------
# A1 — duplicate hash / double count
# ---------------------------------------------------------------------------

def test_two_steps_never_share_a_nonce_and_a_level_is_counted_once(chain_env):
    """REPRODUCTION (A1, dup-hash).

    Mechanism: every send reads its nonce with ONE
    `eth_getTransactionCount(pending)` and keeps no local state. Right
    after step 1's receipt, the read for step 2 is served by a replica
    that has not seen step 1, so step 2 is signed at step 1's nonce. A
    level-up has identical calldata every time and its gas estimate is
    identical, so the signed bytes — and the hash — are IDENTICAL; the
    node answers the re-offer with that hash and the receipt wait returns
    step 1's receipt. 3.7.0 reports two levels, two rows with one hash,
    and the chain has one level.
    """
    node, game, clock, op = chain_env
    kami = 7
    eid = server._kami_entity_id(kami)
    game.level[eid], game.xp[eid] = 10, 10_000
    armed = []

    def lag_after_first(system, sender):
        if system == "level" and not armed:
            armed.append(True)
            node.lag(sender, times=2, behind=1)

    game.after_commit.append(lag_after_first)
    out = _call(server.level_to, kami_id=kami, target_level=12,
                account="testa", allow_partial=True)

    hashes = _hashes(out["txs"])
    assert len(hashes) == len(set(hashes)), (
        f"one hash reported for two steps: {hashes}; reported "
        f"levels_gained={out.get('levels_gained')} "
        f"reached_level={out.get('reached_level')}; chain level "
        f"{game.level[eid]}; transactions mined {len(node.executed)}")
    assert out.get("reached_level") == game.level[eid], (
        f"reported level {out.get('reached_level')}, chain level "
        f"{game.level[eid]}")
    assert game.level[eid] == 12


def test_a_nonce_reused_by_a_stale_read_never_reports_unconfirmed(chain_env):
    """REPRODUCTION (A1, the same root with DIFFERENT calldata).

    Two skill upgrades on different skills: step 2 is signed at step 1's
    nonce (stale read), so its bytes differ — a new hash at a consumed
    nonce, which the lagging replica admits and the chain never mines.
    3.7.0 waits the full 120 s receipt budget and reports the upgrade
    UNCONFIRMED ("may still be included") although the nonce was
    consumed by step 1's hash before the wait began.
    """
    node, game, clock, op = chain_env
    kami = 8
    armed = []

    def lag_after_first(system, sender):
        if system == "skill" and not armed:
            armed.append(True)
            node.lag(sender, times=2, behind=1)

    game.after_commit.append(lag_after_first)
    t0 = clock.now
    out = server.allocate_skills(
        kami, [{"skill_index": 110, "points": 1},
               {"skill_index": 120, "points": 1}],
        account="testa", allow_partial=True,
    )
    eid = server._kami_entity_id(kami)
    assert game.skills[(eid, 110)] == 1
    assert game.skills[(eid, 120)] == 1, (
        f"second upgrade never landed; result: {out}; waited "
        f"{clock.now - t0:.0f}s")
    assert out.get("allocated") == 2


# ---------------------------------------------------------------------------
# A1 — a stranded sequence tail, re-armed by a later call
# ---------------------------------------------------------------------------

def _feeds(n, kami=21, item=11301):
    return [{"op": "feed", "kami_id": kami, "item_id": item} for _ in range(n)]


def _refuse_nonce(node, nonce, error=None):
    node.fail("eth_sendRawTransaction", times=1, error=error,
              when=lambda params: _nonce_of(params[0]) == nonce)


def test_a_refused_step_leaves_nothing_armed_behind_its_nonce(chain_env):
    """REPRODUCTION (A1, the stranded tail).

    Mechanism: `act_sequence` assumes a node REFUSES every nonce behind a
    gap. This node QUEUES them. One refused broadcast (the replica
    readiness error) leaves every later signed step admitted but
    unmineable, invisible to `pending`, and they mine whenever a later
    UNRELATED call fills the gap nonce. 3.7.0 returns with the tail
    armed; the next call's transaction releases it.
    """
    node, game, clock, op = chain_env
    game.inv[11301] = 50
    base = node.pending_count(op)
    _refuse_nonce(node, base + 2, READINESS_ERROR)
    out = server.act_sequence(_feeds(6), account="testa")
    armed = node.queued(op)
    rows = [r["status"] for r in out["steps"]]

    # A later, unrelated call must not execute any step of the sequence.
    executed_before = len(node.executed)
    game.xp[server._kami_entity_id(5)] = 1_000
    server.level_up_kami(5, account="testa")
    released = node.executed[executed_before:]
    assert armed == [] and len(released) == 1, (
        f"nonces armed behind a gap after the call returned: {armed}; "
        f"rows: {rows}; the next unrelated call (a level-up at nonce "
        f"{released[0].nonce}) released {len(released) - 1} stale "
        f"sequence step(s) at nonces {[t.nonce for t in released[1:]]}")


def test_a_sequence_never_waits_the_long_budget_on_steps_that_cannot_mine(
    chain_env,
):
    """REPRODUCTION (A1, the receipt wait behind a gap).

    3.7.0 waits `120 + 10·N` s on ONE budget for steps queued behind the
    refused nonce, which cannot mine until something fills it.
    """
    node, game, clock, op = chain_env
    game.inv[11301] = 50
    base = node.pending_count(op)
    _refuse_nonce(node, base + 2, READINESS_ERROR)
    t0 = clock.now
    server.act_sequence(_feeds(6), account="testa")
    waited = clock.now - t0
    assert waited < 30, f"waited {waited:.0f}s on steps that cannot mine"


def test_a_nonce_consumed_by_another_hash_is_a_collision_not_unconfirmed(
    chain_env,
):
    """REPRODUCTION (A1, `UNCONFIRMED` is a bare receipt timeout).

    A stranded sequence tail is released by a later call; a second later
    call reads `pending` from a replica that is behind and signs at a
    nonce one of those released steps just consumed. 3.7.0 waits 120 s
    and raises UNCONFIRMED "may still be included", although the nonce
    was consumed by a hash this harness itself signed.
    """
    node, game, clock, op = chain_env
    game.inv[11301] = 50
    base = node.pending_count(op)
    _refuse_nonce(node, base + 2, READINESS_ERROR)
    seq = server.act_sequence(_feeds(6), account="testa")
    game.xp[server._kami_entity_id(5)] = 1_000
    server.level_up_kami(5, account="testa")        # fills base+2
    node.lag(op, times=2, behind=3)                 # sees base+3 as free
    step3 = seq["steps"][3].get("tx_hash")
    # The invariant, not the mechanism: the second call either lands
    # (4.0.0: the lane floor never hands out a nonce this harness saw
    # used, so the stale read cannot collide) or its error NAMES the hash
    # that consumed its nonce. It is never "may still be included".
    try:
        server.level_up_kami(5, account="testa")
    except Exception as e:
        text = str(e)
        assert "may still be included" not in text, text
        assert step3 and step3 in text, (
            f"the collision does not name the hash that consumed the "
            f"nonce ({step3}): {text}")


def _external_send(node, key, nonce):
    """A transaction on the same key from ANOTHER signer (a second
    process, a game client): it shares no lane state with this one."""
    from eth_account import Account
    acct = Account.from_key(key)
    signed = Account.sign_transaction({
        "to": acct.address, "value": 0, "gas": 260_000, "nonce": nonce,
        "chainId": server.CHAIN_ID, "maxFeePerGas": 2_500_000,
        "maxPriorityFeePerGas": 0,
    }, key)
    resp = node.rpc({"jsonrpc": "2.0", "id": 1,
                     "method": "eth_sendRawTransaction",
                     "params": ["0x" + bytes(signed.raw_transaction).hex()]})
    return resp["result"]


def test_a_nonce_taken_by_another_signer_is_named_and_ends_the_wait_early(
    chain_env,
):
    """A collision the lane CANNOT prevent: another signer on the same
    key takes the next nonce, and this harness's read of `pending` comes
    from a replica one transaction behind. The transaction it signs at
    the consumed nonce is admitted by that replica and dropped on
    gossip. 3.7.0 waits the full 120 s and says UNCONFIRMED "may still be
    included"; it is a collision, and the hash that consumed the nonce
    is on chain to be named."""
    from conftest import KEY_A
    node, game, clock, op = chain_env
    eid = server._kami_entity_id(5)
    game.xp[eid] = 1_000
    server.level_up_kami(5, account="testa")             # nonce 500
    external = _external_send(node, KEY_A, 501)          # another signer
    node.lag(op, times=2, behind=1)                      # stale replica
    t0 = clock.now
    with pytest.raises(Exception) as ei:
        server.level_up_kami(5, account="testa")
    waited = clock.now - t0
    text = str(ei.value)
    assert external in text, f"collision does not name {external}: {text}"
    assert "NOT signed by this harness" in text, text
    assert "may still be included" not in text, text
    assert waited < 30, f"waited {waited:.0f}s on a transaction that cannot mine"


# ---------------------------------------------------------------------------
# A1 — the replica readiness error aborts a loop
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method", [
    "eth_sendRawTransaction",
    "eth_getTransactionCount",
    "eth_getBalance",
    "eth_estimateGas",
])
def test_the_readiness_answer_does_not_abort_a_loop(chain_env, method):
    """REPRODUCTION (A1, the readiness class).

    `jsonrpc readiness error ... historical version not ready [code 5]`
    is a replica behind the head and clears on the next request. It is
    known only to the dry-run's replay list; anywhere else in a send it
    is terminal, because the retry routing keys on `-32000` and
    `account sequence mismatch` and this payload carries `code 5`. 3.7.0
    aborts the loop at the step it hits.
    """
    node, game, clock, op = chain_env
    game.inv[11301] = 10
    calls = {"n": 0}

    def second_send_only(params):
        calls["n"] += 1
        return calls["n"] == 2 if method != "eth_sendRawTransaction" else (
            _nonce_of(params[0]) == node.latest[op.lower()]
            and node.latest[op.lower()] == 501)

    node.fail(method, times=1, error=READINESS_ERROR, when=second_send_only)
    out = server.use_item_batch(21, 11301, 3, account="testa",
                                allow_partial=True)
    assert out.get("used") == 3, out
    assert game.inv[11301] == 7


def test_a_second_infrastructure_failure_in_the_dry_run_is_not_a_revert(
    chain_env,
):
    """REPRODUCTION (A4). The dry-run retries an infrastructure answer
    once; the SECOND is raised as `transaction dry-run reverted: ...` —
    an infrastructure failure reported as a game revert."""
    node, game, clock, op = chain_env
    # Enough refusals to outlast every retry layer (4.0.0 retries a read
    # three more times on a fresh session before the dry-run's own second
    # attempt), so the dry-run really does fail twice.
    node.fail("eth_call", times=8, error=READINESS_ERROR)
    game.xp[server._kami_entity_id(5)] = 1_000
    with pytest.raises(Exception) as ei:
        server.level_up_kami(5, account="testa")
    assert "reverted" not in str(ei.value), str(ei.value)


# ---------------------------------------------------------------------------
# A3 — a read blocked behind a write loop; a cancel that cannot stop it
# ---------------------------------------------------------------------------

class _Hold:
    """Holds the Nth eth_sendRawTransaction until released (wall time)."""

    def __init__(self, node, nth=1, watchdog_s=3.0):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.released_by_watchdog = False
        self.n = 0
        self.nth = nth
        self.watchdog_s = watchdog_s
        original = node.rpc

        def rpc(request):
            if request["method"] == "eth_sendRawTransaction":
                self.n += 1
                if self.n == self.nth:
                    self.entered.set()
                    if not self.release.wait(self.watchdog_s):
                        self.released_by_watchdog = True
            return original(request)

        node.rpc = rpc


@pytest.fixture()
def wall_env(monkeypatch, accounts):
    """The fake node on REAL time (the test measures wall latency)."""
    node = FakeNode(server.CHAIN_ID)
    game = Game(node)
    monkeypatch.setattr(server, "w3", getattr(
        server, "_install_read_retry", lambda w: w)(make_w3(node)))
    monkeypatch.setattr(server, "_resolve_system", addr_for)
    monkeypatch.setattr(server, "_resolve_component", addr_for)
    monkeypatch.setattr(server, "_require_registered_operator", lambda a: AID)
    monkeypatch.setattr(server, "_kami_owner_id", lambda k: AID)
    monkeypatch.setattr(server, "_kami_state", lambda k: "RESTING")
    monkeypatch.setattr(server, "_inventory_balance",
                        lambda holder, item: game.inv[item])
    game.inv[11301] = 10
    return node, game


def test_a_read_returns_while_a_write_loop_is_in_flight(wall_env):
    """REPRODUCTION (A3).

    FastMCP calls a sync tool body inline on the event loop, so a long
    write loop blocks every other request — a read cannot even be
    dispatched until the loop returns.
    """
    node, game = wall_env
    hold = _Hold(node, nth=1, watchdog_s=3.0)
    marks = {}

    async def main():
        async with create_connected_server_and_client_session(
            server.mcp._mcp_server
        ) as client:
            async with anyio.create_task_group() as tg:
                async def write():
                    await client.call_tool("use_item_batch", {
                        "kami_id": 21, "item_id": 11301, "count": 3,
                        "account": "testa"})
                    marks["write_done"] = time.monotonic()
                marks["t0"] = time.monotonic()
                tg.start_soon(write)
                while not hold.entered.is_set():
                    await anyio.sleep(0.01)
                marks["read_sent"] = time.monotonic()
                await client.call_tool("list_accounts", {})
                marks["read_done"] = time.monotonic()
                hold.release.set()

    anyio.run(main)
    assert not hold.released_by_watchdog, (
        f"the read could not be answered while the write was in flight: "
        f"the write had to be released by the {hold.watchdog_s:.0f}s "
        f"watchdog first; the read completed "
        f"{marks['read_done'] - marks['t0']:.2f}s after the write started")
    assert marks["read_done"] - marks["read_sent"] < 1.0


def test_a_cancel_stops_the_loop_at_the_next_step_boundary(wall_env):
    """REPRODUCTION (A3). A client cancel is a notification the server
    can only read on its event loop — which the sync loop is blocking —
    so 3.7.0 runs every remaining step after the cancel."""
    node, game = wall_env
    hold = _Hold(node, nth=1, watchdog_s=3.0)

    async def main():
        async with create_connected_server_and_client_session(
            server.mcp._mcp_server
        ) as client:
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
                await client.send_notification(mcp_types.ClientNotification(
                    mcp_types.CancelledNotification(
                        params=mcp_types.CancelledNotificationParams(
                            requestId=rid, reason="test cancel"))))
                await anyio.sleep(0.2)
                hold.release.set()
                # Give a cancelled loop time to (not) send its next step.
                await anyio.sleep(0.5)

    anyio.run(main)
    sent = sum(1 for m, _p in node.requests if m == "eth_sendRawTransaction")
    assert sent == 1, f"{sent} uses were sent after a cancel during use 1"
    assert game.inv[11301] == 9


# ---------------------------------------------------------------------------
# A4 — the half-revealed scavenge commit
# ---------------------------------------------------------------------------

@pytest.fixture()
def scav_env(chain_env, monkeypatch):
    node, game, clock, op = chain_env
    monkeypatch.setattr(server, "get_scavenge_points", lambda n, a: {
        "points": 10**9, "tier_cost": 100, "claimable_tiers": 120})
    return chain_env


def test_a_commit_above_the_per_reveal_cap_is_drained_to_zero(scav_env):
    """REPRODUCTION (A4).

    Upstream reveals at most 5,000 rolls per transaction
    (`LibDroptable.MAX_ROLLS_PER_REVEAL`, chunked reveal, upstream
    7b0c5a8b) and leaves the remainder on the commit's `component.value`
    under the same 256-block clock. 3.7.0 sends ONE reveal and returns
    `success`: 7,000 of 12,000 rolls are left on the commit and nothing
    in the result says so.
    """
    node, game, clock, op = scav_env
    out = server.scavenge_claim_and_reveal(53, account="testa")
    assert game.commits.get(Game.COMMIT_ID, 0) == 0, (
        f"{game.commits[Game.COMMIT_ID]} rolls left unrevealed on the "
        f"commit; result status reported: "
        f"{out.get('reveal', {}).get('status')}")
    got = sum(i["amount"] for i in out["revealed_items"])
    assert got == Game.CLAIM_ROLLS


def test_an_already_revealed_commit_is_flagged_not_an_empty_success(
    scav_env,
):
    """REPRODUCTION (A4). Upstream filters a drained commit to 0 and
    reveals nothing without reverting, so a commit revealed elsewhere
    between the claim and this call's reveal comes back as a successful
    reveal with `revealed_items: []` and no reason."""
    node, game, clock, op = scav_env

    def reveal_elsewhere(now):
        if Game.COMMIT_ID in game.commits:
            game.drain(Game.COMMIT_ID, game.commits[Game.COMMIT_ID])

    clock.on_sleep.append(reveal_elsewhere)
    out = server.scavenge_claim_and_reveal(53, account="testa")
    assert out["revealed_items"] == []
    flagged = {k: v for k, v in out.items()
               if k not in ("claim", "reveal", "commit_ids",
                            "revealed_items", "txs", "tx_hash")}
    assert flagged, f"empty revealed_items under success, unflagged: {out}"

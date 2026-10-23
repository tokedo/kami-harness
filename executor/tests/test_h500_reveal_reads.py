"""5.0.0 (C) — the scavenge-reveal loop reads at its own receipt.

`scavenge_claim_and_reveal` reveals until every commit is drained (a
reveal processes at most 5,000 rolls, upstream MAX_ROLLS_PER_REVEAL) and
decides whether to go on from a read of the remaining rolls. Through
4.7.0 that read was an eth_call at `latest`; a replica that had not
applied the reveal answered the count from BEFORE it, the loop took
"unchanged" for "no progress" and stopped after one reveal, reporting a
stale remainder — and the follow-up reveal then reported only the rolls
above 5,000. Right after the claim, the same replica answered 0 for a
commit it had not seen, and the call reported "revealed elsewhere" and
sent nothing.

R1  a lagging replica after the first reveal: 5.0.0 reveals to zero and
    sums both receipts; 4.7.0 stops after one with the pre-reveal count.
R2  every read names a block at or after the receipt that changed it.
R3  a lagging replica after the claim: 5.0.0 reveals; 4.7.0 reports the
    commits revealed elsewhere and sends nothing.
R4  a two-chunk reveal with no lag sums both receipts.
R5  a backend that refuses numbered blocks: the count is read at latest
    once the head has reached the receipt's block, and the result says so.
R6  a reveal that does not land: the notice names the commits left, the
    block the remainder was read at, and the expiry block.
R7  droptable_reveal reads its `rolls_remaining` at its own receipt.

Synthetic commits, rolls and blocks; the hermetic node (fakenode.py).
"""

from __future__ import annotations

from collections import defaultdict

import eth_abi
import pytest
import web3._utils.threads as web3_threads

import server
from conftest import KEY_A
from fakenode import FakeNode, Result, VirtualClock, addr_for, make_w3

AID = 0x4242
ROLLS = 7_250                     # two reveals: 5,000 + 2,250
CID = 2 ** 201 + 1234
KEYS = (1005, 11302)
TOPIC = "0x" + server._DROPTABLE_EVENT_TOPIC


def _uint(v: int) -> Result:
    return Result(output=eth_abi.encode(["uint256"], [v]))


class Drops:
    """The droptable commits, with their history per block."""

    def __init__(self, node: FakeNode):
        self.node = node
        self.now: dict[int, int] = {}
        self.history: list[tuple[int, dict]] = [(0, {})]
        self.reveals_landed = 0
        self.fail_reveal_after: int | None = None
        self.after_commit = []
        h = node.handle
        h(addr_for("system.scavenge.claim"), "executeTyped(uint256)",
          self._claim)
        h(addr_for("system.droptable.item.reveal"), "executeTyped(uint256[])",
          self._reveal)
        h(addr_for("component.value"), "safeGet(uint256)", self._value)

    def at(self, block):
        if block is None:
            return dict(self.now)
        return dict([s for b, s in self.history if b <= block][-1])

    def _record(self, label):
        self.history.append((self.node.block, dict(self.now)))
        for hook in list(self.after_commit):
            hook(label, self.node.block)

    def _value(self, node, caller, args, commit):
        eid = eth_abi.decode(["uint256"], args[:32])[0]
        return _uint(self.at(node.call_block).get(eid, 0))

    def _claim(self, node, caller, args, commit):
        if commit:
            self.now[CID] = ROLLS
            self._record("claim")
        data = eth_abi.encode(["uint256"] * 4, [7, 3, 1, CID])
        return Result(gas_used=900_000,
                      logs=[(addr_for("world"), [TOPIC], data)])

    def _reveal(self, node, caller, args, commit):
        (ids,) = eth_abi.decode(["uint256[]"], args)
        if (self.fail_reveal_after is not None
                and self.reveals_landed >= self.fail_reveal_after):
            return Result(status=0, revert="LibCommit: no seed")
        state = self.at(None if commit else node.call_block)
        budget, logs = 5_000, []
        for cid in ids:
            left = state.get(cid, 0)
            if not left or not budget:
                continue
            chunk = min(left, budget)
            budget -= chunk
            amounts = [chunk // 2, chunk - chunk // 2]
            state[cid] = left - chunk
            if state[cid] == 0:
                state.pop(cid)
            n = len(KEYS)
            logs.append((addr_for("world"), [TOPIC], eth_abi.encode(
                ["uint256"] * (2 * n + 4), [cid, 1, n, *KEYS, n, *amounts])))
        if commit:
            self.now = state
            self.reveals_landed += 1
            self._record("reveal")
        return Result(gas_used=200_000 + 1_130 * (5_000 - budget), logs=logs)


@pytest.fixture()
def scav(monkeypatch):
    node = FakeNode(server.CHAIN_ID)
    drops = Drops(node)
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
    monkeypatch.setattr(server, "_accounts",
                        {"main": server._Account("main", KEY_A, KEY_A)})
    monkeypatch.setattr(server, "_require_registered_operator", lambda a: AID)
    monkeypatch.setattr(server, "get_scavenge_points", lambda n, a: {
        "points": 10**9, "tier_cost": 100, "claimable_tiers": 99})
    return node, drops, clock


def _lag_after(drops, node, label, times=2, nth=1):
    seen = defaultdict(int)

    def arm(what, block):
        if what == label:
            seen[what] += 1
            if seen[what] == nth:
                node.state_lag(times=times, stuck_at=block - 1)
    drops.after_commit.append(arm)


def _total(out) -> int:
    return sum(i["amount"] for i in out["revealed_items"])


def _value_reads(node) -> list:
    to = addr_for("component.value").lower()
    return [p[1] if len(p) > 1 else "latest" for m, p in node.requests
            if m == "eth_call" and (p[0].get("to") or "").lower() == to]


# R1 ------------------------------------------------------------------------

def test_a_replica_behind_the_first_reveal_does_not_stop_the_loop(scav):
    node, drops, clock = scav
    _lag_after(drops, node, "reveal")
    out = server.scavenge_claim_and_reveal(53, account="main")
    assert out["reveals"] == 2, out.get("notice")
    assert out["rolls_remaining"] == {}
    assert drops.now == {}
    assert _total(out) == ROLLS


# R2 ------------------------------------------------------------------------

def test_every_count_is_read_at_or_after_the_receipt_that_changed_it(scav):
    node, drops, clock = scav
    landed = []
    drops.after_commit.append(lambda what, block: landed.append(block))
    server.scavenge_claim_and_reveal(53, account="main")
    reads = _value_reads(node)
    assert reads and "latest" not in reads, reads
    blocks = [int(b, 16) for b in reads]
    assert blocks[0] >= landed[0]                 # the claim's receipt
    assert blocks[-1] >= landed[-1]               # the last reveal's


# R3 ------------------------------------------------------------------------

def test_a_replica_behind_the_claim_does_not_read_as_revealed_elsewhere(scav):
    node, drops, clock = scav
    _lag_after(drops, node, "claim", times=3)
    out = server.scavenge_claim_and_reveal(53, account="main")
    assert "already_revealed" not in out
    assert out["reveals"] == 2
    assert _total(out) == ROLLS


# R4 ------------------------------------------------------------------------

def test_a_two_chunk_reveal_sums_both_receipts(scav):
    node, drops, clock = scav
    out = server.scavenge_claim_and_reveal(53, account="main")
    assert out["reveals"] == 2
    assert _total(out) == ROLLS
    assert len([t for t in out["txs"] if t["step"] == "reveal"]) == 2


# R5 ------------------------------------------------------------------------

def test_a_backend_that_refuses_numbered_blocks_reads_latest_and_says_so(
    scav,
):
    node, drops, clock = scav
    node.refuse_numbered = "missing trie node"
    out = server.scavenge_claim_and_reveal(53, account="main")
    assert out["rolls_remaining"] == {} and _total(out) == ROLLS
    assert "the node could not serve block" in out["notice"]
    assert "read at latest once its head reached block" in out["notice"]


# R6 ------------------------------------------------------------------------

def test_a_reveal_that_does_not_land_names_the_commits_the_read_and_expiry(
    scav,
):
    node, drops, clock = scav
    drops.fail_reveal_after = 1
    landed = {}
    drops.after_commit.append(lambda what, block: landed.setdefault(
        what, []).append(block))
    with pytest.raises(server.BatchTxError) as ei:
        server.scavenge_claim_and_reveal(53, account="main")
    msg = str(ei.value)
    claim_block = landed["claim"][0]
    assert f"({CID})" in msg
    assert "the remainder was read at block " in msg
    read_at = int(msg.split("the remainder was read at block ")[1]
                  .split(";")[0])
    assert read_at >= landed["reveal"][0]
    assert f"they expire at block {claim_block + 256}" in msg
    assert ei.value.outcomes["rolls_remaining"] == {str(CID): ROLLS - 5_000}


# R7 ------------------------------------------------------------------------

def test_droptable_reveal_reads_its_remainder_at_its_receipt(scav):
    node, drops, clock = scav
    claim = server.scavenge_claim(53, account="main")
    clock.sleep(2)
    _lag_after(drops, node, "reveal")
    out = server.droptable_reveal(claim["commit_ids"], account="main")
    assert out["rolls_remaining"] == {str(CID): ROLLS - 5_000}
    assert _value_reads(node)[-1] != "latest"

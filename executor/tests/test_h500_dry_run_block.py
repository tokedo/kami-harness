"""5.0.0 (D) — the dry-run reads no older state than the signer's own
last receipt.

A load-balanced backend can answer `latest` from a replica that has not
applied the block the signer's previous transaction landed in. A walk's
third hop was refused before signing — "unreachable room" — because the
dry-run ran in the room the account had just left; the same hop, sent
again later, landed. Since 5.0.0 a dry-run after a landed transaction of
the same signer reads at max(that receipt's block, the head it sees): a
replica that does not hold the block answers the readiness class (the
read layer retries it on a fresh session); a backend that will not serve
a numbered block at all (pruned, not an archive) is asked once at
`latest`, and a refusal from that read says so.

D1  B19's shape on synthetic rooms 101-104: hop 3 lands; at 4.7.0 it is
    refused from pre-receipt state.
D2  the dry-run's eth_call names a block >= the last receipt's block;
    before any receipt it names `latest`.
D3  a backend that refuses numbered blocks: the dry-run falls back to
    `latest` once; a refusal there names the block it could not serve.
D4  a time-based rule is judged at the head, not at the old receipt's
    block (the bound is max(receipt, head), never the receipt alone).
"""

from __future__ import annotations

import eth_abi
import pytest
import web3._utils.threads as web3_threads

import server
from conftest import KEY_A
from fakenode import FakeNode, Result, VirtualClock, addr_for, make_w3

AID = 0x4242
MOVE = "system.account.move"


@pytest.fixture()
def walk(monkeypatch):
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
    monkeypatch.setattr(server, "_accounts",
                        {"main": server._Account("main", KEY_A, KEY_A)})
    monkeypatch.setattr(server, "_require_registered_operator", lambda a: AID)
    history = [(0, 101)]          # (block it landed in, room)
    hooks = []
    rule = {"not_before": None}

    def room_at(block):
        return [r for b, r in history if b <= block][-1]

    monkeypatch.setattr(server, "_account_view", lambda aid: {
        "index": 1, "name": "walker", "stamina": 100,
        "room": history[-1][1]})

    def move(n, caller, args, commit):
        (target,) = eth_abi.decode(["uint32"], args)
        at = n.block if commit else n.call_block
        if rule["not_before"] is not None and at < rule["not_before"]:
            return Result(status=0, revert="AccMove: on cooldown")
        if abs(target - room_at(at)) != 1:
            return Result(status=0, revert="AccMove: unreachable room")
        if commit:
            history.append((n.block, target))
            for hook in list(hooks):
                hook(target)
        return Result(gas_used=1_000_000)

    node.handle(addr_for(MOVE), "executeTyped(uint32)", move)
    return node, clock, history, hooks, rule


def _move_calls(node) -> list:
    """The block argument of every eth_call to the move system, in order."""
    out = []
    to = addr_for(MOVE).lower()
    for method, params in node.requests:
        if method == "eth_call" and (params[0].get("to") or "").lower() == to:
            out.append(params[1] if len(params) > 1 else "latest")
    return out


def _arm_after_hop_2(node, history, hooks, **lag):
    def arm(target):
        if target == 103:
            hop2_block = history[-1][0]
            node.state_lag(stuck_at=hop2_block - 1, **lag)
    hooks.append(arm)


# D1 ------------------------------------------------------------------------

def test_a_lagging_replica_does_not_refuse_the_third_hop(walk):
    node, clock, history, hooks, rule = walk
    _arm_after_hop_2(node, history, hooks, times=2)
    for room in (102, 103, 104):
        out = server.move_to_room(room, account="main")
        assert out["status"] == "success", out
    assert [r for _b, r in history] == [101, 102, 103, 104]


# D2 ------------------------------------------------------------------------

def test_the_dry_run_names_a_block_no_older_than_the_last_receipt(walk):
    node, clock, history, hooks, rule = walk
    server.move_to_room(102, account="main")
    first = _move_calls(node)
    assert first and first[0] == "latest"      # nothing had landed yet
    hop1_block = history[-1][0]
    mark = len(_move_calls(node))
    server.move_to_room(103, account="main")
    later = _move_calls(node)[mark:]
    assert later, "hop 2 ran no dry-run"
    for blk in later:
        assert blk != "latest" and int(blk, 16) >= hop1_block, later


# D3 ------------------------------------------------------------------------

def test_a_backend_that_refuses_numbered_blocks_falls_back_and_says_so(walk):
    node, clock, history, hooks, rule = walk
    node.refuse_numbered = "missing trie node"
    _arm_after_hop_2(node, history, hooks, times=2)
    server.move_to_room(102, account="main")
    server.move_to_room(103, account="main")
    hop2_block = history[-1][0]
    with pytest.raises(server.PreTxValidationError) as ei:
        server.move_to_room(104, account="main")
    msg = str(ei.value)
    assert "unreachable room" in msg
    assert (f"the dry-run ran at latest because the node could not serve "
            f"block {hop2_block}") in msg
    assert "missing trie node" in msg
    assert [r for _b, r in history] == [101, 102, 103]


def test_a_fallback_read_that_passes_sends(walk):
    node, clock, history, hooks, rule = walk
    node.refuse_numbered = "missing trie node"
    for room in (102, 103, 104):
        assert server.move_to_room(room, account="main")["status"] == "success"


def test_the_pruning_answers_are_a_named_list():
    for marker in ("missing trie node", "header not found",
                   "historical version not found"):
        assert marker in server._HISTORICAL_STATE_MARKERS
        assert marker in server._REPLAY_INFRA_MARKERS
    # a replica that is merely behind is the readiness class, not this one
    assert "historical version not ready" not in (
        server._HISTORICAL_STATE_MARKERS)


# D4 ------------------------------------------------------------------------

def test_a_time_based_rule_is_judged_at_the_head(walk):
    """Hop 1 lands; a rule that opens 30 blocks later (a cooldown) is
    open when hop 2 is sent 60 blocks later. A dry-run pinned to hop 1's
    block would refuse it."""
    node, clock, history, hooks, rule = walk
    server.move_to_room(102, account="main")
    hop1_block = history[-1][0]
    rule["not_before"] = hop1_block + 30
    clock.sleep(60)
    assert server.move_to_room(103, account="main")["status"] == "success"

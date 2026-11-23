"""The harvest-start calls the tools send, pinned byte for byte (5.1.1).

Upstream 1b0b34e5 added two entry points to system.harvest.start that
skip a kami unable to start instead of reverting:
`executeAllowFailure(bytes)` (0xf00c4431) and
`executeBatchedAllowFailure(uint256[],uint32,uint256,uint256)`
(0x49814834). `execute`, `executeTyped` and `executeBatched` are
unchanged. This release vendors the new ABI and calls neither: what
harvest_start and act_sequence's harvest_start step send must be what
5.1.0 sent.

The vendored ABI now carries the new selectors, so the fake node's
"no such function upstream" bare revert no longer stops a tool pointed
at one of them: these tests pin the bytes themselves. Every call to the
system is captured on the wire (the dry-run eth_call, the gas estimate,
the signed transaction) and compared with calldata recorded at 5.1.0
(4b66238) for the same input.
"""

from __future__ import annotations

import json
from pathlib import Path

import eth_abi
import pytest
from eth_account.typed_transactions import TypedTransaction
from eth_utils import keccak
from hexbytes import HexBytes

import server
from fakenode import Result, addr_for
from test_h400_send_path import chain_env  # noqa: F401

SYSTEM = "system.harvest.start"
TO = addr_for(SYSTEM).lower()
FIXTURES = Path(__file__).parent / "fixtures" / "upstream_abi"

EXECUTE = "execute(bytes)"
EXECUTE_TYPED = "executeTyped(uint256,uint32,uint256,uint256)"
EXECUTE_BATCHED = "executeBatched(uint256[],uint32,uint256,uint256)"
ALLOW_FAILURE = "executeAllowFailure(bytes)"
BATCHED_ALLOW_FAILURE = "executeBatchedAllowFailure(uint256[],uint32,uint256,uint256)"
OLD = {"0x09c5eabe": EXECUTE, "0xc8372a87": EXECUTE_TYPED,
       "0x68f37c94": EXECUTE_BATCHED}
NEW = {"0xf00c4431": ALLOW_FAILURE, "0x49814834": BATCHED_ALLOW_FAILURE}

NODE = 9
# Kami indices no mint reaches (uint32, above every minted index): the
# entity ids below are no player's kami.
ONE = [4_000_000_001]
TWO = [4_000_000_001, 4_000_000_002]

# The calldata 5.1.0 (4b66238) sent for these inputs, recorded off this
# file's capture run on that commit. kami entity id = the server's
# _kami_entity_id of the index.
SINGLE = (
    "0xc8372a87"
    "3b1f09351dc1ead27592ac36046939716a7d7c1666917cb144d148d5ea49345b"
    "0000000000000000000000000000000000000000000000000000000000000009"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000"
)
BATCH = (
    "0x68f37c94"
    "0000000000000000000000000000000000000000000000000000000000000080"
    "0000000000000000000000000000000000000000000000000000000000000009"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000002"
    "3b1f09351dc1ead27592ac36046939716a7d7c1666917cb144d148d5ea49345b"
    "a1dfb6759ab55a0327d4612be461c6dd507e7d2d1025e897429703820c7133e0"
)


def _sel(sig: str) -> str:
    return "0x" + keccak(text=sig)[:4].hex()


@pytest.fixture()
def wire(chain_env, monkeypatch):  # noqa: F811
    """The fake node with the two functions 5.1.0 sends; every request
    that carries calldata for the system is recorded as (method, hex)."""
    node, game, clock, op = chain_env
    for sig in (EXECUTE_TYPED, EXECUTE_BATCHED):
        node.handle(addr_for(SYSTEM), sig,
                    lambda n, c, a, commit: Result(gas_used=1_200_000))
    monkeypatch.setattr(server, "_require_kamis_owned", lambda *a: None)
    seen: list[tuple[str, str]] = []
    real = node.rpc

    def rpc(request):
        method, params = request.get("method"), request.get("params") or []
        if method in ("eth_call", "eth_estimateGas") and params:
            call = params[0]
            if (call.get("to") or "").lower() == TO:
                seen.append((method, call.get("data") or call.get("input")))
        elif method == "eth_sendRawTransaction":
            tx = TypedTransaction.from_bytes(HexBytes(params[0])).as_dict()
            if tx.get("to") and "0x" + bytes(tx["to"]).hex() == TO:
                seen.append((method, "0x" + bytes(tx["data"]).hex()))
        return real(request)
    monkeypatch.setattr(node, "rpc", rpc)
    return node, seen


def _sent(seen):
    return [d for m, d in seen if m == "eth_sendRawTransaction"]


def test_the_recorded_calldata_is_the_abi_encoding_of_the_input():
    """The two literals are what the ABI encodes for the input (so the
    record is of the right thing, not only of what was sent)."""
    eids = [server._kami_entity_id(k) for k in TWO]
    single = _sel(EXECUTE_TYPED) + eth_abi.encode(
        ["uint256", "uint32", "uint256", "uint256"], [eids[0], NODE, 0, 0]).hex()
    batch = _sel(EXECUTE_BATCHED) + eth_abi.encode(
        ["uint256[]", "uint32", "uint256", "uint256"], [eids, NODE, 0, 0]).hex()
    assert single == SINGLE
    assert batch == BATCH


@pytest.mark.parametrize("kamis, want", [(ONE, SINGLE), (TWO, BATCH)])
def test_harvest_start_sends_the_5_1_0_calldata(wire, kamis, want):
    node, seen = wire
    out = server.harvest_start(kamis, NODE, account="testa")
    assert out.get("tx_hash"), out
    assert _sent(seen) == [want], seen
    # The dry-run eth_call asks about the same bytes it then signs.
    assert {d for _, d in seen} == {want}, seen


@pytest.mark.parametrize("kamis, want", [(ONE, SINGLE), (TWO, BATCH)])
def test_harvest_start_dry_run_asks_about_the_5_1_0_calldata(wire, kamis, want):
    node, seen = wire
    out = server.harvest_start(kamis, NODE, account="testa", dry_run=True)
    assert out.get("dry_run") is True, out
    assert seen and {d for _, d in seen} == {want}, seen
    assert _sent(seen) == [], seen


@pytest.mark.parametrize("kamis, want", [(ONE, SINGLE), (TWO, BATCH)])
def test_act_sequence_start_step_sends_the_5_1_0_calldata(wire, kamis, want):
    node, seen = wire
    out = server.act_sequence(
        [{"op": "harvest_start", "kami_ids": kamis, "node_index": NODE}],
        account="testa")
    (step,) = out["steps"]
    assert step.get("tx_hash"), out
    assert _sent(seen) == [want], seen


def test_every_call_to_the_system_uses_an_old_entry_point(wire):
    """Over both tools, both paths and both sizes: every selector sent or
    asked about is one of the three 5.1.0 entry points, never a new one."""
    node, seen = wire
    for kamis in (ONE, TWO):
        server.harvest_start(kamis, NODE, account="testa", dry_run=True)
        server.harvest_start(kamis, NODE, account="testa")
        server.act_sequence(
            [{"op": "harvest_start", "kami_ids": kamis, "node_index": NODE}],
            account="testa")
    selectors = {d[:10] for _, d in seen}
    assert len(_sent(seen)) == 4, seen
    assert selectors <= set(OLD), selectors
    assert not selectors & set(NEW), selectors


def test_the_server_declares_only_the_two_functions_it_sends():
    names = sorted(f["name"] for f in server._ABI_HARVEST_START)
    assert names == ["executeBatched", "executeTyped"], names


def test_the_vendored_abi_has_the_new_entry_points():
    """The upstream ABI of the system at the vendored pin: the three
    entry points 5.1.0 knew and the two allow-failure ones."""
    doc = json.loads((FIXTURES / "upstream_abi.json").read_text())
    fns = doc["abis"][doc["systems"][SYSTEM]["abi"]]
    want = {**OLD, **NEW}
    got = {v[0]: sig for sig, v in fns.items() if sig in want.values()}
    assert got == want, got
    for sig in (EXECUTE, ALLOW_FAILURE, EXECUTE_TYPED):
        assert fns[sig][1:] == [["bytes"], "nonpayable"], (sig, fns[sig])
    for sig in (EXECUTE_BATCHED, BATCHED_ALLOW_FAILURE):
        assert fns[sig][1:] == [["bytes[]"], "nonpayable"], (sig, fns[sig])


def test_the_selector_table_lists_no_new_entry_point():
    """The committed table of what the tools send names the system's two
    5.1.0 functions, for harvest_start and act_sequence, and nothing else."""
    table = json.loads((FIXTURES / "selector_table.json").read_text())
    rows = sorted((w["tool"], w["signature"], w["selector"])
                  for w in table["writes"] if w["target"] == SYSTEM)
    assert rows == sorted(
        (tool, sig, _sel(sig)) for tool in ("act_sequence", "harvest_start")
        for sig in (EXECUTE_BATCHED, EXECUTE_TYPED)), rows

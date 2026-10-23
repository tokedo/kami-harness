"""5.0.0 (E) — a kill's spoils are never negative.

`spoils` is a difference of two reads of the killer's harvest bounty:
after the kill (from its own receipt) minus before it (a pre-send read,
or in a sequence the previous kill's after-value carried forward). A
kill only ADDS to that bounty, so when "after" is the smaller one,
something drained the bounty between the reads — the killer's own
harvest stop or collect — and the difference means nothing. Through
4.7.0 it was served anyway: a sequence that stopped and restarted the
killer between two kills reported a large negative `spoils`.

S1  the decode: after < before is `spoils: null` with a decode_error;
    after >= before is the difference, as before.
S2  a sequence that lands a harvest_stop of the killer between two kills
    states the later kill's spoils as null, naming the stop's step; two
    kills in a row still carry the difference.
S3  the liquidate description says the stop's payout is the take.

Synthetic receipts and kamis only.
"""

from __future__ import annotations

import eth_abi
import pytest

import server
from fakenode import Result, addr_for
from test_h400_send_path import chain_env  # noqa: F401
from test_h450_failed_waits import (
    GROSS, KILLER, SPOILS, Kills, _liq, _value_write,
)

FELL = ("the killer's bounty fell between the reads (a stop, collect or "
        "kill by the killer landed in between), so spoils cannot be a "
        "difference")


def _receipt(victim: int, after: int):
    logs = []
    for i, (address, topics, data) in enumerate([
        _value_write(server._harvest_entity_id(victim), GROSS[victim]),
        _value_write(server._harvest_entity_id(victim), 0),
        _value_write(server._harvest_entity_id(KILLER), after),
    ]):
        logs.append({
            "address": address, "topics": topics, "data": "0x" + data.hex(),
            "blockNumber": "0x3e8", "blockHash": "0x" + "11" * 32,
            "transactionHash": "0x" + "22" * 32, "transactionIndex": "0x0",
            "logIndex": hex(i), "removed": False,
        })
    return server._format_receipt({
        "transactionHash": "0x" + "22" * 32, "blockNumber": "0x3e8",
        "blockHash": "0x" + "11" * 32, "transactionIndex": "0x0",
        "from": "0x" + "33" * 20, "to": addr_for("system.harvest.liquidate"),
        "status": "0x1", "gasUsed": "0x10", "cumulativeGasUsed": "0x10",
        "effectiveGasPrice": "0x1", "contractAddress": None, "logs": logs,
        "logsBloom": "0x" + "00" * 256, "type": "0x2",
    })


# S1 ------------------------------------------------------------------------

def test_a_bounty_that_fell_between_the_reads_has_no_spoils_number():
    out = server._decode_kill(_receipt(42, after=480), 42, KILLER,
                              killer_bounty_before=5_900)
    assert out["spoils"] is None
    assert FELL in out["decode_error"]
    assert out["victim_gross"] == GROSS[42]
    assert out["killer_bounty_after"] == 480


def test_a_bounty_that_grew_is_the_difference():
    out = server._decode_kill(_receipt(42, after=1_350), 42, KILLER,
                              killer_bounty_before=700)
    assert out["spoils"] == 650
    assert "decode_error" not in out or FELL not in out["decode_error"]


# S2 ------------------------------------------------------------------------

@pytest.fixture()
def kills(chain_env, monkeypatch):  # noqa: F811
    node, game, clock, op = chain_env
    k = Kills(node)
    killer_harvest = server._harvest_entity_id(KILLER)

    def stop(n, caller, args, commit):
        (harvest_id,) = eth_abi.decode(["uint256"], args)
        if commit and harvest_id == killer_harvest:
            k.bounty[killer_harvest] = 0           # the stop drains it
        return Result(gas_used=900_000)

    node.handle(addr_for("system.harvest.stop"), "executeTyped(uint256)",
                stop)
    return node, k


def test_a_stop_of_the_killer_between_two_kills_leaves_no_spoils_number(
    kills,
):
    node, k = kills
    out = server.act_sequence([
        _liq(41),
        {"op": "harvest_stop", "kami_ids": [KILLER]},
        {"op": "harvest_start", "kami_ids": [KILLER], "node_index": 9},
        _liq(42),
    ], account="testa")
    first, stop, start, second = out["steps"]
    assert [r["status"] for r in out["steps"]] == ["success"] * 4, out
    assert first["spoils"] == SPOILS[41]
    assert second["spoils"] is None, second
    assert "step 1, a harvest_stop of this killer" in second["decode_error"]
    assert second["victim_gross"] == GROSS[42]


def test_two_kills_in_a_row_still_carry_the_difference(kills):
    node, k = kills
    out = server.act_sequence([_liq(41), _liq(42)], account="testa")
    assert [r["spoils"] for r in out["steps"]] == [SPOILS[41], SPOILS[42]]


# S3 ------------------------------------------------------------------------

def test_the_description_names_the_stop_payout_as_the_take():
    d = {t.name: t for t in server.mcp._tool_manager.list_tools()}[
        "liquidate_kami"].description
    flat = " ".join(d.split())
    assert "the harvest_stop payout, not summed spoils, is the take" in flat

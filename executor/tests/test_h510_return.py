"""5.1.0 — the chain's return: a refusal the game now makes, and history
the endpoint no longer serves.

R1  skill_respec refuses a kami that is not RESTING before signing: the
    respec system reverts on any other state since the upstream change
    that made respec kami-only and RESTING-only.
F1  The order book's trade-ID scan never reads an EMPTY log answer below
    the endpoint's floor as "no trades": when the first block it needs
    answers null while the head is served, it fails closed with the
    re-run-the-bootstrap error.
F2  A ledger entry whose nonce is used, whose hash two lookups cannot
    find, and which may have mined below the endpoint's floor is not
    reported as "NOT executed": the notice says the endpoint no longer
    serves that height.

All values are synthetic.
"""

import json

import pytest
from web3.exceptions import BlockNotFound

import lanes
import server
from test_h400_lane import _sign_feed
from test_h400_send_path import chain_env  # noqa: F401  (fixture)


# R1 ------------------------------------------------------------------------

@pytest.mark.parametrize("state", ["HARVESTING", "DEAD", "LISTED"])
def test_respec_refuses_a_kami_that_is_not_resting(
        accounts, validation_ok, sent, monkeypatch, state):
    monkeypatch.setattr(server, "_kami_state", lambda k: state)
    with pytest.raises(server.PreTxValidationError) as ei:
        server.skill_respec(45, account="testa")
    assert f"kami #45 is {state}; skill_respec requires RESTING" in str(
        ei.value)
    assert sent == []


def test_respec_of_a_resting_kami_is_sent(accounts, validation_ok, sent):
    r = server.skill_respec(45, account="testa")
    assert r["status"] == "success" and len(sent) == 1


def test_the_respec_gate_is_in_the_state_table():
    assert server._TOOL_KAMI_STATES["skill_respec"] == ("RESTING",)
    assert "skill_respec" in server._STATE_TOOLS["RESTING"]


# F1 ------------------------------------------------------------------------

FLOOR = 40_000
HEAD = 60_000


def _seed(monkeypatch, tmp_path, block):
    monkeypatch.setattr(
        server, "_KWOB_CACHE_FILE", tmp_path / ".cache" / "kwob_trades.json")
    monkeypatch.setattr(
        server, "_trade_scan_cache",
        {"next_block": 0, "ids": set(), "loaded": False})
    server._KWOB_CACHE_FILE.parent.mkdir(parents=True)
    server._KWOB_CACHE_FILE.write_text(
        json.dumps({"block": block, "trade_ids": [hex(7)]}))


def _floored_endpoint(scanned):
    """Blocks below FLOOR answer null; logs below it come back empty."""
    def get_block(n, full=False):
        n = HEAD if n == "latest" else n
        if n < FLOOR:
            raise BlockNotFound(f"Block with id: '{n}' not found.")
        return {"number": n}

    def get_logs(params):
        scanned.append((params["fromBlock"], params["toBlock"]))
        return []
    server.w3.eth.get_block = get_block
    server.w3.eth.get_logs = get_logs
    server.w3.eth.block_number = HEAD


def test_a_scan_that_must_start_below_the_floor_fails_closed(
        chain, monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path, block=FLOOR - 5_000)
    scanned = []
    _floored_endpoint(scanned)
    with pytest.raises(RuntimeError) as ei:
        server._scan_trade_entity_ids()
    msg = str(ei.value)
    assert "stale" in msg and "kwob_bootstrap.py" in msg
    assert f"block {FLOOR - 5_000 + 1}" in msg
    assert scanned == []                      # no empty range was read
    # Nothing was persisted as current.
    persisted = json.loads(server._KWOB_CACHE_FILE.read_text())
    assert persisted["block"] == FLOOR - 5_000


def test_a_scan_above_the_floor_reads_on(chain, monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path, block=FLOOR + 5_000)
    scanned = []
    _floored_endpoint(scanned)
    assert server._scan_trade_entity_ids() == {7}
    assert scanned and scanned[0][0] == FLOOR + 5_000 - 1_000
    assert json.loads(server._KWOB_CACHE_FILE.read_text())["block"] == HEAD


def test_the_overlap_below_the_snapshot_is_not_the_gap(
        chain, monkeypatch, tmp_path):
    """The scan re-reads 1,000 blocks below the snapshot as overlap; only
    the first block AFTER the snapshot must be served."""
    _seed(monkeypatch, tmp_path, block=FLOOR + 10)
    _floored_endpoint([])
    assert server._scan_trade_entity_ids() == {7}


def test_a_head_that_answers_null_too_is_not_called_a_floor(
        chain, monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path, block=FLOOR - 5_000)

    def nothing(n, full=False):
        raise BlockNotFound("not found")
    server.w3.eth.get_block = nothing
    server.w3.eth.block_number = HEAD
    with pytest.raises(RuntimeError) as ei:
        server._scan_trade_entity_ids()
    assert "Retry shortly" in str(ei.value)
    assert "kwob_bootstrap" not in str(ei.value)


# F2 ------------------------------------------------------------------------

def _earlier_process_entry(node, op, nonce):
    """Another process signed, broadcast and saw mine a feed at `nonce`."""
    lane = lanes.Lane(server.CHAIN_ID, server.Web3.to_checksum_address(op),
                      lanes.default_dir())
    raw = _sign_feed(nonce)
    h = node.rpc({"jsonrpc": "2.0", "id": 1, "method": "eth_sendRawTransaction",
                  "params": ["0x" + raw.hex()]})["result"]
    e = lane.add(nonce, h, raw, "act_sequence#0123456789ab", "act_sequence", 1)
    lane.offered(e)
    lane.save()
    return h, e.signed_at, node.txs[h.lower()].mined_block


def test_an_entry_that_mined_below_the_floor_is_not_called_not_executed(
        chain_env, monkeypatch):  # noqa: F811
    node, game, clock, op = chain_env
    game.xp[server._kami_entity_id(5)] = 1_000
    h, signed_at, mined = _earlier_process_entry(node, op, 500)
    # The chain ran on; the endpoint now serves nothing at or below the
    # block the entry mined in. Its first served block came an hour after
    # the signing.
    node.block = mined + 5_000
    node.floor = mined + 1_000
    node.block_times[node.floor] = int(signed_at) + 3_600
    monkeypatch.setattr(server, "_LANES", {})
    out = server.run_tool("level_up_kami", kami_id=5, account="testa")
    note = out["notice"]
    assert h in note and "NOT executed" not in note, note
    assert f"no longer serves blocks before {node.floor}" in note, note
    assert "nonce 500 is used" in note, note
    assert out["status"] == "success"


def test_an_entry_signed_after_the_floor_keeps_the_proven_verdict(
        chain_env, monkeypatch):  # noqa: F811
    """Signed after the floor block's time: its block is served, so two
    null lookups and a used nonce are proof — NOT executed, as before."""
    node, game, clock, op = chain_env
    game.xp[server._kami_entity_id(5)] = 1_000
    lane = lanes.Lane(server.CHAIN_ID, server.Web3.to_checksum_address(op),
                      lanes.default_dir())
    raw = _sign_feed(500)
    h = "0x" + server.Web3.keccak(raw).hex().removeprefix("0x")
    e = lane.add(500, h, raw, "act_sequence#0123456789ab", "act_sequence", 1)
    lane.offered(e)
    lane.save()
    node.set_nonce(op, 501)                  # 500 used by another hash
    node.block += 5_000
    node.floor = node.block - 4_000
    node.block_times[node.floor] = int(e.signed_at) - 3_600
    monkeypatch.setattr(server, "_LANES", {})
    out = server.run_tool("level_up_kami", kami_id=5, account="testa")
    assert "NOT executed" in out["notice"], out["notice"]
    assert "no longer serves" not in out["notice"]


def test_the_floor_is_measured_by_height_not_by_the_earliest_tag(chain_env):  # noqa: F811
    node, game, clock, op = chain_env
    node.block = 9_000
    node.floor = 6_543
    node.block_times[6_543] = 1_234_567
    assert server._endpoint_floor() == {"block": 6_543, "timestamp": 1_234_567}
    asked = [p for m, p in node.requests if m == "eth_getBlockByNumber"]
    assert all(p[0] != "earliest" for p in asked)

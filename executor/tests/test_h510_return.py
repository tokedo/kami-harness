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


# The item and room catalogs at a99b4b64 ------------------------------------

def test_items_added_upstream_have_names():
    assert server._get_item_name(21007) == "Silt-Caked Box"
    assert server._get_item_name(100012) == "Igors Amulet"
    assert server._get_item_name(13) == "Ballot"
    # Names of items the previous file had keep their ASCII form.
    assert server._get_item_name(11002) == (
        "Melkarth's Heroic Awakening Spell Card")
    assert server._get_item_name(100006) == "KW Maps Data Chip"


# The order-book probe asks twice; the covered position advances ----------

def test_one_null_for_the_start_is_not_a_floor(chain, monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path, block=FLOOR + 5_000)
    asked, scanned = [], []

    def get_block(n, full=False):
        asked.append(n)
        if n == FLOOR + 5_001 and asked.count(n) == 1:
            raise BlockNotFound("not found")          # one null, then served
        return {"number": n}
    server.w3.eth.get_block = get_block
    server.w3.eth.get_logs = lambda p: (scanned.append(p["fromBlock"]), [])[1]
    server.w3.eth.block_number = HEAD
    assert server._scan_trade_entity_ids() == {7}
    assert scanned and asked.count(FLOOR + 5_001) == 2


def test_the_second_scan_needs_the_block_after_the_first_scan(
        chain, monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path, block=FLOOR + 5_000)
    floor = [FLOOR]

    def get_block(n, full=False):
        if n < floor[0]:
            raise BlockNotFound("not found")
        return {"number": n}
    server.w3.eth.get_block = get_block
    server.w3.eth.get_logs = lambda p: []
    server.w3.eth.block_number = HEAD
    assert server._scan_trade_entity_ids() == {7}
    floor[0] = FLOOR + 10_000                 # above the snapshot, below HEAD
    server.w3.eth.block_number = HEAD + 5_000
    assert server._scan_trade_entity_ids() == {7}
    assert json.loads(server._KWOB_CACHE_FILE.read_text())["block"] == HEAD + 5_000


# The lane: release, a known consumer, the skew, the cache ------------------

def _floored_after(node, signed_at, mined, offset_s):
    """The endpoint serves nothing at or below `mined`; its first served
    block's time is `offset_s` after the signing."""
    node.block, node.floor = mined + 5_000, mined + 1_000
    node.block_times[node.floor] = int(signed_at) + offset_s


def test_a_below_floor_entry_is_released(chain_env, monkeypatch):  # noqa: F811
    node, game, clock, op = chain_env
    game.xp[server._kami_entity_id(5)] = 1_000
    h, signed_at, mined = _earlier_process_entry(node, op, 500)
    _floored_after(node, signed_at, mined, 3_600)
    monkeypatch.setattr(server, "_LANES", {})
    out = server.run_tool("level_up_kami", kami_id=5, account="testa")
    assert "no longer serves blocks before" in out["notice"]
    assert all(e.hash != h for e in server._lane(op).active())


def test_a_known_consumer_keeps_the_proven_verdict(chain_env, monkeypatch):  # noqa: F811
    node, game, clock, op = chain_env
    game.xp[server._kami_entity_id(5)] = 1_000
    lane = lanes.Lane(server.CHAIN_ID, server.Web3.to_checksum_address(op),
                      lanes.default_dir())
    raw1 = _sign_feed(500)                    # never reached the node
    h1 = "0x" + server.Web3.keccak(raw1).hex().removeprefix("0x")
    e = lane.add(500, h1, raw1, "act_sequence#0123456789ab", "act_sequence", 1)
    lane.offered(e)
    lane.save()
    raw2 = _sign_feed(500, kami=22)           # another hash took nonce 500
    h2 = node.rpc({"jsonrpc": "2.0", "id": 1, "method": "eth_sendRawTransaction",
                   "params": ["0x" + raw2.hex()]})["result"]
    mined2 = node.txs[h2.lower()].mined_block
    node.block, node.floor = mined2 + 10, mined2 - 1   # h2's block is served
    node.block_times[node.floor] = int(e.signed_at) + 3_600
    monkeypatch.setattr(server, "_LANES", {})
    note = server.run_tool("level_up_kami", kami_id=5, account="testa")["notice"]
    assert "NOT executed" in note and h2 in note
    assert "no longer serves" not in note


@pytest.mark.parametrize("offset_s,below", [
    (-3_600, True), (100, True), (299, True), (301, False), (400, False)])
def test_the_skew_is_five_minutes(chain_env, monkeypatch, offset_s, below):  # noqa: F811
    """An entry signed up to 300 s after the floor block's time may have
    mined below it; one signed later mined in a served block. (The floor
    block's time minus the signing time is -offset_s.)"""
    node, game, clock, op = chain_env
    game.xp[server._kami_entity_id(5)] = 1_000
    h, signed_at, mined = _earlier_process_entry(node, op, 500)
    _floored_after(node, signed_at, mined, -offset_s)
    monkeypatch.setattr(server, "_LANES", {})
    note = server.run_tool("level_up_kami", kami_id=5, account="testa")["notice"]
    assert ("no longer serves blocks before" in note) is below, note
    assert ("NOT executed" in note) is (not below), note


def _block_reads(node):
    return sum(1 for m, p in node.requests if m == "eth_getBlockByNumber")


def test_the_floor_is_kept_ten_minutes_then_measured_again(chain_env):  # noqa: F811
    node, game, clock, op = chain_env
    node.block, node.floor = 9_000, 6_543
    assert server._endpoint_floor()["block"] == 6_543
    before = _block_reads(node)
    node.floor = 7_000                        # the floor rises
    clock.now += 599
    assert server._endpoint_floor()["block"] == 6_543   # kept
    assert _block_reads(node) == before                  # nothing asked
    clock.now += 2
    assert server._endpoint_floor()["block"] == 7_000   # measured again
    assert _block_reads(node) > before
    assert server._FLOOR_TTL_S == 600


# An unreadable floor fails closed ------------------------------------------

def test_one_null_for_the_head_is_not_an_unreadable_floor(chain_env, monkeypatch):  # noqa: F811
    node, game, clock, op = chain_env
    game.xp[server._kami_entity_id(5)] = 1_000
    h, signed_at, mined = _earlier_process_entry(node, op, 500)
    _floored_after(node, signed_at, mined, 3_600)
    node.null_blocks[node.block] = 1          # the head answers null once
    monkeypatch.setattr(server, "_LANES", {})
    note = server.run_tool("level_up_kami", kami_id=5, account="testa")["notice"]
    assert "NOT executed" not in note, note
    assert f"no longer serves blocks before {node.floor}" in note, note


def test_one_null_mid_search_does_not_raise_the_floor(chain_env):  # noqa: F811
    node, game, clock, op = chain_env
    node.block, node.floor = 9_000, 3_000
    node.null_blocks[4_500] = 1               # a served block, one null
    assert server._endpoint_floor()["block"] == 3_000


def test_an_unreadable_floor_is_never_not_executed(chain_env, monkeypatch):  # noqa: F811
    node, game, clock, op = chain_env
    game.xp[server._kami_entity_id(5)] = 1_000
    h, signed_at, mined = _earlier_process_entry(node, op, 500)
    _floored_after(node, signed_at, mined, 3_600)
    node.null_blocks[node.block] = 99         # the head never answers
    monkeypatch.setattr(server, "_LANES", {})
    out = server.run_tool("level_up_kami", kami_id=5, account="testa")
    note = out["notice"]
    assert "NOT executed" not in note, note
    assert "could not be determined on this endpoint" in note, note
    assert h in note
    # Kept, not released as if proven: the next call checks it again.
    assert any(e.hash == h for e in server._lane(op).active())
    assert out["status"] == "success"

# The floor's asks: fresh repeats, the counts, a failed read, the next call --

def _spy(monkeypatch):
    real, asked = server._rpc, []

    def rpc(method, params, fresh=False):
        if method == "eth_getBlockByNumber":
            asked.append((params[0], fresh))
        return real(method, params, fresh)
    monkeypatch.setattr(server, "_rpc", rpc)
    return asked


def test_a_repeated_ask_is_on_a_fresh_session(chain_env, monkeypatch):  # noqa: F811
    """The first ask of a height rides the shared session; every repeat
    (after a null) is made on a fresh one."""
    node, game, clock, op = chain_env
    node.block, node.floor = 9_000, 3_000
    node.null_blocks[4_500] = 1               # a served block, one null
    asked = _spy(monkeypatch)
    assert server._endpoint_floor()["block"] == 3_000
    seen = set()
    for height, fresh in asked:
        assert fresh is (height in seen), (int(height, 16), fresh)
        seen.add(height)
    assert sum(1 for _, f in asked if f) >= 2  # 4,500 and each null height


def test_a_height_is_asked_twice_at_most_and_the_head_thrice(chain_env, monkeypatch):  # noqa: F811
    """Exactly two asks decide a height; the head gets three."""
    node, game, clock, op = chain_env
    node.block, node.floor = 9_000, 3_000
    asked = _spy(monkeypatch)
    assert server._endpoint_floor()["block"] == 3_000
    counts = {}
    for height, _ in asked:
        counts[int(height, 16)] = counts.get(int(height, 16), 0) + 1
    assert all(n == (2 if h < 3_000 else 1) for h, n in counts.items()), counts
    # the head: two nulls are survived, three are "unreadable"
    server._floor_cache.clear()
    node.null_blocks[node.block] = 2
    assert server._endpoint_floor()["block"] == 3_000
    server._floor_cache.clear()
    node.null_blocks[node.block] = 3
    assert server._endpoint_floor() is None


def test_a_failed_read_mid_search_is_unreadable_not_a_floor(chain_env, monkeypatch):  # noqa: F811
    """A read that FAILS (not a null) during the search proves nothing."""
    node, game, clock, op = chain_env
    game.xp[server._kami_entity_id(5)] = 1_000
    h, signed_at, mined = _earlier_process_entry(node, op, 500)
    _floored_after(node, signed_at, mined, 3_600)
    real = server._rpc

    def rpc(method, params, fresh=False):
        if (method == "eth_getBlockByNumber" and params[0] not in ("latest",)
                and 1 < int(params[0], 16) < node.block - 50):
            raise server._RpcUnavailable("503 Service Unavailable")
        return real(method, params, fresh)
    monkeypatch.setattr(server, "_rpc", rpc)
    monkeypatch.setattr(server, "_LANES", {})
    out = server.run_tool("level_up_kami", kami_id=5, account="testa")
    note = out["notice"]
    assert "could not be determined on this endpoint" in note, note
    assert "no longer serves blocks before" not in note, note
    assert "NOT executed" not in note, note
    assert any(e.hash == h for e in server._lane(op).active())


def test_a_kept_entry_is_resolved_on_the_next_call(chain_env, monkeypatch):  # noqa: F811
    """Kept and checked again on the next call: once the floor can be read,
    the same entry gets the below-the-floor notice and is released."""
    node, game, clock, op = chain_env
    game.xp[server._kami_entity_id(5)] = 50_000
    h, signed_at, mined = _earlier_process_entry(node, op, 500)
    _floored_after(node, signed_at, mined, 3_600)
    real, blind = server._rpc, {"on": True}

    def rpc(method, params, fresh=False):
        if (blind["on"] and method == "eth_getBlockByNumber"
                and int(params[0], 16) >= node.block - 2):
            return None                       # the head answers no block
        return real(method, params, fresh)
    monkeypatch.setattr(server, "_rpc", rpc)
    monkeypatch.setattr(server, "_LANES", {})
    first = server.run_tool("level_up_kami", kami_id=5, account="testa")
    assert "could not be determined on this endpoint" in first["notice"]
    again = server.run_tool("level_up_kami", kami_id=5, account="testa")
    assert "could not be determined on this endpoint" in again["notice"]
    blind["on"] = False
    third = server.run_tool("level_up_kami", kami_id=5, account="testa")
    assert "no longer serves blocks before" in third["notice"], third["notice"]
    assert "NOT executed" not in third["notice"]
    assert all(e.hash != h for e in server._lane(op).active())
    assert "notice" not in server.run_tool("level_up_kami", kami_id=5, account="testa")

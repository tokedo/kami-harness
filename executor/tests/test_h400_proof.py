"""4.0.0 leg A amendment — "proven" means two lookups, on fresh sessions.

The endpoint is load-balanced, and a replica answers null for a mined or
a held transaction on some requests. A single null therefore proves
nothing, and the session that is waiting (or resolving the ledger) may
be pinned to exactly such a replica. Every verdict that RELEASES a nonce
or LABELS a transaction as not executed is confirmed by `_confirm`: two
lookups, each on a fresh session, _GONE_SPACING_S apart, each answered
by one replica (receipt, transaction, count and head in one batch).

The fake node routes sessions to replicas (tests/fakenode.py): the
waiting session is put on a replica that cannot see the hash, while a
fresh session reaches one that can.
"""

from __future__ import annotations

import lanes
import server
from test_h400_lane import _arm_earlier_tail          # noqa: F401
from test_h400_send_path import chain_env, Game       # noqa: F401


def _sends_of(node, h=None):
    return [p[0] for m, p in node.requests
            if m == "eth_sendRawTransaction"]


# ---------------------------------------------------------------------------
# (a) the receipt-wait path: _check_inflight
# ---------------------------------------------------------------------------

def test_a_held_transaction_the_waiting_session_cannot_see_is_kept(chain_env):
    """The waiting session's replica sees no hash at all; the transaction
    is in the pool, unmined, for 12 s. A fresh session finds it held, so
    the entry is KEPT: no TxDroppedError, no re-offer, no nonce handed
    out again — and once it mines, a fresh session's receipt ends the
    wait."""
    node, game, clock, op = chain_env
    node.replica("blind", blind_all=True)
    node.session_replica[0] = "blind"
    game.xp[server._kami_entity_id(5)] = 1_000
    node.hold_mining = True
    t0 = clock.now
    clock.on_sleep.append(
        lambda now: node.release_mining() if now - t0 >= 12 else None)

    r = server.level_up_kami(5, account="testa")

    assert r["status"] == "success"
    assert len(_sends_of(node)) == 1               # no re-offer
    assert [n for _s, n, _h in node.sends] == [500]  # no new nonce
    assert game.level[server._kami_entity_id(5)] == 1
    assert server._lane(op).mined_top == 500
    assert clock.now - t0 >= 12                    # waited for it, held


def test_a_mined_transaction_the_waiting_session_cannot_see_ends_the_wait(
    chain_env,
):
    """Mined at once, but the waiting session's replica has no receipt
    for it. A fresh session's receipt ends the wait — no collision is
    reported although that replica counts the nonce as used."""
    node, game, clock, op = chain_env
    node.replica("blind", blind_all=True)
    node.session_replica[0] = "blind"
    game.xp[server._kami_entity_id(5)] = 1_000
    t0 = clock.now
    r = server.level_up_kami(5, account="testa")
    assert r["status"] == "success"
    assert len(_sends_of(node)) == 1
    assert clock.now - t0 < 10                     # first resolve, not 60 s


# ---------------------------------------------------------------------------
# (b) the pre-send path: _lane_prepare
# ---------------------------------------------------------------------------

def test_an_earlier_entry_absent_once_but_held_is_treated_as_armed(
    chain_env, monkeypatch,
):
    node, game, clock, op = chain_env
    game.inv[11301] = 10
    game.xp[server._kami_entity_id(5)] = 1_000
    armed = _arm_earlier_tail(node, op, [501, 502])
    node.replica("flaky", blind_once=armed)       # one null each, then ok
    node.session_replica[0] = "flaky"
    monkeypatch.setattr(server, "_LANES", {})
    out = server.run_tool("level_up_kami", kami_id=5, account="testa")
    assert "released 2 transaction(s) left armed behind nonce 500" in (
        out.get("notice", ""))
    mine = next(t for t in node.executed if t.hash == out["tx_hash"])
    assert mine.nonce == 503                      # after the drained tail
    assert game.inv[11301] == 8


def test_an_earlier_entry_absent_once_but_mined_is_resolved_not_released(
    chain_env, monkeypatch,
):
    node, game, clock, op = chain_env
    game.inv[11301] = 10
    game.xp[server._kami_entity_id(5)] = 1_000
    (h,) = _arm_earlier_tail(node, op, [500])     # contiguous: it mines
    assert node.queued(op) == [] and node.executed[-1].hash == h
    node.replica("flaky", blind_once=[h])
    node.session_replica[0] = "flaky"
    monkeypatch.setattr(server, "_LANES", {})
    out = server.run_tool("level_up_kami", kami_id=5, account="testa")
    assert f"{h} (act_sequence step 1" in out["notice"]
    assert "has since mined at nonce 500" in out["notice"]
    assert "NOT executed" not in out["notice"]
    lane = server._lane(op)
    assert lane.mined_top >= 500 and lane.floor >= 502
    mine = next(t for t in node.executed if t.hash == out["tx_hash"])
    assert mine.nonce == 501


# ---------------------------------------------------------------------------
# The rule itself: two lookups, fresh sessions, spaced
# ---------------------------------------------------------------------------

def test_proof_is_two_lookups_on_two_fresh_sessions_spaced(chain_env):
    node, game, clock, op = chain_env
    h = "0x" + "ab" * 32                           # never broadcast
    opened_before = len(node.sessions_opened)
    t0 = clock.now
    verdict, receipt = server._confirm(h, op, 500)
    assert verdict == "absent" and receipt is None
    opened = node.sessions_opened[opened_before:]
    assert len(opened) == 2
    sids = [sid for sid, _rep, _t in opened]
    assert 0 not in sids and len(set(sids)) == 2   # fresh, and distinct
    times = {sid: [t for s, _m, hh, t in node.lookups
                   if s == sid and hh == h] for sid in sids}
    assert all(times[sid] for sid in sids)
    assert min(times[sids[1]]) - max(times[sids[0]]) >= (
        server._GONE_SPACING_S)
    assert not [1 for s, _m, hh, _t in node.lookups if s == 0 and hh == h]
    assert clock.now - t0 >= server._GONE_SPACING_S


def test_a_null_from_a_replica_behind_the_seen_head_is_not_evidence(
    chain_env,
):
    """Both fresh sessions land on the SAME lagging replica: it has not
    seen the mined transaction (null), its count is one behind (so the
    nonce looks unused) and its head is behind blocks this process has
    already seen. Its null is not evidence: the verdict is unproven, not
    'absent'."""
    node, game, clock, op = chain_env
    game.xp[server._kami_entity_id(5)] = 1_000
    r = server.level_up_kami(5, account="testa")
    h = r["tx_hash"]
    node.replica("lagging", blind=[h.lower()], behind=3, count_behind=1)
    node.fresh_route = lambda sid: "lagging"
    assert server._confirm(h, op, 500) == (None, None)
    # The same replica, caught up to the head this process has seen:
    # now its null and its count are evidence (absent, nonce unused).
    node.replica("lagging", blind=[h.lower()], behind=0, count_behind=1)
    assert server._confirm(h, op, 500)[0] == "absent"

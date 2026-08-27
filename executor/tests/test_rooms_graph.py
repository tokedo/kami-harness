"""Tests for executor/rooms_graph.py — pure pathfinding module."""

import sys
from pathlib import Path

import pytest

# Allow running `pytest tests/test_rooms_graph.py` from the executor/ dir.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import rooms_graph  # noqa: E402


def _xy_adjacent(a: dict, b: dict) -> bool:
    """Return True if two room_info dicts are xy-adjacent on the same z."""
    if a["z"] != b["z"]:
        return False
    dx = abs(a["x"] - b["x"])
    dy = abs(a["y"] - b["y"])
    return (dx == 1 and dy == 0) or (dx == 0 and dy == 1)


def test_trivial():
    assert rooms_graph.shortest_path(47, 47) == [47]


def test_simple_adjacent():
    # Room 3 is (3,4,1) Torii Gate, Room 2 is (3,3,1) Tunnel of Trees.
    # Adjacent on z=1 (y differs by 1), should be a 2-room path.
    assert rooms_graph.shortest_path(3, 2) == [3, 2]


def test_known_route_47_to_13():
    # 47 (3,7,1) Scrap Paths → 13 (4,3,2) Convenience Store.
    # Only z=1→z=2 entry to 13 is the special exit from room 2.
    path = rooms_graph.shortest_path(47, 13)
    assert path[0] == 47
    assert path[-1] == 13
    assert path[-2] == 2  # must enter 13 via the 2→13 special exit
    assert len(path) == 6  # 5 hops


def test_z_transition_requires_special_exit():
    # Any path crossing z-planes must include a non-xy-adjacent step.
    # Use 1 (z=1) → 88 (z=4) — definitely multi-plane.
    path = rooms_graph.shortest_path(1, 88)
    assert len(path) >= 2
    # At least one consecutive pair in the path must NOT be xy-adjacent
    # (i.e. a special-exit hop, which is the only way to change z).
    has_special = False
    for a_idx, b_idx in zip(path, path[1:]):
        a = rooms_graph.room_info(a_idx)
        b = rooms_graph.room_info(b_idx)
        if not _xy_adjacent(a, b):
            has_special = True
            break
    assert has_special, f"No special-exit hop in cross-z path: {path}"


def test_move_cost():
    assert rooms_graph.move_cost([47, 4, 30, 3, 2, 13]) == 25
    assert rooms_graph.move_cost([47]) == 0
    assert rooms_graph.move_cost([]) == 0


def test_unknown_room():
    with pytest.raises(ValueError):
        rooms_graph.shortest_path(47, 9999)
    with pytest.raises(ValueError):
        rooms_graph.shortest_path(9999, 47)


def test_all_rooms_reachable_from_room_1():
    # Sanity check: from the starting room, BFS must reach every
    # "In Game" room. If this fails, either a special exit is missing
    # from the CSV or there's a genuine gate-locked pocket — flag it.
    all_rs = rooms_graph.all_rooms()
    unreachable = []
    for r in all_rs:
        try:
            rooms_graph.shortest_path(1, r)
        except ValueError:
            unreachable.append(r)
    assert not unreachable, f"Rooms unreachable from room 1: {unreachable}"


# ---------------------------------------------------------------------------
# Gates (catalogs/room-gates.csv)
#
# The catalog is a live extract, so these pin the SHAPE and the two rows
# whose behaviour a caller depends on, not the whole table: a world
# update that adds a gate must not fail the suite, but one that changes
# how a gate is reported must.
# ---------------------------------------------------------------------------


def test_ungated_exit_reports_no_gates():
    assert rooms_graph.gates_on(10, 35) == []


def test_quest_gate_is_reported_on_every_inbound_exit():
    """Room 15's gate is generic: it applies from all three entrances,
    which is why routing around it is impossible and a plan through any
    of them strands the account."""
    for src in (11, 16, 18):
        gates = rooms_graph.gates_on(src, 15)
        assert len(gates) == 1
        assert gates[0]["type"] == "QUEST"
        assert gates[0]["index"] == 35


def test_item_gate_carries_its_threshold():
    gates = rooms_graph.gates_on(72, 88)
    assert [g["type"] for g in gates] == ["ITEM"]
    assert gates[0]["index"] == 100004
    assert gates[0]["value"] == "0x1"


def test_gate_rows_are_well_formed():
    seen = set()
    for a, b in rooms_graph.gated_edges():
        for g in rooms_graph.gates_on(a, b):
            assert g["type"] in {"QUEST", "ITEM", "COMPLETE_COMP"}, (
                f"unknown gate type {g['type']!r} on {a}->{b}: server.py's "
                f"evaluator handles three types and must learn any fourth"
            )
            assert isinstance(g["index"], int)
            assert g["value"] != ""
            seen.add(g["type"])
    assert seen == {"QUEST", "ITEM", "COMPLETE_COMP"}


def test_every_gated_edge_exists_in_the_graph():
    """A gate on an edge BFS cannot walk would be dead data — and worse,
    a gate BFS walks that the catalog does not carry is a strand."""
    for a, b in rooms_graph.gated_edges():
        assert b in rooms_graph.neighbors(a)


def test_blocked_edges_are_routed_around():
    """The whole point: an alternative exists, so BFS takes it."""
    unblocked = rooms_graph.shortest_path(10, 37)
    assert unblocked == [10, 35, 48, 9, 36, 25, 37]
    detour = rooms_graph.shortest_path(10, 37, blocked={(36, 25)})
    assert detour[0] == 10 and detour[-1] == 37
    assert (36, 25) not in list(zip(detour, detour[1:]))


def test_no_alternative_raises():
    """Room 15's three entrances all carry the same gate, so blocking
    them disconnects it entirely — the case that must refuse, not plan."""
    assert rooms_graph.shortest_path(10, 15)[-1] == 15
    with pytest.raises(ValueError):
        rooms_graph.shortest_path(10, 15, blocked={(11, 15), (16, 15), (18, 15)})


def test_blocked_does_not_leak_between_calls():
    rooms_graph.shortest_path(10, 37, blocked={(36, 25)})
    assert rooms_graph.shortest_path(10, 37) == [10, 35, 48, 9, 36, 25, 37]

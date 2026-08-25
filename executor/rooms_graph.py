"""
Pure-Python room graph + BFS pathfinding for Kamigotchi.

Builds an undirected adjacency graph from catalogs/rooms.csv:
  - xy-adjacent rooms on the same z-plane (no diagonals)
  - special exits listed in the `Exits` column (bidirectional)

Only rooms with Status == "In Game" are included. Special-exit references
to unknown / non-in-game rooms are silently skipped.

This module is stdlib-only (csv, collections, pathlib). No web3, no
network, no MCP imports — safe to unit-test in isolation.
"""

from __future__ import annotations

import csv
from collections import deque
from pathlib import Path

_ROOMS_CSV = Path(__file__).resolve().parent.parent / "catalogs" / "rooms.csv"

# Cached graph state — populated on first call.
_rooms: dict[int, dict] = {}
_adjacency: dict[int, set[int]] = {}


def _parse_exits(raw: str) -> list[int]:
    """Parse the Exits column into a list of room indices.

    Handles empty strings, single values, and comma-separated lists.
    """
    if not raw:
        return []
    out: list[int] = []
    for piece in raw.split(","):
        piece = piece.strip()
        if piece:
            try:
                out.append(int(piece))
            except ValueError:
                continue
    return out


def _load(force: bool = False) -> None:
    """Lazy-load rooms.csv and build the adjacency graph (idempotent)."""
    global _rooms, _adjacency
    if _rooms and not force:
        return

    rooms: dict[int, dict] = {}
    raw_exits: dict[int, list[int]] = {}

    with open(_ROOMS_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Status", "").strip() != "In Game":
                continue
            try:
                idx = int(row["Index"])
                x = int(row["X"])
                y = int(row["Y"])
                z = int(row["Z"])
            except (KeyError, ValueError):
                continue
            rooms[idx] = {
                "index": idx,
                "name": row.get("Name", "").strip(),
                "x": x,
                "y": y,
                "z": z,
            }
            raw_exits[idx] = _parse_exits(row.get("Exits", ""))

    # Index by (x, y, z) for fast xy-adjacency lookup.
    pos_index: dict[tuple[int, int, int], int] = {
        (r["x"], r["y"], r["z"]): idx for idx, r in rooms.items()
    }

    adjacency: dict[int, set[int]] = {idx: set() for idx in rooms}
    for idx, r in rooms.items():
        x, y, z = r["x"], r["y"], r["z"]
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nbr = pos_index.get((x + dx, y + dy, z))
            if nbr is not None:
                adjacency[idx].add(nbr)

    # Special exits — directed in the CSV, but treat as bidirectional.
    # Skip references to rooms that aren't in the graph (unknown or not
    # in-game). Track the parsed list per-room so room_info() can expose it.
    special_exits: dict[int, list[int]] = {}
    for idx, targets in raw_exits.items():
        keep: list[int] = []
        for tgt in targets:
            if tgt in rooms:
                adjacency[idx].add(tgt)
                adjacency[tgt].add(idx)
                keep.append(tgt)
        special_exits[idx] = keep

    for idx, r in rooms.items():
        r["special_exits"] = special_exits.get(idx, [])

    _rooms = rooms
    _adjacency = adjacency


def shortest_path(src: int, dst: int) -> list[int]:
    """BFS path from src to dst, inclusive of both ends.

    Returns [src, ..., dst] (len == hops + 1). Returns [src] if src == dst.
    Raises ValueError if either room is unknown or no path exists.
    """
    _load()
    if src not in _rooms:
        raise ValueError(f"Unknown room: {src}")
    if dst not in _rooms:
        raise ValueError(f"Unknown room: {dst}")
    if src == dst:
        return [src]

    parents: dict[int, int] = {src: src}
    queue: deque[int] = deque([src])
    while queue:
        cur = queue.popleft()
        if cur == dst:
            break
        for nbr in _adjacency.get(cur, ()):
            if nbr not in parents:
                parents[nbr] = cur
                queue.append(nbr)

    if dst not in parents:
        raise ValueError(f"No path from {src} to {dst}")

    # Reconstruct.
    path: list[int] = []
    cur = dst
    while cur != src:
        path.append(cur)
        cur = parents[cur]
    path.append(src)
    path.reverse()
    return path


def move_cost(path: list[int]) -> int:
    """Stamina cost for a path: 5 * max(0, len(path) - 1)."""
    return 5 * max(0, len(path) - 1)


def room_info(idx: int) -> dict:
    """Return {index, name, x, y, z, special_exits: list[int]} for a room."""
    _load()
    if idx not in _rooms:
        raise ValueError(f"Unknown room: {idx}")
    r = _rooms[idx]
    return {
        "index": r["index"],
        "name": r["name"],
        "x": r["x"],
        "y": r["y"],
        "z": r["z"],
        "special_exits": list(r.get("special_exits", [])),
    }


def neighbors(idx: int) -> list[int]:
    """Sorted room indices adjacent to `idx` in the catalog graph.

    This is the same adjacency BFS routes over: catalog data, not chain
    truth (catalogs/rooms.csv is a community export and can drift), so a
    caller quoting it must say where it came from. Unknown room: [].
    """
    _load()
    return sorted(_adjacency.get(idx, ()))


def all_rooms() -> list[int]:
    """Sorted list of known (In Game) room indices."""
    _load()
    return sorted(_rooms.keys())

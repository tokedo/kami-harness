"""The bundled catalogs are the upstream data at the release pin.

At 5.0.0 the quest catalogs behind get_expected_objective were still a
copy of 2026-05-01, six months behind the world pin of the release: in
play the tool answered "no row" for quests the pinned world carried. A
release re-vendors every pinned catalog from upstream at its pin, and
this test refuses a file whose bytes are not the ones recorded below,
so a stale copy cannot ship unnoticed.

The quest files are upstream's bytes, unchanged. catalogs/nodes.csv is
upstream's rooms/nodes.csv in this repo's eight columns (Index, Name,
Status, Drops, Affinity, Level Limit, YieldIndex, Scav Cost; no BOM, no
"." or node-effects column), so the digest recorded for it is of that
projection; the upstream file it projects is byte-identical at 04cb25f8
and 8fb6ea58.
"""

import hashlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
UPSTREAM = "Asphodel-OS/kamigotchi-open"

# repo path -> (upstream commit, sha256 of the repo file, upstream path)
CATALOG_PINS = {
    "catalogs/quests/quests.csv": (
        "8fb6ea58be5f773909a4d6d8db32f4726512b8e0",
        "2331fee078506b4ff77f82b70fbb525fa5df89e7055d3837f30b08e9d90744b6",
        "packages/contracts/deployment/world/data/quests/quests.csv"),
    "catalogs/quests/objectives.csv": (
        "8fb6ea58be5f773909a4d6d8db32f4726512b8e0",
        "6d50746b2609f10d1b01dce63062c5983ba57ce94d88d91a6313c5b6901ae389",
        "packages/contracts/deployment/world/data/quests/objectives.csv"),
    "catalogs/quests/requirements.csv": (
        "8fb6ea58be5f773909a4d6d8db32f4726512b8e0",
        "79473c04b3f20edbade9f1bf3cfb744cea9e73c3164367c81c870c7d29f09a8a",
        "packages/contracts/deployment/world/data/quests/requirements.csv"),
    "catalogs/quests/rewards.csv": (
        "8fb6ea58be5f773909a4d6d8db32f4726512b8e0",
        "4fdf7cd0a3b6cab38a5e0a66cc7ec830434e01ca219dbe2d17ccefb9c446f98e",
        "packages/contracts/deployment/world/data/quests/rewards.csv"),
    # The eight-column projection (module docstring), not upstream's bytes.
    "catalogs/nodes.csv": (
        "8fb6ea58be5f773909a4d6d8db32f4726512b8e0",
        "0eddad0bdf5c188d9b4e491d5b2535c12bdea2586f1d945bd51b5982e5071a1f",
        "packages/contracts/deployment/world/data/rooms/nodes.csv"),
}

PROJECTED = {"catalogs/nodes.csv": " in this repo's eight columns"}


@pytest.mark.parametrize("path", sorted(CATALOG_PINS))
def test_the_catalog_is_the_upstream_data_at_the_pin(path):
    pin, recorded, upstream = CATALOG_PINS[path]
    got = hashlib.sha256((REPO / path).read_bytes()).hexdigest()
    assert got == recorded, (
        f"{path}: sha256 {got} is not the {recorded} recorded for "
        f"{UPSTREAM} {upstream} at {pin}. Re-vendor it from upstream "
        f"{upstream} at the release pin{PROJECTED.get(path, '')} and "
        f"update this table.")

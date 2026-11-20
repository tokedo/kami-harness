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
"." or node-effects column and, from a99b4b64, no Harvest Multiplier
column), so the digest recorded for it is of that projection. The
projection of upstream's file at 8fb6ea58 is byte-identical to the one
5.0.0 committed from 04cb25f8; at a99b4b64 it differs in one field
(node 56's level limit, 35 then, blank now).

catalogs/items.csv and catalogs/rooms.csv (pinned since 5.1.0) are
projections too, so each digest is of the projection. Both keep upstream's
row order, write UTF-8 without a BOM, LF line ends and minimal csv
quoting, and rewrite every cell to ASCII: U+2019 and U+2018 become ',
U+2026 becomes ..., every run of whitespace one space, ends stripped.

- items.csv is upstream's items/items.csv in the columns Index, Name,
  Type, Rarity, For, Flags, Effects, Requirements, Status, Description
  (every row with an Index); U+201C and U+201D are removed. This rule
  gives every name of the file it replaced (178 items) unchanged.
- rooms.csv is upstream's rooms/rooms.csv in the columns Index, Name,
  Status, X, Y, Z, Exits, Description (every row with an Index of 1 or
  more: room 0 is upstream's debugging room, which the route graph never
  had); U+201C and U+201D become ". Name, Status, coordinates and exits
  equal those of the file it replaced.
"""

import hashlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
UPSTREAM = "Asphodel-OS/kamigotchi-open"

# repo path -> (upstream commit, sha256 of the repo file, upstream path)
CATALOG_PINS = {
    "catalogs/quests/quests.csv": (
        "a99b4b64b505b722203b2337f76a5b604539c1e0",
        "f237d2e5afde0e72c156de25007098d1bab0f0ebc121295d9209fce4626d3eff",
        "packages/contracts/deployment/world/data/quests/quests.csv"),
    "catalogs/quests/objectives.csv": (
        "a99b4b64b505b722203b2337f76a5b604539c1e0",
        "b9d47b1ec5d28d64d315f72b546073dfbd4cc8d14d045cf0547efd9fbe4ec5b6",
        "packages/contracts/deployment/world/data/quests/objectives.csv"),
    "catalogs/quests/requirements.csv": (
        "a99b4b64b505b722203b2337f76a5b604539c1e0",
        "159bfd543545e4fadeb0c6f2219b96c2d1290fde692f143c80c77c55736da3bd",
        "packages/contracts/deployment/world/data/quests/requirements.csv"),
    "catalogs/quests/rewards.csv": (
        "a99b4b64b505b722203b2337f76a5b604539c1e0",
        "fee1f4e9ae8b994910fba8d36458e09b2b30f78f76c4563619a19f2715eb6801",
        "packages/contracts/deployment/world/data/quests/rewards.csv"),
    # Projections (module docstring), not upstream's bytes.
    "catalogs/items.csv": (
        "a99b4b64b505b722203b2337f76a5b604539c1e0",
        "d4d8d19be6803a627829a0629247c8a7906f21f036c78030623fb7874caa269d",
        "packages/contracts/deployment/world/data/items/items.csv"),
    "catalogs/rooms.csv": (
        "a99b4b64b505b722203b2337f76a5b604539c1e0",
        "6b042fbc9f4e161de3d27ee000a0e04f77fa6c1e079d015b8c447ea631b6004f",
        "packages/contracts/deployment/world/data/rooms/rooms.csv"),
    "catalogs/nodes.csv": (
        "a99b4b64b505b722203b2337f76a5b604539c1e0",
        "06c0784e62ddf02f18844b32810e9328197fcfe2ad10f60aba3a8a3fec1dcc1e",
        "packages/contracts/deployment/world/data/rooms/nodes.csv"),
}

PROJECTED = {
    "catalogs/nodes.csv": " in this repo's eight columns",
    "catalogs/items.csv": " by the projection in the module docstring",
    "catalogs/rooms.csv": " by the projection in the module docstring",
}


@pytest.mark.parametrize("path", sorted(CATALOG_PINS))
def test_the_catalog_is_the_upstream_data_at_the_pin(path):
    pin, recorded, upstream = CATALOG_PINS[path]
    got = hashlib.sha256((REPO / path).read_bytes()).hexdigest()
    assert got == recorded, (
        f"{path}: sha256 {got} is not the {recorded} recorded for "
        f"{UPSTREAM} {upstream} at {pin}. Re-vendor it from upstream "
        f"{upstream} at the release pin{PROJECTED.get(path, '')} and "
        f"update this table.")

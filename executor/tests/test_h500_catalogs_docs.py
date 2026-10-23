"""5.0.0 (F) — catalogs and documents.

C1  catalogs/nodes.csv is the upstream deploy data at 04cb25f8, in this
    repo's eight columns: 15 VIPP nodes (item 2), the level-35 limits,
    the scavenge costs of that data.
C2  A commit-reveal window is stated in blocks with the measured
    cadence, never a fixed number of minutes: every reveal description
    and every reveal error text.
C3  integration/system-ids.md's count is its list: the 68 non-admin
    systems of the studio's manifest at the pin, system.pool included.
C4  systems/harvesting.md states each node's own yield item.
C5  requests, imported directly, is pinned.
"""

import csv
import re
from pathlib import Path

import server

REPO = Path(server._REPO)


def _nodes():
    with open(REPO / "catalogs" / "nodes.csv", newline="") as f:
        return {int(r["Index"]): r for r in csv.DictReader(f)}


# C1 ------------------------------------------------------------------------

def test_the_node_catalog_is_the_deploy_data_at_the_pin():
    nodes = _nodes()
    assert len(nodes) == 64
    assert list(next(csv.reader(open(REPO / "catalogs" / "nodes.csv")))) == [
        "Index", "Name", "Status", "Drops", "Affinity", "Level Limit",
        "YieldIndex", "Scav Cost"]
    vipp = sorted(i for i, r in nodes.items() if r["YieldIndex"] == "2")
    assert vipp == [6, 18, 48, 49, 52, 58, 60, 61, 62, 65, 73, 75, 79, 83, 88]
    assert sorted(i for i, r in nodes.items() if r["Level Limit"] == "35") == [
        31, 35, 36, 47, 50, 56, 57, 59]
    assert sorted(i for i, r in nodes.items() if r["Level Limit"] == "15") == [
        1, 2, 3, 29, 30, 55]
    assert {i: nodes[i]["Scav Cost"] for i in (15, 16, 69, 76, 87)} == {
        15: "200", 16: "1000", 69: "1000", 76: "1000", 87: "600"}
    assert nodes[9]["Affinity"] == "Insect, Eerie"


def test_the_catalog_names_its_source():
    readme = (REPO / "README.md").read_text()
    row = [l for l in readme.splitlines() if "catalogs/nodes.csv" in l][0]
    assert "04cb25f8" in row and "deployment/world/data/rooms/nodes.csv" in row


# C2 ------------------------------------------------------------------------

REVEAL_TOOLS = ("scavenge_claim", "droptable_reveal",
                "scavenge_claim_and_reveal", "gacha_use", "gacha_reroll",
                "gacha_reveal")
CADENCE = ("6 to 10 minutes at the cadence measured in October 2026 "
           "(1.5–2.3 s per block, varying with activity); count blocks, "
           "never minutes")


def test_every_reveal_window_is_counted_in_blocks():
    tools = {t.name: t for t in server.mcp._tool_manager.list_tools()}
    for name in REVEAL_TOOLS:
        d = " ".join((tools[name].description or "").split())
        assert "256 blocks" in d, name
        assert CADENCE in d, name
        assert not re.search(r"~\s*\d+\s*min", d), name
    assert server._WINDOW_256 == "256 blocks — " + CADENCE


def test_no_window_in_the_module_is_a_fixed_number_of_minutes():
    src = Path(server.__file__).read_text()
    assert not re.search(r"256 blocks \(~\d+ min", src)
    assert "~1s blocks" not in src


def test_the_gacha_page_counts_blocks():
    text = (REPO / "systems" / "gacha.md").read_text()
    assert "~1s blocks" not in text and "~4 minutes" not in text
    assert CADENCE in text


# C3 ------------------------------------------------------------------------

def test_the_system_id_count_is_the_list():
    text = (REPO / "integration" / "system-ids.md").read_text()
    section = text.split("## System ID Reference", 1)[1].split("\n## ", 1)[0]
    ids = re.findall(r"^\| `(system\.[A-Za-z0-9.]+)`", section, re.M)
    claimed = int(re.search(r"\*\*(\d+) documented player-facing systems\*\*",
                            text).group(1))
    assert len(ids) == len(set(ids)) == claimed == 68
    assert {"system.pool", "system.Kami721.IsInWorld",
            "system.Kami721.Metadata"} <= set(ids)


# C4 ------------------------------------------------------------------------

def test_the_harvesting_page_states_each_nodes_yield_item():
    text = (REPO / "systems" / "harvesting.md").read_text()
    assert "All nodes yield Musu" not in text
    assert "15 of the 64 nodes pay VIPP" in " ".join(text.split())
    assert "all 65 nodes" not in text


# C5 ------------------------------------------------------------------------

def test_requests_is_pinned():
    reqs = (REPO / "executor" / "requirements.txt").read_text()
    assert re.search(r"^requests==\d+\.\d+\.\d+$", reqs, re.M)

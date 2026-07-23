"""Tool-contract surface checks for the 2.0.0-dev interface.

Verifies the advertised tool count (93 = 84 at v1.5.1 − 15 removed
world-state reads + 23 kami-lens wrappers + kamibots_enable_strategies),
the surface taxonomy (every tool classed ACT/PERCEIVE/OUTSOURCE/META),
the EXPOSURE.md row coverage for READ tools (with the deferred rows),
the shared standing sentences on READ descriptions, schema portability
(SPEC §5.1: no anyOf/oneOf/allOf/$ref), and the earlier per-release
schema pins that still apply.
"""

import json
import re
from pathlib import Path

import server
from schema_version import SCHEMA_VERSION

V130_TOOLS = {
    "create_operator_wallet",
    "register_account",
    "bridge_eth_from_mainnet",
    "bridge_status",
}

V150_TOOLS = {
    "scavenge_claim",
    "droptable_reveal",
    "scavenge_claim_and_reveal",
    "sacrifice_reveal",
}

# The 13 tools that submit multiple transactions (or an on-chain
# allow-failure batch) and expose the explicit allow_partial escape
# hatch from fail-on-any-revert reporting (2.0.0-dev H1).
ALLOW_PARTIAL_TOOLS = {
    "travel_to_room",
    "allocate_skills",
    "level_to",
    "level_and_allocate_batch",
    "feed_level_allocate_batch",
    "use_item_batch",
    "equip_all_batch",
    "unequip_all_batch",
    "cancel_kami_listing",
    "complete_all_trades",
    "speed_craft_batch",
    "stop_harvest_batch",
    "sacrifice_kami_batch",
}

# H2: one wrapper per kami-lens query at pin a0a3e1e (0.2.0).
LENS_TOOLS = {
    "lens_kami", "lens_account", "lens_party", "lens_node", "lens_room",
    "lens_inventory", "lens_item", "lens_items", "lens_config",
    "lens_merchant", "lens_phase", "lens_leaderboard", "lens_killers",
    "lens_battles", "lens_trades", "lens_auctions", "lens_quests",
    "lens_market", "lens_portal", "lens_transfers", "lens_feed",
    "lens_chat", "lens_status",
}

# H3/H3.1: new ACT tools (liquidation, gacha, chat send; the D64-a
# ruling added skill_respec, cast_item, newbie_vendor_buy).
H3_ACT_TOOLS = {
    "liquidate_kami", "gacha_use", "gacha_reroll", "gacha_reveal",
    "chat_send", "skill_respec", "cast_item", "newbie_vendor_buy",
}

# H2: removed from the registry (12 Kamibots world-state reads + 3
# Kamiden/native reads the lens supersedes).
REMOVED_TOOLS = {
    "get_inventory", "get_kami_state", "get_kami_state_slim",
    "get_kamis_progress_batch", "get_prices", "get_npc_prices",
    "get_killer_ranking", "get_leaderboard", "get_all_kamis",
    "get_nodes", "get_account_kamis", "get_guild_members",
    "get_kami_market_listings", "list_open_sell_offers",
    "get_account_trades",
}


def _tools():
    return {t.name: t for t in server.mcp._tool_manager.list_tools()}


def test_schema_version():
    assert SCHEMA_VERSION == "2.0.0-dev"


def test_tool_surface_count():
    names = set(_tools())
    assert V130_TOOLS <= names
    assert V150_TOOLS <= names
    assert H3_ACT_TOOLS <= names
    assert "store_operator_key" not in names
    assert len(names) == 101


def test_removed_tools_absent():
    names = set(_tools())
    assert not (REMOVED_TOOLS & names), REMOVED_TOOLS & names


def test_lens_wrapper_set():
    names = set(_tools())
    assert LENS_TOOLS <= names
    assert {n for n in names if n.startswith("lens_")} == LENS_TOOLS
    assert len(LENS_TOOLS) == 23


def test_taxonomy_covers_registry_exactly():
    names = set(_tools())
    assert set(server.TOOL_CLASSES) == names
    counts = {}
    for cls in server.TOOL_CLASSES.values():
        counts[cls] = counts.get(cls, 0) + 1
    assert counts == {"ACT": 54, "PERCEIVE": 31, "OUTSOURCE": 9, "META": 7}
    assert server.READ_TOOLS <= names
    # every lens wrapper is PERCEIVE
    for n in LENS_TOOLS:
        assert server.TOOL_CLASSES[n] == "PERCEIVE"
    for n in H3_ACT_TOOLS:
        assert server.TOOL_CLASSES[n] == "ACT"


def test_read_descriptions_carry_standing_sentence():
    tools = _tools()
    for name in server.READ_TOOLS:
        assert server._UNTRUSTED_STANDING_SENTENCE in (
            tools[name].description or ""
        ), name
    # and lens wrappers name their serving path
    for name in LENS_TOOLS:
        assert server._LENS_SERVING_SENTENCE in (
            tools[name].description or ""
        ), name
    # non-READ tools do not carry it (spot checks)
    for name in ("harvest_start", "start_strategy", "fund_operator"):
        assert server._UNTRUSTED_STANDING_SENTENCE not in (
            tools[name].description or ""
        ), name


def test_exposure_rows():
    """EXPOSURE.md (D59): one row per READ tool on the live registry,
    plus the visible deferred rows."""
    text = (Path(server._REPO) / "EXPOSURE.md").read_text()
    rows = set(re.findall(r"^\| `([a-z0-9_]+)` \|", text, re.M))
    missing = server.READ_TOOLS - rows
    assert not missing, f"READ tools without an EXPOSURE.md row: {missing}"
    stale = rows - server.READ_TOOLS
    assert not stale, f"EXPOSURE.md rows for non-READ/absent tools: {stale}"
    for deferred in ("guild-members", "general-leaderboards",
                     "windowed-killers"):
        assert re.search(rf"^\| {deferred} \| deferred \|", text, re.M), (
            f"deferred row missing: {deferred}"
        )
    # H3 sweep: unserved game actions stay visible, never silent.
    # (skill-respec / cast-item / newbie-vendor-buy left this list when
    # ruling D64-a added their tools.)
    for action in ("set-operator", "friends", "goals", "npc-sell",
                   "token-portal", "npc-relationships"):
        assert re.search(rf"^\| {re.escape(action)} \|", text, re.M), (
            f"ACT-coverage row missing: {action}"
        )


def test_h3_docstrings_stay_mechanical():
    """The PvP/gacha/chat docstrings describe mechanisms only: no
    advisory or endorsement phrasing in either direction."""
    tools = _tools()
    banned = ("griefing", "recommended", "you should", "consider ",
              "be careful", "beware", "warning", "aggressive", "ethical")
    for name in H3_ACT_TOOLS:
        d = (tools[name].description or "").lower()
        for phrase in banned:
            assert phrase not in d, (name, phrase)


def test_allow_partial_surface():
    tools = _tools()
    have = {
        name for name, t in tools.items()
        if "allow_partial" in t.parameters.get("properties", {})
    }
    assert have == ALLOW_PARTIAL_TOOLS
    for name in sorted(have):
        prop = tools[name].parameters["properties"]["allow_partial"]
        assert prop["type"] == "boolean", name
        assert prop["default"] is False, name


def test_all_schemas_portable():
    for name, t in _tools().items():
        blob = json.dumps(t.parameters)
        for banned in ("anyOf", "oneOf", "allOf", "$ref"):
            assert f'"{banned}"' not in blob, f"{name} schema contains {banned}"


def test_lens_wrapper_schema_shapes():
    tools = _tools()
    node = tools["lens_node"].parameters["properties"]
    assert node["node_index"]["type"] == "integer"
    assert node["with_vitals"]["type"] == "boolean"
    assert node["attacker_kami_index"]["default"] == -1
    chat = tools["lens_chat"].parameters["properties"]
    assert set(chat) == {"room_index", "before_ms", "size", "oversize"}
    account = tools["lens_account"].parameters["properties"]
    assert account["account_key"]["type"] == "string"
    assert account["prose"]["default"] is False


def test_enable_strategies_docstring_facts():
    """The operator-key tool states the grant and the counterparty
    identity as facts, names the hard line, and carries no endorsement
    language (D61 neutral framing)."""
    d = _tools()["kamibots_enable_strategies"].description
    assert "operator" in d.lower()
    assert "signs operator-wallet transactions server-side" in d
    assert "kami transfers" in d
    assert "Asphodel" in d
    assert "docs.asphodel.io" in d
    assert "Owner keys are never sent" in d
    for banned in ("trusted", "safe", "secure", "reliable"):
        assert banned not in d.lower(), banned


def test_commit_ids_are_string_arrays():
    tools = _tools()
    for name in ("droptable_reveal", "sacrifice_reveal"):
        commit_ids = tools[name].parameters["properties"]["commit_ids"]
        assert commit_ids["type"] == "array"
        assert commit_ids["items"] == {"type": "string"}, (
            f"{name}.commit_ids items must be plain strings")


def test_scavenge_claim_params_unchanged():
    props = _tools()["scavenge_claim"].parameters["properties"]
    assert set(props) == {"node_index", "account"}
    assert props["node_index"]["type"] == "integer"


def test_revive_method_schema():
    props = _tools()["revive_kami"].parameters["properties"]
    method = props["method"]
    assert method["type"] == "string"
    assert method["default"] == "onyx"  # back-compatible default
    assert set(method["enum"]) == {
        "onyx",
        "red_ribbon_gummy",
        "melkarth_spell_card",
        "djed_pillar",
        "pale_potion",
    }
    assert props["kami_id"]["type"] == "integer"


def test_withdraw_operator_params_unchanged():
    props = _tools()["withdraw_operator"].parameters["properties"]
    assert set(props) == {"amount_eth", "account"}
    assert props["amount_eth"]["default"] == "all"


def test_bridge_schema_shapes():
    props = _tools()["bridge_eth_from_mainnet"].parameters["properties"]
    assert props["amount_eth"]["type"] == "string"
    assert props["account"]["type"] == "string"
    assert props["dry_run"]["type"] == "boolean"
    assert props["dry_run"]["default"] is False


def test_onboarding_schema_shapes():
    tools = _tools()
    assert (tools["create_operator_wallet"]
            .parameters["properties"]["account"]["type"] == "string")
    reg = tools["register_account"].parameters["properties"]
    assert reg["name"]["type"] == "string"
    assert reg["account"]["type"] == "string"

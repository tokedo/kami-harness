"""Tool-contract surface checks for the 2.0.0 interface.

Verifies the advertised tool count (101 = 84 at v1.5.1 − 17 removed
reads + 23 kami-lens wrappers + kamibots_enable_strategies + 8 ACT
additions + the 2 pool swap tools), the surface taxonomy (ACT/PERCEIVE/OUTSOURCE/META), the
EXPOSURE.md row coverage for READ tools (with the deferred rows), the
shared standing sentences on READ descriptions, schema portability
(SPEC §5.1: no anyOf/oneOf/allOf/$ref), the registry-mass budget, the
tools_hash, and the earlier per-release schema pins.
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

# H3/H3.1: new ACT tools (liquidation, gacha, chat send; the post-sweep
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
    # 2.0.0 budget trim (pre-approved): superseded by lens_quests /
    # quest_state
    "get_active_quests", "get_quest_status",
}


def _tools():
    return {t.name: t for t in server.mcp._tool_manager.list_tools()}


def test_schema_version():
    assert SCHEMA_VERSION == "2.2.0"


def test_readme_current_version_matches_schema_version():
    """The hand-maintained "Current:" line in README.md names the live
    SCHEMA_VERSION — it has no other check and drifts silently without
    one."""
    readme = (Path(server._REPO) / "README.md").read_text()
    m = re.search(r"^Current: \*\*`([^`]+)`\*\*", readme, re.M)
    assert m, "README.md has no 'Current:' version line"
    assert m.group(1) == SCHEMA_VERSION


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
    assert counts == {"ACT": 55, "PERCEIVE": 30, "OUTSOURCE": 9, "META": 7}
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
    """EXPOSURE.md: one row per READ tool on the live registry, plus
    the visible deferred rows."""
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
    # the post-sweep ruling added their tools.)
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
    language (neutral framing: facts, no endorsement)."""
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


def test_registry_mass_within_budget():
    """The agent-visible registry mass, computed from the live FastMCP
    registry, stays within the hard budget."""
    mass = server.registry_mass()
    assert mass <= server.REGISTRY_MASS_BUDGET, (
        f"registry mass {mass} exceeds budget {server.REGISTRY_MASS_BUDGET}"
    )


def test_tools_hash_present_and_deterministic():
    """tools_hash is a sha256 over the sorted registry, surfaced in the
    initialize handshake, and deterministic (no fixed value
    asserted)."""
    h = server.TOOLS_HASH
    assert re.fullmatch(r"[0-9a-f]{64}", h)
    assert server.compute_tools_hash() == h  # deterministic recompute
    assert server.mcp._mcp_server.instructions == f"tools_hash={h}"
    assert server.mcp._mcp_server.version == SCHEMA_VERSION


def test_schema_titles_stripped():
    """Served schemas carry no pydantic auto-"title" noise."""
    for name, t in _tools().items():
        assert '"title"' not in json.dumps(t.parameters), name


# ---------------------------------------------------------------------------
# Surface identity across capability flags (SPEC P6)
#
# Every capability flag is read at import, so the surface it might have
# influenced can only be compared by importing the module again under a
# different environment. A client's recorded fingerprint must identify the
# surface, not the operator's configuration.
# ---------------------------------------------------------------------------

_SURFACE_SENTINEL = "---SURFACE-JSON---"

# Printed by the child: the whole agent-visible surface, plus the flag
# values it actually saw (so this test cannot pass on a flag that never
# reached the module).
_SURFACE_PROBE = f"""
import json, server
tools = server.mcp._tool_manager.list_tools()
print({_SURFACE_SENTINEL!r} + json.dumps({{
    "count": len(tools),
    "mass": server.registry_mass(),
    "tools_hash": server.TOOLS_HASH,
    "schema_version": server.SCHEMA_VERSION,
    "surface": sorted(
        [t.name, t.description or "", t.parameters] for t in tools
    ),
    "flags": {{
        "error_snippets": server.ERROR_SNIPPETS,
        "chat": server.CHAT_ENABLED,
        "presentation_mode": server.PRESENTATION_MODE,
    }},
}}, sort_keys=True))
"""

_FLAG_MATRIX = [
    {"KAMI_ERROR_SNIPPETS": snip, "KAMI_CHAT_ENABLED": chat,
     "PRESENTATION_MODE": mode}
    for snip in ("false", "1")
    for chat in ("false", "1")
    for mode in ("envelope", "name-free")
]


def _probe_surface(overrides):
    """Import the module in a fresh process and return its surface payload."""
    import os
    import subprocess
    import sys

    env = dict(os.environ)
    env.pop("KAMI_ERROR_SNIPPETS", None)
    env.pop("KAMI_CHAT_ENABLED", None)
    env.pop("PRESENTATION_MODE", None)
    env["MAINNET_RPC_URL"] = env.get(
        "MAINNET_RPC_URL", "http://127.0.0.1:9/offline-test"
    )
    env.update(overrides)
    executor_dir = str(Path(__file__).resolve().parent.parent)
    env["PYTHONPATH"] = executor_dir
    proc = subprocess.run(
        [sys.executable, "-c", _SURFACE_PROBE],
        cwd=executor_dir, env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    # Import writes a keyless-startup warning to stdout, so the payload is
    # found by its sentinel rather than by position.
    line = [
        ln for ln in proc.stdout.splitlines() if ln.startswith(_SURFACE_SENTINEL)
    ]
    assert len(line) == 1, proc.stdout
    return json.loads(line[0][len(_SURFACE_SENTINEL):])


def test_surface_identical_across_capability_flags():
    """Tool count, registry mass, tools_hash and every (name, description,
    parameters) triple are byte-identical across every combination of the
    capability flags. KAMI_ERROR_SNIPPETS changes error TEXT only."""
    baseline = None
    seen_flags = set()
    for overrides in _FLAG_MATRIX:
        payload = _probe_surface(overrides)
        flags = payload.pop("flags")
        # The child really saw the configuration under test.
        assert flags["error_snippets"] is (
            overrides["KAMI_ERROR_SNIPPETS"] == "1"
        ), overrides
        assert flags["chat"] is (overrides["KAMI_CHAT_ENABLED"] == "1"), overrides
        assert flags["presentation_mode"] == overrides["PRESENTATION_MODE"]
        seen_flags.add(
            (flags["error_snippets"], flags["chat"], flags["presentation_mode"])
        )
        if baseline is None:
            baseline = payload
            assert payload["count"] == 101
            assert payload["tools_hash"] == server.TOOLS_HASH
            continue
        assert json.dumps(payload, sort_keys=True) == json.dumps(
            baseline, sort_keys=True
        ), f"surface differs under {overrides}"
    assert len(seen_flags) == len(_FLAG_MATRIX)

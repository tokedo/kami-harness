"""Tool-contract surface checks for the v1.4.x interface.

Verifies the advertised tool count (84, unchanged since v1.3.0), that
the v1.3.0 additions are still present, and that every schema touched
in v1.4.0 stays in the portable subset (SPEC §5.1: no
anyOf/oneOf/allOf/$ref). v1.4.0 adds exactly one parameter to the
surface: revive_kami's optional `method` enum (default "onyx",
back-compatible).
"""

import json

import server
from schema_version import SCHEMA_VERSION

V130_TOOLS = {
    "create_operator_wallet",
    "register_account",
    "bridge_eth_from_mainnet",
    "bridge_status",
}


def _tools():
    return {t.name: t for t in server.mcp._tool_manager.list_tools()}


def test_schema_version():
    assert SCHEMA_VERSION == "1.4.0"


def test_tool_surface_count():
    names = set(_tools())
    assert V130_TOOLS <= names
    assert "store_operator_key" not in names
    assert len(names) == 84


def test_touched_tool_schemas_portable():
    tools = _tools()
    for name in V130_TOOLS | {"revive_kami", "withdraw_operator"}:
        blob = json.dumps(tools[name].parameters)
        for banned in ("anyOf", "oneOf", "allOf", "$ref"):
            assert f'"{banned}"' not in blob, (
                f"{name} schema contains {banned}")


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

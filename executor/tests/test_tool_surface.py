"""Tool-contract surface checks for the v1.3.0 interface.

Verifies the advertised tool count, the v1.3.0 additions/removal, and
that the new tools' parameter schemas stay in the portable subset
(SPEC §5.1: no anyOf/oneOf/allOf/$ref).
"""

import json

import server
from schema_version import SCHEMA_VERSION

NEW_TOOLS = {
    "create_operator_wallet",
    "register_account",
    "bridge_eth_from_mainnet",
    "bridge_status",
}


def _tools():
    return {t.name: t for t in server.mcp._tool_manager.list_tools()}


def test_schema_version():
    assert SCHEMA_VERSION == "1.3.0"


def test_tool_surface_v130():
    names = set(_tools())
    assert NEW_TOOLS <= names
    assert "store_operator_key" not in names
    assert len(names) == 84


def test_new_tool_schemas_portable():
    tools = _tools()
    for name in NEW_TOOLS:
        blob = json.dumps(tools[name].parameters)
        for banned in ("anyOf", "oneOf", "allOf", "$ref"):
            assert f'"{banned}"' not in blob, (
                f"{name} schema contains {banned}")


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

"""5.0.0 (A) — the strategy-service family has left the surface.

The nine delegation tools came back at 4.6.0 and leave again at 5.0.0,
with everything only they used: the class tag, the error head their
outages raised, the registration flag on `list_accounts`, and the two
per-account credential names the loader read and the onboarding wrote.

G1  no tool of the nine is registered, classed or a READ tool; the
    class set is {ACT, PERCEIVE, META}.
G2  the service is named nowhere an agent can see it: no served
    description, schema or handshake text, and no string the module can
    raise or return.
G3  the credential names are unread: neither the loader nor the
    operator-wallet rebuild asks the store for them, and the account
    entry has nowhere to keep them.
G4  `list_accounts` states the two addresses and nothing else.
G5  the registry mass is at or under the 73,000 budget.

No network, keys, or chain access.
"""

import ast
import json
import re
from pathlib import Path

import pytest

import secrets_store
import server
from conftest import KEY_A

NINE = (
    "register_kamibots", "kamibots_enable_strategies", "start_strategy",
    "stop_strategy", "get_tier", "get_all_strategies",
    "get_all_strategy_statuses", "get_strategy_status", "get_strategy_logs",
)
SERVICE = re.compile(r"kamibots|outsource|strategy[ -]service|privy",
                     re.IGNORECASE)
LEGACY_NAMES = ("MAIN_KAMIBOTS_API_KEY", "MAIN_PRIVY_ID")


def _tools():
    return {t.name: t for t in server.mcp._tool_manager.list_tools()}


# G1 ------------------------------------------------------------------------

def test_none_of_the_nine_is_served_classed_or_read():
    tools = _tools()
    assert not set(NINE) & set(tools), sorted(set(NINE) & set(tools))
    assert not set(NINE) & set(server.TOOL_CLASSES)
    assert not set(NINE) & server.READ_TOOLS
    assert set(server.TOOL_CLASSES.values()) == {"ACT", "PERCEIVE", "META"}
    assert len(tools) == 100


# G2 ------------------------------------------------------------------------

def test_no_served_text_names_the_service():
    for name, t in _tools().items():
        text = (t.description or "") + json.dumps(t.parameters)
        assert not SERVICE.search(text), (name, SERVICE.search(text).group())
    instructions = server.mcp._mcp_server.instructions
    assert not SERVICE.search(instructions)


def test_no_string_the_module_can_raise_or_return_names_the_service():
    """Every string constant in server.py — docstrings, messages, result
    keys — is free of the service; comments are history and may say what
    left. The error classes and the client are gone too."""
    src = (Path(server.__file__)).read_text()
    hits = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if SERVICE.search(node.value):
                hits.append((node.lineno, node.value[:80]))
    assert hits == []
    for gone in ("OutsourceUnavailableError", "StrategyServiceError",
                 "_strategy_api", "KAMIBOTS_BASE", "_headers",
                 "_owned_kami_indices", "_summarize_strategy_statuses",
                 "_OUTSOURCE_TOOLS", "_redactor", "_account_secrets"):
        assert not hasattr(server, gone), gone
    assert "OUTSOURCE_UNAVAILABLE" not in src


# G3 ------------------------------------------------------------------------

@pytest.fixture()
def asked(monkeypatch):
    """Every name the module asks the secret store for."""
    names = []
    real = secrets_store.get

    def spy(name, *a, **k):
        names.append(name)
        return real(name, *a, **k)

    monkeypatch.setattr(secrets_store, "get", spy)
    return names


def test_the_loader_never_reads_the_two_names(
    secret_store, asked, monkeypatch, tmp_path, capsys
):
    secret_store.write_text(
        f"MAIN_OWNER_KEY={KEY_A}\n"
        "MAIN_KAMIBOTS_API_KEY=kb-left-behind\n"
        "MAIN_PRIVY_ID=did:privy:left-behind\n"
    )
    secrets_store.load()
    monkeypatch.setattr(server, "_ROSTER_PATH", tmp_path / "roster.yaml")
    server._load_accounts()
    err = capsys.readouterr().err
    assert "main (owner-only)" in err
    assert not set(LEGACY_NAMES) & set(asked), asked
    assert not SERVICE.search(err)
    acct = server._accounts["main"]
    for attr in ("api_key", "privy_id"):
        assert not hasattr(acct, attr), attr
    assert set(server._Account.__slots__) == {
        "label", "_operator_key", "owner_key", "_operator_addr", "owner_addr"}


def test_the_operator_rebuild_never_reads_the_two_names(
    secret_store, asked, monkeypatch, tmp_path
):
    secret_store.write_text(
        f"MAIN_OWNER_KEY={KEY_A}\n"
        "MAIN_KAMIBOTS_API_KEY=kb-left-behind\n"
        "MAIN_PRIVY_ID=did:privy:left-behind\n"
    )
    secrets_store.load()
    monkeypatch.setattr(server, "_ROSTER_PATH", tmp_path / "roster.yaml")
    monkeypatch.setattr(server, "_accounts",
                        {"main": server._Account("main", None, KEY_A)})
    r = server.create_operator_wallet("main")
    assert r["account"] == "main"
    assert not set(LEGACY_NAMES) & set(asked), asked
    # the keys file keeps what it held; nothing new is written for them
    text = secret_store.read_text()
    assert text.count("MAIN_KAMIBOTS_API_KEY") == 1
    assert text.count("MAIN_PRIVY_ID") == 1


def test_a_left_behind_credential_line_is_not_exported(secret_store,
                                                        monkeypatch):
    """The store still treats the account-id name as secret-shaped (a
    guard for keys files written by 4.6.x): it never reaches the
    environment a child process inherits."""
    import os
    monkeypatch.delenv("MAIN_PRIVY_ID", raising=False)
    secret_store.write_text("MAIN_PRIVY_ID=did:privy:left-behind\n")
    secrets_store.load()
    assert "MAIN_PRIVY_ID" not in os.environ


# G4 ------------------------------------------------------------------------

def test_list_accounts_states_the_two_addresses_only(accounts):
    r = server.list_accounts()
    for label, row in r["accounts"].items():
        assert set(row) == {"operator_address", "owner_address"}, label
    d = _tools()["list_accounts"].description
    assert not SERVICE.search(d)


# G5 ------------------------------------------------------------------------

def test_the_mass_is_inside_the_73000_budget():
    assert server.REGISTRY_MASS_BUDGET == 73_000
    assert server.registry_mass() <= 73_000

"""4.4.0 — a roster label means your own account.

The daemon reads every key that is not digits or a 0x address as an
in-game account NAME. Everywhere else on this surface a label such as
`main` names one of the deployment's own wallets, so a label sent to the
daemon as-is was answered with whichever player chose that name.

K1  `lens_account` with a label reads the label's own account: one
    request, by the label's owner address (the operator address when
    the entry has no owner key), checked to be that wallet's account
    before it is returned untouched. A label whose wallet has no
    account says so in the write tools' words.
    `lens_inventory` with a label is refused before any request: the
    daemon's `inventory` query takes no address, and one wrapper makes
    at most one request.
K2  the two descriptions say it.
K3  every other key is sent exactly as before; daemon errors on the
    label's read pass through as their own classes.

The daemon is the unix-socket JSON-lines stub from test_lens_wrappers;
raw request bytes come from test_400_lens's socket double. Every index
and address here is synthetic (the roster wallets are the standard
local-dev throwaway keys).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import server
from conftest import KEY_A, KEY_B
from test_400_lens import fake_socket  # noqa: F401  (fixture)
from test_lens_wrappers import lens, short_dir  # noqa: F401  (fixtures)

STRANGER_OWNER = "0x" + "11" * 20
STRANGER_OPERATOR = "0x" + "22" * 20
OTHER_OWNER = "0x" + "33" * 20


def _env(index, name, owner, operator):
    return {
        "data": {"id": "0x" + "ab" * 32, "index": index, "name": name,
                 "ownerAddress": owner, "operatorAddress": operator,
                 "roomIndex": 1, "kamis": []},
        "untrusted": ["name"],
        "meta": {"servedAt": "t", "blockNumber": 100, "stale": False,
                 "mode": "daemon", "appliedThrough": 100},
    }


# The player who chose the name "main", index 501.
STRANGER = _env(501, "main", STRANGER_OWNER, STRANGER_OPERATOR)
STRANGER_INVENTORY = {
    "data": {"index": 501, "items": [{"balance": 9, "item": {"index": 1}}]},
    "untrusted": [], "meta": {"servedAt": "t", "stale": False},
}


@pytest.fixture()
def roster(monkeypatch):
    """The deployment's own labels, replacing whatever the secret store
    loaded: `main` (owner A, operator B), `op` (operator B, no owner key)
    and a digit-shaped label `7`."""
    accts = {
        "main": server._Account("main", KEY_B, KEY_A),
        "op": server._Account("op", KEY_B, None),
        "7": server._Account("7", KEY_B, KEY_A),
    }
    monkeypatch.setattr(server, "_accounts", accts)
    return accts


@pytest.fixture()
def own(roster):
    """The label `main`'s own account, index 77."""
    a = roster["main"]
    return _env(77, "mine", a.owner_addr, a.operator_addr)


def _daemon(answers):
    """(query, first arg) -> answer; anything else is answered the way
    the daemon answers a key it holds no account for."""
    def respond(req):
        args = req.get("args") or []
        key = (req["query"], args[0] if args else "")
        if key in answers:
            a = answers[key]
            return a if a is None or "ok" in a else {"ok": True, **a}
        return {"ok": False, "error": {
            "code": "NOT_FOUND", "message": f"account {key[1]} not in mirror"}}
    return respond


def _err(code, message, **extra):
    return {"ok": False, "error": {"code": code, "message": message, **extra}}


def _desc(name):
    return " ".join(server.mcp._tool_manager.get_tool(name).description.split())


# ---------------------------------------------------------------------------
# K1 / K3.1 — a label reads its own account, by its own address
# ---------------------------------------------------------------------------

def test_a_label_reads_its_own_account_not_the_player_named_like_it(
        lens, roster, own):
    owner = roster["main"].owner_addr
    lens["responder"] = _daemon({("account", "main"): STRANGER,
                                 ("account", owner): own})
    r = server.lens_account("main")
    assert [q["args"] for q in lens["requests"]] == [[owner]]
    assert lens["requests"][0]["query"] == "account"
    assert r == own                 # the envelope verbatim, nothing added


def test_the_label_read_keeps_identity_only_prose_and_at_least_block(
        lens, roster, own):
    owner = roster["main"].owner_addr
    lens["responder"] = _daemon({("account", owner): own})
    server.lens_account("main", prose=True, identity_only=True,
                        at_least_block=88)
    assert len(lens["requests"]) == 1
    req = lens["requests"][0]
    assert req["args"] == [owner, "--slim", "--at-least=88"]
    assert req.get("prose") is True


def test_an_owner_less_label_reads_by_its_operator_address(lens, roster):
    op = roster["op"].operator_addr
    mine = _env(78, "mine2", OTHER_OWNER, op)
    lens["responder"] = _daemon({("account", "op"): STRANGER,
                                 ("account", op): mine})
    assert server.lens_account("op") == mine
    assert [q["args"] for q in lens["requests"]] == [[op]]


def test_an_operator_match_on_someone_elses_account_is_not_yours(lens, roster):
    """The daemon tries an address as an owner, then as an operator. An
    account that names the label's owner wallet only as its OPERATOR is
    another player's: the owner wallet has no account."""
    owner = roster["main"].owner_addr
    theirs = _env(502, "squatter", STRANGER_OWNER, owner)
    lens["responder"] = _daemon({("account", "main"): STRANGER,
                                 ("account", owner): theirs})
    with pytest.raises(server.LensQueryError) as ei:
        server.lens_account("main")
    assert str(ei.value) == (
        f"NOT_FOUND: no account is registered for owner wallet {owner} "
        f"(account 'main')")
    assert len(lens["requests"]) == 1


def test_the_ownership_check_compares_addresses_by_value(lens, roster):
    owner = roster["main"].owner_addr
    lower = _env(77, "mine", owner.lower(), STRANGER_OPERATOR)
    lens["responder"] = _daemon({("account", owner): lower})
    assert server.lens_account("main") == lower


def test_an_answer_without_the_owner_field_is_not_served(lens, roster, own):
    owner = roster["main"].owner_addr
    del own["data"]["ownerAddress"]
    lens["responder"] = _daemon({("account", owner): own})
    with pytest.raises(server.LensQueryError) as ei:
        server.lens_account("main")
    assert ei.value.code == "INTERNAL"
    assert "cannot confirm it is account 'main'" in str(ei.value)
    assert "no account is registered" not in str(ei.value)


# ---------------------------------------------------------------------------
# K3.2 — a label with no account says so, and nothing else is asked
# ---------------------------------------------------------------------------

def test_a_label_with_no_account_says_so_in_the_write_tools_words(
        lens, roster):
    owner = roster["main"].owner_addr
    lens["responder"] = _daemon({("account", "main"): STRANGER})
    with pytest.raises(server.LensQueryError) as ei:
        server.lens_account("main")
    assert ei.value.code == "NOT_FOUND"
    assert str(ei.value) == (
        f"NOT_FOUND: no account is registered for owner wallet {owner} "
        f"(account 'main')")
    assert [q["args"] for q in lens["requests"]] == [[owner]]


def test_an_owner_less_label_with_no_account_names_its_operator(lens, roster):
    op = roster["op"].operator_addr
    lens["responder"] = _daemon({("account", "op"): STRANGER})
    with pytest.raises(server.LensQueryError) as ei:
        server.lens_account("op")
    assert str(ei.value) == (
        f"NOT_FOUND: no account is registered for operator {op} "
        f"(account 'op')")
    assert [q["args"] for q in lens["requests"]] == [[op]]


# ---------------------------------------------------------------------------
# K3.3 / K3.4 — every key that is not a label is sent byte for byte as before
# ---------------------------------------------------------------------------

UNCHANGED = [
    # (call, the exact bytes 4.3.0 sends)
    (lambda: server.lens_account("someone"),
     b'{"id": 1, "query": "account", "args": ["someone"]}\n'),
    (lambda: server.lens_account("mainx"),
     b'{"id": 1, "query": "account", "args": ["mainx"]}\n'),
    (lambda: server.lens_account(" main"),
     b'{"id": 1, "query": "account", "args": [" main"]}\n'),
    (lambda: server.lens_account("someone", identity_only=True),
     b'{"id": 1, "query": "account", "args": ["someone", "--slim"]}\n'),
    (lambda: server.lens_inventory("someone"),
     b'{"id": 1, "query": "inventory", "args": ["someone"]}\n'),
    (lambda: server.lens_inventory("mainx"),
     b'{"id": 1, "query": "inventory", "args": ["mainx"]}\n'),
    # a name keeps its case: only a label is matched case-insensitively
    (lambda: server.lens_account("Someone"),
     b'{"id": 1, "query": "account", "args": ["Someone"]}\n'),
    (lambda: server.lens_account("SOMEONE"),
     b'{"id": 1, "query": "account", "args": ["SOMEONE"]}\n'),
    (lambda: server.lens_account("MainX"),
     b'{"id": 1, "query": "account", "args": ["MainX"]}\n'),
    (lambda: server.lens_account("Someone", identity_only=True),
     b'{"id": 1, "query": "account", "args": ["Someone", "--slim"]}\n'),
    (lambda: server.lens_account("SOMEONE", identity_only=True),
     b'{"id": 1, "query": "account", "args": ["SOMEONE", "--slim"]}\n'),
    (lambda: server.lens_account("MainX", identity_only=True),
     b'{"id": 1, "query": "account", "args": ["MainX", "--slim"]}\n'),
    (lambda: server.lens_inventory("Someone"),
     b'{"id": 1, "query": "inventory", "args": ["Someone"]}\n'),
    (lambda: server.lens_inventory("SOMEONE"),
     b'{"id": 1, "query": "inventory", "args": ["SOMEONE"]}\n'),
    (lambda: server.lens_inventory("MainX"),
     b'{"id": 1, "query": "inventory", "args": ["MainX"]}\n'),
    # digits are an index, even when a label is spelled the same
    (lambda: server.lens_account("501"),
     b'{"id": 1, "query": "account", "args": ["501"]}\n'),
    (lambda: server.lens_account("7"),
     b'{"id": 1, "query": "account", "args": ["7"]}\n'),
    (lambda: server.lens_inventory("7"),
     b'{"id": 1, "query": "inventory", "args": ["7"]}\n'),
    # a 0x address is an address
    (lambda: server.lens_account(STRANGER_OWNER),
     b'{"id": 1, "query": "account", "args": ["' + STRANGER_OWNER.encode()
     + b'"]}\n'),
    # empty: the daemon's default operator
    (lambda: server.lens_account(""), b'{"id": 1, "query": "account"}\n'),
    (lambda: server.lens_inventory(""), b'{"id": 1, "query": "inventory"}\n'),
]


@pytest.mark.parametrize("call, sent", UNCHANGED)
def test_a_key_that_is_not_a_label_is_sent_as_before(
        roster, fake_socket, call, sent):
    call()
    assert len(fake_socket.made) == 1
    assert fake_socket.made[-1].sent == sent


def test_an_address_stays_an_address_even_when_a_label_is_spelled_so(
        roster, fake_socket, monkeypatch):
    """A label may be any alphanumeric string, so one can be spelled
    like a 0x address (stored lower-case, as every label is). The key is
    still the address: lens_account sends it as it is, not the label's
    own wallet, and lens_inventory sends it as before instead of
    refusing it."""
    shaped = "0x" + "ab" * 20
    monkeypatch.setitem(server._accounts, shaped,
                        server._Account(shaped, KEY_B, KEY_A))
    server.lens_account(shaped)
    server.lens_inventory(shaped)
    assert [s.sent for s in fake_socket.made] == [
        b'{"id": 1, "query": "account", "args": ["' + shaped.encode()
        + b'"]}\n',
        b'{"id": 1, "query": "inventory", "args": ["' + shaped.encode()
        + b'"]}\n',
    ]


# ---------------------------------------------------------------------------
# K3.5 (as ruled) — lens_inventory refuses a label before any request
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key", ["main", "MAIN", "Main", "op"])
def test_lens_inventory_refuses_a_label_and_asks_nothing(lens, roster, key):
    lens["responder"] = _daemon({("inventory", key): STRANGER_INVENTORY})
    label = key.lower()
    with pytest.raises(server.LensQueryError) as ei:
        server.lens_inventory(key)
    assert ei.value.code == "BAD_ARGS"
    assert str(ei.value) == (
        f"BAD_ARGS: '{label}' is a roster label: lens_inventory takes an "
        f"account index or a player's account name; "
        f"lens_account('{label}') returns your own account's index")
    assert lens["requests"] == []


def test_lens_inventory_refuses_a_label_with_at_least_block_too(lens, roster):
    lens["responder"] = _daemon({("inventory", "main"): STRANGER_INVENTORY})
    with pytest.raises(server.LensQueryError, match="roster label"):
        server.lens_inventory("main", at_least_block=88)
    assert lens["requests"] == []


# ---------------------------------------------------------------------------
# K3.6 — a key that differs from a label only by case is the label
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key", ["MAIN", "Main"])
def test_case_does_not_turn_a_label_into_a_name(lens, roster, own, key):
    owner = roster["main"].owner_addr
    lens["responder"] = _daemon({("account", key): STRANGER,
                                 ("account", owner): own})
    assert server.lens_account(key) == own
    assert [q["args"] for q in lens["requests"]] == [[owner]]


# ---------------------------------------------------------------------------
# K3.7 — daemon trouble on the label's read is the daemon's own error
# ---------------------------------------------------------------------------

def _gate_the_label_read(lens, roster, answer):
    """Answer `answer` on the label's address read; the stranger to a
    name read (which is what 4.3.0 sends)."""
    owner = roster["main"].owner_addr
    lens["responder"] = _daemon({("account", "main"): STRANGER,
                                 ("account", owner): answer})
    return owner


def _never_unregistered(e):
    assert "no account is registered" not in str(e)


def test_a_daemon_that_is_not_live_is_not_live(lens, roster):
    _gate_the_label_read(lens, roster, _err(
        "NOT_READY", "daemon not LIVE (SETUP 40%): mirror empty"))
    with pytest.raises(server.LensNotReadyError) as ei:
        server.lens_account("main")
    assert ei.value.daemon_state == "not-live"
    _never_unregistered(ei.value)


def test_a_starting_daemon_is_starting(lens, roster):
    """The one NOT_FOUND that is not about the account: it must stay a
    LensUnavailableError and never become "not registered"."""
    _gate_the_label_read(lens, roster, _err(
        "NOT_FOUND", "mirror not initialized yet"))
    with pytest.raises(server.LensUnavailableError) as ei:
        server.lens_account("main")
    assert ei.value.daemon_state == "starting"
    _never_unregistered(ei.value)


def test_a_dropped_connection_is_unavailable(lens, roster):
    _gate_the_label_read(lens, roster, None)
    with pytest.raises(server.LensUnavailableError, match="closed the") as ei:
        server.lens_account("main")
    _never_unregistered(ei.value)


def test_not_applied_on_the_label_read_is_retry_not_absent(lens, roster):
    _gate_the_label_read(lens, roster, _err(
        "NOT_APPLIED", "block 90 was not applied within 5000 ms: "
                       "appliedThrough=89", appliedThrough=89))
    with pytest.raises(server.LensNotAppliedError) as ei:
        server.lens_account("main", at_least_block=90)
    assert ei.value.applied_through == 89
    _never_unregistered(ei.value)


@pytest.mark.parametrize("code", ["BAD_ARGS", "INTERNAL"])
def test_other_daemon_errors_on_the_label_read_pass_through(lens, roster, code):
    _gate_the_label_read(lens, roster, _err(code, "something else"))
    with pytest.raises(server.LensQueryError) as ei:
        server.lens_account("main")
    assert ei.value.code == code
    assert str(ei.value) == f"{code}: something else"


def test_no_daemon_is_no_daemon(roster, short_dir, monkeypatch):
    monkeypatch.setattr(server, "KAMI_LENS_SOCKET", str(short_dir / "absent.sock"))
    with pytest.raises(server.LensUnavailableError) as ei:
        server.lens_account("main")
    assert "daemon state: unreachable" in str(ei.value)
    _never_unregistered(ei.value)


# ---------------------------------------------------------------------------
# K2 — the descriptions say it; the refused read is a visible deferral
# ---------------------------------------------------------------------------

def test_lens_account_says_a_label_is_your_own_account():
    d = _desc("lens_account")
    assert "a roster label (your own account)" in d
    assert "a label wins over a name" in d


def test_lens_inventory_says_a_label_is_refused():
    d = _desc("lens_inventory")
    assert "a roster label is refused" in d
    assert "lens_account has your own index" in d


def test_own_inventory_by_label_is_a_visible_deferral():
    text = (Path(server._REPO) / "EXPOSURE.md").read_text()
    assert re.search(r"^\| own-inventory-by-label \| deferred \|", text, re.M)

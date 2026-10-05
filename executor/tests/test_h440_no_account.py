"""4.4.0 part 2 — no account given = your own account.

A lens read called with no account used to be filled by the DAEMON's
configured default operator, which a new deployment does not have. It
is now for the roster account labelled `main`:

L1  lens_account, lens_inventory, lens_party, lens_roster: main's own
    account, or the plain "no account is registered" error while main's
    wallet has none.
L2  lens_quests, lens_market, lens_trades (no account already means
    registry / market / open trades): main's index once it has an
    account, else the 4.3.0 request, never an error for the missing
    argument.
L3  a roster label in lens_inventory reads that label's own inventory.

Without a `main` entry every one of the seven sends the 4.3.0 bytes.
An index is learned with one `account <own address> --slim` read,
checked like lens_account's, cached once found and never while absent.

The daemon is the unix-socket JSON-lines stub; raw bytes come from the
socket double. Indexes and addresses are synthetic.
"""

from __future__ import annotations

import pytest

import server
from conftest import KEY_A, KEY_B
from test_400_lens import fake_socket  # noqa: F401  (fixture)
from test_h440_own_account import (
    OTHER_OWNER, STRANGER_OWNER, STRANGER_OPERATOR, _env, _err,
)
from test_lens_wrappers import lens, short_dir  # noqa: F401  (fixtures)

OWN_INDEX = 77
_UNSET = object()


def _answer(query, args):
    """What the stub daemon serves for a real read: the request echoed,
    so a test can tell which account it was for."""
    return {"data": {"query": query, "args": args}, "untrusted": [],
            "meta": {"servedAt": "t", "stale": False, "mode": "daemon"}}


class World:
    """The stub daemon's world: one roster wallet that is or is not
    registered (index 77), and a daemon default operator (index 900)
    that the daemon itself would prefill when a read names no account."""

    DEFAULT_OPERATOR = "900"

    def __init__(self, acct, registered=True, field="ownerAddress"):
        self.acct = acct
        self.registered = registered
        self.address = acct.owner_addr or acct.operator_addr
        self.field = field
        self.resolution = _UNSET    # override the answer to the slim read
                                    # (None: drop the connection)

    def respond(self, req):
        q, args = req["query"], list(req.get("args") or [])
        flags = [a for a in args if a.startswith("--")]
        pos = [a for a in args if not a.startswith("--")]
        if not pos and q in ("account", "party", "roster", "inventory",
                             "trades", "quests", "market"):
            pos = [self.DEFAULT_OPERATOR]           # the daemon's prefill
        if q == "account":
            if pos[0] == self.address:
                if self.resolution is not _UNSET:
                    return self.resolution
                if self.registered:
                    data = _env(OWN_INDEX, "mine", STRANGER_OWNER,
                                STRANGER_OPERATOR)
                    data["data"][self.field] = self.address
                    return {"ok": True, **data}
            if pos[0] == self.DEFAULT_OPERATOR:
                return {"ok": True, **_env(900, "dflt", OTHER_OWNER,
                                           STRANGER_OPERATOR)}
            return _err("NOT_FOUND", f"account {pos[0]} not in mirror")
        return {"ok": True, **_answer(q, pos + flags)}


def _sent(lens_state):
    return [(r["query"], r.get("args")) for r in lens_state["requests"]]


@pytest.fixture()
def main_acct(monkeypatch):
    """A roster with `main` (owner A, operator B) and a second label."""
    main = server._Account("main", KEY_B, KEY_A)
    farm = server._Account("farm", KEY_A, KEY_B)
    monkeypatch.setattr(server, "_accounts", {"main": main, "farm": farm})
    return main


@pytest.fixture()
def world(lens, main_acct):
    w = World(main_acct)
    lens["responder"] = w.respond
    return w


@pytest.fixture()
def no_main(monkeypatch):
    """A roster with labels, none of them `main`."""
    monkeypatch.setattr(server, "_accounts", {
        "farm": server._Account("farm", KEY_A, KEY_B)})


# The four reads that need an account; the three where none has a meaning.
L1 = {
    "party": lambda **k: server.lens_party(**k),
    "roster": lambda **k: server.lens_roster(**k),
    "inventory": lambda **k: server.lens_inventory(**k),
}
L2 = {
    "trades": lambda **k: server.lens_trades(**k),
    "quests": lambda **k: server.lens_quests(**k),
    "market": lambda **k: server.lens_market(**k),
}


def _resolution(acct, *extra):
    return ("account", [acct.owner_addr, "--slim", *extra])


def _no_account_text(acct):
    return (f"NOT_FOUND: no account is registered for owner wallet "
            f"{acct.owner_addr} (account '{acct.label}')")


# ---------------------------------------------------------------------------
# L1 — main's own account; resolved once, then cached
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", sorted(L1))
def test_l1_reads_mains_index_resolving_it_once(lens, world, query):
    first = L1[query]()
    assert _sent(lens) == [_resolution(world.acct), (query, ["77"])]
    assert first == _answer(query, ["77"])          # the real read, verbatim
    lens["requests"].clear()
    L1[query]()
    assert _sent(lens) == [(query, ["77"])]          # cached: one request


@pytest.mark.parametrize("query", sorted(L1))
def test_l1_without_an_account_says_so_and_asks_again_next_time(
        lens, world, query):
    world.registered = False
    with pytest.raises(server.LensQueryError) as ei:
        L1[query]()
    assert str(ei.value) == _no_account_text(world.acct)
    assert _sent(lens) == [_resolution(world.acct)]   # no second request
    assert server._own_index_cache == {}              # nothing cached
    world.registered = True                           # it registers
    lens["requests"].clear()
    assert L1[query]() == _answer(query, ["77"])
    assert _sent(lens) == [_resolution(world.acct), (query, ["77"])]


def test_lens_account_reads_main_in_one_request(lens, world):
    r = server.lens_account()
    assert _sent(lens) == [("account", [world.acct.owner_addr])]
    assert r["data"]["index"] == OWN_INDEX
    lens["requests"].clear()
    server.lens_account(identity_only=True, prose=True, at_least_block=5)
    assert _sent(lens) == [("account", [world.acct.owner_addr, "--slim",
                                        "--at-least=5"])]
    assert lens["requests"][0].get("prose") is True


def test_lens_account_without_mains_account_says_so(lens, world):
    world.registered = False
    with pytest.raises(server.LensQueryError) as ei:
        server.lens_account()
    assert str(ei.value) == _no_account_text(world.acct)
    assert _sent(lens) == [("account", [world.acct.owner_addr])]


@pytest.mark.parametrize("query", sorted(L1))
def test_l1_at_least_block_holds_both_reads_and_the_cached_one(
        lens, world, query):
    L1[query](at_least_block=90)
    assert _sent(lens) == [_resolution(world.acct, "--at-least=90"),
                           (query, ["77", "--at-least=90"])]
    lens["requests"].clear()
    L1[query](at_least_block=91)
    assert _sent(lens) == [(query, ["77", "--at-least=91"])]


# ---------------------------------------------------------------------------
# L2 — main's index once registered; else the 4.3.0 request, never an error
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", sorted(L2))
def test_l2_sends_mains_index_once_registered(lens, world, query):
    assert L2[query]() == _answer(query, ["77"])
    assert _sent(lens) == [_resolution(world.acct), (query, ["77"])]
    lens["requests"].clear()
    L2[query]()
    assert _sent(lens) == [(query, ["77"])]


@pytest.mark.parametrize("query", sorted(L2))
def test_l2_without_mains_account_sends_the_old_request(lens, world, query):
    world.registered = False
    L2[query]()                                       # no error
    assert _sent(lens) == [_resolution(world.acct), (query, None)]
    assert server._own_index_cache == {}
    lens["requests"].clear()
    L2[query]()                                       # asks again
    assert _sent(lens) == [_resolution(world.acct), (query, None)]


@pytest.mark.parametrize("query", sorted(L2))
@pytest.mark.parametrize("failure, cls", [
    (_err("NOT_READY", "daemon not LIVE (SETUP 40%): mirror empty"),
     server.LensNotReadyError),
    (_err("NOT_FOUND", "mirror not initialized yet"),
     server.LensUnavailableError),
    (None, server.LensUnavailableError),              # dropped connection
    (_err("INTERNAL", "boom"), server.LensQueryError),
])
def test_l2_never_swallows_a_daemon_failure_on_the_resolution_read(
        lens, world, query, failure, cls):
    world.resolution = failure
    with pytest.raises(cls) as ei:
        L2[query]()
    assert "no account is registered" not in str(ei.value)
    assert _sent(lens) == [_resolution(world.acct)]   # the real read not made


@pytest.mark.parametrize("query", sorted(L1))
def test_l1_daemon_failures_on_the_resolution_read_keep_their_class(
        lens, world, query):
    world.resolution = _err("NOT_READY", "daemon not LIVE (SETUP 40%): x")
    with pytest.raises(server.LensNotReadyError) as ei:
        L1[query]()
    assert "no account is registered" not in str(ei.value)
    world.resolution = _err("NOT_APPLIED", "block 90 not applied",
                            appliedThrough=89)
    with pytest.raises(server.LensNotAppliedError):
        L1[query](at_least_block=90)
    assert server._own_index_cache == {}


# ---------------------------------------------------------------------------
# the ownership guard applies to the resolution read
# ---------------------------------------------------------------------------

def _squatted(world):
    """The slim read answers an account that names main's owner wallet
    only as its OPERATOR — someone else's account."""
    theirs = _env(502, "squatter", STRANGER_OWNER, world.acct.owner_addr)
    world.resolution = {"ok": True, **theirs}


@pytest.mark.parametrize("query", sorted(L1))
def test_l1_an_operator_match_is_not_mains_account(lens, world, query):
    _squatted(world)
    with pytest.raises(server.LensQueryError) as ei:
        L1[query]()
    assert str(ei.value) == _no_account_text(world.acct)
    assert _sent(lens) == [_resolution(world.acct)]
    assert server._own_index_cache == {}


@pytest.mark.parametrize("query", sorted(L2))
def test_l2_an_operator_match_is_not_mains_account(lens, world, query):
    _squatted(world)
    L2[query]()
    assert _sent(lens) == [_resolution(world.acct), (query, None)]


def test_a_resolution_answer_without_the_owner_field_is_not_trusted(
        lens, world):
    slim = _env(OWN_INDEX, "mine", STRANGER_OWNER, STRANGER_OPERATOR)
    del slim["data"]["ownerAddress"]
    world.resolution = {"ok": True, **slim}
    with pytest.raises(server.LensQueryError) as ei:
        server.lens_roster()
    assert ei.value.code == "INTERNAL"
    with pytest.raises(server.LensQueryError, match="INTERNAL"):
        server.lens_quests()
    assert server._own_index_cache == {}


_MISSING = object()


@pytest.mark.parametrize("query", ["roster", "quests"])        # L1, L2
@pytest.mark.parametrize("index", [True, "77", 77.0, _MISSING],
                         ids=["bool", "str", "float", "missing"])
def test_a_resolution_answer_without_an_integer_index_is_not_used(
        lens, world, query, index):
    """`true` is an int to Python and would be sent as "True"; a string,
    a float or no index at all is not an account index either. None of
    them is used, cached, or followed by the real read — and the
    reads where no account has a meaning raise it too."""
    slim = _env(OWN_INDEX, "mine", world.acct.owner_addr, STRANGER_OPERATOR)
    if index is _MISSING:
        del slim["data"]["index"]
    else:
        slim["data"]["index"] = index
    world.resolution = {"ok": True, **slim}
    with pytest.raises(server.LensQueryError) as ei:
        (L1 | L2)[query]()
    assert ei.value.code == "INTERNAL"
    assert "has no index" in str(ei.value)
    assert _sent(lens) == [_resolution(world.acct)]   # no second request
    assert server._own_index_cache == {}


# ---------------------------------------------------------------------------
# flags keep their place after the filled index, as the daemon's prefill
# ---------------------------------------------------------------------------

FLAGGED = [
    (lambda: server.lens_party(full=True, stats=True), "party"),
    (lambda: server.lens_roster(stats=True, full=True), "roster"),
    (lambda: server.lens_roster(full=True), "roster"),
    (lambda: server.lens_quests(full=True), "quests"),
    (lambda: server.lens_market(full=True), "market"),
    (lambda: server.lens_trades(full=True), "trades"),
]


@pytest.mark.parametrize("call, query", FLAGGED)
def test_the_filled_request_is_the_daemons_own_prefill_of_the_old_one(
        lens, world, monkeypatch, call, query):
    """The daemon fills a missing account as [operator, ...flags as sent]
    (positionals counted, flags kept in order). The harness's filled
    request is exactly that, with main's index."""
    accounts = server._accounts
    monkeypatch.setattr(server, "_accounts", {})
    call()
    old = lens["requests"][-1].get("args") or []
    monkeypatch.setattr(server, "_accounts", accounts)
    lens["requests"].clear()
    call()
    assert lens["requests"][-1]["args"] == ["77"] + [
        a for a in old if a.startswith("--")]
    assert lens["requests"][-1]["args"][1:] == old


def test_the_flags_in_order(lens, world):
    server.lens_party(full=True, stats=True)
    server.lens_roster(stats=True, full=True)
    server.lens_quests(full=True)
    assert [r["args"] for r in lens["requests"]][1:] == [
        ["77", "--full", "--stats"], ["77", "--stats", "--full"],
        ["77", "--full"]]


# ---------------------------------------------------------------------------
# an explicit index, 0 included, is never "no account"
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("call, query", [
    (lambda: server.lens_party(0), "party"),
    (lambda: server.lens_roster(0), "roster"),
    (lambda: server.lens_trades(0), "trades"),
    (lambda: server.lens_quests(0), "quests"),
    (lambda: server.lens_market(0), "market"),
    (lambda: server.lens_party(12, full=True), "party"),
])
def test_an_explicit_index_is_sent_and_nothing_is_resolved(
        lens, world, call, query):
    call()
    assert len(lens["requests"]) == 1
    assert lens["requests"][0]["query"] == query
    assert lens["requests"][0]["args"][0] in ("0", "12")


def test_a_daemon_default_operator_changes_nothing_while_main_exists(
        lens, world):
    """The stub fills a request with no account with its default
    operator (900), as a configured daemon does. Every read for main
    names main's index, so the daemon's prefill never applies."""
    for query in sorted(L1) + sorted(L2):
        (L1 | L2)[query]()
    real = [r for r in lens["requests"] if r["query"] != "account"]
    assert all(r["args"][0] == "77" for r in real)
    assert server.lens_account()["data"]["index"] == OWN_INDEX


# ---------------------------------------------------------------------------
# L3 — a roster label in lens_inventory reads its own inventory
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key", ["main", "MAIN", "Main"])
def test_lens_inventory_reads_a_labels_own_inventory(lens, world, key):
    assert server.lens_inventory(key) == _answer("inventory", ["77"])
    assert _sent(lens) == [_resolution(world.acct), ("inventory", ["77"])]


def test_lens_inventory_with_an_unregistered_label_says_so(lens, world):
    world.registered = False
    with pytest.raises(server.LensQueryError) as ei:
        server.lens_inventory("main")
    assert str(ei.value) == _no_account_text(world.acct)
    assert _sent(lens) == [_resolution(world.acct)]


def test_lens_inventory_of_an_owner_less_label_resolves_by_its_operator(
        lens, monkeypatch):
    op = server._Account("op", KEY_B, None)
    monkeypatch.setattr(server, "_accounts", {"op": op})
    w = World(op, field="operatorAddress")
    lens["responder"] = w.respond
    assert server.lens_inventory("op") == _answer("inventory", ["77"])
    assert _sent(lens) == [("account", [op.operator_addr, "--slim"]),
                           ("inventory", ["77"])]
    w.registered = False
    server._own_index_cache.clear()
    with pytest.raises(server.LensQueryError, match=(
            f"no account is registered for operator {op.operator_addr} "
            f"\\(account 'op'\\)")):
        server.lens_inventory("op")


def test_each_wallet_is_resolved_and_cached_on_its_own(lens, world):
    """`farm` is another wallet: resolving main does not answer for it."""
    server.lens_inventory("main")
    lens["requests"].clear()
    with pytest.raises(server.LensQueryError, match="account 'farm'"):
        server.lens_inventory("farm")
    farm = server._accounts["farm"]
    assert _sent(lens) == [("account", [farm.owner_addr, "--slim"])]


# ---------------------------------------------------------------------------
# without a `main` entry, every one of the seven sends the 4.3.0 bytes
# ---------------------------------------------------------------------------

NO_MAIN = [
    (lambda: server.lens_account(), b'{"id": 1, "query": "account"}\n'),
    (lambda: server.lens_account(identity_only=True),
     b'{"id": 1, "query": "account", "args": ["--slim"]}\n'),
    (lambda: server.lens_inventory(), b'{"id": 1, "query": "inventory"}\n'),
    (lambda: server.lens_party(), b'{"id": 1, "query": "party"}\n'),
    (lambda: server.lens_party(full=True, stats=True),
     b'{"id": 1, "query": "party", "args": ["--full", "--stats"]}\n'),
    (lambda: server.lens_roster(), b'{"id": 1, "query": "roster"}\n'),
    (lambda: server.lens_roster(stats=True, full=True),
     b'{"id": 1, "query": "roster", "args": ["--stats", "--full"]}\n'),
    (lambda: server.lens_trades(), b'{"id": 1, "query": "trades"}\n'),
    (lambda: server.lens_trades(full=True),
     b'{"id": 1, "query": "trades", "args": ["--full"]}\n'),
    (lambda: server.lens_quests(), b'{"id": 1, "query": "quests"}\n'),
    (lambda: server.lens_quests(full=True),
     b'{"id": 1, "query": "quests", "args": ["--full"]}\n'),
    (lambda: server.lens_market(), b'{"id": 1, "query": "market"}\n'),
    (lambda: server.lens_market(full=True),
     b'{"id": 1, "query": "market", "args": ["--full"]}\n'),
    (lambda: server.lens_party(at_least_block=9),
     b'{"id": 1, "query": "party", "args": ["--at-least=9"]}\n'),
]


@pytest.mark.parametrize("call, sent", NO_MAIN)
def test_without_main_every_read_sends_the_old_bytes(
        no_main, fake_socket, call, sent):
    call()
    assert len(fake_socket.made) == 1
    assert fake_socket.made[-1].sent == sent


# ---------------------------------------------------------------------------
# name-free presentation does not get in the way of the resolution read
# ---------------------------------------------------------------------------

def test_name_free_mode_resolves_by_index_and_address(lens, world, monkeypatch):
    monkeypatch.setattr(server, "PRESENTATION_MODE", "name-free")
    slim = _env(OWN_INDEX, "mine", world.acct.owner_addr, STRANGER_OPERATOR)
    del slim["data"]["name"]                      # withheld, with receipt
    slim["meta"]["suppressed"] = ["name"]
    world.resolution = {"ok": True, **slim}
    assert server.lens_roster() == _answer("roster", ["77"])
    assert [r.get("noAuthored") for r in lens["requests"]] == [True, True]


# ---------------------------------------------------------------------------
# the descriptions
# ---------------------------------------------------------------------------

def _desc(name):
    return " ".join(server.mcp._tool_manager.get_tool(name).description.split())


def test_the_descriptions_say_no_account_is_your_own():
    l1 = ("-1: your own account (roster label main); without that label, "
          "the daemon default operator.")
    for name in ("lens_party", "lens_roster"):
        assert l1 in _desc(name), name
    key = ("Empty: your own account (roster label main); without that "
           "label, the daemon default operator.")
    for name in ("lens_account", "lens_inventory"):
        assert key in _desc(name), name
        assert ("a roster label (your own account), or a player's account "
                "name; a label wins over a name") in _desc(name), name
    for name, rest in (("lens_trades", "open trades only"),
                       ("lens_quests", "registry only"),
                       ("lens_market", "market only")):
        assert (f"-1: your own account (roster label main) once registered; "
                f"else {rest} / daemon default operator.") in _desc(name), name
    assert "refused" not in _desc("lens_inventory")

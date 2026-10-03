"""4.0.0 — the lens 1.0.0 passthroughs.

The daemon is the unix-socket JSON-lines stub from test_lens_wrappers:
argument mapping is asserted on the captured request, and answers pass
through verbatim. What lens leg B has not built yet (receipts,
pool-history, the feed/node selectors, `--equipment`) is exercised
against the agreed 1.0.0 contract, the same way.
"""

from __future__ import annotations

import json

import pytest

import server
from conftest import KEY_A, KEY_B
from test_lens_wrappers import ENVELOPE, lens, short_dir  # noqa: F401


def _args(lens_state):
    return lens_state["requests"][-1].get("args")


# ---------------------------------------------------------------------------
# argument mapping
# ---------------------------------------------------------------------------

@pytest.fixture()
def roster_main(monkeypatch):
    acct = server._Account("main", KEY_B, KEY_A)          # operator B, owner A
    monkeypatch.setitem(server._accounts, "main", acct)
    return acct


CASES = [
    (lambda: server.lens_kami(45, equipment=True), "kami", ["45", "--equipment"]),
    (lambda: server.lens_kami(45, stats=True, equipment=True),
     "kami", ["45", "--stats", "--equipment"]),
    (lambda: server.lens_roster(7, stats=True, full=True),
     "roster", ["7", "--stats", "--full"]),
    (lambda: server.lens_node(86, with_vitals=True, target_kami_indices=[12, 45],
                              occupant_account_index=7),
     "node", ["86", "--with-vitals", "--targets=12,45", "--account=7"]),
    (lambda: server.lens_node(86, occupant_account_index=0),
     "node", ["86", "--account=0"]),
    (lambda: server.lens_feed(limit=200, account_index=7),
     "feed", ["--limit=200", "--account=7"]),
    (lambda: server.lens_feed(100, "KILL", limit=5),
     "feed", ["100", "KILL", "--limit=5"]),
    (lambda: server.lens_pool_history(1, 103), "pool-history", ["1", "103"]),
    (lambda: server.lens_pool_history(1, 103, from_ts=1_790_000_000),
     "pool-history", ["1", "103", "1790000000"]),
]


@pytest.mark.parametrize("call, query, args", CASES)
def test_the_1_0_0_options_reach_the_daemon(lens, call, query, args):
    call()
    req = lens["requests"][-1]
    assert req["query"] == query
    assert req.get("args") == args


def test_defaults_send_none_of_the_new_options(lens):
    """Every new parameter is optional and absent by default: the
    request is byte-for-byte what 3.7.0 sent."""
    for call, args in [
        (lambda: server.lens_kami(45), ["45"]),
        (lambda: server.lens_roster(7), ["7"]),
        (lambda: server.lens_node(86), ["86"]),
        (lambda: server.lens_feed(), None),
        (lambda: server.lens_party(7), ["7"]),
        (lambda: server.lens_inventory("7"), ["7"]),
        (lambda: server.lens_account("7"), ["7"]),
    ]:
        call()
        assert _args(lens) == args


AT_LEAST = [
    (lambda b: server.lens_kami(45, at_least_block=b), "kami", ["45"]),
    (lambda b: server.lens_party(7, at_least_block=b), "party", ["7"]),
    (lambda b: server.lens_roster(7, at_least_block=b), "roster", ["7"]),
    (lambda b: server.lens_account("7", at_least_block=b), "account", ["7"]),
    (lambda b: server.lens_node(86, at_least_block=b), "node", ["86"]),
    (lambda b: server.lens_inventory("7", at_least_block=b), "inventory", ["7"]),
]


@pytest.mark.parametrize("call, query, base", AT_LEAST)
def test_at_least_block_holds_the_read_for_that_block(lens, call, query, base):
    call(34_100_200)
    req = lens["requests"][-1]
    assert req["query"] == query
    assert req["args"] == base + ["--at-least=34100200"]
    assert not any(a.startswith("--max-wait") for a in req["args"])


def test_lens_receipts_reads_the_roster_accounts_owner_address(lens, roster_main):
    server.lens_receipts("main", at_least_block=77)
    req = lens["requests"][-1]
    assert req["query"] == "receipts"
    assert req["args"] == [roster_main.owner_addr, "--at-least=77"]


def test_lens_receipts_falls_back_to_the_operator_address(lens, monkeypatch):
    op_only = server._Account("op", KEY_B, None)
    monkeypatch.setitem(server._accounts, "op", op_only)
    server.lens_receipts("op")
    assert _args(lens) == [op_only.operator_addr]


def test_the_verify_set_carries_at_least_block_and_status_does_not():
    tools = {t.name: t for t in server.mcp._tool_manager.list_tools()}
    verify = {"lens_kami", "lens_party", "lens_roster", "lens_account",
              "lens_node", "lens_inventory", "lens_receipts"}
    for name in verify:
        p = tools[name].parameters["properties"]["at_least_block"]
        assert p == {"default": -1, "type": "integer"}, name
    with_it = {n for n, t in tools.items()
               if "at_least_block" in t.parameters.get("properties", {})}
    assert with_it == verify


# ---------------------------------------------------------------------------
# NOT_APPLIED, INCOMPLETE, and verbatim 1.0.0 envelopes
# ---------------------------------------------------------------------------

def test_not_applied_is_its_own_error_and_carries_applied_through(lens):
    lens["responder"] = lambda req: {
        "ok": False,
        "error": {"code": "NOT_APPLIED",
                  "message": "block 101 was not applied within 5000 ms: "
                             "appliedThrough=99",
                  "appliedThrough": 99},
    }
    with pytest.raises(server.LensNotAppliedError) as ei:
        server.lens_kami(45, at_least_block=101)
    assert ei.value.applied_through == 99
    assert ei.value.code == "NOT_APPLIED"
    assert isinstance(ei.value, server.LensQueryError)
    assert not isinstance(ei.value, server.LensUnavailableError)


def test_incomplete_passes_through_as_a_query_error(lens):
    lens["responder"] = lambda req: {
        "ok": False,
        "error": {"code": "INCOMPLETE",
                  "message": "kami 45 cannot be projected completely"},
    }
    with pytest.raises(server.LensQueryError) as ei:
        server.lens_kami(45)
    assert ei.value.code == "INCOMPLETE"
    assert not isinstance(ei.value, server.LensNotAppliedError)


def test_incomplete_rows_and_the_new_meta_pass_through_verbatim(lens):
    """An incomplete node row has no vitals; nothing here fills them in."""
    env = {
        "data": {"index": 9, "harvestsTotal": 2, "harvestsServed": 2,
                 "harvestsSelected": 1, "targetsAbsent": [77],
                 "harvests": [{"kami": {"index": 12}, "incomplete": True},
                              {"kami": {"index": 45},
                               "vitals": {"hp": {"current": 10}}}]},
        "untrusted": [],
        "meta": {"servedAt": "t", "blockNumber": 34_100_250,
                 "appliedThrough": 34_100_249, "reconciledThrough": 34_100_100,
                 "incompleteRows": 1, "stale": False, "mode": "daemon"},
    }
    lens["responder"] = lambda req: {"ok": True, **env}
    assert server.lens_node(9, with_vitals=True,
                            target_kami_indices=[12, 45, 77]) == env


def test_status_without_the_head_sample_passes_through(lens):
    """The head fields are omitted together when the sample is stale;
    nothing in the harness reads them, and the answer is not padded."""
    status = {"data": {"state": "LIVE", "degraded": ["reconcile-stalled:75"],
                       "sync": {"appliedThrough": 5, "shortReads": 0,
                                "olderWritesSkipped": 0,
                                "lastReconcileAdvanceAt": "t"}},
              "untrusted": [], "meta": {"servedAt": "t", "stale": False}}
    lens["responder"] = lambda req: {"ok": True, **status}
    r = server.lens_status()
    assert r == status
    assert "blockLag" not in r["data"] and "headBlockNumber" not in r["data"]


# ---------------------------------------------------------------------------
# the transport: a held read on its own connection, a timeout that outlasts it
# ---------------------------------------------------------------------------

class _Sock:
    made: list["_Sock"] = []
    reply = {"id": 1, "ok": True, **ENVELOPE}

    def __init__(self, *a):
        self.timeout = None
        self.sent = b""
        self._out = (json.dumps(self.reply) + "\n").encode()
        _Sock.made.append(self)

    def settimeout(self, t):
        self.timeout = t

    def connect(self, path):
        pass

    def sendall(self, b):
        self.sent += b

    def recv(self, n):
        out, self._out = self._out, b""
        return out

    def close(self):
        pass


@pytest.fixture()
def fake_socket(monkeypatch):
    _Sock.made = []
    monkeypatch.setattr(server.socket, "socket", _Sock)
    return _Sock


def test_every_read_opens_its_own_connection(fake_socket):
    server.lens_kami(45, at_least_block=10)
    server.lens_kami(45)
    assert len(fake_socket.made) == 2


def test_the_socket_timeout_outlasts_the_wait(fake_socket):
    server._lens_request("kami", [45])
    assert fake_socket.made[-1].timeout == 30
    server._lens_request("kami", [45], at_least=10)          # daemon default 5 s
    assert fake_socket.made[-1].timeout >= 5 + 15
    server._lens_request("kami", [45], at_least=10, max_wait_ms=29_000)
    s = fake_socket.made[-1]
    assert s.timeout >= 29 + 15
    assert b"--max-wait=29000" in s.sent
    server._lens_request("kami", [45], at_least=10, max_wait_ms=90_000)
    assert b"--max-wait=30000" in fake_socket.made[-1].sent  # the cap


# ---------------------------------------------------------------------------
# descriptions and instructions
# ---------------------------------------------------------------------------

def _desc(name):
    return " ".join(server.mcp._tool_manager.get_tool(name).description.split())


def test_the_agent_is_told_once_how_to_verify_and_what_incomplete_means():
    i = server.mcp._mcp_server.instructions
    assert "at_least_block" in i and "NOT_APPLIED" in i and "retry" in i
    assert "incomplete: true" in i and "never zero" in i


def test_portal_claim_and_cancel_point_to_lens_receipts():
    assert "lens_receipts" in _desc("portal_claim")
    assert "lens_receipts" in _desc("portal_cancel")
    assert "claimable time" in _desc("portal_claim")


def test_lens_feed_states_its_new_default():
    d = _desc("lens_feed")
    assert "NEWEST" in d and "default 50" in d and "1-500" in d


def test_there_is_no_lens_quote_wrapper():
    names = {t.name for t in server.mcp._tool_manager.list_tools()}
    assert "lens_quote" not in names and "pool_swap_quote" in names

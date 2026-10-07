"""4.5.0 — a failed receipt wait is never `error`, and never a second send.

Found in a live play session: an `act_sequence` call reported six
consecutive rows as `"status": "error"` carrying a hash and nothing else,
inside a `partial` result. All six had mined and succeeded. `landed`
under-counted them, and the next liquidate's `spoils` absorbed the two
kills among them. The receipt wait itself had failed — web3's own
provider error out of `wait_for_transaction_receipt` — and the sequence's
one-by-one receipt fallback mapped that untyped exception through
`_failed_tx_fields`' catch-all, `{"status": "error"}`, a state the
contract does not have.

The same untyped exception escapes the single-send path's `_lane_await`;
there `_send_tx_retry` read a `-32000` or readiness text in it as a
pre-send failure and SENT THE ACTION AGAIN.

K1  the sequence fallback: a wait that fails with anything untyped is
    `unconfirmed` with the failure as `reason` and its hash kept, and is
    re-checked before the call returns as a step whose budget ended is;
    `notice` names the steps still unconfirmed for that reason.
K2  `_failed_tx_fields`' catch-all is never reached by a sequence row.
K3  bookkeeping over the final labels: a late landing's kill decodes
    against its own receipt; K3b an unconfirmed kill leaves the next kill
    by the same killer with `spoils: null`, never a number that may hold
    the unconfirmed kill's share.
F1  `_await_receipt`: an untyped exception from the wait is re-checked
    once and is otherwise `TxUnconfirmedError` with `reason` — a
    post-broadcast type, never retried.

Hermetic: the fake node of the 4.0.0 tests (a real Web3 over a simulated
JSON-RPC node, on a virtual clock) and the scripted chain of the 3.5.0
tests.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import textwrap
from types import SimpleNamespace

import eth_abi
import pytest
import requests
import requests.exceptions as requests_exceptions
import web3.exceptions as web3_exceptions

import server
from fakenode import READINESS_ERROR, Result, addr_for
from test_h350_families import FakeChain, _steps, seq_env  # noqa: F401
from test_h400_send_path import _feeds, chain_env  # noqa: F401

# What an endpoint answers while it is failing. Neither is the readiness
# class (_install_read_retry passes it through on the first answer), nor
# "transaction not found", nor "index ... progress", nor -32601, nor
# "request timed out": web3 raises a plain Web3RPCError for both, out of
# wait_for_transaction_receipt (which catches only the first two).
INTERNAL = {"code": -32603, "message": "internal error"}
SERVER_ERROR = {"code": -32000, "message": "upstream request failed"}
# One read on the readiness class is four requests: the first answer and
# _install_read_retry's three retries.
READINESS_READ = 1 + len(server._READ_RETRY_DELAYS_S)

STATES = {"success", "reverted", "unconfirmed", "not_sent"}
FEED = {"op": "feed", "kami_id": 31, "item_id": 11301}


# ---------------------------------------------------------------------------
# The doubles
# ---------------------------------------------------------------------------

KILLER = 31
SPOILS = {41: 700, 42: 650, 43: 600}
GROSS = {41: 1_500, 42: 1_400, 43: 1_300}


def _liq(victim: int) -> dict:
    return {"op": "liquidate", "kami_id": KILLER, "victim_kami_id": victim}


def _value_write(entity: int, value: int):
    """One component.value write, as the chain logs it (ComponentValueSet:
    topic1 the component, topic3 the entity, data one abi-encoded word)."""
    topics = [
        "0x" + server._STORE_SET_RECORD_EVENT,
        "0x" + server._VALUE_COMPONENT_ID.to_bytes(32, "big").hex(),
        "0x" + "00" * 32,
        "0x" + entity.to_bytes(32, "big").hex(),
    ]
    data = (32).to_bytes(32, "big") * 2 + value.to_bytes(32, "big")
    return (addr_for("world"), topics, data)


class Kills:
    """The liquidate system on the fake node. Each kill writes the
    victim's harvest bounty and drains it, and adds that victim's spoils
    to the killer's harvest bounty — the writes _decode_kill reads."""

    def __init__(self, node):
        self.bounty: dict[int, int] = {}
        self.victims = {server._harvest_entity_id(v): v for v in SPOILS}
        self.killer = {server._kami_entity_id(KILLER):
                       server._harvest_entity_id(KILLER)}
        node.handle(addr_for("system.harvest.liquidate"),
                    "executeTyped(uint256,uint256)", self._liquidate)

    def _liquidate(self, node, caller, args, commit):
        victim_harv, killer_eid = eth_abi.decode(["uint256", "uint256"], args)
        victim = self.victims[victim_harv]
        k = self.killer[killer_eid]
        after = self.bounty.get(k, 0) + SPOILS[victim]
        if commit:
            self.bounty[k] = after
        return Result(gas_used=900_000, logs=[
            _value_write(victim_harv, GROSS[victim]),
            _value_write(victim_harv, 0),
            _value_write(k, after),
        ])


def _nonce_of(node, tx_hash) -> int | None:
    tx = node.txs.get(str(tx_hash).lower())
    return None if tx is None else tx.nonce


def _receipts_fail(node, nonces, times, error):
    """The next `times` receipt reads of each of these nonces' hashes are
    answered with `error` — an error body from the node."""
    for n in nonces:
        node.fail("eth_getTransactionReceipt", times=times, error=error,
                  when=lambda p, n=n: _nonce_of(node, p[0]) == n)


def _receipts_unreachable(node, nonces, times):
    """The next `times` receipt reads of each of these nonces' hashes
    never reach the node: the transport raises, as `requests` does when
    the endpoint refuses the connection."""
    provider = server.w3.provider
    inner = provider.make_request
    left = {n: times for n in nonces}

    def make_request(method, params):
        if method == "eth_getTransactionReceipt":
            n = _nonce_of(node, params[0])
            if left.get(n, 0) > 0:
                left[n] -= 1
                raise requests.exceptions.ConnectionError(
                    "connection refused by the endpoint")
        return inner(method, params)

    provider.make_request = make_request


def _no_batched_receipts(monkeypatch):
    """The endpoint will not batch reads: act_sequence's one-by-one
    receipt fallback (the path the live incident took)."""
    monkeypatch.setattr(server, "_batch_receipts", lambda hashes: None)


def _sender_txs(node, sender):
    return sorted((t for t in node.txs.values() if t.sender == sender.lower()),
                  key=lambda t: t.nonce)


def _install_waits(monkeypatch, chain, waits):
    """The scripted chain, with each step's receipt wait scripted:
    "ok" lands it, an exception instance is raised by the wait."""
    monkeypatch.setattr(server, "w3", chain)

    def await_receipt(tx_hash, built, timeout, account=None, ceiling_key=None):
        i = int(tx_hash[-2:], 16)
        w = waits[i]
        if isinstance(w, BaseException):
            raise w
        return SimpleNamespace(transactionHash=bytes([i]) * 32,
                               blockNumber=900 + i, gasUsed=1000 + i, status=1)

    monkeypatch.setattr(server, "_await_receipt", await_receipt)


def _seq_hash(i: int) -> str:
    return "0x" + bytes([i]).hex() * 32


def _exception_classes() -> list[type]:
    """Every exception class the fallback's wait can surface: web3's,
    the transport's, the builtins a lane or decode step can raise, and
    this module's own untyped ones."""
    found = []
    for module in (web3_exceptions, requests_exceptions):
        for _name, obj in vars(module).items():
            if (isinstance(obj, type) and issubclass(obj, Exception)
                    and obj.__module__.startswith(module.__name__.split(".")[0])):
                found.append(obj)
    found += [OSError, ValueError, KeyError, TypeError, AttributeError,
              RuntimeError, LookupError, server._RpcUnavailable,
              server.PreTxValidationError]
    return list(dict.fromkeys(found))


def _instance(cls):
    for args in (("the receipt wait failed",), ()):
        try:
            return cls(*args)
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# F1 — the single-send path: a failed wait is never a second send
# ---------------------------------------------------------------------------

def test_the_wait_turns_every_untyped_exception_into_unconfirmed(monkeypatch):
    """F1 at its one place: whatever web3 or the transport raises out of
    the wait, _await_receipt raises TxUnconfirmedError carrying the hash
    and the failure — a post-broadcast type, never retried."""
    h = "0x" + "cd" * 32
    wrong = []
    for cls in _exception_classes():
        exc = _instance(cls)
        if exc is None or isinstance(exc, web3_exceptions.TimeExhausted):
            continue

        def wait(_h, timeout=None, _e=exc):
            raise _e

        monkeypatch.setattr(server, "w3", SimpleNamespace(
            eth=SimpleNamespace(wait_for_transaction_receipt=wait),
            provider=None))
        try:
            server._await_receipt(h, None, timeout=5)
            wrong.append((cls.__name__, "returned"))
        except server.TxUnconfirmedError as e:
            if (e.tx_hash, e.reason) != (h, server._err_text(exc)[:300]):
                wrong.append((cls.__name__, e.tx_hash, e.reason))
        except Exception as e:                       # noqa: BLE001
            wrong.append((cls.__name__, type(e).__name__))
    assert wrong == [], wrong


@pytest.mark.parametrize("body, reads", [
    (SERVER_ERROR, 1), (READINESS_ERROR, READINESS_READ),
], ids=["-32000", "readiness"])
def test_a_failed_receipt_wait_is_never_a_second_send(chain_env, body, reads):  # noqa: F811
    """The feed mined; the endpoint failed the wait's read with a body
    whose text _send_tx_retry routes on (a -32000, or the readiness class
    surviving the read retry). Exactly ONE transaction goes out, and the
    re-check reads its receipt: the result carries that hash as success."""
    node, game, clock, op = chain_env
    game.inv[11301] = 5
    base = node.pending_count(op)
    _receipts_fail(node, [base], reads, body)

    out = server.use_item_batch(21, 11301, 1, account="testa")

    assert all(f.times == 0 for f in node.faults)     # the wait did fail
    sent = _sender_txs(node, op)
    assert [t.nonce for t in sent] == [base], [(t.nonce, t.hash) for t in sent]
    assert node.latest[op.lower()] == base + 1 and not node.pool[op.lower()]
    (leg,) = out["txs"]
    assert leg["status"] == "success" and leg["tx_hash"].lower() == sent[0].hash
    assert out["used"] == 1


@pytest.mark.parametrize("body, reads, marker", [
    (SERVER_ERROR, 2, "-32000"),
    (READINESS_ERROR, 2 * READINESS_READ, "jsonrpc readiness error"),
], ids=["-32000", "readiness"])
def test_an_unconfirmed_send_carrying_a_retry_marker_is_never_sent_again(
    chain_env, body, reads, marker,  # noqa: F811
):
    """The mechanism that stops the second send, pinned. The action mined;
    the endpoint fails the wait's read AND its re-check with a body whose
    text _send_tx_retry routes on. The TxUnconfirmedError that results
    carries that text in its reason — so the retry-routing marker IS in
    str(e) — and still never routes to a retry: it is a post-broadcast
    type (_POST_BROADCAST), re-raised before any marker is read.
    use_account_item is a single send through _send_tx_retry that lets
    the error out as itself (feed_kami does not retry; use_item_batch
    wraps the error in its batch outcome)."""
    node, game, clock, op = chain_env
    game.inv[21201] = 3
    base = node.pending_count(op)
    _receipts_fail(node, [base], reads, body)

    try:
        out = server.use_account_item(21201, account="testa")
        e = None
    except server.TxUnconfirmedError as raised:
        out, e = None, raised

    sent = _sender_txs(node, op)
    # The transactions first: a retried send shows here as a second nonce.
    assert [t.nonce for t in sent] == [base], (
        [(t.nonce, t.hash) for t in sent], out)
    assert node.latest[op.lower()] == base + 1 and not node.pool[op.lower()]
    assert all(f.times == 0 for f in node.faults)     # wait AND re-check failed
    assert isinstance(e, server.TxUnconfirmedError), out
    assert body["message"] in e.reason, e.reason
    assert marker in str(e), str(e)         # the text a retry would route on
    assert e.tx_hash.lower() == sent[0].hash


def test_a_wait_the_transport_broke_is_unconfirmed_and_the_next_call_resolves_it(
    chain_env,  # noqa: F811
):
    """The transport fails the wait AND its re-check: TxUnconfirmedError
    with the hash and the failure, exactly one transaction, and the next
    call's lane resolution reports it mined."""
    node, game, clock, op = chain_env
    game.inv[11301] = 5
    base = node.pending_count(op)
    _receipts_unreachable(node, [base], 2)          # the wait, the re-check

    with pytest.raises(server.TxUnconfirmedError) as ei:
        server.feed_kami(21, 11301, account="testa")

    e = ei.value
    h = node.by_nonce[op.lower()][base]
    assert e.tx_hash.lower() == h
    assert e.reason == "connection refused by the endpoint"
    assert "is UNCONFIRMED" in str(e) and e.reason in str(e)
    assert [t.nonce for t in _sender_txs(node, op)] == [base]

    game.xp[server._kami_entity_id(5)] = 1_000
    note = server.run_tool("level_up_kami", kami_id=5, account="testa")["notice"]
    assert h in note.lower() and f"has since mined at nonce {base}" in note, note


# ---------------------------------------------------------------------------
# K1 / K3 — the shape found in the live session
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("body, failing_reads", [
    (INTERNAL, 1),                     # the wait fails; its re-check reads
    (INTERNAL, 2),                     # both fail; the pass reads it
    (READINESS_ERROR, 2 * READINESS_READ),
], ids=["wait-only", "wait-and-recheck", "readiness"])
def test_failed_receipt_waits_are_rechecked_and_each_kill_keeps_its_spoils(
    chain_env, monkeypatch, body, failing_reads,  # noqa: F811
):
    """Two kills and the feeds behind them mined and succeeded while the
    endpoint failed their receipt waits. Every row lands with its own
    receipt fields, `landed` counts them, and the third kill's spoils are
    its own — not its own plus the two before it."""
    node, game, clock, op = chain_env
    Kills(node)
    game.inv[11301] = 10
    _no_batched_receipts(monkeypatch)
    base = node.pending_count(op)
    _receipts_fail(node, range(base, base + 4), failing_reads, body)

    out = server.act_sequence(
        [_liq(41), FEED, _liq(42), FEED, _liq(43)], account="testa")

    rows = out["steps"]
    statuses = [r["status"] for r in rows]
    spoils = [r.get("spoils") for r in rows if r["op"] == "liquidate"]
    assert (statuses, spoils) == (["success"] * 5, [700, 650, 600]), (
        statuses, spoils)
    for r in rows:
        assert {"tx_hash", "block", "gas_used", "fee_wei"} <= set(r), r
        assert r["tx_hash"].lower() in node.receipts, r
        assert "reason" not in r, r            # no stale wait failure
    assert out["landed"] == out["sent"] == 5
    assert out["status"] == "complete"
    # Every scripted failure was met: the wait (and, where scripted, its
    # re-check) really failed before the row landed.
    assert all(f.times == 0 for f in node.faults), node.faults
    assert "receipt wait failed" not in out.get("notice", "")


@pytest.mark.parametrize("kind", ["error-body", "transport"])
def test_an_endpoint_that_stays_down_leaves_rows_unconfirmed_with_a_reason(
    chain_env, monkeypatch, kind,  # noqa: F811
):
    """The wait fails, its re-check fails, the end-of-budget pass fails:
    the rows are `unconfirmed` with their hashes and the failure as
    `reason`, never `error`; `landed` excludes them; `notice` names them."""
    node, game, clock, op = chain_env
    game.inv[11301] = 10
    _no_batched_receipts(monkeypatch)
    base = node.pending_count(op)
    down = [base + 1, base + 2]
    if kind == "error-body":
        _receipts_fail(node, down, 10 ** 6, INTERNAL)
        text = "internal error"
    else:
        _receipts_unreachable(node, down, 10 ** 6)
        text = "connection refused by the endpoint"

    out = server.act_sequence(_feeds(4), account="testa")

    rows = out["steps"]
    assert [r["status"] for r in rows] == [
        "success", "unconfirmed", "unconfirmed", "success"], [
        (r["status"], r.get("reason")) for r in rows]
    for i in (1, 2):
        r = rows[i]
        assert r["tx_hash"].lower() == node.by_nonce[op.lower()][base + i]
        assert text in r["reason"] and len(r["reason"]) <= 300, r
        assert "block" not in r and "gas_used" not in r, r
    assert out["landed"] == 2 and out["sent"] == 4
    assert out["status"] == "partial"
    assert out["notice"].startswith(
        "The receipt wait failed for 2 step(s) (steps 1, 2)"), out["notice"]


@pytest.mark.parametrize("exc", [
    OSError("lane state could not be written"),
    KeyError("entry"),
    AttributeError("receipt has no field"),
], ids=lambda e: type(e).__name__)
def test_a_wait_that_fails_for_any_other_reason_is_unconfirmed_not_error(
    seq_env, exc,  # noqa: F811
):
    chain = FakeChain(["ok"] * 3)
    _install_waits(seq_env, chain, ["ok", exc, "ok"])
    out = server.act_sequence(_steps(3), account="testa")
    rows = out["steps"]
    assert [r["status"] for r in rows] == [
        "success", "unconfirmed", "success"], [r["status"] for r in rows]
    assert rows[1]["tx_hash"] == _seq_hash(1)
    assert rows[1]["reason"] == server._err_text(exc)[:300]
    assert out["landed"] == 2 and out["sent"] == 3
    assert out["notice"].startswith(
        "The receipt wait failed for 1 step(s) (step 1)"), out["notice"]


# ---------------------------------------------------------------------------
# K4 (4) — the typed outcomes keep their labels
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("make, expect", [
    (lambda h: server.OnChainRevertError(h, 901, 1001, "kami lacks violence"),
     {"status": "reverted", "block": 901, "gas_used": 1001, "fee_wei": None,
      "reason": "kami lacks violence"}),
    (lambda h: server.TxUnconfirmedError(h, 30),
     {"status": "unconfirmed"}),
    (lambda h: server.TxDroppedError(h, 101, "two null lookups"),
     {"status": "not_sent"}),
    (lambda h: server.TxNonceCollisionError(h, 101, "0x" + "ab" * 32, True),
     {"status": "not_sent", "consumed_by": "0x" + "ab" * 32,
      "signed_by_harness": True}),
], ids=["revert", "unconfirmed", "dropped", "collision"])
def test_the_typed_wait_outcomes_keep_their_labels(seq_env, make, expect):  # noqa: F811
    h = _seq_hash(1)
    chain = FakeChain(["ok"] * 3)
    _install_waits(seq_env, chain, ["ok", make(h), "ok"])
    out = server.act_sequence(_steps(3), account="testa")
    row = out["steps"][1]
    assert {k: row.get(k) for k in expect} == expect, row
    assert row["tx_hash"] == h
    if expect["status"] == "unconfirmed":
        assert "block" not in row and "reason" not in row, row
    assert "receipt wait failed" not in out.get("notice", "")


def test_a_step_that_mines_after_its_wait_gave_up_is_rechecked_and_lands(
    chain_env, monkeypatch,  # noqa: F811
):
    """The fallback's budget-exhausted rows go through the same
    end-of-budget re-check as the batched path's: a step whose
    transaction mines just after its wait gave up lands."""
    node, game, clock, op = chain_env
    game.inv[11301] = 10
    _no_batched_receipts(monkeypatch)
    node.hold_mining = True
    real = server._await_receipt

    def wait_then_mine(*a, **k):
        try:
            return real(*a, **k)
        except server.TxUnconfirmedError:
            node.release_mining()       # it mines just after the wait gave up
            raise

    monkeypatch.setattr(server, "_await_receipt", wait_then_mine)
    out = server.act_sequence(_feeds(2), account="testa")
    rows = out["steps"]
    assert [r["status"] for r in rows] == ["success", "success"], [
        r["status"] for r in rows]
    assert rows[0]["block"] == node.txs[rows[0]["tx_hash"].lower()].mined_block
    assert out["landed"] == 2


# ---------------------------------------------------------------------------
# K2 / K4 (5) — no sequence row can be `error`
# ---------------------------------------------------------------------------

def test_no_exception_class_makes_a_sequence_row_anything_but_a_state(
    seq_env, tmp_path,  # noqa: F811
):
    classes = _exception_classes()
    tried, wrong = 0, []
    for cls in classes:
        exc = _instance(cls)
        if exc is None:
            continue
        tried += 1
        # A fresh lane each time: the scripted chain restarts at nonce 100.
        seq_env.setenv("KAMI_LANE_DIR", str(tmp_path / f"lanes-{tried}"))
        seq_env.setattr(server, "_LANES", {})
        seq_env.setattr(server, "_INFLIGHT", {})
        _install_waits(seq_env, FakeChain(["ok"] * 2), [exc, "ok"])
        out = server.act_sequence(_steps(2), account="testa")
        labels = [r["status"] for r in out["steps"]]
        if not set(labels) <= STATES or labels[0] != "unconfirmed" \
                or out["steps"][0].get("reason") != server._err_text(exc)[:300]:
            wrong.append((cls.__name__, labels))
    assert tried >= 40, tried
    assert wrong == [], wrong


TYPED = {"OnChainRevertError", "TxUnconfirmedError", "TxNotExecutedError",
         "TxNonceCollisionError", "TxDroppedError"}


def _handler_names(handler: ast.ExceptHandler) -> set[str]:
    t = handler.type
    elts = t.elts if isinstance(t, ast.Tuple) else [t] if t is not None else []
    return {e.id if isinstance(e, ast.Name) else getattr(e, "attr", "?")
            for e in elts}


def _status_literals(node) -> list:
    """Literal values given to a `status` key: dict displays and
    subscript assignments, through a conditional expression."""
    def consts(v):
        if isinstance(v, ast.Constant):
            return [v.value]
        if isinstance(v, ast.IfExp):
            return consts(v.body) + consts(v.orelse)
        return []
    out = []
    keys = {k.value for k in getattr(node, "keys", ()) if isinstance(k, ast.Constant)}
    if isinstance(node, ast.Dict) and "steps" not in keys:
        # (A display that also carries `steps` is the call's own result,
        # whose `status` is complete / partial, not a row's.)
        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Constant) and k.value == "status":
                out += consts(v)
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if (isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant)
                    and t.slice.value == "status"):
                out += consts(node.value)
    return out


def test_no_sequence_code_path_can_label_a_row_error():
    """The grep-style guard. In act_sequence and every _seq_ helper:
    `_failed_tx_fields` is called only inside a handler of the typed
    outcomes (its catch-all, `error`, is the per-item word for "no
    transaction known" and is never a sequence state), and every literal
    status is one of the four."""
    fns = [server.act_sequence] + [
        obj for name, obj in vars(server).items()
        if name.startswith("_seq_") and inspect.isfunction(obj)]
    bad = []
    for fn in fns:
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
        parent = {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "_failed_tx_fields"):
                p = node
                while p is not None and not isinstance(p, ast.ExceptHandler):
                    p = parent.get(p)
                names = _handler_names(p) if p is not None else set()
                if not names or not names <= TYPED:
                    bad.append((fn.__name__, node.lineno, sorted(names)))
            for value in _status_literals(node):
                if value not in STATES:
                    bad.append((fn.__name__, node.lineno, value))
    assert len(fns) > 10
    assert bad == [], bad


# ---------------------------------------------------------------------------
# K3b — an unconfirmed kill leaves the next kill without a spoils number
# ---------------------------------------------------------------------------

def test_a_kill_after_an_unconfirmed_kill_by_the_same_killer_has_no_spoils_number(
    chain_env, monkeypatch,  # noqa: F811
):
    """Step 0's kill mined, but nothing could read it: whether its spoils
    are in the killer's bounty is unknown, so step 1's spoils cannot be a
    difference and is null with a decode_error naming step 0 — not 1,350.
    Step 1's own post-value restores the chain for step 2."""
    node, game, clock, op = chain_env
    Kills(node)
    _no_batched_receipts(monkeypatch)
    base = node.pending_count(op)
    _receipts_fail(node, [base], 10 ** 6, INTERNAL)

    out = server.act_sequence([_liq(41), _liq(42), _liq(43)], account="testa")

    a, b, c = out["steps"]
    assert (a["status"], b["status"], c["status"]) == (
        "unconfirmed", "success", "success"), (
        [r["status"] for r in out["steps"]], b.get("spoils"))
    assert b["spoils"] is None, b
    assert "step 0" in b["decode_error"] and "unconfirmed" in b["decode_error"]
    assert b["victim_gross"] == GROSS[42]
    assert c["spoils"] == SPOILS[43], c


# ---------------------------------------------------------------------------
# The surface fingerprint, and the standing text that does not move
# ---------------------------------------------------------------------------

def test_the_surface_fingerprint_and_the_standing_text():
    """4.5.0 changed results, not the surface (4.4.0's `fb65e0db...fac0`,
    71,133). 4.6.0 restores the nine strategy-service tools, so the
    fingerprint and mass are pinned at its values; the handshake's
    standing text stays 4.4.0's byte for byte (957 characters at the
    default KAMI_CALL_BUDGET_S): kami-agent pairs on its sha256."""
    assert server.TOOLS_HASH == (
        "5a31220d88c24ea03f39e55ea3d32e9393870288702bd5d2ab65cdd7f35621a4")
    assert server.registry_mass() == 76_197
    assert server.CALL_BUDGET_S == 90
    assert len(server.STANDING_TEXT) == 957
    assert hashlib.sha256(server.STANDING_TEXT.encode()).hexdigest() == (
        "7c0e7ca6d296bd1c353d88627df7fa60ac6d132b53b88f5daf30a683fdd9ae4b")

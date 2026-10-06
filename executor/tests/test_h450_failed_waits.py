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

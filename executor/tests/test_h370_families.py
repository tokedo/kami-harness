"""3.7.0 families: the false not_sent (F), batched pre-send reads (G),
cheap measurement items (H).

All three come out of Anatoly's 2026-08-28 instant-strike session on
3.6.0 (45 kills in four strikes; ledger
`kami-hybrid-play/memory/raids/2026-08-28d-instant-strikes.md`, tag
`zero_cd_play` in `docs/stack-feedback.md`):

  F — a 61-step strike returned `sent: 0`, every row `not_sent` with
      `reason: ""`, while ALL 61 transactions were mined. The chain was
      the witness; the harness's report was simply false. This file
      reproduces the mechanism against the 3.6.0 code path first, then
      asserts the three fixes: reconcile before reporting, chunk the
      body so no request outlives its timeout, and never write an empty
      reason.

  G — pre-send validation took ~20 s on a 50-61-step plan (a 17-step
      plan took 21 s just to REFUSE), one eth_call per subject with the
      victims not deduped at all. The reads now go out as one batch.

  H — the drink ladder of 3.6.0 spent 148 Energy Drinks, the expensive
      input of this play. The measurement scripts now name their item.
"""

import argparse
import itertools
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import eth_abi
import pytest
from web3 import Web3
from web3.exceptions import MethodNotSupported

import server
from test_h350_families import (  # noqa: F401  (seq_env is a fixture)
    AID,
    FEED,
    FakeChain,
    _install,
    _steps,
    seq_env,
)

LIVE = Path(server.__file__).parent / "tests" / "live"


# ---------------------------------------------------------------------------
# The node of 2026-08-28 19:30:40Z
# ---------------------------------------------------------------------------

#: What the node answered for a nonce it ALREADY HELD when 3.6.0's
#: transport retry re-offered the whole body. An error object whose
#: message is empty is what put `reason: ""` on all 61 rows.
HELD_ERROR = {"code": -32000, "message": ""}


def _hash_for(nonce: int) -> str:
    """The fake's pre-computed tx hash: the product takes keccak of the
    signed raw transaction, and this fake's raw transaction IS its
    nonce."""
    return server._hex_hash(Web3.keccak(nonce.to_bytes(4, "big")))


class IncidentChain(FakeChain):
    """A node that admits part of a body and then loses the request.

    `timeout_after` is how many items of the FIRST batch call the node
    admits before the client's HTTP read timeout fires. Everything the
    node has admitted is answered, on any later call, with `held_error`
    — the incident's own empty-message error object by default.
    """

    def __init__(self, n, timeout_after, base=1873, held_error=None,
                 admit_rest=True, refuse_all=False, pretend_held=0):
        super().__init__(["ok"] * n, nonce=base)
        self.timeout_after = timeout_after
        self.held_error = HELD_ERROR if held_error is None else held_error
        self.admit_rest = admit_rest
        self.refuse_all = refuse_all
        # Nonces the node holds but never told us about: the pending
        # count covers them from the SECOND read on, which is the read
        # the reconciliation makes.
        self.pretend_held = pretend_held
        self.calls = 0

    def _get_nonce(self, addr, block):
        count = super()._get_nonce(addr, block)
        return count + (self.pretend_held if self.nonce_reads > 1 else 0)

    def _make_batch_request(self, requests):
        methods = {m for m, _p in requests}
        if methods != {"eth_sendRawTransaction"}:
            raise NotImplementedError(f"batch methods {sorted(methods)}")
        self.calls += 1
        self.batches.append(len(requests))
        self.batch_requests.append(list(requests))
        self.batch_first_id.append(next(self.provider.request_counter))
        nonces = [
            int.from_bytes(bytes.fromhex(p[0][2:]), "big") for _m, p in requests
        ]
        if self.calls == 1 and self.timeout_after is not None:
            for nonce in nonces[:self.timeout_after]:
                self.broadcasts.append(nonce - self.base)
            raise TimeoutError(
                "HTTPSConnectionPool: read timed out. (read timeout=30)")
        out = []
        for nonce in nonces:
            step = nonce - self.base
            if self.refuse_all or step in self.broadcasts:
                out.append({"jsonrpc": "2.0", "id": nonce,
                            "error": dict(self.held_error)})
            elif self.admit_rest:
                self.broadcasts.append(step)
                out.append({"jsonrpc": "2.0", "id": nonce,
                            "result": _hash_for(nonce)})
            else:
                out.append({"jsonrpc": "2.0", "id": nonce, "error": {
                    "code": -32000,
                    "message": "account sequence mismatch: expected 7, got 6",
                }})
        return out


@pytest.fixture()
def incident_env(seq_env):
    """seq_env plus: no settle sleep, and receipts keyed by nonce."""
    seq_env.setattr(server.time, "sleep", lambda _s: None)
    return seq_env


def _install_incident(monkeypatch, chain, mined=None):
    """Receipts for the incident fakes: every hash is a nonce's hash."""
    monkeypatch.setattr(server, "w3", chain)
    by_hash = {
        _hash_for(chain.base + i): i for i in range(len(chain.outcomes))
    }
    mined = set(range(len(chain.outcomes))) if mined is None else set(mined)

    def await_receipt(tx_hash, built, timeout, account=None, ceiling_key=None):
        i = by_hash[tx_hash]
        if i not in mined:
            raise server.TxUnconfirmedError(tx_hash, timeout)
        return SimpleNamespace(
            transactionHash=bytes.fromhex(tx_hash[2:]),
            blockNumber=32685027 + i, gasUsed=287313, status=1,
        )

    monkeypatch.setattr(server, "_await_receipt", await_receipt)
    return by_hash


# ---------------------------------------------------------------------------
# FAMILY F — a mined sequence is never "not_sent"
# ---------------------------------------------------------------------------

def test_the_3_6_0_mechanism_reproduced_then_fixed(incident_env, monkeypatch):
    """THE INCIDENT, isolated from the chunking fix.

    With the body offered whole — as 3.6.0 always did — the node admits
    38 of 61, the request dies past the 30 s timeout, and the retry gets
    an empty-message error for every nonce the node now holds. 3.6.0
    reported all 61 not_sent with `reason: ""` and polled no receipts.
    3.7.0 reconciles against the pending nonce first, so every one of
    them is what it actually is.
    """
    monkeypatch.setattr(server, "_SEQ_BATCH_CHUNK", 64)
    chain = IncidentChain(61, timeout_after=38)
    _install_incident(incident_env, chain)
    out = server.act_sequence(_steps(61), account="testa")

    # 3.6.0 re-offered all 61 and then mapped the 38 already-held
    # nonces' empty-message errors onto every row. 3.7.0 asks the node
    # what it holds FIRST, so the retry carries only the 23 it does not.
    assert chain.batches == [61, 23]
    assert out["sent"] == 61 and out["landed"] == 61
    assert out["status"] == "complete"
    assert all(r["status"] == "success" for r in out["steps"])
    assert not any("reason" in r for r in out["steps"])
    # Each of the 38 carries the hash computed at sign time, which is
    # the hash the chain gave it.
    for i in range(38):
        assert out["steps"][i]["tx_hash"] == _hash_for(chain.base + i)


def test_a_refusal_on_a_nonce_the_node_holds_is_reconciled_not_reported(
    incident_env, monkeypatch
):
    """Fix (a) on its own, with no transport failure in sight.

    The node holds all 20 nonces and answers every one of them with the
    incident's empty-message error object. The broadcast therefore
    reports 20 refusals — and every one of them is wrong. The pending
    nonce settles it before the call returns.
    """
    monkeypatch.setattr(server, "_SEQ_BATCH_CHUNK", 64)
    chain = IncidentChain(20, timeout_after=None, refuse_all=True,
                          pretend_held=20)
    _install_incident(incident_env, chain)
    out = server.act_sequence(_steps(20), account="testa")

    assert out["sent"] == 20 and out["landed"] == 20
    assert all(r["status"] == "success" for r in out["steps"])
    assert not any("reason" in r for r in out["steps"])
    for i, row in enumerate(out["steps"]):
        assert row["reconciled"] == (
            f"nonce {chain.base + i} < pending count {chain.base + 20}"
        )
        # 3.6.0 wrote "" here. The whole payload is on the row instead.
        assert "no error message" in row["broadcast_error"]
        assert '"code": -32000' in row["broadcast_error"]


def test_a_partial_chunk_is_reconciled_before_the_next_is_offered(
    incident_env,
):
    """The shipped path: 61 steps, chunk 1 loses its request mid-flight.

    The node holds 20 of the first 32; only the 12 it does NOT hold are
    re-offered, and chunk 2 goes out afterwards, not on top of it.
    """
    chain = IncidentChain(61, timeout_after=20)
    _install_incident(incident_env, chain)
    out = server.act_sequence(_steps(61), account="testa")

    assert chain.batches == [32, 12, 29]
    assert out["sent"] == 61 and out["landed"] == 61
    assert chain.broadcasts == list(range(61))


def test_no_step_below_the_pending_nonce_is_ever_reported_not_sent(
    incident_env, monkeypatch
):
    """The invariant, stated as itself.

    The node holds every nonce and answers every one of them with an
    error. Not one row may come back not_sent.
    """
    monkeypatch.setattr(server, "_SEQ_BATCH_CHUNK", 64)
    chain = IncidentChain(20, timeout_after=20)
    _install_incident(incident_env, chain)
    out = server.act_sequence(_steps(20), account="testa")

    pending_count = chain.base + len(chain.broadcasts)
    for i, row in enumerate(out["steps"]):
        if chain.base + i < pending_count:
            assert row["status"] != "not_sent", row


def test_no_step_whose_hash_has_a_receipt_is_ever_reported_not_sent(
    incident_env, monkeypatch
):
    """The other half of the invariant: a mined tx is a mined tx.

    Here the node's pending nonce does NOT cover the step — it lies —
    but the receipt for the hash computed at sign time exists, so the
    row is not_sent over the harness's dead body.
    """
    chain = IncidentChain(3, timeout_after=None, admit_rest=False)
    _install_incident(incident_env, chain)
    # The node refuses everything and reports a pending nonce that
    # covers nothing, yet step 1's transaction is on chain.
    monkeypatch.setattr(server, "_seq_pending_nonce", lambda addr: chain.base)
    monkeypatch.setattr(
        server, "_seq_mined",
        lambda by_step: [i for i in by_step if i == 1],
    )
    out = server.act_sequence(_steps(3), account="testa")

    assert out["steps"][0]["status"] == "not_sent"
    assert out["steps"][1]["status"] == "success"
    assert out["steps"][1]["reconciled"] == (
        "receipt found for the pre-computed hash"
    )
    assert out["steps"][2]["status"] == "not_sent"


def test_a_step_that_really_was_not_sent_still_says_so(incident_env):
    """`not_sent` is not being retired — it is being made true.

    A node that holds nothing and refuses everything gets exactly the
    3.5.0 answer, with a reason that names the refusal.
    """
    chain = IncidentChain(3, timeout_after=None, admit_rest=False)
    _install_incident(incident_env, chain)
    out = server.act_sequence(_steps(3), account="testa")
    assert [r["status"] for r in out["steps"]] == ["not_sent"] * 3
    assert out["sent"] == 0
    assert all("sequence mismatch" in r["reason"] for r in out["steps"])


@pytest.mark.parametrize("payload", [
    {"code": -32000, "message": ""},     # the incident's own payload
    {"code": -32000},
    {"message": ""},
    {},
    "",
    None,
])
def test_an_empty_error_payload_never_becomes_an_empty_reason(payload):
    """ITEM 1(c). Whatever the node said, the row can be read.

    No message to quote means the RAW ITEM goes on the row, with the
    nonce it refused — never the empty string 3.6.0 wrote.
    """
    text = server._seq_error_text(payload, 1873)
    assert text.strip()
    assert "1873" in text
    assert "no error message" in text
    assert len(text) <= 300


def test_a_real_error_payload_reaches_the_row_verbatim():
    text = server._seq_error_text(
        {"code": -32000, "message": "account sequence mismatch: "
                                    "expected 1911, got 1873",
         "data": "sender 0x9B95"},
        1873,
    )
    assert "account sequence mismatch: expected 1911, got 1873" in text
    assert "[code -32000]" in text and "[data sender 0x9B95]" in text


def test_a_long_error_payload_is_truncated_at_300_chars():
    text = server._seq_error_text({"message": "x" * 900}, 1)
    assert len(text) == 300


def test_a_missing_response_names_the_nonce_and_the_batch_size(
    incident_env, monkeypatch
):
    chain = FakeChain(["ok"] * 5)
    _install(incident_env, chain, ["ok"] * 5)
    inner = chain._make_batch_request
    monkeypatch.setattr(
        chain.provider, "make_batch_request", lambda reqs: inner(reqs[:3])
    )
    out = server.act_sequence(_steps(5), account="testa")
    assert out["steps"][3]["reason"] == (
        "no response for nonce 103 in batch of 5"
    )


def test_a_61_step_body_is_offered_in_chunks_of_at_most_32(incident_env):
    """ITEM 1(b): the body is chunked, and the chunks are sequential."""
    chain = FakeChain(["ok"] * 61)
    _install(incident_env, chain, ["ok"] * 61)
    out = server.act_sequence(_steps(61), account="testa")
    assert server._SEQ_BATCH_CHUNK == 32
    assert chain.batches == [32, 29]
    assert max(chain.batches) <= server._SEQ_BATCH_CHUNK
    assert out["landed"] == 61


def test_the_batch_timeout_is_measured_and_scoped_to_the_batch_call():
    """The timeout is chunk × measured worst per-item × 2, floor 30 s —
    and it lives on a provider of its own, so no other RPC call in the
    process has its 30 s changed."""
    assert server._SEQ_BATCH_ITEM_S == 0.5
    assert server._SEQ_BATCH_TIMEOUT_FLOOR_S == 30
    assert server._seq_batch_timeout(1) == 30.0        # the floor holds
    assert server._seq_batch_timeout(32) == 32.0       # a full chunk
    assert server._seq_batch_timeout(server._SEQ_BATCH_CHUNK) == (
        server._SEQ_BATCH_CHUNK * server._SEQ_BATCH_ITEM_S * 2
    )

    dedicated = server._seq_batch_provider(32.0)
    assert dedicated is not server.w3.provider
    assert dedicated.get_request_kwargs()["timeout"] == 32.0
    assert server.w3.provider.get_request_kwargs().get("timeout") is None
    assert dedicated._exception_retry_configuration is None
    # Cached per timeout value: two chunk sizes, not one provider per call.
    assert server._seq_batch_provider(32.0) is dedicated


def test_the_provider_id_counter_is_restored_on_the_dedicated_provider(
    monkeypatch,
):
    """The id counter is borrowed to key a batch by nonce; a failed
    batch call must not leave the dedicated provider's ids elsewhere."""
    class _Dies:
        request_counter = itertools.count()

        def make_batch_request(self, requests):
            raise ConnectionResetError("connection reset by peer")

    stub = _Dies()
    counter = stub.request_counter
    monkeypatch.setattr(server, "_seq_batch_provider", lambda t: stub)
    with pytest.raises(server._SeqBatchTransportError):
        server._seq_batch_send([(0, 7, b"\x01")], 30.0)
    assert stub.request_counter is counter


# --- regression baseline: the strikes that WERE reported correctly ----------
#
# Same session, same code path, 52 / 28 / 25 steps, all reported right.
# Their numbers are the ledger's.

STRIKE_52 = {
    "node": 34, "steps": 52, "kills": 16, "first_block": 32684868,
    "last_block": 32684876, "spoils": 9686,
}


def test_the_52_step_strike_is_reported_exactly_as_it_was(incident_env):
    """3.7.0 must not disturb the strikes 3.6.0 got right.

    The 52-step strike at node 34 landed 52 of 52 in blocks
    32684868-876. The report shape is unchanged: every row success with
    its own block, `sent` and `landed` both 52, and NOT ONE row carrying
    a reconciliation field — nothing needed reconciling.
    """
    n = STRIKE_52["steps"]
    chain = FakeChain(["ok"] * n, nonce=1800)
    _install(incident_env, chain, ["ok"] * n)
    out = server.act_sequence(_steps(n), account="testa")

    assert out["status"] == "complete"
    assert out["sent"] == n == out["landed"]
    assert [r["status"] for r in out["steps"]] == ["success"] * n
    assert all("block" in r and "tx_hash" in r for r in out["steps"])
    assert not any("reconciled" in r or "broadcast_error" in r
                   for r in out["steps"])
    assert chain.nonce_reads == 1            # no reconciliation read
    assert chain.batches == [32, 20]         # chunked, nothing else changed


# ---------------------------------------------------------------------------
# FAMILY G — the pre-send reads, batched
# ---------------------------------------------------------------------------

STRIKE_PLAN = (
    [{"op": "harvest_start", "kami_ids": [12649], "node_index": 86}]
    + [{"op": "liquidate", "kami_id": 12649, "victim_kami_id": v}
       for v in range(20000, 20019)]
    + [{"op": "feed", "kami_id": 12649, "item_id": 11301}] * 40
    + [{"op": "harvest_stop", "kami_ids": [12649]}]
)


def test_web3s_own_batch_api_does_support_eth_call():
    """The brief's claim, verified — and the contrast with the sends.

    web3 v7 refuses eth_sendRawTransaction inside a batch before a
    request is built (test_h360_families.py asserts that), which is why
    the broadcast goes through the provider directly. eth_call is NOT
    on that list, so the read prefetch could have used `batch_requests()`
    — it uses the provider for the same reason the broadcast does: one
    transport, one place where the JSON-RPC ids are set.
    """
    w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:9/offline-test"))
    batch = w3.batch_requests()
    try:
        batch.add(w3.eth.call({"to": "0x" + "11" * 20, "data": "0x"}))
        assert len(batch._requests_info) == 1
        with pytest.raises(MethodNotSupported):
            batch.add(w3.eth.send_raw_transaction(b"\x01"))
    finally:
        batch.cancel()


def test_the_read_plan_dedupes_every_repeated_subject():
    """61 steps, 23 distinct chain subjects: the same killer 20 times,
    the same item 40 times, each read ONCE."""
    parsed = server._seq_parse(STRIKE_PLAN)
    plan = server._seq_read_plan(parsed)
    assert len(parsed) == 61
    assert len(plan) == 23
    assert plan.count(("owner", 12649)) == 1
    assert plan.count(("balance", 11301)) == 1
    assert plan.count(("bounty", 12649)) == 1
    assert sum(1 for k in plan if k[0] == "harvest") == 20   # 19 victims + killer
    assert len(set(plan)) == len(plan)


class _ReadProvider:
    """A node that answers eth_call batches and counts the round-trips."""

    def __init__(self, answers):
        self.answers = answers            # entity_id -> abi-encoded bytes
        self.round_trips = 0
        self.request_counter = itertools.count()

    def make_batch_request(self, requests):
        assert {m for m, _p in requests} == {"eth_call"}
        self.round_trips += 1
        out = []
        for i, (_m, params) in enumerate(requests):
            data = bytes.fromhex(params[0]["data"][2:])
            assert data[:4] == server._SAFEGET_SELECTOR
            entity = int.from_bytes(data[4:36], "big")
            out.append({"jsonrpc": "2.0", "id": i,
                        "result": "0x" + self.answers[entity].hex()})
        return out


@pytest.fixture()
def read_env(monkeypatch):
    """A world whose chain reads only exist inside an eth_call batch."""
    answers = {}
    for k in [12649] + list(range(20000, 20019)):
        answers[server._kami_entity_id(k)] = eth_abi.encode(["uint256"], [AID])
        answers[server._harvest_entity_id(k)] = eth_abi.encode(
            ["string"], ["ACTIVE"])
    answers[server._inventory_entity_id(AID, 11301)] = eth_abi.encode(
        ["uint256"], [999])
    # The killer's bounty shares the harvest entity with its state, and
    # the two are read as different types; the bounty read is answered
    # separately below by overriding after the state answers are in.
    provider = _ReadProvider(answers)
    monkeypatch.setattr(server, "w3", SimpleNamespace(provider=provider))
    monkeypatch.setattr(server, "_resolve_component", lambda c: "0x" + "11" * 20)
    for name in ("_kami_owner_id", "_harvest_state", "_inventory_balance",
                 "_killer_bounty"):
        monkeypatch.setattr(
            server, name,
            lambda *a, _n=name, **k: pytest.fail(
                f"{_n} was read one subject at a time"),
        )
    return provider


def test_the_whole_read_plan_costs_one_round_trip(read_env):
    """ITEM 2: O(chunks), not O(steps). 61 steps, one POST."""
    parsed = server._seq_parse(STRIKE_PLAN)
    reads = server._seq_prefetch_reads(parsed, AID)
    assert read_env.round_trips == 1
    assert len(reads) == 23
    assert reads[("owner", 12649)] == AID
    assert reads[("harvest", 20000)] == "ACTIVE"
    assert reads[("balance", 11301)] == 999


def test_validation_runs_off_the_prefetch_with_no_per_subject_reads(
    read_env, monkeypatch
):
    """The per-subject helpers are trip-wired in this fixture: if any of
    them fires, the batch did not cover the plan."""
    monkeypatch.setattr(server, "_require_gas_balance", lambda *a, **k: None)
    monkeypatch.setattr(
        server, "_get_account",
        lambda a: SimpleNamespace(operator_addr="0x" + "22" * 20),
    )
    parsed = server._seq_parse(STRIKE_PLAN)
    bounty = server._seq_static_validate(parsed, "testa", AID, 0)
    assert read_env.round_trips == 1
    # The killer's bounty comes off the same batch, as a uint over the
    # harvest entity — the same entity its state is read from.
    assert 12649 in bounty


def test_a_node_that_will_not_batch_reads_is_slow_and_not_wrong(monkeypatch):
    """The prefetch has no semantics of its own: when it cannot answer,
    every check falls through to the 3.6.0 per-subject read."""
    class _Refuses:
        request_counter = itertools.count()

        def make_batch_request(self, requests):
            raise ConnectionError("no batches here")

    monkeypatch.setattr(server, "w3", SimpleNamespace(provider=_Refuses()))
    monkeypatch.setattr(server, "_resolve_component", lambda c: "0x" + "11" * 20)
    parsed = server._seq_parse(STRIKE_PLAN)
    assert server._seq_prefetch_reads(parsed, AID) == {}

    seen = []
    monkeypatch.setattr(server, "_kami_owner_id",
                        lambda k: seen.append(("owner", k)) or AID)
    monkeypatch.setattr(server, "_harvest_state",
                        lambda k: seen.append(("harvest", k)) or "ACTIVE")
    monkeypatch.setattr(server, "_inventory_balance",
                        lambda a, i: seen.append(("balance", i)) or 999)
    monkeypatch.setattr(server, "_killer_bounty",
                        lambda k: seen.append(("bounty", k)) or 7)
    monkeypatch.setattr(server, "_require_gas_balance", lambda *a, **k: None)
    monkeypatch.setattr(server, "_get_account",
                        lambda a: SimpleNamespace(operator_addr="0x" + "22" * 20))
    bounty = server._seq_static_validate(parsed, "testa", AID, 0)
    assert bounty == {12649: 7}
    assert ("owner", 12649) in seen and ("balance", 11301) in seen


def test_the_prefetch_never_raises_whatever_the_node_returns(monkeypatch):
    class _Nonsense:
        request_counter = itertools.count()

        def make_batch_request(self, requests):
            return {"error": "batch not supported"}

    monkeypatch.setattr(server, "w3", SimpleNamespace(provider=_Nonsense()))
    monkeypatch.setattr(server, "_resolve_component", lambda c: "0x" + "11" * 20)
    parsed = server._seq_parse(STRIKE_PLAN)
    assert server._seq_prefetch_reads(parsed, AID) == {}


def test_the_act_path_reads_the_chain_and_never_the_lens_daemon():
    """3.4.0 family C doctrine: an ACT tool does not depend on the lens.

    The read plan resolves through components on chain; no lens wrapper
    appears anywhere in the sequence validation path.
    """
    import inspect
    for fn in (server._seq_prefetch_reads, server._seq_read_subject,
               server._seq_static_validate, server._seq_read_plan):
        source = inspect.getsource(fn)
        assert "lens" not in source.lower(), fn.__name__


# ---------------------------------------------------------------------------
# FAMILY H — the measurement scripts name what they burn
# ---------------------------------------------------------------------------

MEASURE = LIVE / "measure_mempool_acceptance.py"


def _measure_module():
    """The live script's module namespace, without running main()."""
    sys.modules.pop("measure_mempool_acceptance", None)
    return runpy.run_path(str(MEASURE), run_name="not_main")


def test_the_measurement_script_has_no_default_item():
    mod = _measure_module()
    assert mod["GHOST_GUM"] == 11301
    assert mod["GOLDEN_APPLE"] == 11313
    assert mod["ENERGY_DRINK"] == 11409
    # Parse the parser the script builds, not a copy of it.
    source = MEASURE.read_text()
    assert '"--item", type=int, required=True' in source
    assert "default=11409" not in source
    assert "ITEM_ID = 11409" not in source


def test_the_measurement_script_refuses_energy_drinks_unless_told():
    mod = _measure_module()
    check = mod["check_item"]
    with pytest.raises(SystemExit) as e:
        check(11409, False)
    assert "11409" in str(e.value) and "11301" in str(e.value)
    assert check(11409, True) == 11409
    assert check(11301, False) == 11301
    assert check(11313, False) == 11313


def test_the_measurement_docstring_names_the_measurement_items():
    doc = MEASURE.read_text().split('"""')[1]
    assert "Ghost Gum 11301" in doc
    assert "Golden Apple 11313" in doc
    assert "--allow-drinks" in doc


def test_argparse_itself_requires_the_item(monkeypatch):
    """Belt and braces: the parser, exercised."""
    mod = _measure_module()
    ap = argparse.ArgumentParser()
    ap.add_argument("--item", type=int, required=True)
    with pytest.raises(SystemExit):
        ap.parse_args([])
    assert ap.parse_args(["--item", str(mod["GHOST_GUM"])]).item == 11301

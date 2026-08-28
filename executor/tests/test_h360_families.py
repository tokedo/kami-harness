"""3.6.0 families: batch broadcast (D) and the receipt-side kill (E).

Both families exist because of what Anatoly's fifth and sixth play
sessions on 3.5.0 measured, and both are checked against the chain
rather than against a hand-built log:

  D — 3.5.0 broadcast a pre-signed tail one HTTP call at a time, which
      paced a 16-step burst at ~0.42 s/step against a 0.27 s bare
      round-trip. 3.6.0 sends the whole tail in ONE JSON-RPC batch whose
      ids are the nonces. The 3.5.0 rejection semantics have to survive
      that transport unchanged — test_h350_families.py asserts them, and
      this file asserts the transport itself.

  E — 3.5.0 read the killer's post-kill HP and cooldown LIVE at decode
      time, so every kill row of a burst carried the burst's last state.
      3.6.0 takes both from the kill receipt's own component writes. The
      fixtures are the real receipts of the burst that exposed it.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from web3 import Web3
from web3.exceptions import MethodNotSupported

import server
from test_h350_families import (  # noqa: F401  (seq_env is a fixture)
    FEED,
    FakeChain,
    KILLER,
    _install,
    _steps,
    entity_ids,
    seq_env,
)

SERIES = Path(__file__).parent / "fixtures" / "liquidation_32677500"
BURST = Path(__file__).parent / "fixtures" / "burst_32682485"


def _load(directory: Path, block: int):
    raw = json.loads((directory / f"{block}.json").read_text())
    return SimpleNamespace(
        logs=[
            SimpleNamespace(
                topics=[bytes.fromhex(t[2:]) for t in lg["topics"]],
                data=bytes.fromhex(lg["data"][2:]),
            )
            for lg in raw["logs"]
        ],
        blockNumber=raw["block"], status=raw["status"], gasUsed=raw["gas_used"],
    )


# ---------------------------------------------------------------------------
# FAMILY D — batch broadcast
# ---------------------------------------------------------------------------

def test_the_whole_tail_goes_out_in_one_round_trip(seq_env):
    """The point of the change: 16 steps, ONE POST, not 16."""
    outcomes = ["ok"] * 16
    chain = FakeChain(outcomes)
    _install(seq_env, chain, outcomes)
    out = server.act_sequence(_steps(16), account="testa")
    assert out["landed"] == 16
    assert chain.batches == [16]
    assert chain.broadcasts == list(range(16))


def test_the_batch_ids_are_the_nonces(seq_env):
    """Mapping is BY NONCE, so a reordered or dropped response cannot
    shift the results onto the wrong steps."""
    outcomes = ["ok"] * 4
    chain = FakeChain(outcomes)
    _install(seq_env, chain, outcomes)
    server.act_sequence(_steps(4), account="testa")

    requests = chain.batch_requests[0]
    assert [m for m, _p in requests] == ["eth_sendRawTransaction"] * 4
    # The ids web3 will stamp start at the tail's first nonce, so id ==
    # nonce for every item (the nonces are consecutive by construction).
    assert chain.batch_first_id == [chain.base]
    # And the fake signs each step as its own nonce, in step order.
    assert [int(p[0], 16) for _m, p in requests] == [
        chain.base + i for i in range(4)
    ]


def test_responses_returned_out_of_order_still_land_on_their_own_steps(
    seq_env, monkeypatch
):
    outcomes = ["ok"] * 5
    chain = FakeChain(outcomes)
    _install(seq_env, chain, outcomes)
    inner = chain._make_batch_request
    monkeypatch.setattr(
        chain.provider, "make_batch_request",
        lambda reqs: list(reversed(inner(reqs))),
    )
    out = server.act_sequence(_steps(5), account="testa")
    assert [r["status"] for r in out["steps"]] == ["success"] * 5
    # Each row's hash is its OWN: the fake's hash byte is the step index.
    assert [r["tx_hash"][:4] for r in out["steps"]] == [
        f"0x{i:02x}" for i in range(5)
    ]


def test_a_nonce_missing_from_the_response_is_not_sent_not_guessed(
    seq_env, monkeypatch
):
    """A node that answers 4 of 5 items must not silently shift the
    fifth's result onto the fourth step."""
    outcomes = ["ok"] * 5
    chain = FakeChain(outcomes)
    _install(seq_env, chain, outcomes)
    inner = chain._make_batch_request
    # The node ADMITS three and answers three: nonces 4 and 5 were never
    # taken, so the pending nonce reconciliation (3.7.0) leaves them
    # not_sent — which is the point of the test.
    monkeypatch.setattr(
        chain.provider, "make_batch_request", lambda reqs: inner(reqs[:3])
    )
    out = server.act_sequence(_steps(5), account="testa")
    statuses = [r["status"] for r in out["steps"]]
    assert statuses == ["success", "success", "success", "not_sent", "not_sent"]
    assert "no response for nonce" in out["steps"][3]["reason"]
    assert "in batch of 5" in out["steps"][3]["reason"]


def test_a_transport_failure_is_retried_once_as_a_batch(seq_env):
    outcomes = ["ok"] * 3
    chain = FakeChain(outcomes, batch_transport_failures=1)
    _install(seq_env, chain, outcomes)
    out = server.act_sequence(_steps(3), account="testa")
    assert out["landed"] == 3
    assert chain.batches == [3, 3]                 # POSTed twice
    assert all("broadcast" not in r for r in out["steps"])


def test_two_transport_failures_fall_back_to_serial_and_say_so(seq_env):
    """Slow beats a lost sequence — and the row records which it was."""
    outcomes = ["ok"] * 3
    chain = FakeChain(outcomes, batch_transport_failures=2)
    _install(seq_env, chain, outcomes)
    out = server.act_sequence(_steps(3), account="testa")
    assert out["landed"] == 3
    assert chain.batches == [3, 3]
    assert chain.broadcasts == [0, 1, 2]           # one send at a time
    assert [r["broadcast"] for r in out["steps"]] == ["serial"] * 3


def test_a_serial_fallback_still_stops_the_tail_at_a_refusal(seq_env):
    outcomes = ["ok", "reject", "ok"]
    chain = FakeChain(outcomes, reject_once=False, batch_transport_failures=2)
    _install(seq_env, chain, ["ok", "ok", "ok"])
    out = server.act_sequence(_steps(3), account="testa")
    assert [r["status"] for r in out["steps"]] == [
        "success", "not_sent", "not_sent"
    ]


def test_a_rejected_tail_is_re_broadcast_as_a_second_batch(seq_env):
    outcomes = ["ok", "reject", "ok"]
    chain = FakeChain(outcomes, reject_once=True)
    _install(seq_env, chain, ["ok", "ok", "ok"])
    out = server.act_sequence(_steps(3), account="testa")
    assert out["landed"] == 3
    assert chain.batches == [3, 2]      # whole sequence, then the tail
    # 1 at head + 1 reconciliation before the resend + 1 to re-sign.
    assert chain.nonce_reads == 3


def test_web3s_own_batch_api_cannot_carry_this_and_that_is_why():
    """The reason the provider's make_batch_request is used directly.

    web3 v7 lists eth_sendRawTransaction in
    RPC_METHODS_UNSUPPORTED_DURING_BATCH and refuses it in the Method
    descriptor, before any request is built and whatever the endpoint
    supports. If a web3 upgrade ever lifts that, this test fails and the
    transport can be reconsidered on its merits.
    """
    w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:9/offline-test"))
    batch = w3.batch_requests()
    try:
        with pytest.raises(MethodNotSupported):
            batch.add(w3.eth.send_raw_transaction(b"\x01"))
    finally:
        batch.cancel()


def test_the_provider_id_counter_is_restored_after_a_batch(seq_env):
    """The id counter is borrowed to key the batch by nonce; a tool call
    must not leave the provider's request ids somewhere else."""
    outcomes = ["ok"] * 2
    chain = FakeChain(outcomes)
    _install(seq_env, chain, outcomes)
    counter = chain.provider.request_counter
    server.act_sequence(_steps(2), account="testa")
    assert chain.provider.request_counter is counter


# ---------------------------------------------------------------------------
# FAMILY E — the killer's own state, from the receipt
# ---------------------------------------------------------------------------

SERIES_INDEX = json.loads((SERIES / "index.json").read_text())
BURST_INDEX = json.loads((BURST / "index.json").read_text())


@pytest.fixture()
def burst_entities(monkeypatch):
    """Bind the burst's recorded harvest entities to synthetic kami ids.

    The killer stays the real 12649 so its KAMI entity — where the
    health and Time.Next writes land — is the one the decoder derives.
    """
    killer_entity = int(BURST_INDEX["killer_harvest_entity"])
    victims = {
        int(b): int(e)
        for b, e in BURST_INDEX["victim_harvest_entities"].items()
    }

    def harvest_entity(kami_id):
        return killer_entity if kami_id == KILLER else victims[kami_id]

    monkeypatch.setattr(server, "_harvest_entity_id", harvest_entity)
    return victims


@pytest.mark.parametrize("block", sorted(SERIES_INDEX["expected"]))
def test_series_rows_decode_their_own_hp_and_cooldown(block, entity_ids):
    expected = SERIES_INDEX["expected"][block]
    out = server._decode_kill(
        _load(SERIES, int(block)), int(block), KILLER, expected["pre"]
    )
    assert out["cooldown_until"] == expected["cooldown_until"]
    assert out["attacker_hp_after"] == expected["attacker_hp_after"]
    assert "decode_error" not in out


def test_the_burst_rows_carry_FOUR_DIFFERENT_cooldowns(burst_entities):
    """The regression itself. 3.5.0 reported one live-read value on
    every row of this burst; the receipts hold four."""
    seen, pre = [], 0
    for block in sorted(BURST_INDEX["expected"]):
        expected = BURST_INDEX["expected"][block]
        out = server._decode_kill(
            _load(BURST, int(block)), int(block), KILLER, pre
        )
        assert out["cooldown_until"] == expected["cooldown_until"]
        assert out["spoils"] == expected["spoils"]
        assert "decode_error" not in out
        seen.append(out["cooldown_until"])
        pre = out["killer_bounty_after"]

    assert len(set(seen)) == 4
    # 3.5.0's single value was the LAST row's, stamped onto all of them.
    stale = BURST_INDEX["live_read_reported_by_350"]
    assert seen.count(stale) == 1 and seen[-1] == stale
    # The chain closes: the burst banked 2329.
    assert pre == 2329


def test_the_last_kill_of_the_burst_is_the_proof(burst_entities):
    """The pinned RPC is not archival, so the receipt-side value cannot
    be checked against a read at that height. It is checked where a live
    read IS correct: the last kill of a burst, with nothing landing
    after it. 3.5.0's live read there returned 1787938453 and the
    receipt says the same number.
    """
    block = max(int(b) for b in BURST_INDEX["expected"])
    expected = BURST_INDEX["expected"][str(block)]
    out = server._decode_kill(
        _load(BURST, block), block, KILLER, expected["pre"]
    )
    assert out["cooldown_until"] == BURST_INDEX["live_read_reported_by_350"]
    assert out["attacker_hp_after"] == expected["attacker_hp_after"] == 0


def test_no_live_read_happens_inside_a_decode(entity_ids, monkeypatch):
    """P4's whole point: a decode reads the receipt and nothing else."""
    def boom(*a, **k):
        raise AssertionError("a live read was made inside _decode_kill")

    monkeypatch.setattr(server, "_kami_last_synced_hp", boom)
    monkeypatch.setattr(server, "_resolve_component", boom)
    out = server._decode_kill(_load(SERIES, 32677552), 32677552, KILLER, 2566)
    assert out["cooldown_until"] == 1787926295
    assert out["spoils"] == 651


def _without(component_id, block=32677552, directory=SERIES):
    receipt = _load(directory, block)
    receipt.logs = [
        lg for lg in receipt.logs
        if int.from_bytes(bytes(lg.topics[1]), "big") != component_id
    ]
    return receipt


def test_a_missing_health_write_is_null_and_names_the_component(entity_ids):
    out = server._decode_kill(
        _without(server._HEALTH_COMPONENT_ID), 32677552, KILLER, 2566
    )
    assert out["attacker_hp_after"] is None
    assert "component.stat.health" in out["decode_error"]
    # The rest of the row is unaffected.
    assert out["cooldown_until"] == 1787926295
    assert out["spoils"] == 651


def test_a_missing_cooldown_write_is_null_and_names_the_component(entity_ids):
    out = server._decode_kill(
        _without(server._TIME_NEXT_COMPONENT_ID), 32677552, KILLER, 2566
    )
    assert out["cooldown_until"] is None
    assert "component.Time.Next" in out["decode_error"]
    assert out["attacker_hp_after"] == 0


def test_the_stat_word_is_four_signed_64_bit_fields_and_sync_is_last():
    """The packing is not an abi-encoded struct, and shift is signed."""
    def word(base, shift, boost, sync):
        return b"".join(
            v.to_bytes(8, "big", signed=True)
            for v in (base, shift, boost, sync)
        )

    assert server._stat_sync_from_word(word(120, 0, 0, 0)) == 0
    assert server._stat_sync_from_word(word(100, -150, 30, 91)) == 91
    assert server._stat_sync_from_word(word(0, 0, 0, -4)) == -4
    assert server._stat_sync_from_word(b"\x00" * 31) is None


def test_component_ids_are_the_keccak_of_the_registered_name():
    """Same derivation musu.py uses for component.value, so a rename
    upstream fails loudly here rather than silently reading nothing."""
    assert server._HEALTH_COMPONENT_ID == int.from_bytes(
        Web3.keccak(text="component.stat.health"), "big"
    )
    assert server._TIME_NEXT_COMPONENT_ID == int.from_bytes(
        Web3.keccak(text="component.Time.Next"), "big"
    )
    # And they are the ids the recorded receipts actually carry.
    receipt = _load(SERIES, 32677500)
    carried = {int.from_bytes(bytes(lg.topics[1]), "big") for lg in receipt.logs}
    assert server._HEALTH_COMPONENT_ID in carried
    assert server._TIME_NEXT_COMPONENT_ID in carried
    assert server._VALUE_COMPONENT_ID in carried

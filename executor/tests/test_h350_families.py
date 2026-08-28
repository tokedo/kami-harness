"""3.5.0 families: act_sequence (A), the decoded kill (B), lens_skills (C).

The act_sequence tests drive a scripted fake chain: each step is given an
outcome (accepted/rejected at broadcast; success/revert/timeout at the
receipt) and the test asserts that the per-step terminal states come back
exactly as scripted and never conflated (P4). The decode tests run
against RECORDED receipts from the 2026-08-28 shrike sweep — the same
four liquidations the gate-1 proof used — so the decoder is checked
against the chain rather than against a hand-built log.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import server

FIXTURES = Path(__file__).parent / "fixtures" / "liquidation_32677500"
KILLER = 12649


# ---------------------------------------------------------------------------
# FAMILY B — decoded kill, against recorded receipts
# ---------------------------------------------------------------------------

def _load(block: int):
    raw = json.loads((FIXTURES / f"{block}.json").read_text())
    logs = [
        SimpleNamespace(
            topics=[bytes.fromhex(t[2:]) for t in lg["topics"]],
            data=bytes.fromhex(lg["data"][2:]),
        )
        for lg in raw["logs"]
    ]
    return SimpleNamespace(
        logs=logs, blockNumber=raw["block"], status=raw["status"],
        gasUsed=raw["gas_used"],
    )


INDEX = json.loads((FIXTURES / "index.json").read_text())
BLOCKS = [r["block"] for r in INDEX["receipts"]]


@pytest.fixture()
def entity_ids(monkeypatch):
    """Map kami ids onto the recorded harvest entities.

    The receipt names entities, not kami indices, so the test binds the
    real entity ids from the fixture to synthetic kami ids: the killer
    is 12649 (its real id) and each victim is its block number.
    """
    killer_entity = int(INDEX["killer_harvest_entity"])
    victims = {
        int(b): int(e) for b, e in INDEX["victim_harvest_entities"].items()
    }

    def harvest_entity(kami_id):
        if kami_id == KILLER:
            return killer_entity
        return victims[kami_id]

    monkeypatch.setattr(server, "_harvest_entity_id", harvest_entity)
    monkeypatch.setattr(server, "_kami_last_synced_hp", lambda k: 0)
    monkeypatch.setattr(server, "_kami_cooldown_until", lambda k: 1787927247)
    return victims


@pytest.mark.parametrize("block", BLOCKS)
def test_victim_gross_equals_the_oracle_amount(block, entity_ids):
    """musu.py's drain rule over the victim entity reproduces the
    oracle's kami_action.amount for every liquidation in the sweep."""
    expected = INDEX["expected"][str(block)]
    out = server._decode_kill(_load(block), block, KILLER, expected["pre"])
    assert out["victim_gross"] == expected["victim_gross"]
    assert "decode_error" not in out


@pytest.mark.parametrize("block", BLOCKS)
def test_spoils_is_the_last_killer_write_minus_the_pre_value(block, entity_ids):
    expected = INDEX["expected"][str(block)]
    out = server._decode_kill(_load(block), block, KILLER, expected["pre"])
    assert out["killer_bounty_after"] == expected["killer_write"]
    assert out["spoils"] == expected["spoils"]


def test_the_sequence_rule_chains_across_the_whole_sweep(entity_ids):
    """A liquidate step's post-value IS the next step's pre-value, and
    the chain closes on the harvest_stop that drained the session."""
    pre = 0
    for block in BLOCKS:
        out = server._decode_kill(_load(block), block, KILLER, pre)
        assert out["spoils"] == INDEX["expected"][str(block)]["spoils"]
        pre = out["killer_bounty_after"]
    assert pre == INDEX["harvest_stop"]["drained"] == 3217


def test_killer_side_is_not_a_drain_and_musu_drain_rule_would_be_wrong(
    entity_ids,
):
    """The asymmetry is real, in BOTH directions.

    First liquidation of a session: the killer entity's writes are
    [0, N], so a drain rule reports a drain that never happened.
    Later ones: no zero write at all, so a drain rule omits the entity.
    """
    killer_entity = int(INDEX["killer_harvest_entity"])

    first = server._component_value_writes(_load(32677500))[killer_entity]
    assert first[0] == 0 and first[-1] == 1191
    assert 0 in first  # a drain rule would MATCH here, wrongly

    later = server._component_value_writes(_load(32677531))[killer_entity]
    assert 0 not in later  # a drain rule would SKIP the entity entirely
    assert later[-1] == 1904

    # The victim side is the opposite shape, which is why max works there.
    victim = server._component_value_writes(_load(32677500))[
        entity_ids[32677500]
    ]
    assert victim[-1] == 0 and max(victim) == 1798


def test_decode_failure_never_fails_a_landed_tx(entity_ids):
    """An unreadable field is None with decode_error, never an exception
    and never a fabricated number."""
    empty = SimpleNamespace(logs=[], blockNumber=1, status=1, gasUsed=1)
    out = server._decode_kill(empty, 32677500, KILLER, 0)
    assert out["victim_gross"] is None
    assert out["spoils"] is None
    assert "decode_error" in out


def test_no_salvage_field_is_returned(entity_ids):
    out = server._decode_kill(_load(32677500), 32677500, KILLER, 0)
    assert "salvage" not in out


# ---------------------------------------------------------------------------
# FAMILY A — act_sequence
# ---------------------------------------------------------------------------

AID = 4242


class _Fn:
    def __init__(self, name, args, chain):
        self.name, self.args, self._chain = name, args, chain

    def build_transaction(self, params):
        return {"data": "0x", "gas": params["gas"], "nonce": params["nonce"]}


class _Contract:
    def __init__(self, chain):
        self._chain = chain
        outer = self

        class _F:
            def __getattr__(self, name):
                return lambda *args: _Fn(name, args, outer._chain)

        self.functions = _F()


class FakeChain:
    """Scripted broadcast + receipt outcomes, one entry per step.

    outcome vocabulary: "ok" | "revert" | "timeout" | "reject"
    ("reject" fails at BROADCAST — nothing lands and the nonce is not
    consumed; the other three all land a transaction).
    """

    def __init__(self, outcomes, nonce=100, reject_once=True):
        self.outcomes = list(outcomes)
        self.base = nonce
        self.reject_once = reject_once
        self.broadcasts = []      # step indices accepted, in order
        self.rejections = 0
        self.nonce_reads = 0
        self.receipt_waits = []
        self.eth = SimpleNamespace(
            contract=lambda address=None, abi=None: _Contract(self),
            get_transaction_count=self._get_nonce,
            send_raw_transaction=self._send,
            wait_for_transaction_receipt=lambda h, timeout=None: None,
            # The signed payload IS the nonce, so a broadcast can be
            # attributed to its step with no bookkeeping: the product
            # signs step j at base + j on the first pass, and after a
            # rejection at j it re-reads a nonce that has advanced by
            # exactly the number of steps that landed (= j). So
            # step == nonce - base holds across a resend too.
            account=SimpleNamespace(
                sign_transaction=lambda built, private_key=None: SimpleNamespace(
                    raw_transaction=built["nonce"].to_bytes(4, "big")
                )
            ),
        )

    def _get_nonce(self, addr, block):
        assert block == "pending", "nonces must be read at pending (P4)"
        self.nonce_reads += 1
        return self.base + len(self.broadcasts)

    def _send(self, raw):
        i = int.from_bytes(raw, "big") - self.base
        if 0 <= i < len(self.outcomes) and self.outcomes[i] == "reject":
            self.rejections += 1
            if self.reject_once:
                self.outcomes[i] = "ok"  # the resend succeeds
            raise RuntimeError("account sequence mismatch: expected 7, got 6")
        self.broadcasts.append(i)
        return bytes([i]) * 32


@pytest.fixture()
def seq_env(monkeypatch, accounts):
    """A world where every act_sequence precondition passes."""
    monkeypatch.setattr(server, "_require_registered_operator", lambda a: AID)
    monkeypatch.setattr(server, "_kami_owner_id", lambda k: AID)
    monkeypatch.setattr(server, "_harvest_state", lambda k: "ACTIVE")
    monkeypatch.setattr(server, "_inventory_balance", lambda a, i: 99)
    monkeypatch.setattr(server, "_killer_bounty", lambda k: 0)
    monkeypatch.setattr(server, "_require_gas_balance", lambda *a, **k: None)
    monkeypatch.setattr(server, "_dry_run", lambda *a, **k: None)
    monkeypatch.setattr(server, "_resolve_system", lambda s: s)
    monkeypatch.setattr(server, "_resolve_component", lambda c: c)
    monkeypatch.setattr(server, "_kami_entity_id", lambda k: k * 10)
    monkeypatch.setattr(server, "_harvest_entity_id", lambda k: k * 100)
    monkeypatch.setattr(server, "_decode_kill", lambda *a, **k: {
        "victim_gross": 1, "spoils": 2, "attacker_hp_after": 0,
        "cooldown_until": 7, "killer_bounty_after": 2,
    })
    return monkeypatch


def _install(monkeypatch, chain, outcomes):
    monkeypatch.setattr(server, "w3", chain)

    def await_receipt(tx_hash, built, timeout, account=None, ceiling_key=None):
        chain.receipt_waits.append((tx_hash, timeout))
        i = int(tx_hash[-2:], 16)
        o = outcomes[i]
        if o == "ok":
            return SimpleNamespace(
                transactionHash=bytes([i]) * 32, blockNumber=900 + i,
                gasUsed=1000 + i, status=1,
            )
        if o == "revert":
            raise server.OnChainRevertError(
                f"0x{i:02x}", 900 + i, 1000 + i, "kami lacks violence (weak)"
            )
        raise server.TxUnconfirmedError(f"0x{i:02x}", timeout)

    monkeypatch.setattr(server, "_await_receipt", await_receipt)


FEED = {"op": "feed", "kami_id": 1, "item_id": 11409}


def _steps(n):
    return [dict(FEED, kami_id=i + 1) for i in range(n)]


def test_terminal_states_are_never_conflated(seq_env):
    """A success, a revert and a timeout in one sequence each come back
    as themselves, with their own receipt evidence (P4)."""
    outcomes = ["ok", "revert", "timeout", "ok"]
    chain = FakeChain(outcomes)
    _install(seq_env, chain, outcomes)
    out = server.act_sequence(_steps(4), account="testa")

    assert [r["status"] for r in out["steps"]] == [
        "success", "reverted", "unconfirmed", "success"
    ]
    assert out["status"] == "partial"
    assert out["sent"] == 4 and out["landed"] == 2
    # The reverted step keeps its hash, block and gas — it IS a tx.
    rev = out["steps"][1]
    assert rev["tx_hash"] and rev["block"] == 901 and rev["gas_used"] == 1001
    assert rev["reason"] == "kami lacks violence (weak)"
    # The unconfirmed step has a hash and no block: the outcome is unknown.
    unc = out["steps"][2]
    assert unc["tx_hash"] and "block" not in unc


def test_all_success_is_complete(seq_env):
    outcomes = ["ok", "ok", "ok"]
    chain = FakeChain(outcomes)
    _install(seq_env, chain, outcomes)
    out = server.act_sequence(_steps(3), account="testa")
    assert out["status"] == "complete"
    assert out["landed"] == 3 == out["sent"]


def test_nonce_read_once_and_all_signed_before_first_broadcast(seq_env):
    outcomes = ["ok"] * 5
    chain = FakeChain(outcomes)
    _install(seq_env, chain, outcomes)
    server.act_sequence(_steps(5), account="testa")
    assert chain.nonce_reads == 1
    assert chain.broadcasts == [0, 1, 2, 3, 4]


def test_a_reverted_step_does_not_stop_the_sequence(seq_env):
    """R-3: later steps still execute after a revert."""
    outcomes = ["revert", "ok", "ok"]
    chain = FakeChain(outcomes)
    _install(seq_env, chain, outcomes)
    out = server.act_sequence(_steps(3), account="testa")
    assert [r["status"] for r in out["steps"]] == [
        "reverted", "success", "success"
    ]
    assert chain.broadcasts == [0, 1, 2]


def test_a_reverted_step_is_never_resent(seq_env):
    outcomes = ["ok", "revert", "ok"]
    chain = FakeChain(outcomes)
    _install(seq_env, chain, outcomes)
    server.act_sequence(_steps(3), account="testa")
    # Three broadcasts, one nonce read: no resend path was taken.
    assert chain.broadcasts == [0, 1, 2]
    assert chain.nonce_reads == 1
    assert chain.rejections == 0


def test_a_broadcast_rejection_resends_the_tail_exactly_once(seq_env):
    outcomes = ["ok", "reject", "ok"]
    chain = FakeChain(outcomes, reject_once=True)
    _install(seq_env, chain, ["ok", "ok", "ok"])
    out = server.act_sequence(_steps(3), account="testa")
    assert chain.rejections == 1
    assert chain.nonce_reads == 2      # re-read before re-signing the tail
    assert [r["status"] for r in out["steps"]] == [
        "success", "success", "success"
    ]


def test_a_second_rejection_reports_the_tail_not_sent(seq_env):
    outcomes = ["ok", "reject", "ok"]
    chain = FakeChain(outcomes, reject_once=False)   # rejects forever
    _install(seq_env, chain, ["ok", "ok", "ok"])
    out = server.act_sequence(_steps(3), account="testa")
    assert chain.rejections == 2
    statuses = [r["status"] for r in out["steps"]]
    assert statuses == ["success", "not_sent", "not_sent"]
    assert out["sent"] == 1 and out["landed"] == 1
    assert out["status"] == "partial"
    assert "sequence mismatch" in out["steps"][1]["reason"]


def test_cap_is_sixteen_and_refuses_rather_than_splitting(seq_env):
    with pytest.raises(server.PreTxValidationError) as e:
        server.act_sequence(_steps(17), account="testa")
    assert "at most 16" in str(e.value)
    assert "not auto-split" in str(e.value)
    # 16 is allowed.
    outcomes = ["ok"] * 16
    chain = FakeChain(outcomes)
    _install(seq_env, chain, outcomes)
    assert server.act_sequence(_steps(16), account="testa")["landed"] == 16


def test_unknown_op_and_missing_field_name_the_step_index(seq_env):
    with pytest.raises(server.PreTxValidationError) as e:
        server.act_sequence(
            [FEED, {"op": "teleport", "kami_id": 1}], account="testa"
        )
    assert "step 1" in str(e.value) and "teleport" in str(e.value)

    with pytest.raises(server.PreTxValidationError) as e:
        server.act_sequence([FEED, {"op": "feed", "kami_id": 2}], "testa")
    assert "step 1" in str(e.value) and "item_id" in str(e.value)


def test_item_balance_is_checked_against_the_NUMBER_of_feed_steps(seq_env):
    seq_env.setattr(server, "_inventory_balance", lambda a, i: 2)
    outcomes = ["ok"] * 2
    chain = FakeChain(outcomes)
    _install(seq_env, chain, outcomes)
    server.act_sequence(_steps(2), account="testa")     # 2 held, 2 fed: ok

    with pytest.raises(server.PreTxValidationError) as e:
        server.act_sequence(_steps(3), account="testa")  # 2 held, 3 fed
    assert "feeds item 11409 3 time(s)" in str(e.value)
    assert "holds 2" in str(e.value)


def test_a_killer_started_by_an_earlier_step_passes_validation(seq_env):
    """The whole point of static validation over a PLAN: step 2's
    precondition is step 1's effect and does not exist yet."""
    seq_env.setattr(server, "_harvest_state", lambda k: "")   # nothing active
    steps = [
        {"op": "harvest_start", "kami_ids": [7], "node_index": 86},
        {"op": "liquidate", "kami_id": 7, "victim_kami_id": 9},
    ]
    # The victim still has to be harvesting NOW, so this must refuse on
    # the victim and NOT on the killer.
    with pytest.raises(server.PreTxValidationError) as e:
        server.act_sequence(steps, account="testa")
    msg = str(e.value)
    assert "victim kami #9" in msg
    assert "killer kami #7" not in msg


def test_a_killer_not_started_anywhere_is_refused(seq_env):
    seq_env.setattr(
        server, "_harvest_state", lambda k: "ACTIVE" if k == 9 else ""
    )
    steps = [{"op": "liquidate", "kami_id": 7, "victim_kami_id": 9}]
    with pytest.raises(server.PreTxValidationError) as e:
        server.act_sequence(steps, account="testa")
    assert "killer kami #7 is not harvesting now" in str(e.value)


def test_harvest_stop_requires_active_or_started_earlier(seq_env):
    seq_env.setattr(server, "_harvest_state", lambda k: "")
    with pytest.raises(server.PreTxValidationError) as e:
        server.act_sequence(
            [{"op": "harvest_stop", "kami_ids": [5]}], account="testa"
        )
    assert "kami #5 is not harvesting now" in str(e.value)

    outcomes = ["ok", "ok"]
    chain = FakeChain(outcomes)
    _install(seq_env, chain, outcomes)
    out = server.act_sequence([
        {"op": "harvest_start", "kami_ids": [5], "node_index": 86},
        {"op": "harvest_stop", "kami_ids": [5]},
    ], account="testa")
    assert out["landed"] == 2


def test_gas_gate_sums_every_step(seq_env):
    seen = {}

    def gate(addr, gas, value, role):
        seen["gas"] = gas

    seq_env.setattr(server, "_require_gas_balance", gate)
    outcomes = ["ok"] * 3
    chain = FakeChain(outcomes)
    _install(seq_env, chain, outcomes)
    server.act_sequence(_steps(3), account="testa")
    assert seen["gas"] == 3 * server._GAS_CEILINGS["feed_kami"]


def test_ceilings_are_fixed_per_op_and_never_estimated(seq_env):
    """A3: the gas offered per step is its table ceiling."""
    steps = [
        FEED,
        {"op": "liquidate", "kami_id": 1, "victim_kami_id": 2},
        {"op": "harvest_start", "kami_ids": [1, 2], "node_index": 86},
        {"op": "harvest_stop", "kami_ids": [1]},
    ]
    plans = [server._seq_plan(s) for s in steps]
    assert plans[0][4] == server._GAS_CEILINGS["feed_kami"] == 3_000_000
    assert plans[1][4] == server._GAS_CEILINGS["liquidate_kami"] == 7_500_000
    assert plans[2][4] == server._harvest_gas("harvest_start", 2)
    assert plans[3][4] == server._harvest_gas("harvest_stop", 1)
    # Batched vs single is chosen by the kami count, as harvest_start does.
    assert plans[2][2] == "executeBatched"
    assert plans[3][2] == "executeTyped"


def test_liquidate_rows_carry_the_decoded_kill_but_no_recoil(seq_env):
    """B: a sequence row has no `hp_before` to difference against, so
    recoil is omitted rather than invented."""
    outcomes = ["ok"]
    chain = FakeChain(outcomes)
    _install(seq_env, chain, outcomes)
    out = server.act_sequence(
        [{"op": "liquidate", "kami_id": 1, "victim_kami_id": 2}],
        account="testa",
    )
    row = out["steps"][0]
    assert row["victim_gross"] == 1 and row["spoils"] == 2
    assert row["cooldown_until"] == 7
    assert "recoil" not in row
    assert "killer_bounty_after" not in row


def test_the_call_raises_only_when_step_one_fails_pre_send(seq_env):
    """Nothing broadcast -> raise. Anything broadcast -> report."""
    outcomes = ["ok"] * 3
    _install(seq_env, FakeChain(outcomes), outcomes)

    def boom(*a, **k):
        raise server.PreTxValidationError("dry run says no")

    seq_env.setattr(server, "_dry_run", boom)
    with pytest.raises(server.PreTxValidationError):
        server.act_sequence(_steps(3), account="testa")


# ---------------------------------------------------------------------------
# FAMILY C — lens_skills
# ---------------------------------------------------------------------------

def test_lens_skills_passes_the_index_through(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        server, "_lens_request",
        lambda q, a=None, **k: seen.update(query=q, args=a) or {"data": {}},
    )
    server.lens_skills()
    assert seen == {"query": "skills", "args": []}
    server.lens_skills(45)
    assert seen == {"query": "skills", "args": [45]}


# ---------------------------------------------------------------------------
# Surface
# ---------------------------------------------------------------------------

def test_surface_at_350():
    tools = {t.name for t in server.mcp._tool_manager.list_tools()}
    assert len(tools) == 104
    assert {"act_sequence", "lens_skills"} <= tools
    assert server.TOOL_CLASSES["act_sequence"] == "ACT"
    assert server.TOOL_CLASSES["lens_skills"] == "PERCEIVE"
    assert "lens_skills" in server.READ_TOOLS
    assert "act_sequence" not in server.READ_TOOLS


def test_registry_mass_within_the_raised_budget():
    assert server.REGISTRY_MASS_BUDGET == 73_000
    mass = server.registry_mass()
    assert mass <= server.REGISTRY_MASS_BUDGET, mass


def test_act_sequence_description_states_the_contract():
    import re
    d = {t.name: t.description for t in server.mcp._tool_manager.list_tools()}
    desc = re.sub(r"\s+", " ", d["act_sequence"])
    for phrase in [
        "consecutive nonces",
        "before any receipt is read",
        "block or two",
        "Only step 1 is dry-run",
        "does not stop the sequence",
        "max 16",
        "not_sent",
    ]:
        assert phrase in desc, phrase
    # D2: no advice, no cycle recipe.
    assert "should" not in desc.lower()


def test_liquidate_kami_says_why_there_is_no_salvage():
    d = {t.name: t.description for t in server.mcp._tool_manager.list_tools()}
    desc = d["liquidate_kami"]
    assert "No salvage" in desc
    assert "absolute" in desc
    assert "victim_gross" in desc and "cooldown_until" in desc

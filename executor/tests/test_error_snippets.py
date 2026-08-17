"""Mechanics snippets on ERROR results (KAMI_ERROR_SNIPPETS) and the
single-source state table they share with the pre-send gates.

Two things are pinned here. First, the table: every kami-state gate reads
its requirement from `server._TOOL_KAMI_STATES`, so a gate and what an
error says about it cannot drift apart, and the rows only ever name tools
this module actually gates. Second, the snippet: with the flag off, error
text is byte-identical to what the gates produced before it existed; with
the flag on, an appended `[mechanics]` block states states, tool names and
numbers this module already holds — and nothing else.

The three examples an agent would see are asserted verbatim (harvest_start
on a HARVESTING kami, harvest_collect on a RESTING kami, a dry-run revert),
because the wording is the contract with the agent, not an implementation
detail.
"""

import inspect
from types import SimpleNamespace

import pytest

import server

PREFIX = server.PreTxValidationError.PREFIX
FAKE_ACCOUNT_ID = 0x7777


@pytest.fixture()
def snippets_on(monkeypatch):
    monkeypatch.setattr(server, "ERROR_SNIPPETS", True)


@pytest.fixture()
def snippets_off(monkeypatch):
    monkeypatch.setattr(server, "ERROR_SNIPPETS", False)


@pytest.fixture()
def world(monkeypatch):
    """A readable world: owned kamis, RESTING, no harvest, room 42.

    Individual tests override the piece they are exercising.
    """
    state = {"kami": "RESTING", "harvest": ""}
    monkeypatch.setattr(
        server, "_require_registered_operator", lambda a: FAKE_ACCOUNT_ID
    )
    monkeypatch.setattr(server, "_kami_owner_id", lambda k: FAKE_ACCOUNT_ID)
    monkeypatch.setattr(server, "_kami_state", lambda k: state["kami"])
    monkeypatch.setattr(server, "_harvest_state", lambda k: state["harvest"])
    monkeypatch.setattr(server, "_account_entity_id", lambda a: FAKE_ACCOUNT_ID)
    monkeypatch.setattr(
        server, "_account_view",
        lambda aid: {"index": 1, "name": "t", "stamina": 7, "room": 42},
    )
    return state


class _RevertingCall:
    """A built contract function whose eth_call dry-run reverts."""

    def __init__(self, args, message):
        self.args = args
        self._message = message

    def call(self, params=None):
        raise ValueError({"code": -32000, "message": self._message})


# ---------------------------------------------------------------------------
# The single source table
# ---------------------------------------------------------------------------


class TestStateTable:
    def test_requirements_are_the_2_1_0_gates(self):
        """The table reproduces exactly the requirements the gates carried
        as literals before it existed."""
        assert server._TOOL_KAMI_STATES == {
            "harvest_start": ("RESTING",),
            "revive_kami": ("DEAD",),
            "liquidate_kami": ("HARVESTING",),
            "gacha_reroll": ("RESTING",),
            "transfer_kami": ("RESTING", "LISTED"),
        }
        assert server._SENDABLE_STATES == {"RESTING", "LISTED"}

    def test_rows_are_the_exact_inversion(self):
        for state, tools in server._STATE_TOOLS.items():
            for tool in tools:
                assert state in server._TOOL_KAMI_STATES[tool]
        for tool, states in server._TOOL_KAMI_STATES.items():
            for state in states:
                assert tool in server._STATE_TOOLS[state]

    def test_every_readable_state_has_a_row(self):
        """Including the states no gate accepts: a gap is a visible empty
        row, never a missing key."""
        assert set(server._STATE_TOOLS) == set(server._KNOWN_KAMI_STATES)
        assert server._STATE_TOOLS["721_EXTERNAL"] == ()
        assert server._STATE_TOOLS[""] == ()

    def test_tables_name_only_live_tools(self):
        live = {t.name for t in server.mcp._tool_manager.list_tools()}
        named = set(server._TOOL_KAMI_STATES)
        for tools in server._HARVEST_STATE_TOOLS.values():
            named |= set(tools)
        assert named <= live

    def test_gates_read_the_table_not_literals(self):
        """No `required_state=` literal survives at a call site: the gate
        resolves the requirement from _TOOL_KAMI_STATES."""
        src = inspect.getsource(server)
        assert 'required_state="' not in src
        assert "required_state='" not in src

    @pytest.mark.parametrize(
        "tool,state,required",
        [
            ("harvest_start", "HARVESTING", "RESTING"),
            ("revive_kami", "RESTING", "DEAD"),
            ("gacha_reroll", "DEAD", "RESTING"),
            ("liquidate_kami", "RESTING", "HARVESTING"),
        ],
    )
    def test_gate_message_unchanged_per_tool(
        self, snippets_off, world, tool, state, required
    ):
        world["kami"] = state
        with pytest.raises(server.PreTxValidationError) as ei:
            server._require_kamis_owned([5], "testa", FAKE_ACCOUNT_ID, tool)
        assert str(ei.value) == (
            f"{PREFIX}kami #5 is {state}; {tool} requires {required}"
        )


# ---------------------------------------------------------------------------
# Flag off: 2.1.0 text, to the byte
# ---------------------------------------------------------------------------


class TestFlagOff:
    def test_no_snippet_on_state_gate(self, snippets_off, world):
        world["kami"] = "HARVESTING"
        with pytest.raises(server.PreTxValidationError) as ei:
            server._require_kamis_owned(
                [123], "testa", FAKE_ACCOUNT_ID, "harvest_start"
            )
        assert str(ei.value) == (
            f"{PREFIX}kami #123 is HARVESTING; harvest_start requires RESTING"
        )
        assert ei.value.mechanics == ""

    def test_no_snippet_on_dry_run_revert(self, snippets_off, world):
        fn = _RevertingCall((server._kami_entity_id(123),), "nope")
        with pytest.raises(server.PreTxValidationError) as ei:
            server._dry_run(fn, "0xabc", account="main")
        assert str(ei.value) == f"{PREFIX}transaction dry-run reverted: nope"

    def test_detail_never_carries_the_snippet(self, snippets_on, world):
        world["kami"] = "HARVESTING"
        with pytest.raises(server.PreTxValidationError) as ei:
            server._require_kamis_owned(
                [123], "testa", FAKE_ACCOUNT_ID, "harvest_start"
            )
        assert ei.value.detail == (
            "kami #123 is HARVESTING; harvest_start requires RESTING"
        )
        assert ei.value.detail not in ei.value.mechanics


# ---------------------------------------------------------------------------
# Flag on: the three snippets an agent sees
# ---------------------------------------------------------------------------


class TestSnippetExamples:
    def test_harvest_start_on_harvesting_kami(self, snippets_on, world):
        world["kami"] = "HARVESTING"
        world["harvest"] = "ACTIVE"
        with pytest.raises(server.PreTxValidationError) as ei:
            server.harvest_start([123], 42, account="testa")
        assert str(ei.value) == (
            "validation failed; no transaction sent: kami #123 is "
            "HARVESTING; harvest_start requires RESTING\n"
            "[mechanics] kami #123: state HARVESTING, harvest entity ACTIVE. "
            "Tools whose harness state gate accepts HARVESTING: "
            "liquidate_kami. Tools whose harness state gate accepts harvest "
            "ACTIVE: harvest_collect, harvest_stop, liquidate_kami. "
            "harvest_start requires RESTING."
        )

    def test_harvest_collect_on_resting_kami(self, snippets_on, world):
        with pytest.raises(server.PreTxValidationError) as ei:
            server.harvest_collect([123], account="testa")
        assert str(ei.value) == (
            "validation failed; no transaction sent: no active harvest "
            "exists for kami #123; its harvest entity state is ''\n"
            "[mechanics] kami #123: state RESTING, harvest entity unset. "
            "Tools whose harness state gate accepts RESTING: gacha_reroll, "
            "harvest_start, transfer_kami. harvest_collect requires harvest "
            "ACTIVE."
        )

    def test_dry_run_revert(self, snippets_on, world):
        fn = _RevertingCall(
            (server._kami_entity_id(123), 42, 0, 0), "kami not in node room"
        )
        with pytest.raises(server.PreTxValidationError) as ei:
            server._dry_run(fn, "0xabc", account="main")
        assert str(ei.value) == (
            "validation failed; no transaction sent: transaction dry-run "
            "reverted: kami not in node room\n"
            "[mechanics] account 'main': room 42, stamina 7. kami #123: "
            "state RESTING, harvest entity unset. Tools whose harness state "
            "gate accepts RESTING: gacha_reroll, harvest_start, "
            "transfer_kami. Not read by the harness for this call: "
            "cooldowns, HP, node/room match, XP."
        )


# ---------------------------------------------------------------------------
# Flag on: the rest of the classes and the guards
# ---------------------------------------------------------------------------


class TestSnippetBehaviour:
    def test_ownership_failure_states_the_state_only(self, snippets_on, world, monkeypatch):
        monkeypatch.setattr(server, "_kami_owner_id", lambda k: 0xDEAD)
        with pytest.raises(server.PreTxValidationError) as ei:
            server._require_kamis_owned(
                [5], "testa", FAKE_ACCOUNT_ID, "harvest_start"
            )
        assert ei.value.mechanics == "\n[mechanics] kami #5: state RESTING."
        assert "Tools whose" not in ei.value.mechanics
        assert "requires" not in ei.value.mechanics

    def test_unknown_state_makes_no_claim(self, snippets_on, world):
        world["kami"] = "ASLEEP"
        with pytest.raises(server.PreTxValidationError) as ei:
            server._require_kamis_owned(
                [5], "testa", FAKE_ACCOUNT_ID, "harvest_start"
            )
        assert "kami #5: state ASLEEP." in ei.value.mechanics
        assert "Tools whose harness state gate accepts ASLEEP" not in str(
            ei.value
        )

    def test_liquidate_victim_without_active_harvest(self, snippets_on, world):
        world["kami"] = "HARVESTING"  # the attacker passes its own gate
        with pytest.raises(server.PreTxValidationError) as ei:
            server.liquidate_kami(9, 5, account="testa")
        assert (
            "kami #9: state HARVESTING, harvest entity unset." in str(ei.value)
        )
        assert "liquidate_kami requires harvest ACTIVE." in str(ei.value)

    def test_out_of_gas_names_its_ceiling(self, snippets_on, world, monkeypatch):
        receipt = SimpleNamespace(
            status=0, gasUsed=3_999_846, blockNumber=500,
            transactionHash="0xdead",
        )
        monkeypatch.setattr(
            server, "w3",
            SimpleNamespace(eth=SimpleNamespace(
                wait_for_transaction_receipt=lambda h, timeout: receipt
            )),
        )
        eid = server._harvest_entity_id(123)
        built = {"gas": 4_000_000, "data": "0x1234abcd" + f"{eid:064x}"}
        with pytest.raises(server.OnChainRevertError) as ei:
            server._await_receipt(
                "0xdead", built, timeout=1, account="main",
                ceiling_key="harvest_collect",
            )
        msg = str(ei.value)
        assert "likely ran out of gas" in msg
        assert (
            "Gas ceiling for this call: _GAS_CEILINGS['harvest_collect'] "
            "= 4,000,000." in msg
        )
        assert "kami #123: state RESTING, harvest entity unset." in msg

    def test_contract_revert_does_not_name_a_ceiling(
        self, snippets_on, world, monkeypatch
    ):
        """A ceiling is named only when the revert WAS out-of-gas."""
        receipt = SimpleNamespace(
            status=0, gasUsed=100_000, blockNumber=500,
            transactionHash="0xdead",
        )
        monkeypatch.setattr(
            server, "w3",
            SimpleNamespace(eth=SimpleNamespace(
                wait_for_transaction_receipt=lambda h, timeout: receipt
            )),
        )
        monkeypatch.setattr(
            server, "_replay_revert_reason", lambda built, block: "nope"
        )
        with pytest.raises(server.OnChainRevertError) as ei:
            server._await_receipt(
                "0xdead", {"gas": 4_000_000, "data": "0x1234abcd"}, timeout=1,
                account="main", ceiling_key="harvest_collect",
            )
        assert "Gas ceiling for this call" not in str(ei.value)

    def test_batch_error_reports_each_failed_step(self, snippets_on, world):
        outcomes = {
            "results": [
                {"kami_id": 7, "status": "error", "reason": "boom"},
                {"kami_id": 8, "status": "success"},
                {"kami_id": 9, "status": "skipped", "reason": "dry-run"},
            ]
        }
        e = server.BatchTxError("equip_all_batch", "1 of 3 failed.", outcomes)
        assert "kami #7: state RESTING." in e.mechanics
        assert "kami #8" not in e.mechanics
        assert "kami #9" not in e.mechanics

    def test_batch_error_leaves_the_returned_payload_untouched(
        self, snippets_on, world
    ):
        outcomes = {"results": [{"kami_id": 7, "status": "error"}]}
        server.BatchTxError("equip_all_batch", "1 of 1 failed.", outcomes)
        assert outcomes == {"results": [{"kami_id": 7, "status": "error"}]}

    def test_silent_skip_shape_is_reported(self, snippets_on, world):
        outcomes = {"per_kami": {7: {"harvest_state": "ACTIVE", "stopped": False}}}
        e = server.BatchTxError("stop_harvest_batch", "1 did not stop.", outcomes)
        assert "kami #7" in e.mechanics


class TestSubjectDerivation:
    def test_only_ids_present_in_this_call_are_named(self):
        eid = server._kami_entity_id(5)
        assert server._calldata_subjects(args=[eid, 42]) == [
            {"kami_id": 5, "read_harvest": True}
        ]
        # An id this call does not carry is never attributed to it.
        server._kami_entity_id(6)
        assert server._calldata_subjects(args=[eid]) == [
            {"kami_id": 5, "read_harvest": True}
        ]
        # An integer that is not a derived entity id names nobody.
        assert server._calldata_subjects(args=[123, 456]) == []

    def test_harvest_ids_resolve_to_their_kami(self):
        hid = server._harvest_entity_id(11)
        assert server._calldata_subjects(args=[[hid]]) == [
            {"kami_id": 11, "read_harvest": True}
        ]

    def test_calldata_hex_is_scanned_past_the_selector(self):
        eid = server._kami_entity_id(77)
        data = "0xdeadbeef" + f"{eid:064x}" + f"{42:064x}"
        assert server._calldata_subjects(data=data) == [
            {"kami_id": 77, "read_harvest": True}
        ]

    def test_index_stays_bounded(self):
        for i in range(server._ENTITY_SUBJECTS_MAX + 50):
            server._kami_entity_id(1_000_000 + i)
        assert len(server._ENTITY_SUBJECTS) <= server._ENTITY_SUBJECTS_MAX


class TestSnippetGuards:
    def test_unreadable_state_leaves_the_error_alone(
        self, snippets_on, world, monkeypatch
    ):
        def boom(_k):
            raise RuntimeError("rpc down")

        monkeypatch.setattr(server, "_kami_state", boom)
        monkeypatch.setattr(server, "_harvest_state", boom)
        fn = _RevertingCall((server._kami_entity_id(123),), "nope")
        with pytest.raises(server.PreTxValidationError) as ei:
            server._dry_run(fn, "0xabc", account="main")
        assert "kami #123" not in str(ei.value)
        assert str(ei.value).startswith(
            f"{PREFIX}transaction dry-run reverted: nope"
        )

    def test_a_partly_readable_kami_reports_only_what_it_read(
        self, snippets_on, world, monkeypatch
    ):
        def boom(_k):
            raise RuntimeError("rpc down")

        monkeypatch.setattr(server, "_kami_state", boom)
        fn = _RevertingCall((server._kami_entity_id(123),), "nope")
        with pytest.raises(server.PreTxValidationError) as ei:
            server._dry_run(fn, "0xabc", account="main")
        assert "kami #123: harvest entity unset." in str(ei.value)
        assert "state" not in ei.value.mechanics.split("kami #123")[1]

    def test_never_introduces_the_retry_routing_marker(
        self, snippets_on, world, monkeypatch
    ):
        """_send_tx_retry routes on "-32000" in str(e); a snippet that
        would contain it is dropped rather than reclassifying the error."""
        monkeypatch.setattr(
            server, "_account_view",
            lambda aid: {"index": 1, "name": "t", "stamina": -32000, "room": 1},
        )
        fn = _RevertingCall((server._kami_entity_id(123),), "nope")
        with pytest.raises(server.PreTxValidationError) as ei:
            server._dry_run(fn, "0xabc", account="main")
        assert ei.value.mechanics == ""
        assert str(ei.value) == f"{PREFIX}transaction dry-run reverted: nope"

    def test_length_is_bounded_and_says_what_it_hid(self, snippets_on, world):
        world["kami"] = "HARVESTING"
        world["harvest"] = "ACTIVE"
        with pytest.raises(server.PreTxValidationError) as ei:
            server._require_kamis_owned(
                list(range(1, 8)), "testa", FAKE_ACCOUNT_ID, "harvest_start"
            )
        snippet = ei.value.mechanics
        assert len(snippet) <= server._SNIPPET_MAX_CHARS
        # Whatever the bound drops, it says how many — nothing goes missing
        # silently, and no sentence is cut in half.
        shown = snippet.count("kami #")
        assert shown <= server._SNIPPET_MAX_SUBJECTS
        assert f"(+{7 - shown} more kamis not shown.)" in snippet
        assert snippet.endswith("harvest_start requires RESTING.")

    def test_snippet_is_mechanics_only(self, snippets_on, world):
        world["kami"] = "HARVESTING"
        world["harvest"] = "ACTIVE"
        with pytest.raises(server.PreTxValidationError) as ei:
            server.harvest_start([123], 42, account="testa")
        text = ei.value.mechanics.lower()
        for banned in (
            "you should", "you can", "you may", "recommend", "consider",
            "instead", "better", "advise", "tip:", "strategy", "optimal",
            "profit",
        ):
            assert banned not in text

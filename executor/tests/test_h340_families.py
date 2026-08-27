"""3.4.0 families: travel that cannot strand, the starving gate, the
lens 0.5.2 passthroughs.

Everything here is offline: the chain reads each family depends on are
monkeypatched, and the room graph comes from the committed catalogs.
"""

import asyncio
from types import SimpleNamespace

import pytest

import rooms_graph
import server

FAKE_ACCOUNT_ID = 0xABCDEF


# ---------------------------------------------------------------------------
# FAMILY A — travel_to_room evaluates gates against the account
# ---------------------------------------------------------------------------


@pytest.fixture()
def travel_world(accounts, monkeypatch):
    """A registered account standing in room 10 with full stamina."""
    monkeypatch.setattr(
        server, "_require_registered_operator", lambda a: FAKE_ACCOUNT_ID
    )
    monkeypatch.setattr(
        server, "_read_account_view",
        lambda aid: ({"index": 1, "name": "t", "stamina": 100, "room": 10}, ""),
    )
    monkeypatch.setattr(server, "_sp_item_balances", lambda aid: [])


def _gate_verdicts(monkeypatch, verdicts):
    """Stub the per-gate chain evaluation: {(type, index): True/False/None}."""
    calls = []

    def fake(gate, account_id):
        calls.append((gate["type"], gate["index"], gate["value"], account_id))
        return verdicts.get((gate["type"], gate["index"]), True)

    monkeypatch.setattr(server, "_evaluate_room_gate", fake)
    return calls


class TestGatedPlanning:
    def test_ungated_target_is_unchanged(self, travel_world, monkeypatch):
        """Regression guard: a plan with no gate on it plans exactly as
        3.3.0 planned it."""
        _gate_verdicts(monkeypatch, {})
        r = asyncio.run(
            server.travel_to_room(37, account="testa", dry_run=True)
        )
        assert r["feasible"] is True
        assert r["path"] == [10, 35, 48, 9, 36, 25, 37]
        assert r["gated_hops"] == []

    def test_a_gate_the_account_passes_stays_on_the_plan(
        self, travel_world, monkeypatch
    ):
        _gate_verdicts(monkeypatch, {("QUEST", 35): True})
        r = asyncio.run(
            server.travel_to_room(15, account="testa", dry_run=True)
        )
        assert r["feasible"] is True
        assert r["path"][-1] == 15
        assert [g["passable"] for g in r["gated_hops"]] == [True]

    def test_dry_run_reports_an_impassable_gate_instead_of_feasible(
        self, travel_world, monkeypatch
    ):
        """The reported defect: this planned 75 -> ... -> 15 -> ... as
        `feasible: true`, executed three hops, and reverted on hop 4."""
        _gate_verdicts(monkeypatch, {("QUEST", 35): False})
        r = asyncio.run(
            server.travel_to_room(15, account="testa", dry_run=True)
        )
        assert r["feasible"] is False
        assert r["path"] == []
        blocked = r["blocked_by"]
        assert blocked and all(b["passable"] is False for b in blocked)
        assert {(b["from"], b["to"]) for b in blocked} == {(11, 15)}
        assert blocked[0]["type"] == "QUEST" and blocked[0]["index"] == 35
        assert "Steel Your Heart" in blocked[0]["text"]

    def test_send_path_refuses_pre_send(self, travel_world, monkeypatch):
        """Zero gas, zero stamina — the whole point of the family."""
        _gate_verdicts(monkeypatch, {("QUEST", 35): False})
        sent = []
        monkeypatch.setattr(
            server, "_send_tx_retry",
            lambda *a, **k: sent.append(a) or {"status": "success"},
        )
        with pytest.raises(server.PreTxValidationError) as ei:
            asyncio.run(server.travel_to_room(15, account="testa"))
        msg = str(ei.value)
        assert "no route from room 10 to room 15" in msg
        assert "QUEST 35" in msg
        assert "Nothing was sent and no stamina was spent" in msg
        assert sent == []

    def test_an_unevaluable_gate_never_silently_passes(
        self, travel_world, monkeypatch
    ):
        _gate_verdicts(monkeypatch, {("QUEST", 35): None})
        with pytest.raises(server.PreTxValidationError) as ei:
            asyncio.run(server.travel_to_room(15, account="testa"))
        assert "gate could not be evaluated" in str(ei.value)

    def test_routes_around_a_gate_when_an_alternative_exists(
        self, travel_world, monkeypatch
    ):
        """A fixture graph where the shortest path is gated and a longer
        ungated one exists: the longer one is planned, not refused."""
        graph = {1: {2, 3}, 2: {1, 4}, 3: {1, 5}, 4: {2}, 5: {3, 4}}

        def sp(a, b, blocked=None):
            blocked = blocked or set()
            from collections import deque
            par = {a: a}
            q = deque([a])
            while q:
                cur = q.popleft()
                for n in sorted(graph.get(cur, ())):
                    if n not in par and (cur, n) not in blocked:
                        par[n] = cur
                        q.append(n)
            if b not in par:
                raise ValueError(f"No path from {a} to {b}")
            out = [b]
            while out[-1] != a:
                out.append(par[out[-1]])
            return out[::-1]

        monkeypatch.setattr(
            server, "rooms_graph",
            SimpleNamespace(
                shortest_path=sp,
                move_cost=lambda p: 5 * (len(p) - 1),
                gates_on=lambda a, b: (
                    [{"type": "QUEST", "index": 9, "value": "0",
                      "text": "gated"}] if (a, b) == (2, 4) else []
                ),
            ),
        )
        monkeypatch.setattr(
            server, "_read_account_view",
            lambda aid: ({"index": 1, "name": "t", "stamina": 100,
                          "room": 1}, ""),
        )
        _gate_verdicts(monkeypatch, {("QUEST", 9): False})
        r = asyncio.run(
            server.travel_to_room(4, account="testa", dry_run=True)
        )
        assert r["feasible"] is True
        assert r["path"] == [1, 3, 5, 4]
        assert r["gated_hops"] == []

    def test_each_distinct_gate_is_read_once(self, travel_world, monkeypatch):
        """Three of room 15's entrances carry the same gate; the account
        is asked about it once, not once per candidate path."""
        calls = _gate_verdicts(monkeypatch, {("QUEST", 35): False})
        asyncio.run(server.travel_to_room(15, account="testa", dry_run=True))
        quest = [c for c in calls if c[0] == "QUEST"]
        assert len(quest) == 1, "room 15's three entrances share one gate"
        assert len(calls) == len(set(calls)), "every gate read at most once"
        assert all(c[3] == FAKE_ACCOUNT_ID for c in calls)


class TestGateEvaluation:
    """Each condition type against its component read."""

    def test_quest_gate_reads_the_account_quest_instance(self, monkeypatch):
        seen = {}

        def comp(address, abi):
            return SimpleNamespace(functions=SimpleNamespace(
                has=lambda e: SimpleNamespace(call=lambda: seen.setdefault(
                    "entity", e) is None or True)
            ))

        monkeypatch.setattr(server, "_resolve_component", lambda n: n)
        monkeypatch.setattr(
            server, "w3", SimpleNamespace(eth=SimpleNamespace(contract=comp))
        )
        gate = {"type": "QUEST", "index": 35, "value": "0", "text": ""}
        assert server._evaluate_room_gate(gate, FAKE_ACCOUNT_ID) is True
        assert seen["entity"] == server._quest_entity_id(35, FAKE_ACCOUNT_ID)

    def test_item_gate_compares_the_balance_to_the_threshold(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            server, "_inventory_balance", lambda holder, item: 1
        )
        gate = {"type": "ITEM", "index": 100004, "value": "0x1", "text": ""}
        assert server._evaluate_room_gate(gate, FAKE_ACCOUNT_ID) is True
        monkeypatch.setattr(
            server, "_inventory_balance", lambda holder, item: 0
        )
        assert server._evaluate_room_gate(gate, FAKE_ACCOUNT_ID) is False

    def test_complete_comp_reads_the_goal_entity_whole(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(server, "_resolve_component", lambda n: n)
        monkeypatch.setattr(
            server, "w3",
            SimpleNamespace(eth=SimpleNamespace(contract=lambda address, abi:
                SimpleNamespace(functions=SimpleNamespace(
                    has=lambda e: SimpleNamespace(
                        call=lambda: seen.setdefault("entity", e) is None
                    )
                ))
            )),
        )
        gate = {"type": "COMPLETE_COMP", "index": 0, "value": "0x" + "ab" * 32,
                "text": ""}
        server._evaluate_room_gate(gate, FAKE_ACCOUNT_ID)
        assert seen["entity"] == int("0x" + "ab" * 32, 16)

    def test_a_failed_read_is_unknown_not_false(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("rpc down")

        monkeypatch.setattr(server, "_inventory_balance", boom)
        gate = {"type": "ITEM", "index": 1, "value": "0x1", "text": ""}
        assert server._evaluate_room_gate(gate, FAKE_ACCOUNT_ID) is None

    def test_an_unknown_type_is_unknown_not_false(self):
        gate = {"type": "LEVEL", "index": 5, "value": "0", "text": ""}
        assert server._evaluate_room_gate(gate, FAKE_ACCOUNT_ID) is None


class TestMidPathGateReport:
    def test_inaccessible_room_revert_names_the_gate(
        self, travel_world, monkeypatch
    ):
        """A3: the chain's word for a gate is bare; the report is not."""
        _gate_verdicts(monkeypatch, {("QUEST", 35): True})

        def sender(account, system, abi, args, **kw):
            if args[0] == 15:
                raise server.PreTxValidationError(
                    "transaction dry-run reverted: revert: "
                    "AccMove: inaccessible room"
                )
            return {"tx_hash": "0x1", "status": "success", "block": 1,
                    "gas_used": 100}

        monkeypatch.setattr(server, "_send_tx_retry", sender)
        with pytest.raises(server.BatchTxError) as ei:
            asyncio.run(server.travel_to_room(15, account="testa"))
        msg = str(ei.value)
        assert "catalogs/room-gates.csv gates 11->15 on" in msg
        assert "QUEST 35" in msg


# ---------------------------------------------------------------------------
# FAMILY C — a starving kami cannot stop or collect
# ---------------------------------------------------------------------------


class TestStarvingGate:
    @pytest.fixture()
    def harvesting(self, accounts, monkeypatch):
        monkeypatch.setattr(
            server, "_require_registered_operator", lambda a: FAKE_ACCOUNT_ID
        )
        monkeypatch.setattr(
            server, "_kami_owner_id", lambda k: FAKE_ACCOUNT_ID
        )
        monkeypatch.setattr(server, "_harvest_state", lambda k: "ACTIVE")

    @pytest.mark.parametrize("action", ["harvest_stop", "harvest_collect"])
    def test_zero_hp_refuses_pre_send(self, harvesting, monkeypatch, action):
        monkeypatch.setattr(server, "_kami_last_synced_hp", lambda k: 0)
        with pytest.raises(server.PreTxValidationError) as ei:
            server._validate_active_harvests([7], "testa", action)
        assert "kami 7 is starving (HP 0): feed first" in str(ei.value)

    @pytest.mark.parametrize("action", ["harvest_stop", "harvest_collect"])
    def test_healthy_kami_passes(self, harvesting, monkeypatch, action):
        monkeypatch.setattr(server, "_kami_last_synced_hp", lambda k: 12)
        server._validate_active_harvests([7], "testa", action)

    def test_an_unreadable_hp_does_not_refuse(self, harvesting, monkeypatch):
        """One-way soundness: only sync == 0 is proof. An unreadable
        value must not manufacture a refusal — the dry-run still guards."""
        monkeypatch.setattr(server, "_kami_last_synced_hp", lambda k: None)
        server._validate_active_harvests([7], "testa", "harvest_stop")

    def test_the_state_gate_still_reports_first(self, harvesting, monkeypatch):
        """A kami with no harvest is reported as that, not as starving."""
        monkeypatch.setattr(server, "_harvest_state", lambda k: "")
        monkeypatch.setattr(server, "_kami_last_synced_hp", lambda k: 0)
        with pytest.raises(server.PreTxValidationError) as ei:
            server._validate_active_harvests([7], "testa", "harvest_stop")
        assert "no active harvest exists" in str(ei.value)
        assert "starving" not in str(ei.value)

    def test_hp_reads_the_sync_word_of_the_health_stat(self, monkeypatch):
        monkeypatch.setattr(server, "_resolve_component", lambda n: n)
        monkeypatch.setattr(
            server, "w3",
            SimpleNamespace(eth=SimpleNamespace(contract=lambda address, abi:
                SimpleNamespace(functions=SimpleNamespace(
                    safeGet=lambda e: SimpleNamespace(
                        call=lambda: (90, 0, 0, 140)
                    )
                ))
            )),
        )
        assert server._kami_last_synced_hp(15540) == 140

    def test_the_dry_run_revert_gains_the_same_sentence(self):
        """A kami that drained to 0 since its last sync passes the gate
        and fails in the dry-run. Same mechanic, same wording."""
        with pytest.raises(server.PreTxValidationError) as ei:
            with server._starving_revert_named([4, 5], "testa", "harvest_stop"):
                raise server.PreTxValidationError(
                    "transaction dry-run reverted: revert: kami starving.."
                )
        msg = str(ei.value)
        assert "kami starving.." in msg
        assert "feed first" in msg

    def test_an_unrelated_revert_passes_through_untouched(self):
        with pytest.raises(server.PreTxValidationError) as ei:
            with server._starving_revert_named([4], "testa", "harvest_stop"):
                raise server.PreTxValidationError("something else entirely")
        assert "feed first" not in str(ei.value)


# ---------------------------------------------------------------------------
# FAMILY D — lens 0.5.2 passthroughs
# ---------------------------------------------------------------------------


class TestLens052Passthroughs:
    @pytest.fixture()
    def captured(self, monkeypatch):
        seen = {}

        def fake(query, args=None, prose=False, oversize=False):
            seen["query"] = query
            seen["args"] = list(args or [])
            seen["prose"] = prose
            return {"data": {}, "untrusted": {}, "meta": {}}

        monkeypatch.setattr(server, "_lens_request", fake)
        return seen

    def test_eligible_only_maps_to_the_daemon_flag(self, captured):
        server.lens_node(
            9, with_vitals=True, attacker_kami_index=15671, eligible_only=True
        )
        assert captured["args"] == [9, 15671, "--with-vitals", "--eligible-only"]

    def test_eligible_only_is_absent_by_default(self, captured):
        server.lens_node(9)
        assert "--eligible-only" not in captured["args"]

    def test_eligible_only_is_not_pre_validated(self, captured):
        """P5: the daemon owns the --with-vitals + attacker rule and
        answers BAD_ARGS for it. The harness must not second-guess it."""
        server.lens_node(9, eligible_only=True)
        assert captured["args"] == [9, "--eligible-only"]

    def test_identity_only_maps_to_slim(self, captured):
        server.lens_account("3379", identity_only=True)
        assert captured["args"] == ["3379", "--slim"]

    def test_identity_only_works_on_the_default_operator(self, captured):
        server.lens_account(identity_only=True)
        assert captured["args"] == ["--slim"]

    def test_identity_only_is_absent_by_default(self, captured):
        server.lens_account("3379")
        assert captured["args"] == ["3379"]

    def test_not_ready_is_its_own_error_class(self):
        err = server.LensNotReadyError("daemon not LIVE (SETUP 0%): mirror empty")
        assert isinstance(err, server.LensUnavailableError)
        assert err.daemon_state == "not-live"
        assert "mirror empty" in str(err)

    def test_not_ready_never_reads_as_a_missing_entity(self, monkeypatch):
        """The wedge this replaces answered `NOT_FOUND: node 9 not in
        mirror` at SETUP 0%, sending a caller to hunt a missing node."""
        assert issubclass(server.LensNotReadyError, server.LensUnavailableError)
        assert not issubclass(server.LensNotReadyError, server.LensQueryError)


class TestSurfaceAdditions:
    def test_the_new_optional_params_are_portable_and_default_off(self):
        tools = {t.name: t for t in server.mcp._tool_manager.list_tools()}
        for tool, param in (
            ("lens_node", "eligible_only"),
            ("lens_account", "identity_only"),
        ):
            schema = tools[tool].parameters["properties"][param]
            assert schema == {"default": False, "type": "boolean"}
            assert param not in tools[tool].parameters.get("required", [])

    def test_travel_to_room_gained_no_flag(self):
        """Gates are evaluated, not flagged past: an `allow_gated` escape
        hatch would have been a parameter an agent calling with defaults
        never finds (P1 — routing lives in descriptions)."""
        tools = {t.name: t for t in server.mcp._tool_manager.list_tools()}
        props = tools["travel_to_room"].parameters["properties"]
        assert "allow_gated" not in props

    def test_lens_status_names_both_degraded_arrays(self):
        tools = {t.name: t for t in server.mcp._tool_manager.list_tools()}
        d = tools["lens_status"].description
        assert "degraded and feedsDegraded" in d

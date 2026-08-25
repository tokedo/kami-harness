"""Contract checks for the 3.0.0 change families.

Five families land here: multi-transaction hash integrity (A), the pool
availability read (B), the travel-planner state source (C), the
error-snippet true-ups (D), and the surface additions (E).

Every snippet assertion is made in BOTH flag polarities. With
KAMI_ERROR_SNIPPETS off the message must be exactly the pre-snippet text
— the flag buys facts, never a different failure — and with it on the
appended block must state only what this module actually read.
"""

import asyncio
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
    monkeypatch.setattr(
        server, "_require_registered_operator", lambda a: FAKE_ACCOUNT_ID
    )
    monkeypatch.setattr(server, "_kami_owner_id", lambda k: FAKE_ACCOUNT_ID)
    monkeypatch.setattr(server, "_kami_state", lambda k: "RESTING")
    monkeypatch.setattr(server, "_harvest_state", lambda k: "")
    monkeypatch.setattr(server, "_account_entity_id", lambda a: FAKE_ACCOUNT_ID)
    monkeypatch.setattr(
        server, "_account_view",
        lambda aid: {"index": 1, "name": "t", "stamina": 100, "room": 47},
    )


def _revert(message):
    def boom(*a, **k):
        raise server.PreTxValidationError(
            f"transaction dry-run reverted: {message}"
        )
    return boom


# ---------------------------------------------------------------------------
# Family A — multi-transaction hash integrity
# ---------------------------------------------------------------------------

class TestRevealedLootDecode:
    """A2: the reveal's own receipt says what dropped.

    The payload layout is pinned against three production reveals on
    Yominet (0x4f27a529 block 32564363 -> 1x item 1005; 0x7a327d5c ->
    1x 11302; 0x990e6991 -> 1x 1002), each cross-checked against the
    same receipt's inventory component writes.
    """

    @staticmethod
    def _receipt(keys, amounts, topic=None):
        head = topic or ("0x" + server._DROPTABLE_EVENT_TOPIC)
        words = [0x40, 0x120, 0, 0, 0, 0, 0, 0, 0, 0]
        words += [len(keys)] + list(keys) + [len(amounts)] + list(amounts)
        data = b"".join(w.to_bytes(32, "big") for w in words)
        return SimpleNamespace(
            logs=[SimpleNamespace(topics=[head], data=data)]
        )

    def test_production_shape_decodes_to_the_one_item_that_dropped(
        self, monkeypatch
    ):
        monkeypatch.setattr(server, "_get_item_name", lambda i: f"item{i}")
        r = self._receipt([1002, 1005, 11302], [0, 1, 0])
        assert server._extract_revealed_items(r) == [
            {"item_index": 1005, "item_name": "item1005", "amount": 1}
        ]

    def test_zero_rolls_are_not_drops(self, monkeypatch):
        monkeypatch.setattr(server, "_get_item_name", lambda i: "x")
        r = self._receipt([1002, 1005], [0, 0])
        assert server._extract_revealed_items(r) == []

    def test_unrelated_topic_is_ignored(self, monkeypatch):
        monkeypatch.setattr(server, "_get_item_name", lambda i: "x")
        r = self._receipt([1002], [1], topic="0x" + "ab" * 32)
        assert server._extract_revealed_items(r) == []

    def test_unrecognised_payload_yields_nothing_rather_than_a_guess(self):
        r = SimpleNamespace(
            logs=[SimpleNamespace(
                topics=["0x" + server._DROPTABLE_EVENT_TOPIC],
                data=b"\x01" * 96,
            )]
        )
        assert server._extract_revealed_items(r) == []

    def test_an_entity_sized_key_is_not_an_item_index(self, monkeypatch):
        """The commit-id payload wears the same array shape; item
        indices are uint32, so an entity id disqualifies the match."""
        monkeypatch.setattr(server, "_get_item_name", lambda i: "x")
        r = self._receipt([2 ** 200], [1])
        assert server._extract_revealed_items(r) == []


class TestFailedLegsCarryTheirHash:
    """A3: a leg that landed and reverted is a transaction and is
    reported as one, in a structured field rather than error prose."""

    def test_reverted_leg_is_recorded(self):
        txs = []
        server._record_failed_leg(
            txs,
            server.OnChainRevertError("0xdead", 9, 100, "boom"),
            step="reveal",
        )
        assert txs == [{
            "step": "reveal", "tx_hash": "0xdead", "status": "reverted",
            "block": 9, "gas_used": 100,
        }]

    def test_a_failure_that_never_reached_the_chain_adds_no_row(self):
        txs = []
        server._record_failed_leg(txs, server.PreTxValidationError("nope"))
        assert txs == []

    def test_hash_fields_never_overwrite_a_documented_item_status(self):
        fields = server._failed_tx_hash_fields(
            server.OnChainRevertError("0xdead", 9, 100, None)
        )
        assert "status" not in fields
        assert fields["tx_hash"] == "0xdead"


# ---------------------------------------------------------------------------
# Family B — pool availability
# ---------------------------------------------------------------------------

class TestPoolDisabled:
    """B1/B2: the gate is the pool entity's own IsDisabled component.

    Absence means enabled — the admin setter removes the entry rather
    than storing false — so presence is the whole read. There is no
    world-config enable flag for pools; a name of that shape does not
    exist on-chain, and reading one would return the same 0 an absent
    field returns.
    """

    def test_no_pool_config_flag_is_read_anywhere(self):
        src = server.__file__
        text = open(src).read()
        assert "POOL_ENABLED" not in text
        assert "POOL_SWAP_ENABLED" not in text

    def test_quote_carries_the_pools_own_switch(self, monkeypatch):
        monkeypatch.setattr(server, "_get_item_name", lambda i: f"i{i}")
        monkeypatch.setattr(
            server, "_require_pool", lambda a, b: (0xABC, 1000, 500, 30)
        )
        monkeypatch.setattr(server, "_pool_disabled", lambda pid: True)
        q = server._pool_quote(1, 1005, 10, 100)
        assert q["disabled"] is True
        assert q["amount_out"] > 0  # a disabled pool still prices

    def test_swap_snippet_names_the_disabled_pool(
        self, snippets_on, world, monkeypatch
    ):
        monkeypatch.setattr(server, "_get_item_name", lambda i: f"i{i}")
        monkeypatch.setattr(
            server, "_require_pool", lambda a, b: (0xABC, 1000, 500, 30)
        )
        monkeypatch.setattr(server, "_pool_disabled", lambda pid: True)
        monkeypatch.setattr(server, "_pool_entity_id", lambda a, b: 0xABC)
        monkeypatch.setattr(server, "_require_item_balance", lambda *a: 999)
        monkeypatch.setattr(server, "_send_tx", _revert("Reverted"))
        with pytest.raises(server.PreTxValidationError) as ei:
            server.pool_swap(1, 1005, 10, 1, account="testa")
        msg = str(ei.value)
        assert msg.startswith(
            PREFIX + "transaction dry-run reverted: Reverted"
        )
        assert "Pool 0xabc (items 1/1005): disabled." in msg
        assert "liquidity removal is not gated on it" in msg

    def test_swap_message_is_unchanged_with_the_flag_off(
        self, snippets_off, world, monkeypatch
    ):
        monkeypatch.setattr(server, "_get_item_name", lambda i: f"i{i}")
        monkeypatch.setattr(
            server, "_require_pool", lambda a, b: (0xABC, 1000, 500, 30)
        )
        monkeypatch.setattr(server, "_pool_disabled", lambda pid: True)
        monkeypatch.setattr(server, "_require_item_balance", lambda *a: 999)
        monkeypatch.setattr(server, "_send_tx", _revert("Reverted"))
        with pytest.raises(server.PreTxValidationError) as ei:
            server.pool_swap(1, 1005, 10, 1, account="testa")
        assert str(ei.value) == (
            PREFIX + "transaction dry-run reverted: Reverted"
        )

    def test_an_enabled_pool_adds_nothing(
        self, snippets_on, world, monkeypatch
    ):
        monkeypatch.setattr(server, "_get_item_name", lambda i: f"i{i}")
        monkeypatch.setattr(
            server, "_require_pool", lambda a, b: (0xABC, 1000, 500, 30)
        )
        monkeypatch.setattr(server, "_pool_disabled", lambda pid: False)
        monkeypatch.setattr(server, "_require_item_balance", lambda *a: 999)
        monkeypatch.setattr(server, "_send_tx", _revert("Reverted"))
        with pytest.raises(server.PreTxValidationError) as ei:
            server.pool_swap(1, 1005, 10, 1, account="testa")
        assert "disabled" not in str(ei.value)


# ---------------------------------------------------------------------------
# Family C — the travel planner
# ---------------------------------------------------------------------------

class TestTravelReadsChainState:
    """C1/C2/C3: room and stamina come from the chain getter, the read
    error is never silent, and no item is spent without a deficit."""

    def test_plan_uses_the_getter_not_a_cached_endpoint(
        self, accounts, monkeypatch
    ):
        monkeypatch.setattr(
            server, "_require_registered_operator", lambda a: FAKE_ACCOUNT_ID
        )
        monkeypatch.setattr(
            server, "_read_account_view",
            lambda aid: ({"index": 1, "name": "t", "stamina": 100,
                          "room": 1}, ""),
        )
        monkeypatch.setattr(server, "_sp_item_balances", lambda aid: [])
        monkeypatch.setattr(
            server, "rooms_graph",
            SimpleNamespace(
                shortest_path=lambda a, b: [1, 2, 3],
                move_cost=lambda p: 5 * (len(p) - 1),
            ),
        )
        r = asyncio.run(
            server.travel_to_room(3, account="testa", dry_run=True)
        )
        assert r["stamina_have"] == 100
        assert r["feasible"] is True
        assert r["plan"] == [
            {"type": "move", "room": 2}, {"type": "move", "room": 3},
        ]

    def test_no_item_is_spent_without_a_deficit(self, accounts, monkeypatch):
        """The trip needs 15 stamina and the account holds 100: the
        SP+ card stays in the inventory."""
        monkeypatch.setattr(
            server, "_require_registered_operator", lambda a: FAKE_ACCOUNT_ID
        )
        monkeypatch.setattr(
            server, "_read_account_view",
            lambda aid: ({"index": 1, "name": "t", "stamina": 100,
                          "room": 1}, ""),
        )
        monkeypatch.setattr(
            server, "_sp_item_balances",
            lambda aid: [{"itemIndex": 21204, "balance": 1, "name": "card"}],
        )
        monkeypatch.setattr(
            server, "rooms_graph",
            SimpleNamespace(
                shortest_path=lambda a, b: [1, 2, 3, 4],
                move_cost=lambda p: 5 * (len(p) - 1),
            ),
        )
        r = asyncio.run(
            server.travel_to_room(
                4, account="testa", dry_run=True, use_items=True
            )
        )
        assert r["items_to_use"] == []
        assert r["feasible"] is True

    def test_use_items_defaults_to_false(self):
        tools = {t.name: t for t in server.mcp._tool_manager.list_tools()}
        props = tools["travel_to_room"].parameters["properties"]
        assert props["use_items"]["default"] is False

    def test_a_read_failure_names_its_cause(self, accounts, monkeypatch):
        """The failure used to report an empty string after the colon,
        and the arm lost pathfinding with no way to know why."""
        monkeypatch.setattr(
            server, "_require_registered_operator", lambda a: FAKE_ACCOUNT_ID
        )

        def blank(aid):
            raise ConnectionError("")

        monkeypatch.setattr(server, "_account_view", blank)
        monkeypatch.setattr(server.time, "sleep", lambda s: None)
        r = asyncio.run(server.travel_to_room(3, account="testa"))
        assert r["error"] == (
            "failed to read account state: ConnectionError"
        )

    def test_the_state_read_is_retried_once(self, accounts, monkeypatch):
        calls = []

        def flaky(aid):
            calls.append(1)
            if len(calls) == 1:
                raise ConnectionError("transient")
            return {"index": 1, "name": "t", "stamina": 50, "room": 1}

        monkeypatch.setattr(server, "_account_view", flaky)
        monkeypatch.setattr(server.time, "sleep", lambda s: None)
        view, err = server._read_account_view(FAKE_ACCOUNT_ID)
        assert len(calls) == 2 and err == ""
        assert view["room"] == 1


class TestUnreachableRoomSnippet:
    """C4 + F6: the re-raise used to drop the snippet entirely on this
    path. The adjacency it now adds is catalog data, and says so."""

    def _setup(self, monkeypatch):
        monkeypatch.setattr(
            server, "_require_registered_operator", lambda a: FAKE_ACCOUNT_ID
        )
        monkeypatch.setattr(
            server, "_account_view",
            lambda aid: {"index": 1, "name": "t", "stamina": 100, "room": 47},
        )
        monkeypatch.setattr(
            server, "_send_tx", _revert("AccMove: unreachable room")
        )

    def test_names_the_catalog_neighbours(
        self, snippets_on, accounts, monkeypatch
    ):
        self._setup(monkeypatch)
        with pytest.raises(server.PreTxValidationError) as ei:
            server.move_to_room(30, account="testa")
        msg = str(ei.value)
        assert msg.startswith(
            PREFIX + "room 30 is not connected to the account's current "
            "room 47; transaction dry-run reverted: AccMove: unreachable room"
        )
        assert (
            "catalogs/rooms.csv lists rooms adjacent to 47 as: 4, 31." in msg
        )

    def test_flag_off_is_the_pre_snippet_message(
        self, snippets_off, accounts, monkeypatch
    ):
        self._setup(monkeypatch)
        with pytest.raises(server.PreTxValidationError) as ei:
            server.move_to_room(30, account="testa")
        assert str(ei.value) == (
            PREFIX + "room 30 is not connected to the account's current "
            "room 47; transaction dry-run reverted: AccMove: unreachable room"
        )


# ---------------------------------------------------------------------------
# Family D — snippet true-ups
# ---------------------------------------------------------------------------

class TestLevelUpReportsXp:
    """D1: the harness's only leveling failure on record named XP as
    unread. It reads it now — and states no requirement, because the XP
    a level costs is the leveling formula, which this module does not
    hold."""

    def _setup(self, monkeypatch):
        monkeypatch.setattr(
            server, "_require_registered_operator", lambda a: FAKE_ACCOUNT_ID
        )
        monkeypatch.setattr(server, "_require_kamis_owned", lambda *a: [])
        monkeypatch.setattr(server, "_kami_state", lambda k: "RESTING")
        monkeypatch.setattr(server, "_harvest_state", lambda k: "")
        monkeypatch.setattr(server, "_account_entity_id", lambda a: FAKE_ACCOUNT_ID)
        monkeypatch.setattr(
            server, "_account_view",
            lambda aid: {"index": 1, "name": "t", "stamina": 100, "room": 47},
        )
        monkeypatch.setattr(
            server, "_kami_progress", lambda k: {"level": 10, "xp": 670}
        )
        monkeypatch.setattr(server, "_send_tx", _revert("insufficient xp"))

    def test_states_level_and_xp_and_stops_calling_xp_unread(
        self, snippets_on, accounts, monkeypatch
    ):
        self._setup(monkeypatch)
        with pytest.raises(server.PreTxValidationError) as ei:
            server.level_up_kami(703, account="testa")
        msg = str(ei.value)
        assert "kami #703: state RESTING, level 10, xp 670." in msg
        assert (
            "Not read by the harness for this call: cooldowns, HP, "
            "node/room match." in msg
        )
        assert "XP." not in msg.split("[mechanics]")[1]
        # No requirement is stated: that would be the leveling formula.
        assert "requires" not in msg.split("[mechanics]")[1]

    def test_flag_off_is_the_chain_reason_alone(
        self, snippets_off, accounts, monkeypatch
    ):
        self._setup(monkeypatch)
        with pytest.raises(server.PreTxValidationError) as ei:
            server.level_up_kami(703, account="testa")
        assert str(ei.value) == (
            PREFIX + "transaction dry-run reverted: insufficient xp"
        )

    def test_an_unreadable_progress_read_leaves_the_error_alone(
        self, snippets_on, accounts, monkeypatch
    ):
        self._setup(monkeypatch)

        def boom(k):
            raise RuntimeError("rpc down")

        monkeypatch.setattr(server, "_kami_progress", boom)
        with pytest.raises(server.PreTxValidationError) as ei:
            server.level_up_kami(703, account="testa")
        assert "level" not in str(ei.value)


class TestWholeLotTake:
    """D2: a right belief ("likely insufficient balance") was overwritten
    by a wrong one ("systemic bug") because the error never named the
    balance. It names it before signing now."""

    def _setup(self, monkeypatch, held):
        monkeypatch.setattr(server, "_get_item_name", lambda i: "MUSU")
        monkeypatch.setattr(server, "_account_entity_id", lambda a: FAKE_ACCOUNT_ID)
        monkeypatch.setattr(
            server, "_trade_terms",
            lambda t: {"state": "PENDING", "pay_item": 1,
                       "pay_amount": 128569},
        )
        monkeypatch.setattr(server, "_inventory_balance", lambda h, i: held)

    def test_unaffordable_take_names_cost_and_holding(
        self, accounts, monkeypatch
    ):
        self._setup(monkeypatch, 415)
        sent = []
        monkeypatch.setattr(
            server, "_send_tx_owner", lambda *a, **k: sent.append(1)
        )
        with pytest.raises(server.PreTxValidationError) as ei:
            server.take_trade("0x2a", account="testa")
        msg = str(ei.value)
        assert "fills the whole lot" in msg
        assert "costs 128,569 of item 1 (MUSU)" in msg
        assert "holds 415" in msg
        assert sent == []  # nothing was signed

    def test_an_affordable_take_is_not_blocked(self, accounts, monkeypatch):
        self._setup(monkeypatch, 200000)
        monkeypatch.setattr(
            server, "_send_tx_owner", lambda *a, **k: {"status": "success"}
        )
        assert server.take_trade("0x2a", account="testa")["status"] == "success"

    def test_unreadable_terms_do_not_block_the_call(
        self, accounts, monkeypatch
    ):
        """A gate that cannot read its precondition must not invent one."""
        monkeypatch.setattr(server, "_trade_terms", lambda t: None)
        monkeypatch.setattr(
            server, "_send_tx_owner", lambda *a, **k: {"status": "success"}
        )
        assert server.take_trade("0x2a", account="testa")["status"] == "success"


class TestAuctionHoldings:
    """D2 (auction half): the same underflow class. The GDA price is a
    curve this module does not hold, so no cost is stated — only what
    the auction charges in and what the account holds."""

    def _setup(self, monkeypatch):
        monkeypatch.setattr(server, "_get_item_name", lambda i: "Onyx Shard")
        monkeypatch.setattr(server, "_account_entity_id", lambda a: FAKE_ACCOUNT_ID)
        monkeypatch.setattr(server, "_auction_currency", lambda i: 100)
        monkeypatch.setattr(server, "_inventory_balance", lambda h, i: 415)
        monkeypatch.setattr(
            server, "_account_view",
            lambda aid: {"index": 1, "name": "t", "stamina": 100, "room": 66},
        )
        monkeypatch.setattr(
            server, "_send_tx_owner",
            _revert("arithmetic underflow or overflow"),
        )

    def test_names_the_currency_and_the_holding(
        self, snippets_on, accounts, monkeypatch
    ):
        self._setup(monkeypatch)
        with pytest.raises(server.PreTxValidationError) as ei:
            server.auction_buy(11, 1, account="testa")
        msg = str(ei.value)
        assert "holds 415 of item 100 (Onyx Shard)." in msg
        # The price is never guessed at.
        assert "price" not in msg.split("[mechanics]")[1]

    def test_flag_off_is_unchanged(self, snippets_off, accounts, monkeypatch):
        self._setup(monkeypatch)
        with pytest.raises(server.PreTxValidationError) as ei:
            server.auction_buy(11, 1, account="testa")
        assert str(ei.value) == (
            PREFIX
            + "transaction dry-run reverted: arithmetic underflow or overflow"
        )


class TestHarvestGatesReportedTogether:
    """D4: "kami on cooldown" masked "kami too far" through a 14-hop
    round trip. The room half is stated alongside, from the node-index
    convention this tool's own description states."""

    def _setup(self, monkeypatch):
        monkeypatch.setattr(
            server, "_require_registered_operator", lambda a: FAKE_ACCOUNT_ID
        )
        monkeypatch.setattr(server, "_require_kamis_owned", lambda *a: [])
        monkeypatch.setattr(server, "_kami_state", lambda k: "RESTING")
        monkeypatch.setattr(server, "_harvest_state", lambda k: "")
        monkeypatch.setattr(server, "_account_entity_id", lambda a: FAKE_ACCOUNT_ID)
        monkeypatch.setattr(
            server, "_account_view",
            lambda aid: {"index": 1, "name": "t", "stamina": 100, "room": 47},
        )
        monkeypatch.setattr(server, "_send_tx", _revert("kami on cooldown"))

    def test_room_and_node_are_both_named(
        self, snippets_on, accounts, monkeypatch
    ):
        self._setup(monkeypatch)
        with pytest.raises(server.PreTxValidationError) as ei:
            server.harvest_start([45], 34, account="testa")
        msg = str(ei.value)
        assert "account 'testa': room 47, stamina 100." in msg
        assert "Node 34 is in room 34." in msg
        assert (
            "Not read by the harness for this call: cooldowns, HP, XP." in msg
        )

    def test_flag_off_is_the_chain_reason_alone(
        self, snippets_off, accounts, monkeypatch
    ):
        self._setup(monkeypatch)
        with pytest.raises(server.PreTxValidationError) as ei:
            server.harvest_start([45], 34, account="testa")
        assert str(ei.value) == (
            PREFIX + "transaction dry-run reverted: kami on cooldown"
        )


# ---------------------------------------------------------------------------
# Family E — surface true-ups
# ---------------------------------------------------------------------------

class TestStrategyStatusSummary:
    """E2: the endpoint answers globally. 23 of 23 calls were capped by
    the client last run, so the agent never saw a complete answer."""

    PAYLOAD = {"statuses": [
        {"kami_id": 45, "status": "running", "state": "healthy",
         "health": "ok", "container_id": "c1", "uptime": 900},
        {"kami_id": 46, "status": "stopped", "state": "exited",
         "health": "bad", "container_id": "c2", "uptime": 0},
        {"kami_id": 999, "status": "running", "state": "healthy",
         "health": "ok", "container_id": "c3", "uptime": 5},
    ]}

    def _setup(self, monkeypatch, payload=None):
        async def api(*a, **k):
            return payload if payload is not None else self.PAYLOAD

        monkeypatch.setattr(server, "_strategy_api", api)
        monkeypatch.setattr(server, "_account_entity_id", lambda a: FAKE_ACCOUNT_ID)
        monkeypatch.setattr(
            server, "_owned_kami_indices", lambda aid: {45, 46}
        )

    def test_default_is_one_row_per_owned_kami(self, monkeypatch):
        self._setup(monkeypatch)
        r = asyncio.run(server.get_all_strategy_statuses(account="testa"))
        assert r["shown"] == 2 and r["upstream_rows"] == 3
        assert r["strategies"] == [
            {"kami_id": 45, "status": "running", "state": "healthy",
             "health": "ok"},
            {"kami_id": 46, "status": "stopped", "state": "exited",
             "health": "bad"},
        ]

    def test_full_returns_the_upstream_answer_verbatim(self, monkeypatch):
        self._setup(monkeypatch)
        r = asyncio.run(
            server.get_all_strategy_statuses(account="testa", full=True)
        )
        assert r == self.PAYLOAD

    def test_an_unrecognised_shape_is_passed_through_whole(self, monkeypatch):
        odd = {"totally": "different"}
        self._setup(monkeypatch, odd)
        assert asyncio.run(
            server.get_all_strategy_statuses(account="testa")
        ) == odd

    def test_an_unreadable_ownership_read_passes_through(self, monkeypatch):
        self._setup(monkeypatch)

        def boom(aid):
            raise RuntimeError("rpc down")

        monkeypatch.setattr(server, "_owned_kami_indices", boom)
        assert asyncio.run(
            server.get_all_strategy_statuses(account="testa")
        ) == self.PAYLOAD

    def test_the_docstring_no_longer_claims_the_endpoint_is_scoped(self):
        tools = {t.name: t for t in server.mcp._tool_manager.list_tools()}
        d = tools["get_all_strategy_statuses"].description
        assert "GLOBAL" in d
        assert "every Kamibots strategy on this account" not in d


class TestLensRoster:
    """E1: agents saw the scaffold's roster call succeed and tried to
    call it; it was not a tool."""

    def test_is_a_one_to_one_wrapper(self, monkeypatch):
        seen = {}

        def fake(query, args=None, **kw):
            seen["q"], seen["a"] = query, args
            return {"data": 1, "untrusted": [], "meta": {}}

        monkeypatch.setattr(server, "_lens_request", fake)
        assert server.lens_roster(7)["data"] == 1
        assert seen == {"q": "roster", "a": [7]}
        server.lens_roster()
        assert seen["a"] == []

    def test_is_registered_perceive_with_both_standing_sentences(self):
        tools = {t.name: t for t in server.mcp._tool_manager.list_tools()}
        d = tools["lens_roster"].description
        assert server.TOOL_CLASSES["lens_roster"] == "PERCEIVE"
        assert "lens_roster" in server.READ_TOOLS
        assert server._LENS_SERVING_SENTENCE in d
        assert server._UNTRUSTED_STANDING_SENTENCE in d


class TestTransientRpcClasses:
    """E3: a refused eth_call is not a reverted one, and a stale
    sequence is a pre-broadcast rejection that nothing landed for."""

    def test_invalid_height_is_infra_not_a_revert(self):
        text = (
            "failed to load state at height 32564363; historical version "
            "not found: 32564363: invalid height (latest height: "
            "32568880): invalid request"
        )
        assert server._is_replay_infra_error(text)

    def test_dry_run_retries_a_refused_call_before_reporting(
        self, monkeypatch
    ):
        calls = []

        class Fn:
            args = [1]

            def call(self, params=None):
                calls.append(1)
                if len(calls) == 1:
                    raise ValueError({
                        "code": -32000,
                        "message": "historical version not ready",
                    })
                return b""

        monkeypatch.setattr(server.time, "sleep", lambda s: None)
        server._dry_run(Fn(), "0xabc")  # must not raise
        assert len(calls) == 2

    def test_a_persistently_refused_call_still_reports(self, monkeypatch):
        class Fn:
            args = [1]

            def call(self, params=None):
                raise ValueError({
                    "code": -32000, "message": "invalid height",
                })

        monkeypatch.setattr(server.time, "sleep", lambda s: None)
        with pytest.raises(server.PreTxValidationError):
            server._dry_run(Fn(), "0xabc")

    def test_sequence_mismatch_is_in_the_retry_class(self):
        assert "account sequence mismatch" in server._RETRY_ROUTING_MARKERS
        assert server._RETRY_ROUTING_MARKER in server._RETRY_ROUTING_MARKERS

    def test_a_snippet_never_introduces_a_retry_marker(
        self, snippets_on, monkeypatch
    ):
        """A snippet that echoed a routing marker into an error would
        turn a final failure into a retried one."""
        monkeypatch.setattr(
            server, "_kami_state", lambda k: "account sequence mismatch"
        )
        monkeypatch.setattr(server, "_harvest_state", lambda k: "")
        assert server._mechanics_snippet(
            subjects=[{"kami_id": 45}]
        ) == ""


class TestHandshakeProvenance:
    """The snippet flag changes no schema, description or hash, so a
    client cannot infer it from the surface."""

    def test_instructions_carry_version_and_capability(self):
        i = server.mcp._mcp_server.instructions
        assert f"tools_hash={server.TOOLS_HASH}" in i
        assert f"schema_version={server.SCHEMA_VERSION}" in i
        assert "error_snippets=" in i

"""Offline tests for the v1.4.0 pre-transaction validation layer.

Every gate is exercised happy + failure: the sender-level gates
(registration, gas balance, dry-run, empty batch), the per-tool
prechecks (harvest, quests, move, item/feed/level, buy_kami,
scavenge/droptable), the revive_kami path argument, and the error
format (stable "validation failed; no transaction sent:" prefix,
observed-vs-required values). Chain access is faked; no keys or
network.
"""

import asyncio
from types import SimpleNamespace

import pytest
from web3 import Web3

from conftest import FAKE_ACCOUNT_ID, FakeContract

import server

PREFIX = server.PreTxValidationError.PREFIX


@pytest.fixture(autouse=True)
def _fresh_registration_caches(monkeypatch):
    """Registration caches are process-global; isolate them per test."""
    monkeypatch.setattr(server, "_operator_account_cache", {})
    monkeypatch.setattr(server, "_owner_registered_cache", set())


# ---------------------------------------------------------------------------
# Sender-level gates (_send_tx / _send_tx_owner / _send_batch_tx)
# ---------------------------------------------------------------------------


class _BoundFn:
    def __init__(self, handler, args):
        self._handler = handler
        self._args = args

    def call(self, params=None):
        return self._handler(*self._args)

    def build_transaction(self, params):
        return {"built": True, **params}


class FakeTxContract:
    """Contract stub whose bound functions support call() AND
    build_transaction() — enough to drive the real sender code path."""

    def __init__(self, handlers):
        contract = self

        class _Functions:
            def __getattr__(self, fn_name):
                handler = contract._handlers[fn_name]
                return lambda *args: _BoundFn(handler, args)

        self._handlers = handlers
        self.functions = _Functions()


@pytest.fixture()
def txchain(monkeypatch, accounts):
    """Full fake send path: registry-backed contracts, balances, and a
    receipt-returning broadcast. Returns a namespace for adjustment."""
    registry: dict[str, object] = {}
    balances: dict[str, int] = {}
    broadcasts: list[bytes] = []
    receipt = SimpleNamespace(
        transactionHash=b"\xab" * 32, status=1, blockNumber=123, gasUsed=42
    )

    eth = SimpleNamespace(
        contract=lambda address=None, abi=None: registry[address],
        get_balance=lambda a: balances.get(a, 10**18),
        get_transaction_count=lambda a: 7,
        send_raw_transaction=lambda raw: broadcasts.append(raw) or b"\x01" * 32,
        wait_for_transaction_receipt=lambda h, timeout=None: receipt,
        account=SimpleNamespace(
            sign_transaction=lambda tx, private_key=None: SimpleNamespace(
                raw_transaction=b"rawtx"
            )
        ),
    )
    fake_w3 = SimpleNamespace(eth=eth, from_wei=Web3.from_wei, to_wei=Web3.to_wei)
    monkeypatch.setattr(server, "w3", fake_w3)
    monkeypatch.setattr(server, "_resolve_system", lambda sid: sid)
    monkeypatch.setattr(server, "_resolve_component", lambda cid: cid)

    # Operator of "testa" is registered by default.
    registry["component.address.operator"] = FakeContract(
        {"getEntitiesWithValue": lambda v: [FAKE_ACCOUNT_ID]}
    )
    registry["component.name"] = FakeContract({"safeGet": lambda e: "testa"})

    return SimpleNamespace(
        registry=registry, balances=balances, broadcasts=broadcasts
    )


class TestSendTxGates:
    def test_happy_path_broadcasts(self, accounts, txchain):
        txchain.registry["system.account.move"] = FakeTxContract(
            {"executeTyped": lambda room: b""}
        )
        r = server._send_tx(
            "testa", "system.account.move", server._ABI_MOVE, [4],
            gas_limit=100_000,
        )
        assert r["status"] == "success"
        assert len(txchain.broadcasts) == 1

    def test_unregistered_operator_blocks(self, accounts, txchain):
        txchain.registry["component.address.operator"] = FakeContract(
            {"getEntitiesWithValue": lambda v: []}
        )
        txchain.registry["system.account.move"] = FakeTxContract(
            {"executeTyped": lambda room: b""}
        )
        op = server._get_account("testa").operator_addr
        with pytest.raises(server.PreTxValidationError) as ei:
            server._send_tx(
                "testa", "system.account.move", server._ABI_MOVE, [4]
            )
        msg = str(ei.value)
        assert msg.startswith(PREFIX)
        assert f"no account is registered for operator {op}" in msg
        assert txchain.broadcasts == []

    def test_gas_balance_names_observed_vs_required(self, accounts, txchain):
        op = server._get_account("testa").operator_addr
        txchain.balances[op] = 10**9  # far below 3M gas at the flat price
        txchain.registry["system.harvest.start"] = FakeTxContract(
            {"executeTyped": lambda *a: b""}
        )
        with pytest.raises(server.PreTxValidationError) as ei:
            server._send_tx(
                "testa", "system.harvest.start", server._ABI_HARVEST_START,
                [1, 1, 0, 0], gas_limit=3_000_000,
            )
        msg = str(ei.value)
        assert f"operator wallet {op} holds 1E-9 ETH" in msg
        assert "gas limit 3000000 at the flat price" in msg
        assert txchain.broadcasts == []

    def test_zero_balance_without_gas_limit_blocks(self, accounts, txchain):
        op = server._get_account("testa").operator_addr
        txchain.balances[op] = 0
        txchain.registry["system.kami.level"] = FakeTxContract(
            {"executeTyped": lambda *a: b""}
        )
        with pytest.raises(server.PreTxValidationError, match="holds 0 ETH"):
            server._send_tx(
                "testa", "system.kami.level", server._ABI_LEVEL, [55]
            )
        assert txchain.broadcasts == []

    def test_dry_run_revert_blocks_with_reason(self, accounts, txchain):
        def revert(*a):
            raise ValueError(
                {"code": -32000, "message": "revert: kami not RESTING: Reverted"}
            )

        txchain.registry["system.harvest.start"] = FakeTxContract(
            {"executeTyped": revert}
        )
        with pytest.raises(server.PreTxValidationError) as ei:
            server._send_tx(
                "testa", "system.harvest.start", server._ABI_HARVEST_START,
                [1, 1, 0, 0], gas_limit=3_000_000,
            )
        msg = str(ei.value)
        assert "transaction dry-run reverted" in msg
        assert "revert: kami not RESTING: Reverted" in msg
        assert txchain.broadcasts == []

    def test_unknown_address_send_error_prepends_balance(
        self, accounts, txchain
    ):
        txchain.registry["system.account.move"] = FakeTxContract(
            {"executeTyped": lambda room: b""}
        )
        op = server._get_account("testa").operator_addr
        txchain.balances[op] = 10**18

        def reject(raw):
            raise ValueError(
                "account init1xyz does not exist: unknown address"
            )

        server.w3.eth.send_raw_transaction = reject
        with pytest.raises(ValueError) as ei:
            server._send_tx(
                "testa", "system.account.move", server._ABI_MOVE, [4],
                gas_limit=100_000,
            )
        msg = str(ei.value)
        assert f"operator wallet {op} (account 'testa') holds 1 ETH" in msg
        assert "unknown address" in msg  # raw RPC error preserved


class TestSendTxOwnerGates:
    def test_unregistered_owner_blocks(self, accounts, txchain):
        txchain.registry["component.name"] = FakeContract(
            {"safeGet": lambda e: ""}
        )
        txchain.registry["system.trade.create"] = FakeTxContract(
            {"executeTyped": lambda *a: b""}
        )
        owner = server._get_account("testa").owner_addr
        with pytest.raises(server.PreTxValidationError) as ei:
            server._send_tx_owner(
                "testa", "system.trade.create", server._ABI_TRADE_CREATE,
                [[1], [1], [2], [1], 0],
            )
        assert f"no account is registered for owner wallet {owner}" in str(
            ei.value
        )
        assert txchain.broadcasts == []

    def test_register_account_exempt_from_registration_gate(
        self, accounts, txchain
    ):
        # An unregistered owner must still be able to send the
        # registration transaction itself.
        txchain.registry["component.name"] = FakeContract(
            {"safeGet": lambda e: ""}
        )
        txchain.registry["system.account.register"] = FakeTxContract(
            {"executeTyped": lambda *a: b""}
        )
        r = server._send_tx_owner(
            "testa", "system.account.register",
            server._ABI_ACCOUNT_REGISTER, ["0x" + "11" * 20, "name"],
            gas_limit=2_000_000,
        )
        assert r["status"] == "success"
        assert len(txchain.broadcasts) == 1

    def test_value_counted_in_balance_gate(self, accounts, txchain):
        owner = server._get_account("testa").owner_addr
        txchain.balances[owner] = 10**18
        txchain.registry["system.kamimarket.buy"] = FakeTxContract(
            {"executeTyped": lambda *a: b""}
        )
        with pytest.raises(server.PreTxValidationError) as ei:
            server._send_tx_owner(
                "testa", "system.kamimarket.buy", server._ABI_KAMI_BUY,
                [[1]], gas_limit=2_000_000, value_wei=2 * 10**18,
            )
        msg = str(ei.value)
        assert "holds 1 ETH" in msg and "2 ETH value" in msg
        assert txchain.broadcasts == []


class TestSendBatchTxGates:
    def test_empty_target_array_blocks(self, accounts, txchain):
        txchain.registry["system.harvest.stop"] = FakeTxContract(
            {"executeBatched": lambda *a: b""}
        )
        with pytest.raises(server.PreTxValidationError) as ei:
            server._send_batch_tx(
                "testa", "system.harvest.stop", server._ABI_HARVEST_STOP,
                "executeBatched", [[]], 4_000_000,
            )
        msg = str(ei.value)
        assert msg.startswith(PREFIX)
        assert "batch target array is empty" in msg
        assert "on-chain no-op" in msg
        assert txchain.broadcasts == []

    def test_happy_batch_broadcasts(self, accounts, txchain):
        txchain.registry["system.harvest.stop"] = FakeTxContract(
            {"executeBatched": lambda ids: b""}
        )
        r = server._send_batch_tx(
            "testa", "system.harvest.stop", server._ABI_HARVEST_STOP,
            "executeBatched", [[111, 222]], 4_000_000,
        )
        assert r["status"] == "success"
        assert len(txchain.broadcasts) == 1


# ---------------------------------------------------------------------------
# Registration / state / holdings helpers against the fake chain
# ---------------------------------------------------------------------------


class TestRegistrationHelpers:
    def test_operator_lookup_and_cache(self, accounts, chain, monkeypatch):
        calls = []

        def entities(v):
            calls.append(v)
            return [FAKE_ACCOUNT_ID]

        chain["component.address.operator"] = FakeContract(
            {"getEntitiesWithValue": entities}
        )
        aid = server._require_registered_operator("testa")
        assert aid == FAKE_ACCOUNT_ID
        server._require_registered_operator("testa")  # cached
        assert len(calls) == 1

    def test_unregistered_operator_message(self, accounts, chain):
        chain["component.address.operator"] = FakeContract(
            {"getEntitiesWithValue": lambda v: []}
        )
        op = server._get_account("testa").operator_addr
        with pytest.raises(server.PreTxValidationError) as ei:
            server._require_registered_operator("testa")
        assert (
            f"no account is registered for operator {op} (account 'testa')"
            in str(ei.value)
        )

    def test_owner_gate_and_cache(self, accounts, chain):
        calls = []

        def name(e):
            calls.append(e)
            return "someone"

        chain["component.name"] = FakeContract({"safeGet": name})
        eid = server._require_registered_owner("testa")
        assert eid == int(server._get_account("testa").owner_addr, 16)
        server._require_registered_owner("testa")  # cached
        assert len(calls) == 1

    def test_owner_gate_unregistered(self, accounts, chain):
        chain["component.name"] = FakeContract({"safeGet": lambda e: ""})
        owner = server._get_account("testa").owner_addr
        with pytest.raises(server.PreTxValidationError) as ei:
            server._require_registered_owner("testa")
        assert f"no account is registered for owner wallet {owner}" in str(
            ei.value
        )


class TestStateHelpers:
    def test_inventory_balance_derivation(self, accounts, chain):
        seen = {}

        def value(entity):
            seen["entity"] = entity
            return 42

        chain["component.value"] = FakeContract({"safeGet": value})
        bal = server._inventory_balance(FAKE_ACCOUNT_ID, 100)
        assert bal == 42
        expected = int.from_bytes(
            Web3.solidity_keccak(
                ["string", "uint256", "uint32"],
                ["inventory.instance", FAKE_ACCOUNT_ID, 100],
            ),
            "big",
        )
        assert seen["entity"] == expected

    def test_account_view_shapes(self, accounts, chain):
        chain["system.getter"] = FakeContract(
            {"getAccount": lambda aid: (9, "tokedo", 27, 53)}
        )
        assert server._account_view(FAKE_ACCOUNT_ID) == {
            "index": 9, "name": "tokedo", "stamina": 27, "room": 53,
        }

    def test_account_view_revert_reads_none(self, accounts, chain):
        def boom(aid):
            raise ValueError({"code": -32000, "message": "Reverted"})

        chain["system.getter"] = FakeContract({"getAccount": boom})
        assert server._account_view(FAKE_ACCOUNT_ID) is None

    def test_kami_state_and_harvest_state(self, accounts, chain):
        states = {
            server._kami_entity_id(45): "HARVESTING",
            server._harvest_entity_id(45): "ACTIVE",
        }
        chain["component.state"] = FakeContract(
            {"safeGet": lambda e: states.get(e, "")}
        )
        assert server._kami_state(45) == "HARVESTING"
        assert server._harvest_state(45) == "ACTIVE"
        assert server._harvest_state(46) == ""


# ---------------------------------------------------------------------------
# Harvest tools
# ---------------------------------------------------------------------------


class TestHarvestValidation:
    def test_start_empty(self, accounts, sent):
        with pytest.raises(server.PreTxValidationError, match="kami_ids is empty"):
            server.harvest_start([], 1, account="testa")
        assert sent == []

    def test_start_not_owned(self, accounts, validation_ok, sent, monkeypatch):
        monkeypatch.setattr(server, "_kami_owner_id", lambda k: 0xDEAD)
        with pytest.raises(server.PreTxValidationError) as ei:
            server.harvest_start([5], 1, account="testa")
        assert "kami #5 is not owned by account 'testa'" in str(ei.value)
        assert sent == []

    def test_start_wrong_state(self, accounts, validation_ok, sent, monkeypatch):
        monkeypatch.setattr(server, "_kami_state", lambda k: "HARVESTING")
        with pytest.raises(server.PreTxValidationError) as ei:
            server.harvest_start([5], 1, account="testa")
        assert "kami #5 is HARVESTING; harvest_start requires RESTING" in str(
            ei.value
        )
        assert sent == []

    def test_start_reports_all_failing_kamis(
        self, accounts, validation_ok, sent, monkeypatch
    ):
        monkeypatch.setattr(
            server, "_kami_state",
            lambda k: "RESTING" if k == 5 else "DEAD",
        )
        with pytest.raises(server.PreTxValidationError) as ei:
            server.harvest_start([5, 6, 7], 1, account="testa")
        msg = str(ei.value)
        assert "kami #6 is DEAD" in msg and "kami #7 is DEAD" in msg
        assert sent == []

    def test_start_happy_single_and_batch(self, accounts, validation_ok, sent):
        server.harvest_start([5], 1, account="testa")
        assert sent[-1]["system"] == "system.harvest.start"
        server.harvest_start([5, 6], 1, account="testa")
        assert sent[-1]["fn_name"] == "executeBatched"

    @pytest.mark.parametrize("tool,action", [
        (server.harvest_stop, "harvest_stop"),
        (server.harvest_collect, "harvest_collect"),
    ])
    def test_stop_collect_empty(self, accounts, sent, tool, action):
        with pytest.raises(server.PreTxValidationError, match=action):
            tool([], account="testa")
        assert sent == []

    @pytest.mark.parametrize("tool", [server.harvest_stop, server.harvest_collect])
    def test_stop_collect_no_active_harvest(
        self, accounts, validation_ok, sent, monkeypatch, tool
    ):
        monkeypatch.setattr(server, "_harvest_state", lambda k: "")
        with pytest.raises(server.PreTxValidationError) as ei:
            tool([5], account="testa")
        assert (
            "no active harvest exists for kami #5; its harvest entity "
            "state is ''" in str(ei.value)
        )
        assert sent == []

    def test_stop_not_owned(self, accounts, validation_ok, sent, monkeypatch):
        monkeypatch.setattr(server, "_kami_owner_id", lambda k: 0xDEAD)
        with pytest.raises(server.PreTxValidationError, match="not owned"):
            server.harvest_stop([5], account="testa")
        assert sent == []

    def test_stop_happy(self, accounts, validation_ok, sent):
        r = server.harvest_stop([5], account="testa")
        assert r["status"] == "success"
        assert sent[-1]["system"] == "system.harvest.stop"

    def test_stop_harvest_batch_empty(self, accounts, sent):
        with pytest.raises(
            server.PreTxValidationError, match="stop_harvest_batch"
        ):
            server.stop_harvest_batch([], account="testa")
        assert sent == []


# ---------------------------------------------------------------------------
# Movement
# ---------------------------------------------------------------------------


class TestMoveValidation:
    def test_already_in_room(self, accounts, validation_ok, sent, monkeypatch):
        monkeypatch.setattr(
            server, "_account_view",
            lambda aid: {"index": 1, "name": "t", "stamina": 50, "room": 4},
        )
        with pytest.raises(server.PreTxValidationError) as ei:
            server.move_to_room(4, account="testa")
        assert "account 'testa' is already in room 4" in str(ei.value)
        assert sent == []

    def test_insufficient_stamina(self, accounts, validation_ok, sent, monkeypatch):
        monkeypatch.setattr(
            server, "_account_view",
            lambda aid: {"index": 1, "name": "t", "stamina": 3, "room": 4},
        )
        with pytest.raises(server.PreTxValidationError) as ei:
            server.move_to_room(9, account="testa")
        assert "account stamina is 3; a room move requires 5" in str(ei.value)
        assert sent == []

    def test_unreachable_room_enriched(
        self, accounts, validation_ok, monkeypatch
    ):
        def revert_send(*a, **kw):
            raise server.PreTxValidationError(
                "transaction dry-run reverted: revert: AccMove: "
                "unreachable room: Reverted"
            )

        monkeypatch.setattr(server, "_send_tx", revert_send)
        with pytest.raises(server.PreTxValidationError) as ei:
            server.move_to_room(9, account="testa")
        msg = str(ei.value)
        assert (
            "room 9 is not connected to the account's current room 1" in msg
        )
        assert "AccMove: unreachable room" in msg  # raw reason preserved

    def test_happy_move(self, accounts, validation_ok, sent):
        r = server.move_to_room(9, account="testa")
        assert r["status"] == "success"
        assert sent[-1]["system"] == "system.account.move"

    def test_travel_requires_registration(self, accounts, monkeypatch):
        def unreg(account):
            raise server.PreTxValidationError(
                f"no account is registered for operator 0xAB (account "
                f"'{account}')"
            )

        monkeypatch.setattr(server, "_require_registered_operator", unreg)
        with pytest.raises(server.PreTxValidationError, match="no account"):
            asyncio.run(server.travel_to_room(9, account="testa"))


# ---------------------------------------------------------------------------
# Quests
# ---------------------------------------------------------------------------


class TestQuestValidation:
    def test_accept_already_accepted(
        self, accounts, validation_ok, sent, monkeypatch
    ):
        monkeypatch.setattr(
            server, "_quest_owned_completed", lambda q, a: (True, False)
        )
        with pytest.raises(server.PreTxValidationError) as ei:
            server.accept_quest(12, account="testa")
        assert "quest 12 is already accepted by account 'testa'" in str(
            ei.value
        )
        assert sent == []

    def test_accept_already_completed(
        self, accounts, validation_ok, sent, monkeypatch
    ):
        monkeypatch.setattr(
            server, "_quest_owned_completed", lambda q, a: (True, True)
        )
        with pytest.raises(server.PreTxValidationError) as ei:
            server.accept_quest(12, account="testa")
        assert "quest 12 is already completed by account 'testa'" in str(
            ei.value
        )
        assert sent == []

    def test_accept_happy(self, accounts, validation_ok, sent, monkeypatch):
        monkeypatch.setattr(
            server, "_quest_owned_completed", lambda q, a: (False, False)
        )
        r = server.accept_quest(12, account="testa")
        assert r["status"] == "success"
        assert sent[-1]["system"] == "system.quest.accept"

    def test_complete_not_accepted(
        self, accounts, validation_ok, sent, monkeypatch
    ):
        monkeypatch.setattr(
            server, "_quest_owned_completed", lambda q, a: (False, False)
        )
        with pytest.raises(server.PreTxValidationError) as ei:
            server.complete_quest(12, account="testa")
        assert (
            "quest 12 is not accepted by account 'testa'; complete_quest "
            "requires an accepted quest" in str(ei.value)
        )
        assert sent == []

    def test_complete_already_completed(
        self, accounts, validation_ok, sent, monkeypatch
    ):
        monkeypatch.setattr(
            server, "_quest_owned_completed", lambda q, a: (True, True)
        )
        with pytest.raises(
            server.PreTxValidationError, match="already completed"
        ):
            server.complete_quest(12, account="testa")
        assert sent == []

    def test_complete_happy(self, accounts, validation_ok, sent, monkeypatch):
        monkeypatch.setattr(
            server, "_quest_owned_completed", lambda q, a: (True, False)
        )
        r = server.complete_quest(12, account="testa")
        assert r["status"] == "success"
        # quest entity derived from the chain-resolved account id
        assert sent[-1]["args"] == [
            server._quest_entity_id(12, FAKE_ACCOUNT_ID)
        ]

    def test_drop_not_accepted(self, accounts, validation_ok, sent, monkeypatch):
        monkeypatch.setattr(
            server, "_quest_owned_completed", lambda q, a: (False, False)
        )
        with pytest.raises(server.PreTxValidationError, match="drop_quest"):
            server.drop_quest(12, account="testa")
        assert sent == []

    def test_drop_completed(self, accounts, validation_ok, sent, monkeypatch):
        monkeypatch.setattr(
            server, "_quest_owned_completed", lambda q, a: (True, True)
        )
        with pytest.raises(
            server.PreTxValidationError, match="cannot be dropped"
        ):
            server.drop_quest(12, account="testa")
        assert sent == []

    def test_drop_happy(self, accounts, validation_ok, sent, monkeypatch):
        monkeypatch.setattr(
            server, "_quest_owned_completed", lambda q, a: (True, False)
        )
        assert server.drop_quest(12, account="testa")["status"] == "success"


# ---------------------------------------------------------------------------
# Items / feeding / leveling / naming
# ---------------------------------------------------------------------------


class TestItemValidation:
    def test_feed_kami_not_owned(self, accounts, validation_ok, sent, monkeypatch):
        monkeypatch.setattr(server, "_kami_owner_id", lambda k: 0xDEAD)
        with pytest.raises(server.PreTxValidationError, match="not owned"):
            server.feed_kami(45, 11301, account="testa")
        assert sent == []

    def test_feed_kami_no_holdings(self, accounts, validation_ok, sent, monkeypatch):
        monkeypatch.setattr(server, "_inventory_balance", lambda h, i: 0)
        with pytest.raises(server.PreTxValidationError) as ei:
            server.feed_kami(45, 11301, account="testa")
        msg = str(ei.value)
        assert "account 'testa' holds 0 of item 11301" in msg
        assert "feed_kami requires 1" in msg
        assert sent == []

    def test_feed_kami_happy(self, accounts, validation_ok, sent):
        r = server.feed_kami(45, 11301, account="testa")
        assert r["status"] == "success"
        assert sent[-1]["system"] == "system.kami.use.item"

    def test_use_item_batch_zero_count(self, accounts, sent):
        with pytest.raises(server.PreTxValidationError) as ei:
            server.use_item_batch(45, 11302, 0, account="testa")
        assert "count is 0; use_item_batch requires at least 1" in str(
            ei.value
        )
        assert sent == []

    def test_use_item_batch_insufficient_holdings(
        self, accounts, validation_ok, sent, monkeypatch
    ):
        monkeypatch.setattr(server, "_inventory_balance", lambda h, i: 3)
        with pytest.raises(server.PreTxValidationError) as ei:
            server.use_item_batch(45, 11302, 5, account="testa")
        msg = str(ei.value)
        assert "holds 3 of item 11302" in msg
        assert "use_item_batch requires 5" in msg
        assert sent == []

    def test_use_item_batch_happy(self, accounts, validation_ok, sent):
        r = server.use_item_batch(45, 11302, 2, account="testa")
        assert r["success"] is True and len(sent) == 2

    def test_use_account_item_zero_amount(self, accounts, sent):
        with pytest.raises(server.PreTxValidationError, match="at least 1"):
            server.use_account_item(21201, account="testa", amount=0)
        assert sent == []

    def test_use_account_item_holdings(
        self, accounts, validation_ok, sent, monkeypatch
    ):
        monkeypatch.setattr(server, "_inventory_balance", lambda h, i: 2)
        with pytest.raises(server.PreTxValidationError) as ei:
            server.use_account_item(21201, account="testa", amount=4)
        assert "holds 2 of item 21201" in str(ei.value)
        assert sent == []

    def test_use_account_item_happy(self, accounts, validation_ok, sent):
        r = server.use_account_item(21201, account="testa", amount=1)
        assert r["status"] == "success"

    def test_level_up_ownership(self, accounts, validation_ok, sent, monkeypatch):
        monkeypatch.setattr(server, "_kami_owner_id", lambda k: 0xDEAD)
        with pytest.raises(server.PreTxValidationError, match="not owned"):
            server.level_up_kami(45, account="testa")
        assert sent == []

    def test_level_up_happy(self, accounts, validation_ok, sent):
        assert server.level_up_kami(45, account="testa")["status"] == "success"

    def test_upgrade_skill_ownership(
        self, accounts, validation_ok, sent, monkeypatch
    ):
        monkeypatch.setattr(server, "_kami_owner_id", lambda k: 0xDEAD)
        with pytest.raises(server.PreTxValidationError, match="not owned"):
            server.upgrade_skill(45, 311, account="testa")
        assert sent == []

    def test_allocate_skills_empty_plan(self, accounts, sent):
        with pytest.raises(server.PreTxValidationError, match="skill_plan is empty"):
            server.allocate_skills(45, [], account="testa")
        assert sent == []

    def test_equip_holdings(self, accounts, validation_ok, sent, monkeypatch):
        monkeypatch.setattr(server, "_inventory_balance", lambda h, i: 0)
        with pytest.raises(server.PreTxValidationError) as ei:
            server.equip_item(45, 1001, account="testa")
        assert "holds 0 of item 1001" in str(ei.value)
        assert sent == []

    def test_unequip_ownership(self, accounts, validation_ok, sent, monkeypatch):
        monkeypatch.setattr(server, "_kami_owner_id", lambda k: 0xDEAD)
        with pytest.raises(server.PreTxValidationError, match="not owned"):
            server.unequip_item(45, "Kami_Pet_Slot", account="testa")
        assert sent == []

    def test_name_kami_length(self, accounts, sent):
        with pytest.raises(server.PreTxValidationError) as ei:
            server.name_kami(45, "x" * 17, account="testa")
        assert "kami name must be 1-16 bytes" in str(ei.value)
        assert "is 17 bytes" in str(ei.value)
        assert sent == []

    def test_name_kami_needs_holy_dust(
        self, accounts, validation_ok, sent, monkeypatch
    ):
        monkeypatch.setattr(server, "_inventory_balance", lambda h, i: 0)
        with pytest.raises(server.PreTxValidationError) as ei:
            server.name_kami(45, "NewName", account="testa")
        assert "holds 0 of item 11011 (Holy Dust)" in str(ei.value)
        assert sent == []

    def test_name_kami_happy(self, accounts, validation_ok, sent):
        assert server.name_kami(45, "NewName", account="testa")[
            "status"
        ] == "success"

    def test_burn_items_empty(self, accounts, sent):
        with pytest.raises(
            server.PreTxValidationError, match="item_indices is empty"
        ):
            server.burn_items([], [], account="testa")
        assert sent == []

    def test_burn_items_length_mismatch(self, accounts, validation_ok, sent):
        with pytest.raises(ValueError, match="same length"):
            server.burn_items([1005], [1, 2], account="testa")
        assert sent == []

    def test_burn_items_zero_amount(self, accounts, validation_ok, sent):
        with pytest.raises(server.PreTxValidationError) as ei:
            server.burn_items([1005], [0], account="testa")
        assert "amount for item 1005 is 0" in str(ei.value)
        assert sent == []

    def test_burn_items_holdings(self, accounts, validation_ok, sent, monkeypatch):
        monkeypatch.setattr(server, "_inventory_balance", lambda h, i: 1)
        with pytest.raises(server.PreTxValidationError) as ei:
            server.burn_items([1005], [5], account="testa")
        assert "holds 1 of item 1005" in str(ei.value)
        assert sent == []

    def test_burn_items_happy(self, accounts, validation_ok, sent):
        assert server.burn_items([1005], [2], account="testa")[
            "status"
        ] == "success"

    def test_listing_buy_empty(self, accounts, sent):
        with pytest.raises(
            server.PreTxValidationError, match="item_indices is empty"
        ):
            server.listing_buy(1, [], [], account="testa")
        assert sent == []

    def test_craft_zero_amount(self, accounts, sent):
        with pytest.raises(server.PreTxValidationError) as ei:
            server.craft_item(6, amount=0, account="testa")
        assert "amount is 0; craft_item requires at least 1" in str(ei.value)
        assert sent == []

    def test_craft_happy(self, accounts, validation_ok, sent):
        assert server.craft_item(6, account="testa")["status"] == "success"


# ---------------------------------------------------------------------------
# revive_kami paths
# ---------------------------------------------------------------------------


class TestReviveValidation:
    @pytest.fixture()
    def dead_kami(self, validation_ok, monkeypatch):
        monkeypatch.setattr(server, "_kami_state", lambda k: "DEAD")

    def test_requires_dead(self, accounts, validation_ok, sent):
        # validation_ok reads every kami as RESTING
        with pytest.raises(server.PreTxValidationError) as ei:
            server.revive_kami(45, account="testa")
        assert "kami #45 is RESTING; revive_kami requires DEAD" in str(
            ei.value
        )
        assert sent == []

    def test_onyx_default_path(self, accounts, dead_kami, sent):
        r = server.revive_kami(45, account="testa")
        assert r["method"] == "onyx"
        assert r["consumed"] == "33x item 100 (Onyx Shard)"
        assert sent[-1]["system"] == "system.kami.onyx.revive"
        # the onyx revive system takes the raw token index
        assert sent[-1]["args"] == [45]

    def test_onyx_insufficient_shards(
        self, accounts, dead_kami, sent, monkeypatch
    ):
        monkeypatch.setattr(server, "_inventory_balance", lambda h, i: 12)
        with pytest.raises(server.PreTxValidationError) as ei:
            server.revive_kami(45, account="testa")
        msg = str(ei.value)
        assert "holds 12 of item 100 (Onyx Shard)" in msg
        assert "revive_kami requires 33" in msg
        assert sent == []

    def test_item_path_uses_use_item_system(self, accounts, dead_kami, sent):
        r = server.revive_kami(45, method="red_ribbon_gummy", account="testa")
        assert r["method"] == "red_ribbon_gummy"
        assert sent[-1]["system"] == "system.kami.use.item"
        assert sent[-1]["args"] == [server._kami_entity_id(45), 11001]

    def test_item_path_no_holdings(self, accounts, dead_kami, sent, monkeypatch):
        monkeypatch.setattr(server, "_inventory_balance", lambda h, i: 0)
        with pytest.raises(server.PreTxValidationError) as ei:
            server.revive_kami(45, method="pale_potion", account="testa")
        assert "holds 0 of item 11004" in str(ei.value)
        assert sent == []

    def test_every_item_path_mapped(self):
        assert {
            v["item_index"] for v in server._REVIVE_ITEM_PATHS.values()
        } == {11001, 11002, 11003, 11004}


# ---------------------------------------------------------------------------
# buy_kami owner-balance gate + scavenge/droptable gates
# ---------------------------------------------------------------------------


class TestBuyKamiBalanceGate:
    def test_balance_below_total_blocks(self, accounts, monkeypatch, sent):
        listings = [
            {"kami_index": 5, "price_eth": 1.0, "price_wei": 10**18,
             "order_id_hex": hex(11), "seller_account_id": "999",
             "expiry": 0, "created_at": 60},
        ]
        monkeypatch.setattr(
            server, "get_kami_market_listings",
            lambda **kw: {"count": 1, "listings": listings},
        )
        monkeypatch.setattr(
            server, "w3",
            SimpleNamespace(
                eth=SimpleNamespace(get_balance=lambda a: 10**17),
                from_wei=Web3.from_wei,
            ),
        )
        with pytest.raises(server.PreTxValidationError) as ei:
            server.buy_kami([5], "2.0", account="testa")
        msg = str(ei.value)
        assert "holds 0.1 ETH" in msg
        assert "requires 1 ETH (live listing total)" in msg
        assert "gas provision" in msg
        assert sent == []


class TestScavengeValidation:
    def test_claim_no_claimable_tier(self, accounts, validation_ok, sent, monkeypatch):
        monkeypatch.setattr(
            server, "get_scavenge_points",
            lambda node, account: {
                "points": 5, "tier_cost": 100, "claimable_tiers": 0,
            },
        )
        with pytest.raises(server.PreTxValidationError) as ei:
            server.scavenge_claim(16, account="testa")
        msg = str(ei.value)
        assert "has 5 scavenge points at node 16" in msg
        assert "claiming a tier requires 100" in msg
        assert sent == []

    def test_droptable_reveal_empty(self, accounts, sent):
        with pytest.raises(
            server.PreTxValidationError, match="commit_ids is empty"
        ):
            server.droptable_reveal([], account="testa")
        assert sent == []

    def test_claim_and_reveal_handles_validation_skip(
        self, accounts, monkeypatch
    ):
        monkeypatch.setattr(
            server, "scavenge_claim",
            lambda node, account: {
                "status": "success", "block": 10, "commit_ids": [111],
            },
        )
        monkeypatch.setattr(
            server, "w3",
            SimpleNamespace(eth=SimpleNamespace(block_number=99)),
        )
        monkeypatch.setattr(server.time, "sleep", lambda s: None)

        def reveal_blocked(ids, account):
            raise server.PreTxValidationError(
                "transaction dry-run reverted: revert: already revealed"
            )

        monkeypatch.setattr(server, "droptable_reveal", reveal_blocked)
        r = server.scavenge_claim_and_reveal(16, account="testa")
        assert r["reveal"] is None
        assert "already revealed" in r["reveal_skipped"]


# ---------------------------------------------------------------------------
# Batch-tool empty guards + error format
# ---------------------------------------------------------------------------


class TestBatchEmptyGuards:
    def test_level_and_allocate_batch_empty(self, accounts):
        with pytest.raises(server.PreTxValidationError, match="targets is empty"):
            asyncio.run(server.level_and_allocate_batch([], account="testa"))

    def test_feed_level_allocate_batch_empty(self, accounts):
        with pytest.raises(server.PreTxValidationError, match="targets is empty"):
            asyncio.run(server.feed_level_allocate_batch([], account="testa"))

    @pytest.mark.parametrize("call", [
        lambda: server.transfer_kami([], to_account="testb", account="testa"),
        lambda: server.buy_kami([], "1.0", account="testa"),
        lambda: server.cancel_kami_listing([], account="testa"),
        lambda: server.sacrifice_kami_batch([], account="testa"),
        lambda: server.unequip_all_batch([], account="testa"),
        lambda: server.equip_all_batch([], account="testa"),
        lambda: server.sacrifice_reveal([], account="testa"),
    ])
    def test_existing_empty_guards_are_validation_errors(
        self, accounts, call
    ):
        with pytest.raises(server.PreTxValidationError):
            call()


class TestErrorFormat:
    def test_prefix_is_stable(self):
        assert PREFIX == "validation failed; no transaction sent: "
        e = server.PreTxValidationError("kami #1 is DEAD")
        assert str(e) == PREFIX + "kami #1 is DEAD"
        assert e.detail == "kami #1 is DEAD"
        assert isinstance(e, ValueError)

    def test_revert_text_extracts_rpc_message(self):
        e = ValueError(
            {"code": -32000, "message": "revert: kami not RESTING: Reverted"}
        )
        assert server._revert_text(e) == "revert: kami not RESTING: Reverted"
        assert server._revert_text(ValueError("plain")) == "plain"

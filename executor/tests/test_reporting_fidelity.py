"""Offline tests for ACT reporting fidelity (2.0.0-dev, H1).

Covers the three terminal states at the sender layer (confirmed-success
/ confirmed-revert / unconfirmed — none conflatable), the best-effort
revert-reason replay at the landed block, the no-blind-retry rule, the
batch matrix (all-success / mixed with and without allow_partial /
all-fail), and the invariant that no tool returns normally when a
submitted, non-allow_partial transaction reverted. No network, keys,
or chain access.
"""

import asyncio
from types import SimpleNamespace

import pytest
from web3 import Web3
from web3.exceptions import TimeExhausted

from conftest import FAKE_ACCOUNT_ID, FakeContract

import server


# ---------------------------------------------------------------------------
# Sender-layer fixtures (full fake send path with settable receipt,
# receipt-wait error, and eth_call replay behavior)
# ---------------------------------------------------------------------------


class _BoundFn:
    def __init__(self, handler, args):
        self._handler = handler
        self._args = args

    def call(self, params=None):
        return self._handler(*self._args)

    def build_transaction(self, params):
        return {"to": "0xsystem", "data": "0xcalldata", **params}


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
    """Fake send path with adjustable receipt status, wait behavior,
    and eth_call replay result."""
    registry: dict[str, object] = {}
    balances: dict[str, int] = {}
    broadcasts: list[bytes] = []
    state = SimpleNamespace(
        registry=registry,
        balances=balances,
        broadcasts=broadcasts,
        receipt=SimpleNamespace(
            transactionHash=b"\xab" * 32, status=1, blockNumber=123,
            gasUsed=42,
        ),
        wait_error=None,   # exception instance to raise from receipt wait
        call_error=None,   # exception instance to raise from replay call
        call_log=[],       # (params, block_identifier) per replay call
    )

    def wait(h, timeout=None):
        if state.wait_error is not None:
            raise state.wait_error
        return state.receipt

    def eth_call(params, block_identifier=None):
        state.call_log.append((params, block_identifier))
        if state.call_error is not None:
            raise state.call_error
        return b""

    eth = SimpleNamespace(
        contract=lambda address=None, abi=None: registry[address],
        get_balance=lambda a: balances.get(a, 10**18),
        get_transaction_count=lambda a: 7,
        send_raw_transaction=lambda raw: broadcasts.append(raw) or b"\x01" * 32,
        wait_for_transaction_receipt=wait,
        call=eth_call,
        account=SimpleNamespace(
            sign_transaction=lambda tx, private_key=None: SimpleNamespace(
                raw_transaction=b"rawtx"
            )
        ),
    )
    fake_w3 = SimpleNamespace(
        eth=eth, from_wei=Web3.from_wei, to_wei=Web3.to_wei
    )
    monkeypatch.setattr(server, "w3", fake_w3)
    monkeypatch.setattr(server, "_resolve_system", lambda sid: sid)
    monkeypatch.setattr(server, "_resolve_component", lambda cid: cid)
    monkeypatch.setattr(server, "_operator_account_cache", {})
    monkeypatch.setattr(server, "_owner_registered_cache", set())
    registry["component.address.operator"] = FakeContract(
        {"getEntitiesWithValue": lambda v: [FAKE_ACCOUNT_ID]}
    )
    registry["component.name"] = FakeContract({"safeGet": lambda e: "testa"})
    registry["system.account.move"] = FakeTxContract(
        {"executeTyped": lambda room: b""}
    )
    return state


def _revert_receipt(state, block=77, gas=55_000):
    state.receipt = SimpleNamespace(
        transactionHash=b"\xcd" * 32, status=0, blockNumber=block,
        gasUsed=gas,
    )


# ---------------------------------------------------------------------------
# Three terminal states at the sender layer
# ---------------------------------------------------------------------------


class TestSenderTerminalStates:
    def test_confirmed_success_payload_has_receipt_fields(
        self, accounts, txchain
    ):
        r = server._send_tx(
            "testa", "system.account.move", server._ABI_MOVE, [4],
            gas_limit=100_000,
        )
        assert r["status"] == "success"
        assert r["tx_hash"] == "0x" + "ab" * 32
        assert r["block"] == 123 and r["gas_used"] == 42
        assert len(txchain.broadcasts) == 1

    def test_confirmed_revert_raises_with_evidence(self, accounts, txchain):
        _revert_receipt(txchain)
        txchain.call_error = ValueError(
            {"code": 3, "message": "execution reverted: kami not RESTING"}
        )
        with pytest.raises(server.OnChainRevertError) as ei:
            server._send_tx(
                "testa", "system.account.move", server._ABI_MOVE, [4],
                gas_limit=100_000,
            )
        msg = str(ei.value)
        assert "0x" + "cd" * 32 in msg           # tx hash
        assert "block 77" in msg                  # landed block
        assert "gas was spent (55000 gas)" in msg  # explicit gas statement
        assert "REVERTED" in msg
        assert "execution reverted: kami not RESTING" in msg  # replayed reason
        # The tx WAS broadcast — the error is about a landed transaction.
        assert len(txchain.broadcasts) == 1

    def test_revert_reason_replayed_at_landed_block(self, accounts, txchain):
        _revert_receipt(txchain, block=901)
        txchain.call_error = ValueError("execution reverted: nope")
        with pytest.raises(server.OnChainRevertError):
            server._send_tx(
                "testa", "system.account.move", server._ABI_MOVE, [4],
                gas_limit=100_000,
            )
        params, block_identifier = txchain.call_log[-1]
        assert block_identifier == 901
        assert params.get("data") == "0xcalldata"

    def test_revert_reason_unavailable_stated(self, accounts, txchain):
        _revert_receipt(txchain)
        txchain.call_error = None  # replay does not revert -> no reason
        with pytest.raises(server.OnChainRevertError) as ei:
            server._send_tx(
                "testa", "system.account.move", server._ABI_MOVE, [4],
                gas_limit=100_000,
            )
        assert "unavailable (the replay did not revert)" in str(ei.value)

    def test_unconfirmed_raises_distinct_error(self, accounts, txchain):
        txchain.wait_error = TimeExhausted("no receipt after 120s")
        with pytest.raises(server.TxUnconfirmedError) as ei:
            server._send_tx(
                "testa", "system.account.move", server._ABI_MOVE, [4],
                gas_limit=100_000,
            )
        msg = str(ei.value)
        assert "0x" + "01" * 32 in msg  # broadcast tx hash
        assert "UNCONFIRMED" in msg
        assert "before retrying" in msg
        assert not isinstance(ei.value, server.OnChainRevertError)

    def test_owner_sender_revert_raises(self, accounts, txchain):
        txchain.registry["system.trade.create"] = FakeTxContract(
            {"executeTyped": lambda *a: b""}
        )
        _revert_receipt(txchain)
        with pytest.raises(server.OnChainRevertError):
            server._send_tx_owner(
                "testa", "system.trade.create", server._ABI_TRADE_CREATE,
                [[1], [1], [2], [1], 0],
            )

    def test_batch_sender_revert_raises(self, accounts, txchain):
        txchain.registry["system.harvest.stop"] = FakeTxContract(
            {"executeBatched": lambda ids: b""}
        )
        _revert_receipt(txchain)
        with pytest.raises(server.OnChainRevertError):
            server._send_batch_tx(
                "testa", "system.harvest.stop", server._ABI_HARVEST_STOP,
                "executeBatched", [[1, 2]], 1_000_000,
            )

    def test_send_eth_revert_raises(self, accounts, txchain):
        a = server._get_account("testa")
        b = server._get_account("testb")
        _revert_receipt(txchain)
        with pytest.raises(server.OnChainRevertError):
            server._send_eth(a.owner_key, a.owner_addr, b.owner_addr, 1000)

    def test_send_eth_unconfirmed_raises(self, accounts, txchain):
        a = server._get_account("testa")
        b = server._get_account("testb")
        txchain.wait_error = TimeExhausted("timeout")
        with pytest.raises(server.TxUnconfirmedError):
            server._send_eth(a.owner_key, a.owner_addr, b.owner_addr, 1000)


class TestNoBlindRetry:
    def test_retry_never_resubmits_a_confirmed_revert(
        self, accounts, txchain
    ):
        _revert_receipt(txchain)
        with pytest.raises(server.OnChainRevertError):
            server._send_tx_retry(
                "testa", "system.account.move", server._ABI_MOVE, [4],
            )
        assert len(txchain.broadcasts) == 1  # exactly one submission

    def test_retry_never_resubmits_an_unconfirmed_tx(
        self, accounts, txchain
    ):
        txchain.wait_error = TimeExhausted("timeout")
        with pytest.raises(server.TxUnconfirmedError):
            server._send_tx_retry(
                "testa", "system.account.move", server._ABI_MOVE, [4],
            )
        assert len(txchain.broadcasts) == 1


# ---------------------------------------------------------------------------
# Batch matrix: all-success / mixed ±allow_partial / all-fail
# ---------------------------------------------------------------------------


def _failing_sender(fail_calls: set[int], calls: list):
    """Sender stub failing (confirmed revert) on the given 1-based call
    numbers, succeeding otherwise."""

    def send(account, system_id, abi, args, **kw):
        calls.append(system_id)
        n = len(calls)
        if n in fail_calls:
            raise server.OnChainRevertError(
                f"0xdead{n}", 9, 100_000, "revert: state changed"
            )
        return {
            "tx_hash": f"0xtx{n}", "status": "success", "block": 100 + n,
            "gas_used": 1000, "account": account,
        }

    return send


class TestUseItemBatchMatrix:
    def test_all_success(self, accounts, validation_ok, sent):
        r = server.use_item_batch(45, 11302, 3, account="testa")
        assert r["success"] is True and r["used"] == 3
        assert len(r["txs"]) == 3
        assert all(
            t["status"] == "success" and "block" in t and "gas_used" in t
            for t in r["txs"]
        )

    def test_mixed_default_raises_with_successes(
        self, accounts, validation_ok, monkeypatch
    ):
        calls = []
        monkeypatch.setattr(
            server, "_send_tx_retry", _failing_sender({3}, calls)
        )
        with pytest.raises(server.BatchTxError) as ei:
            server.use_item_batch(45, 11302, 4, account="testa")
        msg = str(ei.value)
        assert "use 3/4" in msg and "2 use(s) landed" in msg
        assert "0xtx1" in msg and "0xtx2" in msg  # successes included
        assert "0xdead3" in msg                    # the failure itself
        assert len(calls) == 3                     # loop halted

    def test_mixed_allow_partial_returns(
        self, accounts, validation_ok, monkeypatch
    ):
        calls = []
        monkeypatch.setattr(
            server, "_send_tx_retry", _failing_sender({3}, calls)
        )
        r = server.use_item_batch(
            45, 11302, 4, account="testa", allow_partial=True
        )
        assert r["used"] == 2 and r["planned"] == 4
        assert "REVERTED" in r["error"]
        assert len(r["txs"]) == 2

    def test_all_fail_raises(self, accounts, validation_ok, monkeypatch):
        calls = []
        monkeypatch.setattr(
            server, "_send_tx_retry", _failing_sender({1, 2, 3}, calls)
        )
        with pytest.raises(server.BatchTxError) as ei:
            server.use_item_batch(45, 11302, 3, account="testa")
        assert "0 use(s) landed" in str(ei.value)


class TestEquipAllBatchMatrix:
    def _gate_ok(self, chain):
        chain["system.kami.equip"] = FakeContract(
            {"executeTyped": lambda *a: b""}
        )

    def test_all_success_rows_carry_receipts(self, accounts, chain, sent):
        self._gate_ok(chain)
        r = server.equip_all_batch(
            [{"kami_id": 1, "item_index": 100},
             {"kami_id": 2, "item_index": 100}],
            account="testa", delay_seconds=0,
        )
        assert r["equipped"] == 2 and r["errors"] == 0
        for row in r["results"]:
            assert row["status"] == "success"
            assert "tx_hash" in row and "block" in row and "gas_used" in row

    def test_mixed_default_raises_with_successes(
        self, accounts, chain, monkeypatch
    ):
        self._gate_ok(chain)
        calls = []
        monkeypatch.setattr(
            server, "_send_tx_retry", _failing_sender({2}, calls)
        )
        with pytest.raises(server.BatchTxError) as ei:
            server.equip_all_batch(
                [{"kami_id": 1, "item_index": 100},
                 {"kami_id": 2, "item_index": 100}],
                account="testa", delay_seconds=0,
            )
        msg = str(ei.value)
        assert "1 of 2 equips failed" in msg
        assert "0xtx1" in msg          # the success is in the error text
        assert "0xdead2" in msg        # so is the failure
        assert len(calls) == 2         # every entry was still attempted

    def test_mixed_allow_partial_returns(self, accounts, chain, monkeypatch):
        self._gate_ok(chain)
        monkeypatch.setattr(
            server, "_send_tx_retry", _failing_sender({2}, [])
        )
        r = server.equip_all_batch(
            [{"kami_id": 1, "item_index": 100},
             {"kami_id": 2, "item_index": 100}],
            account="testa", delay_seconds=0, allow_partial=True,
        )
        assert r["equipped"] == 1 and r["errors"] == 1

    def test_skips_only_do_not_raise(self, accounts, chain, sent):
        # Dry-run-gated skips send nothing and spend nothing — they are
        # not submitted-transaction failures and stay in-band.
        chain["system.kami.equip"] = FakeContract(
            {"executeTyped": lambda *a: (_ for _ in ()).throw(
                Exception("execution reverted: slot full"))}
        )
        r = server.equip_all_batch(
            [{"kami_id": 1, "item_index": 100}],
            account="testa", delay_seconds=0,
        )
        assert r["skipped"] == 1 and r["errors"] == 0
        assert sent == []

    def test_all_fail_raises(self, accounts, chain, monkeypatch):
        self._gate_ok(chain)
        monkeypatch.setattr(
            server, "_send_tx_retry", _failing_sender({1, 2}, [])
        )
        with pytest.raises(server.BatchTxError):
            server.equip_all_batch(
                [{"kami_id": 1, "item_index": 100},
                 {"kami_id": 2, "item_index": 100}],
                account="testa", delay_seconds=0,
            )


class TestCompleteAllTradesMatrix:
    @pytest.fixture()
    def two_executed(self, monkeypatch):
        monkeypatch.setattr(
            server, "get_account_trades",
            lambda account: {"trades": [
                {"trade_id_hex": "0x1", "status": "EXECUTED"},
                {"trade_id_hex": "0x2", "status": "EXECUTED"},
            ]},
        )

    def test_all_success(self, accounts, two_executed, sent):
        r = server.complete_all_trades(account="testa")
        assert r["completed"] == 2 and r["failed"] == 0

    def test_mixed_default_raises(
        self, accounts, two_executed, monkeypatch
    ):
        monkeypatch.setattr(
            server, "_send_tx_owner", _failing_sender({2}, [])
        )
        with pytest.raises(server.BatchTxError) as ei:
            server.complete_all_trades(account="testa")
        msg = str(ei.value)
        assert "1 of 2 trade completions failed" in msg
        assert "0xtx1" in msg and "0xdead2" in msg

    def test_mixed_allow_partial_returns(
        self, accounts, two_executed, monkeypatch
    ):
        monkeypatch.setattr(
            server, "_send_tx_owner", _failing_sender({2}, [])
        )
        r = server.complete_all_trades(account="testa", allow_partial=True)
        assert r["completed"] == 1 and r["failed"] == 1


class TestCancelKamiListingMatrix:
    @pytest.fixture()
    def two_listings(self, accounts, monkeypatch):
        self_eid = str(server._account_entity_id("testa"))
        monkeypatch.setattr(
            server, "get_kami_market_listings",
            lambda **kw: {"listings": [
                {"kami_index": 5, "price_eth": 1.0, "price_wei": 10**18,
                 "order_id_hex": hex(11), "seller_account_id": self_eid,
                 "expiry": 0, "created_at": 60},
                {"kami_index": 6, "price_eth": 1.0, "price_wei": 10**18,
                 "order_id_hex": hex(12), "seller_account_id": self_eid,
                 "expiry": 0, "created_at": 60},
            ]},
        )

    def test_mixed_default_raises(self, accounts, two_listings, monkeypatch):
        monkeypatch.setattr(server, "_send_tx", _failing_sender({2}, []))
        with pytest.raises(server.BatchTxError) as ei:
            server.cancel_kami_listing([5, 6], account="testa")
        msg = str(ei.value)
        assert "1 of 2 listing cancels failed" in msg
        assert "0xtx1" in msg

    def test_mixed_allow_partial_returns(
        self, accounts, two_listings, monkeypatch
    ):
        monkeypatch.setattr(server, "_send_tx", _failing_sender({2}, []))
        r = server.cancel_kami_listing(
            [5, 6], account="testa", allow_partial=True
        )
        assert r["cancelled"] == 1 and r["failed"] == 1


class TestStopHarvestBatch:
    """The on-chain allow-failure batch: silent per-item skips must not
    read as success, and the whole-tx revert/timeout paths are the
    sender-layer terminal states."""

    def _install(self, txchain, states: dict[int, str]):
        txchain.registry["system.harvest.stop"] = FakeTxContract(
            {"executeBatchedAllowFailure": lambda ids: b""}
        )
        by_hid = {
            server._harvest_entity_id(k): v for k, v in states.items()
        }
        txchain.registry["component.state"] = FakeContract(
            {"safeGet": lambda hid: by_hid[hid]}
        )

    def test_all_stopped_returns(self, accounts, txchain):
        self._install(txchain, {45: "INACTIVE", 46: "INACTIVE"})
        r = server.stop_harvest_batch([45, 46], account="testa")
        assert r["status"] == "success"
        assert r["stopped_count"] == 2 and r["failed_count"] == 0

    def test_silent_skip_raises_by_default(self, accounts, txchain):
        self._install(txchain, {45: "INACTIVE", 46: "ACTIVE"})
        with pytest.raises(server.BatchTxError) as ei:
            server.stop_harvest_batch([45, 46], account="testa")
        msg = str(ei.value)
        assert "1 of 2 harvest stops did not take effect" in msg
        assert "gas was spent" in msg
        assert "ACTIVE" in msg  # per-kami outcome present

    def test_silent_skip_allow_partial_returns(self, accounts, txchain):
        self._install(txchain, {45: "INACTIVE", 46: "ACTIVE"})
        r = server.stop_harvest_batch(
            [45, 46], account="testa", allow_partial=True
        )
        assert r["stopped_count"] == 1 and r["failed_count"] == 1
        assert r["per_kami"][46]["stopped"] is False

    def test_whole_batch_revert_raises(self, accounts, txchain):
        self._install(txchain, {45: "ACTIVE"})
        _revert_receipt(txchain)
        with pytest.raises(server.OnChainRevertError):
            server.stop_harvest_batch([45], account="testa")

    def test_receipt_timeout_raises_unconfirmed(self, accounts, txchain):
        self._install(txchain, {45: "ACTIVE"})
        txchain.wait_error = TimeExhausted("timeout")
        with pytest.raises(server.TxUnconfirmedError):
            server.stop_harvest_batch([45], account="testa")


class TestSequentialLoopsMatrix:
    def test_level_to_mixed_default_raises(
        self, accounts, validation_ok, monkeypatch
    ):
        async def fake_api(path, account):
            return {"progress": {"level": 3}}

        monkeypatch.setattr(server, "_api_get", fake_api)
        monkeypatch.setattr(
            server, "_send_tx_retry", _failing_sender({2}, [])
        )
        with pytest.raises(server.BatchTxError) as ei:
            asyncio.run(server.level_to(45, 5, account="testa"))
        msg = str(ei.value)
        assert "level-up 2/2 failed after 1 level(s) landed" in msg
        assert "0xtx1" in msg

    def test_level_to_mixed_allow_partial_returns(
        self, accounts, validation_ok, monkeypatch
    ):
        async def fake_api(path, account):
            return {"progress": {"level": 3}}

        monkeypatch.setattr(server, "_api_get", fake_api)
        monkeypatch.setattr(
            server, "_send_tx_retry", _failing_sender({2}, [])
        )
        r = asyncio.run(
            server.level_to(45, 5, account="testa", allow_partial=True)
        )
        assert r["levels_gained"] == 1 and r["reached_level"] == 4
        assert len(r["txs"]) == 1

    def test_allocate_skills_mixed_default_raises(
        self, accounts, validation_ok, monkeypatch
    ):
        monkeypatch.setattr(
            server, "_send_tx_retry", _failing_sender({2}, [])
        )
        with pytest.raises(server.BatchTxError) as ei:
            server.allocate_skills(
                45, [{"skill_index": 311, "points": 3}], account="testa"
            )
        assert "upgrade 2/3" in str(ei.value)

    def test_travel_mixed_default_raises(
        self, accounts, validation_ok, monkeypatch
    ):
        async def fake_acct(account):
            return {}

        monkeypatch.setattr(server, "_api_get_account", fake_acct)
        monkeypatch.setattr(
            server, "_extract_account_state",
            lambda raw: {"room": 1, "stamina": 100, "stamina_max": 100,
                         "inventory": []},
        )
        monkeypatch.setattr(
            server, "rooms_graph",
            SimpleNamespace(
                shortest_path=lambda a, b: [1, 2, 3],
                move_cost=lambda p: 5 * (len(p) - 1),
            ),
        )
        monkeypatch.setattr(
            server, "_send_tx_retry", _failing_sender({2}, [])
        )
        with pytest.raises(server.BatchTxError) as ei:
            asyncio.run(server.travel_to_room(3, account="testa"))
        msg = str(ei.value)
        assert "stopped in room 2" in msg
        assert "0xtx1" in msg  # the executed hop is in the error text

    def test_travel_mixed_allow_partial_returns(
        self, accounts, validation_ok, monkeypatch
    ):
        async def fake_acct(account):
            return {}

        monkeypatch.setattr(server, "_api_get_account", fake_acct)
        monkeypatch.setattr(
            server, "_extract_account_state",
            lambda raw: {"room": 1, "stamina": 100, "stamina_max": 100,
                         "inventory": []},
        )
        monkeypatch.setattr(
            server, "rooms_graph",
            SimpleNamespace(
                shortest_path=lambda a, b: [1, 2, 3],
                move_cost=lambda p: 5 * (len(p) - 1),
            ),
        )
        monkeypatch.setattr(
            server, "_send_tx_retry", _failing_sender({2}, [])
        )
        r = asyncio.run(
            server.travel_to_room(3, account="testa", allow_partial=True)
        )
        assert r["reached_target"] is False
        assert r["final_room"] == 2 and r["moves_executed"] == 1
        assert len(r["txs"]) == 1

    def test_level_and_allocate_mixed_default_raises(
        self, accounts, validation_ok, monkeypatch
    ):
        async def fake_api(path, account):
            return {"progress": {"level": 1}}

        monkeypatch.setattr(server, "_api_get", fake_api)
        # kami 5 levels fine (call 1); kami 6's level tx fails (call 2).
        monkeypatch.setattr(
            server, "_send_tx_retry", _failing_sender({2}, [])
        )
        with pytest.raises(server.BatchTxError) as ei:
            asyncio.run(server.level_and_allocate_batch(
                [{"kami_id": 5, "target_level": 2},
                 {"kami_id": 6, "target_level": 2}],
                account="testa",
            ))
        msg = str(ei.value)
        assert "1 of 2 per-kami plans failed" in msg
        assert "0xtx1" in msg  # kami 5's landed tx is in the error text

    def test_level_and_allocate_mixed_allow_partial_returns(
        self, accounts, validation_ok, monkeypatch
    ):
        async def fake_api(path, account):
            return {"progress": {"level": 1}}

        monkeypatch.setattr(server, "_api_get", fake_api)
        monkeypatch.setattr(
            server, "_send_tx_retry", _failing_sender({2}, [])
        )
        r = asyncio.run(server.level_and_allocate_batch(
            [{"kami_id": 5, "target_level": 2},
             {"kami_id": 6, "target_level": 2}],
            account="testa", allow_partial=True,
        ))
        assert r["ok"] == 1 and r["count"] == 2

    def test_sacrifice_batch_mixed_default_raises(
        self, accounts, chain, monkeypatch
    ):
        chain["system.kami.sacrifice.commit"] = FakeContract(
            {"executeTyped": lambda ki: b""}
        )
        monkeypatch.setattr(
            server, "_send_tx_retry", _failing_sender({2}, [])
        )
        with pytest.raises(server.BatchTxError) as ei:
            server.sacrifice_kami_batch(
                [1, 2], account="testa", delay_seconds=0
            )
        msg = str(ei.value)
        assert "1 of 2 sacrifice commits failed" in msg
        assert "0xtx1" in msg

    def test_sacrifice_batch_skips_only_do_not_raise(
        self, accounts, chain, sent
    ):
        def gate(ki):
            if ki == 2:
                raise Exception("execution reverted: not owner")
            return b""

        chain["system.kami.sacrifice.commit"] = FakeContract(
            {"executeTyped": gate}
        )
        r = server.sacrifice_kami_batch(
            [1, 2], account="testa", delay_seconds=0
        )
        assert r["submitted"] == 1 and r["skipped"] == 1 and r["errors"] == 0


# ---------------------------------------------------------------------------
# Invariant: no tool returns normally when a submitted, non-allow_partial
# transaction reverted.
# ---------------------------------------------------------------------------


class TestRevertInvariant:
    @pytest.fixture()
    def reverting_senders(self, monkeypatch):
        def boom(*a, **kw):
            raise server.OnChainRevertError(
                "0xdead", 9, 100_000, "revert: state changed"
            )

        monkeypatch.setattr(server, "_send_tx", boom)
        monkeypatch.setattr(server, "_send_tx_retry", boom)
        monkeypatch.setattr(server, "_send_tx_owner", boom)
        monkeypatch.setattr(server, "_send_batch_tx", boom)
        monkeypatch.setattr(server, "_send_eth", boom)

    @pytest.fixture()
    def batch_env(self, accounts, validation_ok, chain, monkeypatch):
        """Enough mocks that every allow_partial tool reaches its send."""

        async def fake_api(path, account):
            return {"progress": {"level": 1}}

        async def fake_acct(account):
            return {}

        monkeypatch.setattr(server, "_api_get", fake_api)
        monkeypatch.setattr(server, "_api_get_account", fake_acct)
        monkeypatch.setattr(
            server, "_extract_account_state",
            lambda raw: {"room": 1, "stamina": 100, "stamina_max": 100,
                         "inventory": []},
        )
        monkeypatch.setattr(
            server, "rooms_graph",
            SimpleNamespace(
                shortest_path=lambda a, b: [1, 2],
                move_cost=lambda p: 5 * (len(p) - 1),
            ),
        )
        for sysid in ("system.kami.equip", "system.kami.unequip",
                      "system.kami.sacrifice.commit"):
            chain[sysid] = FakeContract({"executeTyped": lambda *a: b""})
        self_eid = str(server._account_entity_id("testa"))
        monkeypatch.setattr(
            server, "get_kami_market_listings",
            lambda **kw: {"listings": [
                {"kami_index": 5, "price_eth": 1.0, "price_wei": 10**18,
                 "order_id_hex": hex(11), "seller_account_id": self_eid,
                 "expiry": 0, "created_at": 60},
            ]},
        )
        monkeypatch.setattr(
            server, "get_account_trades",
            lambda account: {"trades": [
                {"trade_id_hex": "0x1", "status": "EXECUTED"},
            ]},
        )
        monkeypatch.setattr(
            server, "get_scavenge_points",
            lambda node, account: {
                "points": 200, "tier_cost": 100, "claimable_tiers": 2,
            },
        )
        monkeypatch.setattr(
            server, "_quest_owned_completed", lambda q, a: (False, False)
        )

    def _batch_calls(self):
        """One default-arg (allow_partial unset) invocation per
        allow_partial tool except stop_harvest_batch, whose inline send
        path is covered in TestStopHarvestBatch."""
        return {
            "travel_to_room": lambda **kw: asyncio.run(
                server.travel_to_room(2, account="testa", **kw)),
            "allocate_skills": lambda **kw: server.allocate_skills(
                45, [{"skill_index": 311, "points": 1}],
                account="testa", **kw),
            "level_to": lambda **kw: asyncio.run(
                server.level_to(45, 2, account="testa", **kw)),
            "level_and_allocate_batch": lambda **kw: asyncio.run(
                server.level_and_allocate_batch(
                    [{"kami_id": 45, "target_level": 2}],
                    account="testa", **kw)),
            "feed_level_allocate_batch": lambda **kw: asyncio.run(
                server.feed_level_allocate_batch(
                    [{"kami_id": 45, "feed_item_id": 11, "feed_count": 1}],
                    account="testa", **kw)),
            "use_item_batch": lambda **kw: server.use_item_batch(
                45, 11302, 1, account="testa", **kw),
            "equip_all_batch": lambda **kw: server.equip_all_batch(
                [{"kami_id": 1, "item_index": 100}],
                account="testa", delay_seconds=0, **kw),
            "unequip_all_batch": lambda **kw: server.unequip_all_batch(
                [1], account="testa", delay_seconds=0, **kw),
            "cancel_kami_listing": lambda **kw: server.cancel_kami_listing(
                [5], account="testa", **kw),
            "complete_all_trades": lambda **kw: server.complete_all_trades(
                account="testa", **kw),
            "speed_craft_batch": lambda **kw: server.speed_craft_batch(
                29, 1, account="testa", **kw),
            "sacrifice_kami_batch": lambda **kw: server.sacrifice_kami_batch(
                [1], account="testa", delay_seconds=0, **kw),
        }

    def test_batch_tools_raise_when_every_tx_reverts(
        self, batch_env, reverting_senders
    ):
        for name, call in self._batch_calls().items():
            with pytest.raises(
                (server.BatchTxError, server.OnChainRevertError)
            ):
                call()
                pytest.fail(f"{name} returned normally on revert")

    def test_batch_tools_return_with_allow_partial(
        self, batch_env, reverting_senders
    ):
        for name, call in self._batch_calls().items():
            r = call(allow_partial=True)
            assert isinstance(r, dict), name

    def test_single_tx_tools_propagate_revert(
        self, batch_env, reverting_senders
    ):
        calls = {
            "feed_kami": lambda: server.feed_kami(45, 11302, account="testa"),
            "level_up_kami": lambda: server.level_up_kami(45, account="testa"),
            "upgrade_skill": lambda: server.upgrade_skill(
                45, 311, account="testa"),
            "craft_item": lambda: server.craft_item(6, 1, account="testa"),
            "burn_items": lambda: server.burn_items([1005], [1], account="testa"),
            "move_to_room": lambda: server.move_to_room(4, account="testa"),
            "use_account_item": lambda: server.use_account_item(
                21201, account="testa"),
            "harvest_start": lambda: server.harvest_start(
                [45], 1, account="testa"),
            "harvest_stop_batch_tx": lambda: server.harvest_stop(
                [45, 46], account="testa"),
            "accept_quest": lambda: server.accept_quest(1, account="testa"),
            "complete_trade": lambda: server.complete_trade(
                "0x1", account="testa"),
            "take_trade": lambda: server.take_trade("0x1", account="testa"),
            "create_trade": lambda: server.create_trade(
                11312, 1, 1, 100, account="testa"),
            "scavenge_claim": lambda: server.scavenge_claim(
                16, account="testa"),
            "sacrifice_reveal": lambda: server.sacrifice_reveal(
                ["9"], account="testa"),
        }
        for name, call in calls.items():
            with pytest.raises(server.OnChainRevertError):
                call()
                pytest.fail(f"{name} returned normally on revert")

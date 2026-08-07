"""Offline tests for the constant-product item-pool swap pair.

Covers the pool entity-id derivation, the swap math and its fee, the
price-impact figure, and — most of the file — the min_amount_out floor,
which is the whole reason the act tool is shaped the way it is. No
network, keys, or chain access.
"""

from types import SimpleNamespace

import pytest

import server


@pytest.fixture()
def pool(monkeypatch, accounts):
    """A pool with settable reserves, and a recording sender."""
    state = SimpleNamespace(
        reserves={},        # (holder_id, item_index) -> balance
        fee_bps=30,
        sent=[],
        account_balances={},  # item_index -> balance held by the account
    )

    def fake_inventory(holder_id, item_index):
        if holder_id == FAKE_ACCOUNT:
            return state.account_balances.get(item_index, 10**18)
        return state.reserves.get(item_index, 0)

    def fake_send(account, system_id, abi, args, gas_limit=None, **kw):
        state.sent.append(
            {"system": system_id, "args": args, "gas_limit": gas_limit}
        )
        return {
            "tx_hash": "0x" + "ee" * 32, "status": "success",
            "block": 5, "gas_used": 700_000, "account": account,
        }

    monkeypatch.setattr(server, "_inventory_balance", fake_inventory)
    monkeypatch.setattr(server, "_pool_fee_bps", lambda pid: state.fee_bps)
    monkeypatch.setattr(
        server, "_require_registered_operator", lambda a: FAKE_ACCOUNT
    )
    monkeypatch.setattr(server, "_send_tx", fake_send)
    monkeypatch.setattr(server, "_get_item_name", lambda i: f"Item{i}")
    return state


FAKE_ACCOUNT = 999_001
MUSU = 1
ITEM = 11302


class TestPoolEntityId:
    def test_pair_order_does_not_change_the_id(self):
        """A pool is one entity whichever side the caller names first."""
        assert (server._pool_entity_id(MUSU, ITEM)
                == server._pool_entity_id(ITEM, MUSU))

    def test_distinct_pairs_get_distinct_ids(self):
        assert (server._pool_entity_id(MUSU, ITEM)
                != server._pool_entity_id(MUSU, ITEM + 1))

    def test_id_is_a_uint256(self):
        pid = server._pool_entity_id(MUSU, ITEM)
        assert 0 < pid < 2**256


class TestSwapMath:
    def test_constant_product_holds_after_the_trade(self):
        """With the fee set aside, the invariant is what prices the trade."""
        r_in, r_out = 1_000_000, 1_000_000
        out = server._pool_amount_out(1_000, r_in, r_out, 0)
        assert (r_in + 1_000) * (r_out - out) >= r_in * r_out

    def test_fee_reduces_the_output(self):
        args = (10_000, 1_000_000, 1_000_000)
        assert (server._pool_amount_out(*args, 30)
                < server._pool_amount_out(*args, 0))

    def test_larger_trades_price_worse(self):
        """Depth is the whole risk: rate degrades with size."""
        small = server._pool_amount_out(100, 1_000_000, 1_000_000, 30) / 100
        large = server._pool_amount_out(
            500_000, 1_000_000, 1_000_000, 30) / 500_000
        assert large < small

    def test_output_never_drains_the_reserve(self):
        out = server._pool_amount_out(10**12, 1_000, 1_000, 30)
        assert out < 1_000


class TestQuote:
    def test_quote_reports_reserves_fee_and_impact(self, pool):
        pool.reserves = {MUSU: 1_000_000, ITEM: 500_000}
        q = server.pool_swap_quote(MUSU, ITEM, 10_000)
        assert q["reserve_in"] == 1_000_000
        assert q["reserve_out"] == 500_000
        assert q["fee_bps"] == 30
        assert q["amount_out"] > 0
        assert q["price_impact_pct"] > 0

    def test_min_amount_out_follows_slippage(self, pool):
        pool.reserves = {MUSU: 1_000_000, ITEM: 500_000}
        tight = server.pool_swap_quote(MUSU, ITEM, 10_000, slippage_bps=10)
        loose = server.pool_swap_quote(MUSU, ITEM, 10_000, slippage_bps=500)
        assert tight["min_amount_out"] > loose["min_amount_out"]
        assert tight["min_amount_out"] <= tight["amount_out"]

    def test_bigger_trade_shows_bigger_impact(self, pool):
        pool.reserves = {MUSU: 1_000_000, ITEM: 500_000}
        small = server.pool_swap_quote(MUSU, ITEM, 1_000)
        big = server.pool_swap_quote(MUSU, ITEM, 200_000)
        assert big["price_impact_pct"] > small["price_impact_pct"]

    def test_quote_signs_nothing(self, pool):
        pool.reserves = {MUSU: 1_000_000, ITEM: 500_000}
        server.pool_swap_quote(MUSU, ITEM, 10_000)
        assert pool.sent == []


class TestPoolPreconditions:
    def test_same_item_both_sides_rejected(self, pool):
        with pytest.raises(server.PreTxValidationError, match="same item"):
            server.pool_swap_quote(ITEM, ITEM, 100)

    def test_item_to_item_names_the_musu_route(self, pool):
        """There is no item-to-item pool; the error must say what to do
        instead rather than just refusing."""
        pool.reserves = {ITEM: 1_000, ITEM + 1: 1_000}
        with pytest.raises(server.PreTxValidationError) as ei:
            server.pool_swap_quote(ITEM, ITEM + 1, 100)
        msg = str(ei.value)
        assert "must be MUSU" in msg
        assert "two swaps" in msg

    def test_empty_pool_reports_the_reserves_it_read(self, pool):
        pool.reserves = {MUSU: 0, ITEM: 0}
        with pytest.raises(server.PreTxValidationError) as ei:
            server.pool_swap_quote(MUSU, ITEM, 100)
        assert "no pool with liquidity" in str(ei.value)

    def test_zero_amount_rejected(self, pool):
        pool.reserves = {MUSU: 1_000_000, ITEM: 500_000}
        with pytest.raises(server.PreTxValidationError):
            server.pool_swap_quote(MUSU, ITEM, 0)

    def test_dust_trade_rejected_rather_than_quoted_at_zero(self, pool):
        """A quote of 0 out is not a quote — it is a swap that would give
        the input away."""
        pool.reserves = {MUSU: 10**12, ITEM: 1}
        with pytest.raises(server.PreTxValidationError) as ei:
            server.pool_swap_quote(MUSU, ITEM, 1)
        assert "too small to price" in str(ei.value)


class TestSwapFloor:
    """min_amount_out is the point of the tool."""

    def test_floor_is_required_and_positional(self):
        import inspect
        sig = inspect.signature(server.pool_swap)
        p = sig.parameters["min_amount_out"]
        assert p.default is inspect.Parameter.empty, (
            "min_amount_out must be required — a defaulted floor is a "
            "floor callers never think about"
        )

    def test_zero_floor_refused(self, pool):
        pool.reserves = {MUSU: 1_000_000, ITEM: 500_000}
        with pytest.raises(server.PreTxValidationError) as ei:
            server.pool_swap(MUSU, ITEM, 1_000, 0, account="testa")
        assert "accepts any fill" in str(ei.value)
        assert pool.sent == []

    def test_swap_below_floor_sends_nothing(self, pool):
        pool.reserves = {MUSU: 1_000_000, ITEM: 500_000}
        q = server.pool_swap_quote(MUSU, ITEM, 10_000)
        with pytest.raises(server.PreTxValidationError) as ei:
            server.pool_swap(
                MUSU, ITEM, 10_000, q["amount_out"] * 2, account="testa"
            )
        assert "below the min_amount_out floor" in str(ei.value)
        assert "No transaction was sent." in str(ei.value)
        assert pool.sent == []

    def test_floor_is_passed_through_to_the_chain(self, pool):
        """The guard is only real if the contract receives it."""
        pool.reserves = {MUSU: 1_000_000, ITEM: 500_000}
        q = server.pool_swap_quote(MUSU, ITEM, 10_000)
        floor = q["amount_out"] - 5
        server.pool_swap(MUSU, ITEM, 10_000, floor, account="testa")
        assert pool.sent[0]["args"] == [MUSU, ITEM, 10_000, floor]
        assert pool.sent[0]["system"] == "system.pool"

    def test_insufficient_balance_names_the_item(self, pool):
        """The pool system decrements inventory directly, so an
        underfunded swap otherwise surfaces as a bare arithmetic
        underflow that names nothing."""
        pool.reserves = {MUSU: 1_000_000, ITEM: 500_000}
        pool.account_balances = {MUSU: 5}
        with pytest.raises(server.PreTxValidationError) as ei:
            server.pool_swap(MUSU, ITEM, 10_000, 1, account="testa")
        msg = str(ei.value)
        assert "holds 5" in msg and "requires 10000" in msg
        assert pool.sent == []

    def test_successful_swap_reports_what_it_expected(self, pool):
        pool.reserves = {MUSU: 1_000_000, ITEM: 500_000}
        q = server.pool_swap_quote(MUSU, ITEM, 10_000)
        r = server.pool_swap(
            MUSU, ITEM, 10_000, q["amount_out"] - 5, account="testa"
        )
        assert r["status"] == "success"
        assert r["tx_hash"].startswith("0x")
        assert r["expected_out"] == q["amount_out"]
        assert r["min_amount_out"] == q["amount_out"] - 5
        assert r["price_impact_pct"] == q["price_impact_pct"]

    def test_swap_uses_the_audited_ceiling(self, pool):
        pool.reserves = {MUSU: 1_000_000, ITEM: 500_000}
        server.pool_swap(MUSU, ITEM, 1_000, 1, account="testa")
        assert pool.sent[0]["gas_limit"] == server._GAS_CEILINGS["pool_swap"]


class TestSurfacePlacement:
    def test_quote_is_a_read_and_swap_is_an_act(self):
        assert server.TOOL_CLASSES["pool_swap_quote"] == "PERCEIVE"
        assert server.TOOL_CLASSES["pool_swap"] == "ACT"
        assert "pool_swap_quote" in server.READ_TOOLS
        assert "pool_swap" not in server.READ_TOOLS

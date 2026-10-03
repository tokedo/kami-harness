"""4.0.0 — pool_swap encodes the pool system's real function.

Until 4.0.0 the swap was encoded as `executeTyped(uint32,uint32,uint256,
uint256)` (0x7827e2de), a function system.pool does not have: every live
swap was refused by its own dry-run with a bare `Reverted`, and the tool's
dry_run stopped before the eth_call, so it answered clean. Here the fake
chain models upstream PoolSystem.swap and, like the chain, answers a bare
revert for any function the upstream contract lacks
(fixtures/upstream_abi).
"""

from __future__ import annotations

import eth_abi
import pytest
from eth_utils import keccak

import server
from fakenode import Result, addr_for
from test_h400_send_path import AID, chain_env  # noqa: F401

POOL = addr_for("system.pool")
SWAP = "swap(uint32,uint32,uint256,uint256)"
SWAP_SELECTOR = "0x4a4f0718"
OLD_SELECTOR = "0x" + keccak(text="executeTyped(uint32,uint32,uint256,uint256)")[:4].hex()
MUSU, SHARD = 1, 103


class PoolModel:
    """upstream PoolSystem.swap + LibPool.swap, as a contract handler."""

    def __init__(self, node, game):
        self.node, self.game = node, game
        self.reserves = {MUSU: 9_282_178, SHARD: 15_346}
        self.fee_bps = 30
        self.disabled = False
        self.force_revert: str | None = None     # a reason, or "" for bare
        node.handle(POOL, SWAP, self._swap)

    def amount_out(self, i, o, amt):
        net = amt * (10_000 - self.fee_bps)
        return net * self.reserves[o] // (self.reserves[i] * 10_000 + net)

    def _swap(self, n, caller, args, commit):
        i, o, amt, min_out = eth_abi.decode(
            ["uint32", "uint32", "uint256", "uint256"], args)
        if self.force_revert is not None:
            if self.force_revert == "":
                return Result(status=0, bare=True)
            return Result(status=0, revert=self.force_revert)
        if self.disabled:
            return Result(status=0, revert="entity not enabled")
        if amt == 0:
            return Result(status=0, revert="Pool: zero input")
        out = self.amount_out(i, o, amt)
        if out == 0:
            return Result(status=0, revert="Pool: insufficient output")
        if out < min_out:
            return Result(status=0, revert="Pool: slippage exceeded")
        if self.game.inv[i] < amt:
            return Result(status=0, bare=True)   # arithmetic underflow
        if commit:
            self.game.inv[i] -= amt
            self.game.inv[o] += out
            self.reserves[i] += amt
            self.reserves[o] -= out
        return Result(gas_used=720_000,
                      output=eth_abi.encode(["uint256"], [out]))


@pytest.fixture()
def pool_env(chain_env, monkeypatch):
    node, game, clock, op = chain_env
    model = PoolModel(node, game)
    game.inv[MUSU] = 50_000
    game.inv[SHARD] = 0

    def balance(holder, item):
        if holder == AID:
            return game.inv[item]
        return model.reserves.get(item, 0)

    monkeypatch.setattr(server, "_inventory_balance", balance)
    monkeypatch.setattr(server, "_pool_fee_bps", lambda pid: model.fee_bps)
    monkeypatch.setattr(server, "_pool_disabled", lambda pid: model.disabled)
    return node, game, model


def _calls_to_pool(node):
    return [p[0].get("data", p[0].get("input", ""))[:10]
            for m, p in node.requests
            if m in ("eth_call", "eth_estimateGas")
            and str(p[0].get("to", "")).lower() == POOL.lower()]


def _sent(node):
    return [m for m, _ in node.requests if m == "eth_sendRawTransaction"]


def test_the_abi_is_upstream_swap_returning_uint256():
    (fn,) = server._ABI_POOL_SWAP
    assert fn["name"] == "swap"
    assert [i["type"] for i in fn["inputs"]] == [
        "uint32", "uint32", "uint256", "uint256"]
    assert [o["type"] for o in fn["outputs"]] == ["uint256"]
    assert "0x" + keccak(text=SWAP)[:4].hex() == SWAP_SELECTOR


def test_a_swap_lands_encoded_as_swap(pool_env):
    """REPRODUCTION: on 3.7.0's encoding this raised `transaction dry-run
    reverted: ... Reverted` and sent nothing."""
    node, game, model = pool_env
    expected = model.amount_out(MUSU, SHARD, 12_200)
    r = server.pool_swap(MUSU, SHARD, 12_200, expected, account="testa")
    assert r["status"] == "success"
    assert r["received"] == expected == game.inv[SHARD]
    assert r["inventory_out"] == {"before": 0, "after": expected}
    assert set(_calls_to_pool(node)) == {SWAP_SELECTOR}
    assert OLD_SELECTOR not in _calls_to_pool(node)
    assert len(_sent(node)) == 1


def test_dry_run_runs_the_chains_eth_call_and_returns_its_amount_out(pool_env):
    node, game, model = pool_env
    expected = model.amount_out(MUSU, SHARD, 12_200)
    r = server.pool_swap(MUSU, SHARD, 12_200, 1, account="testa", dry_run=True)
    assert r["dry_run"] is True and r["amount_out"] == expected
    assert "tx_hash" not in r and "status" not in r
    assert SWAP_SELECTOR in _calls_to_pool(node)          # the real eth_call
    assert _sent(node) == []
    assert game.inv[MUSU] == 50_000                        # nothing moved


def test_a_dry_run_cannot_answer_clean_for_a_swap_the_chain_refuses(pool_env):
    """The live defect's other half: dry_run used to stop before the
    eth_call. Now a refusal by the chain refuses the dry run too."""
    node, game, model = pool_env
    model.force_revert = "Pool: slippage exceeded"
    with pytest.raises(server.PreTxValidationError) as ei:
        server.pool_swap(MUSU, SHARD, 12_200, 1, account="testa", dry_run=True)
    assert "less than min_amount_out" in str(ei.value)
    assert _sent(node) == []


@pytest.mark.parametrize("reason, words", [
    ("Pool: slippage exceeded", "less than min_amount_out"),
    ("Pool: insufficient output", "too small to buy a whole unit"),
    ("entity not enabled", "disabled by the world admin"),
    ("Pool does not exist", "no pool exists for this item pair"),
    ("Transfer includes untradeable item", "NOT_TRADABLE"),
])
def test_every_pool_reason_reads_as_words(pool_env, reason, words):
    node, game, model = pool_env
    model.force_revert = reason
    for dry in (True, False):
        with pytest.raises(server.PreTxValidationError) as ei:
            server.pool_swap(MUSU, SHARD, 12_200, 1, account="testa",
                             dry_run=dry)
        msg = str(ei.value)
        assert words in msg and "No transaction was sent." in msg
    assert _sent(node) == []


def test_a_bare_revert_is_never_passed_on_bare(pool_env):
    node, game, model = pool_env
    model.force_revert = ""
    with pytest.raises(server.PreTxValidationError) as ei:
        server.pool_swap(MUSU, SHARD, 12_200, 1, account="testa")
    msg = str(ei.value)
    assert "without a reason" in msg
    assert "balance 50000" in msg and "pool enabled" in msg
    assert _sent(node) == []


def test_a_balance_short_at_the_chain_is_named(pool_env, monkeypatch):
    """The pre-send gate read enough; the chain's underflow says nothing.
    The refusal re-reads the balance and names it."""
    node, game, model = pool_env
    real = server._require_item_balance
    monkeypatch.setattr(server, "_require_item_balance", lambda *a: 10**9)
    game.inv[MUSU] = 100
    with pytest.raises(server.PreTxValidationError) as ei:
        server.pool_swap(MUSU, SHARD, 12_200, 1, account="testa")
    assert "holds 100" in str(ei.value) and "below amount_in 12200" in str(ei.value)
    monkeypatch.setattr(server, "_require_item_balance", real)
    with pytest.raises(server.PreTxValidationError) as ei:
        server.pool_swap(MUSU, SHARD, 12_200, 1, account="testa")
    assert "holds 100" in str(ei.value)
    assert _sent(node) == []


def test_a_disabled_pool_is_refused_before_any_eth_call(pool_env):
    node, game, model = pool_env
    model.disabled = True
    for dry in (True, False):
        with pytest.raises(server.PreTxValidationError) as ei:
            server.pool_swap(MUSU, SHARD, 12_200, 1, account="testa",
                             dry_run=dry)
        assert "disabled by the world admin" in str(ei.value)
    assert _calls_to_pool(node) == [] and _sent(node) == []


def test_the_fake_chain_refuses_the_old_encoding_as_the_chain_did(pool_env):
    """The guard that makes this class visible in every hermetic test: a
    function the upstream contract lacks answers {-32000, Reverted}."""
    node, game, model = pool_env
    old = [{"type": "function", "name": "executeTyped",
            "inputs": [{"type": "uint32"}, {"type": "uint32"},
                       {"type": "uint256"}, {"type": "uint256"}],
            "outputs": [{"type": "bytes"}], "stateMutability": "nonpayable"}]
    fn = server.w3.eth.contract(address=POOL, abi=old).functions.executeTyped(
        MUSU, SHARD, 12_200, 1)
    with pytest.raises(server.PreTxValidationError) as ei:
        server._dry_run(fn, server._get_account("testa").operator_addr)
    assert "Reverted" in str(ei.value)

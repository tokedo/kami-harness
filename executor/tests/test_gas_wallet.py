"""Offline tests for get_gas_balance, fund_operator, withdraw_operator.

Balance reads and transaction sending are faked via a balance ledger and
a _send_eth stub that moves value in it; no network, keys, or chain
access.
"""

import inspect
from types import SimpleNamespace

import pytest
from web3 import Web3

from conftest import KEY_A, KEY_B

import server

# Third and fourth well-known local-dev throwaway keys (standard
# anvil/hardhat test keys; never funded on any real network, not secrets).
KEY_C = "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a"
KEY_D = "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6"

ETH = 10**18
FEE = server._PLAIN_TRANSFER_FEE_WEI
# Fake eth_estimateGas result for the withdraw_operator reserve tests
# (the observed plain-transfer burn on Yominet).
EST = 113_251
GASPRICE = server._GAS_PRICE["maxFeePerGas"]
RESERVE = 2 * EST * GASPRICE  # estimate x2 safety factor at the flat price


@pytest.fixture()
def gas_env(monkeypatch):
    """Fabricated accounts with distinct owner/operator addresses, a
    balance ledger, and a _send_eth stub that moves value in the ledger
    (so post-transaction balance reads reflect the transfer). The
    mainnet read is stubbed with its own ledger; addresses absent from
    it read "unavailable" (mirroring _owner_mainnet_eth's degradation,
    which TestOwnerMainnetHelper covers unstubbed)."""
    solo = server._Account("solo", KEY_A, KEY_B)
    noown = server._Account("noown", KEY_C, None)
    ownonly = server._Account("ownonly", None, KEY_D)
    monkeypatch.setattr(
        server, "_accounts",
        {"solo": solo, "noown": noown, "ownonly": ownonly},
    )

    balances: dict[str, int] = {}

    def fake_estimate_gas(tx):
        # Mimic node behavior: estimation fails when the sender cannot
        # cover the value being sent.
        if tx["value"] > balances.get(tx["from"], 0):
            raise ValueError(
                "{'code': -32000, 'message': 'insufficient funds for gas"
                " * price + value'}"
            )
        return EST

    fake_w3 = SimpleNamespace(
        eth=SimpleNamespace(
            get_balance=lambda addr: balances.get(addr, 0),
            estimate_gas=fake_estimate_gas,
        ),
        from_wei=Web3.from_wei,
        to_wei=Web3.to_wei,
    )
    monkeypatch.setattr(server, "w3", fake_w3)

    mainnet: dict[str, int] = {}

    def fake_owner_mainnet_eth(addr):
        if addr in mainnet:
            return str(Web3.from_wei(mainnet[addr], "ether"))
        return "unavailable"

    monkeypatch.setattr(server, "_owner_mainnet_eth", fake_owner_mainnet_eth)

    sends: list[dict] = []

    def fake_send_eth(from_key, from_addr, to_addr, value_wei, gas_limit=None):
        sends.append(
            {"from_key": from_key, "from": from_addr,
             "to": to_addr, "value": value_wei, "gas_limit": gas_limit}
        )
        balances[from_addr] -= value_wei
        balances[to_addr] = balances.get(to_addr, 0) + value_wei
        return {
            "tx_hash": f"0xtx{len(sends)}",
            "status": "success",
            "block": 100 + len(sends),
            "gas_used": 113_251,
        }

    monkeypatch.setattr(server, "_send_eth", fake_send_eth)
    return SimpleNamespace(
        solo=solo, noown=noown, ownonly=ownonly,
        balances=balances, mainnet=mainnet, sends=sends,
    )


class TestGetGasBalance:
    def test_all_accounts_by_default(self, gas_env):
        gas_env.balances[gas_env.solo.operator_addr] = ETH // 2
        gas_env.balances[gas_env.solo.owner_addr] = 2 * ETH
        gas_env.balances[gas_env.noown.operator_addr] = ETH // 4

        r = server.get_gas_balance()
        assert set(r["balances"]) == {"solo", "noown", "ownonly"}
        solo = r["balances"]["solo"]
        assert solo["operator_address"] == gas_env.solo.operator_addr
        assert solo["operator_eth"] == "0.5"
        assert solo["owner_address"] == gas_env.solo.owner_addr
        assert solo["owner_eth"] == "2"

    def test_missing_owner_omits_owner_fields(self, gas_env):
        r = server.get_gas_balance()
        noown = r["balances"]["noown"]
        assert "owner_address" not in noown
        assert "owner_eth" not in noown
        assert "owner_mainnet_eth" not in noown
        assert noown["operator_eth"] == "0"

    def test_owner_only_account_shape(self, gas_env):
        gas_env.balances[gas_env.ownonly.owner_addr] = ETH // 2
        gas_env.mainnet[gas_env.ownonly.owner_addr] = 4 * ETH
        r = server.get_gas_balance()
        assert r["balances"]["ownonly"] == {
            "owner_address": gas_env.ownonly.owner_addr,
            "owner_eth": "0.5",
            "owner_mainnet_eth": "4",
        }

    def test_owner_mainnet_eth_reported(self, gas_env):
        gas_env.mainnet[gas_env.solo.owner_addr] = 3 * ETH
        r = server.get_gas_balance(account="solo")
        assert r["balances"]["solo"]["owner_mainnet_eth"] == "3"

    def test_owner_mainnet_unavailable_keeps_yominet_fields(self, gas_env):
        gas_env.balances[gas_env.solo.owner_addr] = ETH
        r = server.get_gas_balance(account="solo")
        solo = r["balances"]["solo"]
        assert solo["owner_mainnet_eth"] == "unavailable"
        assert solo["owner_eth"] == "1"  # Yominet read unaffected

    def test_single_account(self, gas_env):
        gas_env.balances[gas_env.solo.operator_addr] = ETH
        r = server.get_gas_balance(account="solo")
        assert list(r["balances"]) == ["solo"]
        assert r["balances"]["solo"]["operator_eth"] == "1"

    def test_unknown_account(self, gas_env):
        with pytest.raises(ValueError, match="not found"):
            server.get_gas_balance(account="ghost")

    def test_reads_only_no_sends(self, gas_env):
        server.get_gas_balance()
        assert gas_env.sends == []


class TestFundOperator:
    def test_happy_owner_to_operator(self, gas_env):
        gas_env.balances[gas_env.solo.owner_addr] = ETH

        r = server.fund_operator("0.25", account="solo")
        assert len(gas_env.sends) == 1
        send = gas_env.sends[0]
        assert send["from_key"] == KEY_B  # owner-signed
        assert send["from"] == gas_env.solo.owner_addr
        assert send["to"] == gas_env.solo.operator_addr
        assert send["value"] == ETH // 4
        assert r["status"] == "success"
        assert r["direction"] == "owner->operator"
        assert r["amount_eth"] == "0.25"
        assert r["operator_eth"] == "0.25"  # post-transaction
        assert r["owner_eth"] == "0.75"

    def test_recipient_not_expressible(self, gas_env):
        # The destination is pinned to the registry operator address;
        # the tool exposes no recipient parameter.
        params = set(inspect.signature(server.fund_operator).parameters)
        assert params == {"amount_eth", "account"}

    def test_exact_amount_plus_fee_ok(self, gas_env):
        gas_env.balances[gas_env.solo.owner_addr] = ETH // 10 + FEE
        r = server.fund_operator("0.1", account="solo")
        assert r["operator_eth"] == "0.1"

    def test_insufficient_balance_names_numbers(self, gas_env):
        gas_env.balances[gas_env.solo.owner_addr] = ETH // 10
        with pytest.raises(ValueError) as ei:
            server.fund_operator("0.1", account="solo")
        msg = str(ei.value)
        assert "0.1" in msg  # balance and requested amount
        assert str(Web3.from_wei(FEE, "ether")) in msg  # gas provision
        assert str(server._PLAIN_TRANSFER_GAS) in msg
        assert gas_env.sends == []

    def test_no_owner_key(self, gas_env):
        with pytest.raises(ValueError, match="no owner key"):
            server.fund_operator("0.1", account="noown")
        assert gas_env.sends == []


class TestWithdrawOperator:
    def test_sweep_all_default(self, gas_env):
        gas_env.balances[gas_env.solo.operator_addr] = ETH

        r = server.withdraw_operator(account="solo")
        assert len(gas_env.sends) == 1
        send = gas_env.sends[0]
        assert send["from_key"] == KEY_A  # operator-signed
        assert send["from"] == gas_env.solo.operator_addr
        assert send["to"] == gas_env.solo.owner_addr
        # Estimate-based reserve: balance minus estimate x2 at the flat
        # price; the provisioned gas limit is estimate x2.
        assert send["value"] == ETH - RESERVE
        assert send["gas_limit"] == 2 * EST
        assert r["direction"] == "operator->owner"
        assert r["amount_eth"] == str(Web3.from_wei(ETH - RESERVE, "ether"))
        assert r["gas_limit"] == 2 * EST
        assert r["operator_eth"] == str(Web3.from_wei(RESERVE, "ether"))
        assert r["owner_eth"] == str(Web3.from_wei(ETH - RESERVE, "ether"))

    def test_sweep_zero_balance(self, gas_env):
        with pytest.raises(server.PreTxValidationError) as ei:
            server.withdraw_operator(account="solo")
        msg = str(ei.value)
        assert "holds 0 ETH" in msg and "nothing to sweep" in msg
        assert gas_env.sends == []

    def test_sweep_below_reserve(self, gas_env):
        gas_env.balances[gas_env.solo.operator_addr] = RESERVE
        with pytest.raises(server.PreTxValidationError) as ei:
            server.withdraw_operator(account="solo")
        msg = str(ei.value)
        assert "nothing to sweep" in msg
        assert str(Web3.from_wei(RESERVE, "ether")) in msg  # named reserve
        assert str(EST) in msg  # named estimate
        assert gas_env.sends == []

    def test_sweep_reverifies_actual_value(self, gas_env):
        # The verify estimate on the real sweep value comes back higher
        # than the probe: the reserve is recomputed from it (x2) and the
        # value re-derived, instead of sending a sweep that cannot clear.
        gas_env.balances[gas_env.solo.operator_addr] = ETH

        def two_stage_estimate(tx):
            return EST if tx["value"] == 1 else 3 * EST

        gas_env_w3 = server.w3
        gas_env_w3.eth.estimate_gas = two_stage_estimate
        r = server.withdraw_operator(account="solo")
        send = gas_env.sends[0]
        assert send["gas_limit"] == 6 * EST
        assert send["value"] == ETH - 6 * EST * GASPRICE
        assert r["gas_limit"] == 6 * EST

    def test_explicit_amount(self, gas_env):
        gas_env.balances[gas_env.solo.operator_addr] = ETH
        r = server.withdraw_operator("0.5", account="solo")
        assert gas_env.sends[0]["value"] == ETH // 2
        assert gas_env.sends[0]["gas_limit"] == 2 * EST
        assert r["amount_eth"] == "0.5"
        assert r["owner_eth"] == "0.5"  # post-transaction

    def test_explicit_insufficient_names_numbers(self, gas_env):
        gas_env.balances[gas_env.solo.operator_addr] = 3 * ETH // 10
        with pytest.raises(server.PreTxValidationError) as ei:
            server.withdraw_operator("0.3", account="solo")
        msg = str(ei.value)
        assert "0.3" in msg  # balance and requested amount
        assert str(Web3.from_wei(2 * EST * GASPRICE, "ether")) in msg
        assert str(EST) in msg  # named estimate
        assert gas_env.sends == []

    def test_explicit_estimation_failure(self, gas_env):
        # Requested amount exceeds the balance outright: the node-side
        # estimate fails and surfaces as a validation error naming the
        # observed balance.
        gas_env.balances[gas_env.solo.operator_addr] = 3 * ETH // 10
        with pytest.raises(server.PreTxValidationError) as ei:
            server.withdraw_operator("0.5", account="solo")
        msg = str(ei.value)
        assert "0.3" in msg and "eth_estimateGas failed" in msg
        assert gas_env.sends == []

    def test_no_owner_address(self, gas_env):
        with pytest.raises(ValueError, match="refusing to guess"):
            server.withdraw_operator(account="noown")
        assert gas_env.sends == []

    def test_recipient_not_expressible(self, gas_env):
        params = set(inspect.signature(server.withdraw_operator).parameters)
        assert params == {"amount_eth", "account"}


class TestOwnerMainnetHelper:
    """_owner_mainnet_eth unstubbed (the gas_env fixture stubs it)."""

    def test_happy_path(self, monkeypatch):
        fake = SimpleNamespace(
            eth=SimpleNamespace(get_balance=lambda addr: 5 * ETH // 2)
        )
        monkeypatch.setattr(server, "_w3_mainnet_balance", lambda: fake)
        assert server._owner_mainnet_eth("0xOwner") == "2.5"

    def test_rpc_error_reads_unavailable(self, monkeypatch):
        def boom(addr):
            raise TimeoutError("mainnet RPC timeout")

        fake = SimpleNamespace(eth=SimpleNamespace(get_balance=boom))
        monkeypatch.setattr(server, "_w3_mainnet_balance", lambda: fake)
        assert server._owner_mainnet_eth("0xOwner") == "unavailable"

    def test_unreachable_endpoint_reads_unavailable(self, monkeypatch):
        # Point the fully unmocked helper at a loopback black hole: it
        # degrades to "unavailable" instead of raising or hanging
        # (short per-request timeout).
        monkeypatch.setattr(
            server, "MAINNET_RPC_URL", "http://127.0.0.1:9/offline-test"
        )
        monkeypatch.setattr(server, "_w3_mainnet_balance_cached", None)
        addr = Web3().eth.account.from_key(KEY_A).address
        assert server._owner_mainnet_eth(addr) == "unavailable"

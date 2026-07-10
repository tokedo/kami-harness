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

# Third well-known local-dev throwaway key (standard anvil/hardhat test
# key; never funded on any real network, not a secret).
KEY_C = "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a"

ETH = 10**18
FEE = server._PLAIN_TRANSFER_FEE_WEI


@pytest.fixture()
def gas_env(monkeypatch):
    """Fabricated accounts with distinct owner/operator addresses, a
    balance ledger, and a _send_eth stub that moves value in the ledger
    (so post-transaction balance reads reflect the transfer)."""
    solo = server._Account("solo", KEY_A, KEY_B)
    noown = server._Account("noown", KEY_C, None)
    monkeypatch.setattr(server, "_accounts", {"solo": solo, "noown": noown})

    balances: dict[str, int] = {}
    fake_w3 = SimpleNamespace(
        eth=SimpleNamespace(get_balance=lambda addr: balances.get(addr, 0)),
        from_wei=Web3.from_wei,
        to_wei=Web3.to_wei,
    )
    monkeypatch.setattr(server, "w3", fake_w3)

    sends: list[dict] = []

    def fake_send_eth(from_key, from_addr, to_addr, value_wei):
        sends.append(
            {"from_key": from_key, "from": from_addr,
             "to": to_addr, "value": value_wei}
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
        solo=solo, noown=noown, balances=balances, sends=sends
    )


class TestGetGasBalance:
    def test_all_accounts_by_default(self, gas_env):
        gas_env.balances[gas_env.solo.operator_addr] = ETH // 2
        gas_env.balances[gas_env.solo.owner_addr] = 2 * ETH
        gas_env.balances[gas_env.noown.operator_addr] = ETH // 4

        r = server.get_gas_balance()
        assert set(r["balances"]) == {"solo", "noown"}
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
        assert noown["operator_eth"] == "0"

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
        assert send["value"] == ETH - FEE  # balance minus gas reserve
        assert r["direction"] == "operator->owner"
        assert r["amount_eth"] == str(Web3.from_wei(ETH - FEE, "ether"))
        assert r["operator_eth"] == str(Web3.from_wei(FEE, "ether"))
        assert r["owner_eth"] == str(Web3.from_wei(ETH - FEE, "ether"))

    def test_sweep_below_reserve(self, gas_env):
        gas_env.balances[gas_env.solo.operator_addr] = FEE
        with pytest.raises(ValueError, match="nothing to sweep") as ei:
            server.withdraw_operator(account="solo")
        msg = str(ei.value)
        assert str(Web3.from_wei(FEE, "ether")) in msg  # gas reserve
        assert gas_env.sends == []

    def test_explicit_amount(self, gas_env):
        gas_env.balances[gas_env.solo.operator_addr] = ETH
        r = server.withdraw_operator("0.5", account="solo")
        assert gas_env.sends[0]["value"] == ETH // 2
        assert r["amount_eth"] == "0.5"
        assert r["owner_eth"] == "0.5"  # post-transaction

    def test_explicit_insufficient_names_numbers(self, gas_env):
        gas_env.balances[gas_env.solo.operator_addr] = 3 * ETH // 10
        with pytest.raises(ValueError) as ei:
            server.withdraw_operator("0.3", account="solo")
        msg = str(ei.value)
        assert "0.3" in msg  # balance and requested amount
        assert str(Web3.from_wei(FEE, "ether")) in msg  # gas provision
        assert str(server._PLAIN_TRANSFER_GAS) in msg
        assert gas_env.sends == []

    def test_no_owner_address(self, gas_env):
        with pytest.raises(ValueError, match="refusing to guess"):
            server.withdraw_operator(account="noown")
        assert gas_env.sends == []

    def test_recipient_not_expressible(self, gas_env):
        params = set(inspect.signature(server.withdraw_operator).parameters)
        assert params == {"amount_eth", "account"}

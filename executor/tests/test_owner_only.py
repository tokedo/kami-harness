"""Offline tests for the owner-only account surface (v1.3.1).

The starting condition of a fresh deployment: a keys file holding only
MAIN_OWNER_KEY — the owner wallet exists, the operator wallet does not
yet. v1.3.0 warning-skipped such labels and loaded zero accounts,
leaving the agent's actual starting state (an owner wallet holding ETH)
represented nowhere in the agent-visible environment. These tests pin
the fix: the account loads, is visible in list_accounts and
get_gas_balance, and every operator-signing/-reading path fails with
the factual no-operator-wallet error — never a crash and never a
wrapped/swallowed message.
"""

from types import SimpleNamespace

import pytest
from web3 import Web3

from conftest import KEY_A, FakeContract

import server

OWNER_ADDR = Web3().eth.account.from_key(KEY_A).address

NO_OPERATOR = "has no operator wallet"


class TestOwnerOnlyLoad:
    """The exact v1.3.0 reproduction: an env with only MAIN_OWNER_KEY."""

    @pytest.fixture()
    def load_output(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(server, "_accounts", {})
        monkeypatch.setattr(server, "_ROSTER_PATH", tmp_path / "roster.yaml")
        monkeypatch.setattr(server.os, "environ", {"MAIN_OWNER_KEY": KEY_A})
        server._load_accounts()
        return capsys.readouterr().out

    def test_loads_account_without_skip_warning(self, load_output):
        assert "skipping account" not in load_output
        assert "WARNING" not in load_output
        assert "main (owner-only)" in load_output
        acct = server._accounts["main"]
        assert acct.owner_addr == OWNER_ADDR
        assert not acct.has_operator

    def test_list_accounts_non_empty(self, load_output):
        r = server.list_accounts()
        assert r["accounts"] == {
            "main": {
                "operator_address": None,
                "owner_address": OWNER_ADDR,
                "kamibots_registered": False,
            }
        }

    def test_get_gas_balance_non_empty(self, load_output, monkeypatch):
        monkeypatch.setattr(
            server,
            "w3",
            SimpleNamespace(
                eth=SimpleNamespace(get_balance=lambda addr: 10**18),
                from_wei=Web3.from_wei,
            ),
        )
        monkeypatch.setattr(server, "_owner_mainnet_eth", lambda addr: "2")
        r = server.get_gas_balance()
        assert r["balances"] == {
            "main": {
                "owner_address": OWNER_ADDR,
                "owner_eth": "1",
                "owner_mainnet_eth": "2",
            }
        }


@pytest.fixture()
def owner_only(monkeypatch):
    """Registry holding a single owner-only 'main' account."""
    main = server._Account("main", None, KEY_A)
    monkeypatch.setattr(server, "_accounts", {"main": main})
    return main


class TestNoOperatorErrors:
    """Operator paths on an owner-only account raise the factual error."""

    def test_property_access_raises_factual_error(self, owner_only):
        with pytest.raises(ValueError) as ei:
            owner_only.operator_addr
        assert str(ei.value) == (
            "account 'main' has no operator wallet; "
            "create_operator_wallet generates one"
        )
        with pytest.raises(ValueError, match=NO_OPERATOR):
            owner_only.operator_key

    def test_fund_operator(self, owner_only):
        with pytest.raises(ValueError, match=NO_OPERATOR):
            server.fund_operator("0.01", account="main")

    def test_withdraw_operator(self, owner_only):
        with pytest.raises(ValueError, match=NO_OPERATOR):
            server.withdraw_operator(account="main")

    def test_register_account_not_wrapped_as_revert(self, owner_only):
        with pytest.raises(ValueError) as ei:
            server.register_account("newbie", account="main")
        msg = str(ei.value)
        assert NO_OPERATOR in msg
        assert "create_operator_wallet" in msg
        assert "would revert" not in msg  # not wrapped by the dry-run

    def test_transfer_kami(self, owner_only):
        with pytest.raises(ValueError, match=NO_OPERATOR):
            server.transfer_kami(
                kami_ids=[1],
                to_address="0x00000000000000000000000000000000000000Aa",
                account="main",
            )

    def test_sacrifice_kami_not_wrapped_as_revert(self, owner_only):
        with pytest.raises(ValueError) as ei:
            server.sacrifice_kami(1, account="main")
        msg = str(ei.value)
        assert NO_OPERATOR in msg
        assert "dry-run reverted" not in msg  # not wrapped by the dry-run

    def test_equip_all_batch_raises_instead_of_skipping(self, owner_only):
        with pytest.raises(ValueError, match=NO_OPERATOR):
            server.equip_all_batch(
                [{"kami_id": 1, "item_index": 1}], account="main"
            )

    def test_sacrifice_batch_raises_instead_of_skipping(self, owner_only):
        with pytest.raises(ValueError, match=NO_OPERATOR):
            server.sacrifice_kami_batch([1, 2], account="main")

    def test_check_quest_completable_raises_instead_of_false(
        self, owner_only, chain
    ):
        chain["system.quest.complete"] = FakeContract(
            {"executeTyped": lambda q_id: b""}
        )
        with pytest.raises(ValueError, match=NO_OPERATOR):
            server.check_quest_completable(1, account="main")

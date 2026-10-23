"""The two signers, and the two one-key rosters.

Owner-only (v1.3.1): the starting condition of a fresh deployment — a
keys file holding only MAIN_OWNER_KEY. v1.3.0 warning-skipped such
labels and loaded zero accounts, leaving the agent's actual starting
state (an owner wallet holding ETH) represented nowhere in the
agent-visible environment. The account loads, is visible in
list_accounts and get_gas_balance, and every operator-signing/-reading
path fails with the factual no-operator-wallet error — never a crash and
never a wrapped/swallowed message.

Operator signs (5.0.0, upstream patch 0.4.5, 04cb25f8): the systems of
auction buys, trades, item transfers and gacha resolve the sender with
LibAccount.getByOwnerOrOperator, so nine tools sign with the account's
OPERATOR key — proven on the hermetic node by the sender it sees — and an
operator-only roster (an operator key, no owner key) can use all nine.
The gacha reveal resolves no account, so it signs with the operator too.
The systems that stay owner-only on chain (registration, the newcomer
vendor, KamiSwap purchases, the portal's owner lanes) keep their owner
signer and refuse legibly without an owner key.
"""

from types import SimpleNamespace

import eth_abi
import pytest
import web3._utils.threads as web3_threads
from web3 import Web3

from conftest import KEY_A, KEY_B, FakeContract
from fakenode import FakeNode, Result, VirtualClock, addr_for, make_w3

import server

OWNER_ADDR = Web3().eth.account.from_key(KEY_A).address

NO_OPERATOR = "has no operator wallet"


class TestOwnerOnlyLoad:
    """The exact v1.3.0 reproduction: an env with only MAIN_OWNER_KEY."""

    @pytest.fixture()
    def load_output(self, secret_store, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(server, "_accounts", {})
        monkeypatch.setattr(server, "_ROSTER_PATH", tmp_path / "roster.yaml")
        monkeypatch.setattr(server.os, "environ", {"MAIN_OWNER_KEY": KEY_A})
        server._load_accounts()
        captured = capsys.readouterr()
        # The registry report is diagnostics, not protocol: stdout is the
        # stdio JSON-RPC transport and must carry nothing but JSON-RPC.
        assert captured.out == ""
        return captured.err

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
        # 4.3.0: each balance also in exact wei.
        assert r["balances"] == {
            "main": {
                "owner_address": OWNER_ADDR,
                "owner_eth": "1",
                "owner_wei": str(10**18),
                "owner_mainnet_eth": "2",
                "owner_mainnet_wei": str(2 * 10**18),
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


# ---------------------------------------------------------------------------
# 5.0.0 — the operator signs nine tools (patch 0.4.5)
# ---------------------------------------------------------------------------

# Public local-dev key #2 (anvil/hardhat), never funded anywhere.
KEY_C = "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a"
AID = 0x4242
OTHER_AID = 0x5151


@pytest.fixture()
def op_chain(monkeypatch):
    """The hermetic node; every gate a chain read would answer passes.

    `split` holds an owner key and a DIFFERENT operator key, so the
    sender the node sees says which one signed; `oponly` holds an
    operator key and no owner key (the agent's Season-2 roster)."""
    node = FakeNode(server.CHAIN_ID)
    w3 = server._install_read_retry(make_w3(node))
    clock = VirtualClock()
    node.clock = clock
    t0, b0 = clock.now, node.block
    clock.on_sleep.append(lambda now: setattr(
        node, "block", max(node.block, b0 + int(now - t0))))
    monkeypatch.setattr(server, "w3", w3)
    monkeypatch.setattr(server, "time", clock)
    monkeypatch.setattr(web3_threads, "time", clock)
    monkeypatch.setattr(server, "_resolve_system", addr_for)
    monkeypatch.setattr(server, "_resolve_component", addr_for)
    split = server._Account("split", KEY_B, KEY_A)
    oponly = server._Account("oponly", KEY_C, None)
    monkeypatch.setattr(server, "_accounts",
                        {"split": split, "oponly": oponly})
    # An account's entity is uint256(its owner address): split's owner is
    # in the roster; oponly's owner wallet is elsewhere (entity AID).
    split_aid = int(split.owner_addr, 16)
    bound = {split.operator_addr: split_aid, oponly.operator_addr: AID}
    monkeypatch.setattr(server, "_account_id_for_operator",
                        lambda addr: bound.get(addr))
    monkeypatch.setattr(server, "_require_registered_owner",
                        lambda a: split_aid)
    # Kami 45 belongs to whichever account the call names.
    current = {"aid": split_aid}
    real_get = server._get_account

    def get_account(label):
        acct = real_get(label)
        current["aid"] = split_aid if acct is split else AID
        return acct

    monkeypatch.setattr(server, "_get_account", get_account)
    monkeypatch.setattr(server, "_kami_owner_id", lambda k: current["aid"])
    monkeypatch.setattr(server, "_kami_state", lambda k: "RESTING")
    monkeypatch.setattr(server, "_inventory_balance", lambda h, i: 10**9)
    monkeypatch.setattr(server, "_trade_terms", lambda t: None)
    monkeypatch.setattr(
        server, "get_account_trades",
        lambda account: {"trades": [
            {"trade_id_hex": "0x77", "status": "EXECUTED"}]})
    # The commit is the transaction under test; its reveal has its own.
    monkeypatch.setattr(
        server, "_gacha_commit_and_reveal",
        lambda account, commit, tool: {"commit": commit, "reveal": None,
                                       "commit_ids": []})
    # Registered accounts answer a name (the item-transfer target check).
    names = {AID: "self", split_aid: "split", OTHER_AID: "other"}
    node.handle(addr_for("component.name"), "safeGet(uint256)",
                lambda n, c, a, k: Result(output=eth_abi.encode(
                    ["string"], [names.get(
                        eth_abi.decode(["uint256"], a[:32])[0], "")])))
    return node, split, oponly


def _senders(node, system_id):
    return [t.sender for t in node.executed if (t.to or "").lower()
            == addr_for(system_id).lower()]


OTHER_OWNER = "0x" + f"{OTHER_AID:040x}"

NINE = [
    ("auction_buy", dict(item_index=10, amount=1), "system.auction.buy"),
    ("create_trade", dict(sell_item=11301, sell_amount=1, buy_item=1,
                          buy_amount=5), "system.trade.create"),
    ("take_trade", dict(trade_id="0x77"), "system.trade.execute"),
    ("cancel_trade", dict(trade_id="0x77"), "system.trade.cancel"),
    ("complete_trade", dict(trade_id="0x77"), "system.trade.complete"),
    ("complete_all_trades", dict(), "system.trade.complete"),
    ("transfer_items", dict(item_indices=[11301], amounts=[2],
                            to_address=OTHER_OWNER), "system.item.transfer"),
    ("gacha_use", dict(amount=1), "system.kami.gacha.mint"),
    ("gacha_reroll", dict(kami_ids=[45]), "system.kami.gacha.reroll"),
]


class TestTheOperatorSigns:
    """Each of the nine lands with the OPERATOR as its sender."""

    @pytest.mark.parametrize("tool,kwargs,system", NINE,
                             ids=[t[0] for t in NINE])
    def test_the_operator_is_the_sender(self, op_chain, tool, kwargs,
                                        system):
        node, split, _oponly = op_chain
        getattr(server, tool)(account="split", **kwargs)
        senders = _senders(node, system)
        assert senders == [split.operator_addr.lower()], (
            f"{tool}: sent by {senders}, operator {split.operator_addr}, "
            f"owner {split.owner_addr}")

    def test_the_gacha_reveal_signs_with_the_operator(self, op_chain):
        """The reveal system resolves no account (anyone may reveal), so
        a mint by an operator-only roster can be revealed by it too."""
        node, split, oponly = op_chain
        for acct in (split, oponly):
            out = server.gacha_reveal(["7"], account=acct.label)
            assert out["status"] == "success"
            assert _senders(node, "system.kami.gacha.reveal")[-1] == (
                acct.operator_addr.lower())


class TestAnOperatorOnlyRoster:
    """An operator key and no owner key: the nine are all reachable."""

    @pytest.mark.parametrize("tool,kwargs,system", NINE,
                             ids=[t[0] for t in NINE])
    def test_each_of_the_nine(self, op_chain, tool, kwargs, system):
        node, _split, oponly = op_chain
        out = getattr(server, tool)(account="oponly", **kwargs)
        assert _senders(node, system) == [oponly.operator_addr.lower()], out

    def test_create_a_trade_and_transfer_items(self, op_chain):
        node, _split, oponly = op_chain
        t = server.create_trade(11301, 1, 1, 5, account="oponly")
        x = server.transfer_items([11301], [2], to_address=OTHER_OWNER,
                                  account="oponly")
        assert t["status"] == x["status"] == "success"
        assert x["destination_owner"] == Web3.to_checksum_address(OTHER_OWNER)
        assert {t.sender for t in node.executed} == {
            oponly.operator_addr.lower()}


class TestTheOwnerOnlySetStillRefuses:
    """Owner-only on chain at the pin: registration, the newcomer
    vendor, KamiSwap purchases, the portal's owner lanes. An operator-only
    roster is refused before anything is read or signed, naming the
    missing key."""

    def test_register_account(self, op_chain):
        with pytest.raises(ValueError, match="has no owner key"):
            server.register_account("newbie", account="oponly")

    def test_newbie_vendor_buy(self, op_chain, monkeypatch):
        monkeypatch.setattr(server, "_require_registered_owner",
                            _real_owner_gate)
        with pytest.raises(ValueError, match="has no owner key"):
            server.newbie_vendor_buy(1, "0.01", account="oponly")

    def test_buy_kami_refuses_before_the_listing_read(self, op_chain,
                                                      monkeypatch):
        def no_read(*a, **k):
            raise AssertionError("the listing read ran")
        monkeypatch.setattr(server, "get_kami_market_listings", no_read)
        with pytest.raises(ValueError, match="has no owner key"):
            server.buy_kami([5], "0.01", account="oponly")

    def test_portal_deposit(self, op_chain):
        with pytest.raises(ValueError, match="has no owner key"):
            server.portal_deposit(1, 10, account="oponly")

    def test_portal_withdraw_to_the_owner(self, op_chain, monkeypatch):
        monkeypatch.setattr(server, "_require_registered_owner",
                            _real_owner_gate)
        monkeypatch.setattr(server, "_portal_item",
                            lambda item: {"portal": None, "scale": 0})
        with pytest.raises(ValueError, match="has no owner key"):
            server.portal_withdraw(1, 10, to="owner", account="oponly")

    def test_nothing_was_signed(self, op_chain):
        node, _split, _oponly = op_chain
        for call in (lambda: server.register_account("x", account="oponly"),
                     lambda: server.portal_deposit(1, 10, account="oponly")):
            with pytest.raises(ValueError):
                call()
        assert node.executed == []


_real_owner_gate = server._require_registered_owner

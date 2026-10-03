"""4.0.0 leg B — the surface: token portal, harvest caps, the time box,
the droptable read from chain.

All hermetic: the fake node in fakenode.py models the portal system,
its receipt components and configs, and the ERC-20 it pays out in,
straight from upstream TokenPortalSystem / LibTokenPortal at the pin.
"""

from __future__ import annotations

from collections import defaultdict

import eth_abi
import pytest
from eth_utils import keccak

import server
from conftest import KEY_A, KEY_B
from fakenode import Result, addr_for
from test_h400_send_path import AID, Game, chain_env  # noqa: F401

ETH_TOKEN = "0xE1Ff7038eAAAF027031688E1535a055B2Bac2546"
ONYX_TOKEN = "0x4BaDFb501Ab304fF11217C44702bb9E9732E7CF4"
WORLD_EVENT = "0x" + server._WORLD_EVENT_TOPIC
TRANSFER = "0x" + server._TRANSFER_TOPIC


def _bool(v):
    return Result(output=eth_abi.encode(["bool"], [bool(v)]))


def _addr(a):
    return Result(output=eth_abi.encode(["address"], [a]))


def _u(v):
    return Result(output=eth_abi.encode(["uint256"], [v]))


def _config_id(name):
    return int.from_bytes(keccak(b"is.config" + name.encode()), "big")


def _pack(flat, bps):
    return (flat << 224) | (bps << 192)


class Portal:
    """upstream TokenPortalSystem + LibTokenPortal, as contract handlers."""

    def __init__(self, node, game, clock, account_id, operator):
        self.node, self.game, self.clock = node, game, clock
        self.aid = account_id
        self.operator = operator.lower()
        self.enabled = True
        self.items = {100: (ONYX_TOKEN, 2, False), 103: (ETH_TOKEN, 5, True)}
        self.config = {
            _config_id("PORTAL_ITEM_EXPORT_TAX"): _pack(1, 50),
            _config_id("PORTAL_ITEM_IMPORT_TAX"): _pack(1, 50),
            _config_id("PORTAL_TOKEN_EXPORT_DELAY"): 43_200,
        }
        self.receipts: dict[int, dict] = {}
        self.next_id = 2 ** 160 + 1
        self.token_bal = defaultdict(int)
        self.allowance = defaultdict(int)
        sys_ = addr_for("system.erc20.portal")
        h = node.handle
        h(sys_, "isEnabled()", lambda n, c, a, k: _bool(self.enabled))
        h(sys_, "itemAddrs(uint32)", lambda n, c, a, k: _addr(
            self.items.get(eth_abi.decode(["uint32"], a)[0], ("0x" + "00" * 20,))[0]))
        h(sys_, "itemScales(uint32)", lambda n, c, a, k: Result(
            output=eth_abi.encode(["int32"], [self.items.get(
                eth_abi.decode(["uint32"], a)[0], (0, 0))[1]])))
        h(sys_, "laneItems(uint32)", lambda n, c, a, k: _bool(self.items.get(
            eth_abi.decode(["uint32"], a)[0], (0, 0, False))[2]))
        h(sys_, "withdraw(uint32,uint256)", self._withdraw(False))
        h(sys_, "withdrawToOperator(uint32,uint256)", self._withdraw(True))
        h(sys_, "claim(uint256)", self._claim)
        h(sys_, "cancel(uint256)", self._cancel)
        h(sys_, "deposit(uint32,uint256)", self._deposit)
        comps = {
            "component.id.token.withdraw.owns": lambda r: _u(r["acc"]),
            "component.Time.End": lambda r: _u(r["end"]),
            "component.tax": lambda r: _u(r["tax"]),
        }
        for comp, fn in comps.items():
            h(addr_for(comp), "safeGet(uint256)", self._receipt_read(fn))
        h(addr_for("component.index.item"), "safeGet(uint256)",
          lambda n, c, a, k: Result(output=eth_abi.encode(
              ["uint32"], [self.receipts.get(_id(a), {}).get("item", 0)])))
        h(addr_for("component.has.flag"), "has(uint256)", self._has_flag)
        h(addr_for("component.is.disabled"), "has(uint256)",
          lambda n, c, a, k: _bool(self.receipts.get(_id(a), {}).get("paused")))
        h(addr_for("component.address.operator"), "safeGet(uint256)",
          lambda n, c, a, k: _addr(self.operator))
        # component.value: configs, receipt token amounts, inventories
        h(addr_for("component.value"), "safeGet(uint256)", self._value)
        for token in (ETH_TOKEN, ONYX_TOKEN):
            t = token.lower()
            h(t, "balanceOf(address)", lambda n, c, a, k, t=t: _u(
                self.token_bal[(t, eth_abi.decode(["address"], a)[0].lower())]))
            h(t, "allowance(address,address)", lambda n, c, a, k, t=t: _u(
                self.allowance[(t, eth_abi.decode(["address"], a[:32])[0].lower())]))
            h(t, "approve(address,uint256)", self._approve(t))

    def _receipt_read(self, fn):
        def read(n, c, a, k):
            r = self.receipts.get(_id(a))
            return fn(r) if r else _u(0)
        return read

    def _has_flag(self, n, c, a, k):
        fid = _id(a)
        for rid, r in self.receipts.items():
            if r["lane"] and fid == int.from_bytes(keccak(
                    b"has.flag" + rid.to_bytes(32, "big")
                    + server._PORTAL_OPERATOR_FLAG.encode()), "big"):
                return _bool(True)
        return _bool(False)

    def _value(self, n, c, a, k):
        eid = _id(a)
        if eid in self.config:
            return _u(self.config[eid])
        if eid in self.receipts:
            return _u(self.receipts[eid]["wei"])
        for item, count in list(self.game.inv.items()):
            if eid == server._inventory_entity_id(self.aid, item):
                return _u(count)
        return _u(0)

    def _tax(self, amt):
        return amt * 50 // 10_000 + 1

    def _withdraw(self, lane):
        def run(n, caller, args, commit):
            item, amt = eth_abi.decode(["uint32", "uint256"], args)
            if not self.enabled:
                return Result(status=0, revert="Token Portal: disabled")
            if item not in self.items:
                return Result(status=0, revert="Token Portal: item not registered")
            if lane and not self.items[item][2]:
                return Result(status=0, revert="Token Portal: item not on the operator lane")
            tax = self._tax(amt)
            if self.game.inv[item] < amt:
                return Result(status=0, revert="Inventory: insufficient")
            logs = []
            if commit:
                rid = self.next_id
                self.next_id += 1
                scale = self.items[item][1]
                wei = (amt - tax) * 10 ** (18 - scale)
                self.receipts[rid] = {"acc": self.aid, "item": item,
                                      "wei": wei, "tax": tax,
                                      "end": int(self.clock.now) + 43_200,
                                      "lane": lane, "paused": False}
                self.game.inv[item] -= amt
                value = eth_abi.encode(
                    ["uint256", "uint256", "uint256", "uint32", "uint256",
                     "uint256", "address", "uint256"],
                    [int(self.clock.now), self.aid, rid, item, amt, tax,
                     self.items[item][0], wei])
                data = eth_abi.encode(["uint8[]", "bytes"], [[1] * 8, value])
                logs.append((addr_for("emitter"), [
                    WORLD_EVENT, "0x" + keccak(b"PORTAL_TOKEN_WITHDRAW").hex()],
                    data))
                self.last_sender = caller.sender
            return Result(gas_used=400_000, logs=logs,
                          output=eth_abi.encode(["uint256"], [self.next_id]))
        return run

    def _claim(self, n, caller, args, commit):
        (rid,) = eth_abi.decode(["uint256"], args)
        r = self.receipts.get(rid)
        if r is None:
            return Result(status=0, revert="not receipt owner")
        if self.clock.now < r["end"]:
            return Result(status=0, revert="withdrawal not ready")
        payee = self.operator if r["lane"] else self.owner
        logs = []
        if commit:
            token = self.items[r["item"]][0]
            logs.append((token.lower(), [
                TRANSFER, "0x" + "00" * 12 + addr_for("component.token.holder")[2:].lower(),
                "0x" + "00" * 12 + payee[2:]], eth_abi.encode(["uint256"], [r["wei"]])))
            del self.receipts[rid]
            self.claim_sender = caller.sender
        return Result(gas_used=300_000, logs=logs)

    def _cancel(self, n, caller, args, commit):
        (rid,) = eth_abi.decode(["uint256"], args)
        r = self.receipts.get(rid)
        if r is None:
            return Result(status=0, revert="not receipt owner")
        if commit:
            scale = self.items[r["item"]][1]
            self.game.inv[r["item"]] += r["wei"] // 10 ** (18 - scale)
            del self.receipts[rid]
        return Result(gas_used=300_000)

    def _approve(self, token):
        def run(n, caller, args, commit):
            spender, value = eth_abi.decode(["address", "uint256"], args)
            if commit:
                self.allowance[(token, caller.sender)] = value
            return Result(gas_used=60_000, output=eth_abi.encode(["bool"], [True]))
        return run

    def _deposit(self, n, caller, args, commit):
        item, amt = eth_abi.decode(["uint32", "uint256"], args)
        token = self.items[item][0].lower()
        wei = amt * 10 ** (18 - self.items[item][1])
        if self.allowance[(token, caller.sender)] < wei:
            return Result(status=0, revert="ERC20: insufficient allowance")
        if commit:
            self.allowance[(token, caller.sender)] -= wei
            self.token_bal[(token, caller.sender)] -= wei
            self.game.inv[item] += amt - self._tax(amt)
        return Result(gas_used=500_000)


def _id(args):
    return eth_abi.decode(["uint256"], args[:32])[0]


@pytest.fixture()
def portal_env(chain_env, monkeypatch):
    node, game, clock, op = chain_env
    split = server._Account("split", KEY_B, KEY_A)    # operator B, owner A
    monkeypatch.setitem(server._accounts, "split", split)
    node.set_nonce(split.operator_addr, 40)
    node.set_nonce(split.owner_addr, 500)
    aid = server._account_entity_id("split")
    portal = Portal(node, game, clock, aid, split.operator_addr)
    portal.owner = split.owner_addr.lower()
    monkeypatch.setattr(server, "_require_registered_owner", lambda a: aid)
    monkeypatch.setattr(server, "_require_registered_operator", lambda a: aid)
    monkeypatch.setattr(server, "_inventory_balance",
                        lambda holder, item: game.inv[item])
    game.inv[103] = 200_000
    game.inv[100] = 5_000
    return node, game, clock, portal, split


# ---------------------------------------------------------------------------
# B4 — the token portal
# ---------------------------------------------------------------------------

def test_portal_withdraw_dry_run_states_tax_net_and_claimable_at(portal_env):
    node, game, clock, portal, split = portal_env
    out = server.portal_withdraw(103, 100_000, account="split", dry_run=True)
    assert out["dry_run"] is True and "tx_hash" not in out
    assert out["tax"] == {"flat": 1, "bps": 50, "items": 501}
    assert out["net_items"] == 99_499
    assert out["token"] == {"address": ETH_TOKEN,
                            "amount_wei": str(99_499 * 10 ** 13),
                            "amount": "0.99499"}
    assert out["delay_s"] == 43_200
    assert out["claimable_at"] == int(clock.now) + 43_200
    assert not node.sends


def test_portal_withdraw_to_operator_is_operator_signed_and_decodes_the_receipt(
    portal_env,
):
    node, game, clock, portal, split = portal_env
    out = server.portal_withdraw(103, 100_000, to="operator", account="split")
    assert out["status"] == "success"
    assert portal.last_sender == split.operator_addr.lower()
    rid = int(out["receipt_id"])
    assert rid in portal.receipts and portal.receipts[rid]["lane"] is True
    assert out["claimable_at"] == portal.receipts[rid]["end"]
    assert game.inv[103] == 100_000


def test_portal_withdraw_to_owner_is_owner_signed(portal_env):
    node, game, clock, portal, split = portal_env
    out = server.portal_withdraw(100, 1_000, account="split")
    assert portal.last_sender == split.owner_addr.lower()
    assert portal.receipts[int(out["receipt_id"])]["lane"] is False


@pytest.mark.parametrize("case, call, needle", [
    ("disabled", lambda: server.portal_withdraw(103, 10, account="split"),
     "the token portal is disabled"),
    ("unregistered", lambda: server.portal_withdraw(77, 10, account="split"),
     "is not registered on the token portal"),
    ("not on the lane", lambda: server.portal_withdraw(
        100, 1_000, to="operator", account="split"),
     "not on the portal's operator lane"),
    ("balance", lambda: server.portal_withdraw(103, 300_000, account="split"),
     "holds 200000 of item 103"),
    ("tax", lambda: server.portal_withdraw(103, 1, account="split"),
     "is not below the amount 1"),
])
def test_portal_withdraw_refuses_before_signing(portal_env, case, call, needle):
    node, game, clock, portal, split = portal_env
    if case == "disabled":
        portal.enabled = False
    with pytest.raises(server.PreTxValidationError) as ei:
        call()
    assert needle in str(ei.value)
    assert not node.sends


def test_portal_claim_waits_for_the_delay_then_pays_the_current_operator(
    portal_env,
):
    node, game, clock, portal, split = portal_env
    rid = server.portal_withdraw(103, 100_000, to="operator",
                                 account="split")["receipt_id"]
    with pytest.raises(server.PreTxValidationError, match="claimable at"):
        server.portal_claim(rid, account="split")
    clock.sleep(43_201)
    out = server.portal_claim(rid, account="split")
    assert out["route"] == "operator"
    assert out["payee"].lower() == split.operator_addr.lower()
    assert out["amount_wei"] == str(99_499 * 10 ** 13)
    assert out["amount"] == "0.99499"
    assert portal.claim_sender == split.operator_addr.lower()


def test_portal_claim_refuses_a_receipt_that_is_not_pending(portal_env):
    node, game, clock, portal, split = portal_env
    with pytest.raises(server.PreTxValidationError, match="no pending portal receipt"):
        server.portal_claim("12345", account="split")


def test_portal_cancel_returns_the_items_but_not_the_tax(portal_env):
    node, game, clock, portal, split = portal_env
    rid = server.portal_withdraw(103, 100_000, account="split")["receipt_id"]
    out = server.portal_cancel(rid, account="split")
    assert out["items_refunded"] == 99_499 and out["tax_not_refunded"] == 501
    assert game.inv[103] == 200_000 - 501


def test_portal_deposit_approves_the_spender_when_short_then_deposits(
    portal_env,
):
    node, game, clock, portal, split = portal_env
    owner = split.owner_addr.lower()
    portal.token_bal[(ETH_TOKEN.lower(), owner)] = 10 ** 18
    out = server.portal_deposit(103, 50_000, account="split")
    assert [t["step"] for t in out["txs"]] == ["approve", "deposit"]
    assert out["credited"] == 50_000 - 251
    assert game.inv[103] == 200_000 + 50_000 - 251
    # Allowance now covers it: a second deposit sends no approve.
    portal.token_bal[(ETH_TOKEN.lower(), owner)] = 10 ** 18
    portal.allowance[(ETH_TOKEN.lower(), owner)] = 10 ** 18
    out2 = server.portal_deposit(103, 10_000, account="split")
    assert [t["step"] for t in out2["txs"]] == ["deposit"]


def test_portal_deposit_refuses_a_short_token_balance(portal_env):
    node, game, clock, portal, split = portal_env
    with pytest.raises(server.PreTxValidationError, match="holds 0 of the token"):
        server.portal_deposit(103, 50_000, account="split")
    assert not node.sends


# ---------------------------------------------------------------------------
# B5 — harvest caps and the SIZE/ITEM diagnosis
# ---------------------------------------------------------------------------

@pytest.fixture()
def harvest_env(chain_env, monkeypatch):
    node, game, clock, op = chain_env
    bad = set()
    limit = {"n": 10}

    def batched(n, c, args, commit):
        (ids, _node, _a, _b) = eth_abi.decode(
            ["uint256[]", "uint32", "uint256", "uint256"], args)
        if len(ids) > limit["n"]:
            return Result(status=0, revert="out of gas: EVMCall failed")
        if any(i in bad for i in ids):
            return Result(status=0, revert="Reverted")
        return Result(gas_used=900_000 * len(ids))

    def single(n, c, args, commit):
        (eid, _node, _a, _b) = eth_abi.decode(
            ["uint256", "uint32", "uint256", "uint256"], args)
        if eid in bad:
            return Result(status=0, revert="kami on cooldown")
        return Result(gas_used=900_000)

    h = addr_for("system.harvest.start")
    node.handle(h, "executeBatched(uint256[],uint32,uint256,uint256)", batched)
    node.handle(h, "executeTyped(uint256,uint32,uint256,uint256)", single)
    return node, bad, limit


def test_more_than_ten_kamis_are_refused_before_signing(harvest_env):
    node, bad, limit = harvest_env
    with pytest.raises(server.PreTxValidationError, match="at most 10 per call"):
        server.harvest_start(list(range(1, 12)), 5, account="testa")
    assert not node.sends


def test_a_batch_refused_while_every_kami_passes_alone_is_a_size_failure(
    harvest_env,
):
    node, bad, limit = harvest_env
    limit["n"] = 4
    with pytest.raises(server.PreTxValidationError) as ei:
        server.harvest_start(list(range(1, 8)), 5, account="testa")
    assert "BATCH SIZE" in str(ei.value) and "Reverted" not in str(ei.value)
    assert not node.sends


def test_a_batch_refused_for_one_kami_names_the_kami(harvest_env):
    node, bad, limit = harvest_env
    bad.add(server._kami_entity_id(3))
    with pytest.raises(server.PreTxValidationError) as ei:
        server.harvest_start([1, 2, 3, 4], 5, account="testa")
    assert "failed on an ITEM: kami #3: kami on cooldown" in str(ei.value)
    assert "kami #1" not in str(ei.value) and not node.sends


def test_harvest_start_dry_run_sends_nothing(harvest_env):
    node, bad, limit = harvest_env
    out = server.harvest_start([1, 2], 5, account="testa", dry_run=True)
    assert out == {"dry_run": True, "kamis": [1, 2], "node_index": 5,
                   "gas_limit": server._harvest_gas("harvest_start", 2)}
    assert not node.sends


# ---------------------------------------------------------------------------
# B6 — the call time box
# ---------------------------------------------------------------------------

def test_a_loop_stops_inside_its_box_and_says_what_remains(
    chain_env, monkeypatch,
):
    node, game, clock, op = chain_env
    game.inv[11301] = 50
    game.after_commit.append(
        lambda system, sender: clock.sleep(4) if system == "feed" else None)
    monkeypatch.setattr(server, "CALL_BUDGET_S", 30)
    t0 = clock.now
    out = server.run_tool("use_item_batch", kami_id=21, item_id=11301,
                          count=20, account="testa")
    assert out["time_boxed"] is True
    assert out["used"] + out["remaining"]["uses"] == 20
    assert 0 < out["used"] < 20
    assert clock.now - t0 <= 30
    assert game.inv[11301] == 50 - out["used"]


def test_a_single_transaction_is_never_cut_by_the_box(chain_env, monkeypatch):
    node, game, clock, op = chain_env
    game.xp[server._kami_entity_id(5)] = 1_000
    monkeypatch.setattr(server, "CALL_BUDGET_S", 0.001)
    out = server.run_tool("level_up_kami", kami_id=5, account="testa")
    assert out["status"] == "success"


# ---------------------------------------------------------------------------
# B1 — no third party; the droptable comes from chain
# ---------------------------------------------------------------------------

def test_no_strategy_service_remains():
    src = (server._REPO / "executor" / "server.py").read_text()
    assert "kamibots" not in src.lower()
    assert not hasattr(server, "_api_get")


def test_the_droptable_is_read_from_chain(chain_env):
    node, game, clock, op = chain_env
    reg = server._scavenge_registry_id(53)
    anchor = int.from_bytes(server.Web3.solidity_keccak(
        ["string", "uint256"], ["scavenge.reward", reg]), "big")
    dt, other = 2 ** 200 + 1, 2 ** 200 + 2
    node.handle(addr_for("component.id.anchor"), "getEntitiesWithValue(uint256)",
                lambda n, c, a, k: Result(output=eth_abi.encode(
                    ["uint256[]"], [[dt, other] if _id(a) == anchor else []])))
    node.handle(addr_for("component.type"), "safeGet(uint256)",
                lambda n, c, a, k: Result(output=eth_abi.encode(
                    ["string"], ["ITEM_DROPTABLE" if _id(a) == dt else "ITEM"])))
    node.handle(addr_for("component.keys"), "safeGet(uint256)",
                lambda n, c, a, k: Result(output=eth_abi.encode(
                    ["uint32[]"], [[1001, 1004, 1007]])))
    node.handle(addr_for("component.weights"), "safeGet(uint256)",
                lambda n, c, a, k: Result(output=eth_abi.encode(
                    ["uint256[]"], [[9, 7, 4]])))
    game.commits[reg] = 300                       # component.value(reg)
    out = server.get_scavenge_droptable(53)
    assert out["node_name"] == "Blooming Tree" and out["tier_cost"] == 300
    (table,) = out["droptables"]
    assert table["keys"] == [1001, 1004, 1007] and table["weights"] == [9, 7, 4]
    probs = [i["probability"] for i in table["items"]]
    assert abs(sum(probs) - 1) < 1e-9 and probs[0] == 512 / (512 + 128 + 16)


# ---------------------------------------------------------------------------
# B8 — register_account names the new revert
# ---------------------------------------------------------------------------

def test_register_account_names_the_operator_is_owner_revert(
    accounts, chain, monkeypatch,
):
    from conftest import FakeContract

    def refuse(*a):
        raise ValueError("execution reverted: Account: Operator is an account owner")

    chain["system.account.register"] = FakeContract({"executeTyped": refuse})
    with pytest.raises(ValueError) as ei:
        server.register_account("someone", account="testa")
    assert "Operator is an account owner" in str(ei.value)
    assert "an owner cannot be another account's operator" in str(ei.value)

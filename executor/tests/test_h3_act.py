"""Offline tests for the H3 ACT additions (2.0.0-dev): liquidate_kami,
gacha_use / gacha_reroll / gacha_reveal, chat_send.

No network, keys, or chain access.
"""

from types import SimpleNamespace

import pytest

import server

BIG_CID = int.from_bytes(bytes(range(200, 232)), "big")


def _gacha_receipt(*cids: int):
    logs = []
    for cid in cids:
        logs.append(SimpleNamespace(
            topics=[
                bytes.fromhex(server._STORE_SET_RECORD_EVENT),
                b"\x00" * 32,
                b"\x00" * 32,
                cid.to_bytes(32, "big"),
            ],
            data=b"\x00\x20" + server._GACHA_COMMIT_MARKER,
        ))
    logs.append(SimpleNamespace(topics=[b"\xff" * 32], data=b"unrelated"))
    return SimpleNamespace(logs=logs)


@pytest.fixture()
def gacha_flow(accounts, validation_ok, monkeypatch):
    """Commit sender returning a GACHA_COMMIT receipt, fast clock, and a
    controllable reveal."""
    state = {
        "commits": [],
        "reveals": [],
        "reveal_result": {
            "tx_hash": "0xrev", "status": "success", "block": 12,
            "gas_used": 500_000,
        },
        "reveal_error": None,
    }

    def commit_owner(account, system_id, abi, args, gas_limit=None,
                     value_wei=0, return_receipt=False):
        state["commits"].append({"system": system_id, "args": args})
        res = {"tx_hash": "0xcommit", "status": "success", "block": 10,
               "gas_used": 1_000_000, "account": account}
        if return_receipt:
            res["_receipt"] = _gacha_receipt(BIG_CID)
        return res

    def commit_batch(account, system_id, abi, fn_name, args,
                     gas_per_item=None, use_owner=False,
                     return_receipt=False):
        state["commits"].append(
            {"system": system_id, "fn_name": fn_name, "args": args,
             "use_owner": use_owner}
        )
        res = {"tx_hash": "0xcommit", "status": "success", "block": 10,
               "gas_used": 1_000_000}
        if return_receipt:
            res["_receipt"] = _gacha_receipt(BIG_CID)
        return res

    def reveal(account, ids):
        state["reveals"].append(ids)
        if state["reveal_error"] is not None:
            raise state["reveal_error"]
        return dict(state["reveal_result"])

    monkeypatch.setattr(server, "_send_tx_owner", commit_owner)
    monkeypatch.setattr(server, "_send_batch_tx", commit_batch)
    monkeypatch.setattr(server, "_send_gacha_reveal_tx", reveal)
    monkeypatch.setattr(server.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        server, "w3", SimpleNamespace(eth=SimpleNamespace(block_number=99))
    )
    # owner-entity resolution for the fabricated account
    monkeypatch.setattr(server, "_require_registered_owner", lambda a: 0x7777)
    monkeypatch.setattr(server, "_account_entity_id", lambda a: 0x7777)
    return state


class TestLiquidateKami:
    def test_happy_maps_ids(self, accounts, validation_ok, sent, monkeypatch):
        monkeypatch.setattr(
            server, "_kami_state",
            lambda k: "HARVESTING",
        )
        r = server.liquidate_kami(500, 45, account="testa")
        assert r["status"] == "success"
        assert r["victim_kami_id"] == 500 and r["killer_kami_id"] == 45
        call = sent[0]
        assert call["system"] == "system.harvest.liquidate"
        assert call["args"] == [
            server._harvest_entity_id(500), server._kami_entity_id(45),
        ]
        assert call["gas_limit"] == 7_500_000

    def test_killer_must_be_harvesting(self, accounts, validation_ok, sent):
        # validation_ok reads every kami as RESTING
        with pytest.raises(server.PreTxValidationError) as ei:
            server.liquidate_kami(500, 45, account="testa")
        assert "requires HARVESTING" in str(ei.value)
        assert sent == []

    def test_killer_must_be_owned(self, accounts, validation_ok, sent,
                                  monkeypatch):
        monkeypatch.setattr(server, "_kami_state", lambda k: "HARVESTING")
        monkeypatch.setattr(server, "_kami_owner_id", lambda k: 0xDEAD)
        with pytest.raises(server.PreTxValidationError, match="not owned"):
            server.liquidate_kami(500, 45, account="testa")
        assert sent == []

    def test_victim_harvest_must_be_active(self, accounts, validation_ok,
                                           sent, monkeypatch):
        monkeypatch.setattr(server, "_kami_state", lambda k: "HARVESTING")
        monkeypatch.setattr(server, "_harvest_state", lambda k: "")
        with pytest.raises(server.PreTxValidationError) as ei:
            server.liquidate_kami(500, 45, account="testa")
        assert "no ACTIVE harvest" in str(ei.value)
        assert sent == []


class TestGachaUse:
    def test_happy_commit_and_reveal(self, gacha_flow):
        r = server.gacha_use(2, account="testa")
        assert r["commit"]["status"] == "success"
        assert r["reveal"]["status"] == "success"
        assert r["commit_ids"] == [str(BIG_CID)]
        assert r["amount"] == 2
        assert gacha_flow["commits"][0]["system"] == "system.kami.gacha.mint"
        assert gacha_flow["commits"][0]["args"] == [2]
        assert gacha_flow["reveals"] == [[BIG_CID]]

    def test_amount_bounds(self, accounts, validation_ok):
        for bad in (0, 6):
            with pytest.raises(server.PreTxValidationError, match="1-5"):
                server.gacha_use(bad, account="testa")

    def test_ticket_balance_gate(self, gacha_flow, monkeypatch):
        monkeypatch.setattr(server, "_inventory_balance", lambda h, i: 1)
        with pytest.raises(server.PreTxValidationError) as ei:
            server.gacha_use(3, account="testa")
        msg = str(ei.value)
        assert "gacha_use requires 3" in msg
        assert gacha_flow["commits"] == []

    def test_reveal_failure_raises_with_commit_ids(self, gacha_flow):
        gacha_flow["reveal_error"] = server.PreTxValidationError(
            "gacha reveal gas estimation reverted: revert: no seed"
        )
        with pytest.raises(server.BatchTxError) as ei:
            server.gacha_use(1, account="testa")
        msg = str(ei.value)
        assert "reveal failed after 3 attempts" in msg
        assert "gacha_reveal" in msg          # names the recovery path
        assert str(BIG_CID) in msg            # recovery input in error text
        assert "256 blocks" in msg
        assert len(gacha_flow["reveals"]) == 3
        assert ei.value.outcomes["commit"]["status"] == "success"

    def test_unconfirmed_reveal_not_retried(self, gacha_flow):
        gacha_flow["reveal_error"] = server.TxUnconfirmedError("0xfeed", 180)
        with pytest.raises(server.TxUnconfirmedError):
            server.gacha_use(1, account="testa")
        assert len(gacha_flow["reveals"]) == 1


class TestGachaReroll:
    def test_happy(self, gacha_flow):
        r = server.gacha_reroll([45, 46], account="testa")
        assert r["reveal"]["status"] == "success"
        assert r["kami_ids"] == [45, 46]
        commit = gacha_flow["commits"][0]
        assert commit["system"] == "system.kami.gacha.reroll"
        assert commit["fn_name"] == "reroll"
        assert commit["use_owner"] is True
        assert commit["args"] == [
            [server._kami_entity_id(45), server._kami_entity_id(46)]
        ]

    def test_requires_resting(self, gacha_flow, monkeypatch):
        monkeypatch.setattr(server, "_kami_state", lambda k: "HARVESTING")
        with pytest.raises(server.PreTxValidationError, match="RESTING"):
            server.gacha_reroll([45], account="testa")
        assert gacha_flow["commits"] == []

    def test_reroll_ticket_gate(self, gacha_flow, monkeypatch):
        monkeypatch.setattr(server, "_inventory_balance", lambda h, i: 0)
        with pytest.raises(server.PreTxValidationError) as ei:
            server.gacha_reroll([45], account="testa")
        assert "item 11" in str(ei.value)
        assert gacha_flow["commits"] == []

    def test_empty_raises(self, accounts, validation_ok):
        with pytest.raises(server.PreTxValidationError, match="is empty"):
            server.gacha_reroll([], account="testa")


class TestGachaReveal:
    def test_maps_to_reveal_fn(self, accounts, monkeypatch):
        calls = []

        def reveal(account, ids):
            calls.append(ids)
            return {"tx_hash": "0xrev", "status": "success", "block": 3,
                    "gas_used": 1}

        monkeypatch.setattr(server, "_send_gacha_reveal_tx", reveal)
        r = server.gacha_reveal([str(BIG_CID), "0x10"], account="testa")
        assert r["status"] == "success"
        assert r["commit_ids"] == [str(BIG_CID), "16"]
        assert calls == [[BIG_CID, 16]]

    def test_empty_raises(self, accounts):
        with pytest.raises(server.PreTxValidationError, match="is empty"):
            server.gacha_reveal([], account="testa")

    def test_preflight_uses_owner_and_names_window(self, accounts,
                                                   monkeypatch):
        est_calls = []

        class _Fns:
            def reveal(self, ids):
                def estimate(params):
                    est_calls.append((ids, params))
                    raise ValueError("execution reverted: same block")

                return SimpleNamespace(estimate_gas=estimate)

        monkeypatch.setattr(
            server, "w3",
            SimpleNamespace(
                eth=SimpleNamespace(
                    contract=lambda address=None, abi=None: SimpleNamespace(
                        functions=_Fns()
                    )
                )
            ),
        )
        monkeypatch.setattr(server, "_resolve_system", lambda sid: sid)
        with pytest.raises(server.PreTxValidationError) as ei:
            server.gacha_reveal(["9"], account="testa")
        msg = str(ei.value)
        assert "gacha reveal gas estimation reverted" in msg
        assert "256 blocks" in msg
        owner = server._get_account("testa").owner_addr
        assert est_calls[0][1] == {"from": owner}


class TestSkillRespec:
    def test_happy(self, accounts, validation_ok, sent):
        r = server.skill_respec(45, account="testa")
        assert r["status"] == "success"
        assert r["kami_id"] == 45
        assert "11403" in r["consumed"]
        call = sent[0]
        assert call["system"] == "system.skill.respec"
        assert call["args"] == [server._kami_entity_id(45)]

    def test_requires_potion(self, accounts, validation_ok, sent,
                             monkeypatch):
        monkeypatch.setattr(server, "_inventory_balance", lambda h, i: 0)
        with pytest.raises(server.PreTxValidationError) as ei:
            server.skill_respec(45, account="testa")
        assert "item 11403" in str(ei.value)
        assert sent == []

    def test_requires_ownership(self, accounts, validation_ok, sent,
                                monkeypatch):
        monkeypatch.setattr(server, "_kami_owner_id", lambda k: 0xDEAD)
        with pytest.raises(server.PreTxValidationError, match="not owned"):
            server.skill_respec(45, account="testa")
        assert sent == []


class TestCastItem:
    def test_happy_no_ownership_requirement(self, accounts, validation_ok,
                                            sent, monkeypatch):
        # Target owned by someone else — casting is still valid.
        monkeypatch.setattr(server, "_kami_owner_id", lambda k: 0xDEAD)
        r = server.cast_item(777, 11501, account="testa")
        assert r["status"] == "success"
        assert r["target_kami_id"] == 777 and r["stamina_cost"] == 10
        call = sent[0]
        assert call["system"] == "system.kami.cast.item"
        assert call["args"] == [server._kami_entity_id(777), 11501]

    def test_requires_item(self, accounts, validation_ok, sent, monkeypatch):
        monkeypatch.setattr(server, "_inventory_balance", lambda h, i: 0)
        with pytest.raises(server.PreTxValidationError, match="cast_item"):
            server.cast_item(777, 11501, account="testa")
        assert sent == []

    def test_requires_stamina(self, accounts, validation_ok, sent,
                              monkeypatch):
        monkeypatch.setattr(
            server, "_account_view",
            lambda aid: {"index": 1, "name": "t", "stamina": 4, "room": 1},
        )
        with pytest.raises(server.PreTxValidationError) as ei:
            server.cast_item(777, 11501, account="testa")
        assert "stamina is 4" in str(ei.value) and "requires 10" in str(ei.value)
        assert sent == []


class TestNewbieVendorBuy:
    def _vendor(self, monkeypatch, price_wei, balance=10**18):
        from conftest import FakeContract
        from types import SimpleNamespace as NS
        vendor = FakeContract({"calcPrice": lambda: price_wei})
        eth = NS(
            contract=lambda address=None, abi=None: vendor,
            get_balance=lambda a: balance,
        )
        monkeypatch.setattr(
            server, "w3",
            NS(eth=eth, from_wei=server.Web3.from_wei,
               to_wei=server.Web3.to_wei),
        )
        monkeypatch.setattr(server, "_resolve_system", lambda sid: sid)
        monkeypatch.setattr(
            server, "_require_registered_owner", lambda a: 0x7777
        )

    def test_happy_sends_exact_price(self, accounts, monkeypatch):
        self._vendor(monkeypatch, price_wei=6 * 10**15)  # 0.006 ETH
        calls = []

        def owner_send(account, system_id, abi, args, gas_limit=None,
                       value_wei=0, return_receipt=False):
            calls.append({"system": system_id, "args": args,
                          "value_wei": value_wei})
            return {"tx_hash": "0xbuy", "status": "success", "block": 5,
                    "gas_used": 1, "account": account}

        monkeypatch.setattr(server, "_send_tx_owner", owner_send)
        r = server.newbie_vendor_buy(1234, "0.01", account="testa")
        assert r["status"] == "success"
        assert r["price_eth"] == "0.006"
        assert calls[0]["system"] == "system.newbievendor.buy"
        assert calls[0]["args"] == [1234]
        assert calls[0]["value_wei"] == 6 * 10**15

    def test_price_above_cap_aborts(self, accounts, monkeypatch, sent):
        self._vendor(monkeypatch, price_wei=2 * 10**16)  # 0.02 ETH
        with pytest.raises(server.PreTxValidationError) as ei:
            server.newbie_vendor_buy(1234, "0.01", account="testa")
        assert "above max_price_eth 0.01" in str(ei.value)
        assert sent == []

    def test_balance_gate(self, accounts, monkeypatch, sent):
        self._vendor(monkeypatch, price_wei=6 * 10**15, balance=10**15)
        with pytest.raises(server.PreTxValidationError) as ei:
            server.newbie_vendor_buy(1234, "0.01", account="testa")
        assert "gas provision" in str(ei.value)
        assert sent == []

    def test_zero_cap_rejected(self, accounts, monkeypatch):
        self._vendor(monkeypatch, price_wei=1)
        with pytest.raises(ValueError, match="> 0"):
            server.newbie_vendor_buy(1234, "0", account="testa")


class TestChatSend:
    def test_disabled_by_default(self, accounts, validation_ok, sent,
                                 monkeypatch):
        monkeypatch.setattr(server, "CHAT_ENABLED", False)
        with pytest.raises(server.LensQueryError, match="CHAT_DISABLED"):
            server.chat_send("hello", account="testa")
        assert sent == []

    def test_enabled_sends_to_chat_system(self, accounts, validation_ok,
                                          sent, monkeypatch):
        monkeypatch.setattr(server, "CHAT_ENABLED", True)
        r = server.chat_send("gm room", account="testa")
        assert r["status"] == "success"
        assert r["message_bytes"] == 7
        assert sent[0]["system"] == "system.chat"
        assert sent[0]["args"] == ["gm room"]

    def test_empty_message_guard(self, accounts, validation_ok, sent,
                                 monkeypatch):
        monkeypatch.setattr(server, "CHAT_ENABLED", True)
        with pytest.raises(server.PreTxValidationError, match="empty"):
            server.chat_send("", account="testa")
        assert sent == []

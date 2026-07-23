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

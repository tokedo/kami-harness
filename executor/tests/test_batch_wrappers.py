"""Offline tests for the batch-wrapper tools and Kamibots status read.

Covers feed_level_allocate_batch, equip_all_batch, unequip_all_batch,
speed_craft_batch, get_all_strategy_statuses, and the
get_kamis_progress_batch field additions. No network, keys, or chain
access.
"""

import asyncio

import pytest

from conftest import FakeContract

import server


class TestFeedLevelAllocateBatch:
    def test_happy_all_phases(self, accounts, validation_ok, sent, monkeypatch):
        async def fake_api(path, account):
            return {"progress": {"level": 3}}

        monkeypatch.setattr(server, "_api_get", fake_api)
        r = asyncio.run(
            server.feed_level_allocate_batch(
                [
                    {
                        "kami_id": 5,
                        "feed_item_id": 11,
                        "feed_count": 2,
                        "target_level": 5,
                        "skill_plan": [{"skill_index": 10, "points": 2}],
                    }
                ],
                account="testa",
            )
        )
        assert r["ok"] == 1 and r["count"] == 1
        row = r["results"][0]
        assert row["fed"] == {"done": 2, "planned": 2}
        assert row["leveled"] == {"from": 3, "to": 5, "target": 5}
        assert row["allocated"] == {"done": 2, "planned": 2}
        # 2 feeds + 2 levels + 2 skill points = 6 txs
        assert len(sent) == 6
        systems = [c["system"] for c in sent]
        assert systems == (
            ["system.kami.use.item"] * 2
            + ["system.kami.level"] * 2
            + ["system.skill.upgrade"] * 2
        )

    def test_feed_failure_skips_later_phases(
        self, accounts, validation_ok, sent, monkeypatch
    ):
        def failing_send(account, system_id, abi, args, **kw):
            raise Exception("insufficient balance")

        monkeypatch.setattr(server, "_send_tx_retry", failing_send)

        async def fake_api(path, account):  # must never be reached
            raise AssertionError("level phase ran after feed failure")

        monkeypatch.setattr(server, "_api_get", fake_api)
        r = asyncio.run(
            server.feed_level_allocate_batch(
                [
                    {
                        "kami_id": 5,
                        "feed_item_id": 11,
                        "feed_count": 1,
                        "target_level": 9,
                    }
                ],
                account="testa",
                allow_partial=True,
            )
        )
        assert r["ok"] == 0
        row = r["results"][0]
        assert row["error"].startswith("feed:")
        assert "leveled" not in row

    def test_failure_raises_by_default_with_outcomes(
        self, accounts, validation_ok, sent, monkeypatch
    ):
        def failing_send(account, system_id, abi, args, **kw):
            raise Exception("insufficient balance")

        monkeypatch.setattr(server, "_send_tx_retry", failing_send)
        with pytest.raises(server.BatchTxError) as ei:
            asyncio.run(
                server.feed_level_allocate_batch(
                    [{"kami_id": 5, "feed_item_id": 11, "feed_count": 1}],
                    account="testa",
                )
            )
        msg = str(ei.value)
        assert "1 of 1 per-kami plans failed" in msg
        assert "feed: insufficient balance" in msg  # per-item outcome

    def test_missing_kami_id(self, accounts, validation_ok, sent):
        r = asyncio.run(
            server.feed_level_allocate_batch(
                [{"feed_item_id": 11, "feed_count": 1}],
                account="testa",
                allow_partial=True,
            )
        )
        assert r["ok"] == 0
        assert r["results"][0]["error"] == "target missing kami_id"
        assert sent == []


class TestEquipAllBatch:
    def test_dry_run_gates(self, accounts, chain, sent):
        def gate(eid, item_index):
            if item_index == 200:
                raise Exception("execution reverted: slot full")
            return b""

        chain["system.kami.equip"] = FakeContract({"executeTyped": gate})
        r = server.equip_all_batch(
            [
                {"kami_id": 1, "item_index": 100},
                {"kami_id": 2, "item_index": 200},
                {"kami_id": 1, "item_index": 100},  # duplicate kami de-duped
            ],
            account="testa",
            delay_seconds=0,
        )
        assert r["requested"] == 2
        assert r["equipped"] == 1 and r["skipped"] == 1 and r["errors"] == 0
        assert len(sent) == 1 and sent[0]["system"] == "system.kami.equip"

    def test_empty_raises(self, accounts, chain):
        with pytest.raises(ValueError, match="is empty"):
            server.equip_all_batch([], account="testa")

    def test_bad_entry_raises(self, accounts, chain, sent):
        chain["system.kami.equip"] = FakeContract(
            {"executeTyped": lambda *a: b""}
        )
        with pytest.raises(ValueError, match="bad equips entry"):
            server.equip_all_batch(
                [{"kami_id": 1}], account="testa", delay_seconds=0
            )
        assert sent == []


class TestUnequipAllBatch:
    def test_skips_empty_slots(self, accounts, chain, sent):
        eid_2 = server._kami_entity_id(2)

        def gate(eid, slot):
            if eid == eid_2:
                raise Exception("execution reverted: slot empty")
            return b""

        chain["system.kami.unequip"] = FakeContract({"executeTyped": gate})
        r = server.unequip_all_batch([1, 2], account="testa", delay_seconds=0)
        assert r["requested"] == 2
        assert r["unequipped"] == 1 and r["skipped_empty"] == 1
        statuses = {row["kami_id"]: row["status"] for row in r["results"]}
        assert statuses[2] == "skipped_empty"
        assert len(sent) == 1

    def test_empty_raises(self, accounts, chain):
        with pytest.raises(ValueError, match="is empty"):
            server.unequip_all_batch([], account="testa")


class TestSpeedCraftBatch:
    def test_happy(self, accounts, validation_ok, sent):
        r = server.speed_craft_batch(29, 2, account="testa")
        assert r["success"] is True
        assert r["crafted"] == 2 and r["stamina_used"] == 2
        systems = [c["system"] for c in sent]
        assert systems == [
            "system.account.use.item", "system.craft",
            "system.account.use.item", "system.craft",
        ]

    def test_stops_on_craft_revert(self, accounts, validation_ok, monkeypatch):
        # A craft that lands and reverts raises from the sender; the
        # loop halts and the default (allow_partial=False) raises with
        # the completed cycles in the error text.
        calls = []

        def send(account, system_id, abi, args, **kw):
            calls.append(system_id)
            if system_id == "system.craft":
                raise server.OnChainRevertError("0xdead", 1, 100_000, "revert: stamina")
            return {"tx_hash": "0x1", "status": "success", "block": 1,
                    "gas_used": 1, "account": account}

        monkeypatch.setattr(server, "_send_tx_retry", send)
        with pytest.raises(server.BatchTxError) as ei:
            server.speed_craft_batch(29, 3, account="testa")
        msg = str(ei.value)
        assert "halted after 0/3" in msg
        assert "0xdead" in msg
        assert calls == ["system.account.use.item", "system.craft"]

    def test_craft_revert_allow_partial_returns(
        self, accounts, validation_ok, monkeypatch
    ):
        calls = []

        def send(account, system_id, abi, args, **kw):
            calls.append(system_id)
            if system_id == "system.craft":
                raise server.OnChainRevertError("0xdead", 1, 100_000, "revert: stamina")
            return {"tx_hash": "0x1", "status": "success", "block": 1,
                    "gas_used": 1, "account": account}

        monkeypatch.setattr(server, "_send_tx_retry", send)
        r = server.speed_craft_batch(29, 3, account="testa", allow_partial=True)
        assert r["success"] is False
        assert r["crafted"] == 0 and r["stamina_used"] == 1
        assert "craft failed at cycle 1/3" in r["last_error"]
        assert calls == ["system.account.use.item", "system.craft"]

    def test_zero_count_raises(self, accounts):
        with pytest.raises(ValueError, match="at least 1"):
            server.speed_craft_batch(29, 0, account="testa")


class TestGetAllStrategyStatuses:
    def test_happy_path_endpoint(self, accounts, monkeypatch):
        seen = {}

        async def fake_api(path, account):
            seen["path"] = path
            seen["account"] = account
            return {"strategies": []}

        monkeypatch.setattr(server, "_api_get", fake_api)
        r = asyncio.run(server.get_all_strategy_statuses(account="testa"))
        assert seen["path"] == "/api/strategies/status/all"
        assert r == {"strategies": []}

    def test_unregistered_account_raises(self, accounts):
        # Fabricated accounts have no Kamibots API key; the real _api_get
        # must raise before any network access.
        with pytest.raises(ValueError, match="No Kamibots API key"):
            asyncio.run(server.get_all_strategy_statuses(account="testa"))


class TestGetKamisProgressBatchFields:
    def test_harvest_and_hp_fields(self, accounts, monkeypatch):
        async def fake_api(path, account):
            return {
                "name": "Kami5",
                "state": "HARVESTING",
                "progress": {"level": 2, "experience": 10},
                "skills": {"points": 1, "investments": [{"index": 3, "points": 2}]},
                "stats": {
                    "health": {"base": 10, "total": 12, "sync": 8, "rate": -0.5},
                    "harmony": {"base": 4}, "violence": {"base": 5},
                    "power": {"base": 6}, "slots": {"base": 1, "total": 1},
                },
                "traits": {
                    "body": {"name": "B", "affinity": "EERIE"},
                    "hand": {"name": "H", "affinity": "SCRAP"},
                },
                "harvest": {"state": "ACTIVE", "balance": 55},
            }

        monkeypatch.setattr(server, "_api_get", fake_api)
        r = asyncio.run(server.get_kamis_progress_batch([5], account="testa"))
        k = r["kamis"][0]
        assert k["hp_sync"] == 8 and k["hp_rate"] == -0.5
        assert k["harvest_state"] == "ACTIVE" and k["harvest_balance"] == 55
        assert k["level"] == 2 and k["investments"] == [{"index": 3, "points": 2}]

    def test_per_kami_error_capture(self, accounts, monkeypatch):
        async def fake_api(path, account):
            raise RuntimeError("api down")

        monkeypatch.setattr(server, "_api_get", fake_api)
        r = asyncio.run(server.get_kamis_progress_batch([5], account="testa"))
        assert r["kamis"][0] == {"index": 5, "error": "api down"}

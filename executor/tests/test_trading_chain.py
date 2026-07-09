"""Offline tests for chain-state trading reads.

Covers the get_account_trades chain-truth rewrite, get_item_orderbook
(including the bootstrap-cache and staleness guards), and the
list_open_sell_offers coverage note. No network, keys, or chain access.
"""

import json

import pytest
from web3 import Web3

from conftest import FakeContract

import server


def _anchor(kind: str, tid: int) -> int:
    return int.from_bytes(
        Web3.solidity_keccak(["string", "uint256"], [f"trade.{kind}", tid]), "big"
    )


class TestGetAccountTrades:
    def test_pending_and_executed(self, accounts, chain, monkeypatch):
        monkeypatch.setattr(server, "_get_item_name", lambda i: f"Item{i}")
        acc_eid = server._account_entity_id("testa")
        t_sell, t_buy = 1001, 1002

        keys = {
            _anchor("buy", t_sell): [1], _anchor("sell", t_sell): [5],
            _anchor("buy", t_buy): [7], _anchor("sell", t_buy): [1],
        }
        vals = {
            _anchor("buy", t_sell): [500], _anchor("sell", t_sell): [2],
            _anchor("buy", t_buy): [3], _anchor("sell", t_buy): [900],
        }
        chain["component.id.trade.owns"] = FakeContract(
            {"getEntitiesWithValue": lambda v: [t_buy, t_sell] if v == acc_eid else []}
        )
        chain["component.state"] = FakeContract(
            {"safeGet": lambda ents: ["PENDING" if e == t_sell else "EXECUTED" for e in ents]}
        )
        chain["component.keys"] = FakeContract(
            {"safeGet": lambda ents: [keys[e] for e in ents]}
        )
        chain["component.values"] = FakeContract(
            {"safeGet": lambda ents: [vals[e] for e in ents]}
        )

        r = server.get_account_trades(account="testa")
        assert r["total_open"] == 2
        assert r["pending"] == 1 and r["executed"] == 1
        sell = next(t for t in r["trades"] if t["side"] == "SELL")
        buy = next(t for t in r["trades"] if t["side"] == "BUY")
        assert sell["status"] == "PENDING" and sell["action"] == "cancel_trade"
        assert sell["item_index"] == 5 and sell["item_amount"] == 2
        assert sell["musu_amount"] == 500 and sell["unit_price"] == 250
        assert buy["status"] == "EXECUTED" and buy["action"] == "complete_trade"
        assert buy["item_index"] == 7 and buy["unit_price"] == 300
        assert r["executed_trades"][0]["trade_id_hex"] == hex(t_buy)

    def test_no_trades(self, accounts, chain):
        acc_eid = server._account_entity_id("testa")
        chain["component.id.trade.owns"] = FakeContract(
            {"getEntitiesWithValue": lambda v: [] if v == acc_eid else [1]}
        )
        r = server.get_account_trades(account="testa")
        assert r["total_open"] == 0 and r["trades"] == []

    def test_unknown_account_raises(self, accounts, chain):
        with pytest.raises(ValueError, match="not found"):
            server.get_account_trades(account="nope")


class TestScanTradeEntityIds:
    def _reset_cache(self, monkeypatch, tmp_path, filename="kwob_trades.json"):
        monkeypatch.setattr(
            server, "_KWOB_CACHE_FILE", tmp_path / ".cache" / filename
        )
        monkeypatch.setattr(
            server,
            "_trade_scan_cache",
            {"next_block": 0, "ids": set(), "loaded": False},
        )

    def test_missing_bootstrap_raises(self, chain, monkeypatch, tmp_path):
        self._reset_cache(monkeypatch, tmp_path)
        with pytest.raises(RuntimeError, match="kwob_bootstrap.py"):
            server._scan_trade_entity_ids()

    def test_stale_cache_raises(self, chain, monkeypatch, tmp_path):
        self._reset_cache(monkeypatch, tmp_path)
        cache_file = server._KWOB_CACHE_FILE
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text(
            json.dumps({"block": 100, "trade_ids": [hex(7)]})
        )
        server.w3.eth.block_number = 5_000_000  # far past the prune window
        with pytest.raises(RuntimeError, match="stale"):
            server._scan_trade_entity_ids()

    def test_bootstrap_union_with_log_scan(self, chain, monkeypatch, tmp_path):
        self._reset_cache(monkeypatch, tmp_path)
        cache_file = server._KWOB_CACHE_FILE
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text(
            json.dumps({"block": 500, "trade_ids": [hex(7)]})
        )
        server.w3.eth.block_number = 1_000
        server.w3.eth.get_logs = lambda params: [
            {"topics": [b"", b"", b"", (9).to_bytes(32, "big")]}
        ]
        ids = server._scan_trade_entity_ids()
        assert ids == {7, 9}
        persisted = json.loads(cache_file.read_text())
        assert persisted["block"] == 1_000
        assert set(persisted["trade_ids"]) == {hex(7), hex(9)}


class TestGetItemOrderbook:
    def test_musu_rejected(self, accounts, chain):
        with pytest.raises(ValueError, match="quote currency"):
            server.get_item_orderbook(1)

    def test_missing_bootstrap_raises_from_tool(
        self, accounts, chain, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(
            server, "_KWOB_CACHE_FILE", tmp_path / ".cache" / "kwob_trades.json"
        )
        monkeypatch.setattr(
            server,
            "_trade_scan_cache",
            {"next_block": 0, "ids": set(), "loaded": False},
        )
        with pytest.raises(RuntimeError, match="kwob_bootstrap.py"):
            server.get_item_orderbook(42)

    def test_asks_bids_and_own_tag(self, accounts, chain, monkeypatch):
        monkeypatch.setattr(server, "_get_item_name", lambda i: f"Item{i}")
        t_ask, t_bid, t_other = 2001, 2002, 2003
        all_ids = [t_ask, t_bid, t_other]
        monkeypatch.setattr(
            server, "_scan_trade_entity_ids", lambda: set(all_ids)
        )
        own_eid = int(server._accounts["testa"].owner_addr, 16)
        makers = {t_ask: 777, t_bid: own_eid, t_other: 888}

        keys = {
            _anchor("buy", t_ask): [1], _anchor("sell", t_ask): [42],
            _anchor("buy", t_bid): [42], _anchor("sell", t_bid): [1],
            _anchor("buy", t_other): [1], _anchor("sell", t_other): [9],
        }
        vals = {
            _anchor("buy", t_ask): [1000], _anchor("sell", t_ask): [10],
            _anchor("buy", t_bid): [4], _anchor("sell", t_bid): [200],
            _anchor("buy", t_other): [50], _anchor("sell", t_other): [1],
        }
        chain["component.id.trade.owns"] = FakeContract(
            {"getRaw": lambda ents: [makers[e].to_bytes(32, "big") for e in ents]}
        )
        chain["component.state"] = FakeContract(
            {"safeGet": lambda ents: ["PENDING" for _ in ents]}
        )
        chain["component.keys"] = FakeContract(
            {"safeGet": lambda ents: [keys[e] for e in ents]}
        )
        chain["component.values"] = FakeContract(
            {"safeGet": lambda ents: [vals[e] for e in ents]}
        )
        chain["component.id.target"] = FakeContract(
            {"safeGet": lambda ents: [0 for _ in ents]}
        )

        r = server.get_item_orderbook(42)
        assert r["open_trades_all_items"] == 3
        assert r["skipped"] == {"executed": 0, "targeted": 0, "other_item": 1}
        assert len(r["asks"]) == 1 and len(r["bids"]) == 1
        assert r["best_ask"] == 100.0 and r["best_bid"] == 50.0
        assert r["asks"][0]["trade_id"] == hex(t_ask)
        assert "own" not in r["asks"][0]
        assert r["bids"][0]["own"] == "testa"

        buy_only = server.get_item_orderbook(42, side="buy")
        assert "asks" in buy_only and "bids" not in buy_only


class TestListOpenSellOffersNote:
    def test_note_points_to_orderbook(self, accounts, monkeypatch):
        monkeypatch.setattr(server, "_kamiden_grpc_call", lambda m, b=b"": b"")
        r = server.list_open_sell_offers(seed_account="testa")
        assert r["offers"] == []
        assert "get_item_orderbook" in r["note"]

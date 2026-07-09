"""Offline tests for the KamiSwap marketplace tools.

Covers get_kami_market_listings, buy_kami, cancel_kami_listing, and the
list_kami wei-precision fix. Indexer payloads are hand-encoded protobuf;
no network, keys, or chain access.
"""

import time

import pytest

from conftest import field_bytes, field_str, field_varint

import server


def listing_msg(
    order_id: str,
    seller: str,
    kami_index: int,
    price_wei: int,
    expiry: int,
    ts: int,
    buyer: str = "",
) -> bytes:
    inner = (
        field_str(1, order_id)
        + field_str(2, seller)
        + field_varint(3, kami_index)
        + field_str(4, str(price_wei))
        + field_str(5, str(expiry))
        + field_varint(6, ts)
        + field_str(7, buyer)
    )
    return field_bytes(1, inner)


def install_listings(monkeypatch, messages: list[bytes]):
    payload = b"".join(messages)
    monkeypatch.setattr(server, "_kamiden_grpc_call", lambda m, b=b"": payload)


class TestGetKamiMarketListings:
    def test_filters_and_sorts(self, monkeypatch):
        future = int(time.time()) + 10_000
        past = int(time.time()) - 10_000
        install_listings(
            monkeypatch,
            [
                listing_msg("10", "111", 5, 3 * 10**18, future, 50),
                listing_msg("11", "222", 6, 1 * 10**18, future, 60),
                listing_msg("12", "333", 7, 2 * 10**18, past, 70),  # expired
                listing_msg("13", "444", 8, 9 * 10**18, future, 80, buyer="55"),  # sold
            ],
        )
        r = server.get_kami_market_listings()
        assert r["count"] == 2  # expired + sold dropped
        assert [l["kami_index"] for l in r["listings"]] == [6, 5]  # cheapest first
        assert r["listings"][0]["order_id_hex"] == hex(11)
        assert r["listings"][0]["price_eth"] == 1.0

    def test_price_cap_and_expired_included(self, monkeypatch):
        past = int(time.time()) - 10_000
        install_listings(
            monkeypatch,
            [
                listing_msg("10", "111", 5, 3 * 10**18, past, 50),
                listing_msg("11", "222", 6, 1 * 10**18, past, 60),
            ],
        )
        r = server.get_kami_market_listings(
            include_expired=True, max_price_eth="1.5"
        )
        assert r["count"] == 1
        assert r["listings"][0]["kami_index"] == 6

    def test_empty_payload(self, monkeypatch):
        monkeypatch.setattr(server, "_kamiden_grpc_call", lambda m, b=b"": b"")
        r = server.get_kami_market_listings()
        assert r == {"count": 0, "listings": []}


class TestBuyKami:
    def _market(self, monkeypatch, listings):
        monkeypatch.setattr(
            server,
            "get_kami_market_listings",
            lambda **kw: {"count": len(listings), "listings": listings},
        )

    def test_happy_batch(self, accounts, monkeypatch, sent):
        self._market(
            monkeypatch,
            [
                {"kami_index": 5, "price_eth": 1.0, "price_wei": 10**18,
                 "order_id_hex": hex(11), "seller_account_id": "999",
                 "expiry": 0, "created_at": 60},
                {"kami_index": 7, "price_eth": 0.5, "price_wei": 5 * 10**17,
                 "order_id_hex": hex(12), "seller_account_id": "999",
                 "expiry": 0, "created_at": 70},
            ],
        )
        r = server.buy_kami([5, 7], "2.0", account="testa")
        assert r["status"] == "success"
        assert r["total_eth"] == 1.5
        assert [k["kami_index"] for k in r["kamis_bought"]] == [5, 7]
        assert sent[0]["args"] == [[11, 12]]
        assert sent[0]["value_wei"] == 15 * 10**17

    def test_no_listing_raises(self, accounts, monkeypatch, sent):
        self._market(monkeypatch, [])
        with pytest.raises(ValueError, match="No active KamiSwap listing"):
            server.buy_kami([5], "1.0", account="testa")
        assert sent == []

    def test_cap_exceeded_raises(self, accounts, monkeypatch, sent):
        self._market(
            monkeypatch,
            [{"kami_index": 5, "price_eth": 2.0, "price_wei": 2 * 10**18,
              "order_id_hex": hex(11), "seller_account_id": "999",
              "expiry": 0, "created_at": 60}],
        )
        with pytest.raises(ValueError, match="exceeds max_total_eth"):
            server.buy_kami([5], "1.0", account="testa")
        assert sent == []

    def test_own_listing_raises(self, accounts, monkeypatch, sent):
        self_eid = str(server._account_entity_id("testa"))
        self._market(
            monkeypatch,
            [{"kami_index": 5, "price_eth": 1.0, "price_wei": 10**18,
              "order_id_hex": hex(11), "seller_account_id": self_eid,
              "expiry": 0, "created_at": 60}],
        )
        with pytest.raises(ValueError, match="your own listing"):
            server.buy_kami([5], "2.0", account="testa")

    def test_empty_ids_raises(self, accounts):
        with pytest.raises(ValueError, match="must not be empty"):
            server.buy_kami([], "1.0", account="testa")


class TestCancelKamiListing:
    def test_happy(self, accounts, monkeypatch, sent):
        self_eid = str(server._account_entity_id("testa"))
        monkeypatch.setattr(
            server,
            "get_kami_market_listings",
            lambda **kw: {
                "count": 2,
                "listings": [
                    {"kami_index": 5, "price_eth": 1.0, "price_wei": 10**18,
                     "order_id_hex": hex(11), "seller_account_id": self_eid,
                     "expiry": 0, "created_at": 60},
                    {"kami_index": 6, "price_eth": 1.0, "price_wei": 10**18,
                     "order_id_hex": hex(12), "seller_account_id": "999",
                     "expiry": 0, "created_at": 60},  # someone else's
                ],
            },
        )
        r = server.cancel_kami_listing([5], account="testa")
        assert r["cancelled"] == 1 and r["failed"] == 0
        assert r["results"][0]["listing_id"] == hex(11)
        assert sent[0]["args"] == [11]

    def test_not_own_listing_raises(self, accounts, monkeypatch, sent):
        monkeypatch.setattr(
            server,
            "get_kami_market_listings",
            lambda **kw: {
                "count": 1,
                "listings": [
                    {"kami_index": 5, "price_eth": 1.0, "price_wei": 10**18,
                     "order_id_hex": hex(11), "seller_account_id": "999",
                     "expiry": 0, "created_at": 60},
                ],
            },
        )
        with pytest.raises(ValueError, match="No listing by account"):
            server.cancel_kami_listing([5], account="testa")
        assert sent == []

    def test_empty_ids_raises(self, accounts):
        with pytest.raises(ValueError, match="must not be empty"):
            server.cancel_kami_listing([], account="testa")


class TestListKamiWeiPrecision:
    def test_exact_decimal_conversion(self, accounts, sent):
        # 0.1 ETH is not exactly representable as a float; the Decimal
        # path must produce exactly 10**17 wei.
        r = server.list_kami(45, "0.1", account="testa")
        assert r["status"] == "success"
        assert sent[0]["args"][1] == 10**17
        assert server._eth_to_wei("0.000000000000000001") == 1

    def test_zero_price_raises(self, accounts, sent):
        with pytest.raises(ValueError, match="> 0"):
            server.list_kami(45, "0", account="testa")
        assert sent == []

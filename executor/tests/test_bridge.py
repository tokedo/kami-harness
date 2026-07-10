"""Offline tests for bridge_eth_from_mainnet / bridge_status.

The Initia router is faked at the _router_post/httpx level and mainnet
access via a fake Web3 namespace; nothing here touches the network,
signs with real funds, or needs keys. The M2 startup requirement is
exercised in a keyless subprocess.
"""

import inspect
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from web3 import Web3

from conftest import KEY_A

import server

ETH = 10**18
AMOUNT_WEI = 10**16                 # 0.01 ETH
FEE_WEI = 11 * 10**12               # 0.000011 ETH LayerZero fee
VALUE_WEI = AMOUNT_WEI + FEE_WEI
GAS = 260_000                       # 200k estimate * 1.3
MAX_FEE = 2 * 10 * 10**9 + 10**9    # 2*base(10 gwei) + tip(1 gwei)
MAX_GAS_COST = GAS * MAX_FEE

ROUTE_RESP = {
    "txs_required": 1,
    "amount_out": str(AMOUNT_WEI),
    "operations": [{"layer_zero_transfer": {}, "tx_index": 0}],
    "required_chain_addresses": ["1", "interwoven-1", "yominet-1"],
    "estimated_route_duration_seconds": 300,
}
EVM_TX = {
    "to": "0x66a503a1060ab3f2b1aaabed613fe30babbc1bde",
    "value": str(VALUE_WEI),
    "data": "abcdef",
    "required_erc20_approvals": [],
}
MSGS_RESP = {"txs": [{"evm_tx": EVM_TX}]}


@pytest.fixture()
def bridge_env(monkeypatch, accounts):
    """Fake router, fake mainnet w3, and a Yominet balance ledger."""
    env = SimpleNamespace(
        posts=[], signed=[], raw_sent=[],
        responses={"/v2/fungible/route": ROUTE_RESP,
                   "/v2/fungible/msgs": MSGS_RESP},
        track_error=False,
        mainnet_balances={},
        yominet_balances={},
        accounts=accounts,
    )

    def fake_router_post(path, body):
        env.posts.append((path, body))
        if path == "/v2/tx/track":
            if env.track_error:
                raise ValueError("Router API /v2/tx/track -> 500: boom")
            return {}
        resp = env.responses[path]
        if isinstance(resp, Exception):
            raise resp
        return resp

    monkeypatch.setattr(server, "_router_post", fake_router_post)

    fake_w3 = SimpleNamespace(
        eth=SimpleNamespace(
            get_balance=lambda a: env.yominet_balances.get(a, 0)),
        from_wei=Web3.from_wei,
        to_wei=Web3.to_wei,
    )
    monkeypatch.setattr(server, "w3", fake_w3)

    def fake_sign(tx, private_key):
        env.signed.append({"tx": dict(tx), "key": private_key})
        return SimpleNamespace(raw_transaction=b"\x01\x02")

    def fake_send_raw(raw):
        env.raw_sent.append(raw)
        return SimpleNamespace(hex=lambda: "ab" * 32)

    def forbid_wait(*a, **kw):
        raise AssertionError(
            "M1: wait_for_transaction_receipt must not be called — the "
            "tool returns right after broadcast; bridge_status polls."
        )

    w3m = SimpleNamespace(eth=SimpleNamespace(
        estimate_gas=lambda tx: 200_000,
        get_block=lambda tag: {"baseFeePerGas": 10 * 10**9},
        max_priority_fee=10**9,
        get_balance=lambda addr: env.mainnet_balances.get(addr, 0),
        get_transaction_count=lambda addr: 7,
        account=SimpleNamespace(sign_transaction=fake_sign),
        send_raw_transaction=fake_send_raw,
        wait_for_transaction_receipt=forbid_wait,
    ))
    monkeypatch.setattr(server, "_w3_mainnet", lambda: w3m)
    return env


class TestBech32:
    def test_known_vector(self):
        # Live-verified: accepted by the Initia router for a real
        # widget-equivalent bridge tx.
        assert (server._init_addr("0xae190Eb02b793A17cE6f649A26F71D38a32f9dEd")
                == "init14cvsavpt0yap0nn0vjdzdaca8z3jl80dqf6syl")

    def test_case_insensitive_input(self):
        mixed = "0xae190Eb02b793A17cE6f649A26F71D38a32f9dEd"
        assert server._init_addr(mixed.lower()) == server._init_addr(mixed)


class TestAmountValidation:
    def test_rejects_more_than_6_decimals(self, bridge_env):
        with pytest.raises(ValueError) as ei:
            server.bridge_eth_from_mainnet(
                "0.0000001", account="testa", dry_run=True)
        msg = str(ei.value)
        assert "0.0000001" in msg
        assert "6 decimal" in msg

    def test_no_owner_key(self, bridge_env):
        with pytest.raises(ValueError, match="no owner key"):
            server.bridge_eth_from_mainnet(
                "0.01", account="noown", dry_run=True)


class TestQuoteParsing:
    def test_route_request_shape(self, bridge_env):
        owner = bridge_env.accounts["testa"].owner_addr
        server._bridge_quote(owner, AMOUNT_WEI)
        path, body = bridge_env.posts[0]
        assert path == "/v2/fungible/route"
        # justify-or-drop outcome: layer_zero only, no allow_unsafe, no
        # multi-tx routes
        assert body["experimental_features"] == ["layer_zero"]
        assert "allow_unsafe" not in body
        assert body["allow_multi_tx"] is False
        assert body["amount_in"] == str(AMOUNT_WEI)

    def test_msgs_address_list_maps_chains(self, bridge_env):
        owner = bridge_env.accounts["testa"].owner_addr
        server._bridge_quote(owner, AMOUNT_WEI)
        _, msgs_body = bridge_env.posts[1]
        init = server._init_addr(owner)
        assert msgs_body["address_list"] == [owner, init, init]

    def test_txs_shape_parsed(self, bridge_env):
        owner = bridge_env.accounts["testa"].owner_addr
        q = server._bridge_quote(owner, AMOUNT_WEI)
        assert q["evm_tx"] == EVM_TX
        assert q["route"] == ROUTE_RESP

    def test_msgs_shape_parsed(self, bridge_env):
        bridge_env.responses["/v2/fungible/msgs"] = {
            "msgs": [{"evm_tx": EVM_TX}]}
        owner = bridge_env.accounts["testa"].owner_addr
        q = server._bridge_quote(owner, AMOUNT_WEI)
        assert q["evm_tx"] == EVM_TX

    def test_multi_tx_route_rejected(self, bridge_env):
        bridge_env.responses["/v2/fungible/route"] = {
            **ROUTE_RESP, "txs_required": 2}
        owner = bridge_env.accounts["testa"].owner_addr
        with pytest.raises(ValueError, match="txs_required=2"):
            server._bridge_quote(owner, AMOUNT_WEI)

    def test_missing_evm_tx_rejected(self, bridge_env):
        bridge_env.responses["/v2/fungible/msgs"] = {
            "txs": [{"cosmos_tx": {}}]}
        owner = bridge_env.accounts["testa"].owner_addr
        with pytest.raises(ValueError, match="got 0"):
            server._bridge_quote(owner, AMOUNT_WEI)

    def test_two_evm_txs_rejected(self, bridge_env):
        bridge_env.responses["/v2/fungible/msgs"] = {
            "txs": [{"evm_tx": EVM_TX}, {"evm_tx": EVM_TX}]}
        owner = bridge_env.accounts["testa"].owner_addr
        with pytest.raises(ValueError, match="got 2"):
            server._bridge_quote(owner, AMOUNT_WEI)

    def test_erc20_approvals_rejected(self, bridge_env):
        bridge_env.responses["/v2/fungible/msgs"] = {"txs": [{"evm_tx": {
            **EVM_TX, "required_erc20_approvals": [{"token": "0xdead"}],
        }}]}
        owner = bridge_env.accounts["testa"].owner_addr
        with pytest.raises(ValueError, match="ERC20 approvals"):
            server._bridge_quote(owner, AMOUNT_WEI)

    def test_router_error_names_status_and_body(self, bridge_env):
        bridge_env.responses["/v2/fungible/route"] = ValueError(
            "Router API /v2/fungible/route -> 429: too many requests")
        owner = bridge_env.accounts["testa"].owner_addr
        with pytest.raises(ValueError, match="429: too many requests"):
            server._bridge_quote(owner, AMOUNT_WEI)


class TestFeeBalanceArithmetic:
    def test_dry_run_quote_fields(self, bridge_env):
        owner = bridge_env.accounts["testa"].owner_addr
        bridge_env.mainnet_balances[owner] = VALUE_WEI + MAX_GAS_COST

        r = server.bridge_eth_from_mainnet(
            "0.01", account="testa", dry_run=True)

        assert r["dry_run"] is True
        assert r["amount_eth"] == "0.01"
        assert r["bridge_fee_eth"] == str(Web3.from_wei(FEE_WEI, "ether"))
        assert r["mainnet_gas_max_eth"] == str(
            Web3.from_wei(MAX_GAS_COST, "ether"))
        assert r["mainnet_balance_eth"] == str(
            Web3.from_wei(VALUE_WEI + MAX_GAS_COST, "ether"))
        assert r["estimated_duration_seconds"] == 300
        assert r["recipient_yominet"] == owner
        assert "tx_hash" not in r
        # dry run signs and broadcasts nothing
        assert bridge_env.signed == []
        assert bridge_env.raw_sent == []

    def test_exact_boundary_passes(self, bridge_env):
        owner = bridge_env.accounts["testa"].owner_addr
        bridge_env.mainnet_balances[owner] = VALUE_WEI + MAX_GAS_COST
        r = server.bridge_eth_from_mainnet(
            "0.01", account="testa", dry_run=True)
        assert r["dry_run"] is True

    def test_insufficient_balance_names_all_numbers(self, bridge_env):
        owner = bridge_env.accounts["testa"].owner_addr
        bridge_env.mainnet_balances[owner] = VALUE_WEI + MAX_GAS_COST - 1

        with pytest.raises(ValueError) as ei:
            server.bridge_eth_from_mainnet("0.01", account="testa")
        msg = str(ei.value)
        assert "0.01" in msg                                     # amount
        assert str(Web3.from_wei(FEE_WEI, "ether")) in msg       # bridge fee
        assert str(Web3.from_wei(MAX_GAS_COST, "ether")) in msg  # max gas
        assert str(Web3.from_wei(
            VALUE_WEI + MAX_GAS_COST - 1, "ether")) in msg       # balance
        assert bridge_env.signed == []
        assert bridge_env.raw_sent == []


class TestM1Broadcast:
    def test_returns_submitted_immediately_with_hash(self, bridge_env):
        owner = bridge_env.accounts["testa"].owner_addr
        bridge_env.mainnet_balances[owner] = ETH

        r = server.bridge_eth_from_mainnet("0.01", account="testa")

        # broadcast happened exactly once, owner-signed, quoted fields kept
        assert len(bridge_env.raw_sent) == 1
        assert bridge_env.signed[0]["key"] == KEY_A
        tx = bridge_env.signed[0]["tx"]
        assert tx["nonce"] == 7
        assert tx["gas"] == GAS
        assert tx["maxFeePerGas"] == MAX_FEE
        assert tx["value"] == VALUE_WEI
        assert tx["chainId"] == 1
        # the return is prompt and hash-bearing; the receipt is not
        # awaited (the fake's wait_for_transaction_receipt raises if
        # called) and no "next" hint is attached
        assert r["tx_hash"] == "0x" + "ab" * 32
        assert r["status"] == "submitted"
        assert r["recipient_yominet"] == owner
        assert "next" not in r

    def test_tracker_failure_after_send_does_not_raise(self, bridge_env):
        # M1: after the tx is broadcast nothing may raise, or the hash is
        # lost and a same-nonce retry invited.
        owner = bridge_env.accounts["testa"].owner_addr
        bridge_env.mainnet_balances[owner] = ETH
        bridge_env.track_error = True

        r = server.bridge_eth_from_mainnet("0.01", account="testa")

        assert r["tx_hash"] == "0x" + "ab" * 32
        assert r["status"] == "submitted"

    def test_recipient_not_expressible(self):
        params = set(
            inspect.signature(server.bridge_eth_from_mainnet).parameters)
        assert params == {"amount_eth", "account", "dry_run"}


class TestBridgeStatus:
    def _fake_status_get(self, monkeypatch, status_code, payload, text=""):
        def fake_get(url, params=None, timeout=None):
            assert url.endswith("/v2/tx/status")
            return SimpleNamespace(
                status_code=status_code, json=lambda: payload, text=text)
        monkeypatch.setattr(server.httpx, "get", fake_get)

    def test_completed_with_arrival_balance(self, bridge_env, monkeypatch):
        owner = bridge_env.accounts["testa"].owner_addr
        bridge_env.yominet_balances[owner] = AMOUNT_WEI
        transfer = {"state": "STATE_COMPLETED_SUCCESS", "leg": "final"}
        self._fake_status_get(
            monkeypatch, 200, {"transfers": [transfer]})

        r = server.bridge_status("0x" + "ab" * 32, account="testa")

        assert r["state"] == "STATE_COMPLETED_SUCCESS"
        assert r["completed"] is True
        assert r["yominet_owner_eth"] == "0.01"
        assert r["detail"] == transfer
        # the hash was (re-)registered with the tracker
        assert bridge_env.posts[0] == ("/v2/tx/track", {
            "tx_hash": "0x" + "ab" * 32, "chain_id": "1"})

    def test_pending_top_level_state(self, bridge_env, monkeypatch):
        self._fake_status_get(monkeypatch, 200, {"state": "STATE_PENDING"})
        r = server.bridge_status("0xdead", account="testa")
        assert r["state"] == "STATE_PENDING"
        assert r["completed"] is False

    def test_tracker_failure_ignored(self, bridge_env, monkeypatch):
        bridge_env.track_error = True
        self._fake_status_get(monkeypatch, 200, {"state": "STATE_PENDING"})
        r = server.bridge_status("0xdead", account="testa")
        assert r["state"] == "STATE_PENDING"

    def test_status_endpoint_error_surfaces_excerpt(
        self, bridge_env, monkeypatch
    ):
        self._fake_status_get(monkeypatch, 500, {}, text="tracker exploded")
        r = server.bridge_status("0xdead", account="testa")
        assert r["state"] == "unknown"
        assert r["detail"] == {"error": "tracker exploded"}

    def test_no_owner_key_reports_null_balance(self, bridge_env, monkeypatch):
        self._fake_status_get(monkeypatch, 200, {"state": "STATE_PENDING"})
        r = server.bridge_status("0xdead", account="noown")
        assert r["yominet_owner_eth"] is None


class TestMainnetRpcRequired:
    def test_startup_fails_loudly_without_mainnet_rpc_url(self, tmp_path):
        """M2: no default public endpoint — import refuses keyless."""
        env = {k: v for k, v in os.environ.items()
               if k != "MAINNET_RPC_URL"}
        env["HOME"] = str(tmp_path)  # no ~/.blocklife-keys/.env
        r = subprocess.run(
            [sys.executable, "-c", "import server"],
            cwd=str(Path(server.__file__).parent),
            env=env, capture_output=True, text=True, timeout=120,
        )
        assert r.returncode != 0
        assert "MAINNET_RPC_URL" in r.stderr
        assert "RuntimeError" in r.stderr

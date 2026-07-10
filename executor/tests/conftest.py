"""Shared offline fixtures for executor tool tests.

Everything here runs without keys, network, or chain access: accounts are
fabricated from well-known local-dev throwaway keys, and all chain / API /
transaction access is monkeypatched per test.
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# MAINNET_RPC_URL is required config with no default (the server refuses
# to start without it). Give the test process a loopback placeholder so
# the module imports keyless; nothing in the offline suite connects to it.
os.environ.setdefault("MAINNET_RPC_URL", "http://127.0.0.1:9/offline-test")

import server  # noqa: E402

# Well-known local-dev throwaway keys (standard anvil/hardhat test keys;
# never funded on any real network, not secrets).
KEY_A = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
KEY_B = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"


@pytest.fixture()
def accounts(monkeypatch):
    """Fabricated roster accounts, replacing whatever .env loaded.

    "testa"/"testb" have owner+operator keys; "noown" is operator-only.
    """
    a = server._Account("testa", KEY_A, KEY_A)
    b = server._Account("testb", KEY_B, KEY_B)
    noown = server._Account("noown", KEY_A, None)
    monkeypatch.setattr(
        server, "_accounts", {"testa": a, "testb": b, "noown": noown}
    )
    return {"testa": a, "testb": b, "noown": noown}


class FakeContract:
    """Stub for w3.eth.contract(): functions.<fn>(*args).call() -> handler(*args)."""

    def __init__(self, handlers):
        self._handlers = handlers  # {fn_name: callable(*args)}
        contract = self

        class _Functions:
            def __getattr__(self, fn_name):
                handler = contract._handlers[fn_name]

                def bind(*args):
                    return SimpleNamespace(
                        call=lambda params=None: handler(*args)
                    )

                return bind

        self.functions = _Functions()


@pytest.fixture()
def chain(monkeypatch):
    """Fake chain access.

    Returns a registry dict; tests install FakeContracts keyed by the
    system/component id (``_resolve_system``/``_resolve_component`` are
    patched to be identity functions). ``server.w3.eth.block_number`` and
    ``get_logs`` can be adjusted per test via ``server.w3.eth``.
    """
    registry: dict[str, FakeContract] = {}
    eth = SimpleNamespace(
        contract=lambda address=None, abi=None: registry[address],
        block_number=1_000,
        get_logs=lambda params: [],
    )
    monkeypatch.setattr(server, "w3", SimpleNamespace(eth=eth))
    monkeypatch.setattr(server, "_resolve_component", lambda cid: cid)
    monkeypatch.setattr(server, "_resolve_system", lambda sid: sid)
    return registry


@pytest.fixture()
def sent(monkeypatch):
    """Replace all tx senders with success stubs; returns the call log."""
    calls: list[dict] = []

    def ok(account, system_id, abi, args, **kw):
        calls.append(
            {"account": account, "system": system_id, "args": args, **kw}
        )
        return {
            "tx_hash": f"0xtx{len(calls)}",
            "status": "success",
            "block": 100 + len(calls),
            "gas_used": 500_000,
            "account": account,
        }

    def ok_batch(account, system_id, abi, fn_name, args, **kw):
        calls.append(
            {
                "account": account,
                "system": system_id,
                "fn_name": fn_name,
                "args": args,
                **kw,
            }
        )
        return {
            "tx_hash": f"0xtx{len(calls)}",
            "status": "success",
            "block": 100 + len(calls),
            "gas_used": 500_000,
            "account": account,
        }

    monkeypatch.setattr(server, "_send_tx", ok)
    monkeypatch.setattr(server, "_send_tx_retry", ok)
    monkeypatch.setattr(server, "_send_tx_owner", ok)
    monkeypatch.setattr(server, "_send_batch_tx", ok_batch)
    return calls


# --- Minimal protobuf wire-format encoder (mirrors _proto_decode_fields) ---


def enc_varint(v: int) -> bytes:
    out = b""
    while True:
        b7 = v & 0x7F
        v >>= 7
        if v:
            out += bytes([b7 | 0x80])
        else:
            out += bytes([b7])
            return out


def field_varint(num: int, v: int) -> bytes:
    return enc_varint(num << 3) + enc_varint(v)


def field_bytes(num: int, b: bytes) -> bytes:
    return enc_varint((num << 3) | 2) + enc_varint(len(b)) + b


def field_str(num: int, s: str) -> bytes:
    return field_bytes(num, s.encode())

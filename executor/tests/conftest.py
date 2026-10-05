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

import secrets_store  # noqa: E402
import server  # noqa: E402


# A loopback port nothing listens on: refused at once, never a network.
OFFLINE_RPC = "http://127.0.0.1:9/offline-test"


@pytest.fixture(autouse=True)
def _offline_rpc(monkeypatch):
    """The offline suite never reaches a network.

    The module's client is built at import on the public endpoint. A
    test that needs chain answers installs its own fake; anything it did
    not fake now fails at once against a dead loopback port instead of
    silently querying the public endpoint. It is still an HTTPProvider,
    so the production client's configuration can be asserted on it.
    """
    from web3 import Web3
    monkeypatch.setattr(server, "w3", Web3(Web3.HTTPProvider(
        OFFLINE_RPC, exception_retry_configuration=None)))
    monkeypatch.setattr(server, "_seq_batch_providers", {})


@pytest.fixture(autouse=True)
def _isolated_lanes(tmp_path, monkeypatch):
    """Every test gets its own lane state directory and lane registry.

    A lane is per-process state (floor, ledger of signed hashes); a test
    that inherited the previous test's lane would allocate nonces from
    a floor its own fake chain never saw. The directory is a temp path,
    so no test ever writes lane state under the developer's home.
    """
    monkeypatch.setenv("KAMI_LANE_DIR", str(tmp_path / "lanes"))
    monkeypatch.setattr(server, "_LANES", {})
    monkeypatch.setattr(server, "_INFLIGHT", {})
    monkeypatch.setattr(server, "_REOFFERED", set())
    monkeypatch.setattr(server, "_HEAD_SEEN", [0])


@pytest.fixture(autouse=True)
def _isolated_roster(monkeypatch):
    """Every test starts with an empty roster and no cached own index.

    Since 4.4.0 a lens read called with no account is for the roster's
    `main` entry, and a resolved index is cached for the process. A test
    must not see the labels the developer's own secret store loaded at
    import, nor an index another test resolved. Tests that need a roster
    install one (`accounts`, or their own)."""
    monkeypatch.setattr(server, "_accounts", {})
    monkeypatch.setattr(server, "_own_index_cache", {})


@pytest.fixture()
def secret_store(tmp_path, monkeypatch):
    """Point the secret store at a temp keys file for the whole test.

    Every test that exercises a path which READS or WRITES a secret must
    take this fixture. Without it a writer under test would set_key into
    the real ~/.blocklife-keys/ file, and a reader would see whatever
    keys the developer's machine happens to hold. Yields the temp keys
    file. The manifest points at a path that does not exist, so nothing
    is protected and no Keychain call is reachable.
    """
    monkeypatch.setenv("KAMI_SECRETS_BACKEND", "envfile")
    keys = tmp_path / ".env"
    keys.write_text("")
    original = (secrets_store.KEYS_PATH, secrets_store.MANIFEST_PATH)
    secrets_store.configure(
        keys_file=keys, manifest=tmp_path / "absent.secrets.names"
    )
    yield keys
    secrets_store.KEYS_PATH, secrets_store.MANIFEST_PATH = original
    secrets_store.reset()


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

    def ok_batch(account, system_id, abi, fn_name, args, gas_per_item=None, **kw):
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


# Sentinel account entity ID used by the permissive validation fixture.
FAKE_ACCOUNT_ID = 0x7777


@pytest.fixture()
def validation_ok(monkeypatch):
    """Make every pre-tx validation gate pass (offline).

    Registration resolves to FAKE_ACCOUNT_ID, every kami reads as owned
    by it and RESTING with an ACTIVE harvest, inventory is deep, and the
    getter view reports full stamina in room 1. Tests that exercise a
    specific gate patch the relevant helper themselves instead.
    """
    monkeypatch.setattr(
        server, "_require_registered_operator", lambda a: FAKE_ACCOUNT_ID
    )
    monkeypatch.setattr(
        server, "_require_registered_owner", lambda a: FAKE_ACCOUNT_ID
    )
    monkeypatch.setattr(server, "_kami_owner_id", lambda k: FAKE_ACCOUNT_ID)
    monkeypatch.setattr(server, "_kami_state", lambda k: "RESTING")
    monkeypatch.setattr(server, "_harvest_state", lambda k: "ACTIVE")
    monkeypatch.setattr(
        server, "_inventory_balance", lambda holder, item: 10**9
    )
    monkeypatch.setattr(
        server, "_account_view",
        lambda aid: {"index": 1, "name": "test", "stamina": 100, "room": 1},
    )
    return FAKE_ACCOUNT_ID


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

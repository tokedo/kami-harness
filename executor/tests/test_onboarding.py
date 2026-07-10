"""Offline tests for create_operator_wallet / register_account.

Key generation and persistence run against temp keys/roster files; the
register_account dry-run and send paths run against the faked chain and
tx-sender stubs from conftest. No keys, network, or chain access.
"""

import os
from types import SimpleNamespace

import pytest
import yaml
from web3 import Web3

from conftest import KEY_A, FakeContract

import server

_LABEL = "zznew"
_UP = _LABEL.upper()


@pytest.fixture()
def onboard_env(tmp_path, monkeypatch):
    """Temp keys file + temp roster path + empty registry, clean env."""
    keys = tmp_path / ".env"
    keys.write_text("")
    roster = tmp_path / "roster.yaml"
    monkeypatch.setattr(server, "_KEYS_PATH", keys)
    monkeypatch.setattr(server, "_ROSTER_PATH", roster)
    monkeypatch.setattr(server, "_accounts", {})
    for suffix in ("_OWNER_KEY", "_OPERATOR_KEY",
                   "_KAMIBOTS_API_KEY", "_PRIVY_ID"):
        monkeypatch.delenv(f"{_UP}{suffix}", raising=False)
    return SimpleNamespace(keys=keys, roster=roster)


class TestCreateOperatorWallet:
    def test_requires_owner_key(self, onboard_env):
        with pytest.raises(ValueError) as ei:
            server.create_operator_wallet(_LABEL)
        msg = str(ei.value)
        assert f"{_UP}_OWNER_KEY" in msg
        assert str(onboard_env.keys) in msg

    def test_rejects_bad_label(self, onboard_env):
        with pytest.raises(ValueError, match="bad-label!"):
            server.create_operator_wallet("bad-label!")

    def test_generates_persists_and_updates_roster(
        self, onboard_env, monkeypatch
    ):
        monkeypatch.setenv(f"{_UP}_OWNER_KEY", KEY_A)
        owner_addr = Web3().eth.account.from_key(KEY_A).address

        r = server.create_operator_wallet(_LABEL)

        assert r["operator_address"].startswith("0x")
        assert r["owner_address"] == owner_addr
        # key persisted to the configured keys file, never in the response
        env_text = onboard_env.keys.read_text()
        assert f"{_UP}_OPERATOR_KEY" in env_text
        # live registry hot-loaded, address consistent with stored key
        acct = server._accounts[_LABEL]
        assert acct.operator_addr == r["operator_address"]
        # no key material leaks: the private key hex appears nowhere in
        # the response, under any casing or prefix
        key_hex = acct.operator_key.removeprefix("0x").lower()
        assert key_hex not in str(r).lower()
        # roster.yaml created with the public addresses
        assert r["roster"] == "created"
        roster = yaml.safe_load(onboard_env.roster.read_text())
        entry = roster["accounts"][_LABEL]
        assert entry["owner_address"] == owner_addr
        assert entry["operator_address"] == r["operator_address"]
        # ... and no key material in the roster either
        assert key_hex not in onboard_env.roster.read_text().lower()

    def test_roster_append_preserves_existing_content(
        self, onboard_env, monkeypatch
    ):
        onboard_env.roster.write_text(
            "# hand-written comment that must survive\n"
            "accounts:\n"
            "  veteran:\n"
            '    owner_address: "0x0000000000000000000000000000000000000001"\n'
            '    operator_address: "0x0000000000000000000000000000000000000002"\n'
            '    notes: "keep me"\n'
        )
        monkeypatch.setenv(f"{_UP}_OWNER_KEY", KEY_A)

        r = server.create_operator_wallet(_LABEL)

        assert r["roster"] == "added"
        text = onboard_env.roster.read_text()
        assert "# hand-written comment that must survive" in text
        roster = yaml.safe_load(text)
        assert set(roster["accounts"]) == {"veteran", _LABEL}
        assert roster["accounts"]["veteran"]["notes"] == "keep me"
        assert (roster["accounts"][_LABEL]["operator_address"]
                == r["operator_address"])

    def test_roster_label_already_present(self, onboard_env, monkeypatch):
        onboard_env.roster.write_text(
            "accounts:\n"
            f"  {_LABEL}:\n"
            '    owner_address: "0x0000000000000000000000000000000000000001"\n'
        )
        before = onboard_env.roster.read_text()
        monkeypatch.setenv(f"{_UP}_OWNER_KEY", KEY_A)

        r = server.create_operator_wallet(_LABEL)

        assert r["roster"] == "already_present"
        assert onboard_env.roster.read_text() == before

    def test_upgrades_owner_only_registry_entry_in_place(
        self, onboard_env, monkeypatch
    ):
        # _load_accounts registers owner-only labels since v1.3.1, so
        # the label is already live when the operator is created — the
        # entry must upgrade in place, not conflict or duplicate.
        monkeypatch.setenv(f"{_UP}_OWNER_KEY", KEY_A)
        owner_only = server._Account(_LABEL, None, KEY_A)
        owner_only.api_key = "kb-live-credential"  # in-memory only
        server._accounts[_LABEL] = owner_only

        r = server.create_operator_wallet(_LABEL)

        assert list(server._accounts) == [_LABEL]  # upgraded, no duplicate
        acct = server._accounts[_LABEL]
        assert acct.has_operator
        assert acct.operator_addr == r["operator_address"]
        assert acct.owner_addr == owner_only.owner_addr
        assert acct.api_key == "kb-live-credential"  # survives the upgrade
        assert r["roster"] == "created"

    def test_rejects_existing_operator_and_names_address(
        self, onboard_env, monkeypatch
    ):
        monkeypatch.setenv(f"{_UP}_OWNER_KEY", KEY_A)
        first = server.create_operator_wallet(_LABEL)
        with pytest.raises(ValueError) as ei:
            server.create_operator_wallet(_LABEL)
        msg = str(ei.value)
        assert "already has an operator key" in msg
        assert first["operator_address"] in msg


class TestRegisterAccountValidation:
    def test_name_too_long(self, accounts):
        with pytest.raises(ValueError) as ei:
            server.register_account("sixteen-bytes-xx", account="testa")
        msg = str(ei.value)
        assert "1-15 bytes" in msg
        assert "16 bytes" in msg

    def test_name_empty(self, accounts):
        with pytest.raises(ValueError, match="1-15 bytes"):
            server.register_account("", account="testa")

    def test_name_multibyte_counted_in_bytes(self, accounts):
        with pytest.raises(ValueError) as ei:
            server.register_account("六六六六六六", account="testa")  # 18 bytes
        assert "18 bytes" in str(ei.value)

    def test_name_whitespace_named(self, accounts):
        with pytest.raises(ValueError) as ei:
            server.register_account("bad name", account="testa")
        msg = str(ei.value)
        assert "whitespace" in msg
        assert "bad name" in msg

    def test_no_owner_key(self, accounts):
        with pytest.raises(ValueError, match="no owner key"):
            server.register_account("newbie", account="noown")


class TestRegisterAccountDryRun:
    """eth_call dry-run revert mapping — no transaction is ever sent."""

    def _install(self, chain, exc):
        def executeTyped(operator, name):
            if exc:
                raise exc
            return b""
        chain["system.account.register"] = FakeContract(
            {"executeTyped": executeTyped}
        )

    def test_exists_for_owner(self, accounts, chain, sent):
        self._install(chain, Exception(
            "execution reverted: Account: exists for Owner"))
        with pytest.raises(ValueError) as ei:
            server.register_account("newbie", account="testa")
        msg = str(ei.value)
        assert "Registration would revert" in msg
        assert "already registered" in msg
        assert sent == []

    def test_exists_for_operator(self, accounts, chain, sent):
        self._install(chain, Exception(
            "execution reverted: Account: exists for Operator"))
        with pytest.raises(ValueError, match="bound to another account"):
            server.register_account("newbie", account="testa")
        assert sent == []

    def test_name_taken(self, accounts, chain, sent):
        self._install(chain, Exception(
            "execution reverted: Account: name taken"))
        with pytest.raises(ValueError) as ei:
            server.register_account("newbie", account="testa")
        assert "'newbie' is taken" in str(ei.value)
        assert sent == []

    def test_unmapped_revert_passes_reason_through(
        self, accounts, chain, sent
    ):
        self._install(chain, Exception("execution reverted: whatever else"))
        with pytest.raises(ValueError, match="whatever else"):
            server.register_account("newbie", account="testa")
        assert sent == []

    def test_happy_path_sends_owner_tx(self, accounts, chain, sent):
        self._install(chain, None)
        r = server.register_account("newbie", account="testa")
        assert len(sent) == 1
        call = sent[0]
        assert call["system"] == "system.account.register"
        assert call["gas_limit"] == 2_000_000
        operator_addr, name = call["args"]
        assert operator_addr == accounts["testa"].operator_addr
        assert name == "newbie"
        assert r["status"] == "success"
        assert r["name"] == "newbie"
        assert r["operator_address"] == accounts["testa"].operator_addr
        assert r["owner_address"] == accounts["testa"].owner_addr
        assert r["account_entity_id"] == hex(
            int(accounts["testa"].owner_addr, 16))
        assert r["starting_room"] == 1
        assert "next" not in r  # descriptive responses carry no hints

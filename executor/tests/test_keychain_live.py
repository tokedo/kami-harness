"""LIVE macOS Keychain smoke — opt-in, throwaway item only.

Skipped unless KAMI_KEYCHAIN_LIVE_TEST=1 on darwin. It writes ONE
generic-password item, reads it back through a fresh server process, and
deletes it. Containment is asserted, not assumed:

  * the only service string this file ever passes to `security` is
    kami-mcp/HTEST_OWNER_KEY — asserted before each call;
  * the item must NOT already exist (rc 44) or the test fails rather
    than overwriting somebody's secret;
  * nothing enumerates, dumps, or searches the keychain;
  * teardown runs in a finally and the post-check asserts rc 44.

The stored value is the standard anvil/hardhat throwaway key from
conftest — never funded on any real network, not a secret.
"""

import getpass
import os
import subprocess
import sys
from pathlib import Path

import pytest
from web3 import Web3

from conftest import KEY_A

import secrets_store

pytestmark = pytest.mark.skipif(
    os.environ.get("KAMI_KEYCHAIN_LIVE_TEST") != "1" or sys.platform != "darwin",
    reason="live Keychain smoke is opt-in (KAMI_KEYCHAIN_LIVE_TEST=1, macOS)",
)

NAME = "HTEST_OWNER_KEY"
SERVICE = "kami-mcp/HTEST_OWNER_KEY"
LABEL = "htest"
RC_NOT_FOUND = 44
EXPECTED_ADDR = Web3().eth.account.from_key(KEY_A).address


def _security(*args, expect=None):
    """Run `security` against this test's own item only."""
    assert SERVICE in args, f"refusing a security call not naming {SERVICE}"
    assert not ({"dump-keychain", "find-internet-password"} & set(args))
    proc = subprocess.run(
        ["security", *args], capture_output=True, text=True, timeout=15
    )
    if expect is not None:
        assert proc.returncode == expect, (args[0], proc.returncode, proc.stderr)
    return proc


def _find(expect=None):
    return _security(
        "find-generic-password", "-a", getpass.getuser(), "-s", SERVICE,
        expect=expect,
    )


def _delete():
    return _security(
        "delete-generic-password", "-a", getpass.getuser(), "-s", SERVICE
    )


def test_keychain_round_trip_and_cleanup(tmp_path):
    # Pre-flight: never clobber an existing item.
    assert _find().returncode == RC_NOT_FOUND, (
        f"{SERVICE} already exists — refusing to touch it"
    )

    manifest = tmp_path / "live.secrets.names"
    manifest.write_text(f"{NAME}\n")
    keys = tmp_path / "live.env"
    keys.write_text("")

    original = (secrets_store.KEYS_PATH, secrets_store.MANIFEST_PATH)
    prior_backend = os.environ.get("KAMI_SECRETS_BACKEND")
    try:
        os.environ["KAMI_SECRETS_BACKEND"] = "keychain"
        secrets_store.configure(keys_file=keys, manifest=manifest)

        # Phase 1 — provisioning. The manifest declares the name
        # protected; put() stores it. (Starting a server while the name
        # is still missing is the MissingSecretError path, covered
        # offline in test_secrets_store.py.)
        secrets_store._protected.update(secrets_store._read_manifest())
        assert secrets_store.is_protected(NAME)
        assert secrets_store.where(NAME) == f"macOS Keychain ({SERVICE})"
        secrets_store.put(NAME, KEY_A)  # delete-then-add over `security -i`
        assert _find().returncode == 0, "item was not created"

        # Phase 2 — startup. load() resolves it from the Keychain, and
        # says so.
        secrets_store.reset()
        secrets_store.load()
        assert secrets_store._sources[NAME] == "keychain"
        assert secrets_store.get(NAME) == KEY_A

        # READ BACK in a fresh process: the account must load from the
        # Keychain alone — the keys file is empty and the environment
        # carries no key.
        env = {
            k: v for k, v in os.environ.items()
            if not k.endswith(("_OWNER_KEY", "_OPERATOR_KEY"))
        }
        env.update({
            "KAMI_SECRETS_BACKEND": "keychain",
            "KAMI_KEYS_FILE": str(keys),
            "KAMI_SECRETS_MANIFEST": str(manifest),
            "MAINNET_RPC_URL": "http://127.0.0.1:9/offline-test",
            "PYTHONPATH": str(Path(__file__).resolve().parent.parent),
        })
        child = subprocess.run(
            [sys.executable, "-c",
             f"import server; print(server._accounts[{LABEL!r}].owner_addr)"],
            cwd=str(Path(__file__).resolve().parent.parent),
            env=env, capture_output=True, text=True, timeout=120,
        )
        assert child.returncode == 0, child.stderr
        assert child.stdout.strip() == EXPECTED_ADDR
        # the key itself never appears on either stream
        for stream in (child.stdout, child.stderr):
            assert KEY_A not in stream
            assert KEY_A.removeprefix("0x") not in stream
    finally:
        _delete()
        secrets_store.KEYS_PATH, secrets_store.MANIFEST_PATH = original
        secrets_store.reset()
        if prior_backend is None:
            os.environ.pop("KAMI_SECRETS_BACKEND", None)
        else:
            os.environ["KAMI_SECRETS_BACKEND"] = prior_backend

    # Post-check: the throwaway item is gone.
    assert _find().returncode == RC_NOT_FOUND, f"{SERVICE} survived teardown"

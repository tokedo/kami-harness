"""Offline tests for the pluggable secret store (3.1.0).

Everything here runs against temp files with the envfile backend, except
where a test explicitly stubs the Keychain helpers. Nothing in this file
can reach the real ~/.blocklife-keys/ or the real macOS Keychain: the
`store` fixture re-points the module and every Keychain-backend test
replaces `_keychain_read` / `_keychain_write` first. The live-Keychain
smoke lives in test_keychain_live.py and is opt-in.

The values used are well-known local-dev throwaway keys (see conftest),
never real secrets.
"""

import ast
import os
import re
from pathlib import Path

import pytest

import secrets_store
from conftest import KEY_A, KEY_B

EXECUTOR = Path(__file__).resolve().parent.parent

# A value that must never appear in output, exception text, or os.environ.
SENTINEL = KEY_B


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """The store, pointed at temp paths, with an isolated environment.

    os.environ is replaced by a copy so load()'s config export cannot
    leak into the rest of the session.
    """
    monkeypatch.setattr(os, "environ", dict(os.environ))
    for var in ("KAMI_SECRETS_BACKEND", "KAMI_KEYS_FILE",
                "KAMI_SECRETS_MANIFEST", "ALLOW_ENV_SECRETS",
                "KAMI_SECRETS_VERBOSE"):
        os.environ.pop(var, None)
    keys = tmp_path / ".env"
    keys.write_text("")
    manifest = tmp_path / ".secrets.names"
    original = (secrets_store.KEYS_PATH, secrets_store.MANIFEST_PATH)
    secrets_store.configure(keys_file=keys, manifest=manifest)
    yield type("S", (), {"keys": keys, "manifest": manifest, "dir": tmp_path})
    secrets_store.KEYS_PATH, secrets_store.MANIFEST_PATH = original
    secrets_store.reset()


class TestManifestPath:
    """The manifest is a sibling of the keys file: name with a trailing
    '.env' removed, plus '.secrets.names'."""

    @pytest.mark.parametrize("keys_name,expected", [
        (".env", ".secrets.names"),
        ("hybrid.env", "hybrid.secrets.names"),
        ("keys.txt", "keys.txt.secrets.names"),
    ])
    def test_derived_from_keys_file(self, store, keys_name, expected):
        secrets_store.configure(
            keys_file=store.dir / keys_name, manifest=False or None
        )
        secrets_store.MANIFEST_PATH = None
        derived = secrets_store._manifest_path()
        assert derived == store.dir / expected
        assert derived.parent == (store.dir / keys_name).parent

    def test_explicit_override_wins(self, store):
        secrets_store.configure(manifest=store.dir / "elsewhere.names")
        assert secrets_store._manifest_path() == store.dir / "elsewhere.names"

    def test_absent_manifest_protects_nothing(self, store):
        assert not store.manifest.exists()
        secrets_store.load()
        assert secrets_store._protected == set()
        assert not secrets_store.is_protected("MAIN_OWNER_KEY")


class TestManifestParsing:
    def test_names_comments_and_blanks(self, store):
        store.manifest.write_text(
            "# a comment\n"
            "\n"
            "MAIN_OWNER_KEY\n"
            "   MAIN_OPERATOR_KEY   \n"
            "  # indented comment\n"
        )
        assert secrets_store._read_manifest() == {
            "MAIN_OWNER_KEY", "MAIN_OPERATOR_KEY"
        }


class TestEnvFileParser:
    def test_tolerances(self, store):
        store.keys.write_text(
            "# comment\n"
            "\n"
            "PLAIN=one\n"
            "SPACED = two\n"
            "export EXPORTED=three\n"
            "SINGLE='four'\n"
            'DOUBLE="five"\n'
            "TRAILING=six # not part of the value\n"
            "NOEQUALS\n"
        )
        parsed = secrets_store._parse_env_file(store.keys)
        assert parsed == {
            "PLAIN": "one", "SPACED": "two", "EXPORTED": "three",
            "SINGLE": "four", "DOUBLE": "five", "TRAILING": "six",
        }

    def test_missing_file_is_empty(self, store):
        assert secrets_store._parse_env_file(store.dir / "nope.env") == {}

    def test_round_trips_what_put_writes(self, store):
        """python-dotenv (pinned 1.2.2) quotes what set_key writes; the
        parser must read back exactly what put() stored."""
        secrets_store.put("ZZ_OWNER_KEY", KEY_A)
        reread = secrets_store._parse_env_file(store.keys)
        assert reread["ZZ_OWNER_KEY"] == KEY_A


class TestEnvfileIsTheDefault:
    """The D85 boundary: a deployment that configures nothing never
    reaches the Keychain."""

    def test_backend_defaults_to_envfile(self, store):
        assert "KAMI_SECRETS_BACKEND" not in os.environ
        assert secrets_store._backend() == "envfile"

    def test_no_keychain_call_on_any_path(self, store, monkeypatch):
        def forbidden(*a, **kw):
            raise AssertionError("Keychain reached on the envfile backend")
        monkeypatch.setattr(secrets_store, "_keychain_read", forbidden)
        monkeypatch.setattr(secrets_store, "_keychain_write", forbidden)
        # even with a manifest naming a protected name
        store.manifest.write_text("MAIN_OWNER_KEY\n")
        store.keys.write_text(f"MAIN_OWNER_KEY={KEY_A}\n")
        secrets_store.load()
        assert secrets_store.get("MAIN_OWNER_KEY") == KEY_A
        secrets_store.put("MAIN_OPERATOR_KEY", KEY_A)
        assert secrets_store.where("MAIN_OWNER_KEY") == str(store.keys)

    def test_unknown_backend_fails_loudly(self, store):
        os.environ["KAMI_SECRETS_BACKEND"] = "keychian"
        with pytest.raises(ValueError) as ei:
            secrets_store._backend()
        assert "keychian" in str(ei.value)
        assert "envfile" in str(ei.value)


class TestLoadExportsConfigOnly:
    def test_non_secret_config_exported_secrets_never(self, store):
        store.keys.write_text(
            "ZZ_CONFIG_URL=http://example.invalid\n"
            "ZZ_CONFIG_MODE=envelope\n"
            f"MAIN_OWNER_KEY={SENTINEL}\n"
            "MAIN_PRIVY_ID=did:privy:zz\n"
            "SOME_TOKEN=tok\n"
        )
        secrets_store.load()
        assert os.environ["ZZ_CONFIG_URL"] == "http://example.invalid"
        assert os.environ["ZZ_CONFIG_MODE"] == "envelope"
        for name in ("MAIN_OWNER_KEY", "MAIN_PRIVY_ID", "SOME_TOKEN"):
            assert name not in os.environ, name
        assert SENTINEL not in "\x00".join(os.environ.values())

    def test_process_environment_wins_over_the_file(self, store):
        os.environ["RPC_URL"] = "http://from-the-process"
        store.keys.write_text("RPC_URL=http://from-the-file\n")
        secrets_store.load()
        assert os.environ["RPC_URL"] == "http://from-the-process"


class TestKnownNamesAndGet:
    def test_keys_file_and_process_env_both_visible(self, store):
        store.keys.write_text(f"FILE_OWNER_KEY={KEY_A}\n")
        os.environ["ENVACCT_OWNER_KEY"] = KEY_B
        secrets_store.load()
        known = secrets_store.known_names()
        assert "FILE_OWNER_KEY" in known
        assert "ENVACCT_OWNER_KEY" in known  # the synthetic-account path
        assert secrets_store.get("ENVACCT_OWNER_KEY") == KEY_B

    def test_non_secret_names_are_not_known(self, store):
        store.keys.write_text("RPC_URL=http://example.invalid\n")
        secrets_store.load()
        assert "RPC_URL" not in secrets_store.known_names()

    def test_absent_name(self, store):
        secrets_store.load()
        assert secrets_store.get("NOPE_OWNER_KEY") is None
        with pytest.raises(secrets_store.MissingSecretError):
            secrets_store.get("NOPE_OWNER_KEY", required=True)


class TestPutRouting:
    def test_envfile_writes_the_keys_file(self, store):
        secrets_store.load()
        secrets_store.put("ZZ_OPERATOR_KEY", KEY_A)
        assert "ZZ_OPERATOR_KEY" in store.keys.read_text()
        assert secrets_store.get("ZZ_OPERATOR_KEY") == KEY_A

    def test_keychain_backend_routes_protected_names(self, store, monkeypatch):
        written = {}
        monkeypatch.setattr(secrets_store, "_keychain_write",
                            lambda n, v: written.__setitem__(n, v))
        monkeypatch.setattr(secrets_store, "_keychain_read",
                            lambda n: written.get(n))
        written["ZZ_OWNER_KEY"] = SENTINEL  # already in the "Keychain"
        store.manifest.write_text("ZZ_OWNER_KEY\n")
        os.environ["KAMI_SECRETS_BACKEND"] = "keychain"
        secrets_store.load()
        assert secrets_store.get("ZZ_OWNER_KEY") == SENTINEL

        secrets_store.put("ZZ_OWNER_KEY", KEY_A)          # protected
        secrets_store.put("ZZ_KAMIBOTS_API_KEY", "kb-x")  # not protected

        assert list(written) == ["ZZ_OWNER_KEY"]
        assert written["ZZ_OWNER_KEY"] == KEY_A  # replaced, not appended
        assert "ZZ_OWNER_KEY" not in store.keys.read_text()
        assert "ZZ_KAMIBOTS_API_KEY" in store.keys.read_text()

    def test_refuses_empty(self, store):
        with pytest.raises(ValueError, match="empty secret"):
            secrets_store.put("ZZ_OWNER_KEY", "")


class TestWhereTexts:
    def test_envfile_names_the_keys_file(self, store):
        secrets_store.load()
        assert secrets_store.where("MAIN_OWNER_KEY") == str(store.keys)

    def test_keychain_names_the_item(self, store, monkeypatch):
        monkeypatch.setattr(secrets_store, "_keychain_read", lambda n: KEY_A)
        store.manifest.write_text("MAIN_OWNER_KEY\n")
        os.environ["KAMI_SECRETS_BACKEND"] = "keychain"
        secrets_store.load()
        assert secrets_store.where("MAIN_OWNER_KEY") == (
            "macOS Keychain (kami-mcp/MAIN_OWNER_KEY)"
        )
        # an unprotected name still lives in the keys file
        assert secrets_store.where("OTHER_OWNER_KEY") == str(store.keys)


class TestMissingProtectedSecret:
    def _keychainless(self, store, monkeypatch):
        monkeypatch.setattr(secrets_store, "_keychain_read", lambda n: None)
        store.manifest.write_text("MAIN_OWNER_KEY\n")
        os.environ["KAMI_SECRETS_BACKEND"] = "keychain"

    def test_raises_naming_only_the_name(self, store, monkeypatch):
        self._keychainless(store, monkeypatch)
        # the value IS present in the keys file — without the escape
        # hatch it must not be used, and must not be quoted back.
        store.keys.write_text(f"MAIN_OWNER_KEY={SENTINEL}\n")
        with pytest.raises(secrets_store.MissingSecretError) as ei:
            secrets_store.load()
        msg = str(ei.value)
        assert "MAIN_OWNER_KEY" in msg
        assert SENTINEL not in msg
        assert SENTINEL.removeprefix("0x") not in msg
        assert ei.value.names == ["MAIN_OWNER_KEY"]

    def test_escape_hatch_warns_with_names_only(
        self, store, monkeypatch, capsys
    ):
        self._keychainless(store, monkeypatch)
        store.keys.write_text(f"MAIN_OWNER_KEY={SENTINEL}\n")
        os.environ["ALLOW_ENV_SECRETS"] = "1"
        secrets_store.load()
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "MAIN_OWNER_KEY" in captured.err
        assert "env fallback" in captured.err
        assert SENTINEL not in captured.err
        assert secrets_store.get("MAIN_OWNER_KEY") == SENTINEL


class TestStartupReport:
    def test_report_goes_to_stderr_names_only(self, store, capsys):
        store.keys.write_text(f"MAIN_OWNER_KEY={SENTINEL}\n")
        secrets_store.load()
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "Secrets: 1 total" in captured.err
        assert SENTINEL not in captured.err

    def test_nothing_to_report_says_nothing(self, store, capsys):
        """A deployment with no keys is as quiet as it was before this
        module existed — the keyless lab machine prints one line, and
        that line is the account warning, not a secrets report."""
        secrets_store.load()
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""


class TestNoValueInterpolation:
    """Static scan: no secret value can reach a message.

    Every f-string, and every string literal, in the store and in the
    server module is checked for an interpolation of a value-bearing
    binding. This is the guard that a later edit trips, not a claim
    about today's source only.
    """

    VALUE_BINDINGS = {
        "value", "v", "op_key", "owner_key", "own_key", "api_key",
        "privy_id", "legacy_api", "legacy_privy", "secret", "token",
    }
    VALUE_EXPRESSIONS = ("_values[", "secrets_store.get(", ".operator_key",
                         ".owner_key", "acct.api_key", "acct.privy_id")

    # The single admitted interpolation in the codebase: the value has
    # to reach `security` somehow, and stdin is the channel that keeps it
    # out of argv. Exempted by function, and pinned by the two tests
    # below so the exemption cannot quietly widen.
    STDIN_EXEMPT = ("secrets_store.py", "_keychain_write")

    @pytest.mark.parametrize("module", ["secrets_store.py", "server.py"])
    def test_no_fstring_interpolates_a_secret(self, module):
        tree = ast.parse((EXECUTOR / module).read_text())
        exempt = set()
        for fn in ast.walk(tree):
            if (isinstance(fn, ast.FunctionDef)
                    and (module, fn.name) == self.STDIN_EXEMPT):
                exempt = {id(sub) for sub in ast.walk(fn)}
        offenders = []
        for node in ast.walk(tree):
            if id(node) in exempt:
                continue
            if not isinstance(node, ast.JoinedStr):
                continue
            for part in node.values:
                if not isinstance(part, ast.FormattedValue):
                    continue
                src = ast.unparse(part.value)
                if src in self.VALUE_BINDINGS or any(
                    frag in src for frag in self.VALUE_EXPRESSIONS
                ):
                    offenders.append((module, node.lineno, src))
        assert not offenders, f"secret value interpolated: {offenders}"

    @pytest.mark.parametrize("module", ["secrets_store.py", "server.py"])
    def test_no_literal_names_a_value_placeholder(self, module):
        """Belt to the ast brace: a .format()/%-style placeholder naming
        a value binding, which the ast scan would not see."""
        text = (EXECUTOR / module).read_text()
        for binding in sorted(self.VALUE_BINDINGS):
            for m in re.finditer(rf'\{{{binding}\}}', text):
                line = text[:m.start()].count("\n") + 1
                assert self._is_the_keychain_stdin_line(text, line), (
                    module, line, binding
                )

    @staticmethod
    def _is_the_keychain_stdin_line(text: str, lineno: int) -> bool:
        return text.splitlines()[lineno - 1].strip() == (
            'f\'-w "{value}" -T /usr/bin/security\\n\''
        )

    def test_the_value_reaches_security_over_stdin_never_argv(self):
        """The exempted site, pinned: the command carrying the value is
        fed to `security -i` through `input=`, and no argv list in the
        module carries it."""
        text = (EXECUTOR / "secrets_store.py").read_text()
        assert '["security", "-i"], input=cmd' in text
        assert '-w", value' not in text
        assert text.count("{value}") == 1

"""Pluggable secret store for the MCP executor.

Every private key, API credential and token the server holds is resolved
through this module. Two backends:

  ``envfile`` (DEFAULT)  reads and writes the keys file, today's
                         ``~/.blocklife-keys/.env``. This is the
                         behaviour every earlier version had, and it is
                         what a lab machine or a run VM gets unless it is
                         configured otherwise.
  ``keychain``           protected names live encrypted at rest in the
                         macOS login Keychain as generic-password items
                         ``kami-mcp/<NAME>`` (account = login user);
                         everything else still comes from the keys file.

Which names are protected is defined by a names-only manifest (one name
per line, no values) sitting beside the keys file. **If the manifest is
absent nothing is protected**, which is the state of a plain deployment:
no Keychain item is read, written, or looked for.

Configuration, all optional, all environment:

  KAMI_KEYS_FILE        keys file path (default ~/.blocklife-keys/.env)
  KAMI_SECRETS_BACKEND  envfile (default) | keychain
  KAMI_SECRETS_MANIFEST manifest path (default: the keys file's name with
                        a trailing ".env" removed, plus ".secrets.names",
                        in the same directory — so ~/.blocklife-keys/.env
                        -> ~/.blocklife-keys/.secrets.names and
                        ~/.blocklife-keys/hybrid.env ->
                        ~/.blocklife-keys/hybrid.secrets.names)
  ALLOW_ENV_SECRETS=1   escape hatch: let a protected name resolve from
                        the process env / keys file, with a warning
  KAMI_SECRETS_VERBOSE=1  list Keychain-sourced names in the startup
                        source report (names only, never values)

Secret VALUES never enter os.environ, argv, stdout, tool results, or
exception text — they exist only inside this process and, for protected
names, in the Keychain. Non-secret config from the keys file IS exported
to os.environ (via setdefault, so the process environment wins), because
that is how RPC_URL and friends have always reached the server.

Ported from ~/kami-hybrid-play/executor/secrets_store.py (65b96e6). The
backend default is inverted here: hybrid-play defaults to the Keychain,
this module defaults to the keys file.
"""

from __future__ import annotations

import concurrent.futures
import getpass
import os
import subprocess
import sys
from pathlib import Path

SERVICE_PREFIX = "kami-mcp/"
BACKENDS = ("envfile", "keychain")

_DEFAULT_KEYS_PATH = Path.home() / ".blocklife-keys" / ".env"

# Resolved at import; configure() re-points them (tests, alternate
# deployments). Read through keys_path() / _manifest_path(), never
# captured into another module's constant — a second copy is how a path
# goes stale.
KEYS_PATH: Path = Path(
    os.environ.get("KAMI_KEYS_FILE") or _DEFAULT_KEYS_PATH
).expanduser()
MANIFEST_PATH: Path | None = (
    Path(os.environ["KAMI_SECRETS_MANIFEST"]).expanduser()
    if os.environ.get("KAMI_SECRETS_MANIFEST")
    else None
)

_KC_ACCOUNT = getpass.getuser()
_SECRET_SUFFIXES = ("_KEY", "_TOKEN", "_SECRET", "_PRIVY_ID")
_SECRET_EXACT = {"PRIVY_ID"}

_values: dict[str, str] = {}
_sources: dict[str, str] = {}  # name -> "keychain" | "env"
_envfile: dict[str, str] = {}
_protected: set[str] = set()


class MissingSecretError(RuntimeError):
    """A protected secret resolved nowhere. Names only, never values."""

    def __init__(self, names: list[str]):
        shown = ", ".join(names[:5]) + (
            f" (+{len(names) - 5} more)" if len(names) > 5 else ""
        )
        super().__init__(
            f"Missing {len(names)} protected secret(s): {shown}. Expected in "
            f"the macOS Keychain as generic-password items "
            f"'{SERVICE_PREFIX}<NAME>' (the protected names are the ones "
            f"listed in {_manifest_path()}), or set ALLOW_ENV_SECRETS=1 to "
            f"fall back to {keys_path()}."
        )
        self.names = names


def keys_path() -> Path:
    """The keys file this process reads and writes."""
    return KEYS_PATH


def is_secret_name(name: str) -> bool:
    return name.endswith(_SECRET_SUFFIXES) or name in _SECRET_EXACT


def _backend() -> str:
    """The configured backend. An unrecognised value fails loudly.

    A typo must not resolve to a backend by accident: everything except
    the exact string "envfile" would otherwise reach the Keychain path,
    which is precisely the boundary this module exists to keep.
    """
    backend = os.environ.get("KAMI_SECRETS_BACKEND", "envfile").strip().lower()
    if backend not in BACKENDS:
        raise ValueError(
            f"KAMI_SECRETS_BACKEND={backend!r} is not a known backend; "
            f"expected one of {', '.join(BACKENDS)}."
        )
    return backend


def _env_allowed() -> bool:
    return os.environ.get("ALLOW_ENV_SECRETS") == "1"


def is_protected(name: str) -> bool:
    return name in _protected


def where(name: str) -> str:
    """Human-readable resolved location for a given secret name."""
    if _backend() != "envfile" and is_protected(name):
        return f"macOS Keychain ({SERVICE_PREFIX}{name})"
    return str(keys_path())


def _manifest_path() -> Path:
    """Manifest of protected names: the keys file's own name with a
    trailing ".env" removed, plus ".secrets.names", in the same
    directory. Path.stem is deliberately not used — pathlib reads a bare
    ".env" as a stem with no suffix, which would derive the wrong name
    for the default keys file."""
    if MANIFEST_PATH is not None:
        return MANIFEST_PATH
    path = keys_path()
    return path.parent / (path.name.removesuffix(".env") + ".secrets.names")


def _read_manifest() -> set[str]:
    path = _manifest_path()
    if not path.exists():
        return set()
    names = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.add(line)
    return names


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse a dotenv-style file into a name -> value mapping.

    Tolerates ``KEY = value`` spacing, an optional ``export`` prefix, and
    single- or double-quoted values (python-dotenv's set_key quotes what
    it writes). Values are secrets — never log them.
    """
    parsed: dict[str, str] = {}
    if not path.exists():
        return parsed
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            name = name.strip().removeprefix("export").strip()
            if not name:
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] in "'\"" and value[-1] in "'\"":
                value = value[1:-1]
            else:
                value = value.split(" #", 1)[0].rstrip()
            parsed[name] = value
    return parsed


def _keychain_read(name: str) -> str | None:
    """Read one secret from the Keychain. Returns None if absent/unreadable."""
    if sys.platform != "darwin":
        return None
    try:
        proc = subprocess.run(
            ["security", "find-generic-password", "-a", _KC_ACCOUNT,
             "-s", SERVICE_PREFIX + name, "-w"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    value = proc.stdout.rstrip("\n")
    return value or None


def _keychain_write(name: str, value: str) -> None:
    """Write one secret to the Keychain (delete-then-add, never update).

    In-place update (`add-generic-password -U` on an existing item) asks
    securityd for an ACL change, which blocks on a GUI confirmation dialog
    and wedges every later access to the item — so we always delete the
    old item (no dialog) and create a fresh one. The value is fed to
    ``security -i`` over stdin so it never appears in argv (visible via
    ps) or in a shell string. -T /usr/bin/security at CREATION time lets
    later reads by the security CLI proceed without a per-item GUI
    prompt. Error paths never include the value.
    """
    if any(c in value for c in '"\\\n\r'):
        raise ValueError(
            f"Secret '{name}' contains characters unsafe for a keychain "
            f"write (quote/backslash/newline) — store it manually."
        )
    subprocess.run(
        ["security", "delete-generic-password", "-a", _KC_ACCOUNT,
         "-s", SERVICE_PREFIX + name],
        capture_output=True, text=True, timeout=15,
    )  # rc 44 (not found) is fine — only the fresh add below matters
    cmd = (
        f'add-generic-password -a "{_KC_ACCOUNT}" -s "{SERVICE_PREFIX}{name}" '
        f'-w "{value}" -T /usr/bin/security\n'
    )
    try:
        proc = subprocess.run(
            ["security", "-i"], input=cmd, text=True,
            capture_output=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(
            f"Keychain write failed for '{name}': {type(e).__name__}"
        ) from None
    # security -i exit codes are unreliable across versions — the
    # read-back below is the authoritative success check.
    if _keychain_read(name) != value:
        raise RuntimeError(
            f"Keychain write for '{name}' did not verify on read-back "
            f"(rc={proc.returncode})."
        )


def configure(keys_file=None, manifest=None) -> None:
    """Re-point the store and drop every cached value.

    The only supported way to move the store off its configured paths
    after import. Tests use it to keep the real keys file out of reach;
    passing None for either argument leaves that path as it is.
    """
    global KEYS_PATH, MANIFEST_PATH
    if keys_file is not None:
        KEYS_PATH = Path(keys_file).expanduser()
    if manifest is not None:
        MANIFEST_PATH = Path(manifest).expanduser()
    reset()


def reset() -> None:
    """Drop every cached value, source, parsed entry and protected name."""
    _values.clear()
    _sources.clear()
    _envfile.clear()
    _protected.clear()


def load() -> None:
    """Resolve all secrets and export non-secret config to os.environ.

    Call once at server startup. Raises MissingSecretError if a protected
    secret resolves nowhere. Prints a source report (names only) to stderr.
    """
    _envfile.clear()
    _envfile.update(_parse_env_file(keys_path()))
    _protected.clear()
    _protected.update(_read_manifest())

    for name, value in _envfile.items():
        if not is_secret_name(name) and value:
            os.environ.setdefault(name, value)

    # Unprotected secrets: the keys file is their home, no flag, no warning.
    for name, value in _envfile.items():
        if is_secret_name(name) and value and name not in _protected:
            _values[name], _sources[name] = value, "env"

    # Protected secrets: Keychain, with a flagged escape hatch.
    protected = sorted(_protected)
    if protected and _backend() != "envfile":
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            for n, v in zip(protected, ex.map(_keychain_read, protected)):
                if v:
                    _values[n], _sources[n] = v, "keychain"
    missing, env_used = [], []
    for n in protected:
        if _sources.get(n) == "keychain":
            continue
        v = os.environ.get(n) or _envfile.get(n)
        if v and (_env_allowed() or _backend() == "envfile"):
            _values[n], _sources[n] = v, "env"
            env_used.append(n)
        else:
            missing.append(n)
    if env_used:
        print(
            f"WARNING: {len(env_used)} protected secret(s) loaded from env "
            f"fallback instead of the Keychain: " + ", ".join(env_used),
            file=sys.stderr,
        )
    if missing:
        raise MissingSecretError(missing)
    _report()


def _report() -> None:
    """Report the SOURCE of each secret — names and sources only.

    A store holding nothing, with no manifest, reports nothing: a
    deployment with no keys is meant to be as quiet as it was before
    this module existed.
    """
    if not _sources and not _protected:
        return
    by_source: dict[str, list[str]] = {}
    for n, s in sorted(_sources.items()):
        by_source.setdefault(s, []).append(n)
    counts = ", ".join(f"{s} {len(ns)}" for s, ns in sorted(by_source.items()))
    print(
        f"Secrets: {len(_sources)} total — {counts or 'none'} "
        f"({len(_protected)} protected)",
        file=sys.stderr,
    )
    if not _protected:
        print(
            f"  note: no protected-secrets manifest at {_manifest_path()} — "
            f"every secret comes from {keys_path()}",
            file=sys.stderr,
        )
    for n in sorted(_protected):
        src = _sources.get(n, "missing")
        if src != "keychain" or os.environ.get("KAMI_SECRETS_VERBOSE") == "1":
            print(f"  [{src}] {n}", file=sys.stderr)


def known_names() -> set[str]:
    """Names of every secret this process can resolve.

    Everything load() resolved, plus — on the envfile backend — the
    secret-shaped names live in the process environment. The env scan is
    what makes a key exported into the environment (a deployment that
    sets one directly, and the test suite's synthetic accounts) load
    exactly as a keys-file entry does.
    """
    names = set(_values)
    if _backend() == "envfile":
        names |= {n for n in os.environ if is_secret_name(n)}
    return names


def get(name: str, required: bool = False) -> str | None:
    """Return a secret's value, or None. Never log the return value.

    Cached values from load() are returned directly. Unresolved protected
    names probe the Keychain (env fallback only with ALLOW_ENV_SECRETS=1);
    other names read from process env / the keys file.
    """
    v = _values.get(name)
    if v is not None:
        return v
    if _backend() == "envfile":
        v = os.environ.get(name) or _parse_env_file(keys_path()).get(name) or None
        if v:
            _values[name], _sources[name] = v, "env"
    elif is_protected(name):
        v = _keychain_read(name)
        if v:
            _values[name], _sources[name] = v, "keychain"
        elif _env_allowed():
            v = os.environ.get(name) or _envfile.get(name) or None
            if v:
                _values[name], _sources[name] = v, "env"
                print(
                    f"WARNING: protected secret '{name}' loaded from env "
                    f"fallback (ALLOW_ENV_SECRETS=1)",
                    file=sys.stderr,
                )
    else:
        v = os.environ.get(name) or _envfile.get(name) or None
        if v:
            _values[name], _sources[name] = v, "env"
    if v is None and required:
        raise MissingSecretError([name])
    return v


def put(name: str, value: str) -> None:
    """Persist a secret (create or replace) and cache it in-process.

    Protected names go to the Keychain; everything else to the keys file.
    To protect a NEW name, add it to the manifest before calling this.
    """
    if not value:
        raise ValueError(f"Refusing to store empty secret '{name}'.")
    if _backend() != "envfile" and is_protected(name):
        _keychain_write(name, value)
        _sources[name] = "keychain"
    else:
        from dotenv import set_key
        set_key(str(keys_path()), name, value)
        _envfile[name] = value
        _sources[name] = "env"
    _values[name] = value

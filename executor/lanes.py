"""Per-signer nonce lanes: the persistent ledger of what this harness signed.

One LANE per (chain id, signer address). Operator and owner wallets are
separate lanes because they are separate addresses; a deployment whose
owner and operator are the SAME address has one lane, because a chain
account has exactly one nonce sequence.

A lane holds:

* a re-entrant in-process lock plus an advisory file lock, so the send
  critical section (resolve, allocate, sign, write-ahead, broadcast,
  re-offer, fill) is exclusive across threads AND across server
  processes on this machine that share the state directory;
* a FLOOR: no nonce below it is ever handed out again. It rises with
  every accepted broadcast and every receipt this process observes, and
  it comes down only when the ledger PROVES the entries above it gone;
* a LEDGER of every transaction this harness signed whose fate is not
  yet known (mined, or proven not held by the node). An entry carries
  the signed raw bytes only while it is unresolved — a signed but
  unbroadcast transaction is a bearer instrument for its action — and
  the bytes are purged the moment the entry is resolved or released;
* TOMBSTONES: a released entry (proven not held, or never admitted)
  keeps nonce, hash, call, tool, step and signing time — never the raw
  bytes — until its nonce falls below the chain's latest count, so a
  late mining of it is attributable to this harness.

State file
----------
``$KAMI_LANE_DIR`` if set, else ``$XDG_STATE_HOME/kami-harness/lanes`` if
``XDG_STATE_HOME`` is set, else ``~/.kami-harness/lanes``. The directory
is created mode 0700, each file is written 0600, atomically (temp file,
fsync, rename). The location is independent of the secret backend: it
never reads or requires the keys file. One JSON file per lane,
``<chain_id>-<checksum address>.json``, beside a ``.lock`` file used for
the advisory lock. No key material is ever written.

On a filesystem that does not survive a restart (a container without a
volume) the ledger starts empty after every restart: the floor falls
back to the node's own ``pending`` count, and transactions signed by
the previous process are invisible to this one — the lane cannot
attribute a nonce they consume, and cannot drain a tail they left armed
behind a gap until a later send's nonce reaches it. Mount the state
directory on a volume to keep those guarantees across restarts.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

STATE_VERSION = 1

# Entry states.
SIGNED = "signed"        # written ahead of its broadcast
OFFERED = "offered"      # the node accepted it (or the outcome is unknown)
RELEASED = "released"    # tombstone: proven not held / never admitted


def default_dir() -> Path:
    """The lane state directory, resolved from the environment."""
    explicit = os.environ.get("KAMI_LANE_DIR", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    xdg = os.environ.get("XDG_STATE_HOME", "").strip()
    if xdg:
        return Path(xdg).expanduser() / "kami-harness" / "lanes"
    return Path.home() / ".kami-harness" / "lanes"


@dataclass
class Entry:
    nonce: int
    hash: str
    raw: str | None
    call: str
    tool: str
    step: int | None
    signed_at: float
    state: str = SIGNED
    evidence: str = ""
    kind: str = "action"     # "action" | "fill"

    def public(self) -> dict:
        """What a result may say about an entry (never the raw bytes)."""
        return {
            "tx_hash": self.hash, "nonce": self.nonce, "tool": self.tool,
            "step": self.step, "signed_at": round(self.signed_at, 3),
            "kind": self.kind,
        }


@dataclass
class Lane:
    chain_id: int
    address: str
    directory: Path
    floor: int = 0
    mined_top: int = -1      # highest nonce this harness saw mined
    entries: dict = field(default_factory=dict)   # hash -> Entry
    recent: list = field(default_factory=list)    # recently mined, in memory

    def __post_init__(self):
        self._lock = threading.RLock()
        self._depth = 0
        self._lock_fd = None
        self._warned = False
        self.load()

    # -- persistence ----------------------------------------------------

    @property
    def path(self) -> Path:
        return self.directory / f"{self.chain_id}-{self.address}.json"

    def _warn(self, what: str, err: Exception) -> None:
        if not self._warned:
            self._warned = True
            print(
                f"WARNING: lane state for {self.address} is in memory only "
                f"({what}: {type(err).__name__}: {err})",
                file=sys.stderr,
            )

    def _ensure_dir(self) -> bool:
        try:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self.directory, 0o700)
            return True
        except OSError as e:
            self._warn("cannot create the state directory", e)
            return False

    def load(self) -> None:
        try:
            data = json.loads(self.path.read_text())
        except FileNotFoundError:
            return
        except (OSError, ValueError) as e:
            self._warn("unreadable state file", e)
            return
        if data.get("version") != STATE_VERSION:
            return
        self.floor = int(data.get("floor", 0))
        self.mined_top = int(data.get("mined_top", -1))
        self.entries = {}
        for raw in data.get("entries", []):
            e = Entry(**raw)
            self.entries[e.hash] = e

    def save(self) -> None:
        if not self._ensure_dir():
            return
        data = {
            "version": STATE_VERSION,
            "chain_id": self.chain_id,
            "address": self.address,
            "floor": self.floor,
            "mined_top": self.mined_top,
            "entries": [asdict(e) for e in sorted(
                self.entries.values(), key=lambda e: (e.nonce, e.signed_at))],
        }
        tmp = self.path.with_suffix(f".tmp.{os.getpid()}.{threading.get_ident()}")
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, separators=(",", ":"))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except OSError as e:
            self._warn("cannot write the state file", e)
            with contextlib.suppress(OSError):
                os.unlink(tmp)

    @contextlib.contextmanager
    def critical(self):
        """The send critical section: thread lock, then the file lock.

        Re-entrant within a thread. The outermost entry reloads the
        file (another process may have written it) and the outermost
        exit saves it.
        """
        with self._lock:
            outer = self._depth == 0
            if outer:
                self._acquire_file_lock()
                self.load()
            self._depth += 1
            try:
                yield self
            finally:
                self._depth -= 1
                if outer:
                    self.save()
                    self._release_file_lock()

    def _acquire_file_lock(self) -> None:
        if not self._ensure_dir():
            return
        try:
            fd = os.open(self.path.with_suffix(".lock"),
                         os.O_RDWR | os.O_CREAT, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
            self._lock_fd = fd
        except OSError as e:
            self._warn("cannot take the file lock", e)
            self._lock_fd = None

    def _release_file_lock(self) -> None:
        if self._lock_fd is not None:
            with contextlib.suppress(OSError):
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                os.close(self._lock_fd)
            self._lock_fd = None

    # -- ledger ---------------------------------------------------------

    def add(self, nonce: int, tx_hash: str, raw: bytes, call: str, tool: str,
            step: int | None = None, kind: str = "action") -> Entry:
        if self.is_live_hash(tx_hash, nonce):
            raise ValueError(f"hash {tx_hash} is already in the ledger")
        e = Entry(nonce=nonce, hash=tx_hash, raw="0x" + bytes(raw).hex(),
                  call=call, tool=tool, step=step, signed_at=time.time(),
                  kind=kind)
        self.entries[tx_hash] = e
        return e

    def active(self) -> list[Entry]:
        return sorted((e for e in self.entries.values()
                       if e.state in (SIGNED, OFFERED)),
                      key=lambda e: e.nonce)

    def tombstones(self) -> list[Entry]:
        return sorted((e for e in self.entries.values()
                       if e.state == RELEASED), key=lambda e: e.nonce)

    def at_nonce(self, nonce: int) -> list[Entry]:
        return [e for e in self.entries.values() if e.nonce == nonce]

    def is_live_hash(self, tx_hash: str, nonce: int) -> bool:
        """These exact bytes were already handed out and not released.

        One hash implies one nonce, so the nonce is compared too: a
        signer that produced the same bytes at a DIFFERENT nonce is not
        a real signer, and must not wedge the lane.
        """
        e = self.entries.get(tx_hash)
        if e is not None and e.state != RELEASED and e.nonce == nonce:
            return True
        return any(r["hash"] == tx_hash and r["nonce"] == nonce
                   for r in self.recent)

    def offered(self, e: Entry) -> None:
        e.state = OFFERED
        self.floor = max(self.floor, e.nonce + 1)

    def mined(self, tx_hash: str, nonce: int | None = None) -> None:
        """The transaction has a receipt: final. Drop it from the ledger."""
        e = self.entries.pop(tx_hash, None)
        n = e.nonce if e is not None else nonce
        if n is None:
            return
        self.mined_top = max(self.mined_top, n)
        self.floor = max(self.floor, n + 1)
        self.recent.append({
            "hash": tx_hash, "nonce": n,
            "tool": e.tool if e else "", "step": e.step if e else None,
            "signed_at": e.signed_at if e else None,
            "kind": e.kind if e else "action",
        })
        del self.recent[:-256]

    def recent_at(self, nonce: int) -> dict | None:
        for r in reversed(self.recent):
            if r["nonce"] == nonce:
                return r
        return None

    def release(self, e: Entry, evidence: str) -> None:
        """Proven not held (or never admitted): keep a tombstone only."""
        e.state = RELEASED
        e.raw = None
        e.evidence = evidence[:300]

    def prune(self, e: Entry) -> None:
        self.entries.pop(e.hash, None)

    def recompute_floor(self) -> None:
        """Floor = above everything mined or still possibly held.

        Released entries do not hold the floor up, so a nonce proven
        free is handed out again — that is what keeps a dropped entry
        from leaving a permanent gap in front of every later send.
        """
        tops = [self.mined_top] + [e.nonce for e in self.active()]
        self.floor = max(tops) + 1 if tops else 0

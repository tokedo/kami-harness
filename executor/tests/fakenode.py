"""A hermetic EVM node for send-path tests.

A REAL `web3.Web3` object is built over `FakeNodeProvider`, so every
layer above the wire is the production code path: web3's request
encoding and error formatting, `build_transaction`, local signing with
eth_account, `send_raw_transaction`, `wait_for_transaction_receipt`'s
own polling loop, and contract ABI encoding/decoding. Only the node is
simulated, and it is simulated at the JSON-RPC level — it receives the
same request objects a real endpoint would, and answers with the same
shapes.

What the node models, and why each piece is here:

* A per-sender MEMPOOL that QUEUES a nonce above the sender's next
  expected one instead of refusing it. Pending count = latest count plus
  the CONTIGUOUS run of pooled nonces above it, so a transaction queued
  behind a gap is invisible to `eth_getTransactionCount(pending)`, and
  it mines the moment the gap nonce is filled — by anything.
* Instant inclusion: a transaction whose nonce is the sender's next
  expected one mines in a new block as soon as it is admitted, together
  with every queued transaction it releases.
* Deterministic signing on the client side means two sends of the same
  call at the same nonce with the same gas are BYTE-IDENTICAL and share
  one hash. A re-broadcast of a known hash returns that hash.
* A LAGGING REPLICA (`lag`): for the next k requests the sender's view
  is `behind` transactions old — `eth_getTransactionCount` answers the
  old count and `eth_sendRawTransaction` admits a stale nonce as if it
  were new (returning its hash). A stale-nonce transaction the canonical
  node already has (same hash) changes nothing; one it does not have is
  dropped on gossip and never mines.
* Injected FAULTS: the next k requests of a method answer a given
  JSON-RPC error object (e.g. the replica readiness error) instead.
* Contract HANDLERS keyed by (to address, 4-byte selector): each one
  executes a call against node state, with or without committing, and
  returns a status, gas and logs. `eth_call` and `eth_estimateGas` run a
  handler without committing; a mined transaction runs it committing.

Everything is in memory and deterministic. No network, no key that has
ever been funded anywhere: tests sign with the public local-dev keys in
conftest.
"""

from __future__ import annotations

import itertools
import json
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from types import SimpleNamespace

import time as _real_time

import rlp  # noqa: F401  (eth_account dependency; imported for clarity)
from eth_account import Account
from eth_account.typed_transactions import TypedTransaction
from eth_utils import keccak, to_checksum_address
from hexbytes import HexBytes
from web3 import Web3
from web3.providers.base import JSONBaseProvider

READINESS_ERROR = {
    "code": 5,
    "message": (
        "jsonrpc readiness error: failed to load state at height 33872790; "
        "historical version not ready: 33872790: invalid height (latest "
        "height: 33872790): invalid request"
    ),
}


def addr_for(name: str) -> str:
    """A deterministic contract address for a system/component id."""
    return to_checksum_address(keccak(text=name)[-20:])


def selector(signature: str) -> str:
    return "0x" + keccak(text=signature)[:4].hex()


SAFEGET = selector("safeGet(uint256)")


class VirtualClock:
    """A stand-in for the `time` module: sleeps advance a virtual clock.

    Installed into the modules whose waits matter (server, web3's
    Timeout), so a 120 s receipt budget costs no wall time and the test
    can still read exactly how long the code under test WOULD have
    waited. Anything else is delegated to the real module.
    """

    def __init__(self, start: float = 1_790_000_000.0):
        self.now = float(start)
        self.slept = 0.0
        self.on_sleep = []  # callables(now) run after each sleep

    def time(self) -> float:
        return self.now

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        seconds = max(0.0, float(seconds))
        self.now += seconds
        self.slept += seconds
        for hook in list(self.on_sleep):
            hook(self.now)

    def __getattr__(self, name):
        return getattr(_real_time, name)


@dataclass
class Tx:
    hash: str
    raw: bytes
    sender: str
    nonce: int
    to: str | None
    data: bytes
    value: int
    gas: int
    mined_block: int | None = None
    dropped: bool = False


@dataclass
class Fault:
    method: str
    times: int
    error: dict
    when: object = None  # callable(params) -> bool


@dataclass
class Lag:
    sender: str
    times: int
    behind: int


# What a game system's `executeTyped(...) returns (bytes)` answers.
EMPTY_BYTES_OUTPUT = bytes.fromhex(
    "0000000000000000000000000000000000000000000000000000000000000020"
    "0000000000000000000000000000000000000000000000000000000000000000"
)


@dataclass
class Result:
    status: int = 1
    gas_used: int = 50_000
    logs: list = field(default_factory=list)
    revert: str | None = None
    output: bytes = EMPTY_BYTES_OUTPUT


class FakeNode:
    def __init__(self, chain_id: int):
        self.chain_id = chain_id
        self.block = 1_000
        self.latest = defaultdict(int)        # sender -> mined count
        self.pool = defaultdict(dict)         # sender -> {nonce: Tx}
        self.txs: dict[str, Tx] = {}          # hash -> Tx (known to node)
        self.receipts: dict[str, dict] = {}   # hash -> receipt json
        self.by_nonce = defaultdict(dict)     # sender -> {nonce: hash} mined
        self.handlers: dict[tuple[str, str], object] = {}
        self.faults: list[Fault] = []
        self.lags: list[Lag] = []
        self.requests: list[tuple[str, list]] = []  # every request served
        self.sends: list[tuple[str, int, str]] = []  # (sender, nonce, hash) admitted
        self.executed: list[Tx] = []          # mined, in order
        self.blocks: dict[int, list[Tx]] = defaultdict(list)
        # Replicas behind a load balancer. A SESSION (one connection) is
        # pinned to one replica. A replica can be BLIND to hashes (it
        # answers null for their receipt and transaction — the endpoint's
        # observed inconsistency) and BEHIND (its head and its count lag).
        self.replicas: dict[str, dict] = {
            "primary": {"blind": set(), "behind": 0, "count_behind": 0}}
        self.session_replica: dict[int, str] = {0: "primary"}
        self.fresh_route = lambda sid: "primary"
        self.sessions_opened: list[tuple[int, str, float]] = []
        self.lookups: list[tuple[int, str, str, float]] = []
        self.clock = None
        self.hold_mining = False
        self._sid = itertools.count(1)
        self._tls = threading.local()

    # -- configuration ------------------------------------------------------

    def handle(self, to: str, signature: str, fn) -> None:
        """Install fn(node, tx_like, args_bytes, commit) -> Result."""
        self.handlers[(to.lower(), selector(signature))] = fn

    def fail(self, method: str, times: int = 1, error: dict | None = None,
             when=None) -> None:
        self.faults.append(Fault(method, times, dict(error or READINESS_ERROR),
                                 when))

    def lag(self, sender: str, times: int = 1, behind: int = 1) -> None:
        self.lags.append(Lag(sender.lower(), times, behind))

    def set_nonce(self, sender: str, count: int) -> None:
        self.latest[sender.lower()] = count

    # -- views --------------------------------------------------------------

    def pending_count(self, sender: str) -> int:
        s = sender.lower()
        n = self.latest[s]
        while n in self.pool[s]:
            n += 1
        return n

    def queued(self, sender: str) -> list[int]:
        """Nonces pooled ABOVE the contiguous run: armed behind a gap."""
        s = sender.lower()
        p = self.pending_count(s)
        return sorted(n for n in self.pool[s] if n >= p)

    # -- the JSON-RPC surface ----------------------------------------------

    def _fault_for(self, method: str, params) -> dict | None:
        for f in self.faults:
            if f.method == method and f.times > 0 and (
                f.when is None or f.when(params)
            ):
                f.times -= 1
                return f.error
        return None

    def _lag_for(self, sender: str) -> Lag | None:
        for lg in self.lags:
            if lg.sender == sender.lower() and lg.times > 0:
                return lg
        return None

    def replica(self, name: str, blind=(), behind: int = 0,
                count_behind: int = 0, blind_once=(), blind_all=False) -> None:
        """blind: hashes it never sees; blind_once: hashes it answers null
        for ONCE (then correctly); blind_all: it sees no hash at all."""
        self.replicas[name] = {
            "blind": set(blind), "behind": behind,
            "count_behind": count_behind,
            "blind_once": {h.lower(): 1 for h in blind_once},
            "blind_all": blind_all,
        }

    def _now(self) -> float:
        return self.clock.now if self.clock is not None else 0.0

    def rpc(self, request: dict) -> dict:
        method = request["method"]
        params = request.get("params") or []
        rid = request.get("id")
        self.requests.append((method, params))
        err = self._fault_for(method, params)
        if err is not None:
            return {"jsonrpc": "2.0", "id": rid, "error": dict(err)}
        sid = getattr(self._tls, "session", 0)
        rep = self.replicas[self.session_replica.get(sid, "primary")]
        if method in ("eth_getTransactionReceipt", "eth_getTransactionByHash"):
            h = str(params[0]).lower()
            self.lookups.append((sid, method, h, self._now()))
            once = rep.get("blind_once", {})
            if once.get(h, 0) > 0:
                if method == "eth_getTransactionByHash":
                    once[h] -= 1          # one null answer for the pair
                return {"jsonrpc": "2.0", "id": rid, "result": None}
            if rep.get("blind_all") or h in rep["blind"]:
                return {"jsonrpc": "2.0", "id": rid, "result": None}
        if method == "eth_blockNumber" and rep["behind"]:
            return {"jsonrpc": "2.0", "id": rid,
                    "result": hex(max(0, self.block - rep["behind"]))}
        if method == "eth_getTransactionCount" and rep["count_behind"]:
            real = int(self._eth_getTransactionCount(*params), 16)
            return {"jsonrpc": "2.0", "id": rid,
                    "result": hex(max(0, real - rep["count_behind"]))}
        try:
            result = getattr(self, "_" + method)(*params)
        except _RpcError as e:
            return {"jsonrpc": "2.0", "id": rid, "error": e.payload}
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    def _eth_chainId(self):
        return hex(self.chain_id)

    def _eth_blockNumber(self):
        return hex(self.block)

    def _eth_gasPrice(self):
        return hex(2_500_000)

    def _eth_getBalance(self, addr, block="latest"):
        return hex(10 ** 20)

    def _eth_getCode(self, addr, block="latest"):
        return "0x6080"

    def _eth_getTransactionCount(self, addr, block="latest"):
        s = addr.lower()
        count = self.pending_count(s) if block == "pending" else self.latest[s]
        lg = self._lag_for(s)
        if lg is not None:
            lg.times -= 1
            count = max(0, count - lg.behind)
        return hex(count)

    def _eth_call(self, call, block="latest"):
        res = self._run(call, commit=False)
        if res.status != 1:
            raise _RpcError(_revert_payload(res.revert))
        return "0x" + res.output.hex()

    def _eth_estimateGas(self, call, block=None):
        res = self._run(call, commit=False)
        if res.status != 1:
            raise _RpcError(_revert_payload(res.revert))
        return hex(res.gas_used)

    def _eth_sendRawTransaction(self, raw_hex):
        raw = bytes.fromhex(raw_hex[2:])
        h = "0x" + keccak(raw).hex()
        if h in self.txs:
            # A known transaction re-offered: same bytes, same hash.
            return h
        typed = TypedTransaction.from_bytes(HexBytes(raw)).as_dict()
        sender = Account.recover_transaction(raw).lower()
        nonce = int(typed["nonce"])
        to = typed.get("to")
        to = ("0x" + bytes(to).hex()) if to else None
        tx = Tx(h, raw, sender, nonce, to, bytes(typed.get("data") or b""),
                int(typed.get("value") or 0), int(typed["gas"]))
        lg = self._lag_for(sender)
        if lg is not None:
            lg.times -= 1
            stale_floor = max(0, self.pending_count(sender) - lg.behind)
            if nonce < self.latest[sender] and nonce >= stale_floor:
                # A lagging replica admits a nonce the chain has already
                # used. It answers with the hash; gossip drops it.
                tx.dropped = True
                self.txs[h] = tx
                self.sends.append((sender, nonce, h))
                return h
        if nonce < self.latest[sender]:
            raise _RpcError({
                "code": -32000,
                "message": (
                    f"account sequence mismatch, expected "
                    f"{self.latest[sender]}, got {nonce}: incorrect "
                    f"account sequence"
                ),
            })
        if nonce in self.pool[sender]:
            raise _RpcError({
                "code": -32000,
                "message": "tx with the same nonce already in mempool",
            })
        self.pool[sender][nonce] = tx
        self.txs[h] = tx
        self.sends.append((sender, nonce, h))
        self._mine()
        return h

    def _eth_getBlockByNumber(self, number, full=False):
        n = self.block if number in ("latest", "pending") else int(number, 16)
        txs = [
            self._eth_getTransactionByHash(t.hash) if full else t.hash
            for t in self.blocks.get(n, [])
        ]
        return {"number": hex(n), "hash": _bh(n), "transactions": txs,
                "timestamp": hex(int(self._now()))}

    def _eth_getTransactionReceipt(self, h):
        return self.receipts.get(h.lower())

    def _eth_getTransactionByHash(self, h):
        tx = self.txs.get(h.lower())
        if tx is None or tx.dropped:
            return None
        return {
            "hash": tx.hash, "nonce": hex(tx.nonce), "from": tx.sender,
            "to": tx.to, "value": hex(tx.value), "gas": hex(tx.gas),
            "input": "0x" + tx.data.hex(),
            "blockNumber": None if tx.mined_block is None else hex(tx.mined_block),
            "blockHash": None if tx.mined_block is None else _bh(tx.mined_block),
            "transactionIndex": None if tx.mined_block is None else "0x0",
            "type": "0x2", "chainId": hex(self.chain_id),
            "maxFeePerGas": hex(2_500_000), "maxPriorityFeePerGas": "0x0",
            "v": "0x0", "r": "0x0", "s": "0x0", "accessList": [],
        }

    # -- mining -------------------------------------------------------------

    def release_mining(self) -> None:
        self.hold_mining = False
        self._mine()

    def _mine(self) -> None:
        if self.hold_mining:
            return
        mined_any = False
        for sender in list(self.pool):
            while self.latest[sender] in self.pool[sender]:
                if not mined_any:
                    self.block += 1
                    mined_any = True
                tx = self.pool[sender].pop(self.latest[sender])
                self.latest[sender] += 1
                self._execute(tx)

    def _execute(self, tx: Tx) -> None:
        res = self._run(
            {"from": tx.sender, "to": tx.to, "data": "0x" + tx.data.hex(),
             "value": hex(tx.value)},
            commit=True,
        )
        tx.mined_block = self.block
        self.by_nonce[tx.sender][tx.nonce] = tx.hash
        self.executed.append(tx)
        self.blocks[self.block].append(tx)
        logs = []
        for i, (address, topics, data) in enumerate(res.logs):
            logs.append({
                "address": address, "topics": topics,
                "data": "0x" + data.hex(), "blockNumber": hex(self.block),
                "blockHash": _bh(self.block), "transactionHash": tx.hash,
                "transactionIndex": "0x0", "logIndex": hex(i),
                "removed": False,
            })
        gas_used = min(res.gas_used, tx.gas)
        self.receipts[tx.hash] = {
            "transactionHash": tx.hash, "blockNumber": hex(self.block),
            "blockHash": _bh(self.block), "transactionIndex": "0x0",
            "from": tx.sender, "to": tx.to, "status": hex(res.status),
            "gasUsed": hex(gas_used), "cumulativeGasUsed": hex(gas_used),
            "effectiveGasPrice": hex(2_500_000), "contractAddress": None,
            "logs": logs, "logsBloom": "0x" + "00" * 256, "type": "0x2",
        }

    def _run(self, call: dict, commit: bool) -> Result:
        to = (call.get("to") or "").lower()
        data = call.get("data") or call.get("input") or "0x"
        data = bytes.fromhex(data[2:]) if isinstance(data, str) else bytes(data)
        if not data:
            return Result(gas_used=113_251)  # a plain value transfer
        sel = "0x" + data[:4].hex()
        fn = self.handlers.get((to, sel))
        if fn is None:
            if sel == SAFEGET:
                # A component this test did not model: refuse, so the
                # product's own fallback read (which the test fakes)
                # answers instead of a fabricated zero.
                return Result(status=0, revert="component not modelled")
            return Result()
        caller = SimpleNamespace(sender=(call.get("from") or "").lower())
        return fn(self, caller, data[4:], commit)


class _RpcError(Exception):
    def __init__(self, payload: dict):
        super().__init__(payload.get("message"))
        self.payload = payload


def _revert_payload(reason: str | None) -> dict:
    import eth_abi
    data = "0x08c379a0" + eth_abi.encode(["string"], [reason or ""]).hex()
    return {"code": 3, "message": f"execution reverted: {reason or ''}",
            "data": data}


def _bh(block: int) -> str:
    return "0x" + keccak(block.to_bytes(8, "big")).hex()


class FakeNodeProvider(JSONBaseProvider):
    """JSON-RPC over a FakeNode, through web3's own encoder/decoder.

    `make_batch_request` takes the same [(method, params)] list the
    product hands HTTPProvider, stamps ids from `request_counter` exactly
    as HTTPProvider does, and answers an array.
    """

    def __init__(self, node: FakeNode, session: int = 0, batches=None):
        super().__init__()
        self.node = node
        self.session = session
        self.request_counter = itertools.count()
        self.batches: list[list[str]] = [] if batches is None else batches

    def fresh_session(self) -> "FakeNodeProvider":
        """A new connection: the load balancer routes it to a replica."""
        sid = next(self.node._sid)
        self.node.session_replica[sid] = self.node.fresh_route(sid)
        self.node.sessions_opened.append(
            (sid, self.node.session_replica[sid], self.node._now()))
        return FakeNodeProvider(self.node, sid, self.batches)

    def _on_session(self, fn):
        prior = getattr(self.node._tls, "session", 0)
        self.node._tls.session = self.session
        try:
            return fn()
        finally:
            self.node._tls.session = prior

    def make_request(self, method, params):
        body = json.loads(self.encode_rpc_request(method, params))
        return self._on_session(lambda: self.node.rpc(body))

    def make_batch_request(self, requests):
        body = json.loads(self.encode_batch_rpc_request(requests))
        self.batches.append([r["method"] for r in body])
        return self._on_session(lambda: [self.node.rpc(r) for r in body])

    def is_connected(self, show_traceback: bool = False) -> bool:
        return True


def make_w3(node: FakeNode) -> Web3:
    return Web3(FakeNodeProvider(node))

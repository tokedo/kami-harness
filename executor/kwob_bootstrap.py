"""One-time KWOB trade-ID bootstrap from the Kamigaze state snapshot service.

Why this exists: the public Yominet RPC is a pruned node (~1M blocks of
history). `get_item_orderbook` discovers trade entities from World
`ComponentValueSet` logs, so trades created before the prune horizon are
invisible to the log scan. The game client never notices because it
bootstraps full ECS state from Kamigaze — this script does the same thing
for the one component we care about and persists the result:

    executor/.cache/kwob_trades.json
      {"block": <kamigaze state block>, "trade_ids": ["0x..", ...]}

The MCP server unions this file with its incremental log scan. Re-run the
script only if the cache file is lost or `get_item_orderbook` raises a
staleness error (tool not called for longer than the RPC prune window).

Usage: python3 kwob_bootstrap.py
"""

import json
import struct
from pathlib import Path

import httpx

KAMIGAZE_URL = "https://api.prod.kamigotchi.io"
CACHE_FILE = Path(__file__).parent / ".cache" / "kwob_trades.json"

_HDRS = {
    "Content-Type": "application/grpc-web+proto",
    "Accept": "application/grpc-web+proto",
    "X-Grpc-Web": "1",
}


def _keccak_component_id() -> bytes:
    from eth_utils import keccak

    return keccak(text="component.id.trade.owns")


def _read_varint(data: bytes, off: int):
    result, shift = 0, 0
    while off < len(data):
        b = data[off]
        off += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, off
        shift += 7
    return result, off


def _walk_fields(data: bytes):
    """Yield (field_num, wire_type, value) for a protobuf message."""
    off = 0
    while off < len(data):
        tag, off = _read_varint(data, off)
        fnum, wt = tag >> 3, tag & 7
        if wt == 0:
            val, off = _read_varint(data, off)
        elif wt == 2:
            ln, off = _read_varint(data, off)
            val = data[off : off + ln]
            off += ln
        elif wt == 5:
            val = data[off : off + 4]
            off += 4
        elif wt == 1:
            val = data[off : off + 8]
            off += 8
        else:
            raise ValueError(f"unsupported wire type {wt}")
        yield fnum, wt, val


def _stream_grpc(method: str, body: bytes = b""):
    """Yield each data-frame payload of a (possibly streaming) gRPC-Web call."""
    frame = b"\x00" + struct.pack(">I", len(body)) + body
    with httpx.stream(
        "POST", f"{KAMIGAZE_URL}/{method}", content=frame, headers=_HDRS, timeout=300
    ) as r:
        r.raise_for_status()
        buf = b""
        for chunk in r.iter_bytes():
            buf += chunk
            while len(buf) >= 5:
                ft = buf[0]
                ln = struct.unpack(">I", buf[1:5])[0]
                if len(buf) < 5 + ln:
                    break
                payload = buf[5 : 5 + ln]
                buf = buf[5 + ln :]
                if ft == 0:
                    yield payload


def main() -> None:
    target_id = _keccak_component_id()
    print(f"target component: 0x{target_id.hex()} (component.id.trade.owns)")

    # 1. components: idx <-> 32-byte component ID
    target_idx = None
    n_components = 0
    for payload in _stream_grpc("kamigaze.KamigazeService/GetComponents"):
        for fnum, _, val in _walk_fields(payload):
            if fnum != 1 or not isinstance(val, bytes):
                continue
            n_components += 1
            idx, cid = 0, b""
            for f2, _, v2 in _walk_fields(val):
                if f2 == 1:
                    idx = v2
                elif f2 == 2:
                    cid = v2
            if cid == target_id:
                target_idx = idx
    if target_idx is None:
        raise SystemExit(
            f"IDOwnsTradeComponent not found among {n_components} components"
        )
    print(f"components: {n_components}, owns-trade idx: {target_idx}")

    # 2. state: collect entity idxs having the owns-trade component
    wanted_entity_idxs: set[int] = set()
    state_block = 0
    n_state = 0
    for payload in _stream_grpc("kamigaze.KamigazeService/GetState"):
        for fnum, wt, val in _walk_fields(payload):
            if fnum == 1 and wt == 2:
                n_state += 1
                packed = 0
                for f2, _, v2 in _walk_fields(val):
                    if f2 == 1:
                        packed = v2
                if (packed >> 24) == target_idx:
                    wanted_entity_idxs.add(packed & 0xFFFFFF)
            elif fnum == 3 and wt == 0:
                state_block = max(state_block, val)
    print(
        f"state entries: {n_state:,}, owns-trade entries: {len(wanted_entity_idxs)}, "
        f"state block: {state_block:,}"
    )

    # 3. entities: resolve wanted idxs -> 32-byte entity IDs
    trade_ids: list[str] = []
    n_entities = 0
    for payload in _stream_grpc("kamigaze.KamigazeService/GetEntities"):
        for fnum, _, val in _walk_fields(payload):
            if fnum != 1 or not isinstance(val, bytes):
                continue
            n_entities += 1
            idx, eid = 0, b""
            for f2, _, v2 in _walk_fields(val):
                if f2 == 1:
                    idx = v2
                elif f2 == 2:
                    eid = v2
            if idx in wanted_entity_idxs:
                trade_ids.append("0x" + eid.hex())
    print(f"entities: {n_entities:,}, trade entity IDs resolved: {len(trade_ids)}")
    if len(trade_ids) != len(wanted_entity_idxs):
        print("WARNING: some entity idxs were not resolved")

    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(
        json.dumps({"block": state_block, "trade_ids": sorted(trade_ids)}, indent=0)
    )
    print(f"wrote {CACHE_FILE} ({len(trade_ids)} trades @ block {state_block:,})")


if __name__ == "__main__":
    main()

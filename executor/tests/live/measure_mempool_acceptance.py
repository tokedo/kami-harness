#!/usr/bin/env python3
"""Measure the node's per-sender mempool acceptance. LIVE. SPENDS GAS.

Not a tool and not on the MCP surface: a measurement script, kept beside
the suite because it drives the SAME internals the surface does — the
sign / batch-broadcast / collect path of `act_sequence` — with only the
step cap bypassed in this process.

Why it exists (HARNESS_360 brief, ask 1): 3.5.0's step cap of 16 is an
operator ruling, not a chain fact, and Anatoly re-rules it to the
MEASURED number. The play sessions established that 16 consecutive
nonces from one sender are accepted every time (10 bursts, 0
rejections), that four of one sender's nonces land in a single block,
and that the block gas limit is 45,000,000. What nobody has measured is
where acceptance STOPS: the CometBFT / minievm mempool's per-sender
limit is not readable over RPC, so the only way to know it is to offer
the node a longer run of nonces and watch.

The ladder is FEED-ONLY on purpose. A feed is the cheapest step that
still consumes a nonce (~1.98M gas), it needs no victim and no harvest,
and a reverted feed consumes no item, so a rejected or reverted rung
costs gas and nothing else. Mempool acceptance is a BROADCAST property:
a step that reverts on execution was still accepted, and the table says
so.

WHICH ITEM IS AN ARGUMENT, AND IT IS REQUIRED (3.7.0, ITEM 3). The
measurement items are **Ghost Gum 11301** and **Golden Apple 11313** —
cheap, plentiful, and not the input any play session is short of.
**Energy Drink 11409 is the expensive input of the liquidation play**
and the 2026-08-28 drink ladder spent 148 of them; the script now
refuses 11409 unless `--allow-drinks` says the operator meant it. There
is no default: a measurement that does not say what it burns is a
measurement nobody agreed to.

    KAMI_SECRETS_BACKEND=keychain \\
    KAMI_KEYS_FILE=~/.blocklife-keys/hybrid.env \\
    python3 measure_mempool_acceptance.py --item 11301 --sizes 8 32

Safety rails, all hard:
  * `--budget` items total across every rung (successful feeds only;
    a revert consumes gas, not an item). The ladder stops rather than
    exceed it.
  * The ladder stops if a rung still has unconfirmed transactions
    UNCONFIRMED_STOP_S after its broadcast. It REPORTS them and never
    resends.
  * If a rung is rejected, one extra rung runs at the largest accepted
    size + BRACKET_STEP, to bracket the limit — budget permitting.
  * `_ACT_SEQUENCE_MAX_STEPS` is raised on the imported MODULE OBJECT
    for this process only. The source constant is not touched: it is an
    operator ruling and this script is what the operator rules on.
"""

import argparse
import json
import time
from pathlib import Path

import server

# The measurement items. Cheap, plentiful, and not the play's bottleneck.
GHOST_GUM = 11301
GOLDEN_APPLE = 11313
ENERGY_DRINK = 11409     # the play's expensive input — never a default
KAMI_ID = 12649
ACCOUNT = "shrike"
DEFAULT_BUDGET = 40
UNCONFIRMED_STOP_S = 180
BRACKET_STEP = 8


class RefusedItem(SystemExit):
    """The script refused to burn the item it was pointed at."""


def check_item(item_id: int, allow_drinks: bool) -> int:
    """ITEM 3, made structural: the item is chosen, never defaulted.

    Ghost Gum and Golden Apple are the measurement items. Energy Drink
    is the liquidation play's expensive input and takes an explicit
    --allow-drinks; anything else is allowed but named in the output, so
    the record says what was burnt.
    """
    if item_id == ENERGY_DRINK and not allow_drinks:
        raise RefusedItem(
            f"refusing item {ENERGY_DRINK} (Energy Drink): it is the "
            f"expensive input of the liquidation play. Measure with Ghost "
            f"Gum {GHOST_GUM} or Golden Apple {GOLDEN_APPLE}, or pass "
            f"--allow-drinks if you mean it."
        )
    if item_id not in (GHOST_GUM, GOLDEN_APPLE):
        print(f"NOTE: item {item_id} is not one of the measurement items "
              f"(Ghost Gum {GHOST_GUM} / Golden Apple {GOLDEN_APPLE}).")
    return item_id


def txpool_status():
    """pending / queued as the node reports them, decoded to ints."""
    try:
        raw = server.w3.provider.make_request("txpool_status", [])["result"]
        return {k: int(v, 16) for k, v in raw.items()}
    except Exception as e:  # a node that does not serve it says so
        return {"error": f"{type(e).__name__}: {e}"}


def nonces(addr):
    return {
        "latest": server.w3.eth.get_transaction_count(addr, "latest"),
        "pending": server.w3.eth.get_transaction_count(addr, "pending"),
    }


def run_rung(size, operator_addr, item_id, kami_id):
    """One rung: `size` consecutive feed steps in one act_sequence call."""
    record = {
        "steps_requested": size,
        "before": {"txpool": txpool_status(), "nonces": nonces(operator_addr)},
    }
    captured = {}

    original_broadcast = server._seq_broadcast
    original_await = server._await_receipt

    def broadcast(pending, operator_addr=None):
        captured.setdefault("raws", [signed.raw_transaction
                                     for _j, _b, signed in pending])
        captured.setdefault("first_nonce", pending[0][1]["nonce"])
        t0 = time.monotonic()
        mode, outcomes = original_broadcast(pending, operator_addr)
        t1 = time.monotonic()
        captured.setdefault("calls", []).append({
            "items": len(pending),
            "mode": mode,
            "seconds": round(t1 - t0, 3),
        })
        captured.setdefault("outcomes", []).append([
            {"step": j, "nonce": pending[k][1]["nonce"], "accepted": ok,
             "text": None if ok else text}
            for k, (j, ok, text) in enumerate(outcomes)
        ])
        # The node's own view of the pool the instant the tail is in it.
        captured.setdefault("txpool_after_broadcast", txpool_status())
        captured["broadcast_ended"] = time.time()
        captured["deadline"] = t1 + UNCONFIRMED_STOP_S
        return mode, outcomes

    def await_receipt(tx_hash, built, timeout, account=None, ceiling_key=None):
        """The suite's receipt wait, bounded by the rung's 180 s rule."""
        left = captured.get("deadline", time.monotonic() + timeout)
        return original_await(
            tx_hash, built,
            timeout=max(1, int(min(timeout, left - time.monotonic()))),
            account=account, ceiling_key=ceiling_key,
        )

    server._seq_broadcast = broadcast
    server._await_receipt = await_receipt
    steps = [{"op": "feed", "kami_id": kami_id, "item_id": item_id}] * size
    t_call = time.time()
    try:
        result = server.act_sequence(steps, account=ACCOUNT)
    except Exception as e:
        result = {"error": f"{type(e).__name__}: {e}", "steps": []}
    finally:
        server._seq_broadcast = original_broadcast
        server._await_receipt = original_await
    t_done = time.time()

    rows = result.get("steps", [])
    blocks = sorted({r["block"] for r in rows if "block" in r})
    statuses = {}
    for r in rows:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
    rejected = [
        item for call in captured.get("outcomes", []) for item in call
        if not item["accepted"]
    ]
    record.update({
        "first_nonce": captured.get("first_nonce"),
        "broadcast_calls": captured.get("calls", []),
        "accepted": sum(
            1 for call in captured.get("outcomes", []) for i in call
            if i["accepted"]
        ),
        "rejected": rejected,
        "first_rejected_nonce": rejected[0]["nonce"] if rejected else None,
        "txpool_after_broadcast": captured.get("txpool_after_broadcast"),
        "status_counts": statuses,
        "blocks": {
            "first": blocks[0] if blocks else None,
            "last": blocks[-1] if blocks else None,
            "spanned": (blocks[-1] - blocks[0] + 1) if blocks else None,
            "distinct": len(blocks),
        },
        "gas_used_total": sum(r.get("gas_used", 0) for r in rows),
        "seconds_broadcast_to_last_receipt": round(
            t_done - captured.get("broadcast_ended", t_call), 2
        ),
        "seconds_whole_call": round(t_done - t_call, 2),
        "after": {"txpool": txpool_status(), "nonces": nonces(operator_addr)},
        "landed": result.get("landed"),
        "error": result.get("error"),
        "rows": rows,
    })

    # Transport-only timing at the same batch size, at zero cost: the
    # SAME raw transactions re-offered once they are already mined. The
    # node answers every item with an error, so nothing is spent and
    # nothing is sent; only the round-trip is measured. Reported apart
    # from the acceptance timings, never mixed into them.
    raws = captured.get("raws") or []
    for width in (16, 32):
        if len(raws) >= width:
            t0 = time.monotonic()
            try:
                server._seq_batch_send(
                    [(i, 10_000_000 + i, raws[i]) for i in range(width)]
                )
                ok = True
            except Exception:
                ok = False
            record.setdefault("replay_transport_seconds", {})[width] = {
                "seconds": round(time.monotonic() - t0, 3), "answered": ok,
            }
    return record


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--item", type=int, required=True,
        help=f"item index to feed. The measurement items are Ghost Gum "
             f"{GHOST_GUM} and Golden Apple {GOLDEN_APPLE}. There is no "
             f"default and Energy Drink {ENERGY_DRINK} is refused "
             f"without --allow-drinks.",
    )
    ap.add_argument("--allow-drinks", action="store_true",
                    help=f"permit item {ENERGY_DRINK} (Energy Drink), the "
                         f"expensive input of the liquidation play")
    ap.add_argument("--kami", type=int, default=KAMI_ID)
    ap.add_argument("--account", default=ACCOUNT)
    ap.add_argument("--budget", type=int, default=DEFAULT_BUDGET,
                    help="hard cap on items consumed across every rung")
    ap.add_argument("--sizes", type=int, nargs="+", default=[8, 32])
    ap.add_argument("--out", default="mempool-acceptance.json")
    args = ap.parse_args()
    check_item(args.item, args.allow_drinks)

    account, item_id, budget = args.account, args.item, args.budget
    acct = server._get_account(account)
    aid = server._require_registered_operator(account)
    held = server._inventory_balance(aid, item_id)
    print(f"account {account} holds {held} of item {item_id}; "
          f"budget {budget}")

    spent = 0
    records = []
    queue = list(args.sizes)
    largest_accepted = 0
    bracketed = False
    while queue:
        size = queue.pop(0)
        if spent + size > budget:
            print(f"STOP: rung {size} would take the total to "
                  f"{spent + size} > {budget}")
            break
        # Raised on the module object for THIS PROCESS. The source
        # constant is an operator ruling and is not touched.
        server._ACT_SEQUENCE_MAX_STEPS = max(size, 16)
        print(f"--- rung {size} (spent {spent}) ---", flush=True)
        rec = run_rung(size, acct.operator_addr, item_id, args.kami)
        records.append(rec)
        spent += rec["status_counts"].get("success", 0)
        print(json.dumps({k: v for k, v in rec.items() if k != "rows"},
                         indent=1), flush=True)

        if rec["rejected"]:
            if not bracketed and largest_accepted:
                bracketed = True
                bracket = largest_accepted + BRACKET_STEP
                print(f"rejected at {size}; bracketing at {bracket}")
                queue = [bracket]
                continue
            break
        largest_accepted = max(largest_accepted, rec["accepted"])
        if rec["status_counts"].get("unconfirmed"):
            print(f"STOP: rung {size} left "
                  f"{rec['status_counts']['unconfirmed']} unconfirmed after "
                  f"{UNCONFIRMED_STOP_S}s — reported, not resent")
            break

    Path(args.out).write_text(json.dumps(records, indent=1))
    print(f"wrote {args.out}; item {item_id} consumed {spent}")


if __name__ == "__main__":
    main()

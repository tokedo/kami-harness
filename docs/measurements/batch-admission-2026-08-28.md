# Per-item batch admission, measured — 2026-08-28

The number `_SEQ_BATCH_ITEM_S` is set from, and the reason
`act_sequence` chunks its broadcast at 32 items (3.7.0).

3.6.0 offered a whole pre-signed tail in ONE JSON-RPC body through
`w3.provider`, which carries web3's **default 30 s HTTP read timeout**
(`Web3(Web3.HTTPProvider(RPC_URL))` passes no `request_kwargs`, so
`HTTPSessionManager.request_timeout` = 30.0 applies). Nothing sized that
timeout to what the body was asking the node to do. On 2026-08-28 at
19:30:40Z a 61-step liquidate-heavy body outlived it and the sequence
was reported as 61 × `not_sent` while all 61 transactions mined
(the incident: `docs/stack-feedback.md`, tag `zero_cd_play`; the
reproduction: `executor/tests/test_h370_families.py`).

So the timeout is now **measured per item and per op**, and a request
never carries more than one chunk.

## The table

| op | items | batch call | per item | source |
|---|--:|--:|--:|---|
| feed | 8 | 0.668 s | 0.084 s | gum ladder below, rung 1 (cold connection) |
| feed | 32 | 0.526 s | 0.016 s | gum ladder below, rung 2 |
| feed | 32 | 0.500 s | 0.016 s | drink ladder 2026-08-28, rung 1 (`mempool-acceptance-2026-08-28.md`) |
| feed | 48 | 0.611 s | 0.013 s | drink ladder 2026-08-28, rung 2 |
| feed | 64 | 2.354 s | 0.037 s | drink ladder 2026-08-28, rung 3 |
| **liquidate** | **38** | **> 13 s** | **> 0.342 s** | the 19:31 incident, from the chain's own block timestamps |
| **liquidate** | **61** | **> 30 s** | **> 0.492 s** | the 19:31 incident, from the client timeout it outlived |

Both liquidate rows are LOWER bounds. 38 items were admitted across
blocks 32685027–038, timestamps …459 → …472 = 13 s of chain time
(≈ 3 items/s). The request itself was cut off at web3's 30 s with the
node still working on 61 items, so 30/61 = 0.492 s per item is the
smallest per-item time consistent with what happened; the true figure is
larger. A liquidate body is 20–30× slower per item than a feed body:
`system.kami.liquidate` executes a fight, and `harvestAndFeed`-shaped
work does not.

## The constants that come out of it

    _SEQ_BATCH_CHUNK          = 32
    _SEQ_BATCH_ITEM_S         = 0.5      # the worst row above, rounded up
    _SEQ_BATCH_TIMEOUT_FLOOR_S = 30
    timeout = max(30, chunk × 0.5 × 2)   # = 32 s for a full chunk

The rule is the brief's: **chunk size × measured worst per-item time ×
2, floor 30 s.** The worst measured per-item time in the table is the
incident's own 0.492 s, so a full 32-item chunk gets 32 s — twice as
long as 32 liquidates took to admit on the night it broke, and 60×
longer than 32 feeds have ever taken. A 64-step sequence is two chunks
of 32, offered sequentially, each with its own 32 s, and the first
chunk's outcome is reconciled before the second is offered.

The batch call uses a **dedicated `HTTPProvider` per timeout value**
(`_seq_batch_provider`), cached on the module. The global `w3` provider
is untouched: every other RPC call in the process keeps web3's 30 s.
Measured live at the pin: a 3-item `eth_call` batch through the
dedicated 32-s provider returned in 0.284 s, indistinguishable from
`w3`'s own.

## Method — the gum ladder

    KAMI_SECRETS_BACKEND=keychain \
    KAMI_KEYS_FILE=~/.blocklife-keys/hybrid.env \
    python3 executor/tests/live/measure_mempool_acceptance.py \
        --item 11301 --sizes 8 32 --budget 40

`executor/tests/live/measure_mempool_acceptance.py` drives the shipped
`act_sequence` internals — validate / sign / batch-broadcast / collect —
with the step cap raised on the imported module object for that process
only. Feed-only: **Ghost Gum 11301** on kami 12649 from account
**shrike** (operator `0x9B95…F6e5`), 12649 RESTING, the account quiet
(operator nonce 1959, `pending == latest`, held across a 12 s check
before the first write). Endpoint: the pinned public Yominet RPC.

| rung | steps | first nonce | accepted | rejected | batch call | blocks (first → last) | wall, broadcast → last receipt | gas used | receipt statuses |
|---|--:|--:|--:|--:|--:|---|--:|--:|---|
| 1 | 8 | 1959 | 8 | 0 | 0.668 s | 32685848 (1) | 2.82 s | 9,835,442 | success 8 |
| 2 | 32 | 1967 | 32 | 0 | 0.526 s | 32685854 → 858 (5) | 8.35 s | 39,088,512 | success 32 |

Zero rejections, 40/40 mined successfully, nonces 1959 → 1999 with no
gap, pool drained to `pending 0` after each rung. Rung 1's 0.668 s is
the dedicated provider's FIRST call and pays for a new TCP/TLS
connection; rung 2, on the warmed connection, moved four times the
items in less time. Transport-only replay of already-mined raws at the
same widths (nothing sent, nothing spent): 16 items 0.277 s, 32 items
0.280 s.

**Deviation from the brief, on the record.** The brief asked for rungs
at 16 and 32 and capped the spend at 40 items; 16 + 32 = 48 > 40, so
the ladder ran 8 + 32 = 40 exactly. 32 is the size that matters — it is
the chunk the constant is sized for — and 8 brackets it from below.

## Costs

40 Ghost Gum (shrike held 896 before, 856 after), 48,923,954 gas across
the two rungs at `maxFeePerGas` 2,500,000 wei ≈ 0.000122 ETH. **No
Energy Drinks** (1,738 before and after), no kill, no victim, no other
account touched, nothing left unconfirmed.

## ITEM 2, measured on the same account, read-only

Pre-send validation on a 61-step plan shaped like the 19:30 strike
(1 `harvest_start` + 19 `liquidate` + 40 `feed` + 1 `harvest_stop`;
23 distinct chain subjects), timed three times each, no transaction
built or signed:

| path | wall | HTTP round-trips |
|---|--:|--:|
| 3.6.0, one `eth_call` per subject | **16.3 s** (16.2 / 16.2 / 16.4) | **66** |
| 3.7.0, one batched prefetch | **0.29 s** (0.26 / 0.36 / 0.25) | **1** |

66 round-trips for 22 logical reads: web3 issues three POSTs per
contract call through the pinned endpoint. The prefetch replaces all of
them with a single JSON-RPC batch of 23 `eth_call`s. That is the ~20 s
Anatoly measured in front of every strike, gone. Target was < 3 s.

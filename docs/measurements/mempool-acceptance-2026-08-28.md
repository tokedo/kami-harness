# Per-sender mempool acceptance, measured — 2026-08-28

What the node accepts from ONE sender in one broadcast, measured rather
than assumed. This is the number the step cap (`_ACT_SEQUENCE_MAX_STEPS`,
operator ruling R-3, 16 today) is re-ruled against; the cap is NOT
changed by this document and nothing here recommends a number.

**Method.** `executor/tests/live/measure_mempool_acceptance.py` drives
the shipped `act_sequence` internals — the same validate / sign /
batch-broadcast / collect path the tool uses — with the step cap raised
on the imported module object for that process only. Feed-only: Energy
Drink (item 11409) on kami 12649 from account **shrike** (operator
`0x9B95…F6e5`, on-chain account entity `1039918456…308295`). Harness at
branch `h360` of `0027bc9` (3.5.0) with the 3.6.0 batch broadcast in
place. Endpoint: the pinned public Yominet RPC. Times are from the
measuring machine; block timestamps are the chain's.

## The table

| run | steps | first nonce | accepted | rejected | first rejected nonce | batch call (s) | `txpool_status` right after broadcast | blocks (first → last) | chain time across those blocks | wall, broadcast → last receipt | gas used | receipt statuses |
|---|--:|--:|--:|--:|---|--:|---|---|--:|--:|--:|---|
| smoke | 4 | 1620 | 4 | 0 | — | 0.265 | pending 1, queued 6 | 32683393 → 32683394 (2) | — | 0.93 | 4,610,047 | success 4 |
| 1 | **32** | 1624 | **32** | 0 | — | 0.500 | pending 29, queued 7 | 32683413 → 32683417 (5) | 2 s | 7.86 | 34,406,592 | success 32 |
| 2 | **48** | 1656 | **48** | 0 | — | 0.611 | pending 46, queued 9 | 32683423 → 32683428 (6) | 2 s | 11.50 | 51,609,888 | success 48 |
| 3 | **64** | 1704 | **64** | 0 | — | 2.354 | pending 33, queued 9 | 32683438 → 32683445 (8) | 3 s | 15.97 | 68,813,184 | success 64 |

**Zero rejections at any rung.** No item in any batch came back with an
RPC error, so there is no rejection text to quote and no first-rejected
nonce; the `_SEQ_REJECTION_MARKERS` re-sign branch never fired. The
bracket run (largest accepted + 8) is defined for a rejection and was
therefore not run.

**The ceiling was not found.** 64 consecutive nonces from one sender
were accepted and all 64 mined, successfully, in 3 seconds of chain
time. The limit is somewhere above 64 and this ladder did not reach it:
the drink budget was 152 and the ladder plus its smoke spent 148
(4 + 32 + 48 + 64), leaving no room for a higher rung. Nonces advanced
1620 → 1768 with no gap; the pool drained to `pending 0` after every
rung.

## What else the runs measured

**Nine of one sender's transactions land in a single block, not four.**
Every rung filled its blocks the same way: 3 in the first (the block the
broadcast arrived mid-way through), then **9 per block** until the tail
ran out.

| block | txs in block | block gas used | block gas limit |
|---|--:|--:|--:|
| 32683438 | 3 | 3,225,618 | 45,000,000 |
| 32683439–32683444 | 9 each | 9,676,854 each | 45,000,000 |
| 32683445 | 7 | 7,526,442 | 45,000,000 |

Those blocks held **nothing but our transactions**, at 21% of the block
gas limit, so 9 is not gas pressure and not competition for space — it
is a per-block ceiling on one sender's transactions (or on transactions
per block) somewhere in the node. The earlier play-session observation
of "4 in one block" was a floor, not the limit.

**A feed costs 1,075,206 gas here** (34,406,592 / 32, identical across
all three rungs) — lower than the 1.98M the play session measured,
because those feeds were on a HARVESTING kami and these were not.

**Batch broadcast cost.** One HTTP body, one round-trip, measured around
the call:

| items | acceptance broadcast (s) | transport-only replay (s) |
|--:|--:|--:|
| 4 | 0.265 | — |
| 16 | — | 0.254 / 0.255 / 0.257 |
| 32 | 0.500 | 0.322 / 0.283 / 0.302 |
| 48 | 0.611 | — |
| 64 | 2.354 | — |

The replay column is the same batch re-offered after its transactions
were already mined: the node answers every item with an error, so
nothing is sent and nothing is spent, and what is left is the round-trip
for a body of that size. It is reported apart from the acceptance
timings and is not a substitute for them — 16 and 32 items cost the same
0.25–0.32 s as a single bare `eth_blockNumber` call (0.27 s), which is
the point: at those sizes the batch is one round-trip and nothing more.
Acceptance at 32 and 48 costs about twice a bare round-trip; at 64 the
call took 2.35 s, so the node's per-item admission work does start to
show at that width.

Against 3.5.0's serial broadcast at ~0.42 s per step, measured in the
play session: 32 steps would have taken ~13 s serially and took 0.50 s;
64 steps would have taken ~27 s and took 2.35 s.

**Wall time is not chain time.** Rung 3's 64 steps were all mined within
**3 seconds of chain time** (block 32683438 at ts 1787941073 → block
32683445 at ts 1787941076). The 15.97 s wall figure is the harness
COLLECTING receipts, which it still does one `eth_getTransactionReceipt`
poll per step, serially, after the broadcast. Nothing an on-chain
observer sees waits for that.

## Raw records

`ladder.json` from the script run (one object per rung, including every
per-step row) is not committed — the numbers above are its whole
content, and the per-step rows are 144 identical successes. The script
is committed and re-runnable.

## Costs

148 Energy Drinks (shrike held 1,944), 159,439,711 gas total across the
four runs at `maxFeePerGas` 2,500,000 wei ≈ 0.000399 ETH. No kill, no
victim, no other account touched.

---
module: kami-harness
version: 12
describes: 3d128bf
---

# SPEC — contract registry

What this module guarantees to its callers, what it assumes of the
services it calls, and how each claim is checked. Every line is meant to
be falsifiable: a claim that cannot fail a test or an audit does not
belong here. Implementation description does not belong here either —
this registry says *what holds*, not *how it is built*.

"CI" throughout means the pytest suite under `executor/tests/`, run from
`executor/`. No hosted CI service is configured for this repository.

---

## Provides

### P1 — MCP tool surface

- The registry advertises exactly **104 tools**.
- Every registered tool carries exactly one class tag in
  `server.TOOL_CLASSES`; the tag set is `{ACT, PERCEIVE, OUTSOURCE,
  META}` and the key set equals the registered tool names exactly.
- Class counts: **ACT 56 / PERCEIVE 32 / OUTSOURCE 9 / META 7**.
- Class meanings, as the code partitions them:
  - `ACT` — signs and broadcasts at least one transaction.
  - `PERCEIVE` — world-state read; signs nothing, changes no remote state.
  - `OUTSOURCE` — reaches the third-party strategy service.
  - `META` — wallet, account-registry, and bridge infrastructure; not
    world state.
- `server.READ_TOOLS` is the non-mutating subset: **40 tools** = all 32
  `PERCEIVE` + 5 `OUTSOURCE` reads + 3 `META` reads. `ACT ∩ READ_TOOLS`
  is empty.
- **Routing lives in descriptions, not in error text.** A tool named
  only inside an error message is not discoverable: in one deployment
  the tool an error pointed at ended the run with zero calls. Every
  capability an agent is expected to reach must be reachable from tool
  descriptions alone; error-text pointers are a courtesy on top of that
  and are never the mechanism. The optional mechanics snippet (P4,
  deviation X9) names tool names inside error text and does not change
  this: it is off by default, and every tool it can name states the same
  state requirement in its own description.
- Every served input schema is portable: no `anyOf`, `oneOf`, `allOf`,
  or `$ref` appears in any tool's `parameters`, and no `title` key
  survives to the wire.
- Every `READ_TOOLS` description ends with the standing sentence
  `server._UNTRUSTED_STANDING_SENTENCE`; every `lens_*` description also
  carries `server._LENS_SERVING_SENTENCE`. Non-read tools carry neither.
- Agent-visible registry mass — `len(name) + len(description) +
  len(json.dumps(parameters))` summed over the live registry — is
  **72,855 characters** at this ref, against a `REGISTRY_MASS_BUDGET`
  of 73,000. The budget is capacity that has to be earned: every
  character is spent out of the agent's context before it acts, so the
  ceiling rises only for named capability, never to make room for
  wording that could be tightened instead. Two raises are on record.
  70,000 -> 71,000 is an operator ruling of 2026-08-25, made for the
  named capability `lens_roster`. 71,000 -> 72,000 is an operator
  ruling of 2026-08-27, made for the named capability *the lens 0.5.1
  `full`/`stats` passthroughs*: thirteen optional parameters whose
  schemas alone cost 665 characters, plus the honest caps four wrapper
  descriptions had stopped stating once the deployed daemon passed
  0.5.0. In both cases the wording tightened in the same change was
  tightened because it reads better and did not fund the raise — at
  3.3.0 the two standing sentences below were shortened for a 711-
  character reclaim, and that reclaim was spent on the capability
  before the raise was asked for. **3.4.0 asked for no raise**: its
  four families cost 434 characters and 1,065 were reclaimed first,
  from `Args:` glosses that restated a parameter name the schema
  already carries (`quest_index: Quest index to accept.`, and eleven
  copies of `kami_id: Kami token index.`). A gloss that adds a
  mechanic — a range, a sentinel, a catalog pointer — was kept.
  72,000 -> 73,000 is an operator ruling of 2026-08-28 (**R-2**), made
  for the named capability *pipelined action sequences*
  (`act_sequence`). Its trim pass ran first and was measured before the
  raise was asked for, and it is the point at which this registry ran
  out of slack: the four trims together reclaimed **288 characters** —
  a cross-reference in `liquidate_kami` that restated `lens_node`'s own
  description, two `Args:` glosses (`lens_portal`, `lens_transfers`)
  that restated a schema type with no mechanic attached, five numeric
  defaults the schema already carries, and one `pool_swap` gloss its
  own body already states. **No larger reclaim exists.** The only bulk
  repetition left is the two standing sentences below (4,017 characters
  over 39 and 24 descriptions), already shortened once at 3.3.0, and
  one of them is the handling rule for untrusted player data — not a
  trim target at any budget. The `allow_partial` prose looks like a
  fifth standing sentence and is not: factoring its thirteen wordings
  into one appended sentence COSTS about 100 characters, because five
  of the thirteen currently pay 55 rather than 150. The next capability
  that needs room will need a raise, not a trim.
- Registry mass and `tools_hash` are **interpreter-dependent**: both are
  computed from schemas that the interpreter's own JSON and typing
  machinery generates, so a different Python version can yield different
  values from identical source. **Python 3.13 is the SPEC and production
  basis.** Figures quoted anywhere in this document are 3.13 figures,
  and any downstream pin that records them must record the interpreter
  alongside.

### P2 — tools_hash

- `server.compute_tools_hash()` returns `sha256` over
  `sorted((name, description, parameters))` across the live registry,
  serialized as `json.dumps(surface, sort_keys=True,
  separators=(",", ":"))`, hex-digested. 64 lowercase hex characters.
- Any tool added, removed, renamed, reworded, or reschematized changes
  the value. Nothing else does.
- `server.TOOLS_HASH` holds the value computed at import.
- The MCP `initialize` handshake carries it in the `instructions` field
  as the exact string `tools_hash=<64 hex chars>`.
- Value at this ref (Python 3.13):
  `87dc7481e12677819d388254eb3d23ed601e92823e62aab285710b6331731c1b`.
- The MCP `initialize` handshake additionally carries
  `schema_version=<SCHEMA_VERSION>` and `error_snippets=<on|off>` in the
  same `instructions` field, space-separated after the hash. The
  capability flag changes no name, description, schema or hash (P6), so
  a client cannot infer it from the surface: unstated, the harness half
  of a deployment is unrecordable. `instructions` is therefore the one
  handshake value that is NOT flag-invariant.

### P3 — SCHEMA_VERSION

- `executor/schema_version.py` exports `SCHEMA_VERSION = "3.6.0"`,
  semver.
- It is surfaced as the MCP `serverInfo.version` in the initialize
  handshake (`mcp._mcp_server.version`).
- Bump rule: MAJOR for a renamed/removed tool, a changed/removed
  parameter, or changed semantics or return shape; MINOR for a new tool
  or a new *optional* parameter; PATCH for non-semantic changes.
- `SCHEMA_VERSION` is independent of git tags: git tags mark repository
  states, `SCHEMA_VERSION` marks the tool contract.

### P4 — transaction semantics

Before signing, game-system writes validate mechanically-determinable
preconditions against chain state (registration, signer gas, per-tool
state checks, and an `eth_call` dry-run of the exact calldata). A failed
validation raises `PreTxValidationError`, whose message always begins
with the exact prefix `validation failed; no transaction sent: `, and
spends no gas.

After broadcast there are exactly **three terminal states**, and none is
ever reported as another:

| terminal state | how it is reported |
|---|---|
| confirmed-success | the tool returns; result carries `status="success"` with `tx_hash`, `block`, `gas_used` |
| confirmed-revert | **raises** `OnChainRevertError(tx_hash, block, gas_used, reason)` — never returned alongside or as success |
| unconfirmed | **raises** `TxUnconfirmedError(tx_hash, timeout)` — outcome unknown, the tx may still land |

- **A dry run has no terminal state.** `pool_swap(dry_run=True)` runs
  every pre-send gate the live call runs — distinct items, a MUSU side,
  a pool with liquidity, operator registration, item balance, and the
  live quote against `min_amount_out` — and then returns without an
  `eth_call`, a gas read, or a signature. Nothing is broadcast, so none
  of the three states above applies: the answer carries `dry_run: true`
  as its discriminator and **no `status`, `tx_hash`, `block` or
  `gas_used`**, rather than a fourth `status` value this table does not
  define. It carries the pool's `disabled` flag from the quote, because
  the send path's disabled-pool detection hangs off the `eth_call` a
  dry run does not make and is the one check it cannot perform.
- A returned result never carries `status="reverted"`.
- `OnChainRevertError.reason` is a best-effort `eth_call` replay of the
  exact calldata at the block the transaction landed in; it is `None`
  when the replay does not revert or the RPC refuses, and the message
  says so rather than inventing a reason.
- Nonce/retry logic never resubmits a confirmed revert or an unconfirmed
  transaction.
- **Every send reads its nonce at the `pending` block, never at
  `latest`.** All five send paths (`_send_tx`, `_send_batch_tx`,
  `_send_tx_owner`, `_send_eth`, and the mainnet bridge send) pass the
  `pending` block identifier. The public RPC is load-balanced across
  nodes, and a node that has not yet caught up serves a stale sequence
  at `latest` immediately after a confirmed transaction — observed
  across the hybrid-play fleet on 2026-07-28, where sequential sends
  inside one batch tool collided with their own predecessor. `pending`
  counts the sender's in-flight transactions and closes that race at
  the source; `_send_tx_retry`'s re-fetch on `account sequence
  mismatch` remains the second half. The harm avoided is a retry of a
  **non-idempotent** transfer: a level-up, a feed or an ETH send
  resubmitted after a stale-sequence rejection can execute twice, and
  no retry logic can un-spend it.
- **A pipelined sequence has K terminal states, one per step, and a
  call-level status that is not one of them.** `act_sequence` signs all
  K steps on consecutive nonces read ONCE at `pending` and broadcasts
  the whole tail in ONE round-trip before reading any receipt, so the
  three-state rule
  above binds each STEP and never the call: every step is reported in
  `steps[]` with its own `status` — `success`, `reverted`,
  `unconfirmed`, or `not_sent` — and its own receipt evidence. The call
  returns `status: "complete"` when every step succeeded and
  `"partial"` otherwise, and it RAISES only when step 1 fails before
  anything is broadcast. Once any transaction is in flight the call
  reports rather than raises, because an exception is a text block that
  cannot carry the hashes of the steps that landed.
  - **Only step 1 is dry-run.** Later steps' preconditions are earlier
    steps' effects, which do not exist at the pending block, so an
    `eth_call` for step 2 would fail correct sequences and pass wrong
    ones. Whole-sequence validation is therefore STATIC and forward-
    walked (a killer counts as harvesting if an earlier step starts it),
    and the description says the later steps are the caller's plan.
  - **A reverted step consumes its nonce, is final, and does not stop
    the sequence** (operator ruling R-3): later steps still execute, and
    a revert is NEVER resent — the existing rule that nonce/retry logic
    never resubmits a confirmed revert applies per step.
  - **A broadcast-rejected step is resent at most once.** A rejection
    means the node refused the raw transaction, so the nonce was not
    consumed and NOTHING landed for that step or any after it: the
    steps that did land are awaited, the nonce is re-read, and the tail
    is re-signed and broadcast once more. A second rejection reports
    the tail `not_sent`. A rejection is not a revert and the two are
    never merged.
  - **Cap 64 steps**, refused rather than auto-split — one tool call is
    one reportable unit, the same reason the batch caps are not split.
    64 is the MEASURED per-sender mempool acceptance, not a judgement
    call: operator ruling R-3 of 2026-08-28 re-ruled it from 16 to the
    number the ladder in
    `docs/measurements/mempool-acceptance-2026-08-28.md` returned. Feed-
    only rungs of 32, 48 and 64 consecutive nonces from account shrike,
    each broadcast as one batch, were accepted with **zero rejections**
    and mined in full; the 64 rung landed inside **3 seconds of chain
    time**. The ceiling was NOT reached — acceptance stops somewhere
    above 64 — so 64 is the largest number this repository has evidence
    for, and the cap is not raised past its evidence.
  - **The tail is broadcast as ONE JSON-RPC batch**: a single HTTP body
    of `eth_sendRawTransaction` calls over the provider's existing
    session, not one call per step. web3 v7's `w3.batch_requests()`
    cannot carry it — the library lists `eth_sendRawTransaction` in
    `RPC_METHODS_UNSUPPORTED_DURING_BATCH` and refuses it in the Method
    descriptor before a request is built, whatever the endpoint
    supports — so the provider's own `make_batch_request` is used, which
    is the same array over the same session. **The batch's JSON-RPC ids
    ARE the nonces**, so every response is attributed to its step by
    nonce and never by position: a node that reorders, drops or
    duplicates a response cannot shift a result onto the wrong step, and
    a nonce with no response in the reply is `not_sent`, never inferred.
    Serial sending survives ONLY as a transport fallback — if the batch
    CALL fails (a transport failure, not a refused transaction) it is
    retried once and only then does the tail go out one send at a time,
    with those rows carrying `broadcast: "serial"`. Rejection semantics
    are unchanged by the transport: the outcomes are read in step order
    and the first refusal stops the tail exactly as the serial loop did.
  - **Chain fact (2026-08-28): nine of one sender's transactions land in
    one block.** Every rung of the ladder filled its blocks the same
    way — three in the block the broadcast arrived mid-way through, then
    nine per block. Those blocks carried nothing but that sender's
    transactions, at 9,676,854 gas against a 45,000,000 block limit
    (21% full), so nine is not gas pressure and not competition for
    space; it is a per-block ceiling in the node. The earlier
    play-session observation of four in one block was a floor.
  - Measured before the design was fixed (U-1, 2026-08-28, account
    shrike): two `system.kami.use.item` feeds signed at nonces 1513 and
    1514 and broadcast back-to-back on one keep-alive session to one
    endpoint were BOTH accepted — no `account sequence mismatch` — and
    both mined status 1, in blocks 32678986 and 32678987 (adjacent
    blocks bearing the same timestamp), 0.974 s from first send to
    second receipt. Pipelining works on this chain; the rejection path
    above is a defensive branch, not the expected one. The observation
    also bounds the claim: a burst lands within a few blocks (9 per block per sender), not
    necessarily in ONE block, and the tool description says that.
  - **A decoded kill is decoded from its OWN receipt, on both paths.**
    `victim_gross`, `spoils`, `attacker_hp_after` and `cooldown_until`
    all come from that transaction's `ComponentValueSet` writes —
    `component.value` for the two bounty figures, `component.stat.health`
    (a packed Stat of four big-endian signed 64-bit fields, `sync` last)
    and `component.Time.Next` on the KILLER's kami entity for the other
    two, each component identified as keccak of its registered name. **No
    live read happens inside a decode**, on the sequence path or the
    single-call one. Reading the killer's state live at decode time is
    wrong by construction inside a burst, because the later steps are
    landing while the decoder reads: on the 32682485-496 burst that
    reported `cooldown_until` 1787938453 on all four kills where the
    receipts say 1787938418, 1787938421, 1787938422 and 1787938453. The
    pinned RPC is not archival, so the check is the LAST kill of a burst,
    where a live read has nothing landing after it — and there the two
    agree exactly. A component write absent from a receipt yields `null`
    plus a `decode_error` naming that component, never a substituted
    read. `recoil` still needs the single-call path's pre-send
    `hp_before` and is still omitted on a sequence row.
- Multi-transaction tools raise `BatchTxError` when any item failed. The
  error message carries **every** per-item outcome, successes included,
  and states that successful items are final on-chain and must not be
  resubmitted.
- **Every hash a call landed is reported, including on failure.** A
  transaction that landed and reverted has a hash, a block and spent
  gas, and is visible on-chain whether or not the payload mentions it.
  A multi-transaction tool therefore carries a per-leg `txs` list, and
  each leg that reached the chain appears in it with `tx_hash`,
  `status`, `block` and `gas_used` — the failed leg included. A failure
  that never reached the chain has no hash and adds no row rather than
  an empty one. Because the MCP error path carries no structured
  content (an exception becomes one text block), **the hash-bearing
  channel on failure is the itemized outcomes payload inside the error
  message** — the same payload `allow_partial` returns. Receipt fields
  are added to a per-item row before any `str(e)[:N]` truncation
  applies, so a cut reason can never sever a hash.
- **A batch dry-runs each item before batching.** An allow-failure
  on-chain batch absorbs a per-item revert without reverting the
  transaction, which spends gas on an item that took no effect; each
  item is validated by an `eth_call` of its single-item calldata first,
  a rejected item is `skipped` with its reason (deviation X6), and a
  run in which every item is skipped sends no transaction at all. This
  tightens pre-send validation only: the terminal states of items that
  were submitted are reported exactly as before.
- Exactly **13 tools** expose `allow_partial` (boolean, default
  `False`). With `allow_partial=True` a mixed batch returns its per-item
  result instead of raising. The set is: `travel_to_room`,
  `allocate_skills`, `level_to`, `level_and_allocate_batch`,
  `feed_level_allocate_batch`, `use_item_batch`, `equip_all_batch`,
  `unequip_all_batch`, `cancel_kami_listing`, `complete_all_trades`,
  `speed_craft_batch`, `stop_harvest_batch`, `sacrifice_kami_batch`.
- A batch transaction that lands but whose intended effect did not take
  hold is a failure, not a success: it raises by default and is
  reported per-item under `allow_partial`.

**Mechanics snippet (flag-gated, results only).** With
`KAMI_ERROR_SNIPPETS` on (P6), the messages of `PreTxValidationError`,
`OnChainRevertError` and `BatchTxError` carry an appended
`\n[mechanics] ...` block. It is a courtesy on top of the honest channel
and never a substitute for it: no failure is invented, reclassified, or
softened, and the pre-snippet text is unchanged.

- Contents are states, tool names and numbers this module already holds:
  the kami / harvest-entity state it read, the tools whose harness state
  gate accepts that state (from the single source in
  `server._TOOL_KAMI_STATES` / `_STATE_TOOLS` / `_HARVEST_STATE_TOOLS`),
  the requirement of the tool attempted, the live account room and stamina
  on revert classes, and the `_GAS_CEILINGS` entry the call provisioned
  when the revert was out-of-gas. No advice, no strategy, no game
  documentation: `integration/errors.md` and `systems/*.md` are not
  sources, and no sentence tells the caller what to do.
- A kami is named only when its entity id appears in that call's own
  arguments or calldata, so a failure never has an unrelated kami
  attributed to it.
- The unread-preconditions list is **per call, not per module**: a call
  that reads one of these facts drops it from the list rather than
  claiming it unread. `level_up_kami` reads the kami's level and XP from
  `component.level` / `component.experience` and states both, and states
  no requirement — the XP a level costs is the leveling formula, which
  this module does not hold and does not reimplement. `harvest_start`
  states the node's room from the index convention its own description
  states, so a cooldown revert stops masking a room mismatch. Facts
  still unread on a given call (cooldown, HP, and whichever of room/node
  match or XP that call did not read) are named as unread rather than
  guessed at, and a live read that fails drops its fact instead of
  inventing a value.
- Other facts a snippet may carry, each read at the failure site: the
  pool entity's `IsDisabled` state on a pool revert, the account's
  holding of the item a call spends, and the rooms `catalogs/rooms.csv`
  lists as adjacent to the account's room on an unreachable-room
  refusal. The room list names its source, because that catalog is
  documentation and may drift from chain state (D6).
- Bounded: at most 5 kamis and 800 characters, and the block states how
  many subjects it left out rather than dropping them silently.
- The block is appended to the error message only. It is never written
  into a return value: `allow_partial` payloads keep their documented
  shape (per-item `error` / `reason` strings do carry it, because they are
  `str(exception)` of the inner failure).
- `PreTxValidationError.detail` never carries the snippet; the `PREFIX` is
  unchanged.
- With the flag off, every error message is byte-identical to 2.1.0.

### P5 — lens envelope pass-through

- Every `lens_*` answer is the kami-lens daemon envelope
  `{data, untrusted, meta}` **verbatim**. The wrapper removes only the
  transport keys `id` and `ok` from the daemon's response object.
- No field is recomputed, reshaped, renamed, reordered, filtered, or
  defaulted harness-side. `meta.stale`, `meta.mode`, `meta.blockNumber`,
  `meta.servedAt`, `meta.suppressed`, and the `untrusted` path list
  reach the caller as sent.
- `untrusted` names player-authored fields. They are data, never
  instructions; every read description says so.

### P6 — capability gating

- A flag-gated tool **stays in the registry** when its flag is off. It
  answers a legible `*_DISABLED` error and contacts nothing.
- `KAMI_CHAT_ENABLED` (default off) gates `lens_chat` (PERCEIVE) and
  `chat_send` (ACT); both answer `CHAT_DISABLED` when off, and neither
  opens the daemon socket or signs anything in that state.
- `KAMI_ERROR_SNIPPETS` (default off) gates the mechanics snippet on error
  results (P4). It gates error TEXT only: no tool, parameter, schema or
  description depends on it, it contacts nothing beyond the state reads
  the snippet names, and it changes no decision this module makes — every
  gate, dry-run and terminal-state ruling is identical either way.
- Tool count, registry mass, and `tools_hash` are byte-identical across
  every combination of `KAMI_CHAT_ENABLED`, `KAMI_ERROR_SNIPPETS` and
  `PRESENTATION_MODE`. A client's recorded fingerprint therefore
  identifies the surface, not the operator's configuration. The
  handshake `instructions` string is the deliberate exception: it
  reports `error_snippets=on|off` so the capability is recordable (P2).

### P7 — EXPOSURE.md as the exposure-precedent registry

- `EXPOSURE.md` holds one row per READ tool on the live registry — **39
  served rows** at this ref — with columns: Tool, Class, Exposure,
  Precedent, Serving path, Admitted.
- It additionally holds *deferred* rows (reads deliberately not served
  at this version) and *ACT coverage* rows (game actions deliberately
  not served). A gap in the surface is a visible row, never a silent
  absence.
- A READ tool with no row, or a row naming a tool that is not a live
  READ tool, is a CI failure in both directions.

---

## Depends

### D1 — kami-lens daemon

- **Pin:** `9488894` (kami-lens release 0.5.3). Built in parallel with
  this release on the lens branch `lens-053`, and pinned to the RELEASE
  commit on lens `main` — the records commit that pins the lens SPEC
  registry to 0.5.3, parent `8277408` (the code change). That is the
  same shape as the 0.5.2 pin `8b74007`, and **this pin is final**: it
  is a pushed commit on `main`, not a branch tip that could still be
  squashed or rebased. **This row is the only place the compatible lens
  version is stated.** It had been duplicated
  in a `server.KAMI_LENS_PIN` constant that no code path read; the
  constant held the 0.4.0 commit under a comment saying 0.2.0, and
  nothing could fail on the contradiction. The constant is deleted at
  3.1.0 and the declaration lives here, where the spec version row
  records every change to it. (At 3.0.0 the declared pin was corrected
  from `a0a3e1e` (0.2.0) to `1d7a960`, having lagged the deployed daemon
  by two minor versions; `lens_roster` exists only from 0.3.0, so
  serving it and correcting the pin were the same change.)
- **The 0.4.0 -> 0.5.1 advance at 3.3.0 is load-bearing, not a records
  update.** Three things ride on it. (a) 0.5.0's §3.13 payload economy
  introduced the 50-row caps and row compaction that four wrapper
  descriptions were still describing as uncapped: `lens_party` promised
  "every kami" and `lens_room` promised each account's `kamis[]`, both
  of which the deployed daemon had already stopped serving by default.
  The pin had lagged the daemon again, and the descriptions lied for as
  long as it did. (b) `--stats` and `status.blockLag` arrive at 0.5.1
  and are what Families A and D pass through. (c) 0.5.1 fixes a
  `defaultOperator` prefill defect that counted argv tokens rather than
  positionals, so at 0.5.0 `party --full` with no account argument
  answered `BAD_ARGS` — which is exactly the request
  `lens_party(full=True)` emits on its `-1` default. Family B is not
  servable below the 0.5.1 pin.
- **The 0.5.1 -> 0.5.2 advance at 3.4.0 is what Family D wraps**, and
  unlike the previous two advances this pin did NOT lag the daemon: the
  harness release and the lens release were built against each other.
  Four additions ride on it. (a) `node --eligible-only` filters the
  liquidation preview to rows the attacker can take now and reports
  `harvestsEligible`; the daemon owns its `--with-vitals`-plus-attacker
  rule and answers `BAD_ARGS` for a violation, which passes through per
  P5. (b) `account --slim` serves identity with no roster and no chain
  read — the read that made resolving a target account's name cost a
  whole roster. (c) `status.feedsDegraded` is the per-feed array beside
  the chain-only `degraded`. (d) `NOT_READY` replaces the `NOT_FOUND`
  a pre-LIVE daemon used to answer, and is wrapped here as its own
  error class (EXPOSURE's error-class table).
- **The 0.5.2 -> 0.5.3 advance at 3.5.0 makes `--eligible-only`
  attacker-blind, and Family D is NOT SERVABLE BELOW IT — the same
  lesson as 3.4.0's Family D, so the lab redeploys the lens FIRST.**
  Until 0.5.3 the filter read `liquidation.eligible`, the full pairing
  verdict, which folds in `isStarving(attacker)` and
  `onCooldown(attacker)`. In a zero-cooldown kill loop the attacker
  sits at 0 HP for 4-6 s after every kill, so a read inside that window
  answered `harvestsEligible: 0` with 20+ targets under threshold —
  a payload INDISTINGUISHABLE from "everyone withdrew" (observed node
  35, block 32677631, 2026-08-28). An empty list was reporting a fact
  about the CALLER. At 0.5.3 the filter is TARGET-side (`threshold > 0
  && margin > 0`) and the attacker's own gate is reported once, on the
  new REQUIRED field `attacker.blocked` (`null`,
  `ATTACKER_STARVING` or `ATTACKER_COOLDOWN`), present with or without
  the flag. Per-row `eligible`/`reason` keep their full-pairing
  meaning, so a served row may read `eligible: false, reason:
  ATTACKER_STARVING`. **A 0.5.2 daemon answers the OLD meaning with
  `ok: true`** — it does not fail, it filters on the wrong predicate
  and omits `attacker.blocked` entirely — which is why the version
  floor is stated here rather than left to a runtime check. The harness
  change is description-only: no schema moves, and `lens_node` now says
  eligible_only keeps target-side rows and that `attacker.blocked`
  names the attacker's own gate.
- **The socket honoured undeclared flags silently below this pin.**
  0.5.0 gave the CLI a declared argument vocabulary and made an unknown
  option a usage error, but the SOCKET — the path this harness and its
  agents actually use — kept accepting anything: at 0.5.1 `account 3379
  --slim` returned the whole roster and `node … --eligible-only`
  returned an unfiltered list, both with `ok: true` and no error, while
  the CLI refused the same tokens. Measured here during the 3.4.0 build
  and fixed in 0.5.2, where one module owns the rule for both paths.
  This is why Family D is not servable below `8b74007`: against a 0.5.1
  daemon its two flags do not fail, they are ignored, and the caller
  gets a wrong-but-plausible answer to a question it did not ask.
- **Transport:** local AF_UNIX stream socket, one newline-delimited JSON
  request and one response per connection, 30-second timeout. Path from
  `KAMI_LENS_SOCKET`, else the daemon's own platform default
  (`<platform data dir>/kami-lens/kami-lens.sock`).
- **Request shape we send:** `{id, query, args: [string, ...], prose?,
  oversize?, noAuthored?}`. All positional args are stringified.
- **Response shape we assume:** `{id, ok: true, data, untrusted, meta}`
  on success; `{id, ok: false, error: {code, message}}` on failure.
- **Assumptions:** the envelope key set is stable at this pin; error
  codes (`BAD_ARGS`, `NOT_FOUND`, `KAMIDEN_UNAVAILABLE`,
  `CHAT_DISABLED`, …) are passed through unmapped; `meta.stale=true`
  marks answers served from last-synced state; `NOT_FOUND` carrying
  `mirror not initialized` means *starting*, not *absent*; the daemon
  owns every derived value it serves.
- **Downstream we do not talk to:** the daemon fronts the chain mirror
  and the Kamiden indexing service. Kamiden availability reaches us only
  as a lens error code. We hold no pin on Kamiden.
- **Thin-wrapper rule — this module's obligation, not the daemon's:** a
  `lens_*` tool performs argument mapping, exactly one `_lens_request`,
  and envelope pass-through. No formula math, no multi-query
  composition, no cross-query joins, no derived fields harness-side. A
  read that would require any of those is deferred with a visible
  EXPOSURE row until the daemon serves it.

### D2 — Kamibots / Asphodel API

- **Base:** `https://api.kamibots.xyz`. Auth: per-account `X-Agent-Key`
  header from `{LABEL}_KAMIBOTS_API_KEY`.
- **No version pin is available or asserted.** The dependency is pinned
  by endpoint path and response shape only; there is no upstream version
  string to record.
- **Declared (OUTSOURCE class, 9 tools)** via `_strategy_api`:
  `/api/agent/register`, `/api/agent/operator-key`, `/api/agent/tier`,
  `/api/agent/strategies`, `/api/strategies/status/all`, plus per-kami
  status, logs, start, and stop.
- **Internal read paths (not OUTSOURCE-classed)** via `_api_get`:
  - `get_scavenge_droptable` (PERCEIVE) — `GET /api/playwright/nodes`
    for node metadata; the droptable weights themselves come from chain
    component reads.
- **Blast radius:** an outage of this third party therefore reaches **0
  ACT tools and 1 PERCEIVE tool** in addition to the 9 OUTSOURCE tools.
  `travel_to_room` left this set at 3.0.0: it now reads room and stamina
  from `system.getter.getAccount` and SP+ balances from chain inventory.
  `level_to`, `level_and_allocate_batch` and `feed_level_allocate_batch`
  left it at 3.2.0: they read the kami's current level from the chain's
  Level component (`server._kami_level`), the same source
  `level_up_kami` has validated against since 3.0.0, so an account that
  never registered with this service can now use them. No ACT tool
  reaches this dependency. See deviation X2.
- **Delegation outlives the session.** A strategy started through this
  service keeps signing with the escrowed operator key after the MCP
  session that started it has ended — observed continuing ~23 hours on a
  ~10-minute cycle — with no known enrolment expiry and no enumeration
  API; `stop_strategy` is the only revocation path.
- **Assumptions:** the account and kami response shapes stay stable;
  `/api/accounts/` remains ~15s-cached upstream; HTTP 5xx and connection
  failures are transport-level, not semantic.
- **Migration risk:** this API may move into Asphodel core UX. Endpoint
  identity is not guaranteed across that migration; path stability is an
  assumption, not a contract.

### D3 — chain RPC endpoints (two chains)

| chain | chain id | endpoint config | default |
|---|---|---|---|
| Yominet | `428962654539583` | `RPC_URL` | public Initia endpoint |
| Ethereum mainnet | `1` | `MAINNET_RPC_URL` | **none — the process refuses to start when unset** |

- World contract: `0x2729174c265dbBd8416C6449E0E813E88f43D0E7` on
  Yominet.
- System addresses are resolved by `keccak(system_id_string)` through
  the World's `systems()` component and cached per process; an
  unresolvable system id raises rather than defaulting.
- **Assumptions:** `eth_call` at a historical block is available for
  revert-reason replay (its absence degrades to "reason unavailable",
  never to a wrong reason); the `getEntitiesWithValue` address overload
  is required for `component.address.operator` (the uint256 overload
  reverts on Yominet).

### D4 — Initia router API

- **Base:** `https://router-api.initia.xyz`. Used by
  `bridge_eth_from_mainnet` (quote/build) and `bridge_status`
  (`/v2/tx/status`).
- **No pin is available or asserted.** *This dependency has no owner
  named anywhere else in the repository.*
- **Assumptions:** the quote response carries a signable `evm_tx`
  (`value`, `data`); bridged ETH transits a 6-decimal denom, so amounts
  with more than 6 decimal places are rejected before signing; the
  LayerZero → Initia L1 → IBC path lands native gas ETH at the same
  owner address, typically ~5 min and up to ~20 min observed.

### D5 — key injection contract (pluggable secret store)

Every secret this module holds is resolved through
`executor/secrets_store.py`. The store is the only reader and the only
writer; no other module opens the keys file or the Keychain.

- **Names, not values, are the interface.** A secret VALUE never enters
  `os.environ`, argv, stdout, a tool return value, or an exception
  message — including on the failure paths. What is stated is the NAME
  and its resolved location (`secrets_store.where(name)`: a file path,
  or `macOS Keychain (kami-mcp/<NAME>)`).
- **Backends.** `KAMI_SECRETS_BACKEND` selects `envfile` (**the
  default**) or `keychain`; any other value fails loudly rather than
  resolving to one of them by accident. Under `envfile` every read and
  write is the keys file plus the process environment — byte-for-byte
  the behaviour of every version through 3.0.0. Under `keychain`,
  protected names are macOS generic-password items `kami-mcp/<NAME>`
  with the login user as account, and everything else still comes from
  the keys file.
- **Keys file:** `~/.blocklife-keys/.env` by default (`KAMI_KEYS_FILE`),
  deliberately outside the repository. Parsed tolerantly: `KEY = value`
  spacing, an optional `export` prefix, single- or double-quoted values
  (what `python-dotenv`'s `set_key` writes).
- **Which names are protected** is a names-only manifest — one name per
  line, no values — at `KAMI_SECRETS_MANIFEST`, defaulting to a sibling
  of the keys file: its name with a trailing `.env` removed, plus
  `.secrets.names` (`~/.blocklife-keys/.env` ->
  `~/.blocklife-keys/.secrets.names`; `hybrid.env` ->
  `hybrid.secrets.names`). **An absent manifest protects nothing**, so a
  deployment that configures none of this makes no Keychain call at all.
- **A protected name that resolves nowhere is fatal at startup**
  (`MissingSecretError`, naming only names). `ALLOW_ENV_SECRETS=1` lets
  it fall back to the keys file / process environment, warned on stderr.
- **Read:** `{LABEL}_OPERATOR_KEY` and `{LABEL}_OWNER_KEY` (label
  uppercased), plus `{LABEL}_KAMIBOTS_API_KEY` and `{LABEL}_PRIVY_ID`.
  A label present with only `{LABEL}_OWNER_KEY` loads as an owner-only
  account — it is visible in `list_accounts` and `get_gas_balance`, and
  every operator path raises a factual no-operator-wallet error.
  Secret-shaped names present in the process environment are read too,
  which is how a deployment that exports a key directly, and the test
  suite's synthetic accounts, load identically to a keys-file entry.
- **Written back by the server** through the store:
  `{LABEL}_OPERATOR_KEY` (by `create_operator_wallet`, which generates
  the keypair in-process), `{LABEL}_KAMIBOTS_API_KEY` and
  `{LABEL}_PRIVY_ID` (by `register_kamibots`). Each lands wherever its
  name resolves — keys file, or Keychain when protected.
- **Non-secret config** from the keys file (`RPC_URL`,
  `MAINNET_RPC_URL`, the capability flags) IS exported to `os.environ`,
  by `setdefault`, so an existing process value wins. Secret-shaped
  names are not, so a child process cannot inherit key material.
- `accounts/roster.yaml` maps labels to public addresses. Private key
  material never appears in any tool return value.
- **Assumption:** the keys file is readable and writable by the server
  process and is not indexed by any connected client; on the `keychain`
  backend, that `/usr/bin/security` exists and the login keychain is
  unlocked.

### D6 — local catalogs

- `catalogs/rooms.csv` backs `rooms_graph` BFS routing (rooms with
  `Status == "In Game"` only; unknown special-exit targets are skipped).
- `catalogs/quests/` backs `get_expected_objective`.
- **Assumption:** these are community documentation exports, not chain
  truth, and may drift from chain state. `get_expected_objective` says
  so in its own answer.

---

## Invariants

| claim | enforcement |
|---|---|
| Registry description mass ≤ 73,000 characters, measured from the live registry | `test_tool_surface.py::test_registry_mass_within_budget`, `test_h350_families.py::test_registry_mass_within_the_raised_budget` (72,857 at this ref, on Python 3.13 — 143 characters of headroom) |
| A sequence reports one terminal state per step and never conflates two: a success, a revert and a timeout in one call come back as themselves, each with its own receipt evidence | `test_h350_families.py::test_terminal_states_are_never_conflated` |
| A reverted step does not stop the sequence and is never resent | `test_h350_families.py::test_a_reverted_step_does_not_stop_the_sequence`, `::test_a_reverted_step_is_never_resent` |
| A broadcast-rejected tail is resent exactly once; a second rejection reports `not_sent` | `test_h350_families.py::test_a_broadcast_rejection_resends_the_tail_exactly_once`, `::test_a_second_rejection_reports_the_tail_not_sent` |
| A sequence reads its nonce ONCE at `pending` and signs every step before the first broadcast | `test_h350_families.py::test_nonce_read_once_and_all_signed_before_first_broadcast` (the fake chain asserts the `pending` block identifier) |
| `act_sequence` refuses more than 64 steps rather than splitting them, and 64 goes out as ONE batch | `test_h350_families.py::test_cap_is_the_measured_number_and_refuses_rather_than_splitting` (asserts the constant is 64, that 65 is refused with "at most 64", and that the 64-step call made exactly one batch POST) |
| The whole pre-signed tail is broadcast in ONE round-trip | `test_h360_families.py::test_the_whole_tail_goes_out_in_one_round_trip` (16 steps, one POST) |
| Broadcast results are mapped back to steps BY NONCE, never by position: the batch's JSON-RPC ids are the nonces, a reordered reply still lands on the right steps, and a nonce with no response is `not_sent` | `test_h360_families.py::test_the_batch_ids_are_the_nonces`, `::test_responses_returned_out_of_order_still_land_on_their_own_steps`, `::test_a_nonce_missing_from_the_response_is_not_sent_not_guessed` |
| A batch CALL failure is retried once as a batch and only then falls back to serial sending, which says so in the row | `test_h360_families.py::test_a_transport_failure_is_retried_once_as_a_batch`, `::test_two_transport_failures_fall_back_to_serial_and_say_so`, `::test_a_serial_fallback_still_stops_the_tail_at_a_refusal` |
| A rejected tail is re-broadcast as a second batch, and the provider's request-id counter is left as it was found | `test_h360_families.py::test_a_rejected_tail_is_re_broadcast_as_a_second_batch`, `::test_the_provider_id_counter_is_restored_after_a_batch` |
| web3's own batch API still refuses `eth_sendRawTransaction`, which is why the provider's `make_batch_request` is used | `test_h360_families.py::test_web3s_own_batch_api_cannot_carry_this_and_that_is_why` (fails loudly if a web3 upgrade lifts the ban) |
| `attacker_hp_after` and `cooldown_until` come from the kill receipt's own writes on the killer kami entity, so each row of a burst carries its OWN values; no live read happens inside a decode | `test_h360_families.py::test_series_rows_decode_their_own_hp_and_cooldown`, `::test_the_burst_rows_carry_FOUR_DIFFERENT_cooldowns`, `::test_no_live_read_happens_inside_a_decode` (the 32682485-496 burst, where 3.5.0 reported one live-read value on all four kills) |
| The receipt-side values are the true ones where a live read is known correct — the LAST kill of a burst | `test_h360_families.py::test_the_last_kill_of_the_burst_is_the_proof` (receipt 1787938453 = the live read 3.5.0 returned there; the pinned RPC is not archival, so this is the check that is available) |
| A component write missing from a receipt is null plus a `decode_error` naming that component, never a substituted read | `test_h360_families.py::test_a_missing_health_write_is_null_and_names_the_component`, `::test_a_missing_cooldown_write_is_null_and_names_the_component` |
| The health Stat is decoded as four big-endian SIGNED 64-bit fields with `sync` last, and both component ids are keccak of the registered name | `test_h360_families.py::test_the_stat_word_is_four_signed_64_bit_fields_and_sync_is_last`, `::test_component_ids_are_the_keccak_of_the_registered_name` |
| Whole-sequence static validation counts feed steps against the item balance and accepts a killer started by an earlier step | `test_h350_families.py::test_item_balance_is_checked_against_the_NUMBER_of_feed_steps`, `::test_a_killer_started_by_an_earlier_step_passes_validation` |
| Every step offers a FIXED table ceiling, never an estimate, and the gas gate sums them | `test_h350_families.py::test_ceilings_are_fixed_per_op_and_never_estimated`, `::test_gas_gate_sums_every_step` |
| The decoded kill reproduces the oracle: `victim_gross` = the max non-zero write to the VICTIM harvest entity, `spoils` = the LAST write to the KILLER's minus its pre-send value | `test_h350_families.py::test_victim_gross_equals_the_oracle_amount`, `::test_spoils_is_the_last_killer_write_minus_the_pre_value`, `::test_the_sequence_rule_chains_across_the_whole_sweep` (four recorded receipts from the 2026-08-28 sweep; the chain closes on the harvest_stop that drained 3,217) |
| The killer side is not a drain and musu.py's drain rule must not be used for it | `test_h350_families.py::test_killer_side_is_not_a_drain_and_musu_drain_rule_would_be_wrong` |
| A decode failure never fails a landed transaction: the field is null and `decode_error` says why | `test_h350_families.py::test_decode_failure_never_fails_a_landed_tx` |
| Harvest batch gas clears the measured p95 at every observed batch size, provisions a single kami, and fits 13 kamis in one transaction | `test_gas_ceilings.py::TestHarvestCeilings` (p95 per batch size pinned from the 2026-08-27 kami-oracle extract; the flat-constant shape is what these rows forbid) |
| `MAX_TX_GAS` is the chain's per-transaction lane cap, and every stated per-call maximum is derived from it | `test_gas_ceilings.py::TestBlockLimitGuard::test_max_tx_gas_is_the_lane_cap`, `TestHarvestCeilings::test_docstring_caps_match_the_arithmetic` (the docstring's "(at most N)" must equal `_harvest_max_per_call`, and N+1 must be refused) |
| A gated room exit is evaluated against the calling account before any hop is sent; with no ungated route the call refuses pre-send, and a gate that cannot be evaluated is never silently passed | `test_h340_families.py::TestGatedPlanning`, `::TestGateEvaluation` |
| Every gate type in `catalogs/room-gates.csv` has an evaluator, and every gated edge exists in the routing graph | `test_rooms_graph.py::test_gate_rows_are_well_formed`, `::test_every_gated_edge_exists_in_the_graph` (a fourth gate type fails the suite rather than routing an account into a revert) |
| A kami at 0 stored HP is refused pre-send by both `harvest_stop` and `harvest_collect`, with one wording, and an unreadable HP refuses nothing | `test_h340_families.py::TestStarvingGate` |
| `NOT_READY` is its own error class and never reads as a missing entity | `test_h340_families.py::TestLens052Passthroughs::test_not_ready_is_its_own_error_class`, `::test_not_ready_never_reads_as_a_missing_entity` |
| The registry advertises exactly 102 tools | `test_tool_surface.py::test_tool_surface_count` |
| Every registered tool is class-tagged, and no tag names an absent tool | `test_tool_surface.py::test_taxonomy_covers_registry_exactly` (also pins ACT 55 / PERCEIVE 31 / OUTSOURCE 9 / META 7) |
| Tools removed at this version stay absent | `test_tool_surface.py::test_removed_tools_absent` |
| Every READ tool has an EXPOSURE.md row; no row names a non-READ or absent tool | `test_tool_surface.py::test_exposure_rows` |
| Named deferred reads and unserved ACT rows stay present in EXPOSURE.md | `test_tool_surface.py::test_exposure_rows` |
| Operator keys are only ever escrowed; an owner private key never crosses the wire | `test_outsource.py::TestEnableStrategies::test_owner_key_never_in_request` — asserted on a split account whose owner and operator keys differ, so it cannot pass by key coincidence |
| The escrow request body is exactly `{"operatorKey": <operator key>}` and the service echoes the matching address or the call raises | `test_outsource.py::TestEnableStrategies::test_posts_operator_key_exactly`, `::test_address_echo_mismatch_raises` |
| An account with no operator wallet has nothing to escrow and issues no request | `test_outsource.py::TestEnableStrategies::test_owner_only_account_refuses` |
| `tools_hash` is 64 lowercase hex chars, recomputes identically, and is the first field of the handshake `instructions`, which also carries `schema_version` and `error_snippets`; `serverInfo.version` equals `SCHEMA_VERSION` | `test_tool_surface.py::test_tools_hash_present_and_deterministic`, `test_v300_families.py::TestHandshakeProvenance` |
| Tool count, registry mass, `tools_hash` and every (name, description, parameters) triple are identical across capability-flag settings | `test_tool_surface.py::test_surface_identical_across_capability_flags` — imports the module in 8 subprocesses over `KAMI_ERROR_SNIPPETS` × `KAMI_CHAT_ENABLED` × `PRESENTATION_MODE`, and asserts each child observed the flags it was given, so it cannot pass on a flag that never took effect |
| With `KAMI_ERROR_SNIPPETS` off, error text is what 2.1.0 produced | the pre-existing error-format suite passes unedited with the flag off (`test_validation.py::TestErrorFormat`, `::TestHarvestValidation`, `test_h3_act.py`), and `test_error_snippets.py::TestFlagOff` asserts the exact messages and an empty `mechanics` |
| Every kami-state gate reads its requirement from the single source, and a state row names only tools this module gates | `test_error_snippets.py::TestStateTable` (requirements equal the 2.1.0 literals, rows are the exact inversion, no `required_state=` literal survives in the module source, every named tool is live) |
| A snippet names a kami only when its entity id is in that call's own arguments or calldata | `test_error_snippets.py::TestSubjectDerivation` |
| A snippet states no advice, never lengthens past its bound, never hides a subject silently, reports only facts it read, and never introduces the `-32000` marker retry routes on | `test_error_snippets.py::TestSnippetGuards`, `::TestSnippetBehaviour` |
| The three snippets an agent sees are the pinned wordings | `test_error_snippets.py::TestSnippetExamples` (harvest_start on a HARVESTING kami, harvest_collect on a RESTING kami, a dry-run revert — asserted verbatim) |
| An `allow_partial` return keeps its documented shape with the flag on | `test_error_snippets.py::TestSnippetBehaviour::test_batch_error_leaves_the_returned_payload_untouched` |
| `SCHEMA_VERSION == "3.1.0"` | `test_tool_surface.py::test_schema_version` |
| The default secrets backend is `envfile`, and no code path reaches the Keychain under it — not load, not get, not put, not with a manifest present | `test_secrets_store.py::TestEnvfileIsTheDefault` (the Keychain helpers are replaced with raisers) |
| An unrecognised `KAMI_SECRETS_BACKEND` fails loudly instead of resolving to a backend | `test_secrets_store.py::TestEnvfileIsTheDefault::test_unknown_backend_fails_loudly` |
| The protected-names manifest is the keys file's name with a trailing `.env` removed plus `.secrets.names`, alongside it; an absent manifest protects nothing | `test_secrets_store.py::TestManifestPath` |
| Non-secret config from the keys file reaches `os.environ`; secret-shaped names never do | `test_secrets_store.py::TestLoadExportsConfigOnly` |
| A missing protected secret names the NAME and never the value, even when the value is sitting in the keys file | `test_secrets_store.py::TestMissingProtectedSecret::test_raises_naming_only_the_name` |
| No f-string, log line or exception in the store or the server interpolates a secret value; the one admitted interpolation is the Keychain write's stdin command | `test_secrets_store.py::TestNoValueInterpolation` (ast scan of both modules, plus the pinned exemption) |
| A secret written through the store round-trips: put() then a fresh process reads the same value back, from the Keychain when the name is protected | `test_secrets_store.py::TestPutRouting`, and the opt-in live smoke `test_keychain_live.py` (writes one throwaway item, reads it back through a fresh server import, deletes it, asserts rc 44) |
| `_load_accounts` writes nothing to stdout — the stdio JSON-RPC transport carries protocol only | `test_owner_only.py::TestOwnerOnlyLoad` (asserts the registry report on stderr and an empty stdout) |
| Docstrings are mechanism-only: no advisory or endorsement language in either direction | **partially enforced** — `test_tool_surface.py::test_h3_docstrings_stay_mechanical` covers 8 ACT tools against a banned-phrase list; `::test_enable_strategies_docstring_facts` covers 1 tool against a second list. The remaining 92 tools are **unenforced** |
| No deployment-context references in agent-visible tool descriptions | **unenforced** — no scrub scan exists in this repository. Verified by hand at this ref: all 101 descriptions are clean |
| Every READ description carries the untrusted-data sentence; every lens description names its serving path; non-read tools carry neither | `test_tool_surface.py::test_read_descriptions_carry_standing_sentence` |
| Served schemas are portable (no `anyOf`/`oneOf`/`allOf`/`$ref`) and carry no `title` noise | `test_tool_surface.py::test_all_schemas_portable`, `::test_schema_titles_stripped` |
| `allow_partial` appears on exactly the 13 batch tools, boolean, default `False` | `test_tool_surface.py::test_allow_partial_surface` |
| A submitted transaction's three terminal states are never conflated; a confirmed revert and an unconfirmed tx each raise their own type | `test_reporting_fidelity.py::TestSenderTerminalStates` |
| A revert reason is replayed at the landed block, and stated as unavailable rather than invented when the replay does not revert | `test_reporting_fidelity.py::TestSenderTerminalStates::test_revert_reason_replayed_at_landed_block`, `::test_revert_reason_unavailable_stated` |
| Retry never resubmits a confirmed revert or an unconfirmed transaction | `test_reporting_fidelity.py::TestNoBlindRetry` |
| No tool returns normally when a submitted, non-`allow_partial` transaction reverted | `test_reporting_fidelity.py::TestRevertInvariant` (drives every batch tool with a reverting sender) |
| A batch item that landed but took no effect raises by default and is itemized under `allow_partial` — never counted as done | `test_reporting_fidelity.py::TestStopHarvestBatch::test_silent_skip_raises_by_default`, `::test_silent_skip_allow_partial_returns` |
| An unreachable, starting, or unresponsive lens daemon raises `LensUnavailableError` and never reads as an empty result | `test_lens_wrappers.py::TestLensUnavailable` |
| Lens query errors surface with the daemon's own code, unmapped | `test_lens_wrappers.py::TestQueryErrors` |
| Lens envelopes pass through untouched, stale flags included | `test_lens_wrappers.py::TestEnvelopePassThrough` |
| Strategy-service connection failures and 5xx raise `OutsourceUnavailableError` on **every** strategy-service tool | `test_outsource.py::TestOutsourceDegradation` |
| A missing operator key at the strategy service raises an error naming the exact onboarding step; other 4xx pass through unembellished | `test_outsource.py::TestStartStrategyMissingKey` |
| An account with no operator wallet raises a factual error — never a crash, a swallowed message, a wrapped dry-run revert, or a silent skip | `test_owner_only.py::TestNoOperatorErrors`, `test_owner_only.py::TestOwnerOnlyLoad` |
| Chat tools stay in the registry when disabled, answer `CHAT_DISABLED`, and contact nothing | `test_lens_wrappers.py::TestChatFlag::test_disabled_by_default_no_socket_contact`, `test_h3_act.py::TestChatSend` |
| A declared-but-unimplemented presentation mode fails at startup rather than silently serving `envelope`; an unknown mode fails too | `test_lens_wrappers.py::TestPresentationMode::test_mode_validation` |
| `MAINNET_RPC_URL` has no default: the process refuses to import without it, loudly | `test_bridge.py::TestMainnetRpcRequired::test_startup_fails_loudly_without_mainnet_rpc_url` |
| ACT + PERCEIVE alone suffice to reach every documented game mechanic and to complete every quest | **manual audit, CI-pinned only in its conclusions.** The sufficiency sweep is run by hand against an upstream game-source pin (recorded in `EXPOSURE.md` § "ACT coverage" and in `CHANGELOG.md`); at this ref it covers all 26 quest objective types and all quest requirement chains. CI (`test_tool_surface.py::test_exposure_rows`) asserts only that the recorded gap rows remain present. **The sweep itself is not re-run by CI and does not re-run on an upstream bump** |
| Every leg a multi-transaction tool landed is reported with its hash, on failure as well as success; a failure that never reached the chain adds no row | `test_v300_families.py::TestFailedLegsCarryTheirHash`, `test_reporting_fidelity.py::TestUseItemBatchMatrix::test_mixed_allow_partial_returns`, `::TestSequentialLoopsMatrix::test_level_to_mixed_allow_partial_returns` |
| Receipt fields are structured, never inside a truncated reason string | `test_v300_families.py::TestFailedLegsCarryTheirHash::test_hash_fields_never_overwrite_a_documented_item_status` |
| A batch item that would revert is skipped by its own dry-run before batching, and an all-skip run sends no transaction | `test_reporting_fidelity.py::TestStopHarvestBatch::test_doomed_item_is_skipped_before_the_batch`, `::test_all_skipped_sends_no_transaction` |
| Revealed droptable loot is decoded from the reveal's own receipt, and an unrecognised payload yields nothing rather than a guess | `test_v300_families.py::TestRevealedLootDecode` |
| Pool availability is read from the pool entity's `IsDisabled` component; no world-config pool flag is read anywhere (no such field exists on-chain, and reading one would return the same 0 an absent field returns) | `test_v300_families.py::TestPoolDisabled` |
| The travel planner reads room, stamina and SP+ balances from chain state per call, spends no item without a computed deficit, and never reports a state-read failure with an empty reason | `test_v300_families.py::TestTravelReadsChainState` |
| The unreachable-room refusal keeps its snippet and names its adjacency source | `test_v300_families.py::TestUnreachableRoomSnippet` |
| A call that reads a precondition drops it from the unread list; `level_up_kami` states level and XP and states no XP requirement | `test_v300_families.py::TestLevelUpReportsXp`, `::TestHarvestGatesReportedTogether` |
| An unaffordable whole-lot take fails before signing, naming cost and holding; an unreadable precondition does not block the call | `test_v300_families.py::TestWholeLotTake`, `::TestAuctionHoldings` |
| `get_all_strategy_statuses` summarizes to the calling account's kamis from an on-chain ownership read, and passes an unrecognised or unreadable case through whole | `test_v300_families.py::TestStrategyStatusSummary` |
| `lens_roster` is a 1:1 wrapper, PERCEIVE, carrying both standing sentences | `test_v300_families.py::TestLensRoster` |
| A refused `eth_call` is retried once and never reported as a revert; a stale account sequence is in the retry class and no snippet can introduce a retry marker | `test_v300_families.py::TestTransientRpcClasses` |
| All five send paths read their nonce at the `pending` block, asserted at the site, so a stale `latest` sequence from a lagging load-balanced node cannot invite a retry of a non-idempotent transfer | `test_validation.py::TestPendingNonce`, `test_reporting_fidelity.py::TestSenderTerminalStates::test_send_eth_reads_pending_nonce`, `test_bridge.py::TestBroadcastIsFireAndForget::test_mainnet_nonce_read_at_pending` |
| The three batch level tools read the current level from the chain's Level component and make no Kamibots call: they work on an account with no API key, and an unreadable level refuses the call naming its cause rather than defaulting | `test_batch_wrappers.py::TestLevelPathNeedsNoKamibotsKey` |
| `SPEC.md` exists, is well-formed, and its `describes:` names a ref that resolves in this repository | `test_spec.py::test_spec_frontmatter`, `::test_describes_resolves` |

---

## Deliberate deviations

Each is labeled. A future rework must not "clean" any of these without a
decision — the label is the handle for that decision.

**X1 — `native-reads-kept`.** Six PERCEIVE tools are not lens wrappers,
and three META reads are not world state at all. Each has its own
EXPOSURE row carrying serving path and migration note:

| tool | serving path | why it is still native |
|---|---|---|
| `get_expected_objective` | local `catalogs/quests/` | documentation, not chain truth; no lens equivalent by design |
| `check_quest_completable` | chain `staticCall` | act-guard: answers "would quest-complete revert right now" |
| `quest_state` | chain component reads | act-guard: discriminates the on-chain quest state |
| `get_scavenge_points` | chain component reads | no lens scavenge query at pin `8b74007` |
| `get_scavenge_droptable` | Kamibots node metadata + chain weights | no lens scavenge query at pin `8b74007` |
| `get_item_orderbook` | chain event-scan + component reads | per-item book exceeds `lens_trades` at this pin |
| `get_gas_balance` | Yominet + mainnet RPC | wallet infrastructure |
| `list_accounts` | local roster / env | local configuration |
| `bridge_status` | Initia router API + RPC | cross-chain transport state |

**X2 — `third-party-reach-into-PERCEIVE`.** One internal Kamibots read
remains, inside the PERCEIVE tool `get_scavenge_droptable`: `GET
/api/playwright/nodes` supplies the entity IDs of a node's
`ITEM_DROPTABLE` rewards, which are then the entities for the on-chain
weight reads. No ACT tool reaches this dependency any more, and the
deviation no longer touches action paths.

Its remaining half is not trivially replaceable. The node's name and
tier cost are already available on-chain (`component.value.safeGet` of
`_scavenge_registry_id(node_index)`, as `get_scavenge_points` reads
them) and in `catalogs/nodes.csv`; the reward entity IDs are not — no
helper in this module derives them, and doing so needs an upstream ID
scheme this module does not hold. The tool's `account` parameter is
also described as an API auth header, so replacing the read moves a
description and therefore the surface hash. It is deferred to a
hash-moving release, with the EXPOSURE row already carrying the lens
deferral at pin `8b74007`. 3.3.0 and 3.4.0 are both hash-moving
releases and neither takes it: the reward entity IDs still have no
on-chain derivation in this module, so the deferral is about the
missing derivation, not about the hash.

Two tools were removed from this deviation by doing exactly what it
prescribes — an on-chain read, not a fallback. `travel_to_room` was the
first, at 3.0.0, and is the worked example: its third-party read was
~15s-cached upstream and reached the planner through a field-name
search and a hand-rolled stamina-regeneration estimate, which planned
on a stamina of 3 against a real ~100 and on rooms the account had
already left. The three batch level tools were the second, at 3.2.0:
the chain read they needed (`component.level`) had been sitting in the
module since 3.0.0, used by `level_up_kami` — the single-transaction
twin of the same on-chain path, which is why that tool worked on
accounts where the batch tools raised a missing-API-key error.

**X3 — `internal-only-read-helpers`.** `get_kami_market_listings` and
`get_account_trades` left the tool registry but remain as module
functions backing ACT pre-checks in `buy_kami`, `cancel_kami_listing`,
and `complete_all_trades`. They are not agent-callable and carry no
EXPOSURE row, because a row is owed for what the *surface* exposes.
Deleting them breaks three ACT tools.

**X4 — `quest-natives-alongside-lens`.** `quest_state`,
`check_quest_completable`, and `get_expected_objective` coexist with
`lens_quests` rather than being superseded by it. The lens serves the
registry and per-account acceptance; the natives serve the discriminated
on-chain state and the pre-send act-guard. Two quest-status natives
*were* removed at this version; these three were not.

**X5 — `bridge-submitted-status`.** `bridge_eth_from_mainnet` returns
`status="submitted"` immediately after broadcast and deliberately does
not await a receipt, so P4's three-terminal-state rule does not bind it.
Awaiting would lose the transaction hash across a client timeout and
invite a same-nonce retry, and arrival is minutes away regardless.
Tracking is `bridge_status`.

**X6 — `dry-run-skips-in-band`.** Batch items rejected by their pre-send
dry-run are reported as `skipped` in the return value and do **not**
raise, even with `allow_partial` unset. Nothing was signed and no gas
was spent, so they are not transaction failures. The raise invariant
binds *submitted* transactions only. A run of all-skips returns
normally.

**X7 — `situational-dead-by-design`.** Some tools stop working by
design and stay in the registry anyway: `newbie_vendor_buy` (one
purchase per account, ever, and only while the account is under 24 hours
old) and `create_operator_wallet` (one-shot per label). Removing them on
state change would make `tools_hash` a function of account age rather
than of the surface.

**X8 — `declared-unimplemented-mode`.** `PRESENTATION_MODE=inline-tags`
is a declared mode with no implementation at this version. Selecting it
raises at startup instead of silently falling back to `envelope`. The
mode name stays in `_PRESENTATION_MODES` so the gap is visible.

**X9 — `error-text-mechanics-snippet`.** P1 says routing lives in
descriptions and that a tool named only in an error message is not
discoverable — a deployment once ended a run with zero calls to the tool
an error pointed at. The mechanics snippet (P4) names tool names in error
text anyway, and is admitted because it repeats rather than replaces:
every tool a state row can name states the same requirement in its own
description (`harvest_start` "not already harvesting", `harvest_stop` /
`harvest_collect` "ACTIVE harvest", `revive_kami` "Revive a DEAD kami",
`liquidate_kami` "both HARVESTING on the same node", `gacha_reroll` "must
be RESTING and owned", `transfer_kami` "RESTING or LISTED"). The snippet
says which of those applies to the state just observed. It is off by
default, so the routing mechanism a default deployment offers is
unchanged, and the rows deliberately omit tools whose state requirement
this module does not gate — a row is narrower than "what would work", and
the wording ("tools whose harness state gate accepts X") says so.

---

## Non-goals

- **No agent policy.** No strategy, planner, scorer, or heuristic lives
  here. The surface describes mechanisms; choosing among them is the
  caller's job.
- **Not a world-state indexer.** This module maintains no mirror, cache,
  or derived view of world state, and never recomputes a lens-served
  value (see D1's thin-wrapper rule).
- **Not a general-purpose wallet.** No arbitrary contract call, no
  arbitrary-recipient bridging — the bridge recipient is pinned to the
  signing account's own owner address and is not a parameter.
- **No cross-item pool routing.** Every live pool is MUSU-paired (item
  1), so `pool_swap` and `pool_swap_quote` require MUSU on one side and
  refuse an item-to-item pair before signing rather than routing it as
  two hops. The constraint matches the world rather than narrowing it:
  six live pools, all MUSU-paired. Revisit only if lens pool discovery
  shows a non-MUSU pool.
- **No owner-key escrow, ever.** Only operator keys are escrowed, and
  only to the declared strategy service.
- **Not a completeness guarantee over the game.** Reads and actions not
  served at this version are enumerated in EXPOSURE.md; that list is the
  scope boundary, not an oversight.
- **No hosted CI.** No pipeline runs on push; "CI" is the local pytest
  suite. Nothing in this repository enforces that the suite was run
  before a commit or a tag.

---

## Changelog

| spec version | date | change |
|---|---|---|
| 1 | 2026-07-24 | Initial contract registry, describing `v2.0.0-rc1` (`a65e22f`). |
| 2 | 2026-07-24 | Re-pinned to `48bd154`, which adds one sentence to the `sacrifice_kami` description ("sacrifice is not liquidation"). P1 registry mass 65,830 → 65,942; P2 `tools_hash` `b952adf8…bb43` → `9e236f90…ada8`; mass invariant row updated. Tool count, classes, and schemas unchanged. |
| 3 | 2026-08-07 | Re-pinned to `869767b` (SCHEMA_VERSION 2.1.0). Adds the swap pair `pool_swap_quote` (PERCEIVE) + `pool_swap` (ACT): P1 count 99 -> 101, classes ACT 54 -> 55 / PERCEIVE 29 -> 30, `READ_TOOLS` 37 -> 38. Registry-mass budget 66,000 -> 70,000 with P1 mass 65,942 -> 69,900; P2 `tools_hash` `9e236f90...ada8` -> `7fc11fe9...5262`. Adds the interpreter-basis statement (Python 3.13) to P1, the descriptions-not-error-text routing rule to P1, and the delegation-outlives-the-session property to Depends. Mass, count, class, version and description-scrub invariant rows updated. |
| 4 | 2026-08-07 | Re-pinned to `da11b28`: out-of-gas reverts are now identified from receipt arithmetic before any replay, after a live probe showed the production RPC ignores the `gas` field in `eth_call` (a call priced at 3,083,548 by `eth_estimate_gas` succeeds through `eth_call` at gas=30,000), which makes replay unable to reach that class on this chain. Code and tests only — P1 mass 69,900, P1 count 101, P2 `tools_hash` and all class counts unchanged. |
| 5 | 2026-08-17 | Re-pinned to `2ce4268` (SCHEMA_VERSION 2.2.0). Adds the flag-gated mechanics snippet on error results: P4 gains its paragraph (courtesy on the honest channel, contents, bounds, results-only), P6 gains `KAMI_ERROR_SNIPPETS` and widens the surface-identity claim to it, P1 notes that the snippet's tool-name pointers are not the routing mechanism, and deviation X9 `error-text-mechanics-snippet` argues that admission. The "tools_hash stable across capability flags" invariant moves from **unenforced** to `test_tool_surface.py::test_surface_identical_across_capability_flags` (8 flag combinations, count + mass + hash + every description), and six invariant rows are added for the single-source state table, subject derivation, snippet guards and the pinned snippet wordings. No tool, parameter, schema or description changes: P1 mass 69,900, P1 count 101, P2 `tools_hash` and all class counts unchanged. **Correction:** P3 stated `SCHEMA_VERSION = "2.0.0"` while the module and the invariant row said 2.1.0; P3 now reads 2.2.0. |
| 6 | 2026-08-25 | Re-pinned to `7da193c` (SCHEMA_VERSION **3.0.0**). **MAJOR by P3's own rule**, not the 2.3.0 the build brief labelled it: `get_all_strategy_statuses` changes return shape, and new pre-send gates move failures that were on-chain reverts into `PreTxValidationError`. Five families. (A) Multi-transaction hash integrity: every landed leg is reported on failure as well as success, the hash-bearing failure channel is named in P4 (the MCP error path carries no structured content), receipt fields precede truncation, `scavenge_claim_and_reveal` gains a top-level `txs` and returns its revealed loot decoded from the reveal receipt, and `stop_harvest_batch` dry-runs each item before batching and routes through the standard sender (it previously built, signed and sent inline with no dry-run, no gas check and no send-error wrapping). (B) Pool availability: read from the pool entity's `IsDisabled` component. The world-config flags the run record blamed (`POOL_ENABLED`, `POOL_SWAP_ENABLED`) **do not exist**: a config read returns 0 for an absent field, so the fabricated name confirmed itself, and this version reads the entity and names no config key. (C) `travel_to_room` reads room, stamina and SP+ balances from chain state, leaving deviation X2; state-read failures name their cause and retry once; `use_items` defaults to **False** and consumes only against a computed deficit. (D) Snippet true-ups: the unread-preconditions list is per call, `level_up_kami` states level and XP, `harvest_start` states the node's room, `take_trade` gains a whole-lot balance gate, `auction_buy` names its currency and holding, and the unreachable-room refusal — which had been dropping its snippet entirely on the re-raise — names the catalog adjacency. (E) `lens_roster` served (P1 count 101 -> 102, PERCEIVE 30 -> 31, `READ_TOOLS` 38 -> 39, EXPOSURE 37 -> 38 served rows); `get_all_strategy_statuses` summarized to the account's own kamis with `full=true` for the raw answer; transient-RPC and stale-sequence classes absorbed. D1 re-pinned `a0a3e1e` (0.2.0) -> `1d7a960` (0.4.0), correcting a declared pin that had lagged the deployed daemon by two minor versions. Registry-mass budget 70,000 -> 71,000 by operator ruling for the named capability `lens_roster`, with P1 mass 69,900 -> 69,993; P2 `tools_hash` `7fc11fe9...5262` -> `b7eebb88...f1f8`, and the handshake `instructions` now also carries `schema_version` and `error_snippets`. |
| 7 | 2026-08-26 | Re-pinned to `4fc5f19` (SCHEMA_VERSION **3.1.0**). **MINOR**: no tool, parameter, schema or description changes — P1 count 102, P1 mass 69,993 and P2 `tools_hash` `b7eebb88...f1f8` are all unchanged, and the surface fingerprint of a 3.0.0 deployment and a 3.1.0 one is identical — but two agent-visible texts change: `create_operator_wallet`'s `key_saved` field and the missing-key errors now name the RESOLVED location of a secret rather than the literal `.env`. Four families. (A) D5 rewritten: key injection becomes a pluggable secret store (`executor/secrets_store.py`, ported from kami-hybrid-play `65b96e6`) with `envfile` as the DEFAULT backend and `keychain` as an opt-in, a names-only protected-names manifest derived from the keys-file name, and the standing rule that a secret VALUE never enters `os.environ`, argv, stdout, a result, or an exception. A deployment that configures nothing behaves exactly as 3.0.0 did and makes no Keychain call. `_load_accounts` scans the store instead of `os.environ`; `create_operator_wallet` and `register_kamibots` write through it; the generated operator key stops being assigned into `os.environ`. (B) The six `_load_accounts` messages moved from stdout — the stdio JSON-RPC transport — to stderr. (C) The dead `server.KAMI_LENS_PIN` constant is deleted; D1 is now the single declaration of the compatible lens version (the constant held the 0.4.0 commit under a comment saying 0.2.0). (D) Doc-count drift corrected against the live registry, and `executor/README.md` regains the three tool rows it was missing (`pool_swap`, `pool_swap_quote`, `lens_roster`). **Correction:** P7 stated 38 served EXPOSURE rows while the file holds — and CI requires — one row per READ tool, which is 39. |
| 8 | 2026-08-27 | Re-pinned to `dc2b6aa` (SCHEMA_VERSION **3.2.0**). **MINOR**, not the 3.1.1 the build brief labelled it: no tool, parameter, schema or description changes — P1 count 102, P1 mass 69,993 and P2 `tools_hash` `b7eebb88...f1f8` are unchanged, and the surface fingerprint of a 3.1.0 deployment and a 3.2.0 one is identical — but on an account with no Kamibots API key a missing-key error stops appearing and three tools succeed where they used to fail, which is an agent-visible effect and therefore outside this file's PATCH definition. Two families. (A) Every send path reads its nonce at the `pending` block rather than `latest`: `_send_tx`, `_send_batch_tx`, `_send_tx_owner`, `_send_eth` and the mainnet bridge send, via the single `_NONCE_BLOCK` constant. A load-balanced public RPC serves a stale sequence at `latest` right after a confirmed transaction, and a rejected stale-nonce send is retried — which for a non-idempotent transfer risks executing it twice. P4 gains the paragraph; `_send_tx_retry`'s re-fetch on `account sequence mismatch` is unchanged. (B) `level_to`, `level_and_allocate_batch` and `feed_level_allocate_batch` read the kami's current level from the chain's Level component (`_kami_level`, now also the single derivation behind `_kami_progress`) instead of `GET /api/playwright/kami/{id}/`, through a `_read_kami_level` wrapper in the `_read_account_view` shape — retried once, never defaulted, the exception type always named. The level decides how many transactions are sent, so an unreadable level refuses the call. Chain over lens deliberately: the lens is a separate daemon with its own unavailability class, and making three ACT tools depend on it would trade one external dependency for another; `level_up_kami` — the single-transaction twin of the same on-chain path, which worked on accounts where these three raised — has validated against this component since 3.0.0. Component and client projection cross-checked live on five kamis at block 32,626,207 (15540/46, 158/48, 2808/48, 11224/48, 4277/36 — identical). D2's blast radius drops from 3 ACT + 1 PERCEIVE tool to 0 ACT + 1 PERCEIVE; deviation X2 is renamed `third-party-reach-into-PERCEIVE` and shrinks to `get_scavenge_droptable`, whose remaining read supplies reward entity IDs that have no on-chain derivation in this module and whose replacement would move a description, so it is deferred to a hash-moving release. Two invariant rows added. |
| 9 | 2026-08-27 | Re-pinned to `fbceeb4` (SCHEMA_VERSION **3.3.0**). **MINOR**: thirteen new *optional* parameters, no tool added, removed or renamed — P1 count stays 102 and every class count is unchanged — but every touched description moves the surface fingerprint. D1 advances `1d7a960` (0.4.0) -> `f07b578` (0.5.1), and the advance is load-bearing rather than clerical: 0.5.0's payload economy capped listings at 50 rows and compacted their fields, so for as long as the declared pin lagged the deployed daemon, `lens_party` promised "every kami" and served fifty and `lens_room` promised each account's `kamis[]` and served a `kamiCount`; 0.5.1 adds `--stats` and populates `status.blockLag`; and 0.5.1's `defaultOperator` fix (the prefill counted argv tokens rather than positionals) is what makes `lens_party(full=True)` on the `-1` default reach the daemon at all. Four families. (A) `stats` on `lens_kami`, `lens_roster`, `lens_party`, `lens_node` — the kami sheet's stat block (base/shift/boost/sync/total for health, power, harmony, violence) plus the [body, hand] affinity pair. `lens_node`'s `--stats`-needs-`--with-vitals` rule is NOT pre-validated harness-side: the daemon's `BAD_ARGS` passes through, per P5. On `lens_roster` the flag imposes a 50-row cap the flag-off answer does not have, with no uncapped form, and the description says so. `lens_kami` stops promising "traits, skills", which it has never returned. (B) `full` on the nine wrappers whose 0.5.1 registry query declares `--full` — `lens_node`, `lens_party`, `lens_room`, `lens_items`, `lens_merchant`, `lens_leaderboard`, `lens_trades`, `lens_quests`, `lens_market` — enumerated from the registry rather than from memory. The flag is not uniform: six lift a 50-row cap, `lens_items`/`lens_merchant` restore compacted fields, `lens_quests` returns a different shape. Every capped default now names its count fields. (C) `pool_swap` gains `dry_run`: the full pre-send path with no `eth_call`, gas read or signature. P4 gains the rule that **a dry run has no terminal state** — the answer carries `dry_run: true` and none of `status`/`tx_hash`/`block`/`gas_used`, and carries the quote's `disabled` because the send path's disabled-pool detection is the one check a dry run cannot make. A Non-goals row records the operator ruling that item-to-item pool routing is a non-goal, not a gap: every live pool is MUSU-paired, both swap tools already said so, and their wording is unchanged (delta 0). (D) `SETUP.md`'s claim that no world-state read goes through the Kamibots service is corrected — `get_scavenge_droptable` does, as D2 has always declared — as is its claim that all 31 PERCEIVE tools are lens wrappers, when 24 are. EXPOSURE gains a **deferred row for the lens `skills` query**, served by 0.5.1 and not wrapped here, so the one-wrapper-short gap is visible rather than silent; served rows stay 39. Registry-mass budget 71,000 -> 72,000 by operator ruling of 2026-08-27 for the named capability *the lens 0.5.1 `full`/`stats` passthroughs* (thirteen optional-bool schemas cost 665 characters before any prose), with P1 mass 69,993 -> 71,643 and 357 characters of headroom; the two standing sentences were shortened first for a 711-character reclaim that funded the capability, not the raise. P2 `tools_hash` `b7eebb88...f1f8` -> `f3734714...ac43`. Mass, version and invariant rows updated. |
| 10 | 2026-08-27 | Re-pinned to `6ce36a1` (SCHEMA_VERSION **3.4.0**). **MINOR**: two new *optional* parameters, no tool added, removed or renamed — P1 count stays 102 and every class count is unchanged — but four descriptions move the surface fingerprint. D1 advances `f07b578` (0.5.1) -> `8b74007` (0.5.2), and for the first time in three advances the pin did NOT lag the daemon: the two releases were built against each other. Five families. **(A) `travel_to_room` cannot strand the account.** A plan from room 75 to 37 dry-ran `feasible: true`, executed three hops (15 stamina, ~2.7M gas) and reverted `AccMove: inaccessible room` on hop 4, on a QUEST gate the BFS over `catalogs/rooms.csv` cannot see; it recurred the same day on 11 -> 15. The obvious fix does not work, and establishing that shaped the family: `system.account.move` takes only a destination, reads the account's current room from chain state, and checks **reachability before accessibility**, so an `eth_call` for a later hop answers `AccMove: unreachable room` and never reaches the gate — two distinct reverts, both on record in run telemetry. The gates are therefore evaluated directly. New `catalogs/room-gates.csv` (11 rows, extracted from the lens `room` query over all 70 in-game rooms and deduplicated — the daemon emitted an exit record per adjacency *and* per special exit, so 52 of 196 were duplicate `(from, to)` pairs) gates **25 of the graph's 144 directed edges**. `rooms_graph` gains `gates_on()`, `gated_edges()` and a `blocked` argument on `shortest_path`, and stays chain-free because a gate is a condition on an ACCOUNT. `travel_to_room` evaluates each gate on its plan against the caller on chain — `QUEST` against the account's quest instance, `ITEM` against its inventory balance, `COMPLETE_COMP` against a global goal entity, each read once — drops what it cannot cross, re-plans, and with no route left **refuses pre-send with `PreTxValidationError`** naming every blocking gate by type and index. A gate that cannot be evaluated is reported `gate could not be evaluated` and treated as impassable: never silently passed, never silently downgraded. `dry_run` reports `gated_hops` with `passable: true | false | "unknown"`, and a mid-path revert names the gate the catalog holds for that edge. **There is no `allow_gated` flag** — an escape hatch would be a parameter an agent calling with defaults never finds, and P1 is explicit that routing lives in descriptions. Semantics verified live at block 32,650,458 against an account whose crossings were known (walked the room-68 goal gate, reverted at the room-15 quest gate); note that `COMPLETE_COMP` reads a *community* goal, so an account that never contributed still passes. **(B) Batch gas ceilings from measurement.** Measured live on 3.3.0, `harvest_start` costs ~0.74M gas/kami against a 3,000,000/kami ceiling and `harvest_stop` ~1.5M against 4,000,000 — ~4x, so a 13-kami start and stop each needed two transactions while three docstrings promised one. Re-measured from kami-oracle over receipt-status=1 transactions since 2026-06-01, joining `raw_tx` to `kami_action` on `tx_hash` to recover batch size, and the SHAPE was wrong rather than the numbers: harvest gas is base + slope x n with a large fixed term, so a flat per-kami constant either over-provisions every batch or under-provisions the single-kami call — 349,296 starts and 366,809 stops at n=1 in that window, the commonest call on the surface, and a flat 2,000,000 stop would have sat 24% under its n=1 p95. `_send_batch_tx` gains `gas_base`; the families become start 1,300,000 + 950,000n, stop 1,600,000 + 1,950,000n, collect 1,600,000 + 1,700,000n, each ~1.3x the measured p95 across the whole range, each citing date/batch size/p95/tx count in its table comment. **`MAX_TX_GAS` 40,000,000 -> 31,500,000**: the old value was margin under the 45,000,000 block limit, but the chain refuses a gas limit above a per-transaction **lane cap of 31,500,000**, so this module's ceiling sat above the one that binds and could never reject what the lane rejects — which is why a 13-kami stop was refused here with "Split into calls of at most 10" and the 10-kami retry was then refused by the RPC. Per-call maxima become 31 / 15 / 17 and every "at most N" is derived from the lane cap. Not auto-splitting stays the contract: one tool call is one transaction, because an agent's plan/act accounting depends on it. **(C) A starving kami cannot stop or collect.** `LibKami.verifyHealthy` gates both `HarvestStopSystem` and `HarvestCollectSystem`, so the check goes into `_validate_active_harvests`, already their shared gate, reading `component.stat.health`'s `sync` word — a chain component read, not a lens call, keeping ACT tools free of the daemon. It is **sound one way and the code says so**: health syncs lazily and a harvesting kami only loses HP between syncs, so `sync == 0` proves starvation while `sync > 0` is inconclusive; the dry-run stays the backstop and its bare `kami starving..` is re-raised with the same sentence the pre-send gate uses. An unreadable HP refuses nothing. `liquidate_kami` gains the clause that recoil can leave the attacker at 0 HP. `harvest_start`'s own HP requirement is a named, deliberate gap. **(D) lens 0.5.2 passthroughs.** `lens_node.eligible_only` (-> `--eligible-only`, its `--with-vitals`-plus-attacker rule left to the daemon per P5), `lens_account.identity_only` (-> `--slim`; resolving a target account's name previously cost a whole roster, and one 164-kami account tripped the tool-result cap outright), `lens_status` naming `feedsDegraded` beside `degraded`, and **`NOT_READY` as its own error class** `LensNotReadyError`, a subclass of `LensUnavailableError` — before it, a read against a daemon stuck at `SETUP 0%` answered `NOT_FOUND: node 9 not in mirror`, which reads as "that node does not exist". Family D is **not servable below `8b74007`**, and finding out why was part of this build: measuring it against the running 0.5.1 daemon showed its SOCKET silently honouring undeclared flags where its CLI refused them — `account 3379 --slim` returned the whole roster, `node … --eligible-only` returned an unfiltered list, both `ok: true` — so against 0.5.1 these parameters do not fail, they are ignored. 0.5.2 puts the rule in one module for both paths. The lens query set is identical at 0.5.1 and 0.5.2, so the `skills` deferral row and the 39 served rows stand. **(E) Docs and one retry.** `_send_tx_retry`'s sequence-mismatch backoff widens from a flat 1s to 1/2/4s, recorded together with the fact that the observed failure was an operator key shared with the web client, which no retry policy fixes. `_GAS_PRICE` gains a comment recording that Yominet charges `maxFeePerGas` as offered with no refund and that 2,500,000 wei is deliberately the floor, NOT read from chain, so a raised base fee fails loudly as underpriced. Three harness docs corrected: `systems/health.md` said a kami "dies when HP reaches 0" and listed harvest strain as a cause of death (0 HP is starving; only `LibKami.kill()` kills), `integration/api/harvesting.md` said a zero-HP kami "is liquidated" (liquidat**able**), and `README.md`'s catalog table claimed `rooms.csv` carries gates, which it never has. **No budget raise.** The four families cost 434 characters and 1,065 were reclaimed first, from `Args:` glosses restating a parameter name the schema already carries (`quest_index: Quest index to accept.`, eleven copies of `kami_id: Kami token index.`); glosses carrying a mechanic were kept. P1 mass 71,643 -> **71,012**, 988 characters of headroom against the unchanged 72,000 budget. P2 `tools_hash` `f3734714...ac43` -> `e7b0e942...9c09`. Seven invariant rows added (harvest gas vs measured p95, the lane cap and the docstring caps, gate evaluation and refusal, gate-type coverage, the starving gate, `NOT_READY`). Mass, version, pin and invariant rows updated. |
| 11 | 2026-08-28 | Re-pinned to `ede7b80` (SCHEMA_VERSION **3.5.0**). **MINOR**: two tools added (`act_sequence`, `lens_skills`; P1 count 102 -> 104, ACT 55 -> 56, PERCEIVE 31 -> 32, `READ_TOOLS` 39 -> 40), optional result fields on `liquidate_kami`, one description reworded (`lens_node`), nothing removed or renamed; P4 extended. D1 advances `8b74007` (0.5.2) -> `9488894` (0.5.3), built against each other. Source: the four `zero_cd_play` entries of Anatoly's fourth play session (2026-08-28; lab docket HARNESS_350_DOCKET, rulings R-1..R-3). Four families. **(A) `act_sequence(steps, account)`** — up to 16 actions from a closed vocabulary (feed, liquidate, harvest_start, harvest_stop) signed on consecutive nonces read ONCE at `pending` and broadcast before any receipt is read. Measured live at gate 1 (two Energy Drink feeds on kami 12649, nonces 1513/1514): both broadcasts accepted, blocks 32678986/32678987 with the same second-timestamp, 0.974 s first send to second receipt — so the description's claim is 'within a block or two', not 'one block'. Static whole-sequence validation (ownership, item balance vs feed count, victims ACTIVE, killer HARVESTING or started earlier in the sequence, gas vs the sum of ceilings); `eth_call` dry-run for step 1 ONLY, because later steps' preconditions are earlier steps' effects. Fixed ceilings per op, never estimateGas. P4 gains the sequence paragraph: K per-step terminal states in `steps[]` (success / reverted / unconfirmed / not_sent, receipt fields where a tx exists), call status `complete` / `partial` which is NOT a terminal state, the three-state rule binds each step, a reverted step consumes its nonce, is final and is never resent, a broadcast-rejected step is re-signed at most once, the call raises only when step 1 fails pre-send. The general `no_wait` mode the feedback asked for was refused by ruling (R-1): it would put a fourth, in-flight state on every ACT tool the benchmark agents call with defaults. **(B) The decoded kill** on `liquidate_kami` and every liquidate step: `victim_gross` (max non-zero `ComponentValueSet` write to the victim harvest entity — the kami-oracle musu.py rule, verified equal to the oracle's `harvest_liquidate.amount` on all four kills of the 32677494–32677564 session), `spoils` (LAST write to the killer's harvest entity minus its pre-send bounty — asymmetric on purpose: the killer entity's writes are `[prev, new]` with no zero, so the drain rule misreports them both ways), `attacker_hp_after`, `cooldown_until`, and `recoil` on the single-call form only (a sequence step has no per-step pre-read; the field is omitted, never invented). `salvage` deliberately absent: the victim inventory write is absolute and its prior value is not in the receipt. A decode failure yields `null` + `decode_error` and never fails a landed tx; the pinned RPC is not an archive node and no historical read is assumed. **(C) `lens_skills(kami_index=-1)`**: the registry, or a kami's `unspent` + `invested[]`; EXPOSURE row `lens-skills` deferred -> served (40). **(D) lens 0.5.3 passthrough**: `lens_node.eligible_only` keeps TARGET-side rows (occupant HP under the attacker's threshold) and `attacker.blocked` names the attacker's own gate (null when clear) — before it, a starving attacker's read answered `harvestsEligible: 0` with 20+ targets under threshold, indistinguishable from an empty node (node 35, block 32677631). Not servable below 0.5.3: a 0.5.2 daemon answers the old meaning with `ok: true`, so the lab redeploys the lens first. **(E)** `feed_kami` gains a measured ceiling 3,500,000 (p50 1,361,543 / p95 2,185,084 / p99 2,203,762 / max 2,639,799 over 329,709 successful `system.kami.use.item` txs since 2026-06-01; aligned with `travel_use_item`, same system, and this table's own 1.5x p99 floor) — it estimated per call before. **Budget 72,000 -> 73,000** by operator ruling R-2 (2026-08-28) for the named capability *pipelined action sequences*; the four families cost 2,100 characters, four trims reclaimed 288 first, and P1 mass lands 71,012 -> **72,857** with 143 of headroom — the registry has no slack left below the two standing sentences, and the next capability needs a raise, not a trim. P2 `tools_hash` `e7b0e942...9c09` -> `a4e9aaf5...4c63`. Eleven invariant rows added; 680 tests. |
| 12 | 2026-08-28 | Re-pinned to `3d128bf` (SCHEMA_VERSION **3.6.0**). **MINOR**: no tool, parameter or schema added, removed or renamed (count 104, classes unchanged), but `act_sequence`'s description moves (`max 16` -> `max 64`; the burst claim reworded to 'a few blocks'), so the fingerprint moves: P2 `tools_hash` `a4e9aaf5...4c63` -> `87dc7481...1c1b`; P1 mass 72,857 -> **72,855**. Source: Anatoly's fifth/sixth play sessions on 3.5.0 (report `2026-08-28-instant-strike-limits.md`: 20 kills, deploy -> kill in 3 blocks, decoded spoils == banked delta exactly) and his three asks; lab brief HARNESS_360_BRIEF. Three families. **(A) Step cap 16 -> 64 by operator re-ruling of R-3 (2026-08-28) on a MEASUREMENT, not a guess**: `executor/tests/live/measure_mempool_acceptance.py` drove feed-only sequences of 32 / 48 / 64 consecutive nonces from one sender through the shipped internals — 64/64 accepted, zero rejections at every rung, all mined within 3 s of chain time (blocks 32683438-32683445); the ceiling was NOT reached (drink budget exhausted: 148 Energy Drinks, 159,439,711 gas, ~0.0004 ETH), so the cap sits at the largest measured acceptance and is not raised past its evidence. Chain fact recorded: the node lands **9 of one sender's transactions per block** (blocks of nothing but ours at 9,676,854 of 45,000,000 gas — a per-block admission ceiling, not gas pressure), so an N-step burst spans ~N/9 blocks. Operator note absorbed: future feed-path measurements use the cheapest consumable (Ghost Gum) — Energy Drinks are crafted and scarce. **(B) Batch broadcast**: the pre-signed tail goes out as ONE JSON-RPC batch body over the provider's `make_batch_request` (web3 v7's `batch_requests()` forbids `eth_sendRawTransaction` by a library guard, pinned by a test so a future upgrade fails loudly); batch ids ARE the nonces, so responses map back by nonce and a missing response is `not_sent`, never guessed; the first rejection-marker item still triggers the once-only re-sign of the tail; serial survives only as a transport fallback (rows carry `broadcast: "serial"`). Measured: 32 items 0.500 s (vs ~13 s serial), 64 items 2.354 s (vs ~27 s). Recorded honestly: a batched tail's later items were physically offered to the node — `not_sent` there is a claim about intent, held by the nonce gap. **(C) Receipt-side kill decode**: `attacker_hp_after` and `cooldown_until` now come from the kill receipt's own `ComponentValueSet` writes on the killer entity (`component.stat.health`, a packed Stat of four signed 64-bit fields with `sync` last; `component.Time.Next`) — 3.5.0 read them LIVE at decode time, so every row of a burst carried the last step's state (burst 32682485-96: 3.5.0 said 1787938453 on all four kills; the receipts say ...418 / ...421 / ...422 / ...453, and the last — where the live read was known-correct — matches). No live read inside a decode on either path; `liquidate_kami` uses the receipt too (two fewer round-trips); a missing write is `null` + `decode_error`. Ten invariant rows; 701 tests. Receipt COLLECTION remains serial (~0.25 s/step wall after the chain is done) — a named, deliberate gap for a later release. SETUP.md's lens version corrected 0.5.1 -> 0.5.3 (drift since 3.3.0). |

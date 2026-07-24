---
module: kami-harness
version: 2
describes: 48bd154
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

- The registry advertises exactly **99 tools**.
- Every registered tool carries exactly one class tag in
  `server.TOOL_CLASSES`; the tag set is `{ACT, PERCEIVE, OUTSOURCE,
  META}` and the key set equals the registered tool names exactly.
- Class counts: **ACT 54 / PERCEIVE 29 / OUTSOURCE 9 / META 7**.
- Class meanings, as the code partitions them:
  - `ACT` — signs and broadcasts at least one transaction.
  - `PERCEIVE` — world-state read; signs nothing, changes no remote state.
  - `OUTSOURCE` — reaches the third-party strategy service.
  - `META` — wallet, account-registry, and bridge infrastructure; not
    world state.
- `server.READ_TOOLS` is the non-mutating subset: **37 tools** = all 29
  `PERCEIVE` + 5 `OUTSOURCE` reads + 3 `META` reads. `ACT ∩ READ_TOOLS`
  is empty.
- Every served input schema is portable: no `anyOf`, `oneOf`, `allOf`,
  or `$ref` appears in any tool's `parameters`, and no `title` key
  survives to the wire.
- Every `READ_TOOLS` description ends with the standing sentence
  `server._UNTRUSTED_STANDING_SENTENCE`; every `lens_*` description also
  carries `server._LENS_SERVING_SENTENCE`. Non-read tools carry neither.
- Agent-visible registry mass — `len(name) + len(description) +
  len(json.dumps(parameters))` summed over the live registry — is
  **65,942 characters** at this ref.

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
- Value at this ref:
  `9e236f902fe169aea73fe32d7ca3c1f1e8c683d4d27e6f6a313aba4b5083ada8`.

### P3 — SCHEMA_VERSION

- `executor/schema_version.py` exports `SCHEMA_VERSION = "2.0.0"`,
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

- A returned result never carries `status="reverted"`.
- `OnChainRevertError.reason` is a best-effort `eth_call` replay of the
  exact calldata at the block the transaction landed in; it is `None`
  when the replay does not revert or the RPC refuses, and the message
  says so rather than inventing a reason.
- Nonce/retry logic never resubmits a confirmed revert or an unconfirmed
  transaction.
- Multi-transaction tools raise `BatchTxError` when any item failed. The
  error message carries **every** per-item outcome, successes included,
  and states that successful items are final on-chain and must not be
  resubmitted.
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
- At this ref the only capability flag is `KAMI_CHAT_ENABLED` (default
  off), gating `lens_chat` (PERCEIVE) and `chat_send` (ACT); both answer
  `CHAT_DISABLED` when off, and neither opens the daemon socket or signs
  anything in that state.
- Tool count, registry mass, and `tools_hash` are byte-identical across
  every combination of `KAMI_CHAT_ENABLED` and `PRESENTATION_MODE`. A
  client's recorded fingerprint therefore identifies the surface, not
  the operator's configuration.

### P7 — EXPOSURE.md as the exposure-precedent registry

- `EXPOSURE.md` holds one row per READ tool on the live registry — **37
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

- **Pin:** `a0a3e1e` (kami-lens release 0.2.0), recorded as
  `server.KAMI_LENS_PIN`.
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
  - `travel_to_room` — `GET /api/accounts/{operator}` for room, stamina,
    and inventory before routing.
  - `level_to`, `level_and_allocate_batch`,
    `feed_level_allocate_batch` — `GET /api/playwright/kami/{id}/` for
    current level before issuing level transactions.
  - `get_scavenge_droptable` (PERCEIVE) — `GET /api/playwright/nodes`
    for node metadata; the droptable weights themselves come from chain
    component reads.
- **Blast radius:** an outage of this third party therefore reaches **4
  ACT tools and 1 PERCEIVE tool** in addition to the 9 OUTSOURCE tools.
  See deviation X2.
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

### D5 — `.env` key injection contract

- **Location:** `~/.blocklife-keys/.env`, deliberately outside the
  repository.
- **Read:** `{LABEL}_OPERATOR_KEY` and `{LABEL}_OWNER_KEY` (label
  uppercased). A label present with only `{LABEL}_OWNER_KEY` loads as an
  owner-only account — it is visible in `list_accounts` and
  `get_gas_balance`, and every operator path raises a factual
  no-operator-wallet error.
- **Written back by the server:** `{LABEL}_OPERATOR_KEY` (by
  `create_operator_wallet`, which generates the keypair in-process),
  `{LABEL}_KAMIBOTS_API_KEY` and `{LABEL}_PRIVY_ID` (by
  `register_kamibots`).
- `accounts/roster.yaml` maps labels to public addresses. Private key
  material never appears in any tool return value.
- **Assumption:** the file is readable and writable by the server
  process and is not indexed by any connected client.

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
| Registry description mass ≤ 66,000 characters, measured from the live registry | `test_tool_surface.py::test_registry_mass_within_budget` (65,942 at this ref) |
| The registry advertises exactly 99 tools | `test_tool_surface.py::test_tool_surface_count` |
| Every registered tool is class-tagged, and no tag names an absent tool | `test_tool_surface.py::test_taxonomy_covers_registry_exactly` (also pins ACT 54 / PERCEIVE 29 / OUTSOURCE 9 / META 7) |
| Tools removed at this version stay absent | `test_tool_surface.py::test_removed_tools_absent` |
| Every READ tool has an EXPOSURE.md row; no row names a non-READ or absent tool | `test_tool_surface.py::test_exposure_rows` |
| Named deferred reads and unserved ACT rows stay present in EXPOSURE.md | `test_tool_surface.py::test_exposure_rows` |
| Operator keys are only ever escrowed; an owner private key never crosses the wire | `test_outsource.py::TestEnableStrategies::test_owner_key_never_in_request` — asserted on a split account whose owner and operator keys differ, so it cannot pass by key coincidence |
| The escrow request body is exactly `{"operatorKey": <operator key>}` and the service echoes the matching address or the call raises | `test_outsource.py::TestEnableStrategies::test_posts_operator_key_exactly`, `::test_address_echo_mismatch_raises` |
| An account with no operator wallet has nothing to escrow and issues no request | `test_outsource.py::TestEnableStrategies::test_owner_only_account_refuses` |
| `tools_hash` is 64 lowercase hex chars, recomputes identically, and equals the handshake `instructions` value; `serverInfo.version` equals `SCHEMA_VERSION` | `test_tool_surface.py::test_tools_hash_present_and_deterministic` |
| `tools_hash` is stable across capability-flag settings | **unenforced** — no test asserts it. Verified by hand at this ref: identical across `KAMI_CHAT_ENABLED` × `PRESENTATION_MODE` |
| `SCHEMA_VERSION == "2.0.0"` | `test_tool_surface.py::test_schema_version` |
| Docstrings are mechanism-only: no advisory or endorsement language in either direction | **partially enforced** — `test_tool_surface.py::test_h3_docstrings_stay_mechanical` covers 8 ACT tools against a banned-phrase list; `::test_enable_strategies_docstring_facts` covers 1 tool against a second list. The remaining 90 tools are **unenforced** |
| No deployment-context references in agent-visible tool descriptions | **unenforced** — no scrub scan exists in this repository. Verified by hand at this ref: all 99 descriptions are clean |
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
| `get_scavenge_points` | chain component reads | no lens scavenge query at pin `a0a3e1e` |
| `get_scavenge_droptable` | Kamibots node metadata + chain weights | no lens scavenge query at pin `a0a3e1e` |
| `get_item_orderbook` | chain event-scan + component reads | per-item book exceeds `lens_trades` at this pin |
| `get_gas_balance` | Yominet + mainnet RPC | wallet infrastructure |
| `list_accounts` | local roster / env | local configuration |
| `bridge_status` | Initia router API + RPC | cross-chain transport state |

**X2 — `third-party-reach-into-ACT`.** Internal Kamibots reads sit
inside four ACT tools (`travel_to_room`, `level_to`,
`level_and_allocate_batch`, `feed_level_allocate_batch`) and one
PERCEIVE tool (`get_scavenge_droptable`). A strategy-service outage
therefore reaches action paths, not only the OUTSOURCE class. Kept
because no equivalent read exists at lens pin `a0a3e1e`. The correct
resolution is a lens query, not a fallback.

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

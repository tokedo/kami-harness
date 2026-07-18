# Changelog

All notable changes to the **Kamigotchi environment interface** — the MCP
server surface that KamiBench agents build against — are documented here.

The version tracked here is `SCHEMA_VERSION` (see
[`executor/schema_version.py`](executor/schema_version.py)). It is surfaced
to clients as the MCP `server_version` in the initialize handshake, and it
is distinct from git tags: git tags mark repository states, `SCHEMA_VERSION`
marks the tool contract.

## Versioning policy (semver)

`SCHEMA_VERSION` follows [semantic versioning](https://semver.org):

- **MAJOR** — a breaking change to an existing tool: a renamed or removed
  tool, a changed or removed parameter, or changed semantics/return shape
  that existing callers relied on. Agents must be updated.
- **MINOR** — additive, backward-compatible changes: a new tool, or a new
  *optional* parameter on an existing tool. Existing agents keep working.
  This is the expected path for future studies.
- **PATCH** — non-semantic changes: documentation fixes, wording, catalog
  data refreshes, internal refactors that do not change the tool contract.

## [1.5.0] — Droptable/sacrifice reveal correctness: string commit IDs, estimated gas

No tool added or removed (**84 tools**, unchanged). Ships as MINOR with
one nominally breaking schema change, declared here explicitly: the
`commit_ids` parameter of `droptable_reveal` and `sacrifice_reveal`
changes `array of integer` → `array of string`, and every returned
commit ID (`scavenge_claim`, `scavenge_claim_and_reveal`,
`sacrifice_reveal`) is now a decimal string. Commit IDs are uint256
entity IDs (> 2^128); they exceed IEEE-754 float precision, so no
JSON-boundary caller could ever have round-tripped the integer form
correctly — the integer contract was unusable for its purpose, and no
working caller existed to break. Origin: the scavenge-path fix in
kami-hybrid-play commit `74b1af6` (2026-07-15), merged here into the
v1.4.0 validated tool bodies; the sacrifice-path string typing closes
the inconsistency that fix left open (flagged in hybrid-play's own
delta ledger). Egress surface unchanged: no new hosts.

### Changed — commit IDs cross the MCP boundary as strings

- `droptable_reveal(commit_ids: list[str])` and
  `sacrifice_reveal(commit_ids: list[str])` accept decimal or 0x-hex
  strings (`_parse_commit_id`; ints still accepted from internal
  callers). Schemas stay in the portable subset (plain
  `array`/`string`, no `anyOf`/`oneOf`).
- `scavenge_claim` and `scavenge_claim_and_reveal` return `commit_ids`
  as decimal strings; `sacrifice_reveal` echoes the revealed IDs as
  decimal strings.
- Known residual (out of this release's scope): `sacrifice_kami` still
  returns its `commit_ids` as integers — recorded for a future release.

### Changed — droptable reveal gas is estimated per call

Reveal gas scales with the roll count inside each commit (~1,130
gas/roll measured; per-roll RNG loop), so the fixed 2M limit ran large
scavenge claims out of gas. `droptable_reveal` and the reveal step of
`scavenge_claim_and_reveal` now send with `eth_estimateGas × 1.5`. The
estimate doubles as a preflight under the v1.4.0 validation
convention: a doomed reveal raises the stable
`validation failed; no transaction sent:` marker (it does not adopt
hybrid-play's `status=reverted_preflight` result dict), so the
validation/revert split in invalid-attempt analyses stays mechanical.
All v1.4.0 pre-tx validation on the touched tools is preserved
verbatim in effect: empty-commit_ids guard, registered-operator check,
scavenge claimable-tier check, and the eth_call dry-run of the exact
calldata.

### Changed — `scavenge_claim_and_reveal` retries and reports honestly

- Still waits for the next block after the claim, then retries the
  reveal up to 3 times, 3 seconds apart, inside the reveal window: a
  commit must be revealed in a later block than its claim and within
  256 blocks (~6 min) — the reveal seed is the claim block's
  blockhash, which stops being available after 256 blocks, so an
  expired commit cannot be revealed by any player action. The window
  is stated factually in the docstrings and error text.
- Removed the v1.4.0 mislabel: a reveal revert was reported as
  `reveal_skipped: "reveal reverted — items likely granted directly by
  claim"`, which mislabeled an out-of-gas revert as success. A failed
  reveal now returns the claim result, the commit IDs, and the last
  failure as it occurred (preflight raise or on-chain revert), with no
  interpretation added.

### Tests

- String/hex commit-ID parsing, including a value above 2^53
  round-tripping exactly through the string form.
- Preflight-failure path: raises with the validation marker, nothing
  sent; `scavenge_claim_and_reveal` retry and expiry paths (retries
  succeed / exhaust; no `reveal_skipped` key survives).
- Regression: all three touched tools fail their v1.4.0 validation
  cases identically (empty commit_ids, unclaimable tier, empty
  sacrifice batch).
- Full suite green keyless (no network).

## [1.4.0] — Pre-transaction validation, error legibility, revive paths

Additive (MINOR) release: no tool added or removed (**84 tools**,
unchanged), one new *optional* parameter (`revive_kami.method`, default
`"onyx"` preserves the previous behavior). The behavioral change across
write tools — preconditions that fail are now reported *before*
broadcasting instead of as on-chain reverts — spends strictly less gas
and cannot break an agent contract: no caller could rely on paying for
a revert to learn about it. Egress surface unchanged: no new hosts.

### Added — pre-transaction validation on game-system writes

Every game-system write now validates mechanically-determinable
preconditions against chain state before signing, generalizing
`transfer_kami`'s existing state-precheck + dry-run pattern. A failed
validation raises an error whose message starts with the stable marker
`validation failed; no transaction sent:` — no gas is spent and nothing
is broadcast. A result with `status="reverted"` can therefore only mean
a broadcast transaction reverted on-chain (state changed between
dry-run and inclusion); analyses can classify the two separately.

Sender-level gates (all operator- and owner-signed system writes):

- **Registered account** — operator writes resolve the operator through
  `component.address.operator`'s reverse index (the on-chain
  `LibAccount.getByOperator` lookup); owner writes check the account
  entity's name component. `system.account.register` itself is exempt
  (it creates the account). Positive results are cached per process.
- **Gas balance** — with a known gas limit, balance must cover
  `gas_limit x flat fee + value` (error names observed vs required);
  without one, a zero balance is rejected outright.
- **eth_call dry-run** of the exact calldata from the signing address —
  reverts surface pre-broadcast carrying the chain's revert string.
- **Empty-batch rejection** — a batch write whose target array is empty
  is a validation error (`executeBatched` over an empty array was
  observed in experiment 001 to execute as an on-chain status=1 no-op
  "success"). Enforced per-tool with named messages and again in the
  batch sender as a backstop; the existing empty-array guards on
  transfer/marketplace/sacrifice/equip tools were reclassified to the
  same validation-error type.

Per-tool prechecks (validation coverage, tool -> preconditions checked
before the generic gates):

| Tool | Prechecks |
|---|---|
| `harvest_start` | non-empty batch; registered; each kami owned + RESTING |
| `harvest_stop` / `harvest_collect` | non-empty batch; registered; each kami owned + harvest entity ACTIVE |
| `stop_harvest_batch` | non-empty batch; registered (per-kami failures stay silent skips by design) |
| `move_to_room` | registered; target differs from current room; live stamina >= 5 (system.getter view, regen-projected); non-adjacent target names the current room |
| `travel_to_room` | registered (planner + per-hop gates unchanged) |
| `accept_quest` | registered; quest not already accepted/completed |
| `complete_quest` / `drop_quest` | registered; quest accepted; not already completed |
| `feed_kami` | registered; kami owned; holds the item |
| `use_item_batch` | count >= 1; registered; kami owned; holds `count` of the item |
| `use_account_item` | amount >= 1; registered; holds `amount` of the item |
| `level_up_kami` / `level_to` | registered; kami owned (XP via dry-run) |
| `upgrade_skill` / `allocate_skills` | registered; kami owned; non-empty plan |
| `equip_item` | registered; kami owned; holds the item |
| `unequip_item` | registered; kami owned |
| `name_kami` | name 1-16 bytes; registered; kami owned; holds 1 Holy Dust (11011) |
| `burn_items` | non-empty; parallel arrays; amounts >= 1; registered; holds each amount |
| `listing_buy` | non-empty; registered |
| `craft_item` | amount >= 1; registered |
| `speed_craft_batch` | count >= 1; registered |
| `level_and_allocate_batch` / `feed_level_allocate_batch` | non-empty targets; registered |
| `scavenge_claim` | registered; accumulated points cover >= 1 tier |
| `droptable_reveal` | non-empty commit_ids; registered |
| `buy_kami` | listing exists (existing); owner balance covers live total + gas provision |
| `revive_kami` | registered; kami owned + DEAD; holdings for the chosen path |
| trade/auction/marketplace/transfer/sacrifice writes | sender-level gates (their pre-existing prechecks unchanged) |

### Added — `revive_kami` revive-path argument

New optional `method` parameter (plain string enum — portable schema
subset, no oneOf/anyOf): `"onyx"` (default; system.kami.onyx.revive,
consumes 33 Onyx Shards, restores HP to 33), `"red_ribbon_gummy"`
(item 11001, +10 HP), `"melkarth_spell_card"` (item 11002, +50 HP),
`"djed_pillar"` (item 11003, +5 HP), `"pale_potion"` (item 11004,
+75 HP). Item paths go through `system.kami.use.item`. All five paths
verified against the on-chain item registry (`registry.item` entities)
and both systems resolved on-chain 2026-07-18. The docstring documents
each path's cost and effect factually; no path is recommended.

### Changed — error legibility standard

New validation errors state the failed precondition factually with
observed vs required values ("account stamina is 3; a room move
requires 5", "kami #5 is HARVESTING; harvest_start requires RESTING",
"no account is registered for operator 0x9bff...0076 (account
'main')") — no next-step suggestions, no tool recommendations. Where a
raw RPC error passes through and the underlying precondition is
mechanically known, the factual statement is prepended to the raw
error instead of surfacing the bare chain string: an unfunded sender's
"account init1... does not exist: unknown address" (undiagnosable as
observed in the field) now arrives as "operator wallet 0x...
(account '...') holds 0 ETH on Yominet; the transaction requires gas
paid in ETH from this wallet. Raw RPC error: ...".

### Changed — `withdraw_operator` estimate-based gas reserve

The full-balance sweep's gas reserve was a constant
(250k gas x flat price) that underestimated MiniEVM's actual
requirement — two sweeps reverted during experiment 001 cleanup while
explicit smaller amounts succeeded. The reserve is now
`eth_estimateGas x2` (observed MiniEVM transfer costs vary: ~21.1k gas
to an EIP-7702 delegated EOA, where a bare 21k limit runs out of gas;
~113k for a plain transfer; ~174k on first touch of the recipient;
full-balance sends observed to need ~2x the gas-fee reserve to clear —
measurements from kami-lab's provisioning/sweep_funds.py). The exact
sweep value is re-verified with a second `eth_estimateGas` before
signing, and the transaction is sent with the estimate-based gas
limit. Explicit-amount withdrawals get the same estimate-based
provision. Parameters unchanged.

### Changed — Kamibots API observed-behavior notes (investigation)

- `get_inventory` — the HTTP 400s recorded on every arm of experiment
  001 are not reproducible: the identical request (same route, params,
  header) returns 200 for every registered account as of 2026-07-18.
  Upstream state, not request shape; docstring records both
  observations.
- `get_leaderboard` — upstream returns
  `{"error": "Failed to get leaderboard", "message": "Internal server
  error"}` for both types, under HTTP 500 on some requests and HTTP
  200 on others (both observed 2026-07-18). The docstring states that
  a 200-status error object is returned as the tool result and how to
  recognize it.
- `get_guild_members` — the 403s are the documented tier restriction:
  HTTP 403 for accounts whose tier is not GUILD/TEAM, 200 otherwise
  (both observed live). Docstring states the status-code behavior.

### Tests

- New offline module `test_validation.py` (92 tests): sender-level
  gates driven through the real send path against a faked chain
  (registration, gas balance with observed-vs-required text, dry-run
  revert reasons, unknown-address prepend, empty-batch backstop,
  register-account exemption); registration/state/holdings helpers
  against fake components (including the inventory.instance keccak
  derivation); every per-tool precheck happy + each failure path;
  revive_kami's five paths and schema; buy_kami's balance gate;
  error-format stability (prefix, `_revert_text`).
- `withdraw_operator` tests rewritten for the estimate-based reserve
  (sweep, below-reserve, re-verify escalation, explicit-amount,
  estimation-failure paths).
- Full suite green with keys and keyless (no network).

## [1.3.1] — Owner-only accounts + mainnet balance in the gas view

Ships as PATCH: a behavior fix plus one additive return field. No tool
was added or removed (**84 tools**, unchanged), no input schema
changed, and no existing return field changed shape or meaning —
agents built against 1.3.0 are unaffected. The behavior fix makes a
previously broken state (owner key without operator key) load instead
of being skipped; agents could not have relied on the old skip, since
it produced an empty registry and made every tool unusable.

### Fixed
- **Owner-only accounts are first-class.** A label with
  `{LABEL}_OWNER_KEY` but no `{LABEL}_OPERATOR_KEY` — the starting
  state of a fresh deployment, where the owner wallet holds the
  capital and the operator does not exist yet — previously hit a
  warning-skip in account loading: zero accounts loaded,
  `list_accounts` returned `{"accounts": {}}`, `get_gas_balance`
  returned `{"balances": {}}`, and `fund_operator` reported "Account
  'main' not found. Available: (none)". The agent's actual starting
  state was represented nowhere in the agent-visible environment. Such
  labels now load as registry accounts with the operator absent:
  `list_accounts` shows them (`operator_address: null`) and
  `get_gas_balance` includes them (owner fields present, operator
  fields absent).
- **Clean no-operator errors on every operator path.** Operator
  signing and operator reading on an owner-only account raise
  `account '<label>' has no operator wallet; create_operator_wallet
  generates one` — enforced at the account-registry level, so no path
  can crash with an AttributeError/NoneType instead. Paths that wrap
  eth_call dry-runs (register_account, sacrifice, the batch equip
  loops, quest-completability reads) resolve the operator address
  before their try blocks, so the error surfaces as itself rather than
  as a wrapped "would revert" / per-item "skipped" reason.
- **`create_operator_wallet` upgrades the owner-only registry entry in
  place** — no duplicate-label conflict with the new load path, and
  credentials held only in the live registry survive the upgrade.

### Added (return field, no schema change)
- **`get_gas_balance` reports `owner_mainnet_eth`** — the owner
  wallet's Ethereum-mainnet ETH balance, read via the configured
  `MAINNET_RPC_URL`, for every account with an owner key. Without it
  the gas view of a fresh deployment read as an artificial
  0-everywhere state while the entire starting capital sat on mainnet.
  Graceful degradation: if the mainnet RPC errors or times out the
  field reads `"unavailable"`; it never raises and never blocks the
  Yominet fields beyond a short (5s) timeout. The `get_gas_balance`
  docstring changed to document the field — a recorded-surface delta
  that downstream fixture re-records will pick up.

### Recorded-surface deltas (deferred note, added with v1.4.0)
- Exactly three tool descriptions changed in this release, verified by
  a live dump-and-diff of the v1.3.0 and v1.3.1 tags:
  `create_operator_wallet` (registry entry upgraded in place wording),
  `get_gas_balance` (documents `owner_mainnet_eth` and the per-wallet
  field presence rules), and `list_accounts` (documents
  `operator_address: null` for owner-only accounts). No parameter
  schema changed.

### Config
- `accounts/roster.yaml` is now gitignored (kami-lab audit F1): it is
  per-deployment state (public addresses plus operational notes), not
  part of the interface. Created from `accounts/roster.yaml.template`.

### Tests
- Offline regression for the exact broken reproduction (owner-only
  env loads, no skip warning, non-empty `list_accounts` /
  `get_gas_balance`); clean no-operator errors across representative
  operator paths (`fund_operator`, `withdraw_operator`,
  `register_account`, `transfer_kami`, `sacrifice_kami`(+batch),
  `equip_all_batch`, `check_quest_completable`) asserting the error is
  not wrapped or converted to per-item skips; `create_operator_wallet`
  upgrading an owner-only entry in place; `owner_mainnet_eth` happy
  path, RPC-error path, and unmocked unreachable-endpoint path. The
  suite runs green without keys or network.

## [1.3.0] — Self-onboarding + mainnet bridging

4 tools added, 1 removed. **84 tools** total (was 81). Ships as MINOR:
the removal (`store_operator_key`) is nominally a breaking change, but
it existed only to escrow operator keys for Kamibots-managed strategy
execution — no KamiBench agent contract calls it, and keeping it would
contradict the interface's key-custody boundary (see Removed).

### Added
- **Onboarding** — `create_operator_wallet` generates an operator
  keypair *inside the server process*, persists `{LABEL}_OPERATOR_KEY`
  next to the owner key, hot-loads the account into the live registry,
  and records the public addresses in `accounts/roster.yaml` (the
  roster update is part of the tool, not a manual step). Only public
  addresses are returned; key material never leaves the server process.
  Refuses when an operator key already exists (no rotation).
  `register_account` performs the on-chain registration
  (`system.account.register` `executeTyped(operator, name)`,
  owner-signed, 2M gas limit / 883k observed) with 1–15-byte
  no-whitespace name validation and an eth_call dry-run that maps the
  common reverts ("exists for Owner" / "exists for Operator" /
  "name taken") to actionable errors before any gas is spent.
- **Bridging** — `bridge_eth_from_mainnet` moves Ethereum mainnet ETH
  to Yominet gas ETH at the same account's owner address (recipient
  pinned to the registry, as with every ETH-moving tool) via the Initia
  router API: single-transaction LayerZero OFT routes only
  (multi-transaction routes and unexpected ERC20 approvals are
  refused), local bech32 derivation for `init` addresses, a 6-decimal
  amount cap (the route transits a 6-decimal denom), a balance
  pre-check naming amount + bridge fee + max gas, and EIP-1559 fee
  fields. The tool returns immediately after broadcast with status
  `submitted` and the `tx_hash` — the receipt is not awaited and
  nothing after the broadcast raises, so a broadcast hash can never be
  lost to a receipt timeout. `bridge_status` carries all subsequent
  polling: best-effort tracker registration, router transfer state,
  and the Yominet arrival balance.
- The router route request declares `experimental_features:
  ["layer_zero"]` only. The game widget's flow also sends
  `allow_unsafe=true` and hyperlane/stargate/eureka feature flags;
  those were dropped — `allow_unsafe` only admits unsafe *swap* routes
  (this route has no swap) and the other bridge families must not
  become route candidates. Verified live 2026-07-10: the reduced
  request returns the identical single-transaction OFT route.

### Removed
- **`store_operator_key`** — uploaded the account's operator private
  key to the Kamibots service (for server-side strategy execution).
  This was the single place the interface moved private-key material
  off the server process, contradicting the secrets boundary that
  every other tool (including the new `create_operator_wallet`)
  maintains. `register_kamibots` stays unchanged: it provisions a
  read-API credential only. Its docs (SETUP.md §10, tool tables) and
  the "next: store_operator_key" hint inside `register_kamibots` are
  gone with it.

### Config
- `MAINNET_RPC_URL` is now **required explicit configuration** with no
  default public-endpoint fallback; the server fails loudly at startup
  when it is unset. The endpoint is part of the environment definition
  and is recorded in run manifests.

### Egress
- Exactly **two new egress hosts**: the configured `MAINNET_RPC_URL`
  endpoint (mainnet gas estimation, balance reads, broadcast) and
  `router-api.initia.xyz` (bridge route/msgs quotes, tx tracking and
  status). No other host is contacted by the new tools; removing
  `store_operator_key` also removes the only payload that carried
  private-key material to `api.kamibots.xyz` (the host itself remains,
  for reads).

### Tests
- Offline coverage for all four tools, money paths included: faked
  router quote parsing (`txs`/`msgs` shapes, missing `evm_tx`,
  ERC20-approval refusal, `txs_required != 1`), fee/balance
  arithmetic, 6-decimal rejection, bech32 vectors, keygen persistence
  + no-key-leakage + roster update, name validation, register dry-run
  revert mapping, the post-broadcast no-raise path, and a keyless
  subprocess check that startup fails without `MAINNET_RPC_URL`. The
  suite runs green without keys or network.

## [1.2.0] — Wallet / gas management

Additive (MINOR) release: 3 new tools. **81 tools** total (was 78).
Existing agents keep working unchanged. No new egress hosts: all three
tools use the existing Yominet RPC endpoint.

### Added
- **Wallet / gas management** — `get_gas_balance` (operator + owner ETH
  balances for one account, or all configured accounts when `account`
  is empty), `fund_operator` (plain ETH transfer owner → operator,
  owner-signed, with an owner-balance pre-check covering amount + gas),
  and `withdraw_operator` (operator → owner, operator-signed;
  `amount_eth="all"`, the default, sends the operator balance minus a
  gas reserve). Destinations are pinned to the same account's registry
  addresses — an arbitrary recipient is not expressible in the tool
  parameters. Plain transfers provision 250k gas: a plain ETH transfer
  on Yominet burns ~113k gas (Initia MiniEVM), not the standard 21k.
  Insufficient-balance errors name the balance, the requested amount,
  and the gas provision.

### Tests
- Offline coverage for all three tools (happy + error paths). Balance
  reads and transaction sending are faked; the tests run without keys
  or network.

## [1.1.0] — Marketplace, transfers, sacrifice, order book

Additive (MINOR) release: 14 new tools and backward-compatible patches to
4 existing tools. **78 tools** total (was 64). Existing agents keep
working unchanged.

### Added
- **KamiSwap marketplace** — `get_kami_market_listings` (active listings
  from the Kamiden indexer), `buy_kami` (price-capped batch purchase,
  owner wallet, value-bearing tx), `cancel_kami_listing` (frees kamis
  stuck in LISTED).
- **World order book** — `get_item_orderbook`: complete per-item
  asks/bids read directly from chain state. Requires a one-time trade-ID
  bootstrap (`executor/kwob_bootstrap.py`; see SETUP.md). When the
  bootstrap cache is missing or stale the tool raises an actionable error
  instead of returning an incomplete book.
- **Account-to-account transfers** — `transfer_kami` (`system.kami.send`,
  operator wallet, 1..9 kamis) and `transfer_items`
  (`system.item.transfer`, owner wallet, 1..8 item types, 15 MUSU/type
  fee). Recipient by roster label or raw address; both pre-check state
  on-chain and dry-run via eth_call before submitting.
- **Sacrifice** — `sacrifice_kami` and `sacrifice_kami_batch` (dry-run
  gated commits at the Temple of the Wheel, room 19; reveal fires
  automatically on-chain), `sacrifice_reveal` (manual recovery for a
  failed auto-reveal).
- **Batch wrappers** — `feed_level_allocate_batch` (feed → level →
  allocate per kami, per-kami error isolation), `equip_all_batch` /
  `unequip_all_batch` (dry-run gated equipment loops), `speed_craft_batch`
  (stamina-restore/craft interleave for stamina-gated recipes).
- **Kamibots** — `get_all_strategy_statuses` (live container status,
  including containers absent from the DB listing).
- `_send_tx_owner` supports value-bearing (payable) transactions.

### Changed (backward-compatible)
- `get_account_trades` reads trade entities directly from chain state
  (IDOwnsTrade reverse mapping + batched component reads) instead of the
  Kamiden indexer with per-trade dry-run status probes. Same return
  shape; PENDING/EXECUTED status is now ground truth.
- `list_kami` converts the ETH price with exact decimal arithmetic;
  float rounding could previously misprice a listing at wei precision.
- `get_kamis_progress_batch` adds `hp_sync`, `hp_rate`, `harvest_state`,
  and `harvest_balance` fields per kami.
- `list_open_sell_offers` states its discovery bound and cross-references
  `get_item_orderbook` for the complete per-item book.

### Tests
- Offline test suite covering every new and changed tool (happy + error
  paths). Chain, indexer, and Kamibots API access are faked; the suite
  runs without keys or network.

## [1.0.0] — Environment-interface baseline

First release of `kami-harness` as a pure environment interface for
KamiBench. Establishes the versioned tool contract.

### Changed
- Repurposed the repo from an agent-with-policy harness into a pure
  **environment interface**: mechanics (tool schemas, catalogs, system
  docs, integration references) stay; agent policy (strategy, memory
  schema, decision procedures, operating-mode runners) was removed.
- Rewrote every MCP tool description to be **descriptive, not
  prescriptive**: each states what the tool does, its inputs/outputs, and
  the world mechanics it touches — not when or why an agent should use it.
- Rewrote `README.md` as an interface specification.
- Reworked `SETUP.md` to cover only environment setup (server + client).

### Removed (policy content — extracted to a private experiment repo)
- `strategies/` — calibrated decision heuristics.
- `CLAUDE.md` — playing-agent instructions and per-tick decision priorities.
- `systems/memory.md` — agent memory schema and templates.
- The per-tick decision checklist and strategy/memory layer prose from the
  README; the Hybrid/Autonomous operating-mode narrative from SETUP.
- The autonomous session runner and prompt templates.

The extracted policy content, and a `judgment-sweep` audit record of every
judgment sentence removed and its source location, were relocated to a
private experiment repo — they are not part of this environment interface.

### Added
- `SCHEMA_VERSION` (`executor/schema_version.py`), surfaced via MCP
  `server_version`.
- This `CHANGELOG.md` and its versioning policy.

### Tool surface
- 64 MCP tools across setup, reads, on-chain actions, batch wrappers,
  quests, scavenge, and trading. Unchanged in count and behavior from the
  `v0-pilot` state — only descriptions were rewritten.

[1.5.0]: https://github.com/tokedo/kami-harness/releases/tag/v1.5.0
[1.4.0]: https://github.com/tokedo/kami-harness/releases/tag/v1.4.0
[1.3.1]: https://github.com/tokedo/kami-harness/releases/tag/v1.3.1
[1.3.0]: https://github.com/tokedo/kami-harness/releases/tag/v1.3.0
[1.2.0]: https://github.com/tokedo/kami-harness/releases/tag/v1.2.0
[1.1.0]: https://github.com/tokedo/kami-harness/releases/tag/v1.1.0
[1.0.0]: https://github.com/tokedo/kami-harness/releases/tag/v1.0.0

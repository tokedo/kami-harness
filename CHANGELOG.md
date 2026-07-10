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

[1.3.0]: https://github.com/tokedo/kami-harness/releases/tag/v1.3.0
[1.2.0]: https://github.com/tokedo/kami-harness/releases/tag/v1.2.0
[1.1.0]: https://github.com/tokedo/kami-harness/releases/tag/v1.1.0
[1.0.0]: https://github.com/tokedo/kami-harness/releases/tag/v1.0.0

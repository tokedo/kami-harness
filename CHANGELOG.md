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

[1.1.0]: https://github.com/tokedo/kami-harness/releases/tag/v1.1.0
[1.0.0]: https://github.com/tokedo/kami-harness/releases/tag/v1.0.0

# Kamigotchi MCP Executor

An MCP server that reads private keys from `~/.blocklife-keys/.env`
(outside the repo) and exposes game actions as tools. The connected MCP
client never sees secrets.

```
MCP client --MCP--> executor (server.py) --> kami-lens daemon (local unix socket; world reads)
                                         \-> Yominet RPC (transactions)
                                         \-> Kamibots API (strategy delegation)
                                         \-> Ethereum mainnet RPC + router-api.initia.xyz (bridge)
```

## Account labeling system

Each account has a **label** (e.g., `main`, `farm1`). The label ties
together private keys in `.env` and public addresses in `roster.yaml`:

| File | Contains | Visible to LLM |
|---|---|---|
| `~/.blocklife-keys/.env` | `{LABEL}_OPERATOR_KEY`, `{LABEL}_OWNER_KEY` | No (outside repo, hook-blocked) |
| `accounts/roster.yaml` | Label, owner address, operator address | Yes (in-repo; gitignored per-deployment state) |

Keys live **outside the project directory** at `~/.blocklife-keys/.env`.
Some MCP clients auto-index files in the working directory on startup —
keeping keys external means there is nothing sensitive in the tree to read.

On startup, the server scans `~/.blocklife-keys/.env` for all
`*_OPERATOR_KEY` / `*_OWNER_KEY` pairs, builds an account registry,
and cross-references with `roster.yaml` (warns on mismatches).

All per-account tools accept an `account` parameter (default `"main"`).

## Setup

```bash
cd executor
pip install -r requirements.txt
```

## Initialization flow

1. **Create keys file** outside the repo:
   ```bash
   mkdir -p ~/.blocklife-keys
   cp env.template ~/.blocklife-keys/.env
   # Edit ~/.blocklife-keys/.env: set MAIN_OPERATOR_KEY, MAIN_OWNER_KEY,
   # and MAINNET_RPC_URL (required; the server refuses to start without it)
   ```

2. **Fill `roster.yaml`** with public addresses:
   ```bash
   cp accounts/roster.yaml.template accounts/roster.yaml
   # Edit: set owner_address and operator_address for each label
   ```

3. **Run the kami-lens daemon** — the local world-state daemon that
   answers every PERCEIVE read. Without it those tools raise
   `LensUnavailableError`; nothing else on the surface is affected.
   Set `KAMI_LENS_SOCKET` if its socket is not at the platform default.
   Full instructions in [SETUP.md](../SETUP.md).

4. **Start MCP server** (via your MCP client's config)

5. **Register with Kamibots** (once per account, only if you intend to
   delegate strategies):
   ```
   register_kamibots(account="main")
   ```
   Signs with the owner wallet, saves API key + privy_id to `.env`.
   Starting a strategy additionally requires the explicit operator-key
   escrow step, `kamibots_enable_strategies` — see
   [OUTSOURCE](#outsource--9-tools).

6. **Ready to play** — all other tools now work.

An account that exists only as an owner key reaches the same state
through the tool surface itself — see [Onboarding](#onboarding).

## Running

The server runs as a stdio MCP server, launched by the MCP client.
Example config (Claude Code's `.mcp.json` shown):

```json
{
  "mcpServers": {
    "kamigotchi": {
      "command": "python",
      "args": ["executor/server.py"],
      "cwd": "/path/to/kami-harness"
    }
  }
}
```

## Available tools

The registry advertises **102 tools**. Every tool carries exactly
one class tag — `ACT` / `PERCEIVE` / `OUTSOURCE` / `META` — and the four
classes partition the surface completely:
**ACT 55 / PERCEIVE 31 / OUTSOURCE 9 / META 7**.
The tags live in `server.TOOL_CLASSES`; the counts are contract rows
checked by the suite ([SPEC.md](../SPEC.md) §P1).

The tables below are generated from the live registry: each row is a
tool's registered name, its parameter names in schema order, and the
first line of its description. The full description — argument
semantics, gas limits, failure modes — is what the MCP client receives
on `tools/list`, and is the authority. `39` tools are non-mutating
(`server.READ_TOOLS`): all 31 PERCEIVE, plus the OUTSOURCE and META
reads marked below.

### Pre-transaction validation (all game-system writes)

Every write that targets a game system validates mechanically-
determinable preconditions against chain state before signing:

1. **Registered account** — the signing wallet must be bound to an
   on-chain account entity (operator writes resolve through
   `component.address.operator`; owner writes check the account
   entity's name component; `register_account` itself is exempt).
2. **Gas balance** — the signer's ETH balance must cover the gas
   provision (+ transaction value where applicable).
3. **Per-tool prechecks** — ownership, state, holdings, batch shape
   (see each tool's docstring). Batch writes reject an empty target
   array (an empty `executeBatched` executes as an on-chain status=1
   no-op).
4. **eth_call dry-run** of the exact calldata from the signing
   address.

A failed validation raises `PreTxValidationError`, whose message always
begins with the exact prefix `validation failed; no transaction sent: `
— nothing was signed or broadcast and no gas was spent. It states the
failed precondition factually with observed vs required values.

After broadcast there are exactly **three terminal states**, and none is
ever reported as another:

| terminal state | how it is reported |
|---|---|
| confirmed-success | the tool returns; result carries `status="success"` with `tx_hash`, `block`, `gas_used` |
| confirmed-revert | **raises** `OnChainRevertError(tx_hash, block, gas_used, reason)` — never returned alongside or as success |
| unconfirmed | **raises** `TxUnconfirmedError(tx_hash, timeout)` — outcome unknown, the tx may still land |

A returned result never carries `status="reverted"`. `OnChainRevertError.reason`
is a best-effort `eth_call` replay of the exact calldata at the block the
transaction landed in; it is `None` when the replay does not revert or the
RPC refuses, and the message says so rather than inventing a reason.
Multi-transaction tools raise `BatchTxError` naming **every** per-item
outcome, successes included, and state that successful items are final
on-chain and must not be resubmitted.

### ACT — 55 tools

Signs and broadcasts at least one transaction. Gameplay writes use the
operator wallet; registration, minting, and value-bearing trades use the
owner wallet (noted per tool).

| Tool | Description |
|---|---|
| `accept_quest(quest_index, account)` | Accept a quest by index. |
| `allocate_skills(kami_id, skill_plan, account, allow_partial)` | Allocate multiple skill points in one call. Executes sequentially on-chain. |
| `auction_buy(item_index, amount, account)` | Buy items from the global Dutch auction (Marketplace room 66). |
| `burn_items(item_indices, amounts, account)` | Burn (destroy) items from inventory, reducing their balances. |
| `buy_kami(kami_ids, max_total_eth, account)` | Buy one or more listed kamis on KamiSwap with ETH. Owner wallet. |
| `cancel_kami_listing(kami_ids, account, allow_partial)` | Cancel this account's KamiSwap listing(s). Operator wallet. |
| `cancel_trade(trade_id, account)` | Cancel a pending trade. Returns escrowed items to inventory. Owner wallet. |
| `cast_item(target_kami_id, item_index, account)` | Use an ENEMY_KAMI-shape item on another player's kami in the account's room (system.kami.cast.item). |
| `chat_send(message, account)` | Send a chat message to the account's current room (system.chat). |
| `complete_all_trades(account, allow_partial)` | Find and complete all EXECUTED trades for this account. |
| `complete_quest(quest_index, account)` | Complete an active quest. All objectives must be met. |
| `complete_trade(trade_id, account)` | Complete an executed trade. Called by the maker (owner wallet). |
| `craft_item(recipe_index, amount, account)` | Craft items from a recipe. Consumes inputs, produces outputs, costs stamina. |
| `create_trade(sell_item, sell_amount, buy_item, buy_amount, account)` | Create a trade offer on the in-game marketplace. Uses owner wallet. |
| `drop_quest(quest_index, account)` | Drop/abandon an active quest. |
| `droptable_reveal(commit_ids, account)` | Reveal droptable commits to receive items. |
| `equip_all_batch(equips, account, delay_seconds, allow_partial)` | Equip an inventory item to many kamis (server-side loop, dry-run gated). |
| `equip_item(kami_id, item_index, account)` | Equip an inventory item to a kami. Kami must be RESTING. |
| `feed_kami(kami_id, food_item_id, account)` | Use a food item on a kami to restore HP. Works while harvesting. |
| `feed_level_allocate_batch(targets, account, allow_partial)` | Per kami: FEED consumable items, then LEVEL to a target, then ALLOCATE skills. |
| `gacha_reroll(kami_ids, account)` | Reroll kamis: deposit owned kamis into the gacha pool for random replacements (commit + reveal in one call). |
| `gacha_reveal(commit_ids, account)` | Manually reveal gacha commit(s) — recovery path. |
| `gacha_use(amount, account)` | Spend Gacha Tickets to mint new kamis (commit + reveal in one call). |
| `harvest_collect(kami_ids, account)` | Collect rewards from active harvests WITHOUT stopping them. |
| `harvest_start(kami_ids, node_index, account)` | Start harvesting for one or more kamis at a node. |
| `harvest_stop(kami_ids, account)` | Stop active harvests and auto-collect rewards. |
| `level_and_allocate_batch(targets, account, allow_partial)` | Batch level-up and skill allocation across many kamis in one call. |
| `level_to(kami_id, target_level, account, allow_partial)` | Level up a kami repeatedly until it reaches target_level. |
| `level_up_kami(kami_id, account)` | Level up a kami if it has enough XP. Grants 1 skill point. |
| `liquidate_kami(victim_kami_id, killer_kami_id, account)` | Liquidate another player's harvesting kami (system.harvest.liquidate). |
| `list_kami(kami_id, price_eth, expiry, account)` | List a kami for sale on KamiSwap (ETH price). Operator wallet. |
| `listing_buy(merchant_index, item_indices, amounts, account)` | Buy items from an NPC merchant. Must be in the merchant's room. |
| `move_to_room(room_index, account)` | Move the account to a different room. Costs stamina. |
| `name_kami(kami_id, name, account)` | Name or rename a kami. Costs 1 Holy Dust. Kami must be in room 11. |
| `newbie_vendor_buy(kami_index, max_price_eth, account)` | Buy one kami from the newbie vendor with ETH (system.newbievendor.buy). One purchase per account, ever. |
| `pool_swap(item_in, item_out, amount_in, min_amount_out, account)` | Swap one item against MUSU in a constant-product pool. |
| `register_account(name, account)` | Register the in-game account: one owner-signed transaction that creates the account entity, sets the display name, and binds the operator address. |
| `revive_kami(kami_id, method, account)` | Revive a DEAD kami to RESTING via one of the game's revive paths. |
| `sacrifice_kami(kami_id, account)` | PERMANENTLY sacrifice a kami at the Temple of the Wheel (room 19). |
| `sacrifice_kami_batch(kami_ids, account, delay_seconds, allow_partial)` | PERMANENTLY sacrifice many kamis at the Temple of the Wheel (room 19). |
| `sacrifice_reveal(commit_ids, account)` | Manually reveal sacrifice commit(s) — recovery path only. |
| `scavenge_claim(node_index, account)` | Claim scavenge rewards for a node. |
| `scavenge_claim_and_reveal(node_index, account)` | Claim scavenge rewards AND reveal droptable items in one call. |
| `skill_respec(kami_id, account)` | Reset all of a kami's skills, refunding its skill points (system.skill.respec). |
| `speed_craft_batch(recipe_index, count, stamina_item_id, account, delay_seconds, allow_partial)` | Craft a stamina-gated recipe N times, restoring stamina between crafts. |
| `stop_harvest_batch(kami_ids, account, allow_partial)` | Stop harvests for multiple kamis in one transaction; collects rewards. |
| `take_trade(trade_id, account)` | Take (execute) a pending trade as the taker. Owner wallet. |
| `transfer_items(item_indices, amounts, to_account, to_address, account)` | Transfer in-world items to another account via system.item.transfer. |
| `transfer_kami(kami_ids, to_account, to_address, account)` | Transfer in-world kami(s) to another account via system.kami.send. |
| `travel_to_room(target_room, account, use_items, dry_run, allow_partial)` | Travel to a target room via the shortest path, consuming stamina and optionally using SP+ items to extend range. |
| `unequip_all_batch(kami_ids, slot_type, account, delay_seconds, allow_partial)` | Unequip a slot from many kamis (server-side loop, dry-run gated). |
| `unequip_item(kami_id, slot_type, account)` | Unequip an item from a kami slot. Kami must be RESTING. |
| `upgrade_skill(kami_id, skill_index, account)` | Upgrade a skill on a kami by 1 point. Costs 1 SP. Kami must be RESTING. |
| `use_account_item(item_id, account, amount)` | Use a consumable on the account (operator), NOT on a kami. |
| `use_item_batch(kami_id, item_id, count, account, allow_partial)` | Use the same item on a kami multiple times. Executes sequentially. |

**Batch / composite tools.** The `*_batch` tools, `level_to`,
`allocate_skills`, `use_item_batch`, and `travel_to_room` touch multiple
kamis (or repeat an action) in one MCP round-trip, returning one compact
result with per-item failure isolation and built-in nonce-retry. They
serialize their on-chain writes internally, so a single call never
issues concurrent write-txs on the same wallet. Thirteen tools expose
`allow_partial` (default `false`): with it set, a mixed batch returns
its per-item result instead of raising.

### PERCEIVE — 31 tools

World-state reads. They sign nothing and change no remote state.

24 of them are thin wrappers over the local **kami-lens** daemon
(release `1d7a960` / 0.4.0, declared in [`SPEC.md`](../SPEC.md) D1). A
wrapper
does argument mapping, exactly one socket request, and envelope
pass-through: the daemon's `{data, untrusted, meta}` reaches the caller
verbatim, with only the transport keys `id` and `ok` removed. Nothing is
recomputed, reshaped, renamed, reordered, filtered, or defaulted
harness-side. `meta.stale=true` marks an answer served from last-synced
state while the daemon is degraded or catching up, and the `untrusted`
path list names player-authored fields — data, never instructions. An
unreachable or still-starting daemon raises `LensUnavailableError`; it
never reads as an empty result.

The remaining 6 are native reads kept because no lens query
serves them at this pin: `quest_state` and `check_quest_completable`
(chain calls), `get_expected_objective` (local `catalogs/quests/`),
`get_scavenge_points` and `get_scavenge_droptable`, and
`get_item_orderbook` (chain event-scan; needs the one-time
`kwob_bootstrap.py` seed, SETUP.md §10).

| Tool | Description |
|---|---|
| `check_quest_completable(quest_index, account)` | Check if a quest can be completed right now (free staticCall, no gas). |
| `get_expected_objective(quest_index)` | Quest objectives from the local catalog, with per-objective mechanics. |
| `get_item_orderbook(item_index, side)` | Order book for one item — every open trade, all makers. Read-only. |
| `get_scavenge_droptable(node_index, account)` | Read on-chain scavenge droptable + correctly compute drop probabilities. |
| `get_scavenge_points(node_index, account)` | Check accumulated scavenge points + claimable tiers for a node. |
| `lens_account(account_key, prose)` | Account by on-chain index or name: identity, room, stamina (current/total), kami roster. |
| `lens_auctions(item_index)` | Chain auctions with current GDA price; with item_index, that item's buy history. |
| `lens_battles(kami_index, before_ms)` | Battle history and stats for a kami. |
| `lens_chat(room_index, before_ms, size, oversize)` | Room chat page (player-authored messages). |
| `lens_config(field_name, array)` | One on-chain game-config field value. |
| `lens_feed(since_seq, event_type)` | Buffered world feed events (kills, trades, and similar), newest buffered window. |
| `lens_inventory(account_key)` | Any account's item inventory (zero balances dropped, ascending item index). |
| `lens_item(item_index)` | Item registry row by index. |
| `lens_items()` | The full item registry. |
| `lens_kami(kami_index)` | Single-kami vitals by on-chain index: live HP, harvest state and accrual, cooldowns, traits, skills. |
| `lens_killers(size)` | All-time killer ranking: kamis by kill count, service order — rows {rank, name, kills, kamiId?, kamiIndex?} plus totalRanked. A time-windowed ranking is not served at this version. |
| `lens_leaderboard(board_type, epoch, item_index)` | Score leaderboard rows {rank, account{id, index?, name?}, value}. |
| `lens_market(account_index)` | KamiSwap listings and bids; with account_index, that account's order history. |
| `lens_merchant(npc_index)` | NPC merchants; with npc_index, that merchant's full listing catalog with prices. Prices are viewer-independent; purchase gating is served as text, never applied. |
| `lens_node(node_index, with_vitals, attacker_kami_index)` | Harvest node with its ACTIVE harvests (occupant identities). |
| `lens_party(account_index)` | Party report for an account: every kami with full vitals. |
| `lens_phase()` | World day/night phase (36-hour cycle): {phase, name, cycleHour, secondsToNext, next, at}. |
| `lens_portal(account_index)` | Token portal history for an account, plus open withdrawals. |
| `lens_quests(account_index)` | Quest registry; with account_index, that account's accepted quests and completion state. |
| `lens_room(room_index)` | Room occupancy: accounts currently in the room, each with its kamis ({id, index, name, kamis[{id, index, name, state}]}). |
| `lens_roster(account_index)` | Compact roster: one line per kami (index, state, HP) plus where the account is. |
| `lens_status()` | kami-lens daemon status: sync state, live block, stream health, degraded flags, per-feed service health, and the daemon's version and configuration. |
| `lens_trades(account_index)` | Open chain trades; with account_index, that account's trade history and open offers. |
| `lens_transfers(account_index)` | Item transfer history for an account. |
| `pool_swap_quote(item_in, item_out, amount_in, slippage_bps)` | Price a MUSU-item pool swap before sending it. Reads only. |
| `quest_state(quest_index, account)` | Discriminated read of a quest's on-chain state for the account. |

### OUTSOURCE — 9 tools

Reaches the third-party strategy service: Kamibots, operated by
Asphodel, the developer of Kamigotchi. These tools hand a standing
routine (harvest/rest, feeding, crafting) to that service, which runs it
server-side.

Delegation requires an explicit escrow step.
`kamibots_enable_strategies` stores the account's **operator** private
key with the service; `start_strategy` fails until it has. The escrow
grants everything that operator wallet can sign — harvests, feeds,
moves, and kami transfers to other accounts — and stopping or deleting
a strategy does not withdraw the key. Owner keys are never sent: no tool
on this server transmits an owner private key anywhere. The account's
tier tax applies to strategy proceeds.

| Tool | Description | Read |
|---|---|---|
| `get_all_strategies(account)` | List all active strategies for this account. | yes |
| `get_all_strategy_statuses(account)` | Live container status for every Kamibots strategy on this account. | yes |
| `get_strategy_logs(container_id, tail, account)` | Recent log lines from a running strategy container. | yes |
| `get_strategy_status(kami_id, account)` | Strategy status for a specific kami. Cached 15s server-side. | yes |
| `get_tier(account)` | Account tier info: tier name, tax rate, total/used/remaining strategy slots. | yes |
| `kamibots_enable_strategies(account)` | Store this account's OPERATOR private key with the Kamibots strategy service, enabling start_strategy. | — |
| `register_kamibots(account)` | Register with the Kamibots API using the account's owner wallet. | — |
| `start_strategy(strategy_type, kami_id, node_id, config, account)` | Start a Kamibots strategy for a kami. | — |
| `stop_strategy(kami_id, permanent, account)` | Stop the running strategy for a kami. | — |

### META — 7 tools

Wallet, account-registry, and bridge infrastructure; not world state.

Destinations are pinned: `fund_operator` always pays the same account's
operator address, `withdraw_operator` the same account's owner address,
and `bridge_eth_from_mainnet` lands at the same account's owner address
on Yominet — all taken from the registry; an arbitrary recipient is not
expressible in the tool parameters.

| Tool | Description | Read |
|---|---|---|
| `bridge_eth_from_mainnet(amount_eth, account, dry_run)` | Bridge ETH from Ethereum mainnet to Yominet gas ETH. | — |
| `bridge_status(tx_hash, account)` | State of a mainnet->Yominet bridge transfer, plus arrival balance. | yes |
| `create_operator_wallet(account)` | Generate a fresh operator keypair for an account, server-side. | — |
| `fund_operator(amount_eth, account)` | Send ETH from the owner wallet to the same account's operator wallet. | — |
| `get_gas_balance(account)` | Check native ETH gas balances for the account's wallets on Yominet (and the owner's Ethereum mainnet balance when configured). | yes |
| `list_accounts()` | List all configured accounts with labels and public addresses. | yes |
| `withdraw_operator(amount_eth, account)` | Send ETH from the operator wallet to the same account's owner wallet. | — |

`fund_operator` provisions 250k gas. A plain ETH value transfer on
Yominet burns ~113k gas (Initia MiniEVM), not the standard 21k; at the
flat 0.0025 gwei gas price that is ~0.0000003 ETH per transfer.
MiniEVM transfer costs vary with the recipient (~21.1k gas to an
EIP-7702 delegated EOA, ~174k on first touch), so `withdraw_operator`
measures with eth_estimateGas instead of assuming a constant.

### Onboarding

A playable account is: an owner key in the keys file, an operator key
next to it, an on-chain account entity binding the operator address, and
an operator wallet holding gas ETH. Each of those states is reachable
through the tool surface; none requires a game client or manual file
edits. (Kamibots credentials are not part of a playable account at this
version — they are needed only to delegate strategies.)

- The game client uses a Privy embedded wallet as operator, but
  on-chain the operator is just an EOA address argument to
  `system.account.register` — no operator signature is involved in
  registration.
- `create_operator_wallet` produces the operator key state: the keypair
  is generated inside the server process, `{LABEL}_OPERATOR_KEY` is
  written next to the owner key, the account is hot-loaded into the
  live registry, and the public addresses are appended to
  `accounts/roster.yaml`. Only public addresses appear in the response.
  An account that already has an operator key is refused (rotation via
  `system.account.set.operator` is not implemented).
- `register_account` produces the on-chain state: one owner-signed
  transaction (2M gas limit; 883k observed). Names are 1–15 bytes,
  unique, whitespace-free. An eth_call dry-run runs first, so "exists
  for Owner" / "exists for Operator" / "name taken" reverts surface
  without spending gas. A newly registered account starts in Room 1
  (Misty Riverside) with 100 stamina.
- Operator gas comes from `fund_operator`; owner-side gas ETH that is
  still on Ethereum mainnet crosses via `bridge_eth_from_mainnet`
  (see [Bridging](#bridging)).
- Strategy delegation, if wanted, comes from `register_kamibots`
  (owner-signed message) followed by `kamibots_enable_strategies`.

### Bridging

Bridging converts Ethereum mainnet ETH into native Yominet gas ETH at
the same owner address. The route comes from the Initia router API
(Skip Go-compatible, the same backend as the game's InterwovenKit
bridge widget): a single mainnet transaction does a LayerZero OFT send
to Initia L1 (EID 30326), which auto-forwards over IBC channel-25 to
Yominet. Arrival is typically ~5 min after mainnet inclusion, up to
~20 min observed. Amounts transit a 6-decimal denom, so `amount_eth`
carries at most 6 decimal places.

- Only single-transaction LayerZero OFT routes are accepted: the tool
  refuses multi-transaction routes and routes requiring ERC20
  approvals.
- Before signing, the owner's mainnet balance is checked against
  amount + bridge fee + max gas; refusals name all four numbers.
- `bridge_eth_from_mainnet` returns immediately after broadcast with
  status `submitted` and the `tx_hash`; the mainnet receipt is not
  awaited, and nothing after the broadcast can raise (so the hash is
  never lost). `bridge_status` carries all subsequent polling: router
  transfer state plus the Yominet arrival balance.
- Network egress for these two tools: the configured `MAINNET_RPC_URL`
  endpoint (required, no default — the server fails at startup when it
  is unset) and `router-api.initia.xyz` (route/msgs quotes, tx
  tracking and status).

## Adding new tools

1. Identify the system ID from `integration/system-ids.md`
2. Get the ABI from `integration/api/<system>.md`
3. Add the ABI constant and `@mcp.tool()` function to `server.py`
4. Pick the serving path:
   - on-chain write: `_send_tx(account, system_id, abi, args)`
   - world-state read: `_lens_request(...)` — one request, envelope
     passed through. The thin-wrapper rule is binding: no formula math,
     no multi-query composition, no cross-query joins, no derived fields
     harness-side. A read needing any of those is deferred with a
     visible EXPOSURE.md row until the daemon serves it.
   - strategy service: `_strategy_api(...)`
5. Add `account: str = "main"` parameter to all per-account tools
6. Tag the tool: add its name to exactly one of `_ACT_TOOLS`,
   `_PERCEIVE_TOOLS`, `_OUTSOURCE_TOOLS`, `_META_TOOLS` in `server.py`.
   A missing or duplicate tag fails the suite. If the tool is
   non-mutating, add it to `READ_TOOLS` and give it an EXPOSURE.md row
   (CI-enforced in both directions); the standing untrusted-data
   sentence is appended automatically by `_finalize_descriptions()`.
7. Update the counts in `SPEC.md` §P1 and the `tools_hash` in §P2 — any
   tool added, removed, renamed, or reworded changes both.

Entity ID derivation: kami token index -> entity ID via `_kami_entity_id()`.
See `integration/entity-ids.md` for other entity types.

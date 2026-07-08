# Kamigotchi Environment Interface

This repo is the **environment interface for KamiBench**: an MCP server
that exposes *perception* (state reads) and *action* (on-chain
transactions) for Kamigotchi — a pure on-chain MMORPG on Yominet —
together with the world-knowledge docs and reference catalogs an agent
needs to interpret that surface.

It is the **contract that every KamiBench agent builds against.** The
server handles wallets, nonces, gas, retries, and API auth; an agent
connects over MCP and calls tools. Private keys live only inside the
server process and are never exposed to the connected client.

> **This repo contains no agent policy** — no strategy, no decision
> procedures, no memory schema. Those live in the separate **`kami-agent`**
> repo (the reference agent scaffold). What was removed from here during
> the environment-interface refactor is staged in
> [`migration/to-kami-agent/`](migration/to-kami-agent/) with a full record
> in [`migration/judgment-sweep.md`](migration/judgment-sweep.md).
>
> For the KamiBench project story, see **[kamibench.xyz](https://kamibench.xyz)**.

## The interface contract

```
MCP client (any KamiBench agent) --MCP--> executor (server.py) --> Kamibots API
                                                               \-> Yominet RPC
```

- **Perception** — state-read tools return account, kami, node, market,
  quest, and scavenge state.
- **Action** — transaction tools perform harvesting, movement, leveling,
  equipment, crafting, trading, quests, and scavenging.
- **Secrets boundary** — the server reads owner/operator keys from
  `~/.blocklife-keys/.env` (outside the repo) and signs on the client's
  behalf. The client never sees a key.
- **Versioned** — the tool contract carries a `SCHEMA_VERSION`
  ([`executor/schema_version.py`](executor/schema_version.py)), surfaced to
  clients as the MCP `server_version` in the initialize handshake. See
  [Versioning](#versioning).

## Tool surface

The server exposes **64 tools**. The authoritative, per-tool reference —
signatures, parameters, and behavior — is
[`executor/README.md`](executor/README.md). Grouped overview:

| Group | Tools (examples) | What it covers |
|---|---|---|
| **Setup** | `list_accounts`, `register_kamibots`, `store_operator_key` | Account registry, Kamibots API registration, operator-key delegation |
| **Reads** | `get_tier`, `get_inventory`, `get_kami_state(_slim)`, `get_kamis_progress_batch`, `get_nodes`, `get_prices`, `get_npc_prices`, `get_account_kamis`, `get_all_kamis`, `get_killer_ranking`, `get_leaderboard`, `get_account_trades` | Perception: account, kami, node, market, and ranking state |
| **Strategy execution (Kamibots)** | `start_strategy`, `stop_strategy`, `get_all_strategies`, `get_strategy_status`, `get_strategy_logs` | Kamibots-managed harvest/rest/craft loops |
| **On-chain actions** | `harvest_start/stop/collect`, `move_to_room`, `travel_to_room`, `listing_buy`, `auction_buy`, `feed_kami`, `revive_kami`, `level_up_kami`, `name_kami`, `equip_item`, `unequip_item`, `upgrade_skill`, `use_account_item`, `burn_items`, `craft_item` | Direct Yominet transactions |
| **Quests** | `get_active_quests`, `quest_state`, `get_expected_objective`, `accept_quest`, `complete_quest`, `check_quest_completable`, `drop_quest`, `get_quest_status` | Quest enumeration, state reads, accept/complete/drop |
| **Scavenge & droptable** | `get_scavenge_points`, `scavenge_claim`, `droptable_reveal`, `scavenge_claim_and_reveal` | Scavenge points, commit-reveal droptables |
| **Trading** | `create_trade`, `cancel_trade`, `take_trade`, `complete_trade`, `complete_all_trades`, `list_open_sell_offers` | P2P orderbook trades and discovery |
| **Batch wrappers** | `level_and_allocate_batch`, `level_to`, `allocate_skills`, `use_item_batch`, `stop_harvest_batch`, `get_kamis_progress_batch` | Multi-kami operations serialized in one call |

> **Concurrency:** batch wrappers serialize their on-chain writes
> internally. Two separate write-tx calls issued in parallel against the
> same operator wallet contend for the nonce; the batch wrappers exist so a
> single call never does that.

## World-knowledge docs

The interface is only useful with a model of what the returned state
*means*. These docs distil the game's mechanics into machine-readable
reference.

### Systems (`systems/`)

One file per game system — the rules an agent's world model needs.

| File | Covers |
|---|---|
| [harvesting.md](systems/harvesting.md) | Node assignment, bounty, strain, liquidation exposure |
| [health.md](systems/health.md) | HP mechanics, resting recovery, death, revival |
| [leveling.md](systems/leveling.md) | XP, level-up costs, skill trees, tier gates |
| [scavenging.md](systems/scavenging.md) | Scavenge bar, tier claiming, droptable commit-reveal |
| [liquidation.md](systems/liquidation.md) | PvP kill mechanics, affinity combat triangle |
| [crafting.md](systems/crafting.md) | Recipes, item types, using/burning/transferring |
| [trading.md](systems/trading.md) | P2P trades, marketplace, fees, tax |
| [npc-shops.md](systems/npc-shops.md) | NPC buy/sell, GDA pricing, auctions |
| [equipment.md](systems/equipment.md) | Equip/unequip, slot system, stat bonuses |
| [rooms.md](systems/rooms.md) | World map, movement, stamina cost, gates |
| [quests.md](systems/quests.md) | Quest types, objectives, rewards |
| [gacha.md](systems/gacha.md) | Minting, rerolling, sacrifice, pity system |
| [day-night.md](systems/day-night.md) | 36-hour phase cycle, phase-gated actions |
| [factions.md](systems/factions.md) | Faction reputation, quest-based rep |
| [accounts.md](systems/accounts.md) | Stats, stamina, cooldowns, owner/operator wallets |
| [state-reading.md](systems/state-reading.md) | On-chain queries, HP/stamina projection |

### Catalogs (`catalogs/`)

CSV reference data — some is loaded directly by tools (e.g.
`get_expected_objective` reads `catalogs/quests/`).

| File | Contents |
|---|---|
| [nodes.csv](catalogs/nodes.csv) | Harvest nodes: affinity, drops, level limits, scav cost |
| [items.csv](catalogs/items.csv) | Items: type, tradability, stats |
| [skills.csv](catalogs/skills.csv) | Skill trees: effects, costs, tiers, exclusions |
| [recipes.csv](catalogs/recipes.csv) | Crafting recipes: inputs, outputs, stamina cost |
| [rooms.csv](catalogs/rooms.csv) | Room map: coordinates, exits, gates |
| [shop-listings.csv](catalogs/shop-listings.csv) | NPC shop items and prices |
| [scavenge-droptables.csv](catalogs/scavenge-droptables.csv) | Node scavenge reward tables |
| [quests/](catalogs/quests/) | Quests, objectives, requirements, rewards |

### Integration (`integration/`)

On-chain interaction reference — chain ID, world contract, system IDs,
entity-ID derivation, ABIs, and the Kamibots API. See
[integration/game-data.md](integration/game-data.md) for the game-data
tables and the [file map](#file-map) below for the full index.

## World model (reference facts)

Facts the returned state is expressed in terms of.

### Core loop

```
HARVEST (earn Musu + XP) → COLLECT/STOP → REST (heal) → repeat
         ↓ side effects                      ↓ while resting
    scavenge rolls                      level up, equip, craft,
    liquidation exposure                trade, quests, move
```

All actions are on-chain transactions. Health syncs lazily on each
action — a kami's actual HP is only computed when it does something.

### Resources

| Resource | Source | Function |
|---|---|---|
| **Musu** (item 1) | Harvesting, trading, selling | Base currency: items, crafting, fees, NPC shops |
| **XP** | Harvest output (1:1), quests | Level-ups → skill points |
| **Skill Points** | 1 per level-up | Skill-tree investment (permanent bonuses) |
| **Onyx Shards** (item 100) | Scavenging, quests, drops | Revive dead kamis (33 per revive) |
| **Stamina** | Account stat, regens over time | Movement, crafting |
| **Gacha Ticket** (item 10) | NPC shop, quests | Mint new kamis |
| **Reroll Token** (item 11) | NPC shop, quests | Sacrifice a kami for a new random one |

### Kami stats

| Stat | Role |
|---|---|
| **Health** | Depletable. Drained by harvest strain, restored by resting. Death at 0 |
| **Power** | Scales harvest Fertility (base income rate) |
| **Violence** | Scales harvest Intensity (time-ramping bonus) + liquidation attack |
| **Harmony** | Reduces harvest strain, speeds resting recovery, defends liquidation |
| **Slots** | Equipment capacity (depletable) |

Effective stat: `Total = (1000 + boost) * (base + shift) / 1000`

### Affinities

Each kami has **body** and **hand** affinities from traits. Four types:
`EERIE`, `SCRAP`, `INSECT`, `NORMAL`.

- **Harvest** — matching kami affinity to node affinity yields up to 2×;
  mismatch yields 0.65×. See [systems/harvesting.md](systems/harvesting.md).
- **Combat** — rock-paper-scissors: EERIE > SCRAP > INSECT > EERIE;
  NORMAL is neutral. See [systems/liquidation.md](systems/liquidation.md).

### Cooldowns

Base cooldown after most actions is **180 seconds**, modified by the
`STND_COOLDOWN_SHIFT` bonus (skills can reduce it). See
[systems/accounts.md](systems/accounts.md).

### Chain

- **Chain**: Yominet, ID `428962654539583`
- **RPC**: `https://jsonrpc-yominet-1.anvil.asia-southeast.initia.xyz`
- **World**: `0x2729174c265dbBd8416C6449E0E813E88f43D0E7`
- **Gas**: flat `0.0025 gwei`. Cost is negligible; gas *limits* matter for
  complex calls (e.g. `harvest_start` 3M, `harvest_stop` 4M).
- **Wallets**: dual model. **Owner** registers/trades/mints; **Operator**
  is delegated for gameplay txs (via `system.account.set.operator`).

## Setup

Setting up the environment interface means configuring wallets/RPC,
running the MCP server, and connecting a client. Full instructions are in
[`SETUP.md`](SETUP.md). In brief:

1. Install server deps: `cd executor && pip install -r requirements.txt`.
2. Put owner/operator keys in `~/.blocklife-keys/.env` (outside the repo);
   see [`env.template`](env.template).
3. Map labels to public addresses in `accounts/roster.yaml` (see the
   template).
4. Register the MCP server with your client (Claude Code or any MCP
   client):
   ```json
   {
     "mcpServers": {
       "kamigotchi": {
         "command": "python",
         "args": ["executor/server.py"],
         "cwd": "/absolute/path/to/kami-harness"
       }
     }
   }
   ```
5. Smoke-test: `cd executor && python3 -m pytest tests/ -v`.

The connected client bootstraps an account by calling
`register_kamibots(account=...)` then `store_operator_key(account=...)`.

## Versioning

The tool contract is versioned with `SCHEMA_VERSION`, surfaced as the MCP
`server_version`. Policy (semver) and release history are in
[`CHANGELOG.md`](CHANGELOG.md):

- **MAJOR** — breaking change to an existing tool (name, params, semantics).
- **MINOR** — additive: new tools or new optional params. The expected
  path for future studies.
- **PATCH** — doc/non-semantic changes.

Current: **`1.0.0`** — the environment-interface baseline.

## No agent policy

This repo is deliberately policy-free. It documents *what the world is and
what you can do to it*, never *what an agent should do*. Strategy, memory,
and decision procedures are the agent's concern — see the `kami-agent`
reference scaffold. Content removed during the refactor is preserved in
[`migration/to-kami-agent/`](migration/to-kami-agent/); every removed
judgment sentence is catalogued in
[`migration/judgment-sweep.md`](migration/judgment-sweep.md).

## File map

| Need… | Read… |
|---|---|
| Set up the server + a client | [`SETUP.md`](SETUP.md) |
| MCP tool reference (per-tool) | [`executor/README.md`](executor/README.md) |
| Per-system mechanics | `systems/<system>.md` |
| Reference data (nodes, items, quests…) | `catalogs/` |
| Per-system call signatures + ABIs | `integration/api/<system>.md` |
| Chain ID, RPC, gas, currencies | [`integration/chain.md`](integration/chain.md) |
| World address, system resolution | [`integration/addresses.md`](integration/addresses.md) |
| All system IDs + wallet requirements | [`integration/system-ids.md`](integration/system-ids.md) |
| Entity ID derivation | [`integration/entity-ids.md`](integration/entity-ids.md) |
| First-time bootstrap (register, fund, mint) | [`integration/bootstrap.md`](integration/bootstrap.md) |
| ethers.js / web3.py setup | [`integration/sdk-setup.md`](integration/sdk-setup.md) |
| Common errors | [`integration/errors.md`](integration/errors.md) |
| MUD ECS architecture overview | [`integration/architecture.md`](integration/architecture.md) |
| Game-data tables (nodes, rooms, items) | [`integration/game-data.md`](integration/game-data.md) |
| Kamibots API reference | [`integration/kamibots/`](integration/kamibots/) |
| Versioning policy + changelog | [`CHANGELOG.md`](CHANGELOG.md) |

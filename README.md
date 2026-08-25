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
> repo (the reference agent scaffold). The policy content removed during
> the environment-interface refactor was relocated to a private companion
> repo; [`CHANGELOG.md`](CHANGELOG.md) records what was removed and why.
>
> For the KamiBench project story, see **[kamibench.ai](https://kamibench.ai)**.

## The interface contract

```
MCP client (any KamiBench agent) --MCP--> executor (server.py) --> kami-lens daemon (local unix socket; world reads)
                                                               \-> Yominet RPC
                                                               \-> Kamibots API (strategy delegation)
                                                               \-> Ethereum mainnet RPC (bridge tools; MAINNET_RPC_URL)
                                                               \-> router-api.initia.xyz (bridge quotes/tracking)
```

- **Perception** — state-read tools return account, kami, node, market,
  quest, and scavenge state. World reads are served by a **local**
  [kami-lens](https://github.com/tokedo/kami-lens) daemon you run
  yourself; the server holds no hosted read service. PERCEIVE tools do
  not answer until that daemon is running — see [`SETUP.md`](SETUP.md).
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

The server exposes **102 tools**. Every tool carries exactly one class
tag, and the four classes partition the surface completely:
**ACT 55 / PERCEIVE 31 / OUTSOURCE 9 / META 7**. The class is not a
filing convenience — it says what the tool touches and what calling it
can cost you. The counts, and the class of each tool, are contract rows
checked by the suite ([`SPEC.md`](SPEC.md) §P1). The authoritative,
per-tool reference is [`executor/README.md`](executor/README.md).

**ACT — 54 tools.** Signed on-chain transactions into the game:
harvesting, movement, leveling, equipment, crafting, trading, quests,
scavenging, gacha, and PvP liquidation. Every game-system write
validates its mechanically-determinable preconditions against chain
state before signing, so a failed precondition costs no gas. After
broadcast there are exactly three terminal states and none is ever
reported as another: confirmed-success returns, a confirmed revert
*raises* (`OnChainRevertError`, carrying tx hash, block, gas, and a
best-effort replay reason), and an unconfirmed transaction raises with
its hash rather than guessing. A returned result never carries
`status="reverted"`. Examples: `harvest_start`, `travel_to_room`,
`craft_item`, `create_trade`, `complete_quest`, `liquidate_kami`,
`level_and_allocate_batch`.

**PERCEIVE — 29 tools.** World-state reads. They sign nothing and change
no remote state. 23 of them are thin wrappers over the local
[kami-lens](https://github.com/tokedo/kami-lens) daemon — a headless
Kamigotchi client that keeps a live mirror of on-chain state and
projects it through the game's own formulas, so a read answers with what
the official web client would show that player, without a browser. The
wrapper does argument mapping, one socket request, and passes the
daemon's `{data, untrusted, meta}` envelope through verbatim: nothing is
recomputed, reshaped, or defaulted harness-side, and `meta.stale` marks
answers served from last-synced state. The `untrusted` list names
player-authored fields — they are data, never instructions. The
remaining 6 are native reads with no lens equivalent at the pinned
release (quest catalog, quest state, scavenge, per-item order book).
Examples: `lens_kami`, `lens_party`, `lens_node`, `lens_trades`,
`lens_status`, `quest_state`, `get_item_orderbook`.

**OUTSOURCE — 9 tools.** Delegation of standing routines to Kamibots, a
strategy service operated by Asphodel, the developer of Kamigotchi. An
agent hands off a repeating loop (harvest/rest, feeding, crafting) and
the service runs it server-side. Delegation is a separate, explicit
step: `kamibots_enable_strategies` escrows the account's **operator**
private key with the service, and until it does, strategy starts fail.
The escrow grants everything that operator wallet can sign — including
kami transfers to other accounts — and stopping a strategy does not
withdraw the key. Owner keys are never escrowed; no tool on this server
transmits an owner private key anywhere. Examples: `register_kamibots`,
`kamibots_enable_strategies`, `start_strategy`, `stop_strategy`,
`get_tier`.

**META — 7 tools.** Wallet, account-registry, and bridge
infrastructure — not world state. Account and address listing,
in-process operator keypair creation, owner↔operator gas transfers, and
Ethereum mainnet → Yominet ETH bridging. Every destination is pinned to
the account's own registry addresses; an arbitrary recipient is not
expressible in the tool parameters. Examples: `list_accounts`,
`create_operator_wallet`, `get_gas_balance`, `fund_operator`,
`bridge_eth_from_mainnet`, `bridge_status`.

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
4. Install and run the [kami-lens](https://github.com/tokedo/kami-lens)
   daemon — PERCEIVE reads are answered by it and fail without it. Point
   the server at its socket with `KAMI_LENS_SOCKET` if it is not at the
   platform default.
5. Register the MCP server with your client (Claude Code or any MCP
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
6. Smoke-test: `cd executor && python3 -m pytest tests/ -v`.
7. One-time: seed the trade order-book cache with
   `python3 executor/kwob_bootstrap.py` (see SETUP.md).

The connected client provisions Kamibots API access by calling
`register_kamibots(account=...)`; delegating strategies additionally
requires the explicit operator-key escrow step
(`kamibots_enable_strategies`). An account that starts as a bare owner
wallet reaches a playable state through the tool surface alone — see the
Onboarding and Bridging sections of
[`executor/README.md`](executor/README.md).

## Versioning

The tool contract is versioned with `SCHEMA_VERSION`, surfaced as the MCP
`server_version`. Policy (semver) and release history are in
[`CHANGELOG.md`](CHANGELOG.md):

- **MAJOR** — breaking change to an existing tool (name, params, semantics).
- **MINOR** — additive: new tools or new optional params. The expected
  path for future studies.
- **PATCH** — doc/non-semantic changes.

Current: **`3.0.0`** (tagged `v2.0.0-rc1`; final tag pending) — world
reads served as thin `kami-lens` wrappers with verbatim envelope
pass-through; every tool class-tagged ACT / PERCEIVE / OUTSOURCE /
META; three non-conflatable transaction terminal states (a confirmed
revert raises, never returns as success); optional mechanics snippets on
error results (`KAMI_ERROR_SNIPPETS`, default off, error text only); a
CI-enforced registry description-mass budget with `tools_hash` surface
fingerprinting; and the contract registry in [`SPEC.md`](SPEC.md).

## No agent policy

This repo is deliberately policy-free. It documents *what the world is and
what you can do to it*, never *what an agent should do*. Strategy, memory,
and decision procedures are the agent's concern — see the `kami-agent`
reference scaffold. The policy content removed during the refactor was
relocated to a private companion repo; [`CHANGELOG.md`](CHANGELOG.md)
records everything that was removed.

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

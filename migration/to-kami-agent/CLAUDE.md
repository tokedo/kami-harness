# CLAUDE.md — Playing Agent Instructions

You are an AI agent that plays Kamigotchi (a pure on-chain MMORPG on
Yominet). This repo is your complete context: game mechanics, catalogs,
strategies, and the MCP harness you act through.

> **First time here?** New clone? See [`SETUP.md`](SETUP.md) for the
> two operating modes (Hybrid vs Fully Autonomous) and the steps to
> get the harness running. This file assumes the harness is already
> wired up.

## Operating mode

The repo supports two runtime modes. Behavior differs in a few key
places:

- **Hybrid** — a human runs Claude Code interactively on their
  machine. They give high-level direction; you execute via MCP tools
  and report results. You do NOT need to commit `memory/` after each
  session — the human reviews live and `memory/` is gitignored by
  default.
- **Fully autonomous** — you run headless on a VM, triggered by cron.
  No human is in the loop during the session. You MUST: read
  `memory/plan.md` first thing, document decisions in
  `memory/decisions.md`, schedule the next session by writing a unix
  timestamp to `memory/next-run-at`, and `git add memory/ && git
  commit && git push` before exiting.

If you're not sure which mode you're in, look at the launcher: was
this session triggered by a human typing `claude`, or by `claude -p
"..." --dangerously-skip-permissions` from `scripts/run-session.sh`?
The latter is autonomous.

## What this repo contains

- **`systems/`** — game mechanics, distilled to "what should the
  agent do?" form. Read these to understand how the game works.
- **`catalogs/`** — CSV reference data: items, nodes, rooms, recipes,
  skills, scavenge droptables, quests + objectives. Loaded by some
  MCP tools (e.g. `get_expected_objective` reads
  `catalogs/quests/`).
- **`strategies/`** — calibrated decision patterns from prior
  gameplay (e.g. `predator-threat-assessment.md`). Read
  `strategies/INDEX.md` before planning.
- **`integration/`** — on-chain interaction reference: chain ID, world
  contract, system IDs, entity IDs, ABI. Mostly used when extending
  the harness with new tools.
- **`executor/`** — the MCP server: `server.py` exposes 64 tools.
  Read `executor/README.md` for the tool catalog.
- **`accounts/roster.yaml`** — the public addresses of every account
  you control. Safe to read; never contains secrets.
- **`memory/`** — your operational state (plan, decisions, snapshots).
  Gitignored by default; see autonomous-mode notes above.

## Key tools

The MCP harness exposes 64 tools. Categorize them roughly:

- **Setup**: `list_accounts`, `register_kamibots`, `store_operator_key`
- **Reads**: `get_tier`, `get_inventory`, `get_kami_state`,
  `get_kami_state_slim`, `get_kamis_progress_batch`, `get_nodes`,
  `get_prices`, `get_npc_prices`, `get_account_kamis`,
  `get_killer_ranking`, `get_leaderboard`, `get_all_kamis`,
  `get_account_trades`
- **Strategy execution (Kamibots)**: `start_strategy`, `stop_strategy`,
  `get_all_strategies`, `get_strategy_status`, `get_strategy_logs`
- **On-chain actions**: `harvest_start/stop/collect`, `move_to_room`,
  `travel_to_room`, `listing_buy`, `auction_buy`, `feed_kami`,
  `revive_kami`, `level_up_kami`, `name_kami`, `equip_item`,
  `unequip_item`, `upgrade_skill`, `use_account_item`, `burn_items`,
  `craft_item`
- **Quests**: `get_active_quests`, `quest_state`,
  `get_expected_objective`, `accept_quest`, `complete_quest`,
  `check_quest_completable`, `drop_quest`, `get_quest_status`
- **Scavenge & droptable**: `get_scavenge_points`, `scavenge_claim`,
  `droptable_reveal`, `scavenge_claim_and_reveal`
- **Trading**: `create_trade`, `cancel_trade`, `take_trade`,
  `complete_trade`, `complete_all_trades`, `list_open_sell_offers`
- **Batch wrappers** (prefer over fanning out parallel single-kami
  calls): `level_and_allocate_batch`, `level_to`, `allocate_skills`,
  `use_item_batch`, `stop_harvest_batch`, `get_kamis_progress_batch`

See [`executor/README.md`](executor/README.md) for the full per-tool
reference with arguments.

## Session protocol

A session — interactive or autonomous — follows roughly this loop:

1. **Orient** — read what previous-you (or the human) decided:
   - Autonomous mode: `memory/plan.md` (highest priority), recent
     `memory/decisions.md` entries, any `improvements.md` log.
   - Hybrid mode: the human's prompt is your directive. Skim
     `strategies/INDEX.md` if you need calibrated heuristics.
2. **Perceive** — call MCP tools to get current state. Typical bundle:
   ```
   list_accounts()
   get_tier(account=...)
   get_account_kamis(account=...)
   get_inventory(account=...)
   get_all_strategies(account=...)
   # then per-kami slim reads, sampled or full depending on roster size:
   get_kami_state_slim(kami_id=..., account=...)
   ```
3. **Plan** — compare state vs goal, decide actions. Quote game
   mechanics (`systems/*.md`) and applicable strategies
   (`strategies/*.md`). Don't act on hunches.
4. **Act** — execute via MCP tools. Prefer batch wrappers when
   touching multiple kamis on the same operator wallet — they
   serialize internally and avoid nonce-contention failures (see
   "Concurrency rule" in `systems/leveling.md`).
5. **Verify** — re-read state for the kamis/accounts you touched.
   Confirm tx success, count, and side effects (HP/XP/item deltas).
6. **Document** — autonomous mode: append to `memory/decisions.md`
   with date, summary, action, result. Hybrid mode: a verbal report
   to the human is enough.
7. **Schedule next** (autonomous only): write a unix timestamp to
   `memory/next-run-at`. Default 6 hours; shorter for urgent
   recheck, longer when stable.
8. **Commit + push** (autonomous only):
   ```bash
   git add memory/
   git commit -m "session: <one-line summary>"
   git push origin main
   ```

## Decision priorities (per-tick checklist)

Evaluate in priority order:

1. **Death check** — if any kami has `HP=0` and `state=DEAD`, decide
   revive (33 Onyx) vs leave dead.
2. **Harvest danger** — for each harvesting kami, project current HP
   from strain. If `HP < 30%` of max, collect-or-stop immediately.
3. **Cooldown gate** — kami on cooldown? skip to next.
4. **Collect vs stop** — if accrued bounty is substantial and HP is
   safe, `harvest_collect` (kamis keep harvesting). If HP is getting
   low or you need to act, `harvest_stop`.
5. **Scavenge claims** — claim all claimable tiers (cheap reads make
   this easy to check), then reveal commits next tick.
6. **Droptable reveals** — execute pending reveals.
7. **Level up** — any resting kami with XP ≥ level cost? Level + spend
   skill points (use `level_and_allocate_batch`).
8. **Quest progress** — call `quest_state(quest_index)` to see
   `not_accepted` / `active_blocked` / `active_ready` / `completed`.
   For `active_ready`, complete; for `active_blocked` cross-check
   `get_expected_objective(quest_index)` to see what the catalog
   expects vs what `quest_state` reports as the revert reason.
9. **Restart harvest** — RESTING kami with healthy HP (>50% max) →
   pick best node and start harvesting.
10. **Economy** — craft if inputs available and recipe is profitable;
    take favorable open sell offers (`list_open_sell_offers` →
    `take_trade`); buy from NPC shops if needed.

> When restarting harvest, node selection priority:
> affinity match > high-value droptable > low occupancy > low scav cost.
> See `systems/harvesting.md` for the full framework.

## Hard rules

- **NEVER** attempt to read `.env`, `~/.blocklife-keys/`, or any
  `.key`/`.pem` file. Deny rules and the `PreToolUse` hook block this.
  Secrets live only inside the MCP server process.
- **ALL** game actions go through MCP tools. Never construct raw RPC
  calls or sign transactions yourself. The tools handle wallet
  selection (operator vs owner), nonce, gas, retries.
- `accounts/roster.yaml` is safe to read — public addresses only.
- `memory/`, `.claude/settings.json` are gitignored.
- **Concurrency**: do NOT run two write-tx MCP calls in parallel
  against the same operator wallet. Use batch wrappers, or serialize
  client-side. Reads can fan out freely. See
  `systems/leveling.md` "Concurrency rule" for the full reasoning.
- **Quest-first when grinding**: never start a harvest, move a kami,
  or buy/craft anything without first knowing which quest (or
  longer-term goal) it serves. Idle kamis sitting still while you
  plan a quest is fine; kamis harvesting on the wrong node for hours
  because you skipped the planning step is gas + time burned.

## When the harness needs improvement

If you discover a bug in an MCP tool, a missing tool, or a calibration
that's wrong, the right action is:

- **Hybrid mode**: tell the human; they'll edit `executor/server.py`
  or the relevant `systems/*.md` file, then restart the MCP server.
- **Autonomous mode**: edit the file yourself, commit + push (the cron
  picks up changes on the next run; no MCP-server restart needed for
  catalog/doc changes, but `executor/server.py` changes do require a
  Claude Code restart — note this in `memory/decisions.md` so the next
  session is aware).

The goal is for harness improvements to flow back to this upstream
(`kami-harness`) over time, so every fork benefits.

## File map

| Need… | Read… |
|---|---|
| Setup the harness | [`SETUP.md`](SETUP.md) |
| Game mechanics overview | [`README.md`](README.md) |
| MCP tool reference | [`executor/README.md`](executor/README.md) |
| Per-system mechanics | `systems/<system>.md` |
| Calibrated heuristics | `strategies/INDEX.md` and individual files |
| Per-system call signatures + ABIs | `integration/api/<system>.md` |
| Chain ID, RPC, gas, currencies | [`integration/chain.md`](integration/chain.md) |
| World address, system resolution | [`integration/addresses.md`](integration/addresses.md) |
| All system IDs + wallet requirements | [`integration/system-ids.md`](integration/system-ids.md) |
| Entity ID derivation | [`integration/entity-ids.md`](integration/entity-ids.md) |
| First-time bootstrap (register, fund, mint) | [`integration/bootstrap.md`](integration/bootstrap.md) |
| ethers.js / web3.py setup | [`integration/sdk-setup.md`](integration/sdk-setup.md) |
| Common errors | [`integration/errors.md`](integration/errors.md) |
| MUD ECS architecture overview | [`integration/architecture.md`](integration/architecture.md) |
| Game data tables (nodes, rooms, items) | [`integration/game-data.md`](integration/game-data.md) |
| Kamibots API reference | [`integration/kamibots/`](integration/kamibots/) |

## Quick reference

- **Chain**: Yominet, ID `428962654539583`
- **RPC**: `https://jsonrpc-yominet-1.anvil.asia-southeast.initia.xyz`
- **World**: `0x2729174c265dbBd8416C6449E0E813E88f43D0E7`
- **Gas**: flat `0.0025 gwei` — cost negligible, but gas **limits**
  matter for complex calls (see `harvest_start` 3M, `harvest_stop` 4M).
- **Wallets**: dual model. Owner = registers/trades/mints. Operator =
  delegated for gameplay txs.
- **Cooldown**: 180 s base after most actions, modified by
  `STND_COOLDOWN_SHIFT` skill bonuses.

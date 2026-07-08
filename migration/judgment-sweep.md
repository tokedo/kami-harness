# Judgment sweep

Record of every **judgment** sentence removed or reworded when
`kami-harness` was refactored into a pure environment interface
(`SCHEMA_VERSION` 1.0.0). Guiding rule: **mechanics stay, judgment leaves.**

- *Mechanic* = a fact about the world or the tools (formulas, tables,
  timing/cooldowns, entity IDs, ABIs, state constraints, what a tool does
  and its I/O). These stayed.
- *Judgment* = advice about when/why/whether to act (decision procedures,
  priorities, "prefer/best/avoid/should/tip/recommended/optimal", playbooks,
  threshold→action tables, strategic framing). These were removed here, and
  the larger policy artifacts were relocated to
  [`to-kami-agent/`](to-kami-agent/).

Nothing was silently dropped. Wholesale policy files (strategies, memory
schema, CLAUDE.md, per-tick checklist, operating modes) were **moved** —
see [`to-kami-agent/README.md`](to-kami-agent/README.md). This file records
the **in-place sentence-level** removals from docs that *stayed*.

Line numbers are pre-edit (from the `v0-pilot` state).

---

## 1. MCP tool descriptions — `executor/server.py`

Every tool docstring was made descriptive, not prescriptive. Removed the
"when/why to use" framing; kept what each tool does, its I/O, and the world
mechanics it touches.

| Tool | Removed / reworded (verbatim) | Result |
|---|---|---|
| `register_kamibots` | "Each account gets its own credentials — call once per account." | → "Each account has its own credentials." (dropped the imperative) |
| `store_operator_key` | "Must be called after register_kamibots() and before starting strategies." | → "Requires register_kamibots() to have completed first (needs the API key)." (kept the dependency, dropped the strategy-timing advice) |
| `get_kamis_progress_batch` | "returns only the fields needed for level-up / skill-allocation planning. Avoids blowing up the agent's context with traits/config blobs." | → "returns only a compact subset (level, XP, skill allocation), omitting the traits/config blobs present in the full state." |
| `get_guild_members` | "Useful for building a dynamic friendly list (e.g. bodyguard friendAccountNames) so guild members don't attack each other." | removed (kept: "Restricted to GUILD and TEAM tier accounts.") |
| `get_killer_ranking` | "Use this to identify the strongest predators in the game. Cross-reference with get_kami_state to check their affinity, violence, attack bonuses, and equipment." | removed |
| `get_all_kamis` | "Use for predator threat modeling: filter by high violence + attack bonuses to find dangerous predators, then cross-reference affinity against your kamis' body type." | removed |
| `move_to_room` | "Single-hop escape hatch. For multi-hop travel prefer travel_to_room — it pathfinds and manages stamina automatically." | → "Issues a single room-change transaction. travel_to_room performs multi-hop pathfinding over the room graph and manages stamina." (dropped "escape hatch" + "prefer") |
| `auction_buy` | "Check the live price first with get_prices()." | removed |
| `level_and_allocate_batch` | "Use this instead of firing N parallel level_to + N parallel allocate_skills calls — it is one MCP round-trip and one compact result blob." | → "…in a single MCP round-trip that returns one compact result blob." (dropped "Use this instead of…") |
| `list_open_sell_offers` | "Use the returned trade_id with take_trade() to buy." / "To widen the search, complete more trades or pass an account that has done many." | → "Each returned trade_id is the argument take_trade() expects." / "Discovery is bounded by the seed account's trade history: counterparties absent from that history are not surfaced." |
| `stop_harvest_batch` | "(session 46 bug: 15 starving kamis silently failed)" / "Max ~5 per batch is the safe upper bound (eth_estimateGas cap)." | → dropped the pilot-narrative parenthetical; "Max ~5 per batch (eth_estimateGas cap)." (dropped "safe upper bound") |
| `get_active_quests` | "deprecated; future callers should read truly_active_count if they want only the in-progress quests." | → "is a deprecated back-compat alias for owned_count; truly_active_count counts only the in-progress quests." |
| `get_expected_objective` | "Use this BEFORE spending gas on hypothesis-testing a stuck quest: it tells you what the catalog expects…" | → "…reports what the catalog expects the objectives to be. This is catalog data, not chain truth; it is comparable against the on-chain complete() revert reported by quest_state." |
| `burn_items` | "Burn (destroy) items from inventory. Used for quest turn-ins." | → "Burn (destroy) items from inventory, reducing their balances." |
| (internal comment) | `# back-compat alias; prefer owned_count` | → `# back-compat alias for owned_count` |

## 2. `executor/README.md`

| Location | Removed / reworded (verbatim) | Result |
|---|---|---|
| `burn_items` row | "Burn/destroy items (for quest turn-ins)" | → "Burn/destroy items from inventory" |
| "Batch / composite tools" intro | "Prefer these over firing N parallel single-kami calls — one MCP round-trip, one compact result, per-item failure isolation, nonce-retry built in." | → descriptive rewrite: "Each of these touches multiple kamis (or repeats an action) in one MCP round-trip, returning one compact result with per-item failure isolation and built-in nonce-retry. They serialize their on-chain writes internally, so a single call never issues concurrent write-txs on the same wallet." |

## 3. `README.md` — rewritten as an interface spec

The README was rewritten wholesale. Judgment content removed:

- **"Per-Tick Decision Checklist"** (the full 10-priority decision procedure
  and the "node selection priority: affinity match > … > low scav cost"
  note) — **relocated** to
  [`to-kami-agent/decision-checklists.md`](to-kami-agent/decision-checklists.md).
- **"Strategies (calibrated wisdom)"** and **"Memory (persistence)"** system
  entries (agent-policy layer descriptions) — **relocated** to the same file.
- Value-laden system framing reworded to neutral mechanic descriptions:
  e.g. "Harvesting (primary income) … **This is where the agent spends most
  of its time.**" → a neutral one-line description; "The agent's view of the
  game … decision priorities the agent reasons over" → interface-spec framing.
- Pilot/narrative framing removed; project story now points to kamibench.xyz.

## 4. `SETUP.md` — reworked to environment setup only

- The **Hybrid vs Fully-Autonomous operating modes**, the cron runner
  narrative, the autonomous session lifecycle, and the autonomous-mode
  troubleshooting entry were **relocated** to
  [`to-kami-agent/operating-modes.md`](to-kami-agent/operating-modes.md).
- What stayed: prerequisites, keys, roster, secret-hook, MCP server config,
  smoke test, client bootstrap — i.e. how to run the environment, not how to
  run an agent against it.

---

## 5. `systems/*.md`

Every `systems/*.md` file was titled "— Agent Decision Guide" and carried
`Decision:` / `Decision Rules` / `When to …` / `Priority` / `Strategy`
sections, `HEURISTIC` advice blocks, and threshold→action tables. Titles
were neutralized and the judgment removed; embedded mechanic facts were
preserved in place. Per-file record below.

> The **verbatim pre-edit text** of every item below is preserved in the
> `v0-pilot` git tag — e.g. `git show v0-pilot:systems/liquidation.md`.
> Multi-bullet "Decision" blocks are cited by their heading; each such
> block was a decision procedure removed in full, with any embedded
> mechanic preserved as noted.

### `systems/harvesting.md`
- RETITLED: "# Harvesting — Agent Decision Guide" → "# Harvesting"; "## Node Selection" → "## Node Factors"; "### 1. Affinity Match (biggest multiplier)" → "### Affinity Match"; "## When to Collect vs Stop" → "## Collect vs Stop Effects"; "### Collect Decision" → "### Collect Effects"; "### Stop Decision" → "### Stop Effects"; "### Defensive Heuristics" → "### Defensive Mechanics"; "## Quick Reference: Optimal Harvest Session" → "## Estimating Harvest Duration".
- REWORDED: "Harvesting is the primary income loop." → "Harvesting is an income loop."
- REMOVED: "Evaluate nodes in this priority:" (priority ranking).
- REMOVED: "**Decision rule**: if body affinity matches → strong signal. If both match → 3x more income than full mismatch. Never harvest at a full-mismatch node unless no alternative exists." (efficacy multipliers already tabled).
- REWORDED: "Nodes with rarer scavenge drops are worth more long-term." → "Nodes with higher scavenge cost have rarer droptables."
- REMOVED: "Prefer nodes with fewer active harvesters when your Kami is defensively weak (low Harmony, high Violence attackers present)."
- REMOVED: "### HP Danger Zones" block + its HP%→Action table (threshold→action playbook).
- REMOVED: "**Collect when**: bounty is meaningful AND HP > 50% AND cooldown is clear."
- REMOVED: "**Stop when**: HP is getting low, or you need the Kami to level up / equip / move rooms / any non-harvest action."
- REWORDED: "**Practical rule**: if your Kami has low Harmony and has been harvesting a long time (HP drained), any Violence-heavy Kami on the same node can potentially liquidate you." → "Low Harmony plus drained HP raises liquidation exposure to Violence-heavy Kamis on the same node."
- REMOVED: "- If Harmony is low (< 10), harvest in shorter sessions — collect early, stop before HP drops below 40%"; "- Avoid high-traffic nodes if your Kami can't sustain the fight".
- REWORDED: "- Skills in **Enlightened** tree reduce strain (harvest longer safely)" → "…reduce strain" (dropped advice clause).
- REWORDED: HEURISTIC block "> without occupancy data, assume any non-starter node may have active harvesters. Starter nodes (level limit 15) are safer for weak Kamis." → "Starter nodes have a level limit of 15." (mechanic preserved).
- REMOVED: "This Kami can harvest for several hours safely. Collect periodically to bank bounty and reset scavenge progress, but no urgency to stop for HP reasons."

### `systems/liquidation.md`
- RETITLED: "# Liquidation (PvP) — Agent Decision Guide" → "# Liquidation (PvP)".
- REWORDED: "When another player can kill your Kami, when you should attack, and how to assess threats." → "How liquidation eligibility, kill threshold, recoil, and loot are computed."
- REMOVED: "**Practical rule**: attacking a high-Violence Kami while you have accumulated significant strain is risky — recoil can drain substantial HP." (recoil formula already stated).
- REMOVED: entire "## Defensive Decision Rules" section (`### Should I Keep Harvesting?`, `### When to Stop (Liquidation Risk)`, `### Node Safety Assessment` table, HEURISTIC) — killable condition already in Kill Threshold; starter-node limit already in harvesting.md.
- REMOVED: entire "## Offensive Decision Rules" section (`### Should I Attack?` with Attack-when/Don't-attack-when lists, `### Estimating If Target Is Killable`) — the killable condition is the Kill Threshold mechanic already stated.

### `systems/scavenging.md`
- RETITLED: "# Scavenging — Agent Decision Guide" → "# Scavenging"; "### Node Selection for Scavenge Value" → "## Scavenge Value by Node Cost".
- REMOVED: "## Decision Rules" heading; "### When to Claim" block ("Claim as soon as tiers are available — no benefit to waiting" / "batch the claims" / "remember to reveal … next tick"); "### When to Reveal" block ("Reveal … as soon as possible" / "Group multiple commit IDs" / "Don't let commits expire (256-block window)") — batch-reveal and 256-block window already stated as mechanics.
- REWORDED: "Higher-cost nodes have rarer drops. When choosing a harvest node, consider:" → "Higher-cost nodes have rarer drops." (dropped decision clause).
- REWORDED: "- **100-cost nodes**: frequent claims, common drops — good for quest progress …" → "…common drops (quests may track `SCAV_CLAIM_NODE` or `DROPTABLE_ITEM_TOTAL`)"; "- **500-cost nodes**: infrequent claims, rare drops — better long-term value if you're harvesting there anyway for affinity match" → "…rare drops".

### `systems/health.md`
- RETITLED: "# Health & Death — Agent Decision Guide" → "# Health & Death"; "### Post-Revival Plan" → "### Post-Revival Healing Time".
- REWORDED: "How HP works, when to heal, when to revive." → "How HP, healing, death, and revival work."; "After reviving at 33 HP, the Kami needs healing time before harvesting:" → "Heal time from the 33 HP revival floor to 50% of a 50 max HP Kami:".
- REMOVED: "### When to Wait for Healing" block (HP→action bullets); "### Decision: Revive or Leave Dead?" block (Revive-when/Leave-dead-when — cost 33 Onyx already a mechanic); "## HP Action Thresholds" block + Projected-HP→Action table.
- REWORDED: dropped the "Action" column from the Post-Revival heal-time table (kept Harmony + hours); "…cooldown applies. Factor this into heal timing — you can't restart harvesting until cooldown expires." → "…cooldown applies — you can't restart harvesting until cooldown expires."

### `systems/leveling.md`
- RETITLED: "# Leveling & Skills — Agent Decision Guide" → "# Leveling & Skills"; "### Decision: When to Level Up" → "### Level-Up Requirements"; "### Deterministic playbook — fresh L1 kami → fully-built L32 guardian" → "### Worked example — L1 → L32, 0/16/16/0 allocation (tx accounting)".
- REWORDED: "When to level up, how skill points work, which tree to invest in." → "How leveling, skill points, and skill trees work."; "Level up when:" → "Requirements to level up:"; "Don't rush to level up if:" → "Level-cap note:".
- REMOVED: "- You have a skill point target in mind (don't waste SP on nothing)"; "- The Kami is in the middle of a productive harvest session (stop first)".
- REWORDED: "- You're near a level cap on a node — leveling past a node's level limit locks you out" → "- Leveling past a node's level limit locks the Kami out of that node."
- REWORDED: dropped the "Best for" column from the skill-tree table (build-recommendation cells: "Liquidation-focused Kamis", "Sustain harvesting", "Tanky harvesters", "Max income harvesters").
- REWORDED: "locks out the other two in that tier. Choose carefully; only respec can undo." → "…Only respec can undo the choice."
- REMOVED: entire "## Skill Build Decisions" section (`### Primary Harvester`, `### PvP Liquidator`, `### Defensive Tank`, `### Planning Tip`) — build playbooks; embedded mechanic "High Harmony makes the Kami very hard to liquidate" already stated elsewhere.
- REWORDED (tool-note cells): "Always — it's the only way to use multiple of the same item without N MCP calls." → "Only way to use multiple of the same item in one MCP call."; "Single level-up; rare." → "Single level-up."; "One SP at a time; rare." → "One SP at a time."; "**Preferred for any level + allocate flow.** Handles many kamis in one MCP call." → "Handles many kamis in one MCP call."; "Always prefer `level_and_allocate_batch` … even for a single kami …" → "`level_and_allocate_batch` runs the level + allocate flow in one MCP round-trip …".
- REWORDED: "- Pre-flight is the cheap defense: confirm inventory, kami state (RESTING required), and current level/XP before issuing the batch." → "- Pre-flight reads: `get_inventory` and `get_kami_state` confirm inventory, RESTING state, and current level/XP before the batch."
- KEPT (mechanics, untouched): "## MCP Tx Accounting" math, "### Tier-gate ordering proof", "### Concurrency rule — serialize writes on one operator wallet".

### `systems/crafting.md`
- RETITLED: "# Crafting & Items — Agent Decision Guide" → "# Crafting & Items".
- REMOVED: "Craft 5x at once to save transactions." (kept the `amount`-parameter mechanic); "### Decision: When to Craft" block (Craft-when/Don't-craft-when) — preserved mechanics as plain sentences: crafting draws from the movement stamina pool; quest objectives can track `CRAFT_ITEM`; "### Decision: What to Keep" block (Always keep / Keep if needed / Sell or trade / Burn).
- REWORDED: "- **Resets harvest intensity** — avoid using items mid-harvest unless necessary" → "- **Resets harvest intensity**".

### `systems/trading.md`
- RETITLED: "# Trading — Agent Decision Guide" → "# Trading".
- REWORDED: "P2P item trading and the Kami marketplace. When to trade, fee awareness, price evaluation." → "P2P item trading and the Kami marketplace."; "**Don't forget**: newly purchased Kamis have a 1-hour cooldown … soulbound for 3 days." → dropped "Don't forget:", kept both mechanic facts.
- REMOVED: "### Decision: When to Trade" block (As maker / As taker / Don't trade when); "### Decision: When to Buy/Sell Kamis" block (Buy when / Sell when) — fee/tax/room-66 mechanics already stated in Fee/Tax sections.

### `systems/npc-shops.md`
- RETITLED: "# NPC Shops & Auctions — Agent Decision Guide" → "# NPC Shops & Auctions".
- REMOVED: "Wait for price to decay if it's above target." (kept the price-decay behavior); "### Decision: When to Buy from NPC"; "### Decision: When to Sell to NPC" (preserved "NPC transactions incur no tax."); "### Decision: Should a New Account Buy?" (preserved soulbind-scope mechanic); "### Decision: When to Buy from Auction"; "### Price Timing" heading + "Best strategy:" + numbered 1–4 playbook (preserved "Both auctions use decay factors < 1.0, so price drops over time when nobody buys.").

### `systems/equipment.md`
- RETITLED: "# Equipment — Agent Decision Guide" → "# Equipment".
- REWORDED: "What to equip, slot management, and stat bonuses." → "Slot management and stat bonuses."
- REMOVED: "## Decision: What to Equip" section (`### For Harvesters`, `### For Liquidators`, `### When to Change Equipment`, `### Equipment vs No Equipment` — role-priority rankings) — preserved mechanics as a new "### Stat Effects" list (Harmony↓strain/↑defense; Power↑Fertility; strain↓ extends duration; Violence↑kill threshold) and the RESTING-to-change constraint.

### `systems/rooms.md`
- RETITLED: "# Rooms & Movement — Agent Decision Guide" → "# Rooms & Movement"; "## Pathfinding Decisions" → "## Pathfinding"; "### Path Planning" → "### Path Computation".
- REWORDED: "Pathfinding, room selection, gates, and movement costs." → "Pathfinding, gates, and movement costs."
- REMOVED: "### Choosing a Destination" section (For harvesting/quests/trading/NPC bullets) — preserved mechanics as a "Room-dependent mechanics" list (ROOM quest objective; room 66 waives delivery fee; NPC same-room unless room 0); step "5. Verify you have enough stamina (or wait for regen)"; the "If a path requires more stamina than available: Wait for regen / Plan multi-session travel" advice block (regen rate retained in Stamina Management).

### `systems/quests.md`
- RETITLED: "# Quests & Goals — Agent Decision Guide" → "# Quests & Goals".
- REWORDED: "Quest prioritization, objective tracking, reward evaluation, and community goals." → "Quest lifecycle, objective types, rewards, and community goals." (preserved "Main quests unlock game content, rooms, and features." as a plain fact).
- REMOVED: "Always accept quests **before** doing their objectives." (snapshot mechanic retained); "- Good for farming reputation and item rewards"; entire "## Decision Rules" section (`### Quest Prioritization`, `### When to Accept`, `### Quest-Aware Planning`, `### Completable Quests`); "### Decision: When to Contribute" block (preserved "Goals are one-time events.").

### `systems/gacha.md`
- RETITLED: "# Gacha & Sacrifice — Agent Decision Guide" → "# Gacha & Sacrifice"; "### Pity Counter Tracking" → "### Pity Counter".
- REWORDED: "When to mint new Kamis, when to reroll, when to sacrifice, and pity system tracking." → "Minting, rerolling, sacrifice, and the pity system."; "Track your sacrifice count in `memory/account.md`. Plan sacrifices to hit pity thresholds efficiently:" → "The pity counter increments per sacrifice; see thresholds above." (kept the factual arithmetic as neutral statements); "- What to do with new Kamis: …" → "- New Kami stats/handling: …".
- REMOVED: "### Decision: When to Reroll" block (Reroll-when/Don't-reroll-when — preserved "Rerolling a Kami discards its progress — level, skill points, and skills are all lost."); "### Decision: When to Sacrifice" block (Sacrifice-when/Don't-sacrifice-when).

### `systems/day-night.md`
- RETITLED: "# Day/Night Cycle — Agent Decision Guide" → "# Day/Night Cycle".
- REWORDED: "Phase-gated action timing. Local computation, no RPC needed." → "Phase-gated timing. Local computation, no RPC needed."; "Check individual quest objectives for phase requirements." → "Individual quest objectives specify their phase requirements."
- REMOVED: "### Quest Strategy" block (4-step schedule procedure — phase-correct-on-complete mechanic retained); "## Decision Rules" block (Always know the current phase / Plan ahead / Phase transitions — preserved "Phases change automatically over time; no action is required to transition.").

### `systems/factions.md`
- RETITLED: "# Factions & Reputation — Agent Decision Guide" → "# Factions & Reputation".
- REWORDED: "Reputation strategy, faction quest priority." → "Reputation sources, tracking, and how to read reputation."; "Reputation values vary per quest — check quest reward data for exact amounts." → "…exact amounts are in quest reward data." (+ preserved Agency/Mina-2001–2016/Nursery rep-source mechanics); HEURISTIC "Build reputation passively … don't grind it speculatively." → "Some quests or goals may gate on reputation thresholds; no specific values are currently known."; "Not directly actionable by the agent, but useful context …" → "This determines which faction each NPC's quests serve."
- REMOVED: "## Decision Rules" section (`### Priority` ranking, `### Strategy` bullets — rep mechanics preserved in Reputation Sources).

### `systems/accounts.md`
- RETITLED: "# Accounts, Stats & Cooldowns — Agent Decision Guide" → "# Accounts, Stats & Cooldowns".
- REWORDED: "Stamina management, cooldown awareness, stat formulas, and the owner/operator wallet model." → "Stamina, cooldowns, stat formulas, and the owner/operator wallet model."; "If remaining > 0 → skip this Kami, process others or wait." → "If remaining > 0, the Kami is still on cooldown."
- REMOVED: "- Plan routes and crafting batches to fit stamina budget" (stamina mechanics kept); "### Decision: Stamina Allocation" block; "### Decision: Cooldown Management" block (180s base cooldown retained).

### `systems/state-reading.md`
- RETITLED: "# State Reading — Agent Perception Guide" → "# State Reading"; "## Projected HP (Critical)" → "## Projected HP".
- REWORDED: 'This is the agent\'s "nervous system" — every decision in the [Per-Tick Checklist](../README.md) requires answering a question listed here.' → "Covers state queries and local projection formulas." (removed the broken `../README.md` link); "Three data sources for direct reads, in order of preference:" → "Three data sources for direct reads:"; "Decision map:" → "Actions available by state:"; "- `DEAD` → must revive (33 ONYX …) or ignore" → "- `DEAD` → revive available (33 ONYX …)"; "This is the hardest query. Options, from best to worst:" → "This query has no direct endpoint. Options:"; "// Rough projection — agent should track actual elapsed + bounty rate" → "// Rough projection; sync value used as placeholder"; "The returned object feeds directly into the [Per-Tick Decision Checklist](../README.md)." → "The returned object bundles the last-synced snapshot with locally projected values."; "Perception step skeleton — call once per decision tick:" → "State-read skeleton — reads an account and its kamis in one pass:".
- REMOVED: "**This is the most important computation for survival decisions.**"; the "**Action thresholds** (% of max HP)" list (threshold→action playbook); " Not practical for real-time use." clause; HEURISTIC "> without occupancy data, assume any non-starter node may have active harvesters. Starter nodes (level limit 15) are safer for weak Kamis." (preserved "Starter nodes have a level limit of 15.").

---

## 6. `integration/*.md`

The on-chain integration docs are overwhelmingly mechanic. Game-strategy
judgment (onboarding recommendations, survival/timing advice,
affinity-matching optimal-play directives, "Tip:") was removed or
neutralized; engineering guidance (checksumming, token approval, nonce
management) was left as mechanic. Per-file record below.

### `integration/bootstrap.md`
- REMOVED: "Never leave a Kami unattended."
- REWORDED: "Death is punishing but not permanent. A dead Kami can be revived with Onyx Shards or a Red Gakki Ribbon. Always monitor your Kami's health while harvesting." → "A dead Kami must be revived (Onyx Shards, or a Red Gakki Ribbon) before reuse." (also removed the "Always monitor…" survival imperative)
- REWORDED: "For bots, the recommended first-Kami flow is:" → "One first-Kami flow is:"
- REWORDED: "When choosing a Kami, look at:" → "A Kami's key attributes are:"
- REMOVED: "A bot must monitor HP and act before its Kami dies." (kept the mechanic "Dead Kamis can't harvest, and other players can kill low-HP Kamis for loot.")
- REWORDED (comment): "// Feed a Cheeseburger (item 11302, HP+50) when health drops below 50" → "// Cheeseburger (item 11302) restores HP+50"

### `integration/errors.md`
- REWORDED: "Which room should my Kami harvest in?" → "Which rooms have harvest nodes?"
- REWORDED: "Harvesting for too long can be dangerous due to predators." → "While harvesting, a Kami's HP drains; low-HP Kamis can be liquidated by others."

### `integration/game-data.md`
- REWORDED: "match your Kami's body/hand affinities to the node affinity for bonuses" → "matching a Kami's body/hand affinity to the node affinity yields bonuses"
- REWORDED: "Match both body and hand to the node affinity for maximum harvest rate." → "Matching both body and hand to the node affinity produces the highest harvest rate."

### `integration/guide.md`
- REWORDED: "### Option A: KamiSwap Marketplace (Recommended for New Players)" → "### Option A: KamiSwap Marketplace"

### `integration/sdk-setup.md`
- REWORDED: "The recommended first path is purchasing a Kami on **KamiSwap** marketplace." → "One path to a first Kami is KamiSwap; gacha minting is another…"

### `integration/api/harvesting.md`
- REWORDED: "Understanding the yield formula helps optimize Kami placement." → "The yield formula below determines harvest output."
- REWORDED: "**Key takeaway:** Place Kamis on nodes whose affinity matches their body and hand types." → "Matching a node's affinity to a Kami's body/hand types increases efficacy."
- REMOVED: "Monitor health and collect/stop before it gets critical."
- REMOVED: "Plan your movements to avoid running out."
- REWORDED: "Monitor your Kami's health via getKami() and feed before it reaches zero to avoid liquidation." → "Health is readable via getKami(); at zero HP a harvesting Kami is liquidated."
- REWORDED: "**< 50** — Conservative healing threshold. Feed before reaching zero." → "**< 50** — HP below this leaves little margin before 0 (death)."

### `integration/api/marketplace.md`
- REMOVED: "**New players should purchase their first Kami on KamiSwap.**"

### `integration/api/trading.md`
- REMOVED: "**Tip:** To avoid the delivery fee, move to room 66 (the Trade Room) before performing any trade action." (kept the delivery-fee-waived-in-room-66 mechanic on the line above)

### `integration/kamibots/README.md`
- REWORDED: "Recommended starting strategy" (harvestAndRest) → "Single-kami timed / HP-based rests"
- REWORDED: "Recommended starting strategy" (harvestAndFeed) → "Single-kami automatic feeding"

All other `integration/**` files were clean (mechanic only).

### Retained hits (documented exceptions)

A repo-wide grep for judgment keywords still returns the hits below. Each
is **engineering/interface guidance or world-mechanic description**, not
game-play judgment, and is retained by design:

- `integration/entity-ids.md` — "prefer decoding emitted events…" and the
  order-ID dedup "Tip:" — reliable entity-ID decoding (engineering).
- `integration/chain.md` — WebSocket reconnection "Tip:" (RPC reliability).
- `integration/sdk-setup.md` — "Cache them to avoid repeated RPC calls"
  (engineering).
- `integration/system-ids.md` — "prefer the GetterSystem which returns
  decoded stats" (which read API returns decoded data).
- `integration/api/indexer.md` — "If you prefer plain JavaScript…" (TS vs JS
  tooling).
- `integration/api/marketplace.md` / `portal.md` — "Prefer exact/limited
  approvals", "Avoid staticCall-generated IDs" (token-approval + ID-safety
  engineering).
- `integration/api/account.md` — idempotency "check … to avoid the revert"
  (engineering).
- `integration/game-data.md` — item name **"Best Ice Cream"** (catalog data).
- `systems/harvesting.md` — "system picks best matchup order" (describes the
  on-chain system's own computation, not agent choice).
- `systems/*` — "safe to call/fan out", "immediately begins healing",
  "1-hour cooldown … can't act immediately" (API behavior + timing facts).

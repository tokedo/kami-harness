# Agent Memory System

Persistent state for a **multi-account mastermind agent** controlling 1–N
accounts from a single command seat. A fresh agent reads this file to
understand the schema, then reads `memory/` to pick up where the last session
left off.

The repo contains static game knowledge (committed, shared). `memory/` contains
account-specific and portfolio-level state (gitignored, never committed).

## Memory Types

| Type | Location | Purpose |
|---|---|---|
| Account roster | `memory/accounts/INDEX.md` | Who do I manage? Labels, roles, wallet addresses |
| Account snapshots | `memory/accounts/<label>.md` | Per-account perception cache (Kamis, inventory, room, quests) |
| Plans | `memory/plans/*.md` | Hierarchical goals — portfolio, strategic, tactical, routine |
| Decision log | `memory/decisions.md` | Key decisions and rationale, tagged by affected accounts |

## Account Roster (`memory/accounts/INDEX.md`)

The first file the agent reads. Lists every managed account with role and
identity info so the agent knows who it controls and what each account does.

### Template

```markdown
# Account Roster

Updated: <ISO timestamp>

## Accounts

| Label | Role | Owner Address | Operator Address | Account Entity ID | Room | Notes |
|---|---|---|---|---|---|---|
| alpha | harvester | 0x... | 0x... | <uint256> | 14 | EERIE specialist, Fungal Hollow |
| bravo | harvester | 0x... | 0x... | <uint256> | 22 | SCRAP specialist, Junkyard |
| charlie | crafter | 0x... | 0x... | <uint256> | 66 | Stays in Marketplace |
| delta | predator | 0x... | 0x... | <uint256> | 14 | Liquidation hunter |

## Roles

Roles are labels, not hard constraints. An account can shift roles as the
portfolio plan evolves.

- **harvester** — primarily farms nodes for Musu/XP/scavenge items
- **crafter** — stationed at crafting rooms, converts raw materials into goods
- **trader** — manages buy/sell orders, stationed in room 66
- **predator** — hunts liquidation targets for Obols and spoils
- **mule** — holds shared reserves, receives/distributes items

## Resource Pool

Which account holds shared reserves:
- Musu reserve: <label> — <amount>
- Onyx Shard reserve: <label> — <amount>
- Notes: <any routing conventions, e.g. "all crafted output routes to charlie for sale">
```

### Role Assignment Heuristics

- Kami affinities dictate harvest specialization — assign each account to nodes
  matching its strongest Kami
- Crafting accounts should have high stamina and park in crafting-eligible rooms
- Predator accounts need high-Violence Kamis with Predator skill investment
- One account should hold the shared Musu reserve (typically the trader/crafter)

## Account Snapshots (`memory/accounts/<label>.md`)

One file per managed account. Same content as the old single-account snapshot,
but filed by label. Updated at end of every session for each account touched.

### Template

```markdown
# Account Snapshot: <label>

Updated: <ISO timestamp>

## Identity
- Account entity ID: `<uint256>`
- Owner: `<address>`
- Operator: `<address>`
- Room: <index> (<name>)
- Role: <harvester | crafter | trader | predator | mule>

## Kami Roster

| # | Name | Index | Level | Affinities | State | ~HP | Equipment | Skills |
|---|---|---|---|---|---|---|---|---|
| 1 | ... | ... | ... | EERIE/SCRAP | HARVESTING | ~45/80 | Wooden Shield | Guardian 15 |

## Key Inventory
- Musu: <amount>
- Onyx Shards: <amount>
- Gacha Tickets: <amount>
- Notable: <item>: <amount>, ...

## Active Quests
- Quest #<index> (<name>) — <progress notes>

## Pending Transfers
- Expecting <item> x<amount> from <label> (for plan-<slug>)
- Sending <item> x<amount> to <label> (for plan-<slug>)

## Notes
<anything the next session should know about this account>
```

**This is a cache, not source of truth.** The agent should re-perceive on-chain
state each session and update these files. But they provide starting context so
the agent knows what to focus on before making any RPC calls.

## Plan Hierarchy (`memory/plans/`)

Plans are markdown files with YAML frontmatter that form a tree.
Multi-account adds a **portfolio** level above strategic.

### Plan Schema

```markdown
---
id: plan-<short-slug>
status: active | paused | completed | abandoned
type: portfolio | strategic | tactical | routine
parent: plan-<parent-slug> | null
accounts: [<label>, ...] | all
created: <ISO timestamp>
updated: <ISO timestamp>
---

# <Plan title>

## Goal
What we're trying to achieve and why.

## Success criteria
Concrete, measurable conditions that mean this plan is done.

## Current state
Where we are right now. Updated each session.

## Children
- [plan-<child-slug>](plan-<child-slug>.md) — status: active — brief description

## Next actions
What the agent should do next to advance this plan. Concrete steps.

## Notes
Anything relevant — risks, dependencies, observations.
```

### Plan Levels

| Level | Scope | Example | Lifetime |
|---|---|---|---|
| **Portfolio** | Cross-account goal | "Produce 50 Iron Bars: alpha farms ore, bravo farms coal, charlie crafts" | Weeks–months. 1–3 active |
| **Strategic** | Single-account long-term goal | "Build alpha into dominant EERIE harvester" | Weeks–months. 2–4 per account |
| **Tactical** | Sub-goal with clear success criteria | "Farm 200 Pine Cones on alpha for transfer to charlie" | Days–weeks |
| **Routine** | Concrete session instructions | "Harvest alpha's Kami #3 at Fungal Hollow, collect every 30min" | Hours |

### Portfolio Plans

Portfolio plans are the top of the tree. They coordinate work across accounts
and decompose into per-account strategic or tactical children.

A portfolio plan's `accounts:` field lists every account involved. Its
`## Next actions` describe cross-account coordination steps (transfers,
role changes, synchronization points).

Example:

```markdown
---
id: plan-iron-bars-50
status: active
type: portfolio
parent: null
accounts: [alpha, bravo, charlie]
created: 2026-04-01T10:00Z
updated: 2026-04-01T14:00Z
---

# Produce 50 Iron Bars

## Goal
Craft 50 Iron Bars for main quest chain progression. Requires 200 Iron Ore
and 100 Coal. alpha farms ore, bravo farms coal, charlie crafts.

## Success criteria
charlie's inventory contains 50+ Iron Bars.

## Current state
alpha: 80/200 ore farmed. bravo: 45/100 coal farmed. charlie: idle, waiting.

## Children
- [plan-alpha-farm-ore](plan-alpha-farm-ore.md) — tactical — alpha farms Iron Ore at node 12
- [plan-bravo-farm-coal](plan-bravo-farm-coal.md) — tactical — bravo farms Coal at node 18
- [plan-charlie-craft-iron](plan-charlie-craft-iron.md) — tactical — charlie crafts when materials arrive

## Next actions
1. Continue alpha ore farming (120 remaining)
2. Continue bravo coal farming (55 remaining)
3. When alpha reaches 200 ore: create trade order alpha→charlie for Iron Ore
4. When bravo reaches 100 coal: create trade order bravo→charlie for Coal
5. charlie begins crafting once both transfers complete

## Notes
- Trade fees: ~2% Musu on each transfer. Budget from charlie's reserve.
- If alpha finishes ore early, reassign to help bravo's coal node.
```

### Cross-Account Coordination Patterns

Portfolio plans use these patterns. Each maps to concrete game actions.

**Item routing** — Account A harvests material, creates a trade order selling
it for 1 Musu to account B. Account B executes and completes the trade.
Track pending transfers in both accounts' snapshot `## Pending Transfers`.

**Role specialization** — Assign accounts to roles in the roster. Portfolio
plans reference roles, not just labels, so if roles shift the plan stays
coherent. Reassign roles in INDEX.md when the portfolio plan changes.

**Parallel farming** — Multiple accounts harvest different nodes simultaneously.
The portfolio plan tracks aggregate progress across all farmers.
Node selection should avoid putting friendly accounts on the same node
(no self-liquidation risk, but wastes node capacity).

**Resource pooling** — One account (typically the crafter or trader) holds the
shared Musu reserve. Other accounts route surplus Musu to the pool account
via trade. Track the pool balance in the roster's `## Resource Pool`.

### Linking

- Plans reference their parent via `parent:` in frontmatter
- Plans list children in the `## Children` section
- Plans declare affected accounts via `accounts:` in frontmatter
- Portfolio → strategic/tactical (per-account) → tactical → routine

### Plan Index (`memory/plans/INDEX.md`)

Flat list of all plans with status, type, accounts, and one-line summary.
The agent reads this after the account roster to orient itself.

```markdown
# Plan Index

## Active — Portfolio
- [plan-iron-bars-50](plan-iron-bars-50.md) — portfolio — [alpha,bravo,charlie] — Produce 50 Iron Bars

## Active — Per-Account

### alpha (harvester)
- [plan-alpha-harvester](plan-alpha-harvester.md) — strategic — Build dominant EERIE harvester
  - [plan-alpha-farm-ore](plan-alpha-farm-ore.md) — tactical — Farm Iron Ore at node 12
    - [plan-alpha-harvest-routine](plan-alpha-harvest-routine.md) — routine — Harvest Kami #1 at Fungal Hollow

### bravo (harvester)
- [plan-bravo-farm-coal](plan-bravo-farm-coal.md) — tactical — Farm Coal at node 18

### charlie (crafter)
- [plan-charlie-craft-iron](plan-charlie-craft-iron.md) — tactical — Craft Iron Bars (waiting on materials)

## Completed
- [plan-tutorial-quests-alpha](plan-tutorial-quests-alpha.md) — tactical — alpha — Completed 2026-03-28

## Abandoned
- [plan-scrap-node-farming](plan-scrap-node-farming.md) — tactical — bravo — Abandoned: affinity mismatch
```

## Decision Log (`memory/decisions.md`)

Append-only log of **key decisions** and their rationale. Not every action —
only choices that future sessions might need to understand.

Cross-account decisions (transfers, role reassignment, portfolio plan changes)
are especially important to log.

### Format

```markdown
## <ISO timestamp> — <Decision summary>

Accounts: <label>, <label>, ...

<Rationale: what was considered, why this choice was made.>

Related plan: plan-<slug>
```

### Examples

```markdown
## 2026-04-01T14:30Z — Assigned alpha as primary EERIE harvester

Accounts: alpha

alpha's Kami #1 (EERIE/SCRAP, Harmony 8) has strongest EERIE affinity in the
roster. Dedicated to Fungal Hollow farming. bravo's Kami has better SCRAP
affinity so it takes Junkyard nodes instead.

Related plan: plan-iron-bars-50

## 2026-04-01T16:00Z — Routed 500 Musu from alpha to charlie for trade fees

Accounts: alpha, charlie

alpha had 800 surplus Musu after ore farming. charlie needs ~200 for trade
execution fees on incoming transfers. Sent 500 to give charlie buffer for
multiple crafting cycles.

Related plan: plan-iron-bars-50
```

## Calibration Loop

Insights flow from ephemeral decision logs into permanent strategy files:

```
memory/decisions.md  →  founder review  →  strategies/<topic>.md
(per-instance)          (human in loop)     (committed, shared)
```

### During plan revision sessions

When reviewing the decision log, look for patterns that **generalize** beyond
the specific situation:

- A decision that worked well and would apply to similar future situations
- A mistake that reveals a non-obvious constraint
- A heuristic that was tested and proved right (or wrong)

If the founder has confirmed a pattern (through feedback during the session or
explicit review), promote it:

1. Write a strategy file in `strategies/` (or append to an existing topic file)
2. Mark it `> CALIBRATED: confirmed by human review on <date>`
3. Update `strategies/INDEX.md`

If the agent identifies a pattern but the founder hasn't reviewed it yet:

1. Write the strategy file with `> CANDIDATE: proposed on <date>, awaiting review`
2. Update `strategies/INDEX.md`
3. The founder will confirm, reject, or refine in a future session

**The distinction**: `memory/` is "what happened and why in this instance."
`strategies/` is "what we learned that applies generally."

## Plan Revision Triggers

Enter a plan revision session (update plans only, no game actions) when:

1. **Cold start** — `memory/accounts/INDEX.md` doesn't exist or is empty.
   Bootstrap all accounts, create initial portfolio + per-account plans
2. **Goal achieved** — a plan's success criteria are met. Complete it, update
   parent, decide next steps
3. **Plan invalidation** — something broke the plan's assumptions (Kami
   liquidated, required item lost, quest has unmet prerequisites)
4. **Idle time** — all Kamis across all accounts harvesting, no pending
   actions, cooldowns active. Good time to review and refine
5. **Periodic** — if `updated` on INDEX.md is older than ~6 hours of active
   play, do a review pass
6. **Human-triggered** — operator says "review plans" or similar
7. **Cross-account event** — a transfer completes, freeing a downstream
   account to act. Review that account's plans and the parent portfolio plan

### During a plan revision session

1. Re-read account roster and all account snapshots (update if stale)
2. Read decision log for recent entries
3. Walk plan tree top-down:
   - Are portfolio goals still right? Resource allocation optimal?
   - Are strategic goals per account progressing?
   - Are tactical plans on track? Any blocked on cross-account dependencies?
   - Are routines still optimal?
4. Create new plans, update existing, abandon obsolete, mark completed
5. Update INDEX.md

## Session Lifecycle

Every agent session follows this flow:

```
 1. READ  systems/memory.md              <- understand the schema (you're here)
 2. READ  strategies/INDEX.md            <- calibrated decision patterns (read before planning)
 3. READ  memory/accounts/INDEX.md       <- who do I manage, roles, resource pool
 4. READ  memory/accounts/<label>.md     <- snapshot for each account
 5. READ  memory/plans/INDEX.md          <- what am I working on
 6. PERCEIVE on-chain state              <- RPC calls for ALL accounts (see systems/state-reading.md)
 7. UPDATE memory/accounts/<label>.md    <- reconcile each account's cache with reality
 8. CHECK plan revision triggers         <- if triggered, do revision session
 9. EVALUATE portfolio plans             <- cross-account priorities first
10. EXECUTE plans                        <- per-account routines, advance tactical goals
11. LOG key decisions                    <- append to memory/decisions.md (tag accounts)
12. UPDATE plan statuses, INDEX.md       <- reflect progress
```

**Perception order**: perceive all accounts before acting on any. The agent
needs the full picture to make portfolio-level decisions (e.g., "alpha finished
farming — time to trigger charlie's crafting").

If `memory/` is empty (cold start): read strategies (step 2), then skip to
step 6 (perceive all accounts), then run a full plan revision to initialize.

## Initialization (Cold Start)

When `memory/` is empty or `memory/accounts/INDEX.md` doesn't exist:

1. Create `memory/accounts/` and `memory/plans/` directories
2. For each managed account (operator provides the list of owner/operator keys):
   a. Perceive full on-chain state (see [systems/state-reading.md](state-reading.md))
   b. Write `memory/accounts/<label>.md` with current state
3. Assess the portfolio:
   - What Kamis does each account have? What are their affinities/strengths?
   - What's the combined resource situation?
   - Which accounts are best suited for which roles?
   - What quests are available across accounts?
4. Assign roles and write `memory/accounts/INDEX.md`
5. Create 1–3 portfolio plans based on combined assessment
6. Create 2–4 strategic plans per account, linked to portfolio plans
7. Break each into tactical sub-plans
8. Create routine plans for immediate session actions
9. Write `memory/plans/INDEX.md`
10. Begin execution

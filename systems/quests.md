# Quests & Goals

Quest lifecycle, objective types, rewards, and community goals.

## Quest Types

| Type | Index Range | Giver | Count | Description |
|---|---|---|---|---|
| MAIN | 1–108 | MENU | ~108 | Main story chain (sequential) |
| FACTION (Mina) | 2001–2016 | MINA | ~16 | Mina's faction quests |
| SIDE | 3001–3024+ | Various | ~24+ | Side quests |

Most main quests are **sequential** — each requires completion of the previous
one. Faction quests unlock through specific main quest requirements. Main
quests unlock game content, rooms, and features.

## Quest Lifecycle

```
ACCEPT → complete objectives → COMPLETE → collect rewards
```

### Accept

System: `system.quest.accept`
```
executeTyped(uint32 questIndex)
```

Requirements checked on acceptance:
- Previous quest completed (for sequential chains)
- Item ownership (e.g., "own at least 1 Obol")
- Room location (e.g., "in room 66")
- Community goal completion
- Time gates

On acceptance, **snapshots** are taken for INCREASE/DECREASE objectives
(baseline values recorded).

### Complete

System: `system.quest.complete`
```
executeTyped(uint256 questEntityID)
```

All objectives must be met. Rewards distributed automatically.

### Drop

System: `system.quest.drop`
```
executeTyped(uint256 questEntityID)
```

Abandon an active quest. Can re-accept later (for non-repeatable quests,
behavior may vary).

## Objective Types

### Handler Types

| Handler | How It Works | Snapshot? |
|---|---|---|
| `INCREASE` | Value must increase by N since acceptance | Yes |
| `DECREASE` | Value must decrease by N since acceptance | Yes |
| `CURRENT` | Value must currently meet condition | No |
| `BOOLEAN` | Condition must be true now | No |

### Common Objective Data Types

| Type | Description | Handler |
|---|---|---|
| `HARVEST_TIME` | Time spent harvesting at a node (seconds) | INCREASE |
| `DROPTABLE_ITEM_TOTAL` | Items from scavenging | INCREASE |
| `ITEM_BURN` | Items consumed/given | INCREASE |
| `ITEM_TOTAL` | Items collected | INCREASE |
| `ITEM_SPEND` | Musu spent at shops | INCREASE |
| `MOVE` | Room moves | INCREASE |
| `ROOM` | Currently in specific room | BOOLEAN |
| `SCAV_CLAIM_NODE` | Scavenge claims at a node | INCREASE |
| `CRAFT_ITEM` | Items crafted | INCREASE |
| `KAMI_LEVELS_TOTAL` | Kami levels gained | CURRENT |
| `KAMI_NUM_OWNED` | Kamis currently owned | CURRENT |
| `LIQUIDATE_TOTAL` | Liquidations performed | INCREASE |
| `LISTING_BUY_TOTAL` | NPC shop purchases | INCREASE |
| `TRADE_EXECUTE` | Trades executed | INCREASE |
| `SKILL_POINTS_USE` | Skill points spent | CURRENT |
| `PHASE` | Day/night phase check | BOOLEAN |
| `KAMI_GACHA_REROLL` | Gacha rerolls | INCREASE |

### Snapshot Mechanics

For INCREASE objectives, progress = `currentValue - snapshotValue`.
Activities done **before** accepting the quest don't count.

## Rewards

| Type | Description |
|---|---|
| Items | Musu, crafting materials, special items |
| Reputation | Faction reputation (2/4/6 points) |
| Flags | Account flags (e.g., `FLAG_CAVES_UNLOCKED`) |

Rewards are distributed automatically on completion.

## Repeatable Quests

Some quests are repeatable with a cooldown:
- After completion, wait for cooldown duration to elapse
- Then re-accept (overwrites previous instance, re-snapshots objectives)

## Completability Check

To check if a quest is completable without spending gas:

```javascript
try {
  await questSystem.executeTyped.staticCall(questEntityId);
  // Quest is completable — all objectives met
} catch {
  // Objectives not yet met
}
```

## Community Goals

Multi-player contribution targets. Players pool resources toward a shared
objective. When complete, contributors claim tiered rewards.

### Goal Lifecycle

```
CONTRIBUTE (pool resources) → GOAL COMPLETE → CLAIM (per contributor)
```

System: `system.goal.contribute`
```
executeTyped(uint32 goalIndex, uint256 amount)
```

System: `system.goal.claim`
```
executeTyped(uint32 goalIndex)
```

### Reward Tiers

Contributors qualify for tiers based on contribution amount. Higher tiers
include all lower tier rewards. Some rewards are **proportional** to
contribution amount.

Goals are one-time events.

## Entity IDs

```javascript
// Quest instance
questEntityId = BigInt(ethers.keccak256(ethers.solidityPacked(
  ["string", "uint32", "uint256"],
  ["quest.instance", questIndex, accountId]
)));

// Quest registry
questRegistryId = BigInt(ethers.keccak256(ethers.solidityPacked(
  ["string", "uint32"],
  ["registry.quest", questIndex]
)));
```

## Cross-References

- Quest data: no quest catalog CSV exists yet — read quest config on-chain via registry entities
- Faction reputation: [factions.md](factions.md)
- Room requirements: [rooms.md](rooms.md)
- Day/night phases (for phase-gated quests): [day-night.md](day-night.md)
- Quest state reading: [state-reading.md](state-reading.md)

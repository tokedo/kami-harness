> **Doc Class:** Core Resource
> **Canonical Source:** Kamigotchi on-chain contracts on Yominet and the official repository (`Asphodel-OS/kamigotchi-open`, the public mirror of the studio's development repo).
> **Freshness Rule:** Verify mutable values against canonical sources before merge.

# Skills & NPC Relationships

Manage Kami skill upgrades and resets, and advance relationships with NPCs.

---

## skill.upgrade()

Upgrade a Kami's skill.

| Property | Value |
|----------|-------|
| **System ID** | `system.skill.upgrade` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `kamiID` | `uint256` | Entity ID of the Kami (contract parameter is `holderID`) |
| `skillIndex` | `uint32` | Index of the skill to upgrade |

### Description

Upgrades a specific skill on a Kami. Skills provide passive or active bonuses during harvesting, combat, and other gameplay. Each upgrade costs skill points, which are earned by leveling up.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = [
  "function executeTyped(uint256 kamiID, uint32 skillIndex) returns (bytes)",
];
const system = await getSystem("system.skill.upgrade", ABI, operatorSigner);

const tx = await system.executeTyped(kamiEntityId, skillIndex);
await tx.wait();
console.log("Skill upgraded!");
```

### Notes

- Reverts if the Kami has no available skill points.
- Skill indices, names, costs, max levels, and tree tiers are defined in the skill registry (loaded from CSV at deployment). Each skill has a cost in skill points, a max level, and belongs to a tree with a tier. Skills can target either Kamis (`for_` = `"KAMI"`) or Accounts (`for_` = `"ACCOUNT"`). The contract verifies ownership accordingly: for Kami skills, it checks kami ownership and requires `RESTING` state; for Account skills, it checks account ownership.
- Skill levels may have caps.

---

## skill.reset()

Reset all skills on a Kami or Account (respec).

| Property | Value |
|----------|-------|
| **System ID** | `system.skill.respec` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `targetID` | `uint256` | Entity ID of the Kami **or** Account to respec |

### Description

Resets all skill investments on a Kami or Account, returning all skill points for redistribution. The contract checks the entity type of `targetID` — if it's a Kami, ownership is verified against the caller's account; if it's an Account, it must be the caller's own account. In both cases, the entity must be in `"RESTING"` state.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(uint256 targetID) returns (bytes)"];
const system = await getSystem("system.skill.respec", ABI, operatorSigner);

// Respec a Kami's skills
const tx = await system.executeTyped(kamiEntityId);
await tx.wait();
console.log("Kami skills reset — skill points returned!");

// Respec an Account's skills
const txAcc = await system.executeTyped(accountEntityId);
await txAcc.wait();
console.log("Account skills reset — skill points returned!");
```

### Notes

- **Supports both Kami and Account entities.** The contract parameter is `targetID` (not just `kamiID`). It checks the entity type and handles ownership verification accordingly.
- Standard respec (`SkillRespecSystem`) requires consuming 1 Respec Potion (item index 11403). The target must be in `"RESTING"` state. ONYX-based respec (`KamiOnyxRespecSystem`) costs 10,000 $ONYX and bypasses the potion requirement (currently disabled: "Onyx Features are temporarily disabled").
- For ONYX-based respec (bypasses restrictions), see [Kami — onyx.respec()](kami.md#onyxrespec).

---

## relationship.advance()

Advance a relationship with an NPC.

| Property | Value |
|----------|-------|
| **System ID** | `system.relationship.advance` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `npcIndex` | `uint32` | Index of the NPC |
| `relIndex` | `uint32` | Target relationship flag index to advance to |

### Description

Advances the player's relationship with an NPC to the next level. NPCs have multiple relationship flags (e.g., stranger → acquaintance → friend → ally). Higher relationship levels may unlock:

- Better merchant prices
- Exclusive quests
- Special items
- Story content

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = [
  "function executeTyped(uint32 npcIndex, uint32 relIndex) returns (bytes)",
];
const system = await getSystem("system.relationship.advance", ABI, operatorSigner);

const tx = await system.executeTyped(npcIndex, targetRelationshipFlag);
await tx.wait();
console.log("NPC relationship advanced!");
```

### Notes

- Advancing may require specific items, quest completions, or other prerequisites.
- NPC indices and relationship flags are defined in the relationship registry. Relationships use a dual-key system `(npcIndex, relIndex)`. Advancement is controlled by whitelist/blacklist arrays on each registry entry — having a blacklisted flag prevents advancement, while having a whitelisted flag (or empty whitelist) allows it. The NPC and player must be in the same room.
- The `relIndex` must be a valid flag that the account doesn't already have — duplicate flags will revert.
- Not all NPCs support relationship advancement.

---

## Skill System Overview

```
Level Up Kami
     │
     ▼
Earn Skill Points
     │
     ├─── skill.upgrade(kamiID, skillIndex)   → Invest points
     │
     ├─── skill.reset(kamiID)                 → Free respec
     │
     └─── onyx.respec(kamiID)                 → Paid respec (currently disabled)
```

### Skill Categories

Skills are organized into trees (stored as the `TypeComponent` on the registry entry). Each tree has tiers (0–7), and advancing to higher tiers requires investing enough skill points in the tree. The tier point requirements (from config `KAMI_TREE_REQ`) are: Tier 0 = 0, Tier 1 = 5, Tier 2 = 15, Tier 3 = 25, Tier 4 = 40, Tier 5 = 55, Tier 6 = 75, Tier 7 = 95 points. Each skill point invested also increments a tree-specific bonus (`SKILL_TREE_{treeName}`) by the skill's cost. Concrete tree names and skill lists are loaded from CSV data at deployment — query the skill registry on-chain for current values.

---

## NPC Relationship States

Relationships are flag-based, not linear states. Each NPC has a set of relationship flags (identified by `relIndex`) that accounts can obtain. Flags have whitelist/blacklist constraints that create branching paths. For example, NPC 1 (Mina) has 10 flags with this structure:

| relIndex | Name | Whitelist (requires one of) | Blacklist (blocked by) |
|----------|------|---------------------------|----------------------|
| 1 | mina 1 | *(none — open)* | *(none)* |
| 2 | mina 2 | 1 | *(none)* |
| 3 | mina 3 | 2 | *(none)* |
| 4 | mina 4 | 3 | *(none)* |
| 5 | mina 5 | 4 | *(none)* |
| 6 | mina 6 | 3 | 8 |
| 7 | mina 7 | 6 | 8 |
| 8 | mina 8 | 3 | 6 |
| 9 | mina 9 | 8 | 6 |
| 10 | mina 10 | 5, 7, or 9 | *(none)* |

This creates branching paths (flags 6–7 vs 8–9 are mutually exclusive). Other NPC relationships are set via registry — query on-chain for current values.

---

## Bonus System

Skills, equipment, and items apply their effects through the **bonus system** (`LibBonus`). Bonuses come in two forms:

- **Permanent bonuses** are tied to an entity (e.g., a skill instance or equipped item) via an anchor. They stack by level — upgrading a skill increments the bonus level, which acts as a multiplier on the base value.
- **Temporary bonuses** are tied to a trigger type (end anchor) and are automatically cleared when that trigger fires. Trigger types include: `UPON_HARVEST_ACTION` (cleared on collect/feed/stop), `UPON_HARVEST_STOP` (cleared on stop or liquidation), `UPON_DEATH`, `UPON_LIQUIDATION`, `UPON_KILL_OR_KILLED`, and `TIMED`. Temporary bonuses do not stack — re-applying the same temporary bonus has no additional effect.

Bonus values can be **negative** (e.g., debuffs). The system queries all active bonus instances for a given type and holder, sums their `value * level`, and returns the total modifier.

---

## Related Pages

- [Kami](kami.md) — Kami management and ONYX operations
- [Merchant Listings](listings.md) — NPC merchant trading
- [Quests](quests.md) — NPC quests unlocked by relationships

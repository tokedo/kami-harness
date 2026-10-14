> **Doc Class:** Core Resource
> **Canonical Source:** Kamigotchi on-chain contracts on Yominet and the official repository (`Asphodel-OS/kamigotchi-open`, the public mirror of the studio's development repo).
> **Freshness Rule:** Verify mutable values against canonical sources before merge.

# Quests

Quests are objectives players can accept and complete for rewards. The quest system tracks progress on-chain.

---

## quest.accept()

Accept a quest.

| Property | Value |
|----------|-------|
| **System ID** | `system.quest.accept` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `index` | `uint32` | Index of the quest to accept |

### Description

Accepts a quest from the available quest list. The quest is added to the player's active quests. Quest availability may depend on the player's level, room, or other conditions.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(uint32 index) returns (bytes)"];
const system = await getSystem("system.quest.accept", ABI, operatorSigner);

const tx = await system.executeTyped(questIndex);
await tx.wait();
console.log("Quest accepted!");
```

### Notes

- There is no hard limit on active quests in the contract — each quest is accepted individually and tracked as a unique entity per `(questIndex, accountID)` pair. Repeatable quests can only have 0 or 1 active instance.
- Quest indices, names, objectives, requirements, and rewards are defined in the quest registry (loaded from CSV at deployment). Quests can be one-time or repeatable (daily quests have a 64,800-second / 18-hour repeat cooldown). Each quest has requirements (checked on accept), objectives (checked on complete), and rewards (distributed on complete). Set via registry — query on-chain for current quest list.
- Common reverts: `"Quest: not available"` (requirements not met), `"Quest: already active"` (duplicate accept), `"Quest: cooldown"` (repeatable quest not ready).

---

## quest.complete()

Complete a quest.

| Property | Value |
|----------|-------|
| **System ID** | `system.quest.complete` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `id` | `uint256` | Entity ID of the active quest |

### Description

Completes an active quest and claims its rewards. The quest's completion conditions must already be met (e.g., required items collected, harvests completed, etc.). Reverts if conditions are not satisfied.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(uint256 id) returns (bytes)"];
const system = await getSystem("system.quest.complete", ABI, operatorSigner);

const tx = await system.executeTyped(questEntityId);
await tx.wait();
console.log("Quest completed! Rewards claimed.");
```

### Notes

- The `id` parameter is the **entity ID** of the active quest (not the quest index used in `accept()`).
- Quest rewards (items, XP, etc.) are automatically added to the player's inventory/account.
- Quest completion conditions are checked on-chain — no way to cheat!
- Common reverts: `"Quest: objectives not met"` (conditions incomplete), `"Quest: not active"` (already completed or dropped).

---

## quest.drop()

Drop/abandon an active quest.

| Property | Value |
|----------|-------|
| **System ID** | `system.quest.drop` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `id` | `uint256` | Entity ID of the active quest to drop |

### Description

Drops (abandons) an active quest. The quest is removed from the player's active quest list. Any progress toward the quest's objectives is lost. Useful for clearing quests you no longer want to pursue.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(uint256 id) returns (bytes)"];
const system = await getSystem("system.quest.drop", ABI, operatorSigner);

const tx = await system.executeTyped(questEntityId);
await tx.wait();
console.log("Quest dropped!");
```

### Notes

- The `id` parameter is the **entity ID** of the active quest (not the quest index used in `accept()`).
- Cannot drop a completed quest.
- Repeatable quests can be re-accepted after dropping.

---

## Quest Lifecycle

```
Available Quest          Active Quest           Completed
    (index)                (entity ID)
       │                      │                     │
       ▼                      ▼                     ▼
  quest.accept(index) → quest.complete(entityId) → Rewards
                              │
                              └── quest.drop(entityId) → Abandoned
```

> **Note:** `accept()` takes a quest **index** (from the quest catalog), while `complete()` and `drop()` take the quest **entity ID** (assigned when the quest becomes active).

---

## Related Pages

- [Account](account.md) — General account management
- [Items & Crafting](items-and-crafting.md) — Items that may be quest requirements or rewards
- [Harvesting](harvesting.md) — Harvesting objectives in quests

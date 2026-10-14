> **Doc Class:** Core Resource
> **Canonical Source:** Kamigotchi on-chain contracts on Yominet and the official repository (`Asphodel-OS/kamigotchi-open`, the public mirror of the studio's development repo).
> **Freshness Rule:** Verify mutable values against canonical sources before merge.

# Goals & Scavenge

Community goals and scavenging mechanics for earning rewards through collective participation and exploration.

---

## goal.contribute()

Contribute to a community goal.

| Property | Value |
|----------|-------|
| **System ID** | `system.goal.contribute` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `goalIndex` | `uint32` | Index of the community goal |
| `amt` | `uint256` | Amount to contribute |

### Description

Contributes resources toward a community goal. Goals are collective objectives that all players work toward together. When the goal's total contributions reach the target threshold, all contributors can claim rewards.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = [
  "function executeTyped(uint32 goalIndex, uint256 amt) returns (bytes)",
];
const system = await getSystem("system.goal.contribute", ABI, operatorSigner);

const tx = await system.executeTyped(goalIndex, contributionAmount);
await tx.wait();
console.log("Contributed", contributionAmount, "to goal", goalIndex);
```

### Notes

- Contribution type is determined by the goal's objective entity — each objective has a `TypeComponent` (e.g., item type) and an `IndexComponent` (e.g., item index). When contributing, the matching resource is decremented from the player's account. Contributions are capped at the goal's target value. Goals also support tiered rewards (bronze/silver/gold based on contribution cutoffs) and proportional rewards.
- Your contribution amount is tracked for proportional reward distribution.
- Goals may have time limits or minimum contribution thresholds.

---

## goal.claim()

Claim reward from a completed goal.

| Property | Value |
|----------|-------|
| **System ID** | `system.goal.claim` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `goalIndex` | `uint32` | Index of the community goal |

### Description

Claims the player's share of rewards from a completed community goal. The reward amount may be proportional to the player's contribution. Can only be called after the goal has reached its target.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(uint32 goalIndex) returns (bytes)"];
const system = await getSystem("system.goal.claim", ABI, operatorSigner);

const tx = await system.executeTyped(goalIndex);
await tx.wait();
console.log("Goal reward claimed!");
```

### Notes

- Reverts if the goal is not yet completed.
- Reverts if the player hasn't contributed to this goal.
- Can only claim once per goal.

---

## scavenge.claim()

Claim scavenge points.

| Property | Value |
|----------|-------|
| **System ID** | `system.scavenge.claim` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `scavBarID` | `uint256` | Entity ID of the scavenge bar |

### Description

Claims accumulated scavenge points from a scavenge bar. Scavenging is a passive exploration mechanic where players discover resources or rewards by interacting with the game world.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(uint256 scavBarID) returns (bytes)"];
const system = await getSystem("system.scavenge.claim", ABI, operatorSigner);

const tx = await system.executeTyped(scavBarEntityId);
await tx.wait();
console.log("Scavenge points claimed!");
```

### Notes

- Scavenge bars are point-based reward systems:
  - **Points accumulate** during harvesting and are spent in increments of `tierCost` (set per bar in the registry's `ValueComponent`)
  - **Each tier's worth** of points produces one reward roll from the bar's reward entries (which may include droptable rewards)
  - **Remainder is kept** — points are not fully consumed; the leftover (modulo tierCost) carries over
  - **Keyed by `(field, index)`** — for example, `("NODE", nodeIndex)` ties bars to harvesting nodes, inheriting the node's affinity
- Scavenge bars may be room-specific or account-wide.

---

## Goal Lifecycle

```
  Goal Created (by game)
         │
         ▼
  ┌──────────────┐
  │ ACTIVE       │◄── goal.contribute(goalIndex, amt)
  │              │    (multiple players contribute)
  │ Progress: X% │
  └──────┬───────┘
         │ Target reached
         ▼
  ┌──────────────┐
  │ COMPLETED    │◄── goal.claim(goalIndex)
  │              │    (each contributor claims once)
  └──────────────┘
```

---

## Related Pages

- [Items & Crafting](items-and-crafting.md) — Items used for contributions or earned as rewards
- [Harvesting](harvesting.md) — Resource gathering for goal contributions
- [Account](account.md) — Account management

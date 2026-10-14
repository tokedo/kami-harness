> **Doc Class:** Core Resource
> **Canonical Source:** Kamigotchi on-chain contracts on Yominet and the official repository (`Asphodel-OS/kamigotchi-open`, the public mirror of the studio's development repo).
> **Freshness Rule:** Verify mutable values against canonical sources before merge.

# Kami

Kamis are the core entities in Kamigotchi. This page covers leveling, naming, sacrificing, equipment, item usage, skill management, and ONYX-based premium operations.

---

## level()

Level up a Kami.

| Property | Value |
|----------|-------|
| **System ID** | `system.kami.level` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `kamiID` | `uint256` | Entity ID of the Kami to level up |

### Description

Levels up the specified Kami if it has accumulated enough XP. XP is earned from harvesting, quests, and other gameplay activities. Each level may increase base stats.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(uint256 kamiID) returns (bytes)"];
const system = await getSystem("system.kami.level", ABI, operatorSigner);

const tx = await system.executeTyped(kamiEntityId);
await tx.wait();
console.log("Kami leveled up!");
```

### Notes

- Reverts with `"PetLevel: need more experience"` if the Kami doesn't have enough XP for the next level.
- XP thresholds are calculated dynamically: `cost = BASE * MULT^(level-1)`. Production values: BASE = 40 XP (level 1→2), MULT = 1.259 (i.e. each level costs ~25.9% more than the previous). For example: level 1→2 costs 40 XP, level 2→3 costs ~50 XP, level 5→6 costs ~100 XP, and so on.

---

## name()

Name or rename a Kami.

| Property | Value |
|----------|-------|
| **System ID** | `system.kami.name` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `kamiID` | `uint256` | Entity ID of the Kami |
| `name` | `string` | New name for the Kami |

### Description

Rename a Kami. **Costs 1 Holy Dust** (item index 11011) — the item is consumed from your inventory. The Kami must be in Room 11 (Temple by the Waterfall). For ONYX-based renaming, see [onyx.rename()](#onyxrename).

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(uint256 kamiID, string name) returns (bytes)"];
const system = await getSystem("system.kami.name", ABI, operatorSigner);

const tx = await system.executeTyped(kamiEntityId, "Sparkles");
await tx.wait();
```

### Notes

- Name must be 1–16 characters (bytes). Names must be unique across all Kamis. Costs 1 Holy Dust (item index 11011) and the Kami must be in room 11.
- See also: [onyx.rename()](#onyxrename) for premium rename.

---

## sacrificeCommit()

Sacrifice a Kami to receive loot.

| Property | Value |
|----------|-------|
| **System ID** | `system.kami.sacrifice.commit` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `kamiIndex` | `uint32` | ERC721 token index of the Kami to sacrifice (e.g., `42`) |

> **Note:** `kamiIndex` is the Kami's **ERC721 token index** (the same index used in `getKamiByIndex()`), not a positional index in any list. The contract accepts it as `uint32` here. See also [onyx.revive()](#onyxrevive) which accepts the same value as `uint256`.

### Description

Commits a Kami to the sacrifice process. The Kami is consumed, and a commit ID is generated. Use `sacrificeReveal()` to reveal the resulting loot.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(uint32 kamiIndex) returns (uint256)"];
const system = await getSystem("system.kami.sacrifice.commit", ABI, operatorSigner);

const tx = await system.executeTyped(kamiIndex);
const receipt = await tx.wait();
console.log("Sacrifice committed — use sacrificeReveal() to reveal loot");
```

> **Note:** This is a **destructive action** — the Kami is permanently consumed.

---

## sacrificeReveal()

Reveal loot from a committed sacrifice.

| Property | Value |
|----------|-------|
| **System ID** | `system.kami.sacrifice.reveal` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `commitID` | `uint256` | Commit ID from `sacrificeCommit()` |

### Description

Reveals the loot generated from a sacrifice commit. For batch reveals, use `executeTypedBatch()`.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = [
  "function executeTyped(uint256 commitID)",
  "function executeTypedBatch(uint256[] commitIDs)",
];
const system = await getSystem("system.kami.sacrifice.reveal", ABI, operatorSigner);

// Single reveal
const tx = await system.executeTyped(commitId);
await tx.wait();
console.log("Sacrifice loot revealed!");

// Batch reveal
const txBatch = await system.executeTypedBatch([commitId1, commitId2]);
await txBatch.wait();
```

### Notes

- **Pity system:** The sacrifice system tracks a per-account pity counter. Every **20 sacrifices**, the reveal is guaranteed to come from the **uncommon pity droptable** instead of the normal table. Every **100 sacrifices**, the reveal is guaranteed to come from the **rare pity droptable**. Rare pity takes precedence over uncommon pity (i.e., sacrifice #100 gives a rare, not an uncommon). The pity counter increments on each `sacrificeCommit()` and the appropriate droptable is selected at commit time.

---

## equipment.equip()

Equip an item to a Kami.

| Property | Value |
|----------|-------|
| **System ID** | `system.kami.equip` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `kamiID` | `uint256` | Entity ID of the Kami |
| `itemIndex` | `uint32` | Index of the item in inventory |

### Description

Equips an item from the player's inventory onto the specified Kami. The item is removed from inventory and applied to the Kami's equipment slot. Items provide stat boosts.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(uint256 kamiID, uint32 itemIndex) returns (uint256)"];
const system = await getSystem("system.kami.equip", ABI, operatorSigner);

const tx = await system.executeTyped(kamiEntityId, itemIndex);
await tx.wait();
```

### Notes

- **Slot is automatic:** You only pass the `itemIndex` — the system reads the item's `For` field from the registry to determine the slot. For example, if the item has `For = "Kami_Pet_Slot"` (the on-chain field name for the companion slot), it goes into the Kami's Pet slot. You do **not** pass a slot parameter when equipping.
- **Slot conflict handling:** If the target slot is already occupied, the existing item is **automatically unequipped** (returned to your inventory) before the new item is equipped. No need to manually unequip first.
- **Capacity limit:** Each entity has a default equipment capacity of **1** total equipped item (across all slots), expandable via the `EQUIP_CAPACITY_SHIFT` bonus. Adding new equipment (not replacing) checks capacity — replacing an item in the same slot does not count as adding.
- **Kami state requirement:** The Kami must be in `"RESTING"` state to equip items. Harvesting or dead Kamis cannot be equipped.
- **Item consumed:** The item is consumed from your account's inventory when equipped, and returned when unequipped.
- Equipment slot types use the format `"{EntityType}_{SlotName}_Slot"` — e.g., `"Kami_Pet_Slot"`, `"Account_Badge_Slot"`. Currently all equipment items in the game use the `Kami_Pet_Slot`. See [Equipment Reference](../game-data.md#equipment) for the full list.

---

## equipment.unequip()

Unequip an item from a Kami.

| Property | Value |
|----------|-------|
| **System ID** | `system.kami.unequip` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `kamiID` | `uint256` | Entity ID of the Kami |
| `slotType` | `string` | Equipment slot type to unequip |

### Description

Removes the item from the specified slot and returns it to inventory.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(uint256 kamiID, string slotType) returns (uint32)"];
const system = await getSystem("system.kami.unequip", ABI, operatorSigner);

const tx = await system.executeTyped(kamiEntityId, "Kami_Pet_Slot"); // slot string from item registry
await tx.wait();
```

### Notes

- Valid slot type strings follow the format `"{EntityType}_{SlotName}_Slot"` — e.g., `"Kami_Pet_Slot"`, `"Kami_Hat_Slot"`, `"Account_Badge_Slot"`. The slot value is defined on each equipment item in the registry's `For` field.

---

## kami.item.use()

Use an item on a Kami (e.g., feed, heal).

| Property | Value |
|----------|-------|
| **System ID** | `system.kami.use.item` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `kamiID` | `uint256` | Entity ID of the Kami |
| `itemIndex` | `uint32` | Index of the item in inventory |

### Description

Uses a consumable item on a Kami. Common use cases include feeding (restoring health) and applying buffs. The item is consumed from inventory. The Kami must pass a **cooldown check** (`LibKami.verifyCooldown`) — if on cooldown, the call reverts. The Kami must also be in the **same room** as the account (`LibKami.verifyRoom`).

> **Bot warning:** Using an item resets the Kami's harvest intensity timer (`LibKami.resetIntensity`) and may reset harvest bonuses (`LibBonus.resetUponHarvestAction`). If your Kami is mid-harvest, using items will reset intensity accumulation.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(uint256 kamiID, uint32 itemIndex) returns (bytes)"];
const system = await getSystem("system.kami.use.item", ABI, operatorSigner);

const tx = await system.executeTyped(kamiEntityId, foodItemIndex);
await tx.wait();
```

---

## item.cast()

Cast an item on an enemy Kami.

| Property | Value |
|----------|-------|
| **System ID** | `system.kami.cast.item` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `targetID` | `uint256` | Entity ID of the **target** (enemy) Kami |
| `itemIndex` | `uint32` | Index of the item in inventory |

### Description

Casts a combat item at an enemy Kami. Used in PvP or PvE scenarios to apply debuffs or deal damage. Each cast costs **10 stamina** (`LibAccount.depleteStamina(components, accID, 10)`). The caster's Kami must be in the **same room** as the target Kami (`LibKami.verifyRoom`).

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(uint256 targetID, uint32 itemIndex) returns (bytes)"];
const system = await getSystem("system.kami.cast.item", ABI, operatorSigner);

const tx = await system.executeTyped(enemyKamiId, combatItemIndex);
await tx.wait();
```

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
| `holderID` | `uint256` | Entity ID of the Kami (or Account for account skills) |
| `skillIndex` | `uint32` | Index of the skill to upgrade |

### Description

Upgrades the specified skill on a Kami. Requires the Kami to have available skill points.

> **Note:** The contract parameter is named `holderID` (since the system also supports account skills), but for Kami skill upgrades you pass the Kami's entity ID.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(uint256 holderID, uint32 skillIndex) returns (bytes)"];
const system = await getSystem("system.skill.upgrade", ABI, operatorSigner);

const tx = await system.executeTyped(kamiEntityId, skillIndex);
await tx.wait();
```

> **Note:** See also [Skills & Relationships](skills-and-relationships.md) for more detail on the skill system.

---

## skill.reset()

Reset all skills on a Kami (respec).

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

Resets all skill points on a Kami or Account, allowing them to be redistributed. Consumes 1 Respec Potion (item index 11403) from the account's inventory. The target must be in `"RESTING"` state.

> **Note:** The contract parameter is `targetID` and supports both Kami and Account entity IDs. The system checks the entity type and handles ownership verification accordingly.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(uint256 targetID) returns (bytes)"];
const system = await getSystem("system.skill.respec", ABI, operatorSigner);

const tx = await system.executeTyped(kamiEntityId);
await tx.wait();
```

> **Note:** For ONYX-based respec, see [onyx.respec()](#onyxrespec).

---

## onyx.rename()

Rename a Kami using $ONYX.

> **⚠️ Currently Disabled:** This system reverts with 'Onyx Features are temporarily disabled.' Calls will fail until re-enabled.

| Property | Value |
|----------|-------|
| **System ID** | `system.kami.onyx.rename` |
| **Wallet** | 🔐 Owner |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `kamiID` | `uint256` | Entity ID of the Kami |
| `name` | `string` | New name |

### Description

Premium rename operation that costs $ONYX. Use the free `name()` function for the first rename; this is for subsequent renames or special naming.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

// Must use OWNER wallet
const ABI = ["function executeTyped(uint256 kamiID, string name) returns (bytes)"];
const system = await getSystem("system.kami.onyx.rename", ABI, ownerSigner);

const tx = await system.executeTyped(kamiEntityId, "MegaSparkles");
await tx.wait();
```

### Notes

- ONYX cost per rename is 5,000 $ONYX (item index 100). Same name validation as `name()`: 1–16 characters, must be unique, Kami must be in room 11.
- Requires $ONYX approval to the system contract prior to calling.

---

## onyx.revive()

Revive a dead Kami using $ONYX.

| Property | Value |
|----------|-------|
| **System ID** | `system.kami.onyx.revive` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `kamiIndex` | `uint256` | ERC721 token index of the dead Kami (e.g., `42`) |

> **Note:** Pass the Kami's **ERC721 token index** (e.g., `42`) as a `uint256`. This is the same token index used in `getKamiByIndex()`, NOT a positional index in any list. The contract decodes it as a `uint32` internally.

### Description

Revives a Kami that has died (health reached 0). Costs 33 $ONYX (item index 100). The Kami's state is set from `"DEAD"` to `"RESTING"` and health is restored to 33.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(uint256 id) returns (bytes)"];
const system = await getSystem("system.kami.onyx.revive", ABI, operatorSigner);

const tx = await system.executeTyped(deadKamiIndex);
await tx.wait();
console.log("Kami revived!");
```

### Notes

- ONYX cost is 33 $ONYX per revive. Health is restored to 33.
- Requires $ONYX approval to the system contract.

---

## onyx.respec()

Respec a Kami's skills using $ONYX. Costs 10,000 $ONYX.

> **⚠️ Currently Disabled:** This system reverts with 'Onyx Features are temporarily disabled.' Calls will fail until re-enabled.

| Property | Value |
|----------|-------|
| **System ID** | `system.kami.onyx.respec` |
| **Wallet** | 🔐 Owner |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `kamiID` | `uint256` | Entity ID of the Kami |

### Description

Resets all skill points on a Kami via $ONYX payment. Differs from the free `skill.reset()` in that it may bypass cooldowns or other restrictions.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

// Must use OWNER wallet
const ABI = ["function executeTyped(uint256 kamiID) returns (bytes)"];
const system = await getSystem("system.kami.onyx.respec", ABI, ownerSigner);

const tx = await system.executeTyped(kamiEntityId);
await tx.wait();
```

---

## send()

Send in-world (staked) Kamis to another player without unstaking.

| Property | Value |
|----------|-------|
| **System ID** | `system.kami.send` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters (single)

| Name | Type | Description |
|------|------|-------------|
| `kamiIndex` | `uint32` | ERC721 token index of the Kami to send |
| `toAddress` | `address` | **Operator wallet address** of the recipient |

### Parameters (batch)

| Name | Type | Description |
|------|------|-------------|
| `kamiIndices` | `uint32[]` | Array of ERC721 token indices of Kamis to send |
| `toAddress` | `address` | **Operator wallet address** of the recipient |

### Description

Transfers one or more in-world Kamis to another player's account. Unlike NFT transfers (`system.kami721.transfer`), this operates entirely within the game world — Kamis stay staked and playable. The recipient is identified by their **operator wallet address** (not their owner address). If a Kami is currently listed on the marketplace, its listing is automatically cancelled before transfer. A purchase cooldown is applied to the transferred Kami.

> **Batch limit:** Up to **9 Kamis** per transaction.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = [
  "function executeTyped(uint32 kamiIndex, address toAddress) returns (bytes)",
  "function executeTyped(uint32[] kamiIndices, address toAddress) returns (bytes)",
];
const system = await getSystem("system.kami.send", ABI, operatorSigner);

// Single send
const tx = await system["executeTyped(uint32,address)"](kamiIndex, recipientOperatorAddress);
await tx.wait();

// Batch send
const txBatch = await system["executeTyped(uint32[],address)"](
  [kamiIndex1, kamiIndex2],
  recipientOperatorAddress
);
await txBatch.wait();
```

### Notes

- The `toAddress` parameter is the recipient's **operator address**, not their owner address. The system resolves the recipient's account via `LibAccount.getByOperator()`.
- Cannot send to yourself — reverts with `"KamiSend: cannot send to self"`.
- Kami must be in `RESTING` or `LISTED` state. Listed Kamis have their marketplace listings automatically cancelled.
- A purchase cooldown (`KAMI_MARKET_PURCHASE_COOLDOWN`, default 1 hour) is applied to each transferred Kami.
- Emits a `KAMI_SEND` event with sender account ID, target account ID, and kami index.

---

## Related Pages

- [Harvesting](harvesting.md) — Kami-based harvesting
- [Minting](minting.md) — Acquiring new Kamis via gacha
- [Portal](portal.md) — Staking/unstaking Kami NFTs
- [Skills & Relationships](skills-and-relationships.md) — Skill system details
- [Echo](echo.md) — Force-emit Kami data if state is stale

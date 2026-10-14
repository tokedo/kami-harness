> **Doc Class:** Core Resource
> **Canonical Source:** Kamigotchi on-chain contracts on Yominet and the official repository (`Asphodel-OS/kamigotchi-open`, the public mirror of the studio's development repo).
> **Freshness Rule:** Verify mutable values against canonical sources before merge.

# Items & Crafting

Item management functions for burning, crafting, using, transferring, and revealing droptable items.

---

## item.burn()

Burn items from inventory.

| Property | Value |
|----------|-------|
| **System ID** | `system.item.burn` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `indices` | `uint32[]` | Array of item indices to burn |
| `amts` | `uint256[]` | Array of amounts to burn for each item |

### Description

Permanently destroys items from the player's inventory. Useful for clearing unwanted items or fulfilling burn requirements. This action is irreversible.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = [
  "function executeTyped(uint32[] indices, uint256[] amts) returns (bytes)",
];
const system = await getSystem("system.item.burn", ABI, operatorSigner);

// Burn 10 of item #2 and 5 of item #8
const tx = await system.executeTyped([2, 8], [10, 5]);
await tx.wait();
console.log("Items burned");
```

### Notes

- `indices` and `amts` arrays must have matching lengths.
- **Irreversible** — burned items cannot be recovered.
- Reverts if you don't have enough of the specified items.

---

## item.craft()

Craft an item from a recipe.

| Property | Value |
|----------|-------|
| **System ID** | `system.craft` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `recipeIndex` | `uint32` | Index of the crafting recipe |
| `amount` | `uint256` | Number of items to craft |

### Description

Crafts items using a predefined recipe. The required ingredients are consumed from inventory, and the crafted item is added. Recipe definitions (ingredients, outputs) are stored on-chain.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = [
  "function executeTyped(uint32 recipeIndex, uint256 amount) returns (bytes)",
];
const system = await getSystem("system.craft", ABI, operatorSigner);

// Craft 3 of recipe #5
const tx = await system.executeTyped(5, 3);
await tx.wait();
console.log("Items crafted!");
```

### Notes

- Reverts if you lack the required ingredients.
- Recipes are defined in the recipe registry (loaded from CSV at deployment). Each recipe has: input item indices + amounts, output item index + amount, XP output, and stamina cost. Some recipes also have tool requirements. Set via registry — query on-chain for current recipe list and ingredient requirements.
- Crafting multiple at once is more gas-efficient than individual calls.

---

## account.item.use()

Use an item from inventory (account-level).

| Property | Value |
|----------|-------|
| **System ID** | `system.account.use.item` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `itemIndex` | `uint32` | Index of the item to use |
| `amt` | `uint256` | Amount to use |

### Description

Uses a consumable item from the account's inventory. Effects vary by item type (healing, buffs, quest progress, etc.). The item is consumed.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = [
  "function executeTyped(uint32 itemIndex, uint256 amt) returns (bytes)",
];
const system = await getSystem("system.account.use.item", ABI, operatorSigner);

const tx = await system.executeTyped(potionIndex, 1);
await tx.wait();
```

### Notes

- This applies the item to the **account** (not a specific Kami). For Kami-specific item usage, see [Kami — kami.item.use()](kami.md#kamiitemuse).
- Item effects are defined on-chain per item type.

---

## item.transfer()

Transfer items to another account.

| Property | Value |
|----------|-------|
| **System ID** | `system.item.transfer` |
| **Wallet** | 🔐 Owner |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `indices` | `uint32[]` | Array of item indices to transfer |
| `amts` | `uint256[]` | Array of amounts for each item |
| `targetID` | `uint256` | Entity ID of the receiving account |

### Description

Transfers items from the caller's inventory to another player's account. Both players must be registered.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = [
  "function executeTyped(uint32[] indices, uint256[] amts, uint256 targetID) returns (bytes)",
];
const system = await getSystem("system.item.transfer", ABI, ownerSigner);

// Transfer 5 of item #3 and 10 of item #7 to another account
const tx = await system.executeTyped([3, 7], [5, 10], targetAccountEntityId);
await tx.wait();
console.log("Items transferred!");
```

### Notes

- `indices` and `amts` arrays must have matching lengths.
- **Batch limit:** Up to **8 item types** per transaction.
- The receiver's `targetID` is their entity ID (not wallet address).
- Reverts if you don't have sufficient items.
- **Transfer fee:** Each item type (index) transferred costs **15 MUSU**. The total fee is `indices.length × 15 MUSU`, deducted from the sender's inventory. For example, transferring 3 different item types costs 45 MUSU regardless of the amounts transferred.

---

## droptable.reveal()

Reveal items from a droptable.

| Property | Value |
|----------|-------|
| **System ID** | `system.droptable.item.reveal` |
| **Wallet** | Any (permissionless) |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `ids` | `uint256[]` | Array of droptable entity IDs to reveal |

### Description

Reveals items from pending droptable results. Droptables generate randomized loot from activities like harvesting, quests, and sacrifices. Items stay in a "pending reveal" state until this function is called.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(uint256[] ids) returns (bytes)"];
const system = await getSystem("system.droptable.item.reveal", ABI, operatorSigner);

const droptableIds = [dropId1, dropId2, dropId3];
const tx = await system.executeTyped(droptableIds);
await tx.wait();
console.log("Droptable items revealed!");
```

### Notes

- Batch reveals are more gas-efficient.
- The droptable IDs come from `Store_SetRecord` events emitted during harvest collection, quest completion, or sacrifice reveal. Parse the transaction receipt to extract them — see [Parsing Transaction Events](../entity-ids.md#parsing-transaction-events).
- Revealing uses on-chain randomness — items are determined at reveal time.

---

## Related Pages

- [Kami — equipment](kami.md#equipmentequip) — Equipping items on Kamis
- [Kami — kami.item.use()](kami.md#kamiitemuse) — Using items on specific Kamis
- [Trading](trading.md) — Trading items with other players
- [Merchant Listings](listings.md) — Buying/selling items from NPCs
- [Harvesting](harvesting.md) — Earning items via harvesting

> **Doc Class:** Core Resource
> **Canonical Source:** Kamigotchi on-chain contracts on Yominet and the official repository (`Asphodel-OS/kamigotchi-open`, the public mirror of the studio's development repo).
> **Freshness Rule:** Verify mutable values against canonical sources before merge.

# Merchant Listings

NPC merchants offer items for purchase and accept items for sale. Each merchant has a fixed inventory and pricing.

---

## listing.buy()

Buy items from an NPC merchant.

| Property | Value |
|----------|-------|
| **System ID** | `system.listing.buy` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `merchantIndex` | `uint32` | Index of the NPC merchant |
| `itemIndices` | `uint32[]` | Array of item indices in the merchant's inventory |
| `amts` | `uint32[]` | Array of amounts to buy for each item |

### Description

Purchases items from an NPC merchant's inventory. The cost is deducted from the player's in-game currency/items (depending on the merchant's pricing). Supports buying multiple items in a single transaction.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = [
  "function executeTyped(uint32 merchantIndex, uint32[] itemIndices, uint32[] amts) returns (bytes)",
];
const system = await getSystem("system.listing.buy", ABI, operatorSigner);

// Buy 3 of merchant item #0 and 1 of merchant item #2
const tx = await system.executeTyped(merchantIndex, [0, 2], [3, 1]);
await tx.wait();
console.log("Items purchased from merchant!");
```

### Notes

- `itemIndices` and `amts` arrays must have matching lengths.
- Merchant inventories and pricing are defined in the listing registry (loaded from CSV at deployment). Each listing links an NPC to an item with a currency and base value. Buy pricing can be `FIXED` (static) or `GDA` (Gradual Dutch Auction — price decays over time). Sell pricing can be `FIXED` or `SCALED` (price scales with quantity sold — higher volumes yield lower per-unit prices). Listings may also have requirements (e.g., relationship flags, item ownership). Set via registry — query on-chain for current merchant inventories.
- Merchants may have limited stock or require specific currencies.
- The player must be in the same room as the merchant — move with [account.move()](account.md#move) first.

---

## listing.sell()

Sell items to an NPC merchant.

| Property | Value |
|----------|-------|
| **System ID** | `system.listing.sell` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `merchantIndex` | `uint32` | Index of the NPC merchant |
| `itemIndices` | `uint32[]` | Array of item indices from the player's inventory |
| `amts` | `uint32[]` | Array of amounts to sell for each item |

### Description

Sells items from the player's inventory to an NPC merchant. The merchant pays the player with in-game currency/items based on its buy prices. Supports selling multiple items in a single transaction.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = [
  "function executeTyped(uint32 merchantIndex, uint32[] itemIndices, uint32[] amts) returns (bytes)",
];
const system = await getSystem("system.listing.sell", ABI, operatorSigner);

// Sell 10 of item #5 and 20 of item #12 to merchant
const tx = await system.executeTyped(merchantIndex, [5, 12], [10, 20]);
await tx.wait();
console.log("Items sold to merchant!");
```

### Notes

- Not all items may be sellable to a given merchant.
- Buy prices may differ from sell prices (merchants take a spread).
- The player must be in the merchant's room.

---

## Auction

In addition to merchant listings, Kamigotchi has an auction system:

### auction.buy()

Buy items from the auction house.

| Property | Value |
|----------|-------|
| **System ID** | `system.auction.buy` |
| **Wallet** | 🔐 Owner |
| **Gas** | Default |

#### Parameters

| Name | Type | Description |
|------|------|-------------|
| `itemIndex` | `uint32` | Index of the auction item |
| `amt` | `uint32` | Amount to buy |

#### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = [
  "function executeTyped(uint32 itemIndex, uint32 amt) returns (bytes)",
];
const system = await getSystem("system.auction.buy", ABI, ownerSigner);

const tx = await system.executeTyped(auctionItemIndex, 1);
await tx.wait();
console.log("Auction item purchased!");
```

> **Note:** Auctions use a Gradual Dutch Auction (GDA) pricing model. Each auction is created with: a sale item index, a payment item index, a target price, a time period, a decay rate, an emission rate, a max supply, and a start timestamp. The price decays over time until purchased. The `AuctionBuySystem` ABI is `executeTyped(uint32 itemIndex, uint32 amt)` — it calculates the current GDA price, deducts the payment currency, and credits the purchased item. Auction parameters are set via registry — query on-chain for current auctions.

### GDA Pricing Explained

Gradual Dutch Auction pricing works as follows:

- Each auction starts with a **target price** and **decay rate**
- The price decreases over time until someone buys
- Each purchase resets the price curve upward
- This creates a self-regulating market price

To check the current price without buying, use `staticCall`:

```javascript
try {
  await auctionSystem.executeTyped.staticCall(itemIndex, 1);
  console.log("Current price is affordable");
} catch (e) {
  console.log("Cannot afford at current price or auction inactive");
}
```

### Wallet Type Reference

Throughout this documentation:
- 🔐 **Owner** — Must be called from the owner wallet
- 🎮 **Operator** — Can be called from the operator wallet

---

## Related Pages

- [Items & Crafting](items-and-crafting.md) — Managing inventory items
- [Account — move()](account.md#move) — Moving to merchant rooms
- [Skills & Relationships](skills-and-relationships.md) — NPC relationship effects on merchant pricing

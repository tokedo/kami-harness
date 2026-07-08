> **Doc Class:** Core Resource
> **Canonical Source:** Kamigotchi on-chain contracts on Yominet and the official repository (`Asphodel-OS/kamigotchi`).
> **Freshness Rule:** Verify mutable values against canonical sources before merge.

# Trading

Player-to-player trading allows exchanging items directly. Trades follow a create → execute → complete lifecycle with on-chain escrow.

---

## trade.create()

Create a new trade offer.

| Property | Value |
|----------|-------|
| **System ID** | `system.trade.create` |
| **Wallet** | 🔐 Owner |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `buyIndices` | `uint32[]` | Item indices the maker wants to receive |
| `buyAmts` | `uint256[]` | Amounts for each buy item |
| `sellIndices` | `uint32[]` | Item indices the maker is offering |
| `sellAmts` | `uint256[]` | Amounts for each sell item |
| `targetID` | `uint256` | Target account entity ID (0 for open trade) |

### Description

Creates a trade offer. The **maker's sell items are transferred from inventory to a trade entity** (escrow) immediately upon creation. The trade enters `PENDING` status.

If `targetID` is non-zero, only that specific account can execute the trade. If zero, any player can take it.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = [
  "function executeTyped(uint32[] buyIndices, uint256[] buyAmts, uint32[] sellIndices, uint256[] sellAmts, uint256 targetID) returns (bytes)",
];
const system = await getSystem("system.trade.create", ABI, ownerSigner);

// I want to trade 5 of item #3 for 10 of item #7
const tx = await system.executeTyped(
  [7],   // items I want
  [10],  // amounts I want
  [3],   // items I'm offering
  [5],   // amounts I'm offering
  0      // open trade (anyone can take)
);
await tx.wait();
console.log("Trade created!");
```

### Notes

- **Sell items are immediately escrowed** — removed from your inventory when the trade is created.
- The `buyIndices`/`buyAmts` and `sellIndices`/`sellAmts` arrays must have matching lengths.
- **Each trade is exactly 1 buy item + 1 sell item.** One side must be MUSU (item index 1) — direct item-for-item barter is not supported.
- Items with the `NOT_TRADABLE` flag cannot be traded.
- There is a `MAX_TRADES_PER_ACCOUNT` config limit on the number of open trades per account.
- Use `targetID = 0` for public trades, or specify an account entity ID for private trades.

---

## trade.execute()

Execute (accept) a pending trade.

| Property | Value |
|----------|-------|
| **System ID** | `system.trade.execute` |
| **Wallet** | 🔐 Owner |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `tradeID` | `uint256` | Entity ID of the trade |

### Description

Called by the **taker** (not the maker) to accept a pending trade. The taker's items (matching the maker's `buyIndices`/`buyAmts`) are transferred to the trade entity. The trade moves to `EXECUTED` status.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(uint256 tradeID) returns (bytes)"];
const system = await getSystem("system.trade.execute", ABI, ownerSigner);

const tx = await system.executeTyped(tradeEntityId);
await tx.wait();
console.log("Trade executed! Waiting for maker to complete.");
```

### Notes

- The caller **must not be the maker** — only the taker can execute.
- The trade must be in `PENDING` status.
- If the trade has a `targetID`, only that account can execute it.
- The taker must have the required items in inventory.

---

## trade.complete()

Complete an executed trade.

| Property | Value |
|----------|-------|
| **System ID** | `system.trade.complete` |
| **Wallet** | 🔐 Owner |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `tradeID` | `uint256` | Entity ID of the trade |

### Description

Called by the **maker** to finalize the trade. Items are distributed to both parties:
- Maker receives the taker's items (buy items)
- Taker receives the maker's items (sell items)

The trade entity is resolved.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(uint256 tradeID) returns (bytes)"];
const system = await getSystem("system.trade.complete", ABI, ownerSigner);

const tx = await system.executeTyped(tradeEntityId);
await tx.wait();
console.log("Trade completed! Items exchanged.");
```

### Notes

- Only the **maker** can complete the trade.
- The trade must be in `EXECUTED` status (taker has already called `execute()`).

---

## trade.cancel()

Cancel a pending trade.

| Property | Value |
|----------|-------|
| **System ID** | `system.trade.cancel` |
| **Wallet** | 🔐 Owner |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `tradeID` | `uint256` | Entity ID of the trade |

### Description

Cancels a trade and **returns the escrowed items** to the maker's inventory. Only the maker can cancel, and only while the trade is in `PENDING` status.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(uint256 tradeID) returns (bytes)"];
const system = await getSystem("system.trade.cancel", ABI, ownerSigner);

const tx = await system.executeTyped(tradeEntityId);
await tx.wait();
console.log("Trade cancelled — items returned to inventory.");
```

### Notes

- Only the **maker** can cancel.
- Trade must be in `PENDING` status — cannot cancel an `EXECUTED` trade.
- Escrowed sell items are returned to the maker's inventory.

---

## Fees

Trades incur MUSU fees at multiple stages:

- **Creation fee:** A flat MUSU fee (`TRADE_CREATION_FEE` config) is deducted from the maker's inventory when creating a trade.
- **Delivery fee:** A flat MUSU fee (`TRADE_DELIVERY_FEE` config) is charged to the caller on **every** trade action (create, execute, complete, cancel). Being in the Trade Room (room 66) waives this fee for that action.
- **Trade tax:** On both execution and completion, a percentage-based tax is applied to MUSU amounts exchanged. The rate is configured via `TRADE_TAX_RATE` as `[precision, numerator]` — tax = `amount × numerator / 10^precision`. Only MUSU (item index 1, see [Entity Discovery — Key Constants](../entity-ids.md#key-constants)) is taxed; non-MUSU items pass through untaxed. The tax is deducted from the received amounts.

---

## Trade Lifecycle

```
              Maker                          Taker
                │                              │
                ▼                              │
         trade.create()                        │
         Status: PENDING                       │
         (sell items escrowed)                 │
                │                              │
                │◄─────── trade.execute() ─────┘
                │         Status: EXECUTED
                │         (buy items escrowed)
                ▼
         trade.complete()
         Status: COMPLETED
         (items distributed)

    ─── OR ───

         trade.cancel()    (only from PENDING)
         Status: CANCELLED
         (sell items returned)
```

### Trade Statuses

| Status | Description | Actions Available |
|--------|-------------|-------------------|
| `PENDING` | Maker created, waiting for taker | `execute()` (taker), `cancel()` (maker) |
| `EXECUTED` | Taker accepted, waiting for maker to finalize | `complete()` (maker) |
| `COMPLETED` | Items exchanged, trade resolved | None |
| `CANCELLED` | Maker cancelled, items returned | None |

---

## Discovering Trades

Trade entity IDs are **non-deterministic** — they are assigned by `world.getUniqueEntityId()` at creation time and cannot be derived from known inputs.

### For Trade Creators (Makers)

Capture the trade ID from the creation transaction receipt:

```javascript
import { extractEntityIds } from "./event-helpers.js";

const tradeTx = await tradeSystem.executeTyped(buyIdx, buyAmt, sellIdx, sellAmt, 0);
const tradeReceipt = await tradeTx.wait();
const tradeId = extractEntityIds(tradeReceipt)[0];
console.log("Trade entity ID:", tradeId);
// Store this ID — you'll need it to complete or cancel the trade
```

### For Trade Takers

There is currently no on-chain function to enumerate open trades. To discover trades available to execute:

1. **Parse events** — Monitor `Store_SetRecord` events for new trade entity creation. See [Parsing Transaction Events](../entity-ids.md#parsing-transaction-events).
2. **Use an indexer** — Query an off-chain indexer for open trades (if available).
3. **Direct sharing** — The maker shares the trade ID out-of-band (e.g., via chat).

> **Note:** For targeted trades (`targetID != 0`), only the specified account can execute. For open trades (`targetID = 0`), anyone can take them.

---

## Related Pages

- [Items & Crafting](items-and-crafting.md) — Item management
- [Account](account.md) — Account setup for trading
- [Social / Friends](social.md) — Trading with specific friends

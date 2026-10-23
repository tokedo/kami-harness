> **Doc Class:** Core Resource
> **Canonical Source:** Kamigotchi on-chain contracts on Yominet and the official repository (`Asphodel-OS/kamigotchi-open`, the public mirror of the studio's development repo).
> **Freshness Rule:** Verify mutable values against canonical sources before merge.

# Gacha / Minting

The gacha system lets players mint new Kamis using gacha tickets. Minting follows a commit-reveal pattern for fair randomness.

---

## Mint

Mint new Kamis using gacha tickets.

| Property | Value |
|----------|-------|
| **System ID** | `system.kami.gacha.mint` |
| **Wallet** | 🔐 Owner or 🎮 Operator (since patch 0.4.5) |
| **Gas** | **4,000,000 + 3,000,000 per Kami** |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `amount` | `uint256` | Number of Kamis to mint |

### Description

Commits a mint request for one or more Kamis. Consumes gacha tickets from the player's inventory. This is the **commit** phase of the commit-reveal pattern — the Kami's traits are not determined yet.

After minting, call `reveal()` to reveal the Kamis.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(uint256 amount) returns (bytes)"];
const system = await getSystem("system.kami.gacha.mint", ABI, ownerSigner);

const mintAmount = 3;
const gasLimit = 4_000_000 + 3_000_000 * mintAmount; // Scale with amount

const tx = await system.executeTyped(mintAmount, { gasLimit });
await tx.wait();
console.log("Mint committed! Use reveal() to reveal your Kamis.");
```

### Notes

- **Maximum 5 Kamis per mint transaction** — the contract enforces `require(amount <= 5)`. For larger mints, split across multiple transactions.
- **Gas scales with mint amount**: base 4M + 3M per Kami.
- Requires sufficient gacha tickets — buy via the auction system (see [Buy Gacha Tickets](#buy-gacha-tickets) below).
- Returns commit IDs needed for `reveal()`.

---

## Reveal

Reveal minted Kamis.

| Property | Value |
|----------|-------|
| **System ID** | `system.kami.gacha.reveal` |
| **Wallet** | 🌐 Any (no wallet restriction) |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `rawCommitIDs` | `uint256[]` | Array of commit IDs from mint |

### Description

Reveals the traits (species, stats, rarity) of Kamis from previous mint commits. This is the **reveal** phase — on-chain randomness determines each Kami's attributes.

> **Note:** This function is owner-agnostic — it can be called by **anyone**, not just the minter. The revealed Kamis are sent to the original minting account regardless of who calls `reveal()`.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

// reveal() is a named function, NOT executeTyped
const ABI = ["function reveal(uint256[] rawCommitIDs) external returns (uint256[])"];
const system = await getSystem("system.kami.gacha.reveal", ABI, operatorSigner);

const commitIds = [commitId1, commitId2, commitId3];
const tx = await system.reveal(commitIds);
await tx.wait();
console.log("Kamis revealed!");
```

### Notes

- **Wait at least 1 block between `mint()` and `reveal()`** for randomness security. On Yominet whole days in October 2026 averaged 1.5 to 2.3 s per block (37,800 to 53,800 blocks a day), varying with activity, and blocks arrive in bursts (the gap between blocks ranges from under a second to tens of seconds), so a fixed delay does not guarantee the next block; wait until the block number has moved past the mint's block:
  ```javascript
  const mintReceipt = await mintTx.wait();
  while ((await provider.getBlockNumber()) <= mintReceipt.blockNumber) {
    await new Promise((r) => setTimeout(r, 1000)); // wait for a later block
  }
  await revealSystem.reveal(commitIds);
  ```
- Batch reveals are more gas-efficient.
- After revealing, use [echo.kamis()](echo.md) if the UI doesn't update.

---

## Reroll

Reroll Kamis.

| Property | Value |
|----------|-------|
| **System ID** | `system.kami.gacha.reroll` |
| **Wallet** | 🔐 Owner or 🎮 Operator (since patch 0.4.5) |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `kamiIDs` | `uint256[]` | Array of Kami entity IDs to reroll |

### Description

Rerolls one or more Kamis, re-randomizing their traits. The original Kami is replaced with a new random result. This is a second chance mechanic for players unhappy with their initial mint results.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

// reroll() is a named function, NOT executeTyped
const ABI = ["function reroll(uint256[] kamiIDs) external returns (uint256[])"];
const system = await getSystem("system.kami.gacha.reroll", ABI, ownerSigner);

const kamiIds = [kamiId1, kamiId2];
const tx = await system.reroll(kamiIds);
await tx.wait();
console.log("Kamis rerolled!");
```

### Notes

- Rerolling consumes 1 Reroll Ticket (item index 11) per Kami. The selected Kamis are deposited into the gacha pool and new ones are drawn.
- **Destructive** — the original Kami's traits are replaced permanently.
- Requires a subsequent `reveal()` call — rerolling creates commit entities that must be revealed (same as initial mint).

---

## Buy Gacha Tickets

| Property | Value |
|----------|-------|
| **System ID** | `system.auction.buy` |
| **Wallet** | 🔐 Owner or 🎮 Operator (since patch 0.4.5) |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `itemIndex` | `uint32` | Item to purchase (10 = Gacha Ticket) |
| `amt` | `uint32` | Number of tickets to buy |

Gacha tickets are purchased via the **auction system** (`system.auction.buy`) using a **Gradual Dutch Auction (GDA)** pricing model. Tickets cost **$MUSU** (item index 1).

> **Important:** You must be on the **vending machine tile** (the auction room) to buy gacha tickets. Move there first with [account.move()](account.md#move).

> **History:** The original `buyPublic()` / `buyWL()` functions on `system.buy.gacha.ticket` were used during the initial launch period and are no longer active. All ticket purchases now go through the auction system.

### How It Works

The auction uses GDA pricing — the price starts high and decays over time until purchased. Each ticket purchase resets the price curve. This creates a fair market-driven pricing mechanism.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

// Gacha tickets are bought via the auction system, paid in $MUSU
const ABI = [
  "function executeTyped(uint32 itemIndex, uint32 amt) returns (bytes)",
];
const system = await getSystem("system.auction.buy", ABI, ownerSigner);

// Buy 1 gacha ticket (item index 10) — price is determined by the GDA curve
const tx = await system.executeTyped(10, 1); // itemIndex 10 = Gacha Ticket
await tx.wait();
console.log("Gacha ticket purchased via auction!");
```

### Notes

- **Payment currency:** $MUSU (item index 1) — earn via harvesting, quests, merchant sales, or player trading.
- **Pricing:** Gradual Dutch Auction — price decays over time, resets on each purchase. To check the current price, use `staticCall` — the transaction will consume MUSU equal to the current price:
  ```javascript
  try {
    await system.executeTyped.staticCall(10, 1); // Simulate buying 1 ticket
    console.log("You can afford a ticket at current price");
  } catch (e) {
    console.log("Cannot afford ticket or auction not active");
  }
  ```
- **Location requirement:** Must be on the vending machine tile to purchase.
- See [Merchant Listings — auction.buy()](listings.md#auctionbuy) for full auction system details.

---

## Minting Lifecycle

```
  auction.buy()                     mint(amount)
  (pay $MUSU via GDA)                    │
         │                               ▼
         ▼                         Commit IDs generated
  Gacha Tickets ──── mint() ──────▶      │
  in Inventory                           ▼
                                   reveal(commitIDs)
                                         │
                                         ▼
                                   Kamis Revealed!
                                         │
                                         ├── Keep → Play!
                                         │
                                         └── reroll(kamiIDs)
                                                  │
                                                  ▼
                                             New traits!
```

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| Insufficient gacha tickets | Tried to mint without enough tickets | Buy tickets via `system.auction.buy` first |
| Commit not found | Invalid commit ID passed to `reveal()` | Extract commit IDs from the mint transaction receipt |
| Same-block reveal | Called `reveal()` in the same block as `mint()` | Wait until the block number has moved past the mint's block (count blocks, never seconds) |
| Insufficient MUSU | Cannot afford gacha ticket at current GDA price | Earn MUSU via harvesting, then retry |

See [Common Errors](../errors.md) for the full error reference.

---

## Related Pages

- [Kami](kami.md) — Managing minted Kamis
- [Portal](portal.md) — Staking/unstaking Kami NFTs
- [Echo](echo.md) — Force-emit Kami data after minting

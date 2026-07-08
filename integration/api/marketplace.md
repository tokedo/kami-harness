> **Doc Class:** Core Resource
> **Canonical Source:** Kamigotchi on-chain contracts on Yominet and the official repository (`Asphodel-OS/kamigotchi`).
> **Freshness Rule:** Verify mutable values against canonical sources before merge.

# KamiSwap — Kami Marketplace

KamiSwap is Kamigotchi's native on-chain Kami marketplace. Players can list Kamis for sale, make offers on specific Kamis or the collection, and purchase Kamis — all without leaving the game.

---

## Overview

KamiSwap has **6 player-facing systems** plus the **Newbie Vendor**:

| System ID | Contract | Wallet | Description |
|-----------|----------|--------|-------------|
| `system.kamimarket.list` | KamiMarketListSystem | Operator | List a Kami for sale (ETH) |
| `system.kamimarket.buy` | KamiMarketBuySystem | Owner (payable) | Buy listed Kami(s) with ETH |
| `system.kamimarket.offer` | KamiMarketOfferSystem | Operator | Make a specific or collection offer (WETH) |
| `system.kamimarket.acceptoffer` | KamiMarketAcceptOfferSystem | Operator | Accept an offer |
| `system.kamimarket.cancel` | KamiMarketCancelSystem | Operator | Cancel a listing or offer |
| `system.newbievendor.buy` | NewbieVendorBuySystem | Owner (payable) | Buy a Kami from the Newbie Vendor (one-time, new accounts) |

There is also an **admin-only** registry system (`system.kamimarket.registry`) for configuring fees, vault, and enable/disable — not covered here.

### Key Design Principles

- **No escrow for listings** — Kami stays in the seller's wallet (marked as `LISTED` state)
- **No escrow for offers** — WETH stays in the buyer's wallet (approval-based via KamiMarketVault)
- **Listings use ETH (native)** — buyer sends ETH directly
- **Offers use WETH (ERC-20)** — buyer pre-approves WETH to the KamiMarketVault
- **Ownership transfer stays staked** — Kami is reassigned via `IDOwnsKami` component (no unstake/restake needed)
- **TWAP oracle** — every sale feeds into a time-weighted average price used for pricing reference

### Important Addresses

| Contract | Address | Description |
|----------|---------|-------------|
| **WETH** | `0xE1Ff7038eAAAF027031688E1535a055B2Bac2546` | ERC-20 interface for Yominet ETH, used when a marketplace flow needs token approvals |
| **KamiMarketVault** | *(resolve from World config — see below)* | Holds WETH approvals for offer settlement |

> **Finding the KamiMarketVault address:** The vault address is stored in the `ValueComponent` (`component.value`), keyed by `keccak256("is.config", "KAMI_MARKET_VAULT")`. Read it using the component read pattern:
>
> ```javascript
> // Resolve KamiMarketVault address from ValueComponent
> const valueAddr = await getComponentAddress("component.value");
> const valueComp = new ethers.Contract(
>   valueAddr,
>   ["function getValue(uint256) view returns (uint256)"],
>   provider
> );
> const configEntityId = ethers.keccak256(
>   ethers.solidityPacked(["string", "string"], ["is.config", "KAMI_MARKET_VAULT"])
> );
> const vaultRaw = await valueComp.getValue(configEntityId);
> const vaultAddress = ethers.getAddress(ethers.toBeHex(vaultRaw, 20));
> ```
>
> See [Reading On-Chain Components](../system-ids.md#reading-on-chain-components) for the full `getComponentAddress()` helper.

### Fee Structure

The marketplace fee is configurable via the `KAMI_MARKET_FEE_RATE` config:

- Format: `[precision, numerator]` — fee = `price × numerator / 10^precision`
- Fee is deducted from the sale price; the seller receives `price - fee`
- Fee is sent to the treasury address (`KAMI_MARKET_FEE_RECIPIENT` config)

### Purchase Cooldown

After a Kami is purchased (via listing buy or offer acceptance), the Kami enters a **1-hour cooldown** (`KAMI_MARKET_PURCHASE_COOLDOWN` config, default 3600 seconds). During this cooldown, the Kami cannot be relisted or transferred.

### Soulbound Lock

Certain actions apply a **soulbound lock** to a Kami via `LibSoulbound`. The lock stores an expiry timestamp (`block.timestamp + duration`). While soulbound, the Kami cannot be listed, have offers accepted, or be unstaked. The lock is checked with `LibSoulbound.verify()`, which reverts with `"kami is soulbound"` if the current time is before the expiry.

---

## Entity ID Discovery

Order entity IDs (listings and offers) are **non-deterministic** — they are assigned by `world.getUniqueEntityId()` at creation time. You cannot derive them from known inputs.

To discover order IDs:
1. **From transaction return value** — `execute()` and `executeTyped()` on list/offer systems return `abi.encode(id)` — decode the return data
2. **From events** — listen for marketplace events (`KAMI_LISTING`, `KAMI_OFFER`, `KAMI_COLLECTION_OFFER` entity types)
3. **From the indexer** — query the off-chain indexer for active orders

```javascript
// Example: get listing tx hash, then resolve listing ID from indexer/events
const listTx = await listSystem.executeTyped(kamiIndex, price, expiry);
const receipt = await listTx.wait();
console.log("Listing tx hash:", receipt.hash);
// Resolve listing ID from confirmed events/indexer output keyed by receipt.hash.
// Avoid staticCall-generated IDs in production because IDs are non-deterministic.
```

### Extracting Order IDs from Transaction Receipts

For production bots, parse `Store_SetRecord` events from the transaction receipt to extract the order entity ID:

```javascript
import { extractEntityIds } from "./event-helpers.js"; // See Entity Discovery — Parsing Transaction Events

// After listing
const listTx = await listSystem.executeTyped(kamiIndex, price, expiry);
const listReceipt = await listTx.wait();
const listingId = extractEntityIds(listReceipt)[0];
console.log("Listing entity ID:", listingId);

// After making an offer
const offerTx = await offerSystem.executeTypedOffer(kamiIndex, price, expiry);
const offerReceipt = await offerTx.wait();
const offerId = extractEntityIds(offerReceipt)[0];
console.log("Offer entity ID:", offerId);
```

See [Parsing Transaction Events](../entity-ids.md#parsing-transaction-events) for the full `extractEntityIds()` helper and event parsing details.

---

## Listing Flow

### 1. Create a Listing

List a Kami for sale at a fixed ETH price. The Kami must be `RESTING` and not soulbound. The Kami stays in your wallet but its state changes to `LISTED`, preventing it from being used in gameplay.

**System:** `system.kamimarket.list`  
**Wallet:** Operator  

```solidity
// Solidity ABI
function executeTyped(uint32 kamiIndex, uint256 price, uint256 expiry) returns (bytes)
// kamiIndex — the Kami's token index
// price    — listing price in wei (ETH), must be > 0
// expiry   — expiration timestamp (unix seconds), 0 = no expiration
// returns  — abi.encode(listingEntityId)
```

```javascript
const LIST_ABI = [
  "function executeTyped(uint32 kamiIndex, uint256 price, uint256 expiry) returns (bytes)",
];
const listSystem = await getSystem("system.kamimarket.list", LIST_ABI, operatorSigner);

const kamiIndex = 42;
const price = ethers.parseEther("0.1"); // 0.1 ETH
const expiry = 0; // never expires

const tx = await listSystem.executeTyped(kamiIndex, price, expiry);
const receipt = await tx.wait();
console.log("Kami listed!");
```

### 2. Buy a Listing

Buy one or more listed Kamis with ETH. This is an all-or-nothing batch operation — if any listing in the batch fails, the entire transaction reverts.

**System:** `system.kamimarket.buy`  
**Wallet:** Owner (payable)

```solidity
// Solidity ABI
function executeTyped(uint256[] memory listingIDs) payable returns (bytes)
// listingIDs — array of listing entity IDs to buy
// msg.value  — must be >= total price of all listings
// Excess ETH is refunded automatically
```

```javascript
const BUY_ABI = [
  "function executeTyped(uint256[] memory listingIDs) payable returns (bytes)",
];
const buySystem = await getSystem("system.kamimarket.buy", BUY_ABI, ownerSigner);

const listingIDs = [listingId1, listingId2]; // buy multiple at once
const totalPrice = ethers.parseEther("0.2"); // sum of listing prices

const tx = await buySystem.executeTyped(listingIDs, { value: totalPrice });
await tx.wait();
console.log("Kamis purchased!");
```

> **How to find listing IDs:** Listing IDs are non-deterministic and cannot be derived. To discover active listings, either: (1) parse `Store_SetRecord` events from listing transactions (see [Parsing Transaction Events](../entity-ids.md#parsing-transaction-events)), or (2) query the [Kamiden Indexer](indexer.md) via `GetKamiMarketListings({ Size: 500 })` — this is the recommended approach for bots. There is no on-chain function to enumerate all active listings.

**What happens on buy:**
1. Verifies all listings are active, not expired, and buyer doesn't own them
2. Calculates total price and verifies `msg.value >= totalPrice`
3. For each listing: deducts fee, sends remainder to seller, reassigns Kami ownership
4. Feeds each sale price into the TWAP oracle
5. Refunds any excess ETH to the buyer
6. Kami enters 1-hour purchase cooldown

### 3. Cancel a Listing

Cancel your active listing to return the Kami to `RESTING` state.

**System:** `system.kamimarket.cancel`  
**Wallet:** Operator

```javascript
const CANCEL_ABI = [
  "function executeTyped(uint256 orderID) returns (bytes)",
];
const cancelSystem = await getSystem("system.kamimarket.cancel", CANCEL_ABI, operatorSigner);

const tx = await cancelSystem.executeTyped(listingEntityId);
await tx.wait();
console.log("Listing cancelled, Kami restored to RESTING");
```

---

## Offer Flow

### WETH Setup

Offers use **WETH** (not native ETH). Before making offers, the buyer must approve WETH spending to the **KamiMarketVault** contract.

> **Getting WETH:** If you only have native ETH, wrap it first:
> ```javascript
> const weth = new ethers.Contract(WETH_ADDRESS, ["function deposit() payable"], ownerSigner);
> await (await weth.deposit({ value: ethers.parseEther("0.1") })).wait();
> ```
> See [Chain Configuration — WETH](../chain.md#weth-wrapped-eth) for details.

```javascript
const WETH_ADDRESS = "0xE1Ff7038eAAAF027031688E1535a055B2Bac2546";
const WETH_ABI = [
  "function approve(address spender, uint256 amount) returns (bool)",
  "function allowance(address owner, address spender) view returns (uint256)",
];
const weth = new ethers.Contract(WETH_ADDRESS, WETH_ABI, ownerSigner);

// Approve only your intended max spend (safer than MaxUint256)
// vaultAddress is from KAMI_MARKET_VAULT config
const maxOfferSpend = ethers.parseEther("0.25"); // adjust to your strategy
const approveTx = await weth.approve(vaultAddress, maxOfferSpend);
await approveTx.wait();
console.log("WETH approved:", ethers.formatEther(maxOfferSpend), "WETH");
```

> **Note:** On Yominet, bridge ETH first for gas and native-ETH listing buys. When you need approval-based flows such as offers, wrap that ETH through the local WETH contract at `0xE1Ff...2546`. See [Chain Configuration](../chain.md) for bridging and wrapping details. Prefer exact/limited approvals and top up as needed.

> **Wallet note:** Offers are *created* by the **Operator** wallet, but when an offer is accepted, WETH is pulled from the **Owner** wallet via the vault. Approve WETH from your Owner wallet (as shown above), then create offers from your Operator wallet.

### 1. Make a Specific Offer

Offer to buy a specific Kami at your chosen WETH price.

**System:** `system.kamimarket.offer`  
**Wallet:** Operator

```solidity
// Solidity ABI — generic entry point
function execute(bytes memory arguments) returns (bytes)
// arguments = abi.encode(bool isCollection, uint32 kamiIndex, uint256 price, uint32 quantity, uint256 expiry)

// Typed helpers:
function executeTypedOffer(uint32 kamiIndex, uint256 price, uint256 expiry) returns (bytes)
function executeTypedCollection(uint256 price, uint32 quantity, uint256 expiry) returns (bytes)
```

```javascript
const OFFER_ABI = [
  "function executeTypedOffer(uint32 kamiIndex, uint256 price, uint256 expiry) returns (bytes)",
  "function executeTypedCollection(uint256 price, uint32 quantity, uint256 expiry) returns (bytes)",
  "function execute(bytes) returns (bytes)",
];
const offerSystem = await getSystem("system.kamimarket.offer", OFFER_ABI, operatorSigner);

// Specific offer: target Kami index 42 at 0.08 WETH, no expiry
const tx = await offerSystem.executeTypedOffer(
  42,                             // kamiIndex
  ethers.parseEther("0.08"),      // price in WETH
  0                               // expiry (0 = never)
);
await tx.wait();
console.log("Specific offer created!");
```

### 2. Make a Collection Offer

Offer to buy **any** Kami at your chosen WETH price, with a quantity limit.

```javascript
// Collection offer: buy up to 5 Kamis at 0.05 WETH each, expires in 7 days
const expiry = Math.floor(Date.now() / 1000) + 7 * 24 * 3600;
const tx = await offerSystem.executeTypedCollection(
  ethers.parseEther("0.05"),      // price per Kami in WETH
  5,                               // quantity
  expiry
);
await tx.wait();
console.log("Collection offer created for 5 Kamis!");
```

### 3. Accept an Offer

Accept an incoming offer (specific or collection) and sell your Kami. WETH is pulled from the buyer via the vault.

**System:** `system.kamimarket.acceptoffer`  
**Wallet:** Operator

```solidity
// Single accept
function executeTyped(uint256 offerID, uint32 kamiIndex) returns (bytes)

// Batch accept (collection offers only — sell multiple Kamis to one offer)
function executeTyped(uint256 offerID, uint32[] memory kamiIndices) returns (bytes)

// Generic entry point (supports both single and batch)
function execute(bytes memory arguments) returns (bytes)
// arguments = abi.encode(bool isBatch, uint256 offerID, uint32 kamiIndex, uint32[] kamiIndices)
```

```javascript
const ACCEPT_ABI = [
  "function executeTyped(uint256 offerID, uint32 kamiIndex) returns (bytes)",
  "function executeTyped(uint256 offerID, uint32[] kamiIndices) returns (bytes)",
  "function execute(bytes) returns (bytes)",
];
const acceptSystem = await getSystem("system.kamimarket.acceptoffer", ACCEPT_ABI, operatorSigner);

// Accept a specific offer — sell Kami #42
const tx = await acceptSystem.executeTyped(offerEntityId, 42);
await tx.wait();
console.log("Offer accepted, Kami sold!");
```

**Batch accept (collection offers):**

```javascript
// Accept a collection offer — sell Kamis #10, #15, #22 in one tx
const kamiIndices = [10, 15, 22];
const batchArgs = ethers.AbiCoder.defaultAbiCoder().encode(
  ["bool", "uint256", "uint32", "uint32[]"],
  [true, offerEntityId, 0, kamiIndices]
);
const tx = await acceptSystem.execute(batchArgs);
await tx.wait();
console.log("Batch accepted — 3 Kamis sold!");
```

> **How to find offer IDs:** Offer IDs are non-deterministic. To discover offers on your Kamis, either: (1) parse `Store_SetRecord` events from offer transactions, or (2) query an off-chain indexer. See [Parsing Transaction Events](../entity-ids.md#parsing-transaction-events).

**What happens on accept:**
1. Verifies offer is active, not expired, and seller doesn't own the offer
2. Verifies seller owns the Kami and it's `RESTING` or `LISTED` (not soulbound)
3. **If the Kami has an active listing, all listings for that Kami are automatically cancelled** when the offer is accepted
4. For collection offers: decrements remaining quantity
5. WETH is pulled from buyer → fee to treasury, remainder to seller
6. Kami ownership reassigned via `IDOwnsKami`
7. Sale price fed into TWAP oracle

### 4. Cancel an Offer

Cancel your active offer. No WETH is moved (approval-based, so nothing was escrowed).

```javascript
const tx = await cancelSystem.executeTyped(offerEntityId);
await tx.wait();
console.log("Offer cancelled");
```

---

## Non-Standard Entry Points

The offer system uses **custom function names** instead of the standard `executeTyped()`:

| System | Entry Points | Signatures |
|--------|-------------|-----------|
| `system.kamimarket.offer` | `executeTypedOffer` / `executeTypedCollection` | `executeTypedOffer(uint32 kamiIndex, uint256 price, uint256 expiry)` / `executeTypedCollection(uint256 price, uint32 quantity, uint256 expiry)` |
| `system.kamimarket.acceptoffer` | `executeTyped` (overloaded) | `executeTyped(uint256 offerID, uint32 kamiIndex)` / `executeTyped(uint256 offerID, uint32[] kamiIndices)` |

All other marketplace systems use the standard `executeTyped(...)` pattern.

---

## Complete Example: List → Buy Flow

```javascript
import { ethers } from "ethers";

const RPC_URL = "https://jsonrpc-yominet-1.anvil.asia-southeast.initia.xyz";
const WORLD_ADDRESS = "0x2729174c265dbBd8416C6449E0E813E88f43D0E7";

const provider = new ethers.JsonRpcProvider(RPC_URL, {
  chainId: 428962654539583,
  name: "Yominet",
});

function mustEnv(name) {
  const value = process.env[name];
  if (!value || !value.startsWith("0x")) {
    throw new Error(`Missing ${name}. Set it in your shell before running.`);
  }
  return value;
}

// Helper to resolve system contracts
const world = new ethers.Contract(
  WORLD_ADDRESS,
  ["function systems() view returns (address)"],
  provider
);
const SYSTEMS_COMPONENT_ABI = [
  "function getEntitiesWithValue(uint256) view returns (uint256[])",
];
async function sys(id, abi, signer) {
  const hash = ethers.keccak256(ethers.toUtf8Bytes(id));

  // World.systems() returns the SystemsComponent (IUint256Component),
  // which maps systemAddress -> systemId. We reverse-lookup by value.
  const systemsComponentAddr = await world.systems();
  const systemsComponent = new ethers.Contract(
    systemsComponentAddr,
    SYSTEMS_COMPONENT_ABI,
    provider
  );
  const entities = await systemsComponent.getEntitiesWithValue(hash);
  if (entities.length === 0) throw new Error(`System not found: ${id}`);
  const addr = ethers.getAddress(ethers.toBeHex(entities[0], 20));

  return new ethers.Contract(addr, abi, signer);
}

async function main() {
  const price = ethers.parseEther("0.1");
  const mode = process.env.MARKET_MODE ?? "list";

  if (mode === "list") {
    const sellerOperator = new ethers.Wallet(mustEnv("SELLER_OPERATOR_KEY"), provider);

    // --- Seller lists Kami #42 for 0.1 ETH ---
    const listSys = await sys(
      "system.kamimarket.list",
      ["function executeTyped(uint32, uint256, uint256) returns (bytes)"],
      sellerOperator
    );
    const listTx = await listSys.executeTyped(42, price, 0);
    const listReceipt = await listTx.wait();

    // Extract listing ID from Store_SetRecord events in the receipt
    // See "Extracting Order IDs from Transaction Receipts" above
    const { extractEntityIds } = await import("./event-helpers.js");
    const ids = extractEntityIds(listReceipt);
    if (ids.length > 0) {
      console.log("✅ Kami #42 listed. Listing ID:", ids[0].toString());
      console.log("Rerun with: MARKET_MODE=buy LISTING_ID=" + ids[0].toString());
    } else {
      console.log("✅ Kami #42 listed. Tx:", listReceipt.hash);
      console.log("Could not extract listing ID from events — resolve via indexer, then rerun with:");
      console.log("MARKET_MODE=buy LISTING_ID=<value>");
    }
    return;
  }

  if (mode !== "buy") {
    throw new Error("MARKET_MODE must be 'list' or 'buy'");
  }

  if (!process.env.LISTING_ID) {
    throw new Error("Missing LISTING_ID for MARKET_MODE=buy");
  }
  const buyerOwner = new ethers.Wallet(mustEnv("BUYER_OWNER_KEY"), provider);
  const listingId = BigInt(process.env.LISTING_ID);

  // --- Buyer buys the listing ---
  const buySys = await sys(
    "system.kamimarket.buy",
    ["function executeTyped(uint256[]) payable returns (bytes)"],
    buyerOwner
  );
  const buyTx = await buySys.executeTyped([listingId], {
    value: price,
  });
  await buyTx.wait();
  console.log("✅ Kami #42 purchased!");
}

main().catch(console.error);
```

> **Run modes:** use `MARKET_MODE=list` to create a listing and capture its tx hash, then `MARKET_MODE=buy LISTING_ID=<id>` to purchase.  
> **Why `LISTING_ID` is externalized:** listing IDs come from `world.getUniqueEntityId()` and are non-deterministic. `staticCall` can drift from mined state under concurrency.

---

## ETH vs WETH Summary

| Operation | Currency | Method |
|-----------|----------|--------|
| Buy a listing | **ETH** (native) | `msg.value` — buyer sends ETH with the transaction |
| Make an offer | **WETH** (ERC-20) | Approval-based — buyer approves WETH to the vault beforehand |
| Accept an offer | **WETH** (ERC-20) | Vault pulls WETH from buyer and distributes to seller + treasury |

> **Why the difference?** Listings are instant purchases (buyer initiates and pays in one tx), so native ETH works. Offers require the seller to accept later, so WETH's ERC-20 approval mechanism enables trustless settlement without escrow.

---

## NPC Merchant Shops

NPC merchant item shops are **separate from KamiSwap** and handle buying/selling fungible items (potions, materials, etc.) from in-game NPC merchants using in-game currency (e.g., $MUSU) — not ETH/WETH.

| System ID | Description |
|-----------|-------------|
| `system.listing.buy` | Buy items from an NPC merchant |
| `system.listing.sell` | Sell items to an NPC merchant |

```solidity
// Both systems share the same parameter signature
function executeTyped(uint32 merchantIndex, uint32[] itemIndices, uint32[] amts) returns (bytes)
// merchantIndex — the NPC merchant's entity index
// itemIndices   — which items to buy/sell (indices into the merchant's inventory)
// amts          — quantities for each item
```

**Key details:**

- **Proximity required** — the player must be in the same room as the NPC merchant
- **Pricing models** — merchants support **FIXED** pricing and **GDA** (Gradual Dutch Auction) dynamic pricing, where prices adjust based on supply/demand over time
- **Conditional requirements** — some items may have purchase conditions enforced via `LibConditional` (e.g., minimum level, quest completion)
- **Currency** — transactions use in-game item currency (e.g., $MUSU), not ETH or WETH

These systems are distinct from the KamiSwap P2P marketplace documented above.

---

## Newbie Vendor

The Newbie Vendor is an alternative Kami acquisition path for new players. It offers discounted Kamis at TWAP-derived prices, available one time per account within 24 hours of registration.

**System:** `system.newbievendor.buy`
**Wallet:** Owner (payable)

| Property | Value |
|----------|-------|
| **System ID** | `system.newbievendor.buy` |
| **Wallet** | Owner (payable) |
| **One-time** | Yes — each account can buy exactly once |
| **Time limit** | Must purchase within 24 hours of account registration |
| **Pricing** | `max(TWAP price, minimum price)` — minimum defaults to 0.005 ETH |
| **Soulbound** | Purchased Kami is soulbound for 3 days (cannot list, unstake, or accept offers) |

### Parameters

```solidity
function executeTyped(uint32 kamiIndex) payable returns (bytes)
// kamiIndex — index of the Kami on display in the vendor pool
// msg.value — must be >= calcPrice()

function calcPrice() view returns (uint256)
// Returns current vendor price: max(TWAP oracle price, minimum price)
```

### How It Works

1. Admin populates the vendor with a pool of Kami indices
2. The vendor displays 3 Kamis at a time, rotating every `NEWBIE_VENDOR_CYCLE` seconds
3. Player calls `calcPrice()` to check the current price
4. Player calls `executeTyped(kamiIndex)` with sufficient ETH — excess is refunded
5. The purchased Kami is soulbound for 3 days
6. The `NEWBIE_VENDOR_PURCHASED` flag prevents repeat purchases

### Code Example

```javascript
const VENDOR_ABI = [
  "function executeTyped(uint32 kamiIndex) payable returns (bytes)",
  "function calcPrice() view returns (uint256)",
];
const vendor = await getSystem("system.newbievendor.buy", VENDOR_ABI, ownerSigner);

// Check current price
const price = await vendor.calcPrice();
console.log("Vendor price:", ethers.formatEther(price), "ETH");

// Buy Kami index 7 from the vendor
const tx = await vendor.executeTyped(7, { value: price });
await tx.wait();
console.log("Kami purchased from Newbie Vendor!");
```

### Common Errors

| Error | Cause |
|-------|-------|
| `NewbieVendor: disabled` | Vendor is currently disabled by admin |
| `NewbieVendor: already purchased` | Account already used the one-time purchase |
| `NewbieVendor: account too old` | Account was registered more than 24 hours ago |
| `NewbieVendor: insufficient ETH` | `msg.value` is less than `calcPrice()` |
| `NewbieVendor: pool empty` | No Kamis available in the vendor pool |
| `NewbieVendor: kami not on display` | Selected Kami is in the pool but not in the current display window |

---

## Related Pages

- [Entity Discovery](../entity-ids.md) — How to find order entity IDs
- [Portal (ERC721 / ERC20)](portal.md) — Staking and unstaking Kami NFTs
- [Gacha / Minting](minting.md) — Minting new Kamis via the gacha system
- [Trading](trading.md) — Player-to-player item trades
- [Game Data Reference](../game-data.md) — WETH address, fee config, cooldown values
- [System IDs & ABIs](../system-ids.md) — Complete system reference

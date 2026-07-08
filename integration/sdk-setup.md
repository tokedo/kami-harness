> **Doc Class:** Core Resource
> **Canonical Source:** Kamigotchi on-chain contracts on Yominet and the official repository (`Asphodel-OS/kamigotchi`).
> **Freshness Rule:** Verify mutable values against canonical sources before merge.

# Player API — Overview & Setup

The Kamigotchi Player API is a set of on-chain **System contracts** that handle all game actions. This page covers how to set up your environment and call any system.

If you are starting from zero, run through [Agent Bootstrap](bootstrap.md) first, then come back here.

---

## Prerequisites

- **Node.js** v18+ and **ethers.js v6**
- **ESM mode** enabled (`"type": "module"` in `package.json`)
- **Environment variables** set for `OWNER_PRIVATE_KEY` and `OPERATOR_PRIVATE_KEY`
- Two EOAs: Owner (with $ETH) and a **distinct** Operator (with small $ETH for gas). The higher-level bootstrap can derive the operator from the owner key; this page assumes both keys are already available. Privy is only for the web UI (see [Chain Configuration](chain.md))
- The World contract address

```bash
npm init -y
npm install ethers
npm pkg set type=module
```

---

## Quick Start

```javascript
import { ethers } from "ethers";

// --- Configuration ---
const RPC_URL = "https://jsonrpc-yominet-1.anvil.asia-southeast.initia.xyz";
const WORLD_ADDRESS = "0x2729174c265dbBd8416C6449E0E813E88f43D0E7";

// --- Provider & Signer ---
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

// Operator wallet for regular gameplay
const operatorSigner = new ethers.Wallet(mustEnv("OPERATOR_PRIVATE_KEY"), provider);

// Owner wallet for privileged actions (register, NFTs, ONYX)
const ownerSigner = new ethers.Wallet(mustEnv("OWNER_PRIVATE_KEY"), provider);

if (ownerSigner.address === operatorSigner.address) {
  throw new Error("Operator must be a distinct address. Do not reuse the owner key.");
}

// --- World Contract ---
const WORLD_ABI = [
  "function systems() view returns (address)",
  "function components() view returns (address)",
];
const SYSTEMS_COMPONENT_ABI = [
  "function getEntitiesWithValue(uint256) view returns (uint256[])",
];
const world = new ethers.Contract(WORLD_ADDRESS, WORLD_ABI, provider);

// --- Helper: Resolve System Address ---
async function getSystemAddress(systemId) {
  const hash = ethers.keccak256(ethers.toUtf8Bytes(systemId));

  // World.systems() returns the SystemsComponent (IUint256Component),
  // which maps systemAddress -> systemId. We reverse-lookup by value.
  const systemsComponentAddr = await world.systems();
  const systemsComponent = new ethers.Contract(
    systemsComponentAddr,
    SYSTEMS_COMPONENT_ABI,
    provider
  );
  const entities = await systemsComponent.getEntitiesWithValue(hash);
  if (entities.length === 0) throw new Error(`System not found: ${systemId}`);
  return ethers.getAddress(ethers.toBeHex(entities[0], 20));
}

// --- Helper: Get System Contract ---
async function getSystem(systemId, abi, signer) {
  const address = await getSystemAddress(systemId);
  return new ethers.Contract(address, abi, signer);
}

// --- Yominet Gas Settings ---
// Yominet uses flat gas pricing. Hardcode these overrides instead of relying on gas estimation.
const TX_OVERRIDES = {
  maxFeePerGas: 2500000n,       // 0.0025 gwei
  maxPriorityFeePerGas: 0n,
};

// Usage: const tx = await system.executeTyped(args, { ...TX_OVERRIDES });
```

> **Important:** In ethers v6, pass `chainId` as a number (not `BigInt`) in the provider network object.

---

## Wallet Model

Kamigotchi uses two wallets per player:

| Wallet | Purpose | Used For |
|--------|---------|----------|
| **Owner** | Primary wallet, holds NFTs | `register`, `set.name`, `set.operator`, `onyx.rename` (currently disabled)/`onyx.respec` (currently disabled), ERC721 stake/unstake, ERC20 portal, trade, item transfer, `kamimarket.buy`, `auction.buy`, gacha tickets, gacha mint/reroll |
| **Operator** | Delegated session wallet | move, chat, harvest, quest, craft, `set.pfp`, `set.bio`, `onyx.revive`, `kamimarket.list`, `kamimarket.offer`, `kamimarket.acceptoffer`, `kamimarket.cancel`, `kami.send`, etc. |

> **Note:** The operator wallet is set during `register()` and can be changed with `set.operator()`. In the official client, Privy manages the operator wallet as an embedded wallet.

### New Player Path

After registering, new players need to acquire their first Kami before they can participate in gameplay. One path to a first Kami is KamiSwap; gacha minting is another — buy tickets with $MUSU via the auction system. See the [Integration Guide](guide.md#step-5-get-your-first-kami) for the full walkthrough.

### Determining Which Wallet to Use

Each function in this documentation includes a **Wallet** badge:

- 🔐 **Owner** — Must be called from the owner wallet
- 🎮 **Operator** — Can be called from the operator wallet

This convention is used consistently across all Player API documentation pages.

---

## Payment Methods

Kamigotchi uses two distinct payment mechanisms depending on the system:

### Native ETH (`msg.value`)

Some systems accept payment as native ETH sent directly with the transaction (i.e., via `msg.value`). These are `payable` functions:

| System | Usage |
|--------|-------|
| `system.kamimarket.buy` | Buy a Kami from the KamiSwap marketplace |
| `system.kamimarket.buy` | Purchase Kami listing(s) from the marketplace |

```javascript
// Example: payable call with msg.value
const tx = await vendorSystem.executeTyped(kamiIndex, { value: price });
```

### In-Game ETH Balance (Item 103)

Certain systems use an **in-game ETH balance** (tracked as item index `103`) rather than `msg.value`. This balance is deposited into the game via `system.erc20.portal`:

| System | Usage |
|--------|-------|
| `system.auction.buy` | Buy gacha tickets via Dutch auction — debits $MUSU from inventory |
| `system.kamimarket.offer` | WETH offer amount — requires WETH approval to KamiMarketVault |

> **Key distinction:** If a system is `payable`, you send native ETH with `msg.value`. If it deducts from inventory (e.g., $MUSU for gacha tickets), you need the item in your in-game inventory. Check each system's documentation for which payment method it uses.

---

## Calling Convention

All systems follow the MUD pattern:

### Option A: `executeTyped()` (Recommended)

Each system exposes a typed function with named parameters:

```javascript
const LEVEL_ABI = ["function executeTyped(uint256 kamiID) returns (bytes)"];
const levelSystem = await getSystem("system.kami.level", LEVEL_ABI, operatorSigner);

const tx = await levelSystem.executeTyped(kamiEntityId);
await tx.wait();
```

### Option B: `execute(bytes)` (Generic)

Encode arguments manually:

```javascript
const SYSTEM_ABI = ["function execute(bytes) returns (bytes)"];
const levelSystem = await getSystem("system.kami.level", SYSTEM_ABI, operatorSigner);

const calldata = ethers.AbiCoder.defaultAbiCoder().encode(
  ["uint256"],
  [kamiEntityId]
);
const tx = await levelSystem.execute(calldata);
await tx.wait();
```

---

## Gas Limits

Most calls work with default gas estimation, but some systems require **hardcoded gas limits**:

| System | Gas Limit | Reason |
|--------|-----------|--------|
| `system.account.move` | 1,200,000 | Upper bound for rooms with gates |
| `system.harvest.liquidate` | 7,500,000 | Complex liquidation logic |
| `system.kami.gacha.mint` | 4,000,000 + 3,000,000/kami | Scales with mint amount |

```javascript
// Example: setting gas limit explicitly
const tx = await moveSystem.executeTyped(roomIndex, {
  gasLimit: 1_200_000,
});
```

For systems with "Default" gas, ethers.js gas estimation works correctly on Yominet. No manual `gasLimit` override is needed.

---

## Error Handling

System calls revert with Solidity error messages. Wrap calls in try/catch:

```javascript
try {
  const tx = await system.executeTyped(args);
  const receipt = await tx.wait();
  console.log("Success:", receipt.hash);
} catch (error) {
  if (error.reason) {
    console.error("Revert reason:", error.reason);
  } else {
    console.error("Transaction failed:", error.message);
  }
}
```

Common revert reasons:

| Error | Cause |
|-------|-------|
| `"Account: no account detected"` | Account not yet registered — call `system.account.register` first |
| `"Account: Operator not found"` | Operator wallet not set or calling from wrong wallet |
| `"PetLevel: need more experience"` | Kami doesn't have enough XP to level up |
| `"PetName: name too short"` / `"PetName: name too long"` | Name must be 1–16 bytes |

---

## Caching System Addresses

System addresses rarely change. Cache them to avoid repeated RPC calls:

```javascript
const systemCache = new Map();

async function getCachedSystem(systemId, abi, signer) {
  if (!systemCache.has(systemId)) {
    const address = await getSystemAddress(systemId);
    systemCache.set(systemId, address);
  }
  return new ethers.Contract(systemCache.get(systemId), abi, signer);
}
```

> **Note:** If a system is upgraded by the Asphodel team, you'll need to clear your cache. This is rare but possible in the MUD framework.

---

## Reading State

Use the **GetterSystem** for read-only queries (no gas cost):

```javascript
// Full ABI with struct fields — required for ethers.js to decode named return values.
// See system-ids.md -> Getter System for the complete reference.
const GETTER_ABI = [
  "function getKami(uint256 kamiId) view returns (tuple(uint256 id, uint32 index, string name, string mediaURI, tuple(tuple(int32 base, int32 shift, int32 boost, int32 sync) health, tuple(int32 base, int32 shift, int32 boost, int32 sync) power, tuple(int32 base, int32 shift, int32 boost, int32 sync) harmony, tuple(int32 base, int32 shift, int32 boost, int32 sync) violence) stats, tuple(uint32 face, uint32 hand, uint32 body, uint32 background, uint32 color) traits, string[] affinities, uint256 account, uint256 level, uint256 xp, uint32 room, string state))",
  "function getAccount(uint256 accountId) view returns (tuple(uint32 index, string name, int32 currStamina, uint32 room))",
];

const getterAddr = await getSystemAddress("system.getter"); // ID = keccak256("system.getter")
const getter = new ethers.Contract(getterAddr, GETTER_ABI, provider);

// Read without spending gas
const kamiData = await getter.getKami(kamiId);
const accountData = await getter.getAccount(accountId);
```

### Check Balances

```javascript
// Check native ETH balance
const balance = await provider.getBalance(ownerSigner.address);
console.log("ETH balance:", ethers.formatEther(balance));

// Check WETH balance
const WETH = new ethers.Contract(
  "0xE1Ff7038eAAAF027031688E1535a055B2Bac2546",
  ["function balanceOf(address) view returns (uint256)"],
  provider
);
const wethBal = await WETH.balanceOf(ownerSigner.address);
console.log("WETH balance:", ethers.formatEther(wethBal));
```

### Reading Game State — Practical Tips

- **Check if a Kami is alive:** `kamiData.state === "RESTING"` means alive and idle. Other states: `"HARVESTING"` (busy but alive), `"DEAD"` (needs revive).
- **Check stamina:** `accountData.currStamina` (int32) — decreases per room move. Regenerates over time on-chain.
- **Check room:** `accountData.room` for the account's current room, `kamiData.room` for a Kami's room (both uint32 room index).
- **Inventory queries:** The getter system does not include inventory data. Use the `ValueComponent` directly — see the [Inventory Queries](#inventory-queries) section below and [Entity Discovery](entity-ids.md) for deriving inventory entity IDs.

---

## Inventory Queries

The getter system does not return inventory data. To check item balances, resolve the `component.value` component and read inventory entity IDs directly.

### Setup

```javascript
import { ethers } from "ethers";
import { provider, ownerSigner, getSystemAddress } from "./kamigotchi.js";

// Resolve a Component address via the Components registry (NOT the Systems registry).
// World.components() returns the ComponentsRegistryComponent, which maps componentAddress -> componentId.
async function getComponentAddress(componentName) {
  const hash = ethers.keccak256(ethers.toUtf8Bytes(componentName));
  const componentsRegistryAddr = await (
    new ethers.Contract(
      "0x2729174c265dbBd8416C6449E0E813E88f43D0E7",
      ["function components() view returns (address)"],
      provider
    )
  ).components();
  const componentsRegistry = new ethers.Contract(
    componentsRegistryAddr,
    ["function getEntitiesWithValue(uint256) view returns (uint256[])"],
    provider
  );
  const entities = await componentsRegistry.getEntitiesWithValue(hash);
  if (entities.length === 0) throw new Error(`Component not found: ${componentName}`);
  return ethers.getAddress(ethers.toBeHex(entities[0], 20));
}

const VALUE_ABI = ["function getValue(uint256 entity) view returns (uint256)"];
const valueAddr = await getComponentAddress("component.value");
const valueComponent = new ethers.Contract(valueAddr, VALUE_ABI, provider);
```

### Reading a Specific Item Balance

Inventory entity IDs are derived as `keccak256(abi.encodePacked("inventory.instance", accountId, itemIndex))`:

```javascript
const accountId = BigInt(ownerSigner.address); // account entity = address as uint256

function getInventoryEntityId(accountId, itemIndex) {
  return BigInt(
    ethers.keccak256(
      ethers.solidityPacked(
        ["string", "uint256", "uint32"],
        ["inventory.instance", accountId, itemIndex]
      )
    )
  );
}

// --- Check common balances ---

// MUSU (item index 1) — primary currency earned from harvesting
const musuId = getInventoryEntityId(accountId, 1);
const musuBalance = await valueComponent.getValue(musuId);
console.log("MUSU:", musuBalance.toString());

// VIPP (item index 2) — VIP Points, earned from specific harvest nodes
const vippId = getInventoryEntityId(accountId, 2);
const vippBalance = await valueComponent.getValue(vippId);
console.log("VIPP:", vippBalance.toString());

// Onyx Shards (item index 100) — in-game form of $ONYX (1 ONYX = 100 shards)
const onyxId = getInventoryEntityId(accountId, 100);
const onyxBalance = await valueComponent.getValue(onyxId);
console.log("Onyx Shards:", onyxBalance.toString());

// Gacha Tickets (item index 10)
const ticketId = getInventoryEntityId(accountId, 10);
const ticketBalance = await valueComponent.getValue(ticketId);
console.log("Gacha Tickets:", ticketBalance.toString());

// Any item — just change the index (see game-data.md for the full list)
const woodenStickId = getInventoryEntityId(accountId, 1001);
const stickBalance = await valueComponent.getValue(woodenStickId);
console.log("Wooden Sticks:", stickBalance.toString());
```

> **Note:** `getValue()` returns `0` for entities that don't exist (i.e., items you've never held). This is safe to call for any item index. See [Game Data Reference](game-data.md) for the full item index table.

---

## Full Helper Module

Here's a reusable helper module for all examples in this documentation:

```javascript
// kamigotchi.js — Reusable helper module
import { ethers } from "ethers";

export const RPC_URL = "https://jsonrpc-yominet-1.anvil.asia-southeast.initia.xyz";
export const WORLD_ADDRESS = "0x2729174c265dbBd8416C6449E0E813E88f43D0E7";

export const provider = new ethers.JsonRpcProvider(RPC_URL, {
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

export const ownerSigner = new ethers.Wallet(mustEnv("OWNER_PRIVATE_KEY"), provider);
export const operatorSigner = new ethers.Wallet(mustEnv("OPERATOR_PRIVATE_KEY"), provider);

const WORLD_ABI = [
  "function systems() view returns (address)",
  "function components() view returns (address)",
];
const SYSTEMS_COMPONENT_ABI = [
  "function getEntitiesWithValue(uint256) view returns (uint256[])",
];
export const world = new ethers.Contract(WORLD_ADDRESS, WORLD_ABI, provider);

const systemCache = new Map();

export async function getSystemAddress(systemId) {
  if (!systemCache.has(systemId)) {
    const hash = ethers.keccak256(ethers.toUtf8Bytes(systemId));

    // World.systems() returns the SystemsComponent (IUint256Component),
    // which maps systemAddress -> systemId. We reverse-lookup by value.
    const systemsComponentAddr = await world.systems();
    const systemsComponent = new ethers.Contract(
      systemsComponentAddr,
      SYSTEMS_COMPONENT_ABI,
      provider
    );
    const entities = await systemsComponent.getEntitiesWithValue(hash);
    if (entities.length === 0) throw new Error(`System not found: ${systemId}`);
    const addr = ethers.getAddress(ethers.toBeHex(entities[0], 20));

    systemCache.set(systemId, addr);
  }
  return systemCache.get(systemId);
}

export async function getSystem(systemId, abi, signer) {
  const address = await getSystemAddress(systemId);
  return new ethers.Contract(address, abi, signer);
}

// --- Helper: Resolve Component Address ---
// Components resolve via world.components(), NOT world.systems().
// The Components registry maps componentAddress -> componentId.
const COMPONENTS_REGISTRY_ABI = [
  "function getEntitiesWithValue(uint256) view returns (uint256[])",
];
const componentCache = new Map();

export async function getComponentAddress(componentName) {
  if (!componentCache.has(componentName)) {
    const hash = ethers.keccak256(ethers.toUtf8Bytes(componentName));
    const componentsRegistryAddr = await world.components();
    const componentsRegistry = new ethers.Contract(
      componentsRegistryAddr,
      COMPONENTS_REGISTRY_ABI,
      provider
    );
    const entities = await componentsRegistry.getEntitiesWithValue(hash);
    if (entities.length === 0) throw new Error(`Component not found: ${componentName}`);
    const addr = ethers.getAddress(ethers.toBeHex(entities[0], 20));
    componentCache.set(componentName, addr);
  }
  return componentCache.get(componentName);
}
```

All code examples in this documentation import from this module:

```javascript
import {
  getSystem,
  getComponentAddress,
  provider,
  ownerSigner,
  operatorSigner,
} from "./kamigotchi.js";
```

Most API snippets assume these exports are already in scope.

---

## Quick Reference

A dense cheat sheet for common bot operations. All snippets assume the [helper module](#full-helper-module) is imported.

### Derive Entity IDs

```javascript
const accountId  = BigInt(ownerAddress);                                                          // account
const kamiId     = BigInt(ethers.keccak256(ethers.solidityPacked(["string","uint32"], ["kami.id", kamiIndex])));  // kami
const harvestId  = BigInt(ethers.keccak256(ethers.solidityPacked(["string","uint256"], ["harvest", kamiId])));    // harvest
const inventoryId = BigInt(ethers.keccak256(ethers.solidityPacked(["string","uint256","uint32"], ["inventory.instance", accountId, itemIndex]))); // inventory
```

See [Entity Discovery](entity-ids.md) for the full list.

### Read Game State

```javascript
const getter = new ethers.Contract(await getSystemAddress("system.getter"), GETTER_ABI, provider);
const kami    = await getter.getKami(kamiId);       // .stats.health, .room, .state, .level, .xp
const account = await getter.getAccount(accountId); // .currStamina, .room, .name
```

### Check If Kami Is Alive

```javascript
const kami = await getter.getKami(kamiId);
const alive = kami.state === "RESTING" || kami.state === "HARVESTING";
// "DEAD" → needs revive via system.kami.onyx.revive (costs 33 ONYX)
```

### Check Stamina

```javascript
const account = await getter.getAccount(accountId);
console.log("Stamina:", account.currStamina.toString());
// Each room move costs stamina (on-chain config ACCOUNT_STAMINA index 2)
```

### Check Inventory

```javascript
// Derive the inventory entity for a specific item, then read its ValueComponent
const invId = BigInt(ethers.keccak256(
  ethers.solidityPacked(["string","uint256","uint32"], ["inventory.instance", accountId, itemIndex])
));
const balance = await valueComponent.get(invId); // returns 0 if entity doesn't exist
```

### Common Bot Loop

```
loop:
  kami   = getter.getKami(kamiId)
  if kami.state == "DEAD"       → revive or swap Kami
  if kami.health < threshold    → use healing item (system.kami.use.item)
  if account.room != targetRoom → move (system.account.move, gasLimit: 1_200_000)
  if kami.state == "RESTING"    → start harvest (system.harvest.start, kamiId, nodeIndex, 0, 0)
  wait N minutes
  collect rewards               → system.harvest.collect(harvestId)
  reveal droptable items        → system.droptable.item.reveal(pendingDropIds)
  repeat
```

---

## API Pages

| Page | Systems Covered |
|------|----------------|
| [Echo](echo.md) | `system.echo.kamis`, `system.echo.room` |
| [Kami](kami.md) | Level, name, sacrifice, equip, items, skills, ONYX, send |
| [Account](account.md) | Register, move, settings, chat |
| [Harvesting](harvesting.md) | Start, stop, collect, liquidate |
| [Quests](quests.md) | Accept, complete, drop |
| [Trading](trading.md) | Create, execute, complete, cancel |
| [Social / Friends](social.md) | Request, accept, cancel, block |
| [Items & Crafting](items-and-crafting.md) | Burn, craft, use, transfer, droptable |
| [Merchant Listings](listings.md) | Buy, sell |
| [Skills & Relationships](skills-and-relationships.md) | Skill upgrade/reset, NPC relationships |
| [Goals & Scavenge](goals-and-scavenge.md) | Contribute, claim |
| [Gacha / Minting](minting.md) | Mint, reveal, reroll, tickets |
| [Portal](portal.md) | ERC721 stake/unstake, ERC20 deposit/withdraw |
| [Entity Discovery](entity-ids.md) | Entity ID derivation and lookup |
| [KamiSwap Marketplace](marketplace.md) | List, buy, offer, cancel |
| [Kamiden Indexer](indexer.md) | Off-chain gRPC: listings, bids, history, real-time stream |

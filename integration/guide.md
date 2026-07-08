> **Doc Class:** Agent Guidance
> **Canonical Source:** Derived from Core Resources and on-chain canonical sources.
> **Freshness Rule:** Do not become source-of-truth for canonical values; link back to Core Resources for addresses, IDs, and tables.

# Integration Guide

This guide walks third-party developers through the low-level contract integration flow after bootstrap. By the end, you'll be able to register accounts, manage Kamis, and interact with the full game API.

If you want the shortest first-run path for a new bot developer, start with [Agent Bootstrap](agent-bootstrap.md) and return here for the full flow.

---

## Prerequisites

| Requirement | Details |
|-------------|---------|
| **Runtime** | Node.js v18+ (v20+ recommended) |
| **Library** | ethers.js v6 |
| **Module Mode** | ESM (`"type": "module"` in `package.json`) |
| **Environment** | `OWNER_PRIVATE_KEY`, `OPERATOR_PRIVATE_KEY`, and `KAMI_ACCOUNT_NAME` |
| **Wallets** | Two EOAs: Owner (with $ETH on Yominet) and a **distinct** Operator (with small $ETH for gas). The high-level bootstrap can derive the operator from the owner key; this guide assumes both keys are already available. |
| **Network** | Yominet (Chain ID: `428962654539583`) |

> **Bootstrap vs low-level integration:** The single-owner-key bootstrap uses `OWNER_PRIVATE_KEY`, `BRIDGE_AMOUNT_ETH`, and `KAMI_ACCOUNT_NAME` as user inputs, then derives and funds a distinct operator wallet. The code in this guide starts *after* that derivation step and expects both keys to be exported.

---

## Funding Your Wallet

**There is no faucet on Yominet.** You must arrive with real ETH on Yominet before you can transact.

Use one of these bot-oriented paths:

1. **Base agent bootstrap route** — Use [Yominet Bridge Tooling](tools/yominet-bridge/README.md) if your agent starts from a single owner key funded on Base.
2. **External funding route** — If you are not using the bootstrap route, fund the owner wallet through an external route you control before running these scripts. For current network details, see [Chain Configuration](chain.md).

**Cost summary:**

| Action | Cost | Currency |
|--------|------|----------|
| Gas (thousands of txs) | ~0.001 ETH | Native ETH |
| KamiSwap (first Kami) | Variable (~0.01 ETH) | Native ETH (msg.value) |
| Gacha ticket (public) | $MUSU (GDA pricing) | In-game $MUSU (item 1, earned via harvesting) |
| Marketplace listing | Variable | Native ETH (msg.value) |
| Marketplace offer | Variable | WETH (approval-based) |

**Recommended starting budget:** 0.01 ETH bridged to Yominet.

> **Note:** If you are using the single-owner-key bootstrap, bridge ETH to the Owner first, then fund the derived Operator from that balance before gameplay transactions.

---

## Step 0: Create a Runnable Project

```bash
mkdir kamigotchi-agent
cd kamigotchi-agent
npm init -y
npm install ethers nice-grpc-web @bufbuild/protobuf tsx
npm pkg set type=module

# Linux/macOS
export OWNER_PRIVATE_KEY=0xYOUR_OWNER_PRIVATE_KEY
export OPERATOR_PRIVATE_KEY=0xYOUR_OPERATOR_PRIVATE_KEY
export KAMI_ACCOUNT_NAME=MyBot01
```

> **Windows PowerShell:** use `$env:OWNER_PRIVATE_KEY="0x..."`, `$env:OPERATOR_PRIVATE_KEY="0x..."`, and `$env:KAMI_ACCOUNT_NAME="MyBot01"`.

---

## Step 1: Connect to Yominet

```javascript
import { ethers } from "ethers";

// Network configuration
const RPC_URL = "https://jsonrpc-yominet-1.anvil.asia-southeast.initia.xyz";
const CHAIN = { chainId: 428962654539583, name: "Yominet" };

// Connect
const provider = new ethers.JsonRpcProvider(RPC_URL, CHAIN);

// Verify connection
const blockNumber = await provider.getBlockNumber();
console.log(`Connected to Yominet (block: ${blockNumber})`);
```

> **Important:** In ethers v6, use a numeric `chainId` in the provider network object.

---

## Step 2: Set Up Wallets

Kamigotchi uses a **dual-wallet model**. Contract interactions distinguish between an Owner wallet and a **distinct** Operator wallet. The higher-level bootstrap may derive the operator from the owner key, but by the time you reach the contract layer you must have both keys available and the operator must be a different address from the owner:

```javascript
function mustEnv(name) {
  const value = process.env[name];
  if (!value || !value.startsWith("0x")) {
    throw new Error(`Missing ${name}. Set it before running this script.`);
  }
  return value;
}

// Owner wallet — holds NFTs, registers account, does privileged operations
const ownerSigner = new ethers.Wallet(mustEnv("OWNER_PRIVATE_KEY"), provider);

// Operator wallet — handles routine gameplay transactions
const operatorSigner = new ethers.Wallet(mustEnv("OPERATOR_PRIVATE_KEY"), provider);

if (ownerSigner.address === operatorSigner.address) {
  throw new Error("Operator must be a distinct address. Do not reuse the owner key.");
}

console.log("Owner:", ownerSigner.address);
console.log("Operator:", operatorSigner.address);
```

> **Note:** In production, use secure key management. Never hardcode private keys.

---

## Step 3: Set Up World Contract Helper

```javascript
const WORLD_ADDRESS = "0x2729174c265dbBd8416C6449E0E813E88f43D0E7";
const WORLD_ABI = [
  "function systems() view returns (address)",
];
const SYSTEMS_COMPONENT_ABI = [
  "function getEntitiesWithValue(uint256) view returns (uint256[])",
];
const world = new ethers.Contract(WORLD_ADDRESS, WORLD_ABI, provider);

// Cache for system addresses
const systemCache = new Map();

async function getSystemAddress(systemId) {
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
    if (entities.length === 0) {
      throw new Error(`System not found in registry: ${systemId}`);
    }
    const addr = ethers.getAddress(ethers.toBeHex(entities[0], 20));
    systemCache.set(systemId, addr);
  }
  return systemCache.get(systemId);
}

async function getSystem(systemId, abi, signer) {
  const address = await getSystemAddress(systemId);
  return new ethers.Contract(address, abi, signer);
}
```

---

## Step 4: Register an Account

Registration is called from the **Owner wallet** and takes the **Operator address** as a parameter. Pass the address of your distinct operator wallet directly.

```javascript
const REGISTER_ABI = [
  "function executeTyped(address operatorAddress, string name) returns (bytes)",
];
const GETTER_ABI = [
  "function getAccount(uint256 accountId) view returns (tuple(uint32 index, string name, int32 currStamina, uint32 room))",
];

const registerSystem = await getSystem(
  "system.account.register",
  REGISTER_ABI,
  ownerSigner // Must use Owner wallet; this becomes the account owner
);
const getter = await getSystem("system.getter", GETTER_ABI, provider);

const accountName = process.env.KAMI_ACCOUNT_NAME ?? "MyBot01";
const nameBytes = ethers.toUtf8Bytes(accountName).length;
if (nameBytes < 1 || nameBytes > 15) {
  throw new Error(
    `Invalid KAMI_ACCOUNT_NAME "${accountName}" (${nameBytes} bytes). Use 1-15 bytes.`
  );
}

const ownerAccountId = BigInt(ownerSigner.address);
const operatorAccountId = BigInt(operatorSigner.address);

if (ownerSigner.address === operatorSigner.address) {
  throw new Error("Operator must be distinct from owner. Do not reuse the owner address.");
}

async function hasAccount(accountId) {
  try {
    const account = await getter.getAccount(accountId);
    return account.name !== "";
  } catch {
    return false;
  }
}

if (await hasAccount(ownerAccountId)) {
  console.log("Owner already has a registered account — skipping register().");
} else {
  if (await hasAccount(operatorAccountId)) {
    throw new Error(
      "Operator address is already in use by another account. Generate a new operator wallet."
    );
  }

  const ownerBalance = await provider.getBalance(ownerSigner.address);
  if (ownerBalance === 0n) {
    throw new Error(
      `Owner has 0 ETH on Yominet (${ownerSigner.address}). Bridge ETH first, then retry register().`
    );
  }

  let gasEstimate;
  try {
    gasEstimate = await registerSystem.executeTyped.estimateGas(
      operatorSigner.address,
      accountName
    );
  } catch (err) {
    const reason =
      err?.info?.error?.message || err?.shortMessage || err?.reason || err?.message || "";
    if (reason.includes("does not exist")) {
      throw new Error(
        `Owner address ${ownerSigner.address} is not initialized on Yominet yet. Bridge ETH first, then retry register().`
      );
    }
    throw err;
  }

  const gasPrice = (await provider.getFeeData()).gasPrice ?? 2_500_000n;
  const minGasCost = gasEstimate * gasPrice;
  if (ownerBalance < minGasCost) {
    throw new Error(
      `Owner needs at least ${ethers.formatEther(minGasCost)} ETH for register() gas, has ${ethers.formatEther(ownerBalance)} ETH`
    );
  }

  const tx = await registerSystem.executeTyped(
    operatorSigner.address,
    accountName
  );
  const receipt = await tx.wait();
  console.log("Account registered! Tx:", receipt.hash);
}
```

> **What happens:** `AccountRegisterSystem.executeTyped(operatorAddress, name)` creates a new account entity owned by `msg.sender` (your Owner wallet) and sets the provided address as the Operator. The Operator can then sign routine gameplay transactions on behalf of the account.
>
> **If you see `missing revert data` or `fee payer address ... does not exist`:** pre-check `owner`/`operator` registration state, name length (1-15 bytes), and owner gas balance before sending the tx.

### Changing the Operator Later

If you need to rotate your Operator wallet, use `system.account.set.operator`:

```javascript
const SET_OPERATOR_ABI = [
  "function executeTyped(address newOperator) returns (bytes)",
];
const setOperatorSystem = await getSystem(
  "system.account.set.operator",
  SET_OPERATOR_ABI,
  ownerSigner // Must use Owner wallet
);

const newOperator = new ethers.Wallet(newOperatorPrivateKey, provider);
const tx = await setOperatorSystem.executeTyped(newOperator.address);
await tx.wait();
console.log("Operator updated to:", newOperator.address);
```

---

## Step 5: Get Your First Kami

After registering, you need at least one Kami to participate in gameplay (harvesting, quests, combat). There are four ways to acquire a Kami:

### Option A: KamiSwap Marketplace

The **KamiSwap** marketplace lets players buy Kamis listed by other players. This is the simplest way to get your first Kami — browse available listings and purchase one with native ETH.

See [KamiSwap — Marketplace](api/marketplace.md) for full details on browsing listings, buying, and making offers.

> **Finding your Kami after purchase:** Use `IDOwnsKamiComponent` to list your Kamis, or scan `getKamiByIndex()` (as shown in the [Complete Example](#complete-example-script) below). See [Entity Discovery — Enumerating Your Kamis](entity-ids.md#enumerating-your-kamis) for the component-based approach.

#### Pull Active Listings from Kamiden

Programmatic bots should query the Kamiden indexer before buying. Follow the proto setup in [Kamiden Indexer](api/indexer.md#connecting-from-nodejs), then fetch current listings:

```typescript
import { createChannel, createClient } from "nice-grpc-web";
import { KamidenServiceDefinition } from "./proto.ts";

const channel = createChannel("https://api.prod.kamigotchi.io");
const kamiden = createClient(KamidenServiceDefinition, channel);

const { Listings = [] } = await kamiden.getKamiMarketListings({ Size: 25 });
const activeListings = Listings
  .filter((listing) => !listing.BuyerAccountID)
  .sort((a, b) => {
    const left = BigInt(a.Price);
    const right = BigInt(b.Price);
    return left < right ? -1 : left > right ? 1 : 0;
  });

for (const listing of activeListings) {
  console.log(
    `Kami #${listing.KamiIndex} | ${ethers.formatEther(BigInt(listing.Price))} ETH | order ${listing.OrderID}`
  );
}
```

Once you choose a listing, buy it from the Owner wallet:

```javascript
const selected = activeListings[0];
if (!selected) throw new Error("No active KamiSwap listings available.");

const listingId = BigInt(selected.OrderID);
const listingPrice = BigInt(selected.Price);

const buySystem = await getSystem(
  "system.kamimarket.buy",
  ["function executeTyped(uint256[] memory listingIDs) payable returns (bytes)"],
  ownerSigner
);

await (await buySystem.executeTyped([listingId], { value: listingPrice })).wait();
console.log(`Purchased Kami #${selected.KamiIndex}`);
```

### Option B: Receive via In-Game Transfer

Another player can send you a Kami using `system.kami.send`. The Kami arrives in your account automatically — no staking required. There is a **60-minute cooldown** after receiving a Kami before you can use it in gameplay.

See [Trading](api/trading.md) for direct player-to-player item trades.

---

## Step 6: Perform Basic Actions

### Move to a Room

```javascript
const MOVE_ABI = ["function executeTyped(uint32 roomIndex) returns (bytes)"];
const moveSystem = await getSystem(
  "system.account.move",
  MOVE_ABI,
  operatorSigner
);

const tx = await moveSystem.executeTyped(1, { gasLimit: 1_200_000 });
await tx.wait();
console.log("Moved to room 1");
```

### Start Harvesting

```javascript
const HARVEST_ABI = [
  "function executeTyped(uint256 kamiID, uint32 nodeIndex, uint256 taxerID, uint256 taxAmt) returns (bytes)",
];
const harvestSystem = await getSystem(
  "system.harvest.start",
  HARVEST_ABI,
  operatorSigner
);

const tx = await harvestSystem.executeTyped(myKamiId, harvestNodeIndex, 0, 0);
await tx.wait();
console.log("Harvesting started");
```

### Collect Harvest Rewards

```javascript
const COLLECT_ABI = [
  "function executeTyped(uint256 id) returns (bytes)",
];
const collectSystem = await getSystem(
  "system.harvest.collect",
  COLLECT_ABI,
  operatorSigner
);

const tx = await collectSystem.executeTyped(harvestId);
await tx.wait();
console.log("Rewards collected");
```

### Level Up a Kami

```javascript
const LEVEL_ABI = [
  "function executeTyped(uint256 kamiID) returns (bytes)",
];
const levelSystem = await getSystem(
  "system.kami.level",
  LEVEL_ABI,
  operatorSigner
);

const tx = await levelSystem.executeTyped(kamiId);
await tx.wait();
console.log("Kami leveled up!");
```

---

## Step 7: Read Game State

```javascript
// Full ABI with struct fields — required for ethers.js to decode return values.
// See system-ids.md -> Getter System for the complete reference.
const GETTER_ABI = [
  "function getKami(uint256 kamiId) view returns (tuple(uint256 id, uint32 index, string name, string mediaURI, tuple(tuple(int32 base, int32 shift, int32 boost, int32 sync) health, tuple(int32 base, int32 shift, int32 boost, int32 sync) power, tuple(int32 base, int32 shift, int32 boost, int32 sync) harmony, tuple(int32 base, int32 shift, int32 boost, int32 sync) violence) stats, tuple(uint32 face, uint32 hand, uint32 body, uint32 background, uint32 color) traits, string[] affinities, uint256 account, uint256 level, uint256 xp, uint32 room, string state))",
  "function getAccount(uint256 accountId) view returns (tuple(uint32 index, string name, int32 currStamina, uint32 room))",
];

const getterAddr = await getSystemAddress("system.getter");
const getter = new ethers.Contract(getterAddr, GETTER_ABI, provider);

// No gas cost — read-only
const kamiData = await getter.getKami(kamiId);
console.log("Kami data:", kamiData);
```

---

## What's Next

Now that you've registered, set up wallets, and can call systems — you'll need to work with **entity IDs** for real gameplay. Entity IDs are how Kamigotchi identifies everything: your account, your Kamis, active harvests, trades, and quests.

👉 **[Entity Discovery](entity-ids.md)** — Learn how to derive and find all the entity IDs you need, with a complete helper library.

👉 **[Game Data Reference](game-data.md)** — Lookup tables for item indices, room indices, skill trees, quest chains, and harvest node data.

---

## Complete Example Script

A single end-to-end script that takes a fresh wallet through the full first-run flow: connect, register, pull KamiSwap listings, buy a Kami, move to a harvest room, start harvesting, wait, and collect.

```typescript
// complete-example.ts — Full first-run bot script (ethers v6 + Kamiden, ESM)
//
// Prerequisites:
//   npm init -y
//   npm install ethers nice-grpc-web @bufbuild/protobuf tsx
//   npm pkg set type=module
//   Copy ./proto.ts from the official client as shown in api/indexer.md
//   export OWNER_PRIVATE_KEY=0x...
//   export OPERATOR_PRIVATE_KEY=0x...
//   export KAMI_ACCOUNT_NAME=MyBot01
//   npx tsx complete-example.ts

import { ethers } from "ethers";
import { createChannel, createClient } from "nice-grpc-web";
import { KamidenServiceDefinition } from "./proto.ts";

// ============================================================
// Configuration
// ============================================================

const RPC_URL = "https://jsonrpc-yominet-1.anvil.asia-southeast.initia.xyz";
const WORLD_ADDRESS = "0x2729174c265dbBd8416C6449E0E813E88f43D0E7";
const CHAIN = { chainId: 428962654539583, name: "Yominet" };
const KAMIDEN_URL = "https://api.prod.kamigotchi.io";

// How long to harvest before collecting (in seconds).
// 120 s is enough to accumulate a small reward for demonstration.
const HARVEST_WAIT_SECONDS = 120;
const OPERATOR_GAS_FLOOR = ethers.parseEther("0.0005");
const OWNER_RESERVE = ethers.parseEther("0.0005");

// ============================================================
// Environment helpers
// ============================================================

function mustEnv(name) {
  const value = process.env[name];
  if (!value || !value.startsWith("0x")) {
    throw new Error(
      `Missing or invalid ${name}. Export it before running:\n  export ${name}=0xYOUR_KEY`
    );
  }
  return value;
}

// ============================================================
// Provider & wallets
// ============================================================

const provider = new ethers.JsonRpcProvider(RPC_URL, CHAIN);
const ownerSigner = new ethers.Wallet(mustEnv("OWNER_PRIVATE_KEY"), provider);
const operatorSigner = new ethers.Wallet(mustEnv("OPERATOR_PRIVATE_KEY"), provider);
const kamiden = createClient(
  KamidenServiceDefinition,
  createChannel(KAMIDEN_URL)
);

// ============================================================
// System resolver (inlined — no external helper import)
// ============================================================

const world = new ethers.Contract(
  WORLD_ADDRESS,
  ["function systems() view returns (address)"],
  provider
);

const SYSTEMS_COMPONENT_ABI = [
  "function getEntitiesWithValue(uint256) view returns (uint256[])",
];

const systemCache = new Map();

async function getSystemAddress(systemId) {
  if (systemCache.has(systemId)) return systemCache.get(systemId);

  const hash = ethers.keccak256(ethers.toUtf8Bytes(systemId));

  // World.systems() returns the SystemsComponent (IUint256Component),
  // which maps systemAddress -> systemId. We reverse-lookup by value.
  const scAddr = await world.systems();
  const sc = new ethers.Contract(scAddr, SYSTEMS_COMPONENT_ABI, provider);
  const entities = await sc.getEntitiesWithValue(hash);
  if (entities.length === 0) {
    throw new Error(`System "${systemId}" not found in registry`);
  }
  const addr = ethers.getAddress(ethers.toBeHex(entities[0], 20));
  systemCache.set(systemId, addr);
  return addr;
}

async function getSystem(systemId, abi, signer) {
  const address = await getSystemAddress(systemId);
  return new ethers.Contract(address, abi, signer);
}

// ============================================================
// Entity ID helpers
// ============================================================

/** Harvest entity ID: keccak256(abi.encodePacked("harvest", uint256(kamiEntityId))) */
function getHarvestEntityId(kamiEntityId) {
  return BigInt(
    ethers.keccak256(
      ethers.solidityPacked(["string", "uint256"], ["harvest", kamiEntityId])
    )
  );
}

// ============================================================
// Main flow
// ============================================================

async function main() {
  // ----------------------------------------------------------
  // 1. Connect and check balances
  // ----------------------------------------------------------
  const blockNumber = await provider.getBlockNumber();
  console.log(`Connected to Yominet (block ${blockNumber})`);
  console.log("Owner:   ", ownerSigner.address);
  console.log("Operator:", operatorSigner.address);

  if (ownerSigner.address === operatorSigner.address) {
    throw new Error("Operator must be a distinct address. Do not reuse the owner key.");
  }

  const [ownerBal, operatorBal] = await Promise.all([
    provider.getBalance(ownerSigner.address),
    provider.getBalance(operatorSigner.address),
  ]);
  console.log("Owner balance:   ", ethers.formatEther(ownerBal), "ETH");
  console.log("Operator balance:", ethers.formatEther(operatorBal), "ETH");

  if (ownerBal === 0n) throw new Error("Owner wallet has no ETH. Bridge funds first.");
  if (operatorBal === 0n) {
    console.warn("⚠️  Operator wallet has no ETH. It will need gas to send gameplay transactions.");
    console.warn("   Send a small amount of ETH to:", operatorSigner.address);
  } else if (operatorBal < OPERATOR_GAS_FLOOR) {
    console.warn("⚠️  Operator gas is low:", ethers.formatEther(operatorBal), "ETH");
  }

  // ----------------------------------------------------------
  // 2. Register account (skip if already registered)
  // ----------------------------------------------------------
  const registerSystem = await getSystem(
    "system.account.register",
    ["function executeTyped(address operatorAddress, string name) returns (bytes)"],
    ownerSigner
  );
  const getterForRegister = await getSystem(
    "system.getter",
    [
      "function getAccount(uint256 accountId) view returns (tuple(uint32 index, string name, int32 currStamina, uint32 room))",
    ],
    provider
  );

  const accountName = process.env.KAMI_ACCOUNT_NAME ?? "MyBot01";
  const accountNameBytes = ethers.toUtf8Bytes(accountName).length;
  if (accountNameBytes < 1 || accountNameBytes > 15) {
    throw new Error(
      `Invalid KAMI_ACCOUNT_NAME "${accountName}" (${accountNameBytes} bytes). Use 1-15 bytes.`
    );
  }

  async function hasAccount(address) {
    try {
      const account = await getterForRegister.getAccount(BigInt(address));
      return account.name !== "";
    } catch {
      return false;
    }
  }

  if (await hasAccount(ownerSigner.address)) {
    console.log("Owner already registered — skipping.");
  } else {
    if (await hasAccount(operatorSigner.address)) {
      throw new Error(
        "Operator address already in use. Create a fresh operator wallet and retry."
      );
    }

    const regGas = await registerSystem.executeTyped.estimateGas(
      operatorSigner.address,
      accountName
    );
    const gasPrice = (await provider.getFeeData()).gasPrice ?? 2_500_000n;
    const minRegCost = regGas * gasPrice;
    if (ownerBal < minRegCost) {
      throw new Error(
        `Owner has ${ethers.formatEther(ownerBal)} ETH, but register() needs at least ${ethers.formatEther(minRegCost)} ETH for gas`
      );
    }

    try {
      const regTx = await registerSystem.executeTyped(
        operatorSigner.address,
        accountName
      );
      await regTx.wait();
      console.log("Account registered.");
    } catch (err) {
      const reason = err.reason || err.message || "";
      if (reason.includes("missing revert data")) {
        throw new Error(
          "register() reverted without reason. Re-check owner/operator registration state, name byte length (1-15), and owner ETH."
        );
      }
      throw err;
    }
  }

  // ----------------------------------------------------------
  // 3. Acquire first Kami via KamiSwap Marketplace
  // ----------------------------------------------------------
  const ownerBalanceAfterRegister = await provider.getBalance(ownerSigner.address);
  const maxKamiSpend =
    ownerBalanceAfterRegister > OWNER_RESERVE
      ? ownerBalanceAfterRegister - OWNER_RESERVE
      : 0n;
  const listingsResponse = await kamiden.getKamiMarketListings({ Size: 25 });
  const activeListings = (listingsResponse.Listings ?? [])
    .filter((listing) => !listing.BuyerAccountID)
    .sort((a, b) => {
      const left = BigInt(a.Price);
      const right = BigInt(b.Price);
      return left < right ? -1 : left > right ? 1 : 0;
    });

  if (activeListings.length === 0) {
    throw new Error("No active KamiSwap listings available.");
  }

  console.log("\nActive KamiSwap listings:");
  for (const listing of activeListings.slice(0, 10)) {
    console.log(
      `  Kami #${listing.KamiIndex} | ${ethers.formatEther(BigInt(listing.Price))} ETH | order ${listing.OrderID}`
    );
  }

  const selectedListing = activeListings.find(
    (listing) => BigInt(listing.Price) <= maxKamiSpend
  );
  if (!selectedListing) {
    throw new Error(
      `No listing is affordable after reserving ${ethers.formatEther(OWNER_RESERVE)} ETH for owner gas.`
    );
  }

  const listingId = BigInt(selectedListing.OrderID);
  const listingPrice = BigInt(selectedListing.Price);
  console.log(
    `\nBuying Kami #${selectedListing.KamiIndex} for ${ethers.formatEther(listingPrice)} ETH (order ${selectedListing.OrderID})`
  );

  const buySystem = await getSystem(
    "system.kamimarket.buy",
    ["function executeTyped(uint256[] memory listingIDs) payable returns (bytes)"],
    ownerSigner
  );

  const buyTx = await buySystem.executeTyped([listingId], { value: listingPrice });
  await buyTx.wait();
  console.log("Kami purchased.");

  // ----------------------------------------------------------
  // 4. Discover the Kami's entity ID via component lookup
  // ----------------------------------------------------------
  // Use the component.id.kami.owns component to find all Kamis owned by this
  // account. This is O(1) on-chain — no brute-force scanning required.
  // See: entity-ids.md and system-ids.md

  // Resolve a component address from the World's component registry.
  // Components resolve via world.components(), NOT world.systems().
  const worldForComponents = new ethers.Contract(
    WORLD_ADDRESS,
    ["function components() view returns (address)"],
    provider
  );

  async function getComponentAddress(componentName) {
    const hash = ethers.keccak256(ethers.toUtf8Bytes(componentName));
    const componentsRegistryAddr = await worldForComponents.components();
    const componentsRegistry = new ethers.Contract(
      componentsRegistryAddr,
      ["function getEntitiesWithValue(uint256) view returns (uint256[])"],
      provider
    );
    const entities = await componentsRegistry.getEntitiesWithValue(hash);
    if (entities.length === 0)
      throw new Error(`Component not found: ${componentName}`);
    return ethers.getAddress(ethers.toBeHex(entities[0], 20));
  }

  const accountEntityId = BigInt(ownerSigner.address);

  const OWNS_KAMI_ABI = [
    "function getEntitiesWithValue(uint256) view returns (uint256[])",
  ];
  const ownsKamiAddr = await getComponentAddress("component.id.kami.owns");
  const ownsKami = new ethers.Contract(ownsKamiAddr, OWNS_KAMI_ABI, provider);

  const myKamiIds = await ownsKami.getEntitiesWithValue(accountEntityId);
  if (myKamiIds.length === 0) {
    throw new Error(
      "No Kami found for this account. Buy one from KamiSwap or mint via Gacha first."
    );
  }

  const GETTER_ABI = [
    "function getKami(uint256 kamiId) view returns (tuple(uint256 id, uint32 index, string name, string mediaURI, tuple(tuple(int32 base, int32 shift, int32 boost, int32 sync) health, tuple(int32 base, int32 shift, int32 boost, int32 sync) power, tuple(int32 base, int32 shift, int32 boost, int32 sync) harmony, tuple(int32 base, int32 shift, int32 boost, int32 sync) violence) stats, tuple(uint32 face, uint32 hand, uint32 body, uint32 background, uint32 color) traits, string[] affinities, uint256 account, uint256 level, uint256 xp, uint32 room, string state))",
    "function getAccount(uint256 accountId) view returns (tuple(uint32 index, string name, int32 currStamina, uint32 room))",
  ];
  const getterAddr = await getSystemAddress("system.getter");
  const getter = new ethers.Contract(getterAddr, GETTER_ABI, provider);

  // Use the first owned Kami
  const kamiEntityId = myKamiIds[0];
  const kamiData = await getter.getKami(kamiEntityId);
  console.log(
    `Found Kami: entityId=${kamiEntityId} | index=${kamiData.index} | name=${kamiData.name || "(unnamed)"}`
  );
  console.log(`Owned Kamis total: ${myKamiIds.length}`);

  // ----------------------------------------------------------
  // 5. Move to a harvest room (Room 1 — Misty Riverside has a node)
  // ----------------------------------------------------------
  // New accounts start in Room 1 after registration, but if we've moved
  // before, make sure we're there now.
  const accountData = await getter.getAccount(accountEntityId);
  const currentRoom = accountData.room;

  if (Number(currentRoom) !== 1) {
    const moveSystem = await getSystem(
      "system.account.move",
      ["function executeTyped(uint32 roomIndex) returns (bytes)"],
      operatorSigner
    );
    const moveTx = await moveSystem.executeTyped(1, { gasLimit: 1_200_000 });
    await moveTx.wait();
    console.log("Moved to Room 1.");
  } else {
    console.log("Already in Room 1.");
  }

  // ----------------------------------------------------------
  // 6. Start harvesting
  // ----------------------------------------------------------
  // harvest.start params:
  //   kamiID    — entity ID of the Kami
  //   nodeIndex — harvest node index (node index matches room index; Room 1 = node 1)
  //   taxerID   — 0 for player-initiated harvests
  //   taxAmt    — 0 for player-initiated harvests
  const harvestStartSystem = await getSystem(
    "system.harvest.start",
    [
      "function executeTyped(uint256 kamiID, uint32 nodeIndex, uint256 taxerID, uint256 taxAmt) returns (bytes)",
    ],
    operatorSigner
  );

  try {
    const startTx = await harvestStartSystem.executeTyped(kamiEntityId, 1, 0, 0);
    await startTx.wait();
    console.log("Harvesting started on node 1.");
  } catch (err) {
    const reason = err.reason || err.message || "";
    if (reason.includes("already") || reason.includes("harvesting")) {
      console.log("Kami is already harvesting — skipping start.");
    } else {
      throw err;
    }
  }

  // ----------------------------------------------------------
  // 7. Wait for rewards to accumulate
  // ----------------------------------------------------------
  console.log(`Waiting ${HARVEST_WAIT_SECONDS}s for rewards to accumulate...`);
  await new Promise((resolve) => setTimeout(resolve, HARVEST_WAIT_SECONDS * 1000));

  // ----------------------------------------------------------
  // 8. Collect harvest rewards
  // ----------------------------------------------------------
  // Harvest entity ID is deterministic: keccak256("harvest", kamiEntityId)
  const harvestEntityId = getHarvestEntityId(kamiEntityId);

  const collectSystem = await getSystem(
    "system.harvest.collect",
    ["function executeTyped(uint256 id) returns (bytes)"],
    operatorSigner
  );

  const collectTx = await collectSystem.executeTyped(harvestEntityId);
  await collectTx.wait();
  console.log("Rewards collected! Harvest ID:", harvestEntityId.toString());

  console.log("Done. Your bot is registered, has a Kami, and is harvesting on Yominet.");
}

main().catch((err) => {
  console.error("Fatal error:", err.reason || err.message || err);
  process.exit(1);
});
```

---

## Gas Quick Reference

| Operation | Gas Limit | Notes |
|-----------|-----------|-------|
| Most systems | Default | Let the provider estimate |
| `account.move()` | 1,200,000 | Rooms with gates |
| `harvest.liquidate()` | 7,500,000 | Complex PvP logic |
| `gacha.mint(n)` | 4M + 3M × n | Scales with mint count |

> **Default gas estimation:** For systems marked "Default" above, ethers.js gas estimation works correctly on Yominet. Only override `gasLimit` for the specific systems noted (move: 1.2M, liquidate: 7.5M, gacha mint: 4M+3M/kami).

---

## Transaction Management

When building bots or automated systems that send rapid transactions, you need to manage **nonces** and **gas settings** carefully. The official Kamigotchi client uses an internal `TxQueue` that handles this — here's how to replicate the key patterns.

### Gas Settings

Yominet uses a flat fee model. Hardcode these values — do **not** rely on `eth_gasPrice` or EIP-1559 estimation:

```javascript
const TX_OVERRIDES = {
  maxFeePerGas: 2500000n,       // 0.0025 gwei — Yominet's flat gas price
  maxPriorityFeePerGas: 0n,     // No priority fee needed
};

const tx = await system.executeTyped(args, {
  ...TX_OVERRIDES,
  gasLimit: 1_200_000,          // Set per-system (see Gas Quick Reference)
});
```

### Nonce Management

If you send multiple transactions without waiting for each to confirm, you **must** manage nonces manually. Otherwise the RPC will reject transactions with duplicate or out-of-order nonces.

```javascript
const signer = operatorSigner; // or ownerSigner, depending on the systems you call

// Fetch the current nonce once, then increment locally
let nonce = await provider.getTransactionCount(signer.address, "pending");

async function sendWithNonce(system, method, args, overrides = {}) {
  const tx = await system[method](...args, {
    ...TX_OVERRIDES,
    nonce: nonce,
    ...overrides,
  });
  nonce++; // Increment immediately — don't wait for confirmation
  return tx;
}
```

### Retry on Nonce Errors

Nonce errors (`NONCE_EXPIRED`, `account sequence mismatch`, `TRANSACTION_REPLACED`) mean your local nonce drifted from the chain. Reset from the network and retry:

```javascript
async function sendWithRetry(system, method, args, overrides = {}) {
  try {
    return await sendWithNonce(system, method, args, overrides);
  } catch (error) {
    const isNonceError =
      error?.code === "NONCE_EXPIRED" ||
      error?.code === "TRANSACTION_REPLACED" ||
      error?.message?.includes("account sequence");

    if (isNonceError) {
      // Reset nonce from network and retry once
      nonce = await provider.getTransactionCount(signer.address, "pending");
      return await sendWithNonce(system, method, args, overrides);
    }
    throw error;
  }
}
```

> **⚠️ Warning:** Sending multiple transactions without nonce management will cause failures. Always track nonces locally if you're sending faster than block confirmation time. The official client uses a mutex-protected queue with automatic nonce tracking — consider a similar pattern for production bots.

---

## Common Pitfalls

| Issue | Solution |
|-------|----------|
| `"Not owner"` revert | Use the **owner wallet** for privileged operations |
| `"Not registered"` revert | Call `register()` first |
| System address is `0x0` | Check the system ID string for typos |
| Transaction reverts silently | Wrap in try/catch and check `error.reason` |
| Stale UI data | Call `echo.kamis()` or `echo.room()` to force-emit |
| ERC20 deposit fails | Approve the World contract for the token amount |

---

## Architecture Quick Reference

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Owner Wallet │     │   World      │     │  Components  │
│ (register,   │────▶│  (registry)  │────▶│  (state)     │
│  NFTs, ONYX) │     │              │     │              │
└──────────────┘     │  ┌────────┐  │     │ Health       │
                     │  │System A│  │     │ Power        │
┌──────────────┐     │  │System B│  │     │ Inventory    │
│ Operator     │────▶│  │System C│  │     │ Position     │
│ Wallet       │     │  └────────┘  │     │ ...          │
│ (gameplay)   │     └──────────────┘     └──────────────┘
└──────────────┘
```

---

## Next Steps

> 📖 **Read next: [Entity Discovery](entity-ids.md)** — Understanding how to derive entity IDs is essential for reading game state, building queries, and calling most systems. Read this before diving into individual API pages.

1. **Explore the API** — Browse the [Player API pages](sdk-setup.md) for full function documentation
2. **Check contracts** — See [Live Addresses](addresses.md) and [System IDs](system-ids.md)
3. **Understand the chain** — Review [Chain Configuration](chain.md) for network details
4. **Read the architecture** — [Architecture Overview](architecture.md) explains the MUD ECS model

---

## Support

For questions, integration support, or to report issues, contact the Asphodel team directly.

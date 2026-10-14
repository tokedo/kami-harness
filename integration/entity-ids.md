> **Doc Class:** Core Resource
> **Canonical Source:** Kamigotchi on-chain contracts on Yominet and the official repository (`Asphodel-OS/kamigotchi-open`, the public mirror of the studio's development repo).
> **Freshness Rule:** Verify mutable values against canonical sources before merge .

# Entity Discovery

How to find and derive the entity IDs you need for gameplay. This is the missing link between "I registered an account" and "now what?"

---

## The MUD ECS Pattern

In Kamigotchi's MUD Entity Component System, everything is an **entity** — a `uint256` identifier. Accounts, Kamis, harvests, trades, quests, rooms, items, and nodes are all entities.

Entity IDs are computed **deterministically** using one of two patterns:

| Pattern | How | Example |
|---------|-----|---------|
| **Address cast** | `uint256(uint160(address))` | Account entities |
| **Keccak hash** | `keccak256(abi.encodePacked(prefix, index))` | Kamis, harvests, rooms, nodes, items |

This means you can **derive** most entity IDs client-side without any on-chain calls.

---

## Account Entity ID

Your account entity ID is simply your **owner wallet address** cast to `uint256`:

```javascript
// Derive account entity ID from owner wallet address
function getAccountEntityId(ownerAddress) {
  return BigInt(ownerAddress);
}

// Example
const ownerAddress = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045";
const accountId = BigInt(ownerAddress);
// => 1234...n (a large uint256)
```

**How it works:** In `LibAccount.sol`, the `create()` function calls `addressToEntity(ownerAddr)`, which is defined as:

```solidity
function addressToEntity(address addr) pure returns (uint256) {
  return uint256(uint160(addr));
}
```

The `getByOwner()` function uses the same derivation — it takes `uint256(uint160(owner))` and verifies the entity has the `"ACCOUNT"` shape.

> **Starting room:** After registration, the account's `IndexRoomComponent` is set to **1** (Misty Riverside). You can read the current room via `GetterSystem.getAccount(id).room`.

---

## Kami Entity IDs

### Deriving from Token Index

Every Kami has a **token index** (`uint32`). The entity ID is derived deterministically:

```solidity
// Solidity (from LibKami.sol)
function genID(uint32 kamiIndex) internal pure returns (uint256) {
    return uint256(keccak256(abi.encodePacked("kami.id", kamiIndex)));
}
```

```javascript
// JavaScript equivalent
import { ethers } from "ethers";

function getKamiEntityId(kamiIndex) {
  return BigInt(
    ethers.keccak256(
      ethers.solidityPacked(["string", "uint32"], ["kami.id", kamiIndex])
    )
  );
}

// Example: Kami with token index 42
const kamiId = getKamiEntityId(42);
```

### After Gacha Minting

The gacha mint is a two-step process: **commit** (mint) → **reveal**.

1. **`KamiGachaMintSystem.executeTyped(amount)`** — Commits to a gacha roll. Returns encoded commit IDs (not Kami IDs yet).
2. **`KamiGachaRevealSystem.reveal(commitIDs)`** — Reveals the actual Kamis. Returns an array of **Kami entity IDs**.

```javascript
// Step 1: Mint (commit)
const mintSystem = await getSystem(
  "system.kami.gacha.mint",
  ["function executeTyped(uint256 amount) returns (bytes)"],
  ownerSigner
);

// Preflight only: staticCall can drift from mined state.
const encodedPreflightCommitIds = await mintSystem.executeTyped.staticCall(1);
const [preflightCommitIds] = ethers.AbiCoder.defaultAbiCoder().decode(
  ["uint256[]"],
  encodedPreflightCommitIds
);

const mintTx = await mintSystem.executeTyped(1);
const mintReceipt = await mintTx.wait();

async function resolveCommitIds(mintTxHash, fallbackIds) {
  // Expected indexer response: { "commitIds": ["123", "456"] }
  const indexerBaseUrl = process.env.KAMIGOTCHI_INDEXER_URL;
  if (!indexerBaseUrl) return fallbackIds;

  const url = `${indexerBaseUrl}/gacha/commits?mintTxHash=${mintTxHash}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch commit IDs from indexer (${res.status})`);

  const payload = await res.json();
  if (!Array.isArray(payload.commitIds) || payload.commitIds.length === 0) {
    throw new Error("Indexer response missing commitIds");
  }
  return payload.commitIds.map((v) => BigInt(v));
}

const commitIds = await resolveCommitIds(mintReceipt.hash, preflightCommitIds);

// Step 2: Reveal (must wait ~1 block for randomness)
const revealSystem = await getSystem(
  "system.kami.gacha.reveal",
  ["function reveal(uint256[] commitIDs) returns (uint256[])"],
  ownerSigner // can be called by anyone
);
const revealTx = await revealSystem.reveal(commitIds);
const revealReceipt = await revealTx.wait();

// The return value contains the Kami entity IDs
```

> **Note:** `staticCall` is preflight only and can drift if state changes between simulation and tx inclusion. For production bots, resolve commit IDs from confirmed tx data (for example an indexer endpoint keyed by `mintTxHash`) before reveal retries.

### After Staking a Kami721 NFT

When staking an ERC-721 Kami, the **token ID from the NFT contract IS the token index** passed to the stake system:

```javascript
const tokenId = 42; // your Kami721 NFT token ID

// The entity ID for this Kami is:
const kamiEntityId = getKamiEntityId(tokenId);
// = keccak256(abi.encodePacked("kami.id", uint32(42)))
```

After staking via `system.kami721.stake`, the Kami entity is linked to your account entity.

### Enumerating Your Kamis

Use the **GetterSystem** to look up Kami data by index:

```javascript
const GETTER_ABI = [
  "function getKamiByIndex(uint32 index) view returns (tuple)",
  "function getKami(uint256 id) view returns (tuple)",
];
const getter = new ethers.Contract(getterSystemAddr, GETTER_ABI, provider);

// Look up Kami by its token index
const kamiData = await getter.getKamiByIndex(42);
console.log("Kami entity ID:", kamiData.id);
console.log("Account:", kamiData.account);  // 0 if unowned
console.log("State:", kamiData.state);      // "RESTING", "HARVESTING", "DEAD", "721_EXTERNAL"

// Stat fields: base, shift, boost, sync
// ⚠️ ethers.js gotcha: `kamiData.health.shift` returns a function (Array.shift),
// not the stat value. Access stat fields by positional index instead:
const hp = kamiData.health;
console.log("Health:", `base=${hp[0]} shift=${hp[1]} boost=${hp[2]} sync=${hp[3]}`);
```

To list all Kamis owned by your account, use the **`component.id.kami.owns`** component on-chain, or call `getKami()` with known entity IDs. The `LibAccount.getKamis(accID)` function returns all Kami entity IDs owned by an account — this can be queried through the component directly.

### After KamiSwap or Gacha Purchase

After buying a Kami, you need its token index to derive the entity ID. Use the `component.id.kami.owns` component to find all Kamis owned by your account:

```javascript
// Find your Kami after purchase using component read
const OWNS_KAMI_ABI = ["function getEntitiesWithValue(uint256) view returns (uint256[])"];
const ownsKamiAddr = await getComponentAddress("component.id.kami.owns");
const ownsKami = new ethers.Contract(ownsKamiAddr, OWNS_KAMI_ABI, provider);

const accountId = BigInt(ownerSigner.address);
const myKamiIds = await ownsKami.getEntitiesWithValue(accountId);

// Get token index for each Kami
const getter = new ethers.Contract(getterAddr, GETTER_ABI, provider);
for (const kamiId of myKamiIds) {
  const data = await getter.getKami(kamiId);
  console.log(`Kami #${data.index}: ${data.name || "(unnamed)"} — ${data.state}`);
}

// Use the first Kami's entity ID for harvesting, etc.
const myKamiEntityId = myKamiIds[0];
```

See [Reading On-Chain Components](system-ids.md#reading-on-chain-components) for the `getComponentAddress()` helper.

---

## Harvest Entity IDs

Harvest entity IDs are derived **deterministically from the Kami entity ID**:

```solidity
// Solidity (from LibHarvest.sol)
function genID(uint256 kamiID) internal pure returns (uint256) {
    return uint256(keccak256(abi.encodePacked("harvest", kamiID)));
}
```

```javascript
// JavaScript equivalent
function getHarvestEntityId(kamiEntityId) {
  return BigInt(
    ethers.keccak256(
      ethers.solidityPacked(["string", "uint256"], ["harvest", kamiEntityId])
    )
  );
}

// Example
const kamiId = getKamiEntityId(42);
const harvestId = getHarvestEntityId(kamiId);
```

### From the `harvest.start()` Return Value

The `HarvestStartSystem` also **returns the harvest entity ID** in its return value:

```javascript
const harvestSystem = await getSystem(
  "system.harvest.start",
  ["function executeTyped(uint256 kamiID, uint32 nodeIndex, uint256 taxerID, uint256 taxAmt) returns (bytes)"],
  operatorSigner
);

const tx = await harvestSystem.executeTyped(kamiId, nodeIndex, 0, 0);
const receipt = await tx.wait();

// The return value is abi.encode(harvestEntityId)
// But you can also just compute it:
const harvestId = getHarvestEntityId(kamiId);
```

### Key Insight

Each Kami can only have **one harvest at a time**. The harvest entity ID is always deterministic from the Kami ID, so you never need to store it — just recompute it when needed.

---

## Trade Entity IDs

Trade entity IDs are **generated on-chain** using `world.getUniqueEntityId()`, which computes `keccak256(abi.encodePacked(++nonce))`. The nonce increments, but the resulting entity IDs are keccak hashes — large seemingly-random `uint256` values, **not** sequential integers. They cannot be predicted client-side.

### From the `trade.create()` Return Value

```javascript
const tradeSystem = await getSystem(
  "system.trade.create",
  ["function executeTyped(uint32[] buyIndices, uint256[] buyAmts, uint32[] sellIndices, uint256[] sellAmts, uint256 targetID) returns (bytes)"],
  ownerSigner
);

const tx = await tradeSystem.executeTyped(
  [1],        // buy MUSU
  [1000n],    // amount
  [1001],     // sell Wooden Sticks
  [5n],       // amount
  0           // no target (open trade)
);
const receipt = await tx.wait();

// Decode the return value to get tradeId
// return abi.encode(id)
```

### From Events

The `TradeCreateSystem` emits a `TRADE_CREATE` event containing:
- Trade ID
- Maker account ID
- Target taker account ID
- Buy order (indices + amounts)
- Sell order (indices + amounts)

Parse the transaction receipt logs to extract the trade entity ID.

---

## Quest Entity IDs

Quest entity IDs (for *accepted* quests) are derived **deterministically** from the quest registry index and the account ID:

```solidity
// Solidity (from LibQuest.sol)
function genQuestID(uint32 index, uint256 accID) internal pure returns (uint256) {
    return uint256(keccak256(abi.encodePacked("quest.instance", index, accID)));
}
```

```javascript
// JavaScript equivalent
function getQuestEntityId(questIndex, accountEntityId) {
  return BigInt(
    ethers.keccak256(
      ethers.solidityPacked(
        ["string", "uint32", "uint256"],
        ["quest.instance", questIndex, accountEntityId]
      )
    )
  );
}

// Example: Quest index 1 for your account
const questId = getQuestEntityId(1, accountId);
```

### From the `quest.accept()` Return Value

The `QuestAcceptSystem` also returns the quest entity ID:

```javascript
const questSystem = await getSystem(
  "system.quest.accept",
  ["function executeTyped(uint32 index) returns (bytes)"],
  operatorSigner
);

const tx = await questSystem.executeTyped(1); // accept quest index 1
const receipt = await tx.wait();

// Return value is abi.encode(questID)
// But you can compute it: getQuestEntityId(1, accountId)
```

---

## Room, Node, and Item Entity IDs

These registry entities follow the same keccak hash pattern:

```javascript
// Room entity ID
function getRoomEntityId(roomIndex) {
  return BigInt(
    ethers.keccak256(
      ethers.solidityPacked(["string", "uint32"], ["room", roomIndex])
    )
  );
}

// Node entity ID (harvest nodes share the same index as their room)
function getNodeEntityId(nodeIndex) {
  return BigInt(
    ethers.keccak256(
      ethers.solidityPacked(["string", "uint32"], ["node", nodeIndex])
    )
  );
}

// Item entity ID (registry item)
function getItemEntityId(itemIndex) {
  return BigInt(
    ethers.keccak256(
      ethers.solidityPacked(["string", "uint32"], ["registry.item", itemIndex])
    )
  );
}

// Quest registry entity ID (not the same as an accepted quest instance)
function getQuestRegistryEntityId(questIndex) {
  return BigInt(
    ethers.keccak256(
      ethers.solidityPacked(["string", "uint32"], ["registry.quest", questIndex])
    )
  );
}
```

> **Note:** For rooms and nodes, the index used is the `uint32` room/node index (e.g., room 1, node 12). These are **not** the entity IDs — the entity IDs are the keccak hashes. You pass **indices** (not entity IDs) to most system calls like `account.move(roomIndex)` or `harvest.start(kamiID, nodeIndex, ...)`.

---

## Quick Reference: Entity ID Derivation

| Entity | Derivation | Deterministic? |
|--------|-----------|----------------|
| **Account** | `uint256(uint160(ownerAddress))` | ✅ Yes |
| **Kami** | `keccak256("kami.id", kamiIndex)` | ✅ Yes |
| **Harvest** | `keccak256("harvest", kamiEntityId)` | ✅ Yes |
| **Quest (instance)** | `keccak256("quest.instance", questIndex, accountId)` | ✅ Yes |
| **Trade** | `world.getUniqueEntityId()` — `keccak256(++nonce)` | ❌ No (read from return value or events) |
| **Room** | `keccak256("room", roomIndex)` | ✅ Yes |
| **Node** | `keccak256("node", nodeIndex)` | ✅ Yes |
| **Item (registry)** | `keccak256("registry.item", itemIndex)` | ✅ Yes |
| **Quest (registry)** | `keccak256("registry.quest", questIndex)` | ✅ Yes |
| **Scavenge Bar (registry)** | `keccak256("registry.scavenge", field, index)` | ✅ Yes |
| **Scavenge Bar (instance)** | `keccak256("scavenge.instance", field, index, holderID)` | ✅ Yes |
| **Inventory** | `keccak256("inventory.instance", holderEntityId, itemIndex)` | ✅ Yes |
| **Equipment** | `keccak256("equipment.instance", holderEntityId, slot)` | ✅ Yes |
| **Friend Request** | `keccak256("friendship", sourceAccID, targetAccID)` | ✅ Yes |

---

## Scavenge Bar Entity IDs

Scavenge bars (reward progress trackers attached to harvest nodes) have two entity types: a **registry** entry defining the bar's configuration, and an **instance** entry tracking a specific player's progress.

```solidity
// Solidity (from LibScavenge.sol)

// Registry (shared bar definition)
function genRegID(string memory field, uint32 index) internal pure returns (uint256) {
    return uint256(keccak256(abi.encodePacked("registry.scavenge", field, index)));
}

// Instance (per-player progress)
function genInstanceID(string memory field, uint32 index, uint256 holderID) internal pure returns (uint256) {
    return uint256(keccak256(abi.encodePacked("scavenge.instance", field, index, holderID)));
}
```

```javascript
// JavaScript equivalents
function getScavengeRegistryId(field, index) {
  return BigInt(
    ethers.keccak256(
      ethers.solidityPacked(["string", "string", "uint32"], ["registry.scavenge", field, index])
    )
  );
}

function getScavengeInstanceId(field, index, holderEntityId) {
  return BigInt(
    ethers.keccak256(
      ethers.solidityPacked(
        ["string", "string", "uint32", "uint256"],
        ["scavenge.instance", field, index, holderEntityId]
      )
    )
  );
}

// Example: Scavenge bar for node index 5, for your account
const regId = getScavengeRegistryId("NODE", 5);
const instanceId = getScavengeInstanceId("NODE", 5, accountId);
```

The `field` parameter is typically `"NODE"` (uppercased) for harvest node scavenge bars.

---

## Friendship Entity IDs

Friendship entities are **directional** — there is one entity from account A → B and another from B → A. Each entity tracks the relationship state (`REQUEST`, `FRIEND`, or `BLOCKED`).

```solidity
// Solidity (from LibFriend.sol)
function genID(uint256 accID, uint256 targetID) internal pure returns (uint256) {
    return uint256(keccak256(abi.encodePacked("friendship", accID, targetID)));
}
```

```javascript
// JavaScript equivalent
function getFriendshipEntityId(sourceAccountId, targetAccountId) {
  return BigInt(
    ethers.keccak256(
      ethers.solidityPacked(
        ["string", "uint256", "uint256"],
        ["friendship", sourceAccountId, targetAccountId]
      )
    )
  );
}

// Example: Check if you sent a friend request to another player
const friendshipId = getFriendshipEntityId(myAccountId, theirAccountId);
```

> **Note:** Friendships are bidirectional but stored as two separate entities. When A sends a friend request to B, only `friendship(A, B)` is created (state: `REQUEST`). When B accepts, `friendship(B, A)` is also created, and both are set to `FRIEND`.

---

## General Approach: Working with Return Values and Events

Most Kamigotchi systems return entity IDs in their `bytes` return value (encoded via `abi.encode`). The general workflow:

1. **Call a system** — e.g., `harvest.start()`, `trade.create()`, `quest.accept()`
2. **Read the return value** — Decode the `bytes` return to get the entity ID
3. **Or derive it** — For deterministic IDs, compute it client-side

For non-deterministic IDs (like trades), you can also parse **emitted events** from the transaction receipt. Kamigotchi uses a custom `LibEmitter` system for structured events like `TRADE_CREATE`, `TRADE_EXECUTE`, etc.

```javascript
// Example: Decoding a return value
const tx = await someSystem.executeTyped(args);
const receipt = await tx.wait();

// If you need return data before sending a tx,
// use staticCall as a preflight simulation:
const returnData = await someSystem.executeTyped.staticCall(args);
const [entityId] = ethers.AbiCoder.defaultAbiCoder().decode(
  ["uint256"],
  returnData
);
```

> **Important:** `staticCall` does not persist state and can diverge from mined tx results if state changes in between. For non-deterministic IDs, prefer decoding emitted events or reading from the indexer after confirmation.

---

## Parsing Transaction Events

Kamigotchi emits structured events via `LibEmitter`, which writes to MUD's `Store_SetRecord` log. This is the primary way to extract non-deterministic entity IDs (trades, marketplace orders, portal receipts) from mined transactions.

### Store_SetRecord Event

All MUD state changes emit a `Store_SetRecord` event:

```javascript
const STORE_SET_RECORD_ABI = [
  "event Store_SetRecord(bytes32 tableId, bytes32[] keyTuple, bytes staticData, bytes32 encodedLengths, bytes dynamicData)",
];
```

The `tableId` identifies which component/table was modified, and `keyTuple[0]` typically contains the entity ID.

### Extracting Entity IDs from Transaction Receipts

```javascript
import { ethers } from "ethers";

const STORE_SET_RECORD_TOPIC = ethers.id(
  "Store_SetRecord(bytes32,bytes32[],bytes,bytes32,bytes)"
);

/**
 * Extract entity IDs created in a transaction by filtering Store_SetRecord logs.
 * @param {ethers.TransactionReceipt} receipt - The mined transaction receipt
 * @param {string} [tableId] - Optional: filter by specific table ID (component hash)
 * @returns {bigint[]} Array of entity IDs found in keyTuple[0]
 */
function extractEntityIds(receipt, tableId) {
  const iface = new ethers.Interface([
    "event Store_SetRecord(bytes32 tableId, bytes32[] keyTuple, bytes staticData, bytes32 encodedLengths, bytes dynamicData)",
  ]);

  const entityIds = [];
  for (const log of receipt.logs) {
    if (log.topics[0] !== STORE_SET_RECORD_TOPIC) continue;
    try {
      const parsed = iface.parseLog({ topics: log.topics, data: log.data });
      if (tableId && parsed.args.tableId !== tableId) continue;
      if (parsed.args.keyTuple.length > 0) {
        entityIds.push(BigInt(parsed.args.keyTuple[0]));
      }
    } catch (_) {
      // Skip non-matching logs
    }
  }
  return entityIds;
}
```

### Marketplace: Extracting Listing and Offer IDs

After creating a listing or offer, the new order entity ID appears in the Store_SetRecord logs:

```javascript
// Create a listing
const listTx = await listSystem.executeTyped(kamiIndex, price, expiry);
const listReceipt = await listTx.wait();

// Extract the listing entity ID from events
const entityIds = extractEntityIds(listReceipt);
// The listing ID is typically the first new entity created
// Filter by checking which IDs are new marketplace order entities
console.log("Created entity IDs:", entityIds);
```

> **Tip:** Marketplace order creation emits Store_SetRecord for multiple components (order data, ownership, type). The order entity ID appears consistently across these logs. Deduplicate the extracted IDs to find unique entities.

### Trades: Extracting Trade IDs

```javascript
const tradeTx = await tradeSystem.executeTyped(buyIdx, buyAmt, sellIdx, sellAmt, 0);
const tradeReceipt = await tradeTx.wait();

const tradeEntityIds = extractEntityIds(tradeReceipt);
// The trade entity ID is the non-deterministic ID from world.getUniqueEntityId()
console.log("Trade entity ID:", tradeEntityIds[0]);
```

### ERC20 Portal: Extracting Withdrawal Receipt IDs

```javascript
const withdrawTx = await portalSystem.withdraw(itemIndex, amount);
const withdrawReceipt = await withdrawTx.wait();

const receiptIds = extractEntityIds(withdrawReceipt);
// Use this receipt ID later to claim or cancel the withdrawal
const receiptId = receiptIds[0];
```

### Droptable: Extracting Pending Reveal IDs

Harvest collections, quest completions, and sacrifices may create droptable entities that need revealing:

```javascript
const collectTx = await harvestSystem.executeTyped(harvestId);
const collectReceipt = await collectTx.wait();

// Droptable entities are created during collection
const droptableIds = extractEntityIds(collectReceipt);
// Reveal them:
await droptableRevealSystem.executeTyped(droptableIds);
```

### Gacha: Extracting Commit IDs from Mint

```javascript
const mintTx = await mintSystem.executeTyped(amount);
const mintReceipt = await mintTx.wait();

// Commit IDs from the mint transaction
const commitIds = extractEntityIds(mintReceipt);
// Wait at least 1 block, then reveal
await new Promise((r) => setTimeout(r, 2000));
await revealSystem.reveal(commitIds);
```

> **Note:** The `extractEntityIds` function returns ALL entity IDs created or modified in a transaction. For complex transactions that touch many entities, you may need to filter by component table ID or deduplicate. In practice, both deterministic IDs and non-deterministic IDs (from `world.getUniqueEntityId()`) are large keccak hashes. You may need to filter by component table ID to distinguish them.

---

## Complete Helper Library

```javascript
import { ethers } from "ethers";

export const EntityIds = {
  account(ownerAddress) {
    return BigInt(ownerAddress);
  },

  kami(kamiIndex) {
    return BigInt(
      ethers.keccak256(
        ethers.solidityPacked(["string", "uint32"], ["kami.id", kamiIndex])
      )
    );
  },

  harvest(kamiEntityId) {
    return BigInt(
      ethers.keccak256(
        ethers.solidityPacked(["string", "uint256"], ["harvest", kamiEntityId])
      )
    );
  },

  questInstance(questIndex, accountEntityId) {
    return BigInt(
      ethers.keccak256(
        ethers.solidityPacked(
          ["string", "uint32", "uint256"],
          ["quest.instance", questIndex, accountEntityId]
        )
      )
    );
  },

  room(roomIndex) {
    return BigInt(
      ethers.keccak256(
        ethers.solidityPacked(["string", "uint32"], ["room", roomIndex])
      )
    );
  },

  node(nodeIndex) {
    return BigInt(
      ethers.keccak256(
        ethers.solidityPacked(["string", "uint32"], ["node", nodeIndex])
      )
    );
  },

  item(itemIndex) {
    return BigInt(
      ethers.keccak256(
        ethers.solidityPacked(["string", "uint32"], ["registry.item", itemIndex])
      )
    );
  },

  questRegistry(questIndex) {
    return BigInt(
      ethers.keccak256(
        ethers.solidityPacked(["string", "uint32"], ["registry.quest", questIndex])
      )
    );
  },

  scavengeRegistry(field, index) {
    return BigInt(
      ethers.keccak256(
        ethers.solidityPacked(["string", "string", "uint32"], ["registry.scavenge", field, index])
      )
    );
  },

  scavengeInstance(field, index, holderEntityId) {
    return BigInt(
      ethers.keccak256(
        ethers.solidityPacked(
          ["string", "string", "uint32", "uint256"],
          ["scavenge.instance", field, index, holderEntityId]
        )
      )
    );
  },

  inventory(holderEntityId, itemIndex) {
    return BigInt(
      ethers.keccak256(
        ethers.solidityPacked(
          ["string", "uint256", "uint32"],
          ["inventory.instance", holderEntityId, itemIndex]
        )
      )
    );
  },

  equipment(holderEntityId, slot) {
    return BigInt(
      ethers.keccak256(
        ethers.solidityPacked(
          ["string", "uint256", "string"],
          ["equipment.instance", holderEntityId, slot]
        )
      )
    );
  },

  friendship(sourceAccountId, targetAccountId) {
    return BigInt(
      ethers.keccak256(
        ethers.solidityPacked(
          ["string", "uint256", "uint256"],
          ["friendship", sourceAccountId, targetAccountId]
        )
      )
    );
  },
};
```

---

## Inventory Discovery

The `GetterSystem.getAccount()` returns an `AccountShape` with four fields: `index`, `name`, `currStamina`, and `room`. **It does not include inventory.** You must query inventory separately.

### How Inventory Works

Each inventory entry is an entity with three components:

| Component | Description |
|-----------|-------------|
| `component.id.inventory.owns` | The holder's entity ID (your account ID) |
| `component.index.item` | The item's registry index (e.g., `1` for MUSU, `1001` for Wooden Stick) |
| `component.value` | The quantity held |

Inventory entity IDs are **deterministic** — derived from the holder ID and item index:

```solidity
// Solidity (from LibInventory.sol)
function genID(uint256 holderID, uint32 itemIndex) internal pure returns (uint256) {
    return uint256(keccak256(abi.encodePacked("inventory.instance", holderID, itemIndex)));
}
```

```javascript
// JavaScript equivalent
function getInventoryEntityId(holderEntityId, itemIndex) {
  return BigInt(
    ethers.keccak256(
      ethers.solidityPacked(
        ["string", "uint256", "uint32"],
        ["inventory.instance", holderEntityId, itemIndex]
      )
    )
  );
}
```

### Reading a Specific Item Balance

If you know which item you're looking for, compute the inventory entity ID and read `component.value`:

```javascript
// Check how much MUSU (item index 1) the account holds
const accountId = BigInt(ownerAddress);
const musuInventoryId = getInventoryEntityId(accountId, 1);

// Read component.value for this entity
const balance = await valueComponent.get(musuInventoryId);
console.log("MUSU balance:", balance.toString());
```

`LibInventory.getBalanceOf(components, holderID, itemIndex)` does exactly this internally.

### Enumerating All Inventory Items

To get **all** items held by an account, query `component.id.inventory.owns` for all entities with the account's ID as their value:

```javascript
// Get all inventory entity IDs for this account
const inventoryIds = await idOwnsInventoryComponent.getEntitiesWithValue(accountId);

// For each inventory entity, read the item index and quantity
for (const invId of inventoryIds) {
  const itemIndex = await indexItemComponent.get(invId);
  const quantity = await valueComponent.get(invId);
  console.log(`Item ${itemIndex}: ${quantity}`);
}
```

This mirrors `LibInventory.getAllForHolder(components, holderID)` which returns all inventory entity IDs where `component.id.inventory.owns` matches the holder.

### Key Constants

Some commonly referenced item indices:

| Constant | Index | Item |
|----------|-------|------|
| `MUSU_INDEX` | 1 | $MUSU currency |
| `GACHA_TICKET_INDEX` | 10 | Gacha Ticket |
| `REROLL_TICKET_INDEX` | 11 | Reroll Ticket |
| `ONYX_INDEX` | 100 | Onyx Shard ($ONYX) |
| `OBOL_INDEX` | 1015 | Obol |

### Notes

- Inventory entities are **created lazily** — they only exist once a player has received at least one of that item.
- When a balance reaches zero, the inventory entity is **deleted** to reduce state bloat.
- The `TRANSFER_FEE` constant is set to 15 (used for inter-account item transfers).

---

## Equipment Discovery

Equipment instances are also deterministic entities, derived from the holder ID and slot string:

```javascript
function getEquipmentEntityId(holderEntityId, slot) {
  return BigInt(
    ethers.keccak256(
      ethers.solidityPacked(
        ["string", "uint256", "string"],
        ["equipment.instance", holderEntityId, slot]
      )
    )
  );
}

// Example: Check if a Kami has something in the Kami_Pet_Slot
const equipId = getEquipmentEntityId(kamiEntityId, "Kami_Pet_Slot");
```

To enumerate all equipment on an entity, query `component.id.equipment.owns`:

```javascript
const equipIds = await idOwnsEquipmentComponent.getEntitiesWithValue(kamiEntityId);
for (const eqId of equipIds) {
  const itemIndex = await indexItemComponent.get(eqId);
  const slot = await forComponent.get(eqId);
  console.log(`Slot ${slot}: Item ${itemIndex}`);
}
```

---

## See Also

- [Game Data Reference](game-data.md) — Lookup tables for item, room, node, skill, and quest indices
- [Overview & Setup](sdk-setup.md) — SDK setup and calling conventions
- [Integration Guide](guide.md) — Step-by-step walkthrough

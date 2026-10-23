> **Doc Class:** Core Resource
> **Canonical Source:** Kamigotchi on-chain contracts on Yominet and the official repository (`Asphodel-OS/kamigotchi-open`, the public mirror of the studio's development repo).
> **Freshness Rule:** Verify mutable values against canonical sources before merge.

# System IDs & ABI References

Kamigotchi has **67 documented player-facing systems** in the World contract. Each system is identified by a human-readable string ID, hashed with `keccak256` for on-chain lookup. The World contains additional internal and admin systems not covered here.

---

## System ID Reference

### Account Systems

| System ID | Description | Wallet | Page |
|-----------|-------------|--------|------|
| `system.account.register` | Register a new account | Owner | [Account](api/account.md) |
| `system.account.move` | Move to a room | Operator | [Account](api/account.md) |
| `system.account.set.bio` | Set account bio | Operator | [Account](api/account.md) |
| `system.account.set.name` | Rename account | Owner | [Account](api/account.md) |
| `system.account.set.operator` | Update operator wallet | Owner | [Account](api/account.md) |
| `system.account.set.pfp` | Set profile picture | Operator | [Account](api/account.md) |
| `system.account.use.item` | Use item from inventory | Operator | [Items](api/items-and-crafting.md) |

### Chat

| System ID | Description | Wallet | Page |
|-----------|-------------|--------|------|
| `system.chat` | Send chat message | Operator | [Account](api/account.md) |

### Echo Systems

| System ID | Description | Wallet | Page |
|-----------|-------------|--------|------|
| `system.echo.kamis` | Force-emit Kami data | Operator | [Echo](api/echo.md) |
| `system.echo.room` | Force-emit Room data | Operator | [Echo](api/echo.md) |

### Kami Systems

| System ID | Description | Wallet | Page |
|-----------|-------------|--------|------|
| `system.kami.level` | Level up Kami | Operator | [Kami](api/kami.md) |
| `system.kami.name` | Name/rename Kami | Operator | [Kami](api/kami.md) |
| `system.kami.equip` | Equip item to Kami | Operator | [Kami](api/kami.md) |
| `system.kami.unequip` | Unequip item from Kami | Operator | [Kami](api/kami.md) |
| `system.kami.use.item` | Use item on Kami (feed) | Operator | [Kami](api/kami.md) |
| `system.kami.cast.item` | Cast item on enemy Kami | Operator | [Kami](api/kami.md) |
| `system.kami.sacrifice.commit` | Sacrifice Kami | Operator | [Kami](api/kami.md) |
| `system.kami.sacrifice.reveal` | Reveal sacrifice loot | Operator | [Kami](api/kami.md) |
| `system.kami.onyx.rename` | Rename Kami via ONYX (currently disabled) | Owner | [Kami](api/kami.md) |
| `system.kami.onyx.revive` | Revive dead Kami via ONYX | Operator | [Kami](api/kami.md) |
| `system.kami.onyx.respec` | Respec Kami via ONYX (currently disabled) | Owner | [Kami](api/kami.md) |
| `system.kami.send` | Send in-world Kami(s) to another player | Operator | [Kami](api/kami.md) |

### Skill Systems

| System ID | Description | Wallet | Page |
|-----------|-------------|--------|------|
| `system.skill.upgrade` | Upgrade Kami skill | Operator | [Skills](api/skills-and-relationships.md) |
| `system.skill.respec` | Reset Kami skills | Operator | [Skills](api/skills-and-relationships.md) |

### Harvest Systems

| System ID | Description | Wallet | Page |
|-----------|-------------|--------|------|
| `system.harvest.start` | Start harvesting | Operator | [Harvesting](api/harvesting.md) |
| `system.harvest.stop` | Stop harvesting | Operator | [Harvesting](api/harvesting.md) |
| `system.harvest.collect` | Collect harvest rewards | Operator | [Harvesting](api/harvesting.md) |
| `system.harvest.liquidate` | Liquidate harvest | Operator | [Harvesting](api/harvesting.md) |

### Item Systems

| System ID | Description | Wallet | Page |
|-----------|-------------|--------|------|
| `system.item.burn` | Burn items | Operator | [Items](api/items-and-crafting.md) |
| `system.item.transfer` | Transfer items | Owner or Operator | [Items](api/items-and-crafting.md) |
| `system.craft` | Craft item from recipe | Operator | [Items](api/items-and-crafting.md) |
| `system.droptable.item.reveal` | Reveal droptable items | Any | [Items](api/items-and-crafting.md) |

### Quest Systems

| System ID | Description | Wallet | Page |
|-----------|-------------|--------|------|
| `system.quest.accept` | Accept a quest | Operator | [Quests](api/quests.md) |
| `system.quest.complete` | Complete a quest | Operator | [Quests](api/quests.md) |
| `system.quest.drop` | Drop an active quest | Operator | [Quests](api/quests.md) |

### Trade Systems

| System ID | Description | Wallet | Page |
|-----------|-------------|--------|------|
| `system.trade.create` | Create a trade | Owner or Operator | [Trading](api/trading.md) |
| `system.trade.execute` | Execute a trade (taker) | Owner or Operator | [Trading](api/trading.md) |
| `system.trade.complete` | Complete a trade (maker) | Owner or Operator | [Trading](api/trading.md) |
| `system.trade.cancel` | Cancel a trade (maker) | Owner or Operator | [Trading](api/trading.md) |

### Social / Friend Systems

| System ID | Description | Wallet | Page |
|-----------|-------------|--------|------|
| `system.friend.request` | Send friend request | Operator | [Social](api/social.md) |
| `system.friend.accept` | Accept friend request | Operator | [Social](api/social.md) |
| `system.friend.cancel` | Cancel/remove/unblock | Operator | [Social](api/social.md) |
| `system.friend.block` | Block an account | Operator | [Social](api/social.md) |

### Listing / Merchant Systems

| System ID | Description | Wallet | Page |
|-----------|-------------|--------|------|
| `system.listing.buy` | Buy from NPC merchant | Operator | [Listings](api/listings.md) |
| `system.listing.sell` | Sell to NPC merchant | Operator | [Listings](api/listings.md) |

### Gacha / Minting Systems

| System ID | Description | Wallet | Page |
|-----------|-------------|--------|------|
| `system.kami.gacha.mint` | Mint Kami with gacha ticket | Owner or Operator | [Minting](api/minting.md) |
| `system.kami.gacha.reveal` | Reveal minted Kami | N/A | [Minting](api/minting.md) |
| `system.kami.gacha.reroll` | Reroll Kami | Owner or Operator | [Minting](api/minting.md) |
| `system.buy.gacha.ticket` | Buy gacha tickets (deprecated — use `system.auction.buy` instead) | Owner | [Minting](api/minting.md) |

### Getter / View Systems

| System ID | Description | Wallet | Page |
|-----------|-------------|--------|------|
| `system.getter` | Read-only view system (getKami, getAccount, etc.) | N/A | [Getter System](#getter-system) |

### Portal Systems

| System ID | Description | Wallet | Page |
|-----------|-------------|--------|------|
| `system.kami721.stake` | Stake Kami NFT into game | Owner | [Portal](api/portal.md) |
| `system.kami721.unstake` | Unstake Kami NFT from game | Owner | [Portal](api/portal.md) |
| `system.kami721.transfer` | Transfer Kami NFT | Owner | [Portal](api/portal.md) |
| `system.Kami721.IsInWorld` | Check if Kami is in-world (view) | N/A | [Portal](api/portal.md) |
| `system.Kami721.Metadata` | Get Kami token URI metadata (view) | N/A | [Portal](api/portal.md) |
| `system.erc20.portal` | ERC20 deposit/withdraw | Owner | [Portal](api/portal.md) |

> **IMPORTANT: Case-sensitive system IDs.** Most system IDs use lowercase dot notation (e.g., `system.account.register`). Two exceptions use **PascalCase**: `system.Kami721.IsInWorld` and `system.Kami721.Metadata`. Case is critical when hashing with `keccak256()` — a wrong case produces a different hash and the system will not resolve.

### NPC / Relationship Systems

| System ID | Description | Wallet | Page |
|-----------|-------------|--------|------|
| `system.relationship.advance` | Advance NPC relationship | Operator | [Skills & Relationships](api/skills-and-relationships.md) |

### Goal & Scavenge Systems

| System ID | Description | Wallet | Page |
|-----------|-------------|--------|------|
| `system.goal.contribute` | Contribute to goal | Operator | [Goals](api/goals-and-scavenge.md) |
| `system.goal.claim` | Claim goal reward | Operator | [Goals](api/goals-and-scavenge.md) |
| `system.scavenge.claim` | Claim scavenge points | Operator | [Goals](api/goals-and-scavenge.md) |

### Marketplace Systems

| System ID | Description | Wallet | Page |
|-----------|-------------|--------|------|
| `system.kamimarket.list` | List a Kami for sale (ETH) | Operator | [Marketplace](api/marketplace.md) |
| `system.kamimarket.buy` | Buy listed Kami(s) with ETH | Owner | [Marketplace](api/marketplace.md) |
| `system.kamimarket.offer` | Make a specific or collection offer (WETH) | Operator | [Marketplace](api/marketplace.md) |
| `system.kamimarket.acceptoffer` | Accept an offer (specific or collection) | Operator | [Marketplace](api/marketplace.md) |
| `system.kamimarket.cancel` | Cancel a listing or offer | Operator | [Marketplace](api/marketplace.md) |
| `system.newbievendor.buy` | Buy a Kami from the Newbie Vendor (one-time, new accounts only) | Owner (payable) | [Marketplace](api/marketplace.md) |

### Auction Systems

| System ID | Description | Wallet | Page |
|-----------|-------------|--------|------|
| `system.auction.buy` | Buy from auction | Owner or Operator | [Listings](api/listings.md) |

---

## Resolving System Addresses

All system addresses are resolved from the World registry using the hashed system ID:

```javascript
import { ethers } from "ethers";

const WORLD_ADDRESS = "0x2729174c265dbBd8416C6449E0E813E88f43D0E7";
const WORLD_ABI = ["function systems() view returns (address)"];
const SYSTEMS_COMPONENT_ABI = [
  "function getEntitiesWithValue(uint256) view returns (uint256[])",
];

const provider = new ethers.JsonRpcProvider(
  "https://jsonrpc-yominet-1.anvil.asia-southeast.initia.xyz"
);
const world = new ethers.Contract(WORLD_ADDRESS, WORLD_ABI, provider);
let systemsComponent;
async function getSystemsComponent() {
  if (!systemsComponent) {
    const systemsComponentAddress = await world.systems();
    systemsComponent = new ethers.Contract(
      systemsComponentAddress,
      SYSTEMS_COMPONENT_ABI,
      provider
    );
  }
  return systemsComponent;
}

async function getSystemAddress(systemStringId) {
  const hash = ethers.keccak256(ethers.toUtf8Bytes(systemStringId));
  const systemsComponent = await getSystemsComponent();
  const entities = await systemsComponent.getEntitiesWithValue(hash);
  if (entities.length === 0) throw new Error(`System not found: ${systemStringId}`);
  return ethers.getAddress(ethers.toBeHex(entities[0], 20));
}

// Examples
const kamiLevelAddr = await getSystemAddress("system.kami.level");
const harvestStartAddr = await getSystemAddress("system.harvest.start");
```

---

## ABI Pattern

All systems follow the same ABI pattern inherited from `solecs/System.sol`:

```solidity
interface ISystem {
    // Generic entry point — calldata is ABI-encoded arguments
    function execute(bytes memory arguments) external returns (bytes memory);

    // Typed entry point — varies per system
    // e.g., for KamiLevelSystem:
    // function executeTyped(uint256 kamiID) external returns (bytes memory);
}
```

### Common ABI Fragment

```javascript
// This ABI works for calling any system's execute() function
const SYSTEM_ABI = [
  "function execute(bytes) returns (bytes)",
  "function executeTyped(uint256) returns (bytes)", // varies per system
];
```

> **Note:** The `executeTyped()` signature differs per system. Refer to individual [Player API](api/overview.md) pages for exact typed signatures.

### Non-Standard Entry Points

Most systems use `executeTyped(...)` as their typed entry point. However, some systems expose **custom function names** instead:

| System | Entry Points | Signatures |
|--------|-------------|-----------|
| `system.kami.gacha.reveal` | `reveal` | `reveal(uint256[] rawCommitIDs) returns (uint256[])` |
| `system.kami.gacha.reroll` | `reroll` | `reroll(uint256[] kamiIDs) returns (uint256[])` |
| `system.buy.gacha.ticket` | `buyPublic` / `buyWL` (deprecated) | `buyPublic(uint256 amount)` / `buyWL()` — **no longer active; use `system.auction.buy` for gacha tickets** |
| `system.erc20.portal` | `deposit` / `withdraw` / `claim` / `cancel` | `deposit(uint32, uint256)` / `withdraw(uint32, uint256) returns (uint256)` / `claim(uint256)` / `cancel(uint256)` |
| `system.kami721.transfer` | `batchTransfer` / `batchTransferToMany` | `batchTransfer(uint256[], address)` / `batchTransferToMany(uint256[], address[])` |
| `system.getter` | `getKami` / `getAccount` / `getKamiByIndex` | View functions — see [Getter System](#getter-system) below |
| `system.kami.sacrifice.commit` | `executeTyped` | `executeTyped(uint32 kamiIndex) returns (uint256)` — Takes uint32 kamiIndex (ERC721 token index), not uint256 entity ID |
| `system.kami.sacrifice.reveal` | `executeTyped` / `executeTypedBatch` | `executeTyped(uint256 commitID)` / `executeTypedBatch(uint256[] commitIDs)` |
| `system.harvest.stop` | `executeTyped` / `executeBatched` / `executeBatchedAllowFailure` / `executeAllowFailure` | `executeTyped(uint256 id) returns (bytes)` / `executeBatched(uint256[] ids) returns (bytes[])` / `executeBatchedAllowFailure(uint256[] ids) returns (bytes[])` / `executeAllowFailure(bytes) returns (bytes)` |
| `system.harvest.collect` | `executeTyped` / `executeBatched` / `executeBatchedAllowFailure` / `executeAllowFailure` | `executeTyped(uint256 id) returns (bytes)` / `executeBatched(uint256[] ids) returns (bytes[])` / `executeBatchedAllowFailure(uint256[] ids) returns (bytes[])` / `executeAllowFailure(bytes) returns (bytes)` |
| `system.kami721.stake` | `executeTyped` / `executeBatch` | `executeTyped(uint32 tokenIndex) returns (bytes)` / `executeBatch(uint32[] tokenIndices)` |
| `system.kami721.unstake` | `executeTyped` / `executeBatch` | `executeTyped(uint32 tokenIndex) returns (bytes)` / `executeBatch(uint32[] tokenIndices)` |
| `system.kamimarket.offer` | `executeTypedOffer` / `executeTypedCollection` | `executeTypedOffer(uint32, uint256, uint256)` / `executeTypedCollection(uint256, uint32, uint256)` |
| `system.kamimarket.acceptoffer` | `executeTyped` (overloaded) | `executeTyped(uint256, uint32)` / `executeTyped(uint256, uint32[])` |
| `system.Kami721.IsInWorld` | `isInWorld` | `isInWorld(uint256 petIndex) view returns (bool)` |
| `system.Kami721.Metadata` | `tokenURI` | `tokenURI(uint256 petIndex) view returns (string)` |
| `system.harvest.start` | `executeTyped` / `executeBatched` | `executeTyped(uint256 kamiID, uint32 nodeIndex, uint256 taxerID, uint256 taxAmt) returns (bytes)` / `executeBatched(uint256[] kamiIDs, uint32 nodeIndex, uint256 taxerID, uint256 taxAmt) returns (bytes[])` |
| `system.kamimarket.buy` | `executeTyped` (payable, array) | `executeTyped(uint256[] listingIDs) payable returns (bytes)` |
| `system.kami.send` | `executeTyped` (overloaded) | `executeTyped(uint32, address)` / `executeTyped(uint32[], address)` |
| `system.newbievendor.buy` | `executeTyped` (payable) / `calcPrice` | `executeTyped(uint32 kamiIndex) payable returns (bytes)` / `calcPrice() view returns (uint256)` |

> When integrating, always check the actual Solidity source for the correct function name if `executeTyped()` reverts with "not implemented".

---

## Getter System

The **GetterSystem** (`system.getter`, ID = `keccak256("system.getter")`) provides read-only view functions (no gas required):

```javascript
const GETTER_ABI = [
  "function getKami(uint256 kamiId) view returns (tuple(uint256 id, uint32 index, string name, string mediaURI, tuple(tuple(int32 base, int32 shift, int32 boost, int32 sync) health, tuple(int32 base, int32 shift, int32 boost, int32 sync) power, tuple(int32 base, int32 shift, int32 boost, int32 sync) harmony, tuple(int32 base, int32 shift, int32 boost, int32 sync) violence) stats, tuple(uint32 face, uint32 hand, uint32 body, uint32 background, uint32 color) traits, string[] affinities, uint256 account, uint256 level, uint256 xp, uint32 room, string state))",
  "function getAccount(uint256 accountId) view returns (tuple(uint32 index, string name, int32 currStamina, uint32 room))",
  "function getKamiByIndex(uint32 index) view returns (tuple(uint256 id, uint32 index, string name, string mediaURI, tuple(tuple(int32 base, int32 shift, int32 boost, int32 sync) health, tuple(int32 base, int32 shift, int32 boost, int32 sync) power, tuple(int32 base, int32 shift, int32 boost, int32 sync) harmony, tuple(int32 base, int32 shift, int32 boost, int32 sync) violence) stats, tuple(uint32 face, uint32 hand, uint32 body, uint32 background, uint32 color) traits, string[] affinities, uint256 account, uint256 level, uint256 xp, uint32 room, string state))",
];

// Resolve GetterSystem address first, then call
const getterAddr = await getSystemAddress("system.getter");
const getter = new ethers.Contract(getterAddr, GETTER_ABI, provider);

const kamiData = await getter.getKami(kamiEntityId);
const accountData = await getter.getAccount(accountEntityId);
const kamiByIdx = await getter.getKamiByIndex(42);
```

### Return Type Reference

**`getKami(uint256)` / `getKamiByIndex(uint32)`** → `KamiShape`:

```solidity
struct KamiShape {
  uint256 id;
  uint32 index;
  string name;
  string mediaURI;
  KamiStats stats;    // (Stat health, Stat power, Stat harmony, Stat violence)
  KamiTraits traits;  // (uint32 face, uint32 hand, uint32 body, uint32 background, uint32 color)
  string[] affinities;
  uint256 account;
  uint256 level;
  uint256 xp;
  uint32 room;
  string state;
}

struct Stat { int32 base; int32 shift; int32 boost; int32 sync; }
```

**`getAccount(uint256)`** → `AccountShape`:

```solidity
struct AccountShape {
  uint32 index;
  string name;
  int32 currStamina;
  uint32 room;
}
```

> **Note:** `getKamiByIndex(uint32)` looks up a Kami by its token index rather than entity ID. The `execute(bytes)` function on GetterSystem is not implemented and will revert — use the named view functions directly.

---

## Reading On-Chain Components

Components store entity data in the MUD ECS model. Components resolve via `world.components()` (the **Components** registry), NOT `world.systems()` (the Systems registry).

### Resolving Component Addresses

```javascript
// Components resolve via world.components(), NOT world.systems().
// The Components registry maps componentAddress -> componentId.
const world = new ethers.Contract(WORLD_ADDRESS, [
  "function components() view returns (address)",
], provider);

async function getComponentAddress(componentName) {
  const hash = ethers.keccak256(ethers.toUtf8Bytes(componentName));
  const componentsRegistryAddr = await world.components();
  const componentsRegistry = new ethers.Contract(
    componentsRegistryAddr,
    ["function getEntitiesWithValue(uint256) view returns (uint256[])"],
    provider
  );
  const entities = await componentsRegistry.getEntitiesWithValue(hash);
  if (entities.length === 0) throw new Error(`Component not found: ${componentName}`);
  return ethers.getAddress(ethers.toBeHex(entities[0], 20));
}
```

### Key Components for Bot Development

| Component Name | ABI | Use Case |
|---------------|-----|----------|
| `component.value` | `getValue(uint256) view returns (uint256)` | Read inventory balances, stat values, config values |
| `component.id.kami.owns` | `getEntitiesWithValue(uint256) view returns (uint256[])` | List all Kamis owned by an account |
| `component.id.inventory.owns` | `getEntitiesWithValue(uint256) view returns (uint256[])` | List all inventory entries for a holder |
| `component.index.item` | `getValue(uint256) view returns (uint32)` | Read item index from an inventory/equipment entity |
| `component.state` | `getValue(uint256) view returns (string)` | Read entity state (e.g., Kami: RESTING, HARVESTING, DEAD) |

> **Stat component IDs** use the `component.stat.*` prefix: `component.stat.health`, `component.stat.power`, `component.stat.harmony`, `component.stat.violence`, `component.stat.slots`, `component.stat.stamina`. These are `BareComponent` types — `getEntitiesWithValue()` is not available on them; use `getValue(entityId)` to read the packed `Stat` struct directly. For most use cases, prefer the [GetterSystem](#getter-system) which returns decoded stats.

### Reading Inventory Balance

```javascript
// Check how many of a specific item you hold
const VALUE_ABI = ["function getValue(uint256 entity) view returns (uint256)"];
const valueAddr = await getComponentAddress("component.value");
const valueComponent = new ethers.Contract(valueAddr, VALUE_ABI, provider);

// Compute the inventory entity ID (see Entity Discovery)
const accountId = BigInt(ownerAddress);
const musuInventoryId = BigInt(
  ethers.keccak256(
    ethers.solidityPacked(
      ["string", "uint256", "uint32"],
      ["inventory.instance", accountId, 1] // item index 1 = MUSU
    )
  )
);

const balance = await valueComponent.getValue(musuInventoryId);
console.log("MUSU balance:", balance.toString());
```

### Enumerating Owned Kamis

```javascript
// List all Kamis owned by your account
const OWNS_KAMI_ABI = ["function getEntitiesWithValue(uint256) view returns (uint256[])"];
const ownsKamiAddr = await getComponentAddress("component.id.kami.owns");
const ownsKami = new ethers.Contract(ownsKamiAddr, OWNS_KAMI_ABI, provider);

const accountId = BigInt(ownerAddress);
const kamiEntityIds = await ownsKami.getEntitiesWithValue(accountId);
console.log("Owned Kamis:", kamiEntityIds.length);

// Get details for each Kami
const getter = new ethers.Contract(getterSystemAddr, GETTER_ABI, provider);
for (const kamiId of kamiEntityIds) {
  const data = await getter.getKami(kamiId);
  console.log(`Kami #${data.index}: ${data.name} (${data.state})`);
}
```

### Reading Config Values

Config values are stored in the **ValueComponent** (`component.value`), not in a separate config component. The entity ID for each config is derived by hashing the prefix `"is.config"` with the config name:

```javascript
// Config values are stored in ValueComponent, keyed by keccak256("is.config", name)
const VALUE_ABI = ["function getValue(uint256 entity) view returns (uint256)"];
const valueAddr = await getComponentAddress("component.value");
const valueComp = new ethers.Contract(valueAddr, VALUE_ABI, provider);

// Read a config value
const configEntityId = ethers.keccak256(
  ethers.solidityPacked(["string", "string"], ["is.config", "KAMI_MARKET_VAULT"])
);
const rawValue = await valueComp.getValue(configEntityId);
const vaultAddress = ethers.toBeHex(rawValue, 20); // for address configs
console.log("KamiMarketVault:", vaultAddress);
```

> **Note:** Component names use lowercase dot notation (e.g., `component.value`). The ABI for most components includes `getValue(uint256)` for single-entity reads and `getEntitiesWithValue(uint256)` for reverse lookups (finding all entities with a given value).

---

## Related Pages

- [Live Addresses](addresses.md) — Core contract addresses
- [Player API Overview](sdk-setup.md) — How to call systems
- [Architecture Overview](architecture.md) — MUD ECS model

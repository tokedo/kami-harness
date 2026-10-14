> **Doc Class:** Core Resource
> **Canonical Source:** Kamigotchi on-chain contracts on Yominet and the official repository (`Asphodel-OS/kamigotchi-open`, the public mirror of the studio's development repo).
> **Freshness Rule:** Verify mutable values against canonical sources before merge.

# Account

Account functions handle player registration, room movement, profile settings, and chat.

---

## register()

Register a new Kamigotchi account.

| Property | Value |
|----------|-------|
| **System ID** | `system.account.register` |
| **Wallet** | 🔐 Owner |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `operatorAddress` | `address` | The operator wallet address for in-game transactions |
| `name` | `string` | Display name for the account |

### Description

Creates a new account in the game world. Must be called from the **owner wallet**. The `operatorAddress` is the delegated wallet that will handle routine gameplay transactions (moving, chatting, trading, etc.).

This is typically the first function a new player calls.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

// Must use OWNER wallet
const ABI = [
  "function executeTyped(address operatorAddress, string name) returns (bytes)",
];
const system = await getSystem("system.account.register", ABI, ownerSigner);

const operatorAddr = "0x...YOUR_OPERATOR_WALLET_ADDRESS...";
const tx = await system.executeTyped(operatorAddr, "PlayerOne");
await tx.wait();
console.log("Account registered!");
```

### Notes

- Each owner wallet can only register **one account**.
- **Idempotency check:** To avoid the `"Account: exists for Owner"` revert on restart, check registration status first:
  ```javascript
  const getter = new ethers.Contract(getterAddr, GETTER_ABI, provider);
  const accountId = BigInt(ownerSigner.address);
  try {
    const data = await getter.getAccount(accountId);
    if (data.name !== "") {
      console.log("Already registered as:", data.name);
      // Skip registration
    }
  } catch (_) {
    // Not registered — proceed with register()
  }
  ```
- **Name format:** Names are validated by **byte length** (1-16 bytes), not character count. Multi-byte UTF-8 characters (e.g., emoji, CJK) consume more than 1 byte each. Stick to ASCII alphanumeric characters for predictable length. Names must be unique across all accounts.
- Practical rule: the contract reverts if name bytes are `>= 16`, so use **1-15 bytes**.
  ```javascript
  const name = "MyBot01";
  const nameBytes = ethers.toUtf8Bytes(name).length;
  if (nameBytes < 1 || nameBytes > 15) {
    throw new Error(`Invalid name byte length: ${nameBytes}`);
  }
  ```
- **Operator address reuse:** Each operator address can only be assigned to one account. Using the same operator key for two accounts will revert with `"Account: exists for Operator"`.
- The operator wallet can be changed later with `set.operator()`.
- In the official client, Privy creates and manages the operator wallet automatically.
- **Starting room:** New accounts are placed in **Room 1** (Misty Riverside). The contract sets `IndexRoomComponent` to `1` in `LibAccount.create()`.
- **Stamina config** (`ACCOUNT_STAMINA` on-chain config array):
  - Index 0 = **Base stamina**: `100` (max stamina for a new account)
  - Index 1 = **Recovery period**: `60` seconds per 1 stamina point recovered
  - Index 2 = Move cost (per room move)
  - Index 3 = XP per move
- **Stamina formula**: `currentStamina = min(total, sync + floor((now - lastActionTime) / recoveryPeriod))`

---

## move()

Move the account to a different room.

| Property | Value |
|----------|-------|
| **System ID** | `system.account.move` |
| **Wallet** | 🎮 Operator |
| **Gas** | **1,200,000** (hardcoded upper bound) |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `roomIndex` | `uint32` | Index of the target room |

### Description

Moves the player's account to the specified room. Rooms contain harvest nodes, NPCs, merchants, and other players. Some rooms have **gates** that require conditions to enter (hence the high gas limit).

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(uint32 roomIndex) returns (bytes)"];
const system = await getSystem("system.account.move", ABI, operatorSigner);

const tx = await system.executeTyped(targetRoomIndex, {
  gasLimit: 1_200_000, // Required — rooms with gates need extra gas
});
await tx.wait();
console.log("Moved to room", targetRoomIndex);
```

### Notes

- Gas limit of 1,200,000 is an upper bound. Rooms without gates cost less, but it's safe to always use this limit.
- If the room state doesn't update after moving, use [echo.room()](echo.md) to force-emit data.

#### Room Connectivity

Players **cannot** move to any arbitrary room — movement is restricted to **connected rooms**:

1. **Adjacent rooms:** Rooms whose on-chain `Location` coordinates (x, y, z) differ by exactly 1 on a single axis (x or y) with the same z. This is standard grid adjacency — `LibRoom.isAdjacent()` checks `|Δx| == 1, Δy == 0` or `|Δx| == 0, |Δy| == 1`, same z-level.
2. **Special exits:** Some rooms have an `ExitsComponent` listing additional room indices that can be reached regardless of coordinate adjacency (e.g., portals like Room 11 → Room 15, or Room 72 → Room 88). These are the "Exits" listed in the [Room table](../game-data.md#rooms).
3. **Access gates:** Even if a room is reachable, it may have **gate conditions** that must be met (e.g., quest completion, owning a specific item). If conditions fail, the move reverts with `"AccMove: inaccessible room"`.

The move system (`AccountMoveSystem`) checks reachability first (`LibRoom.isReachable`), then accessibility (`LibRoom.isAccessible`), then deducts stamina. Each move costs stamina (configured via `ACCOUNT_STAMINA` config index 2) and grants XP (config index 3).

> **Stamina:** Each move costs stamina and grants XP. Current stamina is readable via `getAccount(accountId).currStamina`. Stamina regenerates over time on-chain. If stamina reaches 0, moves will revert. Check stamina before moving in bot loops.

---

## chat.send()

Send a chat message in the current room.

| Property | Value |
|----------|-------|
| **System ID** | `system.chat` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `message` | `string` | The chat message to send |

### Description

Sends a text message visible to all players in the same room. Messages are emitted as events and picked up by the indexer.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(string message) returns (bytes)"];
const system = await getSystem("system.chat", ABI, operatorSigner);

const tx = await system.executeTyped("Hello world!");
await tx.wait();
```

### Notes

- There is no explicit message length limit in the `ChatSystem` contract — messages are arbitrary strings. Practical limits are imposed by block gas limits.
- **Conditional requirements:** The system checks configurable requirements via `LibConditional` before allowing a message to be sent. If conditions aren't met, the transaction reverts with `"can't send messages"`. Admin-configured prerequisites may include room requirements or item ownership. These conditions can change without a contract upgrade.
- Messages are on-chain and public — they cost gas (minimal on Yominet, flat 0.0025 gwei).

---

## set.bio()

Set the account's bio / description.

| Property | Value |
|----------|-------|
| **System ID** | `system.account.set.bio` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `bio` | `string` | The bio text |

### Description

Updates the player's profile bio. Visible to other players when inspecting the account.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(string bio) returns (bytes)"];
const system = await getSystem("system.account.set.bio", ABI, operatorSigner);

const tx = await system.executeTyped("Kami breeder & harvesting enthusiast 🌾");
await tx.wait();
```

### Notes

- Bio can be at most 140 bytes. Exceeding 140 bytes reverts with `"Account: bio cannot exceed 140chars"`.

---

## set.pfp()

Set profile picture to an owned Kami.

| Property | Value |
|----------|-------|
| **System ID** | `system.account.set.pfp` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `kamiID` | `uint256` | Entity ID of the Kami to use as profile picture |

### Description

Sets the player's profile picture to the visual of a Kami they own.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(uint256 kamiID) returns (bytes)"];
const system = await getSystem("system.account.set.pfp", ABI, operatorSigner);

const tx = await system.executeTyped(favoriteKamiId);
await tx.wait();
```

### Notes

- The Kami must be owned by the caller's account. If not, the transaction reverts with `"kami not urs"`.

---

## set.name()

Rename the account.

| Property | Value |
|----------|-------|
| **System ID** | `system.account.set.name` |
| **Wallet** | 🔐 Owner |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `name` | `string` | New account name |

### Description

Changes the player's display name. Must be called from the owner wallet.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

// Must use OWNER wallet
const ABI = ["function executeTyped(string name) returns (bytes)"];
const system = await getSystem("system.account.set.name", ABI, ownerSigner);

const tx = await system.executeTyped("NewPlayerName");
await tx.wait();
```

### Notes

- Same validation rules as registration: names must be 1-16 bytes, non-empty, and unique across all accounts.
- Reverts: `"Account: name cannot be empty"`, `"Account: name must be < 16chars"`, `"Account: name taken"`.

---

## set.operator()

Update the operator wallet.

| Property | Value |
|----------|-------|
| **System ID** | `system.account.set.operator` |
| **Wallet** | 🔐 Owner |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `operatorAddress` | `address` | New operator wallet address |

### Description

Changes the delegated operator wallet. The previous operator wallet will no longer be able to perform in-game actions. Use this if your operator wallet is compromised or you want to switch to a new session key.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

// Must use OWNER wallet
const ABI = ["function executeTyped(address operatorAddress) returns (bytes)"];
const system = await getSystem("system.account.set.operator", ABI, ownerSigner);

const newOperator = "0x...NEW_OPERATOR_ADDRESS...";
const tx = await system.executeTyped(newOperator);
await tx.wait();
console.log("Operator updated");
```

### Notes

- The old operator wallet immediately loses access.
- Make sure the new operator wallet has $ETH for gas.

---

## use.item()

Use a consumable item on the account.

| Property | Value |
|----------|-------|
| **System ID** | `system.account.use.item` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `itemIndex` | `uint32` | Index of the item to use |
| `amt` | `uint256` | Amount of the item to consume |

### Description

Uses consumable items on the player's account (stamina potions, XP potions, etc.). The item must have shape "ACCOUNT" and meet "USE" requirements. Syncs stamina before applying the item effect.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(uint32 itemIndex, uint256 amt) returns (bytes)"];
const system = await getSystem("system.account.use.item", ABI, operatorSigner);

const tx = await system.executeTyped(itemIndex, 1n);
await tx.wait();
console.log("Item used on account!");
```

---

## Related Pages

- [Echo](echo.md) — Force-emit room/kami data after actions
- [Social / Friends](social.md) — Friend requests and blocking
- [Items & Crafting](items-and-crafting.md) — Item usage from inventory
- [Quests](quests.md) — Quest management
- [Trading](trading.md) — Player-to-player trading

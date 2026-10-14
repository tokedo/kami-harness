> **Doc Class:** Core Resource
> **Canonical Source:** Kamigotchi on-chain contracts on Yominet and the official repository (`Asphodel-OS/kamigotchi-open`, the public mirror of the studio's development repo).
> **Freshness Rule:** Verify mutable values against canonical sources before merge.

# Social / Friends

The social system lets players send friend requests, manage friendships, and block other accounts.

---

## friend.request()

Send a friend request.

| Property | Value |
|----------|-------|
| **System ID** | `system.friend.request` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `targetAddr` | `address` | **Owner address** of the target account |

### Description

Sends a friend request to another player by their owner wallet address. The target must accept the request for the friendship to be established.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(address targetAddr) returns (bytes)"];
const system = await getSystem("system.friend.request", ABI, operatorSigner);

const targetOwnerAddress = "0x...TARGET_OWNER_ADDRESS...";
const tx = await system.executeTyped(targetOwnerAddress);
await tx.wait();
console.log("Friend request sent!");
```

### Notes

- Uses the target's **owner wallet address**, not operator address.
- Cannot send a request to yourself — reverts with `"FriendRequest: cannot fren self"`.
- Cannot send a request to an account that has blocked you.
- Duplicate requests to the same account will revert.
- The target's pending inbound requests are capped by the `FRIENDS_REQUEST_LIMIT` config. If the target has too many pending requests, the transaction reverts with `"Max friend requests reached"`.
- Common reverts: `"Friend: already friends"`, `"Friend: already pending"`, `"Friend: blocked"`.

---

## friend.accept()

Accept a friend request.

| Property | Value |
|----------|-------|
| **System ID** | `system.friend.accept` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `requestID` | `uint256` | Entity ID of the friend request |

### Description

Accepts an incoming friend request. Both accounts become friends, enabling features like targeted trades.

### Notes

- Total friends per account are capped by the `FRIENDS_BASE_LIMIT` config (plus any bonus). If accepting would exceed the limit, the transaction reverts.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(uint256 requestID) returns (bytes)"];
const system = await getSystem("system.friend.accept", ABI, operatorSigner);

const tx = await system.executeTyped(requestEntityId);
await tx.wait();
console.log("Friend request accepted!");
```

---

## friend.cancel()

Cancel a request, remove a friend, or remove a block.

| Property | Value |
|----------|-------|
| **System ID** | `system.friend.cancel` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `entityID` | `uint256` | Entity ID of the friend/request/block relationship |

### Description

A multipurpose function that handles four scenarios based on the entity's current state:

| State | Action |
|-------|--------|
| Pending request (outgoing) | Cancels the friend request |
| Pending request (incoming) | Declines the friend request |
| Active friendship | Removes the friend |
| Active block | Unblocks the account |

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(uint256 entityID) returns (bytes)"];
const system = await getSystem("system.friend.cancel", ABI, operatorSigner);

// Cancel a pending request, remove a friend, or unblock
const tx = await system.executeTyped(relationshipEntityId);
await tx.wait();
console.log("Relationship removed");
```

### Notes

- The `entityID` must be a relationship entity that involves the caller's account.
- This is the only way to unfriend someone or unblock after blocking.

---

## friend.block()

Block an account.

| Property | Value |
|----------|-------|
| **System ID** | `system.friend.block` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `targetAddr` | `address` | **Owner address** of the account to block |

### Description

Blocks another player. Blocked accounts cannot send friend requests to the blocker. If a friendship exists, it is removed.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = ["function executeTyped(address targetAddr) returns (bytes)"];
const system = await getSystem("system.friend.block", ABI, operatorSigner);

const tx = await system.executeTyped(targetOwnerAddress);
await tx.wait();
console.log("Account blocked");
```

### Notes

- Uses the target's **owner wallet address**.
- To unblock, use `friend.cancel()` with the block entity ID.
- Blocking is one-directional — the blocked party can still see the blocker's public data.

---

## Relationship Lifecycle

```
                    friend.request()
  No Relation ──────────────────────▶ Pending Request
       ▲                                    │
       │                                    ├─── friend.accept() ──▶ Friends
       │                                    │                          │
       │                                    └─── friend.cancel() ─────┘
       │                                         (cancel request)      │
       │                                                               │
       └──────────────── friend.cancel() ─────────────────────────────┘
                          (remove friend)

  Any State ─── friend.block() ──▶ Blocked ─── friend.cancel() ──▶ No Relation
```

---

## Related Pages

- [Account](account.md) — Account registration and settings
- [Trading](trading.md) — Trading with friends using `targetID`

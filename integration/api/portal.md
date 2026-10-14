> **Doc Class:** Core Resource
> **Canonical Source:** Kamigotchi on-chain contracts on Yominet and the official repository (`Asphodel-OS/kamigotchi-open`, the public mirror of the studio's development repo).
> **Freshness Rule:** Verify mutable values against canonical sources before merge.

# Portal (ERC721 / ERC20)

The portal system bridges assets between on-chain wallets and the in-game world. Stake NFTs into the game and manage ERC-20 token deposits/withdrawals.

> **📌 Feb 2026 Update:** The Kami NFT Portal has been simplified to **import-only**. Unstaking (exporting Kamis back to your wallet) has been removed from the UI. The portal now focuses on staking Kamis into the game world.

---

## ERC721 — Kami NFT Portal

### ERC721.kami.stake()

Deposit a Kami NFT from your wallet into the game world.

| Property | Value |
|----------|-------|
| **System ID** | `system.kami721.stake` |
| **Wallet** | 🔐 Owner |
| **Gas** | Default |

#### Parameters

| Name | Type | Description |
|------|------|-------------|
| `tokenIndex` | `uint32` | Index/token ID of the Kami NFT |

#### Description

Stakes a Kami NFT from the owner's wallet into the game world. The NFT is transferred to the World contract, and a corresponding Kami entity is created in-game. The Kami can then be used for harvesting, combat, and other activities.

#### Code Example

```javascript
import { ethers } from "ethers";
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const KAMI721_ADDRESS = "0x5d4376b62fa8ac16dfabe6a9861e11c33a48c677";
const WORLD_ADDRESS = "0x2729174c265dbBd8416C6449E0E813E88f43D0E7";

// Step 1: Approve the World contract to transfer your NFT
const kami721 = new ethers.Contract(
  KAMI721_ADDRESS,
  ["function approve(address to, uint256 tokenId)"],
  ownerSigner
);
await (await kami721.approve(WORLD_ADDRESS, tokenId)).wait();

// Step 2: Stake into game
const ABI = ["function executeTyped(uint32 tokenIndex) returns (bytes)"];
const system = await getSystem("system.kami721.stake", ABI, ownerSigner);

const tx = await system.executeTyped(tokenId);
await tx.wait();
console.log("Kami staked into game world!");
```

#### Notes

- **Prerequisite:** Your account must be in **Room 12 (Scrap Confluence)**. Call `account.move(12)` first.
- **Requires NFT approval** before staking — approve the World contract as the operator.
- Must use the **owner wallet** (the one that holds the NFT).
- Active marketplace listings for the Kami are automatically cancelled during staking.
- For batch staking, see `ERC721.kami.batch.stake()` below.

---

### ~~ERC721.kami.unstake()~~ — Removed

> **⚠️ As of the Feb 2026 patch, the Kami Portal is import-only.** Unstaking (exporting Kamis back to your wallet as NFTs) has been removed from the client. The on-chain `system.kami721.unstake` contract still exists but is no longer exposed in the game UI. The portal now only supports importing (staking) Kamis into the game world.

---

### ERC721.kami.batch.stake()

Batch stake multiple Kami NFTs.

| Property | Value |
|----------|-------|
| **System ID** | `system.kami721.stake` |
| **Wallet** | 🔐 Owner |
| **Gas** | Default |

#### Parameters

| Name | Type | Description |
|------|------|-------------|
| `tokenIndices` | `uint32[]` | Array of Kami token IDs to stake |

#### Code Example

```javascript
import { ethers } from "ethers";
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const KAMI721_ADDRESS = "0x5d4376b62fa8ac16dfabe6a9861e11c33a48c677";
const WORLD_ADDRESS = "0x2729174c265dbBd8416C6449E0E813E88f43D0E7";

// Approve all at once
const kami721 = new ethers.Contract(
  KAMI721_ADDRESS,
  ["function setApprovalForAll(address operator, bool approved)"],
  ownerSigner
);
await (await kami721.setApprovalForAll(WORLD_ADDRESS, true)).wait();

// Batch stake — uses executeBatch(), NOT executeTyped
const ABI = ["function executeBatch(uint32[] tokenIndices)"];
const system = await getSystem("system.kami721.stake", ABI, ownerSigner);

const tx = await system.executeBatch([tokenId1, tokenId2, tokenId3]);
await tx.wait();
```

---

### ERC721.kami.batch.unstake()

Batch unstake multiple Kamis.

| Property | Value |
|----------|-------|
| **System ID** | `system.kami721.unstake` |
| **Wallet** | 🔐 Owner |
| **Gas** | Default |

#### Parameters

| Name | Type | Description |
|------|------|-------------|
| `tokenIndices` | `uint32[]` | Array of in-game Kami indices to unstake |

#### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

// Batch unstake — uses executeBatch(), NOT executeTyped
const ABI = ["function executeBatch(uint32[] tokenIndices)"];
const system = await getSystem("system.kami721.unstake", ABI, ownerSigner);

const tx = await system.executeBatch([kamiIndex1, kamiIndex2, kamiIndex3]);
await tx.wait();
```

---

### ERC721.kami.batch.transfer()

Batch transfer Kamis to a single address.

| Property | Value |
|----------|-------|
| **System ID** | `system.kami721.transfer` |
| **Wallet** | 🔐 Owner |
| **Gas** | Default |

#### Parameters

| Name | Type | Description |
|------|------|-------------|
| `tokenIndices` | `uint256[]` | Array of Kami token indices to transfer |
| `to` | `address` | Recipient address |

#### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

// batchTransfer() is a named function, NOT executeTyped
const ABI = [
  "function batchTransfer(uint256[] tokenIndices, address to)",
];
const system = await getSystem("system.kami721.transfer", ABI, ownerSigner);

const tx = await system.batchTransfer(
  [kamiIndex1, kamiIndex2],
  recipientAddress
);
await tx.wait();
```

---

### ERC721.kami.batch.transferToMultiple()

Batch transfer Kamis to multiple addresses (1:1 mapping).

| Property | Value |
|----------|-------|
| **System ID** | `system.kami721.transfer` |
| **Wallet** | 🔐 Owner |
| **Gas** | Default |

#### Parameters

| Name | Type | Description |
|------|------|-------------|
| `tokenIndices` | `uint256[]` | Array of Kami token indices |
| `to` | `address[]` | Array of recipient addresses (matching length) |

#### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

// batchTransferToMany() is a named function, NOT executeTyped
const ABI = [
  "function batchTransferToMany(uint256[] tokenIndices, address[] to)",
];
const system = await getSystem("system.kami721.transfer", ABI, ownerSigner);

const tx = await system.batchTransferToMany(
  [kamiIndex1, kamiIndex2],
  [recipientAddr1, recipientAddr2]
);
await tx.wait();
```

---

### ERC721.kami.isInWorld()

Check whether a Kami NFT is currently staked in the game world.

| Property | Value |
|----------|-------|
| **System ID** | `system.Kami721.IsInWorld` |
| **Wallet** | N/A (view function) |
| **Gas** | None (read-only) |

#### Parameters

| Name | Type | Description |
|------|------|-------------|
| `petIndex` | `uint256` | The ERC-721 token index of the Kami |

#### Description

Returns `true` if the Kami identified by `petIndex` is currently staked in the game world, `false` otherwise. This is a view-only system -- it costs no gas and can be called by anyone. Internally it converts the `petIndex` to an entity ID via `LibKami.getByIndex` and checks world membership via `LibKami.isInWorld`.

> **Important:** `execute()` and `executeTyped()` both revert on this system. Use the named `isInWorld()` function directly.

#### Code Example

```javascript
import { ethers } from "ethers";
import { getSystemAddress } from "./kamigotchi.js";

const provider = new ethers.JsonRpcProvider(
  "https://jsonrpc-yominet-1.anvil.asia-southeast.initia.xyz"
);

const ABI = ["function isInWorld(uint256 petIndex) view returns (bool)"];
const addr = await getSystemAddress("system.Kami721.IsInWorld");
const isInWorldSystem = new ethers.Contract(addr, ABI, provider);

const staked = await isInWorldSystem.isInWorld(42); // petIndex, not entity ID
console.log("Kami #42 in world:", staked); // true or false
```

#### Notes

- **View only** -- no transaction or signer required; use a provider.
- Takes the **petIndex** (ERC-721 token index), not the internal entity ID.
- Useful for checking stake status before attempting portal operations.

---

### ERC721.kami.tokenURI()

Retrieve the on-chain metadata URI for a Kami NFT.

| Property | Value |
|----------|-------|
| **System ID** | `system.Kami721.Metadata` |
| **Wallet** | N/A (view function) |
| **Gas** | None (read-only) |

#### Parameters

| Name | Type | Description |
|------|------|-------------|
| `petIndex` | `uint256` | The ERC-721 token index of the Kami |

#### Description

Returns a base64-encoded JSON metadata string for the Kami identified by `petIndex`. The metadata is generated on-chain via `LibKami721.getJsonBase64`. This system is structured as upgradeable -- the metadata logic lives in a system contract rather than the NFT contract itself.

> **Important:** `execute()` and `executeTyped()` both revert on this system. Use the named `tokenURI()` function directly.

#### Code Example

```javascript
import { ethers } from "ethers";
import { getSystemAddress } from "./kamigotchi.js";

const provider = new ethers.JsonRpcProvider(
  "https://jsonrpc-yominet-1.anvil.asia-southeast.initia.xyz"
);

const ABI = ["function tokenURI(uint256 petIndex) view returns (string)"];
const addr = await getSystemAddress("system.Kami721.Metadata");
const metadataSystem = new ethers.Contract(addr, ABI, provider);

const uri = await metadataSystem.tokenURI(42); // petIndex, not entity ID
console.log("Metadata URI:", uri);
// Returns a data URI: data:application/json;base64,...
// Decode the base64 payload to get the JSON metadata object.
```

#### Notes

- **View only** -- no transaction or signer required; use a provider.
- Takes the **petIndex** (ERC-721 token index), not the internal entity ID.
- Returns a `data:application/json;base64,...` URI. Decode the base64 portion to get the JSON metadata.
- Metadata is generated on-chain and may change if the system contract is upgraded.

---

## ERC20 — Token Portal

### ERC20.deposit()

Deposit an ERC-20 token into the game world.

| Property | Value |
|----------|-------|
| **System ID** | `system.erc20.portal` |
| **Wallet** | 🔐 Owner |
| **Gas** | Default |

#### Parameters

| Name | Type | Description |
|------|------|-------------|
| `itemIndex` | `uint32` | Game item index representing the ERC-20 token |
| `itemAmt` | `uint256` | Amount to deposit |

#### Description

Deposits ERC-20 tokens from the owner's wallet into the game world as in-game items. Requires prior ERC-20 approval.

#### Code Example

```javascript
import { ethers } from "ethers";
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ONYX_ADDRESS = "0x4BaDFb501Ab304fF11217C44702bb9E9732E7CF4";
const WORLD_ADDRESS = "0x2729174c265dbBd8416C6449E0E813E88f43D0E7";
const onyxItemIndex = 100;
const depositAmount = ethers.parseUnits("10", 18); // 10 ONYX

// Step 1: Approve ERC-20 spend
const onyx = new ethers.Contract(
  ONYX_ADDRESS,
  ["function approve(address spender, uint256 amount) returns (bool)"],
  ownerSigner
);
await (await onyx.approve(WORLD_ADDRESS, depositAmount)).wait();

// Step 2: Deposit into game — deposit() is a named function, NOT executeTyped
const ABI = [
  "function deposit(uint32 itemIndex, uint256 itemAmt)",
];
const system = await getSystem("system.erc20.portal", ABI, ownerSigner);

const tx = await system.deposit(onyxItemIndex, depositAmount);
await tx.wait();
console.log("ONYX deposited into game world!");
```

#### Notes

- The `itemIndex` maps an in-game item to a specific ERC-20 contract. The mapping is stored in the `TokenPortalSystem` contract's local storage (`itemAddrs` and `itemScales` mappings), initialized from the item registry. Items must be of type `"ERC20"`. The primary token is ONYX (item index 100). The conversion scale and token address are set per item via `setItem()` or `initItem()` admin calls. Set via registry — query the `TokenPortalSystem` contract for current item→ERC-20 mappings.
- `itemIndex = 100` is ONYX, while `itemIndex = 103` is the in-game ETH balance.
- Requires ERC-20 `approve()` before depositing.
- Prefer approving the exact deposit amount (or a tight cap) instead of unlimited allowances.

---

### ERC20.withdraw()

Withdraw ERC-20 tokens from the game world.

| Property | Value |
|----------|-------|
| **System ID** | `system.erc20.portal` |
| **Wallet** | 🔐 Owner |
| **Gas** | Default |

#### Parameters

| Name | Type | Description |
|------|------|-------------|
| `itemIndex` | `uint32` | Game item index representing the ERC-20 token |
| `itemAmt` | `uint256` | Amount to withdraw |

#### Description

Initiates a withdrawal of ERC-20 tokens from the game world back to the owner's wallet. Withdrawals have a **pending period** (configured per token via the `PORTAL_TOKEN_EXPORT_DELAY` config) before they can be claimed with `ERC20.claim()`. During the pending period, you can cancel the withdrawal with `ERC20.cancel()` to return the tokens to your in-game inventory.

#### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

// withdraw() is a named function, NOT executeTyped
const ABI = [
  "function withdraw(uint32 itemIndex, uint256 itemAmt) returns (uint256)",
];
const system = await getSystem("system.erc20.portal", ABI, ownerSigner);

const tx = await system.withdraw(onyxItemIndex, withdrawAmount);
await tx.wait();
console.log("Withdrawal initiated — use ERC20.claim() after the pending period.");
```

#### Capturing the Receipt ID

The `withdraw()` function returns a `uint256` receipt ID, but mined transactions don't expose return values in receipts. Capture it via event parsing:

```javascript
import { extractEntityIds } from "./event-helpers.js";

const withdrawTx = await system.withdraw(onyxItemIndex, withdrawAmount);
const withdrawReceipt = await withdrawTx.wait();
const receiptId = extractEntityIds(withdrawReceipt)[0];
console.log("Withdrawal receipt ID:", receiptId);
// Use this receiptId with claim() or cancel() after the pending period
```

See [Parsing Transaction Events](../entity-ids.md#parsing-transaction-events) for the `extractEntityIds()` helper.

---

### ERC20.claim()

Claim a pending ERC-20 withdrawal.

| Property | Value |
|----------|-------|
| **System ID** | `system.erc20.portal` |
| **Wallet** | 🔐 Owner |
| **Gas** | Default |

#### Parameters

| Name | Type | Description |
|------|------|-------------|
| `receiptID` | `uint256` | Entity ID of the withdrawal receipt |

#### Description

Claims a pending ERC-20 withdrawal after the required waiting period has elapsed. Tokens are transferred from the World contract to the owner's wallet.

#### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

// claim() is a named function, NOT executeTyped
const ABI = ["function claim(uint256 receiptID)"];
const system = await getSystem("system.erc20.portal", ABI, ownerSigner);

const tx = await system.claim(withdrawalReceiptId);
await tx.wait();
console.log("ERC-20 tokens claimed to wallet!");
```

---

### ERC20.cancel()

Cancel a pending ERC-20 withdrawal.

| Property | Value |
|----------|-------|
| **System ID** | `system.erc20.portal` |
| **Wallet** | 🔐 Owner |
| **Gas** | Default |

#### Parameters

| Name | Type | Description |
|------|------|-------------|
| `receiptID` | `uint256` | Entity ID of the withdrawal receipt |

#### Description

Cancels a pending withdrawal. The tokens are returned to the player's in-game inventory instead of being sent to the wallet. Note that the export tax charged during `withdraw()` is **not refunded** on cancellation.

#### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

// cancel() is a named function, NOT executeTyped
const ABI = ["function cancel(uint256 receiptID)"];
const system = await getSystem("system.erc20.portal", ABI, ownerSigner);

const tx = await system.cancel(withdrawalReceiptId);
await tx.wait();
console.log("Withdrawal cancelled — tokens returned to game inventory.");
```

---

## Portal Flow Summary

### ERC-721 (Kami NFTs)

```
  Wallet                              Game World
    │                                     │
    │── approve() + kami.stake() ────────▶ │  (NFT → Game Entity)
    │                                     │
    │◀──────────── kami.unstake() ─────── │  (Game Entity → NFT)
    │                                     │
    │── kami.batch.transfer() ──────────▶  │  (NFT wallet-to-wallet transfer)
```

### ERC-20 (Tokens)

```
  Wallet                              Game World
    │                                     │
    │── approve() + ERC20.deposit() ────▶ │  (Tokens → Items)
    │                                     │
    │◀── ERC20.withdraw() ────────────── │  (Items → Pending)
    │                                     │
    │◀── ERC20.claim() ──────────────── │  (Pending → Wallet)
    │                                     │
    │              ERC20.cancel() ──────▶ │  (Pending → Items)
```

---

## Related Pages

- [Kami](kami.md) — Managing staked Kamis
- [Minting](minting.md) — Minting new Kamis via gacha
- [Chain Configuration](../chain.md) — Network and token details
- [Live Addresses](../addresses.md) — Contract addresses for approvals

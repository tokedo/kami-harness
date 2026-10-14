> **Doc Class:** Core Resource
> **Canonical Source:** Kamigotchi on-chain contracts on Yominet and the official repository (`Asphodel-OS/kamigotchi-open`, the public mirror of the studio's development repo).
> **Freshness Rule:** Verify mutable values against canonical sources before merge.

# Chain Configuration

Kamigotchi is deployed on **Yominet**, an Initia L2 rollup built on the OP Stack with Celestia DA (Data Availability).

---

## Network Details

| Parameter | Value |
|-----------|-------|
| **Chain Name** | Yominet |
| **Chain ID (EVM)** | `428962654539583` |
| **RPC URL** | `https://jsonrpc-yominet-1.anvil.asia-southeast.initia.xyz` |
| **WebSocket RPC** | `wss://jsonrpc-ws-yominet-1.anvil.asia-southeast.initia.xyz` |
| **REST API** | `https://rest-yominet-1.anvil.asia-southeast.initia.xyz` |
| **Block Explorer** | [scan.initia.xyz/yominet-1](https://scan.initia.xyz/yominet-1) |
| **Gas Price** | Flat `0.0025 gwei` |
| **Native Token** | $ETH (bridged) |
| **Currency Symbol** | ETH |

---

## Adding Yominet to Your Wallet

### MetaMask (Manual)

1. Open MetaMask → Settings → Networks → Add Network
2. Fill in:
   - **Network Name:** Yominet
   - **RPC URL:** `https://jsonrpc-yominet-1.anvil.asia-southeast.initia.xyz`
   - **Chain ID:** `428962654539583`
   - **Currency Symbol:** ETH
   - **Block Explorer URL:** `https://scan.initia.xyz/yominet-1`
3. Click **Save**

### Programmatic (ethers.js v6)

```javascript
import { ethers } from "ethers";

const YOMINET = {
  chainId: 428962654539583,
  name: "Yominet",
};

const provider = new ethers.JsonRpcProvider(
  "https://jsonrpc-yominet-1.anvil.asia-southeast.initia.xyz",
  YOMINET
);
```

> **Note:** In ethers v6, pass `chainId` as a JavaScript number in the network object (not a `BigInt`).

### Supported Wallets

| Wallet | Supported |
|--------|-----------|
| MetaMask | ✅ |
| Rabby | ✅ |

---

## Bridging

ETH on Yominet is **bridged via LayerZero** from Ethereum, Base, or Arbitrum. Your **Owner wallet** needs ETH for gas and purchases. Browser players get an Operator wallet through Privy; agent bootstraps should derive a **distinct** operator wallet from the owner key and fund it before gameplay transactions.

> **There is no faucet.** You must bridge real ETH to Yominet to get gas tokens.

### Option 1: Kamigotchi In-Game Bridge (Recommended)

The Kamigotchi client includes a built-in bridge powered by the Initia bridge.

1. Open the Kamigotchi client
2. Go to **Settings > Bridge**
3. Select the amount of ETH to bridge from Arbitrum, Base, or Ethereum
4. Confirm the transaction in your wallet
5. Wait for the bridge to complete — funds arrive as native ETH on Yominet

This is the simplest option if you already have the Kamigotchi client running.

### Option 2: Initia Bridge

The [Initia Bridge](https://app.initia.xyz/?openBridge=true) supports bridging ETH to Yominet.

1. Go to the [Initia Bridge](https://app.initia.xyz/?openBridge=true)
2. Select **Yominet** as the destination chain
3. Enter the destination wallet address (your Owner wallet)
4. Send ETH from **Arbitrum**, **Base**, or **Ethereum** mainnet
5. Funds arrive as native ETH on Yominet

### Option 3: Base Agent Bootstrap Route

For agent flows that start with only ETH on Base, use the working bridge tooling in the Yominet bridge tooling. The only user-facing bridge inputs are the owner private key and bridge amount; the runtime derives the Yominet recipients from that key.

### Recommended Funding Amounts

For a new player, bridge **0.01 ETH**. Gas is extremely cheap (~0.001 ETH for thousands of transactions). The main ETH costs are:

- **KamiSwap purchases** — buying your first Kami on the [KamiSwap marketplace](api/marketplace.md) (paid in native ETH via `msg.value`)
- **Gacha tickets** — purchased with $MUSU via Dutch auction (see [Gacha / Minting](api/minting.md))

---

## Gas

Yominet uses a **flat gas price** of `0.0025 gwei` (`2500000 wei`). This is extremely low compared to Ethereum mainnet.

```javascript
// Gas is cheap — but some systems need hardcoded gas limits:
// - account.move() (system.account.move):              1,200,000 gas (rooms with gates)
// - harvest.liquidate() (system.harvest.liquidate):     7,500,000 gas
// - gacha.mint() (system.kami.gacha.mint):               4,000,000 + 3,000,000 per kami
```

> **Note:** Always set appropriate gas limits for high-compute operations. The flat gas price means cost is minimal, but gas **limits** still matter for complex system calls.

---

## Currencies: Native ETH vs WETH vs In-Game Currencies

Yominet has several distinct currency types. Understanding the differences is critical for bot development.

| Currency | Type | Where It Lives | Used For |
|----------|------|---------------|----------|
| **Native ETH** | Gas token | Wallet balance | Gas fees, KamiSwap marketplace listing buys (`msg.value`) |
| **WETH** | ERC-20 | Contract `0xE1Ff...2546` | ERC-20 approval flows such as marketplace offers and portal deposits |
| **In-game ETH** | Inventory item | In-game (item 103) | In-game ETH-denominated actions |
| **$MUSU** | Inventory item | In-game (item 1) | Merchant purchases, trade fees, NPC gifts, quest costs |
| **$ONYX** | ERC-20 | Contract `0x4BaD...7CF4` on Yominet | Bridged into game as Onyx Shards via portal. Also used directly for revive, rename (disabled), respec (disabled) |
| **Onyx Shards** | Inventory item | In-game (item 100) | In-game form of $ONYX. **1 ONYX = 100 Onyx Shards.** Deposited via `system.erc20.portal` |

> **Key distinction:** Bridge into Yominet ETH first and use that balance for gas plus native-ETH purchases such as `kamimarket.buy`. When a system needs ERC-20 approvals, interact with the local WETH contract. In-game ETH (item 103) is a separate inventory item created by depositing WETH through the portal.

---

## WETH (Wrapped ETH)

| Token | Contract Address |
|-------|-----------------|
| **Wrapped ETH (WETH)** | [`0xE1Ff7038eAAAF027031688E1535a055B2Bac2546`](https://scan.initia.xyz/yominet-1/address/0xE1Ff7038eAAAF027031688E1535a055B2Bac2546) |

WETH is needed for marketplace offers (which use ERC-20 approvals).

> **How to think about WETH on Yominet:** The local contract at `0xE1Ff...2546` is the ERC-20 interface for Yominet ETH. If you only need gas or native-ETH purchases, bridged ETH is enough. If you need approval-based flows, call `deposit()` to wrap ETH into the ERC-20 interface and `withdraw()` to unwrap it back.

### Wrapping and Unwrapping ETH

```javascript
const WETH_ADDRESS = "0xE1Ff7038eAAAF027031688E1535a055B2Bac2546";
const WETH_ABI = ["function deposit() payable", "function withdraw(uint256)"];
const weth = new ethers.Contract(WETH_ADDRESS, WETH_ABI, ownerSigner);

// Wrap native ETH into WETH
const tx = await weth.deposit({ value: ethers.parseEther("0.1") });
await tx.wait();

// Unwrap WETH back to native ETH
const unwrapTx = await weth.withdraw(ethers.parseEther("0.1"));
await unwrapTx.wait();
```

---

## $MUSU (In-Game Currency)

$MUSU is the **primary in-game currency** (item index 1). It is **not** an ERC-20 token — it exists only as an in-game inventory item.

### Earning $MUSU

- Harvesting at resource nodes (primary source)
- Player-to-player trading

### $MUSU Uses

- Merchant purchases from in-game shops
- Used to purchase gacha tickets (via Dutch auction)
- Used in KWOB (Kamigotchi World Order Book) — the player-to-player trading system

> **Note:** $MUSU cannot be transferred on-chain as a token. It can only be traded between players using the in-game [Trading](api/trading.md) system.

---

## Game Currency: $ONYX

$ONYX is the in-game ERC-20 token used for premium operations.

| Contract Address |
|-----------------|
| [`0x4BaDFb501Ab304fF11217C44702bb9E9732E7CF4`](https://scan.initia.xyz/yominet-1/address/0x4BaDFb501Ab304fF11217C44702bb9E9732E7CF4) |

### $ONYX Uses

- `onyx.revive(kamiIndex)` — Revive a dead Kami (costs 33 ONYX) *(active)*
- `onyx.rename(kamiID, name)` — Rename a Kami (costs 5000 ONYX) *(currently disabled on production)*
- `onyx.respec(kamiID)` — Respec a Kami's skills (costs 10000 ONYX) *(currently disabled on production)*

> **Note:** Most $ONYX operations require the **Owner wallet** — except `onyx.revive()`, which uses the **Operator wallet**.

### Acquiring $ONYX

- **Trading on Baseline Markets** — $ONYX can be bought and sold on [Baseline Markets](https://legacy.baseline.markets). Search for the ONYX token on Yominet.
- **Player-to-player trading** — Use the in-game [Trading](api/trading.md) system to exchange items or $MUSU for $ONYX with other players.

---

## Onyx Shards

**Onyx Shards** (item index 100) are the in-game form of $ONYX. When $ONYX (ERC-20) is deposited into the game via the [ERC20 Portal](api/portal.md), it converts to Onyx Shards at a rate of **1 ONYX = 100 Onyx Shards**. Conversely, withdrawing Onyx Shards via the portal converts them back to $ONYX at the same rate. Onyx Shards can also be obtained through gameplay activities (e.g., trading with other players).

---

## WebSocket Event Subscription

Yominet exposes a WebSocket RPC endpoint for real-time event streaming. This is useful for bots that need to react to on-chain events (e.g., harvest completions, marketplace listings, droptable reveals).

### Connecting with ethers.js v6

```javascript
import { ethers } from "ethers";

const WS_URL = "wss://jsonrpc-ws-yominet-1.anvil.asia-southeast.initia.xyz";
const WORLD_ADDRESS = "0x2729174c265dbBd8416C6449E0E813E88f43D0E7";

const wsProvider = new ethers.WebSocketProvider(WS_URL, {
  chainId: 428962654539583,
  name: "Yominet",
});

// Subscribe to Store_SetRecord events (MUD's universal state-change event)
// This fires whenever any component value is created or updated on-chain.
const STORE_SET_RECORD_TOPIC = ethers.id(
  "Store_SetRecord(bytes32,bytes32[],bytes,bytes32)"
);

wsProvider.on(
  {
    address: WORLD_ADDRESS,
    topics: [STORE_SET_RECORD_TOPIC],
  },
  (log) => {
    console.log("Store_SetRecord event:");
    console.log("  Block:", log.blockNumber);
    console.log("  Tx:", log.transactionHash);
    console.log("  Data:", log.data.slice(0, 66) + "...");
    // Decode further using ethers.AbiCoder — see Entity Discovery for patterns
  }
);

console.log("Listening for Store_SetRecord events...");

// Handle disconnects
wsProvider.websocket.on("close", () => {
  console.log("WebSocket disconnected — reconnecting...");
  // Implement your reconnection logic here
});
```

### Filtering by Table ID

To listen for specific component changes (e.g., only inventory updates), filter on `topics[1]` which contains the `tableId` (the keccak256 hash of the component name):

```javascript
// Listen only for ValueComponent changes (inventory balance updates)
const VALUE_TABLE_ID = ethers.keccak256(ethers.toUtf8Bytes("component.value"));

wsProvider.on(
  {
    address: WORLD_ADDRESS,
    topics: [STORE_SET_RECORD_TOPIC, VALUE_TABLE_ID],
  },
  (log) => {
    console.log("Inventory/value change detected:", log.transactionHash);
  }
);
```

> **Tip:** WebSocket connections may drop under load. Always implement reconnection logic. For high-reliability setups, consider polling via HTTP RPC as a fallback. See [Entity Discovery](entity-ids.md) for details on decoding entity IDs from event logs.

---

## Infrastructure

| Layer | Technology |
|-------|-----------|
| Execution | OP Stack (Optimistic Rollup) |
| Data Availability | Celestia |
| Settlement | Initia L1 |
| Smart Contracts | Solidity (MUD ECS framework) |

---

## Related Pages

- [Architecture Overview](architecture.md) — How the MUD ECS model works
- [Live Addresses](addresses.md) — All deployed contract addresses
- [Integration Guide](guide.md) — Getting started for developers

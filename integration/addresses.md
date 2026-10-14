> **Doc Class:** Core Resource
> **Canonical Source:** Kamigotchi on-chain contracts on Yominet and the official repository (`Asphodel-OS/kamigotchi-open`, the public mirror of the studio's development repo).
> **Freshness Rule:** Verify mutable values against canonical sources before merge.

# Live Contract Addresses

All core Kamigotchi contracts deployed on Yominet.

---

## Core Contracts

| Contract | Address | Explorer |
|----------|---------|----------|
| **World** | `0x2729174c265dbBd8416C6449E0E813E88f43D0E7` | [View](https://scan.initia.xyz/yominet-1/address/0x2729174c265dbBd8416C6449E0E813E88f43D0E7) |
| **Kami721 (NFT)** | `0x5d4376b62fa8ac16dfabe6a9861e11c33a48c677` | [View](https://scan.initia.xyz/yominet-1/address/0x5d4376b62fa8ac16dfabe6a9861e11c33a48c677) |
| **ONYX Token** | `0x4BaDFb501Ab304fF11217C44702bb9E9732E7CF4` | [View](https://scan.initia.xyz/yominet-1/address/0x4BaDFb501Ab304fF11217C44702bb9E9732E7CF4) |
| **WETH** | `0xE1Ff7038eAAAF027031688E1535a055B2Bac2546` | [View](https://scan.initia.xyz/yominet-1/address/0xE1Ff7038eAAAF027031688E1535a055B2Bac2546) |

---

## System Contract Addresses

System contracts are **not deployed at fixed addresses**. They are registered in the World contract and resolved dynamically at runtime.

### How to Resolve a System Address

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

// Resolve any system by its string ID
async function getSystemAddress(systemId) {
  const hash = ethers.keccak256(ethers.toUtf8Bytes(systemId));
  const systemsComponent = await getSystemsComponent();
  const entities = await systemsComponent.getEntitiesWithValue(hash);
  if (entities.length === 0) throw new Error(`System not found: ${systemId}`);
  return ethers.getAddress(ethers.toBeHex(entities[0], 20));
}

// Example: resolve the Kami level system
const levelSystemAddr = await getSystemAddress("system.kami.level");
console.log("KamiLevelSystem:", levelSystemAddr);
```

> **Note:** Token contracts (WETH, ONYX, Kami721) have **fixed addresses** listed in the table above — they do not need dynamic resolution. Only system contracts require the resolver pattern shown here.

> For the full resolver with legacy fallback support, see the [Integration Guide](guide.md).

### Why Dynamic Resolution?

The MUD framework allows systems to be **upgraded** by deploying new contracts and updating the World registry. Hardcoding system addresses would break on upgrades. Always resolve from the World contract.

---

## Token Contracts

### ONYX (ERC-20)

The in-game currency token. Standard ERC-20 interface.

| Address |
|---------|
| [`0x4BaDFb501Ab304fF11217C44702bb9E9732E7CF4`](https://scan.initia.xyz/yominet-1/address/0x4BaDFb501Ab304fF11217C44702bb9E9732E7CF4) |

```javascript
const ONYX_ABI = [
  "function balanceOf(address) view returns (uint256)",
  "function approve(address spender, uint256 amount) returns (bool)",
  "function transfer(address to, uint256 amount) returns (bool)",
  "function allowance(address owner, address spender) view returns (uint256)",
];

const onyx = new ethers.Contract(
  "0x4BaDFb501Ab304fF11217C44702bb9E9732E7CF4",
  ONYX_ABI,
  signer
);

const balance = await onyx.balanceOf(walletAddress);
```

### Kami721 (ERC-721)

The Kami NFT contract. Standard ERC-721 interface with game-specific extensions.

| Address |
|---------|
| [`0x5d4376b62fa8ac16dfabe6a9861e11c33a48c677`](https://scan.initia.xyz/yominet-1/address/0x5d4376b62fa8ac16dfabe6a9861e11c33a48c677) |

```javascript
const KAMI721_ABI = [
  "function balanceOf(address) view returns (uint256)",
  "function ownerOf(uint256 tokenId) view returns (address)",
  "function approve(address to, uint256 tokenId)",
  "function setApprovalForAll(address operator, bool approved)",
  "function transferFrom(address from, address to, uint256 tokenId)",
];

const kami721 = new ethers.Contract(
  "0x5d4376b62fa8ac16dfabe6a9861e11c33a48c677",
  KAMI721_ABI,
  signer
);
```

---

## Related Pages

- [System IDs & ABIs](system-ids.md) — All system identifiers
- [Chain Configuration](chain.md) — Network details
- [Architecture Overview](../architecture.md) — How contracts interact

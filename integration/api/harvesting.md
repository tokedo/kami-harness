> **Doc Class:** Core Resource
> **Canonical Source:** Kamigotchi on-chain contracts on Yominet and the official repository (`Asphodel-OS/kamigotchi`).
> **Freshness Rule:** Verify mutable values against canonical sources before merge.

# Harvesting

Harvesting is the core resource-gathering mechanic in Kamigotchi. Players assign Kamis to harvest nodes in rooms to earn items and XP over time.

---

## harvest.start()

Start harvesting at a node.

| Property | Value |
|----------|-------|
| **System ID** | `system.harvest.start` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `kamiID` | `uint256` | Entity ID of the Kami to assign to the harvest |
| `nodeIndex` | `uint32` | Index of the harvest node in the current room |
| `taxerID` | `uint256` | Taxer entity ID (pass `0` for player-initiated harvests) |
| `taxAmt` | `uint256` | Tax amount (pass `0` for player-initiated harvests) |

### Description

Assigns a Kami to a harvest node. For player-initiated harvests, pass `0, 0` for the `taxerID` and `taxAmt` parameters (taxation is for system-level use).

Kamis must be in the same room as the harvest node and not already harvesting elsewhere.

For batching multiple Kamis to the same node, use `executeBatched()` (see below).

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = [
  "function executeTyped(uint256 kamiID, uint32 nodeIndex, uint256 taxerID, uint256 taxAmt) returns (bytes)",
  "function executeBatched(uint256[] kamiIDs, uint32 nodeIndex, uint256 taxerID, uint256 taxAmt) returns (bytes[])",
];
const system = await getSystem("system.harvest.start", ABI, operatorSigner);

// Single Kami
const tx = await system.executeTyped(kamiId, harvestNodeIndex, 0, 0);
await tx.wait();
console.log("Harvesting started for Kami");

// Batch — multiple Kamis on the same node
const txBatch = await system.executeBatched(
  [kamiId1, kamiId2, kamiId3],
  harvestNodeIndex,
  0, 0
);
await txBatch.wait();
console.log("Harvesting started for 3 Kamis");
```

### Notes

- The `nodeIndex` parameter corresponds to the room index — each harvest node shares an index with its room (see [Game Data](../game-data.md#harvest-nodes)).
- A newly purchased or minted Kami starts in the account's current room.
- Kamis already assigned to a harvest will cause the transaction to revert.
- **There is no node capacity limit** — any number of Kamis can harvest at the same node simultaneously. No need to check availability.
- Nodes may have additional requirements (e.g., minimum Kami level) enforced by `LibNode.verifyRequirements()` — check node data before starting.
- Move to the room first with [account.move()](account.md#move) before starting a harvest.
- **Batch variant:** `executeBatched(uint256[] kamiIDs, uint32 nodeIndex, uint256 taxerID, uint256 taxAmt)` starts harvests for multiple Kamis in one transaction.

#### Tax System

The `taxerID` and `taxAmt` parameters attach a **tax entity** to the harvest. Tax entities (`LibTax`) redirect a percentage of the harvest bounty to a recipient on collection. The tax rate is specified in **basis points** (1e4 precision) and is capped at **2000 (20%)**. Each tax entity stores an owner (the harvest ID), a recipient (`taxerID`), and the rate (`taxAmt`). For player-initiated harvests, pass `0, 0` — taxation is intended for system-level integrations (e.g., NPC or faction harvests). Multiple tax entities can be attached to the same harvest; all are deducted from the bounty on collect.

---

## harvest.stop()

Stop active harvests.

| Property | Value |
|----------|-------|
| **System ID** | `system.harvest.stop` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `id` | `uint256` | Harvest entity ID to stop |

### Description

Stops a single active harvest. The Kami is released and can be reassigned. Any uncollected rewards are collected automatically (collect-and-stop).

For batch stopping, use `executeBatched()` (see below).

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = [
  "function executeTyped(uint256 id) returns (bytes)",
  "function executeBatched(uint256[] ids) returns (bytes[])",
];
const system = await getSystem("system.harvest.stop", ABI, operatorSigner);

// Single harvest
const tx = await system.executeTyped(harvestId);
await tx.wait();
console.log("Harvest stopped");

// Batch — multiple harvests
const txBatch = await system.executeBatched([harvestId1, harvestId2]);
await txBatch.wait();
console.log("Harvests stopped");
```

### Notes

- Stopping a harvest collects rewards automatically.
- **Batch variant:** `executeBatched(uint256[] ids)` stops multiple harvests in one transaction — more gas-efficient than stopping one by one.
- **Allow-failure variants:** `executeAllowFailure(bytes)` and `executeBatchedAllowFailure(uint256[] ids)` silently return `0` instead of reverting when a harvest fails validation (e.g., wrong state, on cooldown, unhealthy Kami). Useful for fire-and-forget batch operations.

```javascript
// Batch stop with allow-failure — skips invalid harvests instead of reverting
const ABI_AF = [
  "function executeBatchedAllowFailure(uint256[] ids) returns (bytes[])",
];
const system = await getSystem("system.harvest.stop", ABI_AF, operatorSigner);

const tx = await system.executeBatchedAllowFailure([harvestId1, harvestId2, harvestId3]);
await tx.wait();
```

---

## harvest.collect()

Collect rewards from harvests.

| Property | Value |
|----------|-------|
| **System ID** | `system.harvest.collect` |
| **Wallet** | 🎮 Operator |
| **Gas** | Default |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `id` | `uint256` | Harvest entity ID to collect from |

### Description

Collects accumulated rewards (items, XP) from a single harvest. Can be called while the harvest is still active (partial collection).

For batch collecting, use `executeBatched()` (see below).

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = [
  "function executeTyped(uint256 id) returns (bytes)",
  "function executeBatched(uint256[] ids) returns (bytes[])",
];
const system = await getSystem("system.harvest.collect", ABI, operatorSigner);

// Single harvest
const tx = await system.executeTyped(harvestId);
await tx.wait();
console.log("Rewards collected!");

// Batch — multiple harvests
const txBatch = await system.executeBatched([harvestId1, harvestId2, harvestId3]);
await txBatch.wait();
console.log("All rewards collected!");
```

### Notes

- Rewards accumulate over time — collecting early is fine but yields less.
- **Batch variant:** `executeBatched(uint256[] ids)` collects from multiple harvests in one transaction — more gas-efficient.
- **Allow-failure variants:** `executeAllowFailure(bytes)` and `executeBatchedAllowFailure(uint256[] ids)` silently return `0` instead of reverting when a harvest fails validation. Useful for collecting from many harvests where some may be in an invalid state.

```javascript
// Batch collect with allow-failure — skips invalid harvests instead of reverting
const ABI_AF = [
  "function executeBatchedAllowFailure(uint256[] ids) returns (bytes[])",
];
const system = await getSystem("system.harvest.collect", ABI_AF, operatorSigner);

const tx = await system.executeBatchedAllowFailure([harvestId1, harvestId2, harvestId3]);
await tx.wait();
```

---

## harvest.liquidate()

Liquidate another player's harvest.

| Property | Value |
|----------|-------|
| **System ID** | `system.harvest.liquidate` |
| **Wallet** | 🎮 Operator |
| **Gas** | **7,500,000** (hardcoded) |

### Parameters

| Name | Type | Description |
|------|------|-------------|
| `victimHarvID` | `uint256` | Entity ID of the victim's harvest to liquidate |
| `killerID` | `uint256` | Entity ID of your Kami performing the liquidation |

### Description

Uses your Kami to liquidate another player's harvest. This is a competitive PvP mechanic — the liquidator's Kami must be strong enough to overpower the harvest. Rewards may be split between the liquidator and the original harvester.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ABI = [
  "function executeTyped(uint256 victimHarvID, uint256 killerID) returns (bytes)",
];
const system = await getSystem("system.harvest.liquidate", ABI, operatorSigner);

const tx = await system.executeTyped(targetHarvestId, myKamiId, {
  gasLimit: 7_500_000, // Required — complex liquidation logic
});
await tx.wait();
console.log("Harvest liquidated!");
```

### Notes

- **Gas limit of 7,500,000 is required** — the liquidation logic is computationally expensive.
- This is a PvP action — use wisely!

#### Kill Log & Economy

On a successful liquidation, `LibKill` produces a **KillLog** with the following fields:

| Field | Description |
|-------|-------------|
| `bounty` | Total MUSU in the victim's harvest at time of kill |
| `salvage` | MUSU returned to the victim's account (based on victim's Power stat) |
| `spoils` | MUSU awarded to the attacker's harvest (based on attacker's Power stat) |
| `strain` | Health cost component from the kill |
| `karma` | Health damage to the attacker, calculated from `target.Violence - source.Harmony` scaled by affinity efficacy. If the attacker's Harmony exceeds the target's Violence, karma is zero |

The attacker also receives 1 **Obol** (item 1015) per kill. The total health **recoil** to the attacker is derived from both strain and karma.

**Animosity** determines whether a liquidation can succeed: it computes a health threshold from `Phi(ln(source.Violence / target.Harmony))` scaled by a configurable ratio and affinity efficacy. If the victim's current HP is above this threshold, the liquidation reverts.

#### Liquidation Requirements Checklist

All of the following must be true or the transaction reverts:

1. **Target harvest is active** — `victimHarvID` must be a valid, active harvest entity
2. **Your Kami is harvesting** — `killerID` must be in `"HARVESTING"` state
3. **Same node** — Your Kami must be actively harvesting on the **same harvest node** as the victim
4. **Same room** — Your account must be in the same room as the harvest node
5. **Healthy** — Your Kami must have health > 0 (synced at call time)
6. **Off cooldown** — Your Kami's liquidation cooldown must have expired
7. **Sufficient Violence** — Your Kami's Violence stat must meet the threshold to overpower the victim (`LibKill.isLiquidatableBy`). Reverts with `"kami lacks violence (weak)"` if insufficient

#### On Success

- The victim's harvest bounty is split — a portion goes to the victim as "salvage" (based on their Power), the rest becomes "spoils" for the attacker (based on attacker's Power)
- The attacker takes health "recoil" damage from the kill (based on strain and karma)
- The victim receives **salvage** (MUSU) based on their Power stat, plus **XP equal to the salvage amount**
- The victim's Kami dies (state → `"DEAD"`) and their harvest stops
- The attacker's liquidation cooldown is reset

---

## Harvest Lifecycle

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ harvest.     │     │ harvest.     │     │ harvest.     │
│ start()      │────▶│ collect()    │────▶│ stop()       │
│              │     │ (partial)    │     │ (auto-collects│
└─────────────┘     └─────────────┘     │  + sets RESTING)│
                                         └─────────────┘
```

**Important:** `harvest.stop()` automatically collects any remaining bounty, then sets the Kami to RESTING state with a zeroed balance. You **cannot** call `harvest.collect()` after stopping — the contract requires the Kami to be in HARVESTING state for collection. Always collect *before* stopping if you want a separate collect step, or simply call stop (which auto-collects).

---

## Yield & Timing

Harvest rewards accumulate continuously over time. The yield formula below determines harvest output.

### How Bounty Accrues

Harvest output (called **bounty**) is calculated each time a harvest is **synced** (on collect or stop). The formula in `LibHarvest.calcBounty()` is:

```
bounty = (rate × duration × boost) / precision
```

Where:
- **rate** = `fertility + intensity` (in MUSU/second, at 1e6 precision)
- **duration** = seconds since last sync (`block.timestamp - lastSyncTimestamp`)
- **boost** = base boost + bonus from skills/equipment (`HARV_BOUNTY_BOOST`)
- **precision** = combined precision divisor from config

### Fertility (Base Rate)

Fertility is the core harvest rate, driven by the Kami's **Power** stat:

```
fertility = (precision × power × ratio × efficacy) / 3600
```

- **Power** — Kami's total Power stat (base + bonuses from skills/equipment)
- **ratio** — Core fertility multiplier from `KAMI_HARV_FERTILITY` config
- **efficacy** — Affinity matchup bonus (see below)

### Efficacy (Affinity Matching)

Efficacy modifies fertility based on how well the Kami's **body and hand affinities** match the node's affinity:

- **Matching affinity** → Positive efficacy boost (harvest more)
- **Neutral affinity** → Reduced bonus
- **Opposing affinity** → Negative efficacy shift (harvest less)
- **Normal trait** → Gets half the matching bonus

Nodes can have one or two affinities (e.g., "Eerie, Scrap"). The system picks the most favorable matchup order — body affinity has more impact than hand affinity.

Matching a node's affinity to a Kami's body/hand types increases efficacy.

### Intensity (Time Bonus)

Intensity is a secondary yield component that **grows over time** and scales with the Kami's **Violence** stat:

```
intensity = (precision × (violence_base + minutes_elapsed) × boost) / (ratio × 3600)
```

- **violence_base** = config multiplier × Kami's Violence stat
- **minutes_elapsed** = minutes since the last intensity reset (rounded down)
- **boost** = base + `HARV_INTENSITY_BOOST` from skills/equipment

Intensity increases the longer a Kami stays on a node. It resets when a harvest is started or moved.

### Collecting Bounty

- Bounty accrues **continuously** — there is no "ready" timer or fixed interval.
- **Collecting early** gives you whatever has accumulated so far; **collecting later** gives more.
- Calling `harvest.collect()` syncs the bounty (snapshots the accrued amount), resets the duration timer, and adds the bounty to the account's inventory.
- The Kami's **Health decreases** over time while harvesting (strain). If health reaches zero, the Kami is liquidated.
- Calling `harvest.stop()` automatically collects any remaining bounty before stopping.
- **Block time:** Yominet has ~1 second block times, so duration-based calculations update approximately once per second.

### Harvest Node Data

Each node has a **Yield Index** (the item index granted — `1` for MUSU on most nodes, or `2` for VIPP/VIP Paper on certain deeper nodes) and a **Scav Cost** (the stamina cost for scavenging at that node). Nodes also have a **Level Limit** — some beginner nodes cap the Kami level that can earn XP there.

See the [Harvest Nodes table](../game-data.md#harvest-nodes) for per-node affinity, yield index, and scav cost values.

### Summary

| Factor | Stat | Effect |
|--------|------|--------|
| Fertility | Power | Higher Power → faster base MUSU rate |
| Efficacy | Body/Hand affinity | Matching node affinity → bonus yield |
| Intensity | Violence | Higher Violence + longer time → bonus yield |
| Bounty boost | Skills/Equipment | Percentage multiplier on total output |
| Strain | Health/Harmony | Higher Harmony/skills → slower health drain |

> **Stamina:** Each room move costs stamina. Current stamina is readable via `getAccount(accountId).currStamina`. Stamina regenerates over time (rate configured on-chain via `ACCOUNT_STAMINA` config).

---

## Feeding During Harvest

There is no dedicated `harvest.feed()` system. To heal a Kami while it is harvesting, use the [kami.item.use()](kami.md#kamiitemuse) system (`system.kami.use.item`) with a healing item (e.g., food). This restores the Kami's health without interrupting the active harvest. Health is readable via `getKami()`; at zero HP a harvesting Kami is liquidated.

## Health Monitoring

### Understanding Stat Fields

Each Kami stat (health, power, harmony, violence) is a struct with four `int32` fields:

```solidity
struct Stat { int32 base; int32 shift; int32 boost; int32 sync; }
```

| Field | Meaning |
|-------|---------|
| `base` | Innate value from the Kami's traits and level |
| `shift` | Permanent modifications (from leveling, equipment changes, etc.) |
| `boost` | Temporary buffs from equipment, skills, and active effects |
| `sync` | The last on-chain synced value — updated when the chain processes a harvest collect, stop, or other state-changing action |

**Effective stat value** = `((1000 + boost) × (base + shift)) / 1000`, floored to 0 if negative. The `boost` field is a **percentage multiplier in parts per thousand** — for example, `boost = 100` means +10%, `boost = -200` means -20%. It is **not** simply added to base + shift. The `sync` field reflects the last computed on-chain snapshot and may lag behind the real-time effective value during active harvests (since health drains continuously but only syncs on actions).

### Monitoring During Harvest

```javascript
// Poll Kami health during an active harvest
const getter = new ethers.Contract(getterAddr, GETTER_ABI, provider);

async function checkHealth(kamiEntityId) {
  const kami = await getter.getKami(kamiEntityId);
  const h = kami.stats.health;
  const effective = Math.max(0, ((1000 + Number(h.boost)) * (Number(h.base) + Number(h.shift))) / 1000);
  console.log(`Health: ${effective} (base=${h.base} shift=${h.shift} boost=${h.boost} sync=${h.sync})`);
  return effective;
}

// Poll every 60 seconds and heal if health drops below 50
const interval = setInterval(async () => {
  const hp = await checkHealth(kamiEntityId);
  if (hp < 50) {
    console.log("Health low — feeding Kami");
    const feedTx = await feedSystem.executeTyped(kamiEntityId, 11302); // Cheeseburger (HP+50)
    await feedTx.wait();
  }
}, 60_000);
```

> **Note:** Yominet has ~1 second block times. Polling every 30-60 seconds is sufficient for health monitoring. Health drain rate depends on the Kami's Harmony stat and active skills — higher Harmony means slower drain.

### Health Thresholds

- **0** — Kami is dead. Harvest stops automatically. Must revive before further use.
- **< 50** — HP below this leaves little margin before 0 (death).
- **> 100** — Safe range for most harvests.

Health drain (strain) is calculated by `LibKami.calcStrain` each time a harvest is synced:

```
strain = ceil(amt × core × boost / (precision × (harmony + nudge)))
```

Where:
- **amt** = MUSU earned (the bounty being collected), NOT time elapsed
- **core** = base strain multiplier from config
- **boost** = strain boost modifier (skills/equipment can reduce this)
- **precision** = config precision divisor
- **harmony** = Kami's effective Harmony stat
- **nudge** = small constant to prevent division by zero

Config key: `KAMI_HARV_STRAIN`. Higher Harmony means less strain per unit of bounty collected. Strain is proportional to harvest output — a Kami earning more MUSU takes more health damage.

### Resting Recovery

When a Kami is in RESTING state (after `harvest.stop()`), it recovers HP over time via `LibKami.calcRecovery`:

```
metabolism = (precision × (harmony + nudge) × ratio × boost) / 3600
recovery = (duration × metabolism) / 10^9
```

Where:
- **harmony** = Kami's effective Harmony stat
- **nudge** = small constant to prevent division by zero
- **ratio** = recovery rate multiplier from config
- **boost** = recovery boost modifier (skills/equipment)
- **duration** = seconds spent resting since last sync

Config key: `KAMI_REST_METABOLISM`. Higher Harmony means faster HP recovery while resting.

---

## Related Pages

- [Kami](kami.md) — Kami stats that affect harvest performance
- [Account — move()](account.md#move) — Move to the room with harvest nodes
- [Echo](echo.md) — Force-emit room data to see harvest nodes
- [Items & Crafting](items-and-crafting.md) — Items earned from harvesting
- [Goals & Scavenge](goals-and-scavenge.md) — Scavenge bars tied to harvest nodes

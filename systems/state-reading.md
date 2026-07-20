# State Reading

How to query game state and project values between on-chain syncs.
Covers state queries and local projection formulas.

## Overview

Three read paths:

### 1. Kamibots API (V1 primary)

Pre-computed game-meaningful state — projected HP, earnings, node
occupancy, strategy status. No local computation or interpretation needed.

See [integration/kamibots/](../integration/kamibots/)

**V1 agents use this.** External dependency — will be replaced by a
local interpretation layer on top of the MUD sync in Phase 2.

### 2. Local headless sync client (planned)

A previous draft here pointed to a local MUD indexer
(`integration/sync/`, now removed): it targeted MUD v2, while
Kamigotchi runs MUD classic (solecs) — the drafted stack would have
indexed nothing. The planned replacement is a headless run of the
game's own client sync stack (snapshot/stream service + RPC
event-replay fallback into a local ECS mirror). That mirror is also
the only complete path for discovery queries (node occupancy, room
presence): most components are `BareComponent`, so on-chain reverse
lookup reverts.

### 3. Direct RPC (fallback)

The patterns documented below. Still useful for:
- One-off queries when the sync isn't running
- `staticCall` checks (e.g., quest completability)
- Understanding the data model and entity structure
- Kamiden indexer data (marketplace, kill feed, activity stream)

### Projection formulas (always needed)

**Regardless of which read method you use**, HP/stamina/bounty values are
lazy-synced on-chain — they only update when an action is executed. Between
actions, the agent **must project** current values locally using the
formulas in this file + elapsed time. Both the synced database and direct
RPC calls return the same last-synced snapshots.

---

### Direct RPC data sources

Three data sources for direct reads:

| Source | Cost | Freshness | Use for |
|---|---|---|---|
| **GetterSystem** | Free (view call) | Last sync only | Kami stats, account room/stamina, level, XP |
| **Component reads** | Free (view call) | Last sync only | Inventory balances, ownership lists, state enum, equipment |
| **Kamiden indexer** | Free (gRPC) | Near-real-time | Marketplace listings/offers, trade history, kill feed, activity stream |

## Kami State

### Get all my Kamis

```javascript
// component.id.kami.owns maps accountId → kamiEntityId[]
const ownsKamiAddr = await getComponentAddress("component.id.kami.owns");
const ownsKami = new ethers.Contract(ownsKamiAddr,
  ["function getEntitiesWithValue(uint256) view returns (uint256[])"], provider);
const kamiIds = await ownsKami.getEntitiesWithValue(accountId);
```

### Current state

```javascript
const kami = await getter.getKami(kamiId);
// kami.state: "RESTING" (1), "HARVESTING" (2), "DEAD" (3), "721_EXTERNAL" (4)
```

Actions available by state:
- `RESTING` → can harvest, equip, level, quest, move
- `HARVESTING` → can collect, stop, feed (use item), get liquidated
- `DEAD` → revive available (33 ONYX via `system.kami.onyx.revive`)
- `721_EXTERNAL` → unstaked NFT, not in game

### Stats (synced values)

```javascript
const h = kami.stats.health;
// Access by index — ethers.js .shift conflicts with Array.shift
const [base, shift, boost, sync] = [Number(h[0]), Number(h[1]), Number(h[2]), Number(h[3])];

// Effective (max) stat
const maxHP = Math.max(0, Math.floor((1000 + boost) * (base + shift) / 1000));
// sync = last on-chain HP snapshot (only accurate at moment of last action)
```

Same pattern for `kami.stats.power`, `kami.stats.harmony`, `kami.stats.violence`.

### Level, XP, affinities

```javascript
kami.level   // BigInt — current level
kami.xp      // BigInt — current XP
kami.affinities // string[] — e.g. ["EERIE", "SCRAP"] (body, hand)
kami.room    // uint32 — room index
kami.index   // uint32 — token index (for entity ID derivation)
```

### Equipment

```javascript
// Enumerate all equipment on a Kami
const ownsEquipAddr = await getComponentAddress("component.id.equipment.owns");
const ownsEquip = new ethers.Contract(ownsEquipAddr,
  ["function getEntitiesWithValue(uint256) view returns (uint256[])"], provider);
const equipIds = await ownsEquip.getEntitiesWithValue(kamiId);

// For each, read item index
const indexItemAddr = await getComponentAddress("component.index.item");
const indexItem = new ethers.Contract(indexItemAddr,
  ["function getValue(uint256) view returns (uint32)"], provider);
for (const eqId of equipIds) {
  const itemIdx = await indexItem.getValue(eqId);
}
```

## Projected HP

GetterSystem returns the last-synced HP (`sync` field). Between syncs, HP
changes continuously — draining while harvesting, recovering while resting.

### If HARVESTING: project HP downward

```
projectedHP = syncHP - projectedStrain
```

Strain is proportional to **bounty earned**, not time directly. Project bounty
first, then derive strain:

```
// Project bounty since last sync
fertility = Power * 1500 * Efficacy / 3600          // Musu/sec at 1e6 precision
intensity = 1e6 * (Violence * 5 + minutesElapsed) * 10 / (480 * 3600)
rate = fertility + intensity
projectedBounty = rate * elapsedSeconds * boost / 1e9

// Project strain from that bounty
strain = ceil(projectedBounty * 6500 * (1000 + strainBoost) / (1e6 * (Harmony + 20)))
```

Simplified strain-per-Musu ratio: `~6.5 / (Harmony + 20)`.

| Harmony | Strain per Musu | Musu before losing 50 HP |
|---|---|---|
| 5 | 0.26 | ~192 |
| 10 | 0.217 | ~231 |
| 20 | 0.163 | ~308 |
| 30 | 0.13 | ~385 |

### If RESTING: project HP upward

```
healRate = (Harmony + 20) * 0.6 / 3600    // HP/sec (base, before boost)
projectedHP = min(maxHP, syncHP + healRate * elapsedSeconds)
```

A Harmony-10 Kami heals ~18 HP/hr. Full heal from 0 → ~2.8h at Harmony 10.

### When is syncHP accurate?

`syncHP` updates on: harvest.start, harvest.collect, harvest.stop,
kami.use.item (feeding), level up, equip/unequip. Immediately after any of
these, `syncHP == actualHP`. The drift grows with elapsed time.

## Account State

### Room and stamina

```javascript
const account = await getter.getAccount(accountId);
account.room         // uint32 — current room index
account.currStamina  // int32 — last-synced stamina
```

**Stamina is lazy-synced** — it regenerates over time on-chain but the
`currStamina` value only updates on actions (move, craft). Project:

```
projectedStamina = min(maxStamina, syncStamina + regenRate * elapsedSeconds)
```

Regen rate and max are on-chain configs (`ACCOUNT_STAMINA`). Each room move
costs stamina (varies by room).

### Inventory (item balances)

```javascript
// Derive inventory entity, read ValueComponent
function getInventoryEntityId(accountId, itemIndex) {
  return BigInt(ethers.keccak256(ethers.solidityPacked(
    ["string", "uint256", "uint32"],
    ["inventory.instance", accountId, itemIndex]
  )));
}

const valueAddr = await getComponentAddress("component.value");
const valueComp = new ethers.Contract(valueAddr,
  ["function getValue(uint256) view returns (uint256)"], provider);

// Common checks
const musu = await valueComp.getValue(getInventoryEntityId(accountId, 1));     // Musu
const onyx = await valueComp.getValue(getInventoryEntityId(accountId, 100));   // Onyx Shards
const tickets = await valueComp.getValue(getInventoryEntityId(accountId, 10)); // Gacha Tickets
```

Returns `0` for items never held — safe to call for any index.

### Enumerate all held items

```javascript
const ownsInvAddr = await getComponentAddress("component.id.inventory.owns");
const ownsInv = new ethers.Contract(ownsInvAddr,
  ["function getEntitiesWithValue(uint256) view returns (uint256[])"], provider);
const invIds = await ownsInv.getEntitiesWithValue(accountId);

const indexItemAddr = await getComponentAddress("component.index.item");
const indexItem = new ethers.Contract(indexItemAddr,
  ["function getValue(uint256) view returns (uint32)"], provider);

for (const invId of invIds) {
  const itemIdx = await indexItem.getValue(invId);
  const qty = await valueComp.getValue(invId);
  // itemIdx → qty
}
```

## Harvest State

### Is my Kami harvesting?

```javascript
const kami = await getter.getKami(kamiId);
const isHarvesting = kami.state === "HARVESTING";
```

### Harvest entity ID and node

```javascript
// Harvest ID is deterministic from Kami ID
const harvestId = BigInt(ethers.keccak256(
  ethers.solidityPacked(["string", "uint256"], ["harvest", kamiId])
));
```

To find which node a Kami is harvesting on, read the harvest entity's
`component.index.node` or `IDRoomComponent`. Alternatively, track the
`nodeIndex` passed to `harvest.start()` locally — it doesn't change
during a harvest session.

### Estimated bounty accrual

Project using Fertility + Intensity formulas (see [Projected HP](#projected-hp)
for the rate computation). Multiply `rate * elapsed * boost / 1e9` for
projected Musu earned since last collect/start.

### Time since last collect/start

Read `TimeStartComponent` or `TimeLastComponent` on the harvest entity:

```javascript
const timeAddr = await getComponentAddress("component.time.start");
const timeComp = new ethers.Contract(timeAddr,
  ["function getValue(uint256) view returns (uint256)"], provider);
const startTime = await timeComp.getValue(harvestId);
const elapsed = Math.floor(Date.now() / 1000) - Number(startTime);
```

## World Awareness

### Current room

```javascript
const account = await getter.getAccount(accountId);
const roomIndex = account.room; // uint32
```

### Who else is on my node?

This query has no direct endpoint. Options:

1. **Kamiden stream** — subscribe to `HarvestEnds` and `Kills` events to
   track active harvesters. No direct "list harvesters on node X" endpoint.
2. **Echo system** — call `system.echo.room` to force-emit room data. Costs
   gas (a transaction, not a view call). The emitted events include occupants,
   but parsing requires indexer integration.
3. **Component scan** — query `component.state` for all Kamis with value
   `"HARVESTING"`, then check their node. Expensive — requires enumerating
   entities.

Starter nodes have a level limit of 15.

### Day/night phase

Local computation, no RPC needed:

```javascript
function getDayPhase(timestamp = Math.floor(Date.now() / 1000)) {
  const hour = Math.floor(timestamp / 3600) % 36;
  if (hour < 12) return "DAYLIGHT";   // phase 1
  if (hour < 24) return "EVENFALL";   // phase 2
  return "MOONSIDE";                  // phase 3
}
```

36-hour cycle. Some quests and mechanics are phase-gated.

### NPC shop prices (GDA projection)

Some NPC shops use Gradual Dutch Auction pricing — price rises on purchase,
decays over time. The agent can project current price locally:

```
price = startPrice * decayFactor^(timeSinceLastPurchase)
```

Exact decay params are on-chain config per listing. For static-price shops,
prices are fixed in the shop listing data.
See [catalogs/shop-listings.csv](../catalogs/shop-listings.csv).

## Quest & Progress State

### Enumerate active quests

Quest instance entity IDs are deterministic:
```javascript
function getQuestEntityId(questIndex, accountId) {
  return BigInt(ethers.keccak256(ethers.solidityPacked(
    ["string", "uint32", "uint256"],
    ["quest.instance", questIndex, accountId]
  )));
}
```

To check if a quest is active, read its `StateComponent`:
```javascript
const stateAddr = await getComponentAddress("component.state");
const stateComp = new ethers.Contract(stateAddr,
  ["function getValue(uint256) view returns (string)"], provider);
const questState = await stateComp.getValue(getQuestEntityId(questIndex, accountId));
// Non-empty string = active. Empty/revert = not accepted.
```

To enumerate **all** active quests, query `component.id.quest.owns`:
```javascript
const ownsQuestAddr = await getComponentAddress("component.id.quest.owns");
const ownsQuest = new ethers.Contract(ownsQuestAddr,
  ["function getEntitiesWithValue(uint256) view returns (uint256[])"], provider);
const questIds = await ownsQuest.getEntitiesWithValue(accountId);
```

### Objective progress

Quest objectives track deltas from acceptance (snapshot-based). The agent
must compare current state (e.g., Musu harvested, items collected) against
the snapshot taken at accept time. Objective data is stored in quest
components — read `component.value` on objective sub-entities.

### Completable quests

Try `quest.complete()` via `staticCall` — if it doesn't revert, the quest
is completable. This is a free view-call check:
```javascript
try {
  await questSystem.executeTyped.staticCall(questEntityId);
  // Quest is completable
} catch {
  // Objectives not yet met
}
```

## Marketplace State

Marketplace data requires the **Kamiden indexer** — listing and offer entity
IDs are non-deterministic (generated via `world.getUniqueEntityId()`).

### Active listings

```javascript
import { createChannel, createClient } from "nice-grpc-web";
import { KamidenServiceDefinition } from "./proto.js";

const channel = createChannel("https://api.prod.kamigotchi.io");
const client = createClient(KamidenServiceDefinition, channel);

const { Listings } = await client.getKamiMarketListings({ Size: 500 });
// Each listing: .OrderID, .KamiIndex, .Price (wei), .SellerAccountID, .Expiry
```

### Active offers

```javascript
const { Bids } = await client.getKamiMarketBids({ Size: 500 });
// Each bid: .OrderID, .KamiIndex, .Price (wei), .BidType (1=collection, 2=specific), .Quantity
```

### Real-time stream

```javascript
for await (const response of client.subscribeToStream({})) {
  for (const feed of response.Feed ?? []) {
    // feed.KamiMarketLists, feed.KamiMarketBuys, feed.Kills, feed.HarvestEnds, etc.
  }
}
```

No authentication required. Reconnect on stream close (~5s retry).
See [integration/api/indexer.md](../integration/api/indexer.md) for full method list.

## Setup Pattern

State-read skeleton — reads an account and its kamis in one pass:

```javascript
async function perceive(getter, valueComp, ownsKami, accountId, kamiIds) {
  const now = Math.floor(Date.now() / 1000);
  const account = await getter.getAccount(accountId);

  const kamis = await Promise.all(kamiIds.map(async (id) => {
    const k = await getter.getKami(id);
    const hp = [Number(k.stats.health[0]), Number(k.stats.health[1]),
                Number(k.stats.health[2]), Number(k.stats.health[3])];
    const maxHP = Math.max(0, Math.floor((1000 + hp[2]) * (hp[0] + hp[1]) / 1000));
    const harmony = Math.max(0, Math.floor(
      (1000 + Number(k.stats.harmony[2])) * (Number(k.stats.harmony[0]) + Number(k.stats.harmony[1])) / 1000
    ));
    const power = Math.max(0, Math.floor(
      (1000 + Number(k.stats.power[2])) * (Number(k.stats.power[0]) + Number(k.stats.power[1])) / 1000
    ));

    // Project current HP
    let projectedHP = hp[3]; // sync value
    if (k.state === "HARVESTING") {
      const strainPerMusu = 6.5 / (harmony + 20);
      // Rough projection; sync value used as placeholder
      projectedHP = hp[3]; // use sync as lower bound estimate
    } else if (k.state === "RESTING") {
      const healRate = (harmony + 20) * 0.6 / 3600;
      // elapsedSinceSync would need TimeLastComponent read — omitted for brevity
      projectedHP = Math.min(maxHP, hp[3]); // conservative
    }

    return {
      id, state: k.state, level: Number(k.level), xp: Number(k.xp),
      maxHP, syncHP: hp[3], projectedHP, power, harmony,
      affinities: k.affinities, room: k.room,
    };
  }));

  const musu = Number(await valueComp.getValue(
    getInventoryEntityId(accountId, 1)));
  const onyx = Number(await valueComp.getValue(
    getInventoryEntityId(accountId, 100)));

  return {
    account: { room: account.room, stamina: Number(account.currStamina) },
    kamis, musu, onyx, phase: getDayPhase(now), timestamp: now,
  };
}
```

The returned object bundles the last-synced snapshot with locally projected
values.

## Future: Processed State Layer

Currently the agent must compute projected values locally. A future
middleware layer may provide pre-computed state via a REST API, eliminating
manual projection. Until then, the formulas in this file are the source of
truth for between-sync state estimation.

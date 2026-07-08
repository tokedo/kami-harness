# Kamibots API Integration — V1 Primary

> **V1 primary integration** for both world-state reads and strategy
> execution. This is what V1 agents use.

Base URL: `https://api.kamibots.xyz`

## V1 vs Long-Term Architecture

```
V1 (now):     Agent ──► Kamibots API ──► game state + strategy execution
Long-term:    Agent ──► local MUD sync + interpretation layer ──► game state
              Agent ──► direct contract calls ──► strategy execution
```

Kamibots API is a **V1 convenience**, not a permanent dependency. The
long-term architecture is fully self-contained: the agent reads raw ECS
state from the local MUD sync ([Phase 2](../sync/)), interprets it using
game logic (formulas in `systems/` files), and executes transactions
directly against the World contract.

## What Kamibots Does NOT Cover

Direct game actions — feed, move, revive, craft, equip, attack, scavenge
— are done via **direct on-chain calls** using patterns in
[integration/api/](../api/). Kamibots is for repeated strategy loops +
pre-computed state reads only.

> Game action endpoints (feed, revive, move, etc.) are planned for agent
> key access in a future Kamibots update but are not yet whitelisted.

---

## 1. Auth Flow

Three steps, all programmatic. No browser needed.

### Step 1: Register with wallet signature

Sign `"Register for Kamibots: <unix_timestamp>"` with EIP-191 `personal_sign`.
Timestamp must be within 5 minutes of server time (replay protection).

```
POST /api/agent/register
Content-Type: application/json

{
  "walletAddress": "0xYourWalletAddress",
  "signature": "0x...",
  "message": "Register for Kamibots: 1712019600",
  "label": "My Agent"
}
```

Response:
```json
{
  "apiKey": "kamibots_abc123...",
  "privyId": "did:privy:abc123",
  "isNewUser": true,
  "hasOperatorKey": false
}
```

**Save both `apiKey` and `privyId` immediately.** The API key is shown
exactly once. `privyId` is required for strategy start/stop calls.

```javascript
// ethers.js v5
const timestamp = Math.floor(Date.now() / 1000);
const message = `Register for Kamibots: ${timestamp}`;
const signature = await wallet.signMessage(message);

const res = await fetch('https://api.kamibots.xyz/api/agent/register', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ walletAddress: wallet.address, signature, message, label: 'My Agent' })
});
const { apiKey, privyId } = await res.json();
```

### Step 2: Store operator key

The operator key signs on-chain transactions. Encrypted at rest (AES-256-GCM).

```
POST /api/agent/operator-key
X-Agent-Key: kamibots_<key>

{ "operatorKey": "0x..." }
```

### Step 3: All subsequent requests

All endpoints (except `/register`) require:
```
X-Agent-Key: kamibots_<key>
```

Additional API keys (max 10 per account):
```
POST /api/agent/keys
X-Agent-Key: kamibots_<key>

{ "label": "My Second Agent" }
```

Revoke a key: `DELETE /api/agent/keys/:keyId`

---

## 2. Rate Limits

| Type | Limit |
|---|---|
| Read endpoints | 60 req/min per key |
| Write endpoints | 10 req/min per key |
| Exceeded | `429 Too Many Requests` |

Rate limits apply **per API key**, not per account. Multiple keys allow
proportionally higher throughput.

---

## 3. Tier System

| Tier | Tax Rate | Base Slots | How to Get |
|---|---|---|---|
| FREE | 12% | 1 | Default |
| PRO | 6% | 11 | Hold insignia NFT (`0x014C4861F5f19b4c86f26657Dd40c1a18539D11A`) |
| GUILD | 6% | 11 | Guild membership |
| TEAM | 0.001% | 999 | Team membership |

Extra slots: +1 per Strategy NFT held (`0xE10498F8C0589D0C17F4C9e28a59B5BFccA582a8`).
After NFT purchase/transfer, call `POST /api/agent/tier/refresh`.

Tax rates are enforced server-side — cannot be overridden.

### Strategy availability by tier

| Strategy | FREE | PRO | GUILD | TEAM | Max Active | Notes |
|---|---|---|---|---|---|---|
| `harvestAndRest` | yes | yes | yes | yes | per slot | Single-kami timed / HP-based rests |
| `harvestAndFeed` | yes | yes | yes | yes | per slot | Single-kami automatic feeding |
| `rest_v3` | yes | yes | yes | yes | 5/account | Multi-kami, predator detection |
| `auto_v2` | no | max 2 | max 3 | unlimited | see tier | Autonomous multi-kami |
| `bodyguard` | no | no | max 1 | max 1 | 1/account, up to 8 guards | Node protection |
| `craft` | no | max 1 | no | max 1 | 1/account | Autonomous crafting |

> Multi-kami strategies consume multiple slots. A `rest_v3` with 3 kamis
> uses 3 slots. Check `GET /api/agent/tier` before starting.

### Check tier and slots

```
GET /api/agent/tier
```

Response: `{ "tier": "PRO", "taxRate": 600, "maxStrategies": 11, "usedSlots": 3, "remainingSlots": 8 }`

---

## 4. Strategy Types

### harvestAndRest — single kami, timed or HP-based rests

Available: all tiers.

```json
{
  "strategyType": "harvestAndRest",
  "kamiId": 45,
  "nodeId": 9,
  "config": {
    "farmInterval": 1800,
    "restInterval": 1800,
    "initialCooldown": 60,
    "startHarvestId": "0x...",
    "stopHarvestId": "0x...",
    "useHpBasedRest": false,
    "hpThresholdLow": 30,
    "hpThresholdHigh": 80
  }
}
```

If `useHpBasedRest: true`, rests when HP < `hpThresholdLow`%, resumes
at `hpThresholdHigh`%. If `false`, uses fixed `farmInterval`/`restInterval` timers.

### harvestAndFeed — single kami, automatic feeding

Available: all tiers.

```json
{
  "strategyType": "harvestAndFeed",
  "kamiId": 45,
  "nodeId": 9,
  "config": {
    "farmInterval": 1800,
    "restInterval": 1800,
    "initialCooldown": 60,
    "startHarvestId": "0x...",
    "stopHarvestId": "0x...",
    "enableFeedInterval": true,
    "feedInterval": 3600,
    "foodType": 11302,
    "enableFailsafeRest": true,
    "failsafeRestDuration": 600
  }
}
```

`foodType` uses item IDs (see [Food Items](#8-food-items) below).
`enableFailsafeRest`: if feeding fails (out of food), rest instead.

### rest_v3 — multi-kami, predator detection

Available: all tiers. Max 5 active per account.

```json
{
  "strategyType": "rest_v3",
  "config": {
    "kamiIndices": [45, 46, 47],
    "nodeId": "0x...",
    "predatorTeam": {
      "eerie": 100, "scrap": 101, "insect": 102, "normal": 103
    },
    "restV3Preferences": [
      {
        "kamiIndex": 45,
        "autoCollect": true,
        "bountyCollectThreshold": 10000,
        "reviveOnDeath": true,
        "safetyMargin": 5
      }
    ]
  }
}
```

`safetyMargin`: 0–10. Percentage of max HP above predator threshold.
Higher = safer, less farming time.

### auto_v2 — autonomous multi-kami harvesting

Available: PRO (max 2), GUILD (max 3), TEAM (unlimited).

```json
{
  "strategyType": "auto_v2",
  "config": {
    "kamiIndices": [45, 46, 47],
    "harvestPreferences": [
      {
        "kamiIndex": 45,
        "regenMethod": "FEED",
        "autoCollect": true,
        "bountyCollectThreshold": 10000,
        "reviveOnDeath": true,
        "safetyMargin": 0
      }
    ]
  }
}
```

`regenMethod`: `"FEED"` or `"REST"`.

### bodyguard — guard squad on a node

Available: GUILD/TEAM only. Max 1 per account, up to 8 guard kamis.

```json
{
  "strategyType": "bodyguard",
  "config": {
    "guardKamiIndices": [50, 51, 52, 53],
    "friendAccountNames": ["ally1", "ally2"],
    "guardPreferences": [
      {
        "guardIndex": 50,
        "strategy": "KAMIKAZE",
        "regenMethod": "FEED",
        "reviveOnDeath": true,
        "autoCollect": true,
        "bountyCollectThreshold": 5000,
        "maintenanceFeedEnabled": true,
        "maintenanceFeedThresholdPercent": 80,
        "skipCursedPredators": false
      }
    ]
  }
}
```

Guard strategies: `KAMIKAZE` (aggressive, attacks all enemies) or
`SENTINEL` (passive/defensive).

### craft — autonomous crafting

Available: PRO/TEAM only. Max 1 per account. No kamiId needed.

```json
{
  "strategyType": "craft",
  "config": {
    "recipes": [
      { "recipeIndex": 0, "craftAmount": 10, "priority": 1, "name": "Basic Potion" },
      { "recipeIndex": 2, "craftAmount": 5, "priority": 2, "name": "Advanced Potion" }
    ]
  }
}
```

Runs recipes in priority order, spending stamina efficiently.

---

## 5. Strategy Lifecycle

### Start

```
POST /api/strategies/start
X-Agent-Key: kamibots_<key>

{
  "strategyType": "harvestAndRest",
  "kamiId": 45,
  "nodeId": 9,
  "config": { ... },
  "keyData": { "privy_id": "did:privy:..." }
}
```

**`keyData.privy_id` is required.** Agent middleware does NOT auto-inject
it — include it from the `/register` response.

`nodeId` must match the kami's current room. Check with
`GET /api/playwright/kami/:kamiId/slim` first.

Response: `{ "id": "uuid", "status": "RUNNING", "monitoringEndpoint": "/api/strategies/status/<kamiId>" }`

### Stop

```
DELETE /api/strategies/kami/:kamiId
X-Agent-Key: kamibots_<key>

{ "keyData": { "privy_id": "did:privy:..." } }
```

### Status (cached 15s)

```
GET /api/strategies/status/:kamiId
```

Response: `{ "kamiId": "45", "status": "RUNNING", "health": "HEALTHY", "uptime": 3600 }`

All strategies: `GET /api/strategies/status/all`

### Logs

```
GET /api/strategies/:containerId/logs?tail=30
```

### List active strategies

```
GET /api/agent/strategies
```

Response:
```json
{
  "strategies": [
    {
      "id": "uuid-string",
      "kami_id": "45",
      "strategy_type": "harvestAndRest",
      "status": "ACTIVE",
      "config": { ... },
      "vm_ip": "137.184.149.248",
      "created_at": "2026-04-01T12:00:00Z"
    }
  ]
}
```

> `status` is normalized to uppercase (`ACTIVE`, `PAUSED`, etc.) for
> consistency with other strategy endpoints. `config` and `vm_ip` are
> enriched from container records when available, and may be `null` if
> the container record was cleaned up.

### Get guild members

Returns all guild and team member account names. Useful for building a
dynamic friendly list (e.g. bodyguard `friendAccountNames`).
**Restricted to GUILD and TEAM tier.**

```
GET /api/agent/guild/members
X-Agent-Key: kamibots_<key>
```

Response:
```json
{
  "members": ["player1", "player2", "player3"]
}
```

> Use this to keep your bodyguard strategy's friend list up to date
> without hardcoding names.

---

## 6. State Read Endpoints

### Kami data — use playwright endpoints

| Endpoint | Returns | Bonuses | Harvest Info | Cache |
|---|---|---|---|---|
| `GET /api/playwright/kami/:kamiId/` | Full: stats, harvest, skills, traits, bonuses, progress | yes | yes | — |
| `GET /api/playwright/kami/:kamiId/slim` | Slim: stats, harvest, skills, bonuses (no traits/affinity) | yes | yes | — |
| `GET /api/playwright/kami/:kamiId/state` | State string only (HARVESTING, RESTING, etc.) | no | no | — |
| `GET /api/playwright/kamis/all` | All kamis in game: index, name, state, image (basic only) | no | no | 24h |
| `GET /api/kami/:kamiId` | On-chain basic: name, HP, room, stats, state | no | no | — |

The playwright endpoints return trait-based bonuses that affect harvest
rates, combat thresholds, recovery speed, and cooldowns; the on-chain
basic endpoints do not.

**Slim vs Full**: the slim endpoint omits `traits` (body/hand affinity,
trait names, per-trait stats); the full endpoint includes them.

**All kamis**: the `/playwright/kamis/all` endpoint returns basic
listing data (index, name, state) for every kami in the game. It does
NOT include stats, bonuses, or affinity. Use it to enumerate kami IDs,
then query individual kamis for details. Cached 24h.

Bonuses returned by playwright endpoints:

| Bonus | Affects |
|---|---|
| `bonuses.harvest.fertility` | Harvest rate |
| `bonuses.harvest.intensity` | Yield intensity |
| `bonuses.harvest.bounty` | Collection reward scaling |
| `bonuses.harvest.strain` | Farming duration limits |
| `bonuses.rest.metabolism` | HP recovery speed |
| `bonuses.general.cooldown` | Action cooldown reduction |
| `bonuses.attack.threshold` / `spoils` / `recoil` | Combat modifiers |
| `bonuses.defense.salvage` | Damage mitigation |

### Account and inventory

| Endpoint | Description | Cache |
|---|---|---|
| `GET /api/agent/inventory` | All items and balances | — |
| `GET /api/agent/tier` | Tier, tax rate, slot usage | — |
| `GET /api/accounts/:address` | Full account (inventory, kamis, stamina, stats) | 15s |
| `GET /api/accounts/:address/kamis` | List kamis by operator address | — |
| `GET /api/accounts/by-owner/:ownerAddress/kamis` | Kamis by owner wallet | 15s |

### Market and pricing

| Endpoint | Description | Cache |
|---|---|---|
| `GET /api/prices/latest` | Marketplace prices for all items | 3.3m |
| `GET /api/prices/item/:itemName` | Price history for item | 5m |
| `GET /api/npc-prices/live` | Live NPC shop prices (all) | — |
| `GET /api/npc-prices/item/:itemIndex` | NPC price for item | 60s |
| `GET /api/npc-prices/bulk/:itemIndex/:quantity` | Bulk NPC pricing | 30s |

### Game data catalogs

| Endpoint | Description | Cache |
|---|---|---|
| `GET /api/playwright/items` | All items with effects, requirements, drops | 24h |
| `GET /api/playwright/nodes` | All nodes with affinity, room, drops, requirements | 24h |
| `GET /api/playwright/rooms` | All room definitions | 24h |
| `GET /api/playwright/skills` | All skill definitions | 24h |
| `GET /api/playwright/traits` | All trait definitions | 24h |
| `GET /api/playwright/recipes/all` | Crafting recipes with ingredients and results | 12h |
| `GET /api/playwright/npc/all` | NPC shop listings | 5m |
| `GET /api/playwright/config` | Game configuration | 1h |

Force refresh (after game updates): `POST /api/playwright/<type>/refresh`
(available for items, nodes, rooms, skills, traits, kamis).

### Other lookups

| Endpoint | Description | Cache |
|---|---|---|
| `GET /api/kami/name/:name` | Look up kami by name | 5m |
| `GET /api/kami/:kamiId/harvestId` | Current harvest ID | — |
| `GET /api/playwright/kami/:kamiId/stop-harvest-id` | Stop/collect harvest ID | — |
| `GET /api/leaderboards/:type` | Leaderboards (harvest, kill) | 20m |
| `GET /api/killer-ranking` | Killer rankings | 1h |
| `GET /api/kami-rush` | Kami rush event data | 5m |

---

## 7. Error Handling

```json
{ "error": "No active operator key found.", "code": 400 }
```

| Code | Meaning |
|---|---|
| 400 | Missing or invalid parameters |
| 403 | Insufficient tier/slots, ownership validation failed |
| 404 | Kami/strategy not found |
| 409 | Strategy already running, or deletion in progress |
| 429 | Rate limit exceeded |
| 500 | Server-side failure |

---

## 8. Food Items

Use item IDs (not 0-based indices) when specifying `foodType` in
strategy configs.

| Name | Item ID | HP Restored |
|---|---|---|
| Gum | 11301 | 25 |
| Burger | 11302 | 50 |
| Candy | 11303 | 50 |
| Cookies | 11304 | 100 |
| Resin | 11311 | 35 |
| Honeydew | 11312 | 75 |
| Golden Apple | 11313 | 150 |
| Blue Pansy | 11314 | 25 |

---

## 9. Agent Checklist

1. Register → save `apiKey` + `privyId`
2. Store operator key
3. Check tier and available slots
4. Read kami state via playwright slim endpoint
5. Start strategy with `privy_id` in `keyData`
6. Monitor via status endpoint (15s cache)
7. Check inventory before feeding/crafting strategies

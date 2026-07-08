# Scavenging

Secondary loot system tied to harvest nodes. Harvest output fills a scavenge
bar; when full, claim for droptable rolls.

## How It Works

1. Kami harvests on a node → earns Musu
2. On collect or stop, harvest output is added to the node's **scavenge bar**
3. When accumulated points >= tier cost → tiers become claimable
4. Claim → rewards distributed (items, droptable rolls)
5. Droptable rolls require a **reveal** transaction (commit-reveal pattern)

Points = harvest output. More productive harvests fill the bar faster.

## Scavenge Bar

Each node has a scavenge bar with a **tier cost** — points needed per reward.

| Tier Cost | Node Type | Examples |
|---|---|---|
| 100 | Starter nodes | Misty Riverside, Tunnel of Trees |
| 200 | Mid-tier nodes | Forest paths, cave rooms |
| 300 | Advanced nodes | Deeper Forest Path, Airplane Crash |
| 500 | Premium nodes | Scrap Confluence, Techno Temple, Lotus Pool |

Higher tier cost = more harvesting per reward, but **rarer droptables**.

### Claimable Tiers

```
tiers = floor(currentPoints / tierCost)
remainingPoints = currentPoints % tierCost
```

Partial progress toward the next tier is preserved after claiming.

## Claiming Rewards

System: `system.scavenge.claim`

Each claimed tier distributes rewards from the node's reward configuration.
Multiple tiers claimed at once = rewards multiplied by tier count.

### Reward Types

- **Droptable rolls** — random loot via commit-reveal (most common)
- **Items** — direct item grants
- **Stats/bonuses** — stat modifications

### Commit-Reveal Flow

Droptable rewards create a **commit** that must be separately **revealed**:

1. **Claim** → commit created (stores which droptable, block number for seed)
2. **Reveal** (next transaction, different block) → random items distributed

The reveal must happen within **256 blocks** (~50 minutes). If missed, an
admin `forceReveal` can rescue stuck commits.

## Scavenge Value by Node Cost

Higher-cost nodes have rarer drops.

- **100-cost nodes**: frequent claims, common drops (quests may track
  `SCAV_CLAIM_NODE` or `DROPTABLE_ITEM_TOTAL`)
- **500-cost nodes**: infrequent claims, rare drops

Scavenge points = harvest output, so affinity-matched harvesting on a high-cost
node still fills the bar — it just takes longer per tier.

## Tracking Progress

Two entity types:

- **Instance** (per-account progress): `keccak256("scavenge.instance", "NODE", nodeIndex, accountId)` —
  read `Value` component to get accumulated points
- **Registry** (per-node config): `keccak256("registry.scavenge", "NODE", nodeIndex)` —
  used as the `scavBarID` argument when claiming

Compare instance points against the node's tier cost to check claimability.

## How to Execute

**Claim** — `system.scavenge.claim` (Operator wallet)
```
executeTyped(uint256 scavBarID)
```
- `scavBarID` = **registry** entity (node-level, shared): `keccak256("registry.scavenge", "NODE", nodeIndex)`
- Reverts if no tiers are claimable (points < tierCost)
- Returns commit IDs for any droptable rewards

**Reveal** — `system.droptable.reveal` (Operator wallet)
```
executeTyped(uint256[] commitIDs)
```
- Batch reveal: pass all pending commit IDs
- Must be called in a later block than the commit
- Items distributed directly to account inventory

### Entity IDs

```
scavBarId = keccak256("registry.scavenge", "NODE", nodeIndex)
```

## Cross-References

- Harvest output formulas: [harvesting.md](harvesting.md)
- Node catalog with scavenge costs: [catalogs/nodes.csv](../catalogs/nodes.csv)
- Scavenge droptables: [catalogs/scavenge-droptables.csv](../catalogs/scavenge-droptables.csv)
- Quest objectives that track scavenging: [quests.md](quests.md)

# Harvesting

Harvesting is an income loop. A Kami sits on a node, earns the node's
yield item (Musu on most nodes, VIPP on some) over time, takes HP strain,
and can be liquidated (killed) by another player's Kami on the same node.

## Lifecycle

```
START (kami + node) → accruing bounty, taking strain
  → COLLECT (take bounty, keep harvesting, reset cooldown)
  → STOP (take bounty, return to RESTING)
  → LIQUIDATED (killed by another player, lose most bounty)
```

Prerequisites for START: Kami is `RESTING`, off cooldown, HP > 0, account in
same room as node, node requirements met (e.g., level limit).

## Node Factors

### Affinity Match

Efficacy multiplier on Fertility (base income):

| Body + Hand match | Efficacy | Yield multiplier |
|---|---|---|
| Both match node | 1000 + 650 + 350 = **2000** | **2.0x** |
| Body matches, hand neutral | 1000 + 650 + 0 = **1650** | **1.65x** |
| Hand matches, body neutral | 1000 + 0 + 350 = **1350** | **1.35x** |
| Both neutral (NORMAL kami or node) | **1000** | **1.0x** |
| Body matches, hand mismatches | 1000 + 650 - 100 = **1550** | **1.55x** |
| Body mismatches, hand matches | 1000 - 250 + 350 = **1100** | **1.1x** |
| Both mismatch | 1000 - 250 - 100 = **650** | **0.65x** |

Affinity types: `EERIE`, `SCRAP`, `INSECT`, `NORMAL`.
- NORMAL Kami/node → always neutral (1.0x)
- Same non-NORMAL → Strong
- Different non-NORMAL → Weak

Dual-affinity nodes (e.g., "EERIE, SCRAP"): system picks best matchup order
for body (higher impact) vs hand.

### Scavenge Droptable Value

Nodes with higher scavenge cost have rarer droptables. Check
[catalogs/scavenge-droptables.csv](../catalogs/scavenge-droptables.csv) for
reward tables per node.

Higher scav cost (points to fill bar) = rarer drops. The costs in
[catalogs/nodes.csv](../catalogs/nodes.csv) at the upstream pin
(`04cb25f8`): 100 on the starter nodes (10 nodes), 200 (18), 300 (8),
400 (12), 500 (2), 600 (4) and 1000 (3) — the cave and castle nodes
cost twice what they did before that deploy data (e.g. Techno Temple,
Lotus Pool and Fungus Garden 1000).

Scavenge points = harvest output. So higher Fertility = faster scavenge fills.

### Node Yield Item

Each node pays its own yield item: `IndexItem` on the node, which the
harvest claim reads (`LibNode.getItem`). At the upstream pin
(`04cb25f8`) 15 of the 64 nodes pay VIPP (item index 2) — nodes 6, 18,
48, 49, 52, 58, 60, 61, 62, 65, 73, 75, 79, 83 and 88 — and the rest pay
Musu (item index 1): the `YieldIndex` column of
[catalogs/nodes.csv](../catalogs/nodes.csv). A stop or collect states the
item it paid per kami (`payouts[].item`); a liquidation's salvage (from
block 34,199,935) and spoils are in the node's yield item too. The
scavenge droptable determines secondary item drops; see the "Drops"
column.

### Level Restrictions

Some nodes have level caps (`Level Limit = 15` means only Kamis at or
below level 15). At the pin: 15 on the starter nodes 1, 2, 3, 29, 30 and
55; 35 on nodes 31, 35, 36, 47, 50, 56, 57 and 59 (the catalog's
`Level Limit` column). Check the node catalog before assigning.

### Occupancy & Liquidation Risk

If other Kamis are harvesting on the same node, your Kami can be liquidated.

## Bounty Accumulation

### Fertility (steady rate, Power-based)

```
Fertility = Power * 1500 * Efficacy / 3600
```

- Efficacy = affinity multiplier (see table above), default 1000
- Linear in Power: doubling Power doubles Fertility

### Intensity (ramping rate, Violence-based)

```
Intensity = 1e6 * (Violence * 5 + minutesElapsed) * 10 / (480 * 3600)
```

- Grows linearly with time (minutes since intensity reset)
- Small contribution early, significant over hours
- Resets on certain actions (equip changes)

### Total Bounty

```
Bounty = (Fertility + Intensity) * Duration * Boost / 1e9
```

- Duration = seconds since last sync
- Boost = 1000 base + skill/equipment bonuses

### Reference Output Rates

| Power | Efficacy | Approx Musu/hr (Fertility only) |
|---|---|---|
| 10 | 1000 (neutral) | ~15 |
| 10 | 2000 (perfect) | ~30 |
| 20 | 1000 (neutral) | ~30 |
| 20 | 2000 (perfect) | ~60 |

Intensity adds ~5-15% on top after the first hour, growing over time.

## Strain (HP Cost)

```
strain = ceil(harvestedAmount * 6500 * (1000 + strainBoost) / (1e6 * (Harmony + 20)))
```

Key insight: **strain scales with harvest output** — more Musu earned = more
HP lost. Harmony is the primary defense against strain.

### Strain-to-Bounty Ratio

For a Kami with Harmony H, base strain per Musu earned:

```
strain_per_musu ≈ 6.5 / (H + 20)
```

| Harmony | Strain per Musu | Musu before losing 50 HP |
|---|---|---|
| 5 | 0.26 | ~192 |
| 10 | 0.217 | ~231 |
| 15 | 0.186 | ~269 |
| 20 | 0.163 | ~308 |
| 30 | 0.13 | ~385 |

> Higher Harmony = longer harvest sessions before HP danger.

## Collect vs Stop Effects

### Collect Effects

Collecting triggers:
- Bounty transferred to account (split by tax if taxer set)
- XP = amount collected (feeds leveling)
- Scavenge bar incremented by harvest amount
- Cooldown resets (180s base)
- Harvest continues

### Stop Effects

Stopping does everything Collect does, plus ends the harvest → Kami goes to
`RESTING` and begins healing.

## Liquidation Risk

Another player's Kami can kill yours if:
1. Both Kamis are `HARVESTING` on the **same node**
2. Your HP has dropped below the kill threshold

### Kill Threshold

```
threshold = animosity(attacker.Violence, victim.Harmony) * efficacy * victim.maxHP
```

- Animosity uses a Gaussian CDF over ln(Violence/Harmony) — higher attacker
  Violence relative to your Harmony = higher threshold
- Affinity matchups modify efficacy (attacker hand vs victim body)

Low Harmony plus drained HP raises liquidation exposure to Violence-heavy
Kamis on the same node.

### Consequences of Liquidation

- **Your Kami dies** (state = `DEAD`, HP = 0)
- **Salvage**: you retain a small portion of bounty (scales with your Power)
- **Spoils**: attacker steals a portion (scales with attacker Power)
- **Remaining bounty is destroyed** (not transferred to anyone)
- **Revival costs 33 Onyx Shards** and only restores 33 HP

### Defensive Mechanics

- High Harmony + low Violence = hard to liquidate (high effective threshold
  from defender side, low animosity from attacker perspective)
- Skills in **Guardian** tree increase defense threshold and salvage ratio
- Skills in **Enlightened** tree reduce strain

Starter nodes have a level limit of 15, and eight deeper nodes one of 35
(see Level Restrictions).

## Tax System

When starting a harvest, optionally set a taxer (e.g., guild leader). The
taxer receives a percentage of all collected bounty. If no tax needed, set
`taxAmt = 0`.

## Side Effects on Collection

Every collect/stop also triggers:
1. **XP** = Musu collected (1:1)
2. **Scavenge** = bar increment by harvest amount → claim when tier is full
3. **Score** = account leaderboard increment

## Estimating Harvest Duration

Two-step estimate using the tables above:

1. **Safe Musu** = (HP * 0.5) / strain_per_musu (from Strain-to-Bounty table)
2. **Safe hours** = safe_musu / musu_per_hour (from Reference Output Rates table)

Example: Power=10, Harmony=10, HP=50:
```
strain_per_musu = 6.5 / (10 + 20) = 0.217
safe_musu = 25 / 0.217 ≈ 115 Musu
At ~15 Musu/hr (Power=10, neutral): safe_hours ≈ 115 / 15 ≈ 7.7 hours to 50% HP
```

## Node Catalog Reference

See [catalogs/nodes.csv](../catalogs/nodes.csv) for all 64 nodes with:
- Affinity type (for matching)
- Level limits
- Yield item (`YieldIndex`: 1 Musu, 2 VIPP)
- Scavenge cost
- Drop descriptions

## How to Execute

All harvest calls use the **Operator** wallet. Gas is default except liquidate.

### System IDs

| Action | System ID |
|---|---|
| Start | `system.harvest.start` |
| Stop | `system.harvest.stop` |
| Collect | `system.harvest.collect` |
| Liquidate | `system.harvest.liquidate` |

### Harvest Entity ID

Derived deterministically from the Kami entity ID — no on-chain lookup needed:
```
harvestId = keccak256(abi.encodePacked("harvest", kamiEntityId))
```
One harvest per Kami at a time. Use `harvestId` for stop/collect/liquidate calls.

### Function Signatures

**start** — `executeTyped(uint256 kamiID, uint32 nodeIndex, uint256 taxerID, uint256 taxAmt)`
Pass `0, 0` for taxerID/taxAmt (player-initiated). Batch variant:
`executeBatched(uint256[] kamiIDs, uint32 nodeIndex, uint256 taxerID, uint256 taxAmt)`

**stop** — `executeTyped(uint256 harvestId)`
Auto-collects bounty. Batch: `executeBatched(uint256[] ids)`.
Allow-failure variant: `executeBatchedAllowFailure(uint256[] ids)` — skips invalid harvests.

**collect** — `executeTyped(uint256 harvestId)`
Partial collection, harvest continues. Batch: `executeBatched(uint256[] ids)`.
Allow-failure variant: `executeBatchedAllowFailure(uint256[] ids)`.

**liquidate** — `executeTyped(uint256 victimHarvID, uint256 killerID)`
**Gas limit: 7,500,000 required.** Both Kamis must be harvesting on the same node.

### Gas Notes

- Start/stop/collect: default gas limit is fine
- Liquidate: hardcode `gasLimit: 7_500_000` — complex PvP logic
- Gas price is flat `0.0025 gwei`, cost is negligible

Full details: [integration/api/harvesting.md](../integration/api/harvesting.md)

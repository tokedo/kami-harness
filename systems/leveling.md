# Leveling & Skills

How leveling, skill points, and skill trees work.

## XP Sources

Kami XP comes from:
- **Harvesting** — XP = Musu collected (1:1), on collect or stop
- **Kill salvage** — victim Kami gets XP = salvage amount
- **Item effects** — some items grant XP when used on a Kami

> Account XP (from movement, crafting) is a **separate pool** and does NOT
> feed Kami leveling.

## Level-Up Cost

XP cost to advance from current level:

```
cost = floor(40 * 1.259^(level - 1))
```

XP is **consumed** on level-up — surplus is retained.

| Level | XP to next | Cumulative |
|---|---|---|
| 1 | 40 | 40 |
| 2 | 50 | 90 |
| 3 | 63 | 153 |
| 4 | 80 | 233 |
| 5 | 100 | 333 |
| 6 | 126 | 459 |
| 7 | 159 | 618 |
| 8 | 200 | 818 |
| 9 | 252 | 1,070 |
| 10 | 317 | 1,387 |
| 15 | 1,007 | 5,530 |
| 20 | 3,198 | 17,330 |
| 25 | 10,162 | 53,000 (approx) |
| 30 | 32,285 | 163,000 (approx) |

### Level-Up Requirements

Requirements to level up:
- Kami is `RESTING` (required)
- `currentXP >= levelCost`
- **Batch levels**: if XP covers multiple levels, call `level()` repeatedly
  (one level per call, no batch function)

Level-cap note:
- Leveling past a node's level limit locks the Kami out of that node.

## Skill Points

Each level-up grants **1 skill point**. New Kamis start with 1 SP at level 1.

All skills currently cost **1 SP per upgrade level**.

### Respec

Costs 1 **Respec Potion** (item 11403). Refunds all skill points for that
Kami. Full reset — all skills removed, all bonuses cleared.

## Skill Trees

4 trees, each with **6 tiers** of 3 skills = 72 total skills.

Config defines 8 tier slots (0–7), but only tiers 1–6 have deployed skills.
Tier 0 is unlocked at 0 points (no skills there), tier 7 (95 points) has no
skills currently. The agent only needs to plan around tiers 1–6.

| Tree | Focus |
|---|---|
| **Predator** | Violence, attack threshold, spoils, cooldown |
| **Enlightened** | Resting recovery, harvest bounty, strain reduction |
| **Guardian** | Harmony, defense threshold, salvage, health |
| **Harvester** | Power, harvest fertility/bounty, strain reduction |

### Tier Gates

Must invest N total tree points before skills at that tier unlock:

| Tier | Tree Points Required | Skills |
|---|---|---|
| 1 | 5 | 3 per tree |
| 2 | 15 | 3 per tree |
| 3 | 25 | 3 per tree (mutually exclusive — pick 1) |
| 4 | 40 | 3 per tree |
| 5 | 55 | 3 per tree |
| 6 | 75 | 3 per tree (mutually exclusive — pick 1) |

Tree points = total SP spent in that tree (each skill costs 1, so
tree points = number of skill upgrades in tree).

### Tier 3 and Tier 6 Exclusions

At tiers 3 and 6, the three skills are **mutually exclusive** — choosing one
locks out the other two in that tier. Only respec can undo the choice.

## Skill Effects

Skills grant bonuses via these effect types:

| Key | Effect | Used by |
|---|---|---|
| `SHS` | +Health (shift) | Guardian |
| `SPS` | +Power (shift) | Harvester |
| `SVS` | +Violence (shift) | Predator |
| `SYS` | +Harmony (shift) | Guardian |
| `HFB` | Harvest Fertility boost (%) | Harvester |
| `HIB` | Harvest Intensity boost (Musu/hr) | Guardian |
| `HBB` | Harvest Bounty boost (%) | Enlightened, Harvester |
| `ATS` | Attack threshold shift (%) | Predator |
| `ATR` | Attack threshold ratio (%) | Predator |
| `ASR` | Attack spoils ratio (%) | Predator |
| `DTS` | Defense threshold shift (%) | Guardian |
| `DTR` | Defense threshold ratio (%) | Guardian, Harvester |
| `DSR` | Defense salvage ratio (%) | Guardian |
| `RMB` | Resting recovery boost (%) | Enlightened |
| `SB` | Strain boost (%) | Enlightened, Harvester (negative = less strain) |
| `CS` | Cooldown shift (seconds) | Predator (negative = shorter cooldown) |

Percent effects have precision 3 (×1000 in storage).

## How to Execute

**Level up** — `system.kami.level` (Operator wallet)
```
executeTyped(uint256 kamiID)
```
- Kami must be `RESTING`
- Must have `XP >= levelCost`
- Grants 1 skill point

**Upgrade skill** — `system.skill.upgrade` (Operator wallet)
```
executeTyped(uint256 holderID, uint32 skillIndex)
```
- `holderID` = Kami entity ID (for Kami skills)
- Kami must be `RESTING`
- Must meet tier gate requirement
- Must not violate exclusions

**Respec** — `system.skill.respec` (Operator wallet)
```
executeTyped(uint256 targetID)
```
- Consumes 1 Respec Potion (item 11403)
- Refunds all SP, clears all skill bonuses

## Cross-References

- Skill catalog: [catalogs/skills.csv](../catalogs/skills.csv)
- XP from harvesting: [harvesting.md](harvesting.md)
- Stat formulas (how boosts apply): [accounts.md](accounts.md)

---

## MCP Tx Accounting & Procedure (calibrated 2026-04-28)

**No on-chain batching exists for level-up or skill allocation.** Every
level-up, every single skill point, and every item use is its own tx.
The `*_batch` MCP tools are server-side wrappers — they save MCP
round-trips and provide unified error handling, but they do **not**
fold multiple operations into one on-chain tx.

### Tool truth table

| MCP tool | on-chain tx model | use when |
|---|---|---|
| `use_item_batch(kami_id, item_id, count=N)` | N txs (`system.kami.use.item`), one per item | Only way to use multiple of the same item in one MCP call. |
| `use_account_item(item_id, amount=N)` | N txs (`system.account.use.item`) | Account-level items only (stamina ice cream, VIPP). NOT for kami XP potions. |
| `level_up_kami(kami_id)` | 1 tx (`system.kami.level`) | Single level-up. |
| `level_to(kami_id, target_level=N)` | (target − current) txs (`system.kami.level`) | Single-kami level-ups, no skill alloc needed. |
| `upgrade_skill(kami_id, skill_index)` | 1 tx (`system.skill.upgrade`) | One SP at a time. |
| `allocate_skills(kami_id, skill_plan)` | sum-of-points txs (`system.skill.upgrade`) | Single-kami SP plan. |
| **`level_and_allocate_batch(targets=[...])`** | per kami: (target − current) `level` txs **+** sum-of-points `skill.upgrade` txs | Handles many kamis in one MCP call. |

`level_and_allocate_batch` runs the level + allocate flow in one MCP
round-trip with structured per-kami result and per-kami error capture.

### Calibrated XP grants per item

Verified empirically on the calibration operator (2026-04-28) against a
fresh kami:

| Item | Index | XP per use |
|---|---:|---:|
| Fortified XP Potion | **11411** | **50,000** |
| Greater XP Potion | **11402** | TBD (not yet measured) |

### Cumulative XP cost L1 → L_N

From `cost = floor(40 * 1.259^(level - 1))`. Verified empirically:
**L1 → L32 = 194,613 XP** (matches floor calc to within 1 XP).

| Target level | Cumulative XP from L1 | Cumulative SP earned (incl. starter) |
|---:|---:|---:|
| 5  |    232 |  5 |
| 10 |  1,069 | 10 |
| 15 |  3,721 | 15 |
| 20 | 12,116 | 20 |
| 25 | 38,679 | 25 |
| 30 | 122,723 | 30 |
| **32** | **~194,613** | **32** |
| 33 | ~245,083 | 33 |

So 4 Fortified XP Potions = 200K XP = exactly the budget for L1 → L32
(with ~5K leftover toward L32 → L33).

### Worked example — L1 → L32, 0/16/16/0 allocation (tx accounting)

For a SCRAP-bodied L1 kami at 0/0/0/0, going to a 0/16/16/0 guardian
build, with 4× Fortified XP Potions in account inventory:

**Pre-flight (2 read calls):**
```
get_inventory(account=...)              # confirm 4× item 11411
get_kami_state(kami_id=N, account=...)  # confirm RESTING, lvl=1, xp=0
```

**Execute (2 MCP calls, 67 on-chain txs):**
```
# 1. Deposit 200K XP — 4 on-chain txs
use_item_batch(account=..., kami_id=N, item_id=11411, count=4)

# 2. Level + allocate — 31 level txs + 32 skill txs = 63 on-chain txs
level_and_allocate_batch(account=..., targets=[{
  "kami_id": N,
  "target_level": 32,
  "skill_plan": [
    {"skill_index": 311, "points": 5},   # Guardian T1 — Defensiveness max
    {"skill_index": 312, "points": 5},   # Guardian T1 — second tier-1 max (G=10 → T2 unlocks at 5)
    {"skill_index": 323, "points": 5},   # Guardian T2 (G=15 → T3 unlocks)
    {"skill_index": 331, "points": 1},   # Guardian T3 mutex pick
    {"skill_index": 212, "points": 5},   # Enlightened T1 (E=5 → T2 unlocks)
    {"skill_index": 222, "points": 5},   # Enlightened T2
    {"skill_index": 223, "points": 5},   # Enlightened T2 (E=15 → T3 unlocks)
    {"skill_index": 232, "points": 1}    # Enlightened T3 mutex pick
  ]
}])
```

**Post-verify (1 read):**
```
get_kami_state(kami_id=N)               # confirm lvl 32, 0 SP unspent
```

### Tier-gate ordering proof (skill_plan above)

Each entry adds points cumulatively in its tree. Tier gates are:
T1=0, T2=5, T3=15, T4=25, T5=40, T6=55 tree points.

| step | skill | tree | tree pts after | gate met? |
|---|---|---|---:|---|
| 311×5 | Guardian T1 | G | 5 | T2 ✓ |
| 312×5 | Guardian T1 | G | 10 | (still T2) |
| 323×5 | Guardian T2 | G | 15 | T3 ✓ |
| 331×1 | Guardian T3 mutex | G | 16 | done |
| 212×5 | Enlightened T1 | E | 5 | T2 ✓ |
| 222×5 | Enlightened T2 | E | 10 | (still T2) |
| 223×5 | Enlightened T2 | E | 15 | T3 ✓ |
| 232×1 | Enlightened T3 mutex | E | 16 | done |

Total: 32 SP exactly. Order is safe.

### Tx-count formula for any plan

```
tx_count = N_potions
         + (target_level - current_level)        # level-ups
         + sum(skill_plan[i].points)             # skill upgrades
```

For the 4-potion → L32 → 0/16/16/0 case: 4 + 31 + 32 = **67 on-chain txs**.

Wall-clock budget on the calibration operator: ~3 sec/tx average → ~3.5
min for the full sequence. Gas cost is negligible (0.0025 gwei flat).

### Failure modes to expect

- `use_item_batch` returns `{used: K, planned: N, success: false}` if
  any of the N potion uses fails on chain (e.g. inventory insufficient,
  RPC blip beyond retry budget). Used count is authoritative.
- `level_and_allocate_batch` returns per-kami `{leveled, allocated,
  error}`. If `target_level` exceeds available XP, it levels as far
  as it can; the subsequent skill plan still runs but `upgrade_skill`
  txs that need more SP than the kami has will fail individually.
- Pre-flight reads: `get_inventory` and `get_kami_state` confirm
  inventory, RESTING state, and current level/XP before the batch.

### Concurrency rule — serialize writes on one operator wallet

**Do not run two write-tx MCP calls in parallel against the same
operator wallet.** Observed 2026-04-28 during calibration: parallel
`use_item_batch` calls against two kamis on the same operator returned
a `Connection reset by peer` on one of them with `used: 0`, while the
other succeeded. Likely cause is nonce contention or RPC keepalive
collision — two signers competing for the same nonce slot.

Safe pattern:
- **Multi-kami level + allocate**: pass all kamis in a single
  `level_and_allocate_batch(targets=[...])` call. The MCP server
  serializes internally per-kami. Confirmed clean on a 2-kami batch
  (62 levels + 64 skill txs over ~6 min, no errors).
- **Multi-kami item-use**: call `use_item_batch` **sequentially**, one
  kami at a time. There is no multi-kami variant; serialize at the
  client (do not fan out parallel MCP calls).
- Reads (`get_kami_state`, `get_inventory`, etc.) are safe to fan out —
  they don't sign txs.

When a parallel-write attempt does fail with a connection error,
**verify state first** (`get_inventory` + `get_kami_state`) before
retrying. The MCP returns `used: 0` truthfully in the cases observed,
but trust-but-verify is cheap.

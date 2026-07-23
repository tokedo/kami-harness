# Gacha & Sacrifice

Minting, rerolling, sacrifice, and the pity system.

## Minting New Kamis

Spend **Gacha Tickets** (item 10) to create new Kamis.

### Process (Commit-Reveal)

1. **Mint** (commit) — spend tickets, new Kamis added to gacha pool
2. **Reveal** (separate transaction) — random Kamis drawn from pool and
   assigned to your account

The Kamis you receive are random from the entire pool — not necessarily the
ones just created.

### Constraints

- Max **5 mints per transaction**
- Must have sufficient Gacha Tickets
- Reveal must happen within **256 blocks** (~4 minutes on Yominet's ~1s blocks) of commit

### Kami Stats at Creation

New Kamis start with:

| Attribute | Value |
|---|---|
| Level | 1 |
| XP | 0 |
| Skill Points | 1 |
| State | `RESTING` |
| Health base | ~50 (varies by traits) |
| Power base | ~10 (varies by traits) |
| Violence base | ~10 (varies by traits) |
| Harmony base | ~10 (varies by traits) |
| Slots stat | 0 base (varies by traits — most Kamis get +1 from traits) |

Stats are modified by random trait assignments. Each Kami gets 5 traits
(face, hand, body, background, color) selected by weighted random from a
trait registry. Traits add deltas to base stats.

> Note: the Slots **stat** base is 0 (traits typically add +1). This is
> separate from the equipment system's `DEFAULT_CAPACITY` constant (1),
> which is a floor on usable equipment slots. See [equipment.md](equipment.md).

### Affinities

Each Kami gets:
- **Body affinity** — from body trait
- **Hand affinity** — from hand trait

Types: `EERIE`, `SCRAP`, `INSECT`, `NORMAL`.
If both match → `PURE` breed. Otherwise `MIXED`.

## Rerolling

Exchange existing Kamis for random new ones.

### Process

1. **Reroll** (commit) — your Kamis go into the gacha pool, spend Reroll
   Tokens (item 11)
2. **Reveal** — receive the same number of random Kamis from the pool

Each Kami deposited costs 1 Reroll Token.

### Reroll Counter

Each Kami tracks how many times it has been rerolled. This counter increments
each time a Kami is withdrawn from the pool.

Rerolling a Kami discards its progress — level, skill points, and skills are
all lost.

## Sacrifice

**Permanently burn** a Kami in exchange for a random item reward.

### Process (Commit-Reveal)

1. **Sacrifice** (commit) — Kami is permanently destroyed (NFT burned,
   state = DEAD, ownership cleared)
2. **Reveal** — random item from sacrifice droptable distributed

**Irreversible.** Sacrificed Kamis cannot be revived.

### Kami Requirements

- Must be owned by your account
- Must be in `RESTING` state
- One Kami per transaction

### Pity System

The pity system guarantees better rewards at fixed intervals. Each account
tracks a running sacrifice counter.

| Interval | Droptable |
|---|---|
| Every 100 sacrifices | `droptable.sacrifice.rare` (guaranteed rare+) |
| Every 20 sacrifices | `droptable.sacrifice.uncommon` (guaranteed uncommon+) |
| Otherwise | `droptable.sacrifice.normal` (standard) |

**Rare pity takes precedence** when both thresholds align (e.g., sacrifice
#100 uses rare, not uncommon).

### Pity Counter

The pity counter increments per sacrifice; see thresholds above.
- At 18/20, 2 more sacrifices reach the uncommon+ threshold
- At 95/100, 5 more reach the rare+ threshold

## Obtaining Tickets and Tokens

### Gacha Tickets (item 10)

Sources:
- **NPC shop** — buy from NPC merchants
- **Auction** — GDA-priced auction (target: 32,000 Musu, see [npc-shops.md](npc-shops.md))
- **Quest rewards** — some quests grant tickets
- **Public/WL mint** — buy with ETH (if enabled)

### Reroll Tokens (item 11)

Sources:
- **NPC shop** — buy from NPC merchants
- **Auction** — GDA-priced auction (target: 50 Onyx, see [npc-shops.md](npc-shops.md))
- **Quest rewards** — some quests grant tokens

## How to Execute

### Mint

**Commit** — `system.kami.gacha.mint` (Owner wallet)
```
executeTyped(uint256 amount)
```
- Max amount: 5
- Deducts `amount` Gacha Tickets

**Reveal** — `system.kami.gacha.reveal` (anyone can call)
```
reveal(uint256[] commitIDs)   // NOT executeTyped; execute() reverts
```
- Must be in a different block than commit
- Reveal within 256 blocks

### Reroll

**Commit** — `system.kami.gacha.reroll` (Owner wallet)
```
reroll(uint256[] kamiIDs)
```
- Kamis must be `RESTING` and owned by you
- Deducts `kamiIDs.length` Reroll Tokens

**Reveal** — same as mint reveal

### Sacrifice

**Commit** — `system.kami.sacrifice.commit` (Operator wallet)
```
executeTyped(uint32 kamiIndex)
```
- Kami must be `RESTING` and owned by you
- Kami is **permanently destroyed** on commit

**Reveal** — `system.kami.sacrifice.reveal` (Operator wallet)
```
executeTyped(uint256[] commitIDs)
```
- Must be in a different block
- Item reward distributed to account

## Cross-References

- Gacha Ticket auction pricing: [npc-shops.md](npc-shops.md)
- Kami stats and affinities: [accounts.md](accounts.md)
- New Kami stats/handling: [harvesting.md](harvesting.md), [leveling.md](leveling.md)
